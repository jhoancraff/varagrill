"""
Vistas del flujo de facturacion: pre-factura (vista previa de cuenta sin
efecto fiscal), factura (documento fiscal con IVA desglosado) y cuentas por
cobrar (abonos contra facturas con saldo pendiente).

Reutiliza la logica de descuento de inventario de api_views.py
(_load_preparation_structure / _compute_pedido_ingredient_needs) para no
duplicar el arbol de recetas/subrecetas, y VGPago (ya extendido con un FK
opcional a factura) para los abonos, asi el cuadre de caja diario en
reportes.py sigue funcionando sin cambios.
"""
import json
import logging
from decimal import Decimal, InvalidOperation

from django.db import models, transaction
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .api_views import (
    BILLABLE_ORDER_STATES,
    _compute_pedido_ingredient_needs,
    _compute_preparation_cost_map,
    _load_preparation_structure,
    _snapshot_costo_venta_detalles,
)
from .auth_helpers import _auth_response, _is_admin_user, _is_cajera_user, _is_owner_or_contador_user
from .impresion_lpd import imprimir_factura_caja, imprimir_prefactura_caja
from .models import (
    VGCliente,
    VGCorrelativoFiscal,
    VGDatosFiscalesEmisor,
    VGFactura,
    VGFacturaLinea,
    VGIngrediente,
    VGMetodoPago,
    VGMovimientoInventario,
    VGOrdenCobro,
    VGPago,
    VGPedido,
    VGPreFactura,
    VGPreFacturaLinea,
)
from .tasa_cambio import obtener_tasa_actual

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------
def _porcentaje_iva_default():
    emisor = VGDatosFiscalesEmisor.objects.first()
    return emisor.porcentaje_iva_default if emisor else Decimal('16.00')


def _resolve_cliente(data):
    """
    Devuelve (cliente, error_message). Si viene cliente_id, debe existir ya.
    Si no, usa/crea uno por nombre (o "Consumidor Final" si no se indica
    ninguno), igual que pedido_create_view hace para pedidos rapidos.
    """
    cliente_id = data.get('cliente_id')
    if cliente_id not in [None, '']:
        try:
            return VGCliente.objects.get(pk=int(cliente_id)), None
        except (TypeError, ValueError, VGCliente.DoesNotExist):
            return None, 'El cliente indicado no existe.'

    nombre = str(data.get('cliente_nombre', '') or '').strip() or 'Consumidor Final'
    tipo_documento = str(data.get('cliente_tipo_documento', '') or '').strip().upper()
    numero_documento = str(data.get('cliente_numero_documento', '') or '').strip()
    if tipo_documento and tipo_documento not in {clave for clave, _ in VGCliente.TIPOS_DOCUMENTO}:
        return None, 'El tipo de documento del cliente no es valido.'

    cliente, created = VGCliente.objects.get_or_create(
        nombre__iexact=nombre,
        defaults={'nombre': nombre, 'tipo_documento': tipo_documento, 'numero_documento': numero_documento},
    )
    if not created and numero_documento and not cliente.numero_documento:
        cliente.tipo_documento = tipo_documento
        cliente.numero_documento = numero_documento
        cliente.save(update_fields=['tipo_documento', 'numero_documento'])
    return cliente, None


def _resolve_moneda(data):
    """
    Devuelve (moneda, error_message). La moneda de la cuenta no se elige
    aparte: se toma directo del método de pago seleccionado en Cobro
    (VGMetodoPago.moneda) — así una cuenta que se va a pagar con un método
    en bolívares se muestra/imprime solo en bolívares, y una en dólares solo
    en dólares, sin mezclar las dos. Si no viene metodo_pago_id (ej. una
    pre-factura generada sin tener aún el método decidido), queda en USD.
    """
    metodo_pago_id = data.get('metodo_pago_id')
    if metodo_pago_id in [None, '']:
        return 'USD', None
    try:
        metodo = VGMetodoPago.objects.get(pk=int(metodo_pago_id))
    except (TypeError, ValueError, VGMetodoPago.DoesNotExist):
        return None, 'El metodo de pago es invalido.'
    return metodo.moneda, None


def _pedidos_facturables_por_ids(pedido_ids):
    """
    Bloquea (select_for_update) y valida los pedidos: deben existir, estar
    en un estado facturable (listo/entregado) y no tener ya una factura no
    anulada. Debe llamarse dentro de una transaction.atomic().
    Devuelve (pedidos, error_message).
    """
    pedidos = list(
        VGPedido.objects.select_for_update()
        .filter(pk__in=pedido_ids)
        .prefetch_related(
            'detalles__producto__receta__ingrediente',
            'detalles__producto__receta__preparacion',
            'detalles__producto__receta_vinculada__receta__ingrediente',
            'detalles__producto__receta_vinculada__receta__preparacion',
            'detalles__producto__subreceta_vinculada__componentes__ingrediente',
            'detalles__producto__subreceta_vinculada__componentes__sub_preparacion',
            'detalles__adicionales__preparacion',
            'detalles__opciones__preparacion',
            'detalles__opciones__producto',
        )
    )
    found_ids = {pedido.id for pedido in pedidos}
    missing_ids = sorted(set(pedido_ids) - found_ids)
    if missing_ids:
        return None, f'Los pedidos {missing_ids} no existen.'

    not_billable = sorted(pedido.id for pedido in pedidos if pedido.estado not in BILLABLE_ORDER_STATES)
    if not_billable:
        return None, f'Los pedidos {not_billable} ya no están listos para facturar (revisa su estado actual).'

    ya_facturados = sorted(
        pedido.id for pedido in pedidos if pedido.facturas.exclude(estado='anulada').exists()
    )
    if ya_facturados:
        return None, f'Los pedidos {ya_facturados} ya tienen una factura emitida.'

    return pedidos, None


def _lineas_data_desde_pedidos(pedidos, porcentaje_iva):
    lineas = []
    for pedido in pedidos:
        for detalle in pedido.detalles.all():
            peso_factor = (detalle.peso_gramos / Decimal('1000')) if detalle.peso_gramos else Decimal('1')
            lineas.append({
                'descripcion': detalle.producto.nombre,
                'producto_id': detalle.producto_id,
                'cantidad': Decimal(detalle.cantidad) * peso_factor,
                'precio_unitario': detalle.precio_unitario,
                'porcentaje_iva': porcentaje_iva,
            })
            for adicional in detalle.adicionales.all():
                lineas.append({
                    'descripcion': f'Adicional — {adicional.preparacion.nombre}',
                    'producto_id': None,
                    'cantidad': Decimal(adicional.cantidad),
                    'precio_unitario': adicional.precio_unitario,
                    'porcentaje_iva': porcentaje_iva,
                })
            for opcion in detalle.opciones.all():
                lineas.append({
                    'descripcion': f'{opcion.grupo_nombre}: {opcion.nombre}',
                    'producto_id': None,
                    'cantidad': Decimal('1'),
                    'precio_unitario': opcion.precio_unitario,
                    'porcentaje_iva': porcentaje_iva,
                })
    return lineas


def _emitir_factura(pedidos, cliente, request_user, pre_factura=None, porcentaje_iva=None, moneda='USD'):
    """
    Crea la VGFactura + lineas + VGOrdenCobro a partir de pedidos ya
    validados y bloqueados (ver _pedidos_facturables_por_ids). Descuenta
    inventario y marca los pedidos como 'pagado' (operativamente cerrados),
    igual que pedidos_cobro_view — la diferencia es que aqui NO se crea un
    VGPago de una vez: el cobro real queda pendiente como una VGOrdenCobro
    hasta que se registren los abonos. Debe llamarse dentro de la misma
    transaction.atomic() que bloqueo los pedidos.
    """
    if porcentaje_iva is None:
        porcentaje_iva = _porcentaje_iva_default()

    numero_factura = VGCorrelativoFiscal.siguiente('FACTURA')
    numero_control = VGCorrelativoFiscal.siguiente('CONTROL')
    tasa_actual = obtener_tasa_actual()

    factura = VGFactura.objects.create(
        numero_factura=numero_factura,
        numero_control=numero_control,
        cliente=cliente,
        pre_factura=pre_factura,
        moneda=moneda,
        tasa_cambio_referencia=tasa_actual.tasa if tasa_actual else None,
        creado_por=request_user,
        actualizado_por=request_user,
    )
    factura.pedidos.set(pedidos)

    for linea_data in _lineas_data_desde_pedidos(pedidos, porcentaje_iva):
        linea = VGFacturaLinea(
            factura=factura,
            descripcion=linea_data['descripcion'],
            producto_id=linea_data['producto_id'],
            cantidad=linea_data['cantidad'],
            precio_unitario=linea_data['precio_unitario'],
            porcentaje_iva=linea_data['porcentaje_iva'],
        )
        linea.calcular_montos()
        linea.save()

    factura.recalcular_totales()
    factura.saldo_pendiente = factura.total
    factura.save(update_fields=['subtotal', 'total_iva', 'total', 'saldo_pendiente'])

    VGOrdenCobro.objects.create(
        factura=factura,
        monto_total=factura.total,
        saldo_pendiente=factura.total,
        estado='pendiente',
        responsable=request_user,
        creado_por=request_user,
        actualizado_por=request_user,
    )

    components_by_preparation, yields_by_preparation = _load_preparation_structure()
    ingredient_costs = dict(VGIngrediente.objects.values_list('id', 'costo_unitario'))
    preparation_cost_map = _compute_preparation_cost_map(components_by_preparation, ingredient_costs, yields_by_preparation)
    unit_cost_cache = {}

    for pedido in pedidos:
        pedido.estado = 'pagado'
        pedido.actualizado_por = request_user
        pedido.save(update_fields=['estado', 'actualizado_por', 'fecha_actualizacion'])

        _snapshot_costo_venta_detalles(pedido, ingredient_costs, preparation_cost_map, unit_cost_cache)

        needs = _compute_pedido_ingredient_needs(pedido, components_by_preparation, yields_by_preparation)
        if needs:
            ingredients_by_id = {
                ingredient.id: ingredient
                for ingredient in VGIngrediente.objects.select_for_update().filter(id__in=needs.keys())
            }
            for ingrediente_id, cantidad in needs.items():
                ingredient = ingredients_by_id.get(ingrediente_id)
                if ingredient is None or cantidad <= 0:
                    continue
                ingredient.stock_actual = ingredient.stock_actual - cantidad
                ingredient.save(update_fields=['stock_actual'])
                VGMovimientoInventario.objects.create(
                    ingrediente=ingredient,
                    tipo_movimiento='salida',
                    cantidad=cantidad,
                    motivo=f'Venta — Factura #{factura.numero_factura} (Pedido #{pedido.id})',
                    id_referencia=pedido.id,
                    creado_por=request_user,
                )

    return factura


# ---------------------------------------------------------------------------
# Serializadores
# ---------------------------------------------------------------------------
def _serialize_cliente(cliente):
    if cliente is None:
        return None
    return {
        'id': cliente.id,
        'nombre': cliente.nombre,
        'tipo_documento': cliente.tipo_documento,
        'numero_documento': cliente.numero_documento,
        'direccion_fiscal': cliente.direccion_fiscal,
    }


def _serialize_linea(linea):
    return {
        'id': linea.id,
        'descripcion': linea.descripcion,
        'producto_id': linea.producto_id,
        'cantidad': str(linea.cantidad),
        'precio_unitario': str(linea.precio_unitario),
        'porcentaje_iva': str(linea.porcentaje_iva),
        'base_imponible': str(linea.base_imponible),
        'monto_iva': str(linea.monto_iva),
        'subtotal': str(linea.subtotal),
    }


def _serialize_prefactura(prefactura):
    return {
        'id': prefactura.id,
        'numero': prefactura.numero,
        'codigo': f'PF-{prefactura.numero:06d}',
        'cliente': _serialize_cliente(prefactura.cliente),
        'pedidos': [pedido.id for pedido in prefactura.pedidos.all()],
        'fecha_emision': prefactura.fecha_emision.isoformat(),
        'subtotal': str(prefactura.subtotal),
        'total_iva': str(prefactura.total_iva),
        'total': str(prefactura.total),
        'moneda': prefactura.moneda,
        'tasa_cambio_referencia': str(prefactura.tasa_cambio_referencia) if prefactura.tasa_cambio_referencia is not None else None,
        'estado': prefactura.estado,
        'notas': prefactura.notas,
        'lineas': [_serialize_linea(linea) for linea in prefactura.lineas.all()],
    }


def _serialize_pago(pago):
    return {
        'id': pago.id,
        'monto': str(pago.monto),
        'metodo_pago': pago.metodo_pago.nombre,
        'metodo_pago_id': pago.metodo_pago_id,
        'referencia': pago.referencia,
        'fecha_pago': pago.fecha_pago.isoformat(),
        'creado_por': (pago.creado_por.get_full_name() or pago.creado_por.username) if pago.creado_por else '',
    }


def _serialize_factura(factura, incluir_detalle=True):
    data = {
        'id': factura.id,
        'numero_factura': factura.numero_factura,
        'numero_control': factura.numero_control,
        'codigo': f'{factura.numero_factura:08d}',
        'cliente': _serialize_cliente(factura.cliente),
        'pedidos': [pedido.id for pedido in factura.pedidos.all()],
        'fecha_emision': factura.fecha_emision.isoformat(),
        'subtotal': str(factura.subtotal),
        'total_iva': str(factura.total_iva),
        'descuento': str(factura.descuento),
        'total': str(factura.total),
        'saldo_pendiente': str(factura.saldo_pendiente),
        'moneda': factura.moneda,
        'tasa_cambio_referencia': str(factura.tasa_cambio_referencia) if factura.tasa_cambio_referencia is not None else None,
        'estado': factura.estado,
        'motivo_anulacion': factura.motivo_anulacion,
        'notas': factura.notas,
    }
    if incluir_detalle:
        data['lineas'] = [_serialize_linea(linea) for linea in factura.lineas.all()]
        data['pagos'] = [
            _serialize_pago(pago) for pago in factura.pagos.filter(estado='completado').order_by('fecha_pago')
        ]
    return data


def _serialize_orden_cobro(orden):
    return {
        'id': orden.id,
        'factura': _serialize_factura(orden.factura, incluir_detalle=False),
        'monto_total': str(orden.monto_total),
        'saldo_pendiente': str(orden.saldo_pendiente),
        'estado': orden.estado,
        'fecha_limite': orden.fecha_limite.isoformat() if orden.fecha_limite else None,
        'responsable': (orden.responsable.get_full_name() or orden.responsable.username) if orden.responsable else '',
        'notas': orden.notas,
        'fecha_creacion': orden.fecha_creacion.isoformat(),
    }


def _serialize_datos_fiscales(emisor):
    if emisor is None:
        return None
    return {
        'rif': emisor.rif,
        'razon_social': emisor.razon_social,
        'nombre_comercial': emisor.nombre_comercial,
        'domicilio_fiscal': emisor.domicilio_fiscal,
        'telefono': emisor.telefono,
        'porcentaje_iva_default': str(emisor.porcentaje_iva_default),
    }


# ---------------------------------------------------------------------------
# Clientes (busqueda liviana para el formulario de facturacion)
# ---------------------------------------------------------------------------
def clientes_buscar_view(request):
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not request.user.is_authenticated:
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion.'}, status=401)

    query = str(request.GET.get('q', '') or '').strip()
    clientes = VGCliente.objects.all().order_by('nombre')
    if query:
        clientes = clientes.filter(models.Q(nombre__icontains=query) | models.Q(numero_documento__icontains=query))

    return _auth_response({'ok': True, 'clientes': [_serialize_cliente(cliente) for cliente in clientes[:20]]})


# ---------------------------------------------------------------------------
# Datos fiscales del emisor (una sola fila, la configura el administrador)
# ---------------------------------------------------------------------------
@csrf_exempt
def datos_fiscales_view(request):
    if request.method not in ['GET', 'POST']:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_owner_or_contador_user(request.user):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para ver los datos fiscales.'}, status=401)

    emisor = VGDatosFiscalesEmisor.objects.first()

    if request.method == 'GET':
        return _auth_response({'ok': True, 'datos_fiscales': _serialize_datos_fiscales(emisor)})

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    rif = str(data.get('rif', '') or '').strip()
    razon_social = str(data.get('razon_social', '') or '').strip()
    if not rif or not razon_social:
        return _auth_response({'ok': False, 'message': 'El RIF y la razon social son obligatorios.'}, status=400)

    try:
        porcentaje_iva_default = Decimal(str(data.get('porcentaje_iva_default', '16.00')))
    except InvalidOperation:
        return _auth_response({'ok': False, 'message': 'El porcentaje de IVA no es valido.'}, status=400)

    valores = {
        'rif': rif,
        'razon_social': razon_social,
        'nombre_comercial': str(data.get('nombre_comercial', '') or '').strip(),
        'domicilio_fiscal': str(data.get('domicilio_fiscal', '') or '').strip(),
        'telefono': str(data.get('telefono', '') or '').strip(),
        'porcentaje_iva_default': porcentaje_iva_default,
    }

    if emisor is None:
        emisor = VGDatosFiscalesEmisor.objects.create(**valores)
    else:
        for campo, valor in valores.items():
            setattr(emisor, campo, valor)
        emisor.save()

    return _auth_response({
        'ok': True,
        'message': 'Datos fiscales guardados correctamente.',
        'datos_fiscales': _serialize_datos_fiscales(emisor),
    })


# ---------------------------------------------------------------------------
# Pre-facturas
# ---------------------------------------------------------------------------
@csrf_exempt
def prefacturas_view(request):
    if request.method not in ['GET', 'POST']:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not (_is_admin_user(request.user) or _is_cajera_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para gestionar pre-facturas.'}, status=401)

    if request.method == 'GET':
        prefacturas = (
            VGPreFactura.objects.filter(estado='vigente')
            .select_related('cliente')
            .prefetch_related('lineas', 'pedidos')
            .order_by('-fecha_emision')
        )
        return _auth_response({'ok': True, 'prefacturas': [_serialize_prefactura(p) for p in prefacturas]})

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    raw_ids = data.get('pedido_ids')
    if not isinstance(raw_ids, list) or len(raw_ids) == 0:
        return _auth_response({'ok': False, 'message': 'Debes seleccionar al menos un pedido.'}, status=400)
    try:
        pedido_ids = sorted({int(raw_id) for raw_id in raw_ids})
    except (TypeError, ValueError):
        return _auth_response({'ok': False, 'message': 'Hay un pedido invalido en la seleccion.'}, status=400)

    cliente, error = _resolve_cliente(data)
    if error:
        return _auth_response({'ok': False, 'message': error}, status=400)

    moneda, error = _resolve_moneda(data)
    if error:
        return _auth_response({'ok': False, 'message': error}, status=400)

    with transaction.atomic():
        pedidos, error = _pedidos_facturables_por_ids(pedido_ids)
        if error:
            return _auth_response({'ok': False, 'message': error}, status=409)

        porcentaje_iva = _porcentaje_iva_default()
        numero = VGCorrelativoFiscal.siguiente('PREFACTURA')
        tasa_actual = obtener_tasa_actual()
        prefactura = VGPreFactura.objects.create(
            numero=numero,
            cliente=cliente,
            moneda=moneda,
            tasa_cambio_referencia=tasa_actual.tasa if tasa_actual else None,
            notas=str(data.get('notas', '') or '').strip(),
            creado_por=request.user,
            actualizado_por=request.user,
        )
        prefactura.pedidos.set(pedidos)

        for linea_data in _lineas_data_desde_pedidos(pedidos, porcentaje_iva):
            linea = VGPreFacturaLinea(
                prefactura=prefactura,
                descripcion=linea_data['descripcion'],
                producto_id=linea_data['producto_id'],
                cantidad=linea_data['cantidad'],
                precio_unitario=linea_data['precio_unitario'],
                porcentaje_iva=linea_data['porcentaje_iva'],
            )
            linea.calcular_montos()
            linea.save()

        prefactura.recalcular_totales()
        prefactura.save(update_fields=['subtotal', 'total_iva', 'total'])

    try:
        imprimir_prefactura_caja(prefactura)
    except Exception:
        logger.exception('Fallo al imprimir la pre-factura %s', prefactura.numero)

    return _auth_response({
        'ok': True,
        'message': 'Pre-factura generada correctamente.',
        'prefactura': _serialize_prefactura(prefactura),
    }, status=201)


@csrf_exempt
def prefactura_convertir_view(request, prefactura_id):
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not (_is_admin_user(request.user) or _is_cajera_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para emitir facturas.'}, status=401)

    with transaction.atomic():
        try:
            # No select_related('cliente') aqui: cliente es nullable (SET_NULL) y
            # PostgreSQL no permite FOR UPDATE sobre el lado nulable de un outer
            # join. Se accede a prefactura.cliente despues, con una query aparte.
            prefactura = VGPreFactura.objects.select_for_update().get(pk=prefactura_id)
        except VGPreFactura.DoesNotExist:
            return _auth_response({'ok': False, 'message': 'La pre-factura no existe.'}, status=404)

        if prefactura.estado != 'vigente':
            return _auth_response({'ok': False, 'message': 'Esta pre-factura ya no esta vigente.'}, status=409)

        pedido_ids = sorted(prefactura.pedidos.values_list('id', flat=True))
        if not pedido_ids:
            return _auth_response({'ok': False, 'message': 'La pre-factura no tiene pedidos asociados.'}, status=409)

        pedidos, error = _pedidos_facturables_por_ids(pedido_ids)
        if error:
            return _auth_response({'ok': False, 'message': error}, status=409)

        primera_linea = prefactura.lineas.first()
        porcentaje_iva = primera_linea.porcentaje_iva if primera_linea else None
        cliente = prefactura.cliente
        if cliente is None:
            cliente, error = _resolve_cliente({})
            if error:
                return _auth_response({'ok': False, 'message': error}, status=400)

        factura = _emitir_factura(
            pedidos, cliente, request.user, pre_factura=prefactura, porcentaje_iva=porcentaje_iva,
            moneda=prefactura.moneda,
        )

        prefactura.estado = 'convertida'
        prefactura.actualizado_por = request.user
        prefactura.save(update_fields=['estado', 'actualizado_por', 'fecha_actualizacion'])

    try:
        imprimir_factura_caja(factura)
    except Exception:
        logger.exception('Fallo al imprimir la factura %s', factura.numero_factura)

    return _auth_response({
        'ok': True,
        'message': 'Factura emitida correctamente.',
        'factura': _serialize_factura(factura),
    }, status=201)


@csrf_exempt
def prefactura_anular_view(request, prefactura_id):
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not (_is_admin_user(request.user) or _is_cajera_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para anular pre-facturas.'}, status=401)

    try:
        prefactura = VGPreFactura.objects.get(pk=prefactura_id)
    except VGPreFactura.DoesNotExist:
        return _auth_response({'ok': False, 'message': 'La pre-factura no existe.'}, status=404)

    if prefactura.estado != 'vigente':
        return _auth_response({'ok': False, 'message': 'Esta pre-factura ya no esta vigente.'}, status=409)

    prefactura.estado = 'anulada'
    prefactura.actualizado_por = request.user
    prefactura.save(update_fields=['estado', 'actualizado_por', 'fecha_actualizacion'])

    return _auth_response({'ok': True, 'message': 'Pre-factura anulada correctamente.'})


# ---------------------------------------------------------------------------
# Facturas
# ---------------------------------------------------------------------------
@csrf_exempt
def facturas_view(request):
    if request.method not in ['GET', 'POST']:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not (_is_admin_user(request.user) or _is_cajera_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para gestionar facturas.'}, status=401)

    if request.method == 'GET':
        estado = str(request.GET.get('estado', '') or '').strip().lower()
        facturas = (
            VGFactura.objects.select_related('cliente')
            .prefetch_related('lineas', 'pedidos')
            .order_by('-fecha_emision')
        )
        if estado:
            facturas = facturas.filter(estado=estado)
        return _auth_response({
            'ok': True,
            'facturas': [_serialize_factura(factura, incluir_detalle=False) for factura in facturas[:200]],
        })

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    raw_ids = data.get('pedido_ids')
    if not isinstance(raw_ids, list) or len(raw_ids) == 0:
        return _auth_response({'ok': False, 'message': 'Debes seleccionar al menos un pedido.'}, status=400)
    try:
        pedido_ids = sorted({int(raw_id) for raw_id in raw_ids})
    except (TypeError, ValueError):
        return _auth_response({'ok': False, 'message': 'Hay un pedido invalido en la seleccion.'}, status=400)

    cliente, error = _resolve_cliente(data)
    if error:
        return _auth_response({'ok': False, 'message': error}, status=400)

    moneda, error = _resolve_moneda(data)
    if error:
        return _auth_response({'ok': False, 'message': error}, status=400)

    with transaction.atomic():
        pedidos, error = _pedidos_facturables_por_ids(pedido_ids)
        if error:
            return _auth_response({'ok': False, 'message': error}, status=409)

        factura = _emitir_factura(pedidos, cliente, request.user, moneda=moneda)

    try:
        imprimir_factura_caja(factura)
    except Exception:
        logger.exception('Fallo al imprimir la factura %s', factura.numero_factura)

    return _auth_response({
        'ok': True,
        'message': 'Factura emitida correctamente.',
        'factura': _serialize_factura(factura),
    }, status=201)


def factura_detail_view(request, factura_id):
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not (_is_admin_user(request.user) or _is_cajera_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para ver esta factura.'}, status=401)

    try:
        factura = (
            VGFactura.objects.select_related('cliente')
            .prefetch_related('lineas', 'pedidos', 'pagos__metodo_pago', 'pagos__creado_por')
            .get(pk=factura_id)
        )
    except VGFactura.DoesNotExist:
        return _auth_response({'ok': False, 'message': 'La factura no existe.'}, status=404)

    return _auth_response({'ok': True, 'factura': _serialize_factura(factura)})


@csrf_exempt
def factura_abono_view(request, factura_id):
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not (_is_admin_user(request.user) or _is_cajera_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para registrar cobros.'}, status=401)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    try:
        monto = Decimal(str(data.get('monto', '')))
    except InvalidOperation:
        return _auth_response({'ok': False, 'message': 'El monto no es valido.'}, status=400)
    if monto <= 0:
        return _auth_response({'ok': False, 'message': 'El monto debe ser mayor a cero.'}, status=400)

    try:
        metodo_pago = VGMetodoPago.objects.get(pk=int(data.get('metodo_pago_id')), activo=True)
    except (TypeError, ValueError, VGMetodoPago.DoesNotExist):
        return _auth_response({'ok': False, 'message': 'El metodo de pago es invalido.'}, status=400)

    with transaction.atomic():
        try:
            factura = VGFactura.objects.select_for_update().select_related('cliente').get(pk=factura_id)
        except VGFactura.DoesNotExist:
            return _auth_response({'ok': False, 'message': 'La factura no existe.'}, status=404)

        if factura.estado in ('pagada', 'anulada'):
            return _auth_response({'ok': False, 'message': 'Esta factura ya no admite cobros.'}, status=409)

        if monto > factura.saldo_pendiente:
            return _auth_response({
                'ok': False,
                'message': f'El monto excede el saldo pendiente (${factura.saldo_pendiente}).',
            }, status=400)

        referencia = str(data.get('referencia', '') or '').strip() \
            or f'ABONO-{timezone.now().strftime("%Y%m%d%H%M%S")}-{factura.id}'

        pago = VGPago.objects.create(
            factura=factura,
            monto=monto,
            metodo_pago=metodo_pago,
            referencia=referencia,
            estado='completado',
            creado_por=request.user,
        )

        factura.saldo_pendiente = factura.saldo_pendiente - monto
        factura.estado = 'pagada' if factura.saldo_pendiente <= 0 else 'abonada_parcial'
        factura.actualizado_por = request.user
        factura.save(update_fields=['saldo_pendiente', 'estado', 'actualizado_por', 'fecha_actualizacion'])

        orden = getattr(factura, 'orden_cobro', None)
        if orden is not None:
            orden.saldo_pendiente = factura.saldo_pendiente
            orden.estado = 'saldada' if factura.saldo_pendiente <= 0 else 'parcial'
            orden.actualizado_por = request.user
            orden.save(update_fields=['saldo_pendiente', 'estado', 'actualizado_por', 'fecha_actualizacion'])

    return _auth_response({
        'ok': True,
        'message': 'Abono registrado correctamente.',
        'factura': _serialize_factura(factura),
        'pago': _serialize_pago(pago),
    }, status=201)


@csrf_exempt
def factura_anular_view(request, factura_id):
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Solo un administrador puede anular facturas.'}, status=401)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    motivo = str(data.get('motivo', '') or '').strip()
    if not motivo:
        return _auth_response({'ok': False, 'message': 'Debes indicar el motivo de la anulacion.'}, status=400)

    with transaction.atomic():
        try:
            factura = VGFactura.objects.select_for_update().get(pk=factura_id)
        except VGFactura.DoesNotExist:
            return _auth_response({'ok': False, 'message': 'La factura no existe.'}, status=404)

        if factura.estado == 'anulada':
            return _auth_response({'ok': False, 'message': 'Esta factura ya esta anulada.'}, status=409)

        if factura.saldo_pendiente != factura.total:
            return _auth_response({
                'ok': False,
                'message': 'No se puede anular una factura con abonos ya registrados.',
            }, status=409)

        factura.estado = 'anulada'
        factura.motivo_anulacion = motivo
        factura.actualizado_por = request.user
        factura.save(update_fields=['estado', 'motivo_anulacion', 'actualizado_por', 'fecha_actualizacion'])

        orden = getattr(factura, 'orden_cobro', None)
        if orden is not None:
            orden.estado = 'anulada'
            orden.actualizado_por = request.user
            orden.save(update_fields=['estado', 'actualizado_por', 'fecha_actualizacion'])

    return _auth_response({
        'ok': True,
        'message': 'Factura anulada correctamente.',
        'factura': _serialize_factura(factura),
    })


# ---------------------------------------------------------------------------
# Cuentas por cobrar
# ---------------------------------------------------------------------------
def cuentas_por_cobrar_view(request):
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not (_is_admin_user(request.user) or _is_cajera_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para ver cuentas por cobrar.'}, status=401)

    ordenes = (
        VGOrdenCobro.objects.filter(estado__in=['pendiente', 'parcial'])
        .select_related('factura__cliente', 'responsable')
        .order_by('fecha_creacion')
    )
    return _auth_response({'ok': True, 'ordenes_cobro': [_serialize_orden_cobro(orden) for orden in ordenes]})

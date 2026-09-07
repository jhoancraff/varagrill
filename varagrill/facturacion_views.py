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
from datetime import date
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
from .impresion_lpd import imprimir_factura_caja, imprimir_nota_entrega_caja, imprimir_prefactura_caja
from .models import (
    VGCliente,
    VGCorrelativoFiscal,
    VGDatosFiscalesEmisor,
    VGFactura,
    VGFacturaLinea,
    VGIngrediente,
    VGMetodoPago,
    VGMovimientoInventario,
    VGNotaEntrega,
    VGOrdenCobro,
    VGPago,
    VGPedido,
    VGPreFactura,
    VGPreFacturaLinea,
)
from .tasa_cambio import obtener_tasa_actual

logger = logging.getLogger(__name__)

# Tolerancia al comparar un pago (convertido de bolivares, con 6 decimales de
# precision) contra un saldo_pendiente de solo 2 decimales — ver
# nota_entrega_abono_view/factura_abono_view. Muchisimo mas chica que un
# centavo real, asi que solo absorbe el redondeo de la conversion, nunca un
# sobrepago genuino (que siempre es de centavos completos para arriba).
TOLERANCIA_REDONDEO_ABONO = Decimal('0.00001')


def _tasa_conversion_vigente(moneda, fecha_emision, tasa_cambio_referencia, tasa_pago_actual):
    """
    Tasa BCV que corresponde usar AHORA para convertir un pago en bolivares de
    una nota de entrega o factura — la misma logica para calcularla al mostrar
    el saldo pendiente (ver nota_entrega_detail_view/factura_detail_view) y al
    registrar de verdad el abono (ver nota_entrega_abono_view/
    factura_abono_view), para que lo que se le muestra a la cajera ANTES de
    cobrar sea exactamente lo que el sistema va a registrar.

    Si el documento es de HOY: se usa la tasa que se congelo al emitirlo (la
    que se le cotizo al cliente) — un pago del mismo dia no debe moverse ni un
    centimo aunque el cache de la tasa BCV se haya refrescado mientras tanto
    (ver TASA_TTL en tasa_cambio.py, se refresca solo varias veces al dia).

    Si el documento es de un dia anterior (fiado de verdad, no cobrado el
    mismo dia): se usa la tasa BCV de HOY a proposito, para que el negocio no
    pierda valor por la devaluacion del bolivar mientras la deuda sigue sin
    cobrarse — el excedente (o la diferencia) por el cambio de tasa se le
    cobra al cliente en ese momento.

    Devuelve None si el documento no es en bolivares, o si no hay ninguna tasa
    disponible en ningun lado (documento sin congelar y sin tasa BCV vigente).
    """
    if moneda != 'VES':
        return None
    tasa_actual = tasa_pago_actual.tasa if tasa_pago_actual else None
    es_de_hoy = timezone.localdate(fecha_emision) == timezone.localdate()
    if es_de_hoy:
        return tasa_cambio_referencia or tasa_actual
    return tasa_actual or tasa_cambio_referencia


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
    en un estado facturable (ver BILLABLE_ORDER_STATES en api_views.py) y no
    tener ya una factura no anulada. Debe llamarse dentro de una
    transaction.atomic().
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
        # Moneda del metodo CON EL QUE SE HIZO ESTE PAGO — no necesariamente la
        # misma que nota.moneda/factura.moneda si distintos abonos de un mismo
        # documento se hicieron con cuentas de distinta moneda (ver
        # cambia_metodo en nota_entrega_abono_view). El frontend debe usar
        # esto (junto con tasa_cambio_referencia, de abajo) para mostrar CADA
        # pago en su propia moneda, no en la del documento.
        'moneda': pago.metodo_pago.moneda,
        'referencia': pago.referencia,
        'fecha_pago': pago.fecha_pago.isoformat(),
        'tasa_cambio_referencia': str(pago.tasa_cambio_referencia) if pago.tasa_cambio_referencia is not None else None,
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
        desde_raw = request.GET.get('desde')
        hasta_raw = request.GET.get('hasta')
        try:
            desde = date.fromisoformat(desde_raw) if desde_raw else None
            hasta = date.fromisoformat(hasta_raw) if hasta_raw else None
        except ValueError:
            return _auth_response({'ok': False, 'message': 'Las fechas no son validas.'}, status=400)
        if desde and hasta and desde > hasta:
            return _auth_response({'ok': False, 'message': '"Desde" no puede ser posterior a "Hasta".'}, status=400)

        facturas = (
            VGFactura.objects.select_related('cliente')
            .prefetch_related('lineas', 'pedidos')
            .order_by('-fecha_emision')
        )
        if estado:
            facturas = facturas.filter(estado=estado)
        if desde:
            facturas = facturas.filter(fecha_emision__date__gte=desde)
        if hasta:
            facturas = facturas.filter(fecha_emision__date__lte=hasta)
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
        monto_input = Decimal(str(data.get('monto', '')))
    except InvalidOperation:
        return _auth_response({'ok': False, 'message': 'El monto no es valido.'}, status=400)
    if monto_input <= 0:
        return _auth_response({'ok': False, 'message': 'El monto debe ser mayor a cero.'}, status=400)

    try:
        metodo_pago = VGMetodoPago.objects.get(pk=int(data.get('metodo_pago_id')), activo=True)
    except (TypeError, ValueError, VGMetodoPago.DoesNotExist):
        return _auth_response({'ok': False, 'message': 'El metodo de pago es invalido.'}, status=400)

    # Igual que en pedidos_cobro_view/nota_entrega_abono_view: obligatorio para
    # cualquier metodo que no sea efectivo.
    referencia_usuario = str(data.get('referencia', '') or '').strip()
    if not referencia_usuario and not metodo_pago.es_efectivo:
        return _auth_response({
            'ok': False,
            'message': f'Indica el número de referencia del pago por {metodo_pago.nombre}.',
        }, status=400)

    with transaction.atomic():
        try:
            factura = VGFactura.objects.select_for_update().select_related('cliente').get(pk=factura_id)
        except VGFactura.DoesNotExist:
            return _auth_response({'ok': False, 'message': 'La factura no existe.'}, status=404)

        if factura.estado in ('pagada', 'anulada'):
            return _auth_response({'ok': False, 'message': 'Esta factura ya no admite cobros.'}, status=409)

        tasa_pago_actual = obtener_tasa_actual()

        # monto_input viene en la moneda de la factura (lo que el cajero ve en
        # pantalla y le cobra al cliente) — VGPago.monto y saldo_pendiente
        # siempre se guardan en USD (ver VGMetodoPago.moneda), asi que si la
        # factura es en bolivares hay que convertir a USD antes de comparar o
        # descontar. Ver _tasa_conversion_vigente: si el pago es del mismo dia
        # en que se emitio la factura se usa la tasa que se le cotizo al
        # cliente entonces (no debe moverse ni un centimo aunque el cache de
        # la tasa BCV se haya refrescado mientras tanto — reportado 2026-09);
        # si es fiado de un dia anterior se usa la tasa de HOY a proposito,
        # para no perder valor por la devaluacion del bolivar.
        tasa_conversion = _tasa_conversion_vigente(
            factura.moneda, factura.fecha_emision, factura.tasa_cambio_referencia, tasa_pago_actual,
        )
        if factura.moneda == 'VES':
            if not tasa_conversion or tasa_conversion <= 0:
                return _auth_response({
                    'ok': False,
                    'message': 'No hay tasa de cambio disponible para convertir el monto a dolares.',
                }, status=400)
            monto = (monto_input / tasa_conversion).quantize(Decimal('0.000001'))
        else:
            monto = monto_input.quantize(Decimal('0.000001'))

        if monto > factura.saldo_pendiente + TOLERANCIA_REDONDEO_ABONO:
            saldo_en_moneda_factura = (
                factura.saldo_pendiente * tasa_conversion if tasa_conversion else factura.saldo_pendiente
            )
            unidad = 'Bs' if factura.moneda == 'VES' else '$'
            return _auth_response({
                'ok': False,
                'message': f'El monto excede el saldo pendiente ({unidad} {saldo_en_moneda_factura:.2f}).',
            }, status=400)

        referencia = referencia_usuario or f'ABONO-{timezone.now().strftime("%Y%m%d%H%M%S")}-{factura.id}'

        pago = VGPago.objects.create(
            factura=factura,
            monto=monto,
            metodo_pago=metodo_pago,
            referencia=referencia,
            estado='completado',
            # Ver el comentario equivalente en nota_entrega_abono_view: la tasa
            # que de verdad se uso para convertir este pago, no siempre la de hoy.
            tasa_cambio_referencia=(
                tasa_conversion if factura.moneda == 'VES'
                else (tasa_pago_actual.tasa if tasa_pago_actual else None)
            ),
            creado_por=request.user,
        )

        # Se redondea a 2 decimales (y nunca se deja negativo) apenas se resta:
        # monto tiene 6 decimales de precision (ver VGPago.monto) pero el saldo
        # de una factura siempre es un monto "limpio" en dolares — sin este
        # redondeo, un pago exacto por Bs podia dejar un residuo de fracciones
        # de centavo que nunca llegaba a estado 'pagada'.
        factura.saldo_pendiente = max(
            (factura.saldo_pendiente - monto).quantize(Decimal('0.01')),
            Decimal('0.00'),
        )
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
def factura_reimprimir_view(request, factura_id):
    """
    Reenvia una factura ya emitida a la impresora de caja — para cuando el
    ticket original se traspapelo, no salio bien, o el cliente pide otra
    copia mas tarde el mismo dia. No cambia nada del estado de la factura
    (saldo, pagos, numeracion fiscal): solo repite el trabajo de impresion
    con los datos que ya estan guardados, marcado como reimpresion.
    """
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not (_is_admin_user(request.user) or _is_cajera_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para reimprimir facturas.'}, status=401)

    try:
        factura = (
            VGFactura.objects.select_related('cliente')
            .prefetch_related('lineas')
            .get(pk=factura_id)
        )
    except VGFactura.DoesNotExist:
        return _auth_response({'ok': False, 'message': 'La factura no existe.'}, status=404)

    exito, motivo = imprimir_factura_caja(factura, es_reimpresion=True)
    if not exito:
        return _auth_response({
            'ok': False,
            'message': motivo or 'No se pudo reimprimir la factura.',
        }, status=502)

    return _auth_response({
        'ok': True,
        'message': f'Factura {factura.numero_factura:08d} reenviada a la impresora.',
    })


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


# ---------------------------------------------------------------------------
# Notas de entrega — recibo de venta sin efecto fiscal (ver VGNotaEntrega).
# Se generan desde pedidos_cobro_view (api_views.py) al cobrar directo; aca
# solo viven la consulta del historial y la reimpresion.
# ---------------------------------------------------------------------------
def _serialize_nota_entrega(nota, incluir_detalle=True, tasa_pago_actual=None):
    es_de_hoy = timezone.localdate(nota.fecha_emision) == timezone.localdate()
    data = {
        'id': nota.id,
        'codigo': nota.codigo,
        'fecha_emision': nota.fecha_emision.isoformat(),
        'es_de_hoy': es_de_hoy,
        'total': str(nota.total),
        'saldo_pendiente': str(nota.saldo_pendiente),
        'estado': nota.estado,
        'moneda': nota.moneda,
        'tasa_cambio_referencia': str(nota.tasa_cambio_referencia) if nota.tasa_cambio_referencia is not None else None,
        'metodo_pago': nota.metodo_pago.nombre,
        'metodo_pago_id': nota.metodo_pago_id,
        'referencia': nota.referencia,
        'pedidos': [pedido.id for pedido in nota.pedidos.all()],
    }
    if nota.estado != 'pagada':
        # Tasa que se usaria AHORA MISMO si se le registrara un abono a esta
        # nota (ver _tasa_conversion_vigente) — para fiado de dias anteriores
        # es la tasa BCV de hoy, distinta a la congelada al emitir. Se manda
        # aparte de tasa_cambio_referencia para que la cajera vea, ANTES de
        # cobrar, cuanto es el saldo pendiente a valor de hoy (con la
        # diferencia por la devaluacion ya calculada) en vez de enterarse
        # despues de que el abono no le cuadro. En una nota de hoy da lo
        # mismo que tasa_cambio_referencia (es la misma tasa).
        tasa_vigente = _tasa_conversion_vigente(
            nota.moneda, nota.fecha_emision, nota.tasa_cambio_referencia, tasa_pago_actual,
        )
        data['tasa_cobro_vigente'] = str(tasa_vigente) if tasa_vigente else None
        data['saldo_pendiente_bs_vigente'] = (
            str((nota.saldo_pendiente * tasa_vigente).quantize(Decimal('0.01')))
            if nota.moneda == 'VES' and tasa_vigente else None
        )
    if incluir_detalle:
        data['pagos'] = [
            _serialize_pago(pago) for pago in nota.pagos.filter(estado='completado').order_by('fecha_pago')
        ]
    return data


def notas_entrega_view(request):
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not (_is_admin_user(request.user) or _is_cajera_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para ver las notas de entrega.'}, status=401)

    desde_raw = request.GET.get('desde')
    hasta_raw = request.GET.get('hasta')
    try:
        desde = date.fromisoformat(desde_raw) if desde_raw else None
        hasta = date.fromisoformat(hasta_raw) if hasta_raw else None
    except ValueError:
        return _auth_response({'ok': False, 'message': 'Las fechas no son validas.'}, status=400)
    if desde and hasta and desde > hasta:
        return _auth_response({'ok': False, 'message': '"Desde" no puede ser posterior a "Hasta".'}, status=400)

    notas = (
        VGNotaEntrega.objects.select_related('metodo_pago')
        .prefetch_related('pedidos')
        .order_by('-fecha_emision')
    )
    if desde:
        notas = notas.filter(fecha_emision__date__gte=desde)
    if hasta:
        notas = notas.filter(fecha_emision__date__lte=hasta)

    tasa_pago_actual = obtener_tasa_actual()
    return _auth_response({
        'ok': True,
        'notas_entrega': [
            _serialize_nota_entrega(nota, incluir_detalle=False, tasa_pago_actual=tasa_pago_actual)
            for nota in notas[:200]
        ],
    })


def nota_entrega_detail_view(request, nota_id):
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not (_is_admin_user(request.user) or _is_cajera_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para ver esta nota de entrega.'}, status=401)

    try:
        nota = (
            VGNotaEntrega.objects.select_related('metodo_pago')
            .prefetch_related('pedidos', 'pagos__metodo_pago', 'pagos__creado_por')
            .get(pk=nota_id)
        )
    except VGNotaEntrega.DoesNotExist:
        return _auth_response({'ok': False, 'message': 'La nota de entrega no existe.'}, status=404)

    tasa_pago_actual = obtener_tasa_actual()
    return _auth_response({
        'ok': True,
        'nota_entrega': _serialize_nota_entrega(nota, tasa_pago_actual=tasa_pago_actual),
    })


@csrf_exempt
def nota_entrega_abono_view(request, nota_id):
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not (_is_admin_user(request.user) or _is_cajera_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para registrar cobros.'}, status=401)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    try:
        monto_input = Decimal(str(data.get('monto', '')))
    except InvalidOperation:
        return _auth_response({'ok': False, 'message': 'El monto no es valido.'}, status=400)
    if monto_input <= 0:
        return _auth_response({'ok': False, 'message': 'El monto debe ser mayor a cero.'}, status=400)

    try:
        metodo_pago = VGMetodoPago.objects.get(pk=int(data.get('metodo_pago_id')), activo=True)
    except (TypeError, ValueError, VGMetodoPago.DoesNotExist):
        return _auth_response({'ok': False, 'message': 'El metodo de pago es invalido.'}, status=400)

    # Igual que en pedidos_cobro_view: obligatorio para cualquier metodo que no
    # sea efectivo, para poder cruzarlo despues contra el estado de cuenta.
    referencia_usuario = str(data.get('referencia', '') or '').strip()
    if not referencia_usuario and not metodo_pago.es_efectivo:
        return _auth_response({
            'ok': False,
            'message': f'Indica el número de referencia del pago por {metodo_pago.nombre}.',
        }, status=400)

    confirma_cambio_metodo = bool(data.get('confirmar_cambio_metodo'))

    with transaction.atomic():
        try:
            nota = VGNotaEntrega.objects.select_related('metodo_pago').select_for_update().get(pk=nota_id)
        except VGNotaEntrega.DoesNotExist:
            return _auth_response({'ok': False, 'message': 'La nota de entrega no existe.'}, status=404)

        if nota.estado == 'pagada':
            return _auth_response({'ok': False, 'message': 'Esta nota de entrega ya no admite cobros.'}, status=409)

        # La nota se emitio con un metodo "declarado" (lo que se imprimio en
        # el momento del cobro rapido — ver pedidos_cobro_view), pero el
        # cliente puede terminar pagando con una cuenta distinta (p. ej. se
        # declaro Efectivo pero paga por Pago Movil). Eso mueve la plata a
        # otra cuenta bancaria real, asi que se le pide confirmacion explicita
        # a la cajera antes de aplicarlo — si no confirma, no se registra
        # nada todavia y el frontend le muestra la alerta.
        cambia_metodo = metodo_pago.id != nota.metodo_pago_id
        if cambia_metodo and not confirma_cambio_metodo:
            return _auth_response({
                'ok': False,
                'requiere_confirmacion': True,
                'metodo_anterior': nota.metodo_pago.nombre,
                'metodo_nuevo': metodo_pago.nombre,
                'message': (
                    f'Esta nota se generó con «{nota.metodo_pago.nombre}» y la estás '
                    f'cobrando con «{metodo_pago.nombre}». ¿Confirmas el cambio de cuenta?'
                ),
            }, status=409)

        tasa_pago_actual = obtener_tasa_actual()

        # monto_input llega en la moneda del metodo de pago que se esta usando
        # PARA ESTE abono (no necesariamente la moneda declarada en la nota —
        # ver cambia_metodo arriba), VGPago.monto y saldo_pendiente se guardan
        # siempre en USD. Ver _tasa_conversion_vigente: si el pago es del
        # mismo dia en que se emitio la nota se usa la tasa que se le cotizo
        # al cliente entonces (no debe moverse ni un centimo aunque el cache
        # de la tasa BCV se haya refrescado mientras tanto — reportado
        # 2026-09); si es fiado de un dia anterior se usa la tasa de HOY a
        # proposito, para no perder valor por la devaluacion del bolivar.
        tasa_conversion = _tasa_conversion_vigente(
            metodo_pago.moneda, nota.fecha_emision, nota.tasa_cambio_referencia, tasa_pago_actual,
        )
        if metodo_pago.moneda == 'VES':
            if not tasa_conversion or tasa_conversion <= 0:
                return _auth_response({
                    'ok': False,
                    'message': 'No hay tasa de cambio disponible para convertir el monto a dolares.',
                }, status=400)
            monto = (monto_input / tasa_conversion).quantize(Decimal('0.000001'))
        else:
            monto = monto_input.quantize(Decimal('0.000001'))

        if monto > nota.saldo_pendiente + TOLERANCIA_REDONDEO_ABONO:
            saldo_en_moneda_metodo = (
                nota.saldo_pendiente * tasa_conversion if tasa_conversion else nota.saldo_pendiente
            )
            unidad = 'Bs' if metodo_pago.moneda == 'VES' else '$'
            return _auth_response({
                'ok': False,
                'message': f'El monto excede el saldo pendiente ({unidad} {saldo_en_moneda_metodo:.2f}).',
            }, status=400)

        referencia = referencia_usuario or f'ABONO-{timezone.now().strftime("%Y%m%d%H%M%S")}-{nota.id}'

        pago = VGPago.objects.create(
            nota_entrega=nota,
            monto=monto,
            metodo_pago=metodo_pago,
            referencia=referencia,
            estado='completado',
            # La tasa que de verdad se uso para convertir este pago (ver
            # arriba) — no siempre la de hoy: asi el monto en bolivares que se
            # muestre despues (cuadre de caja, historial de notas) siempre
            # reconstruye exactamente lo que la cajera cobro, sin importar que
            # el BCV cambie despues. Si el metodo es en dolares no hubo
            # conversion, pero se congela la tasa de hoy igual por si mas
            # adelante se corrige la cuenta de este pago hacia una cuenta en
            # bolivares (ver cambiar_metodo_pago).
            tasa_cambio_referencia=(
                tasa_conversion if metodo_pago.moneda == 'VES'
                else (tasa_pago_actual.tasa if tasa_pago_actual else None)
            ),
            creado_por=request.user,
        )

        # Ver el comentario equivalente en factura_abono_view: se redondea a 2
        # decimales (y nunca se deja negativo) para que un pago con precision
        # de 6 decimales nunca deje un residuo de fracciones de centavo que
        # impida llegar a estado 'pagada'.
        nota.saldo_pendiente = max(
            (nota.saldo_pendiente - monto).quantize(Decimal('0.01')),
            Decimal('0.00'),
        )
        nota.estado = 'pagada' if nota.saldo_pendiente <= 0 else 'abonada_parcial'
        nota.actualizado_por = request.user
        update_fields = ['saldo_pendiente', 'estado', 'actualizado_por', 'fecha_actualizacion']
        if cambia_metodo:
            # Confirmado por la cajera arriba: la nota pasa a declarar la
            # cuenta con la que de verdad se esta cobrando, para que el resto
            # del saldo (si queda pendiente) se siga cotizando en la moneda
            # correcta de aqui en adelante.
            nota.metodo_pago = metodo_pago
            nota.moneda = metodo_pago.moneda
            update_fields += ['metodo_pago', 'moneda']
        nota.save(update_fields=update_fields)

    return _auth_response({
        'ok': True,
        'message': 'Abono registrado correctamente.',
        'nota_entrega': _serialize_nota_entrega(nota, tasa_pago_actual=tasa_pago_actual),
        'pago': _serialize_pago(pago),
    }, status=201)


@csrf_exempt
def nota_entrega_reimprimir_view(request, nota_id):
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not (_is_admin_user(request.user) or _is_cajera_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para reimprimir notas de entrega.'}, status=401)

    try:
        nota = VGNotaEntrega.objects.get(pk=nota_id)
    except VGNotaEntrega.DoesNotExist:
        return _auth_response({'ok': False, 'message': 'La nota de entrega no existe.'}, status=404)

    exito, motivo = imprimir_nota_entrega_caja(nota, es_reimpresion=True)
    if not exito:
        return _auth_response({
            'ok': False,
            'message': motivo or 'No se pudo reimprimir la nota de entrega.',
        }, status=502)

    return _auth_response({
        'ok': True,
        'message': f'Nota de entrega {nota.codigo} reenviada a la impresora.',
    })

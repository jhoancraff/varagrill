"""
Vistas de compras a proveedores: el borrador compartido donde el analista arma una
factura de proveedor ingrediente por ingrediente antes de confirmarla (ver
VGCompraBorrador/VGDetalleCompraBorrador en models/restaurant.py), y las cuentas por
pagar (abonos contra VGCompra con saldo pendiente) — espejo de facturacion_views.py
pero para el lado de los egresos a proveedores en vez de los ingresos de clientes.

Reutiliza _serialize_compra/_finalizar_estado_pago_compra de api_views.py para no
duplicar esa lógica entre el alta manual, la importación por Excel y este borrador.
"""
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .api_views import (
    _costo_unitario_por_compra,
    _finalizar_estado_pago_compra,
    _serialize_abono_compra,
    _serialize_compra,
)
from .auth_helpers import _auth_response, _is_admin_user
from .gastos_views import _serialize_gasto
from .models import (
    VGAbonoCompra,
    VGCompra,
    VGCompraBorrador,
    VGDetalleCompra,
    VGDetalleCompraBorrador,
    VGGasto,
    VGIngrediente,
    VGMetodoPago,
    VGMovimientoInventario,
)
from .tasa_cambio import obtener_tasa_actual, tasa_cambio_para_registro

# Mismos valores y mismo motivo que en facturacion_views.py: TOLERANCIA_REDONDEO_ABONO
# absorbe el redondeo de convertir un pago en bolivares a dolares (muchisimo mas chico
# que un centavo real, nunca un sobrepago genuino); TOLERANCIA_CIERRE_ABONO decide
# cuando un saldo restante minusculo (polvo de redondeo entre tasas distintas) se
# perdona del todo en vez de dejar la cuenta "abonada_parcial" por unos centimos.
TOLERANCIA_REDONDEO_ABONO = Decimal('0.00001')
TOLERANCIA_CIERRE_ABONO = Decimal('0.01')


def _get_borrador_abierto():
    return VGCompraBorrador.objects.filter(estado='abierto').order_by('-fecha_creacion').first()


def _serialize_detalle_borrador(detalle):
    return {
        'id': detalle.id,
        'ingrediente_id': detalle.ingrediente_id,
        'ingrediente_nombre': detalle.ingrediente.nombre,
        'unidad_medida': detalle.ingrediente.unidad_medida,
        'cantidad': str(detalle.cantidad),
        'precio_total': str(detalle.precio_total),
        'costo_unitario': str(detalle.costo_unitario.quantize(Decimal('0.000001'))) if detalle.cantidad else '0',
        'tasa_cambio_referencia': str(detalle.tasa_cambio_referencia) if detalle.tasa_cambio_referencia is not None else None,
        'precio_total_bs': (
            str((detalle.precio_total * detalle.tasa_cambio_referencia).quantize(Decimal('0.01')))
            if detalle.tasa_cambio_referencia else None
        ),
    }


def _serialize_borrador(borrador):
    if borrador is None:
        return {'id': None, 'detalles': [], 'total': '0'}
    detalles = list(borrador.detalles.select_related('ingrediente').order_by('fecha_creacion'))
    total = sum((detalle.precio_total for detalle in detalles), Decimal('0'))
    return {
        'id': borrador.id,
        'detalles': [_serialize_detalle_borrador(detalle) for detalle in detalles],
        'total': str(total),
    }


@csrf_exempt
def admin_compra_borrador_view(request):
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    return _auth_response({'ok': True, 'borrador': _serialize_borrador(_get_borrador_abierto())})


@csrf_exempt
def admin_compra_borrador_agregar_view(request):
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    try:
        cantidad = Decimal(str(data.get('cantidad', '')))
    except InvalidOperation:
        return _auth_response({'ok': False, 'message': 'La cantidad debe ser numerica.'}, status=400)
    if cantidad <= 0:
        return _auth_response({'ok': False, 'message': 'La cantidad debe ser mayor a cero.'}, status=400)

    # El precio de esta linea se puede cargar en UNA sola moneda — en dolares
    # (`precio_total`) o en bolivares (`precio_total_bs`), nunca las dos a la
    # vez (mismo criterio que admin_gastos_view/compra_abono_view). Si se
    # carga en bolivares, ese es el monto EXACTO que se congela con la tasa
    # BCV de hoy y nunca se recalcula después, aunque el lote se termine de
    # armar o confirmar días más tarde con el BCV ya distinto.
    precio_total_raw = data.get('precio_total')
    precio_total_bs_raw = data.get('precio_total_bs')
    tiene_precio = precio_total_raw not in (None, '')
    tiene_precio_bs = precio_total_bs_raw not in (None, '')
    if tiene_precio and tiene_precio_bs:
        return _auth_response({
            'ok': False,
            'message': 'Ingresa el precio solo en dólares o solo en bolívares, no en los dos.',
        }, status=400)

    tasa_linea = None
    if tiene_precio_bs:
        try:
            precio_total_bs = Decimal(str(precio_total_bs_raw))
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'El precio en bolívares no es válido.'}, status=400)
        if precio_total_bs < 0:
            return _auth_response({'ok': False, 'message': 'El precio en bolívares no puede ser negativo.'}, status=400)

        if precio_total_bs == 0:
            precio_total = Decimal('0')
        else:
            tasa_actual = obtener_tasa_actual()
            tasa_linea = tasa_actual.tasa if tasa_actual else None
            if not tasa_linea or tasa_linea <= 0:
                return _auth_response({
                    'ok': False,
                    'message': 'No hay tasa de cambio disponible para convertir el precio a dólares.',
                }, status=400)
            precio_total = (precio_total_bs / tasa_linea).quantize(Decimal('0.000001'))
    else:
        try:
            precio_total = Decimal(str(precio_total_raw)) if tiene_precio else Decimal('0')
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'El precio total no es válido.'}, status=400)
        # Precio en 0 SI se permite a propósito (ej. mercancía de cortesía/donada
        # que igual debe sumar al stock, sin generar deuda con el proveedor) —
        # solo se bloquea un precio negativo, que no tiene sentido.
        if precio_total < 0:
            return _auth_response({'ok': False, 'message': 'El precio total pagado no puede ser negativo.'}, status=400)
        if precio_total > 0:
            tasa_linea = tasa_cambio_para_registro()

    ingrediente_id = data.get('ingrediente_id')
    with transaction.atomic():
        if ingrediente_id not in (None, ''):
            try:
                ingrediente = VGIngrediente.objects.get(pk=int(ingrediente_id))
            except (ValueError, TypeError, VGIngrediente.DoesNotExist):
                return _auth_response({'ok': False, 'message': 'El ingrediente seleccionado no existe.'}, status=400)
        else:
            nombre = str(data.get('nombre', '') or '').strip()
            if not nombre:
                return _auth_response({'ok': False, 'message': 'El nombre del ingrediente es obligatorio.'}, status=400)
            unidad = str(data.get('unidad', '') or '').strip()
            if unidad not in dict(VGIngrediente.UNIDADES):
                return _auth_response({'ok': False, 'message': 'Indica una unidad valida (g, ml o unidad) para crear el ingrediente.'}, status=400)

            existente = VGIngrediente.objects.filter(nombre__iexact=nombre).first()
            if existente is not None:
                ingrediente = existente
            else:
                ingrediente = VGIngrediente.objects.create(
                    nombre=nombre,
                    unidad_medida=unidad,
                    stock_actual=Decimal('0'),
                    stock_minimo=Decimal('0'),
                    costo_unitario=Decimal('0'),
                    creado_por=request.user,
                    actualizado_por=request.user,
                )

        borrador = _get_borrador_abierto()
        if borrador is None:
            borrador = VGCompraBorrador.objects.create(creado_por=request.user, actualizado_por=request.user)

        VGDetalleCompraBorrador.objects.create(
            borrador=borrador,
            ingrediente=ingrediente,
            cantidad=cantidad,
            precio_total=precio_total,
            tasa_cambio_referencia=tasa_linea,
            creado_por=request.user,
        )

    return _auth_response({'ok': True, 'borrador': _serialize_borrador(borrador)}, status=201)


@csrf_exempt
def admin_compra_borrador_editar_view(request):
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    borrador = _get_borrador_abierto()
    if borrador is None:
        return _auth_response({'ok': False, 'message': 'No hay ningun borrador abierto.'}, status=400)

    try:
        detalle = borrador.detalles.get(pk=int(data.get('detalle_id')))
    except (ValueError, TypeError, VGDetalleCompraBorrador.DoesNotExist):
        return _auth_response({'ok': False, 'message': 'Esa fila del borrador no existe.'}, status=400)

    # Solo se permite corregir el monto en bolívares de una línea ya cargada
    # en bolívares, y siempre con la MISMA tasa que quedó congelada al
    # agregarla — así toda la factura mantiene una sola tasa, sin importar
    # cuánto tiempo pase entre agregar y confirmar.
    if not detalle.tasa_cambio_referencia:
        return _auth_response({
            'ok': False,
            'message': 'Esta línea no se cargó en bolívares, no se puede editar el monto en Bs.',
        }, status=400)

    precio_total_bs_raw = data.get('precio_total_bs')
    if precio_total_bs_raw in (None, ''):
        return _auth_response({'ok': False, 'message': 'Indica el nuevo monto en bolívares.'}, status=400)
    try:
        precio_total_bs = Decimal(str(precio_total_bs_raw))
    except InvalidOperation:
        return _auth_response({'ok': False, 'message': 'El precio en bolívares no es válido.'}, status=400)
    if precio_total_bs < 0:
        return _auth_response({'ok': False, 'message': 'El precio en bolívares no puede ser negativo.'}, status=400)

    tasa_linea = detalle.tasa_cambio_referencia
    precio_total = (precio_total_bs / tasa_linea).quantize(Decimal('0.000001'))

    detalle.precio_total = precio_total
    detalle.save(update_fields=['precio_total'])

    return _auth_response({'ok': True, 'borrador': _serialize_borrador(borrador)})


@csrf_exempt
def admin_compra_borrador_quitar_view(request):
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    borrador = _get_borrador_abierto()
    if borrador is None:
        return _auth_response({'ok': False, 'message': 'No hay ningun borrador abierto.'}, status=400)

    try:
        detalle = borrador.detalles.get(pk=int(data.get('detalle_id')))
    except (ValueError, TypeError, VGDetalleCompraBorrador.DoesNotExist):
        return _auth_response({'ok': False, 'message': 'Esa fila del borrador no existe.'}, status=400)

    detalle.delete()
    if not borrador.detalles.exists():
        borrador.delete()
        return _auth_response({'ok': True, 'borrador': _serialize_borrador(None)})

    return _auth_response({'ok': True, 'borrador': _serialize_borrador(borrador)})


@csrf_exempt
def admin_compra_borrador_descartar_view(request):
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    borrador = _get_borrador_abierto()
    if borrador is not None:
        borrador.delete()

    return _auth_response({'ok': True, 'borrador': _serialize_borrador(None)})


@csrf_exempt
def admin_compra_borrador_confirmar_view(request):
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    proveedor_nombre = str(data.get('proveedor_nombre', '') or '').strip()
    if not proveedor_nombre:
        return _auth_response({'ok': False, 'message': 'El proveedor es obligatorio para confirmar la carga.'}, status=400)
    numero_factura_proveedor = str(data.get('numero_factura_proveedor', '') or '').strip()

    # El total a pagar YA NO se calcula solo (nunca se asume la suma de las
    # líneas): el analista tiene que escribirlo a mano, en dólares o en
    # bolívares (nunca los dos) — obligatorio, incluso 0 (mercancía de
    # cortesía/obsequio del proveedor, que igual entra al inventario con su
    # costo real, ver el costeo por línea más abajo, sin generar deuda). Esto
    # es lo mismo que ya exige admin_ingredientes_import_view para la
    # importación por Excel.
    total_a_pagar_raw = data.get('total_a_pagar')
    total_a_pagar_bs_raw = data.get('total_a_pagar_bs')
    tiene_override_usd = total_a_pagar_raw not in (None, '')
    tiene_override_bs = total_a_pagar_bs_raw not in (None, '')
    if tiene_override_usd and tiene_override_bs:
        return _auth_response({
            'ok': False,
            'message': 'Ingresa el total a pagar solo en dólares o solo en bolívares, no en los dos.',
        }, status=400)
    if not tiene_override_usd and not tiene_override_bs:
        return _auth_response({
            'ok': False,
            'message': 'Escribe el total a pagar (en $ o en Bs) para poder confirmar la carga — usa 0 si es una cortesía sin costo.',
        }, status=400)

    total_a_pagar_override = None
    total_a_pagar_bs_override = None
    if tiene_override_usd:
        try:
            total_a_pagar_override = Decimal(str(total_a_pagar_raw))
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'El total a pagar no es válido.'}, status=400)
        if total_a_pagar_override < 0:
            return _auth_response({'ok': False, 'message': 'El total a pagar no puede ser negativo.'}, status=400)
    elif tiene_override_bs:
        try:
            total_a_pagar_bs_override = Decimal(str(total_a_pagar_bs_raw))
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'El total a pagar en bolívares no es válido.'}, status=400)
        if total_a_pagar_bs_override < 0:
            return _auth_response({'ok': False, 'message': 'El total a pagar en bolívares no puede ser negativo.'}, status=400)

    borrador = _get_borrador_abierto()
    if borrador is None or not borrador.detalles.exists():
        return _auth_response({'ok': False, 'message': 'El borrador esta vacio, agrega al menos un ingrediente.'}, status=400)

    with transaction.atomic():
        compra = VGCompra.objects.create(
            proveedor_nombre=proveedor_nombre,
            numero_factura_proveedor=numero_factura_proveedor,
            estado='recibido',
            tasa_cambio_referencia=tasa_cambio_para_registro(data.get('tasa_cambio_referencia')),
            creado_por=request.user,
            actualizado_por=request.user,
        )

        for detalle in borrador.detalles.select_related('ingrediente'):
            ingrediente = detalle.ingrediente
            costo_unitario = _costo_unitario_por_compra(detalle.precio_total, detalle.cantidad, ingrediente)
            ingrediente.stock_actual = Decimal(str(ingrediente.stock_actual)) + detalle.cantidad
            ingrediente.costo_unitario = costo_unitario
            ingrediente.ultimo_proveedor = proveedor_nombre
            ingrediente.actualizado_por = request.user
            ingrediente.save(update_fields=['stock_actual', 'costo_unitario', 'ultimo_proveedor', 'actualizado_por', 'fecha_actualizacion'])

            VGDetalleCompra.objects.create(
                compra=compra, ingrediente=ingrediente, cantidad=detalle.cantidad, costo_unitario=costo_unitario,
            )
            VGMovimientoInventario.objects.create(
                ingrediente=ingrediente,
                tipo_movimiento='entrada',
                cantidad=detalle.cantidad,
                motivo=f'Carga manual por lote — Compra #{compra.id}',
                compra=compra,
                creado_por=request.user,
            )

        if total_a_pagar_bs_override is not None:
            if not compra.tasa_cambio_referencia or compra.tasa_cambio_referencia <= 0:
                return _auth_response({
                    'ok': False,
                    'message': 'No hay tasa de cambio disponible para convertir el total a dólares.',
                }, status=400)
            # 6 decimales, no 2 (ver el comentario en VGCompra.total): redondear
            # a centavos aquí desalineaba saldo_pendiente de total_bs_factura y
            # dejaba un residuo al pagar exactamente ese monto en bolívares.
            compra.total = (total_a_pagar_bs_override / compra.tasa_cambio_referencia).quantize(Decimal('0.000001'))
            compra.total_bs_factura = total_a_pagar_bs_override.quantize(Decimal('0.01'))
            compra.moneda_origen = 'VES'
            compra.save(update_fields=['total', 'total_bs_factura', 'moneda_origen'])
        else:
            # 6 decimales, no 2 (ver el comentario en VGCompra.total).
            compra.total = total_a_pagar_override.quantize(Decimal('0.000001'))
            # La deuda real de este lote es en dólares (lo que el analista
            # escribió) — el equivalente en bolívares que se le muestre
            # después se recalcula con la tasa BCV vigente en cada momento, no
            # con la tasa del día en que se cargó (ver moneda_origen en el
            # modelo y _serialize_compra/compra_abono_view), igual que ya se
            # hace para la importación por Excel.
            compra.moneda_origen = 'USD'
            compra.save(update_fields=['total', 'moneda_origen'])
        _finalizar_estado_pago_compra(compra)

        borrador.delete()

    return _auth_response({
        'ok': True,
        'message': 'Compra registrada y cuenta por pagar generada.',
        'compra': _serialize_compra(compra, incluir_detalle=True),
    }, status=201)


# ---------------------------------------------------------------------------
# Cuentas por pagar
# ---------------------------------------------------------------------------
def cuentas_por_pagar_view(request):
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para ver cuentas por pagar.'}, status=401)

    # `estado=pagadas` es el historial de facturas ya saldadas (compras y
    # gastos), filtrado por cuándo se terminaron de pagar (fecha_actualizacion,
    # que se actualiza junto con estado_pago) — para responder "qué facturas
    # pagué en tal período". Por defecto (sin el parámetro) sigue siendo el
    # comportamiento de siempre: solo lo pendiente/abonado parcial.
    estado_filtro = str(request.GET.get('estado', '') or '').strip().lower()
    if estado_filtro == 'pagadas':
        desde_raw = request.GET.get('desde')
        hasta_raw = request.GET.get('hasta')
        try:
            desde = date.fromisoformat(desde_raw) if desde_raw else timezone.localdate().replace(day=1)
            hasta = date.fromisoformat(hasta_raw) if hasta_raw else timezone.localdate()
        except ValueError:
            return _auth_response({'ok': False, 'message': 'Las fechas no son validas.'}, status=400)
        if desde > hasta:
            return _auth_response({'ok': False, 'message': '"Desde" no puede ser posterior a "Hasta".'}, status=400)

        compras = (
            VGCompra.objects.filter(
                estado_pago='pagada', fecha_actualizacion__date__gte=desde, fecha_actualizacion__date__lte=hasta,
            )
            .order_by('-fecha_actualizacion')
        )
        gastos = (
            VGGasto.objects.filter(
                estado_pago='pagado', fecha_actualizacion__date__gte=desde, fecha_actualizacion__date__lte=hasta,
            )
            .select_related('categoria', 'creado_por')
            .order_by('-fecha_actualizacion')
        )
    else:
        compras = (
            VGCompra.objects.filter(estado_pago__in=['pendiente', 'abonada_parcial'])
            .order_by('fecha_creacion')
        )
        gastos = (
            VGGasto.objects.filter(estado_pago__in=['pendiente', 'abonada_parcial'])
            .select_related('categoria', 'creado_por')
            .order_by('fecha_creacion')
        )

    cuentas = [
        {**_serialize_compra(compra), 'tipo': 'compra'} for compra in compras
    ] + [
        {**_serialize_gasto(gasto), 'tipo': 'gasto'} for gasto in gastos
    ]
    return _auth_response({'ok': True, 'compras': cuentas})


@csrf_exempt
def compra_abono_view(request, compra_id):
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    # El abono se puede pagar en UNA sola moneda — en dolares (`monto`) o en
    # bolivares (`monto_bs`), nunca las dos a la vez (mismo criterio que
    # admin_gastos_view). Si se paga en dolares, el monto en bolivares que se
    # muestre despues se deriva de la tasa congelada de la compra.
    monto_raw = data.get('monto')
    monto_bs_raw = data.get('monto_bs')
    tiene_monto = monto_raw not in (None, '')
    tiene_monto_bs = monto_bs_raw not in (None, '')
    if tiene_monto and tiene_monto_bs:
        return _auth_response({
            'ok': False,
            'message': 'Ingresa el monto solo en dólares o solo en bolívares, no en los dos.',
        }, status=400)
    if not tiene_monto and not tiene_monto_bs:
        return _auth_response({'ok': False, 'message': 'Indica el monto del abono.'}, status=400)

    try:
        metodo_pago = VGMetodoPago.objects.get(pk=int(data.get('metodo_pago_id')), activo=True)
    except (TypeError, ValueError, VGMetodoPago.DoesNotExist):
        return _auth_response({'ok': False, 'message': 'El metodo de pago es invalido.'}, status=400)

    with transaction.atomic():
        try:
            compra = VGCompra.objects.select_for_update().get(pk=compra_id)
        except VGCompra.DoesNotExist:
            return _auth_response({'ok': False, 'message': 'La compra no existe.'}, status=404)

        if compra.estado_pago == 'pagada':
            return _auth_response({'ok': False, 'message': 'Esta cuenta ya esta saldada.'}, status=409)

        tasa_abono = None
        if tiene_monto_bs:
            try:
                monto_bs = Decimal(str(monto_bs_raw))
            except InvalidOperation:
                return _auth_response({'ok': False, 'message': 'El monto en bolívares no es válido.'}, status=400)
            if monto_bs <= 0:
                return _auth_response({'ok': False, 'message': 'El monto en bolívares debe ser mayor a cero.'}, status=400)

            # La MISMA tasa que usa _serialize_compra para mostrarle al
            # analista "debes Bs. X" — para que pagar exactamente ese monto en
            # bolívares salde la deuda completa. Una compra en bolívares (o
            # sin moneda_origen registrada, el comportamiento de siempre) usa
            # la tasa que quedó CONGELADA al cargarla — NUNCA la de hoy, para
            # que el BCV moviéndose entre que se cargó y se pagó no deje
            # residuo (reportado 2026-09, lote #26). Una compra cargada en
            # DÓLARES (por ahora solo desde la importación por Excel, ver
            # VGCompra.moneda_origen) es distinta: la deuda real está en
            # dólares, así que un pago en bolívares se convierte con la tasa
            # BCV VIGENTE (la de HOY), igual que ya hace gasto_abono_view para
            # un gasto en dólares — mezclar las dos tasas es justo lo que
            # dejaba residuos o rechazaba el pago final.
            if compra.moneda_origen == 'USD':
                tasa_actual = obtener_tasa_actual()
                tasa_abono = tasa_actual.tasa if tasa_actual else compra.tasa_cambio_referencia
            else:
                tasa_abono = compra.tasa_cambio_referencia
                if not tasa_abono or tasa_abono <= 0:
                    tasa_actual = obtener_tasa_actual()
                    tasa_abono = tasa_actual.tasa if tasa_actual else None
            if not tasa_abono or tasa_abono <= 0:
                return _auth_response({
                    'ok': False,
                    'message': 'No hay tasa de cambio disponible para convertir el monto a dólares.',
                }, status=400)
            # 6 decimales, no 2 — con la tasa BCV actual, redondear a centavos de
            # dolar aca perdia varios bolivares al reconvertir el monto despues.
            monto = (monto_bs / tasa_abono).quantize(Decimal('0.000001'))
        else:
            try:
                monto = Decimal(str(monto_raw))
            except InvalidOperation:
                return _auth_response({'ok': False, 'message': 'El monto no es valido.'}, status=400)
            if monto <= 0:
                return _auth_response({'ok': False, 'message': 'El monto debe ser mayor a cero.'}, status=400)
            tasa_abono = tasa_cambio_para_registro()

        if monto > compra.saldo_pendiente + TOLERANCIA_REDONDEO_ABONO:
            return _auth_response({
                'ok': False,
                'message': f'El monto excede el saldo pendiente (${compra.saldo_pendiente}).',
            }, status=400)

        referencia = str(data.get('referencia', '') or '').strip()

        abono = VGAbonoCompra.objects.create(
            compra=compra,
            monto=monto,
            metodo_pago=metodo_pago,
            referencia=referencia,
            tasa_cambio_referencia=tasa_abono,
            creado_por=request.user,
        )

        # 6 decimales, no 2 (mismo motivo que VGFactura.saldo_pendiente, ver
        # el comentario en el modelo) — nunca negativo. TOLERANCIA_CIERRE_ABONO
        # perdona un residuo minusculo (polvo de redondeo) en vez de dejar la
        # cuenta "abonada_parcial" por unos pocos centavos.
        saldo_restante = max(
            (compra.saldo_pendiente - monto).quantize(Decimal('0.000001')),
            Decimal('0'),
        )
        compra.saldo_pendiente = (
            Decimal('0') if saldo_restante <= TOLERANCIA_CIERRE_ABONO else saldo_restante
        )
        # Red de seguridad adicional para compras de ANTES de este arreglo, y
        # solo para las que NO están en dólares: para una compra en dólares
        # (moneda_origen='USD') cada abono en bolívares ya se convierte con la
        # tasa vigente del día en que se pagó (ver arriba), así que sumarlos
        # y compararlos contra el total valorado con la tasa VIEJA congelada
        # de cuando se cargó mezclaría dos tasas distintas — la tolerancia en
        # dólares de más arriba ya alcanza para esas. Para el resto (en
        # bolívares, o sin moneda_origen registrada): la deuda "real" en
        # bolívares es `total_bs_factura` si se cargó así, o si no, el total
        # en dólares valorado con la tasa que quedó congelada en la compra —
        # la MISMA cuenta que ve el analista como "debes Bs. X". Si abonos
        # VIEJOS quedaron convertidos con la tasa del día de cada pago en vez
        # de la tasa de la compra (antes de que compra_abono_view empezara a
        # usar siempre la tasa de la compra), esto perdona el residuo de esa
        # inconsistencia histórica.
        deuda_bs = (
            None
            if compra.moneda_origen == 'USD'
            else compra.total_bs_factura
            if compra.total_bs_factura is not None
            else (compra.total * compra.tasa_cambio_referencia).quantize(Decimal('0.01'))
            if compra.tasa_cambio_referencia
            else None
        )
        if deuda_bs is not None and compra.tasa_cambio_referencia:
            abonado_bs = sum(
                (
                    registro.monto * registro.tasa_cambio_referencia
                    for registro in compra.abonos.all()
                    if registro.tasa_cambio_referencia is not None
                ),
                Decimal('0'),
            )
            # El residuo se compara en DÓLARES (no en bolívares) para decidir
            # si se perdona.
            saldo_bs = deuda_bs - abonado_bs
            saldo_equivalente_usd = saldo_bs / compra.tasa_cambio_referencia
            if saldo_equivalente_usd <= TOLERANCIA_CIERRE_ABONO:
                compra.saldo_pendiente = Decimal('0.00')
        compra.estado_pago = 'pagada' if compra.saldo_pendiente <= 0 else 'abonada_parcial'
        compra.actualizado_por = request.user
        compra.save(update_fields=['saldo_pendiente', 'estado_pago', 'actualizado_por', 'fecha_actualizacion'])

    return _auth_response({
        'ok': True,
        'message': 'Abono registrado correctamente.',
        'compra': _serialize_compra(compra, incluir_detalle=True),
        'abono': _serialize_abono_compra(abono),
    }, status=201)

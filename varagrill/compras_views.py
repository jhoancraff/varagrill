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

        total = Decimal('0')
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
            total += detalle.precio_total

        compra.total = total
        compra.save(update_fields=['total'])
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
    # admin_gastos_view). Si se paga en bolivares, ese es el monto EXACTO que
    # se registra (se congela con la tasa BCV de hoy, y nunca se recalcula
    # despues); si se paga en dolares, el monto en bolivares que se muestre
    # despues se deriva de esa misma tasa congelada.
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

    tasa_abono = None
    if tiene_monto_bs:
        try:
            monto_bs = Decimal(str(monto_bs_raw))
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'El monto en bolívares no es válido.'}, status=400)
        if monto_bs <= 0:
            return _auth_response({'ok': False, 'message': 'El monto en bolívares debe ser mayor a cero.'}, status=400)

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

        # Misma tolerancia que TOLERANCIA_REDONDEO_ABONO en facturacion_views.py:
        # un pago que salda la cuenta COMPLETA convertido de bolivares puede
        # traer 6 decimales de precision que redondean una fraccion de
        # centavo por ENCIMA del saldo (2 decimales) — sin esta tolerancia,
        # ese pago legitimo por el total exacto se rechazaba con este error.
        if monto > compra.saldo_pendiente + Decimal('0.00001'):
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

        # Redondeado a 2 decimales (y nunca negativo) antes de decidir el
        # estado — igual que _registrar_abono_gasto en gastos_views.py: monto
        # puede traer 6 decimales de precision (si se pago en bolivares, ver
        # arriba) pero saldo_pendiente siempre es un monto "limpio" en
        # dolares. Sin este redondeo, saldar una compra completa con un monto
        # convertido de bolivares podia dejar un residuo como "0.000002" —
        # mayor a cero, aunque el saldo mostrado ya redondeaba a $0.00 — y la
        # cuenta se quedaba en 'abonada_parcial' en vez de pasar a 'pagada'
        # (reportado 2026-09).
        compra.saldo_pendiente = max(
            (compra.saldo_pendiente - monto).quantize(Decimal('0.01')),
            Decimal('0.00'),
        )
        compra.estado_pago = 'pagada' if compra.saldo_pendiente <= 0 else 'abonada_parcial'
        compra.actualizado_por = request.user
        compra.save(update_fields=['saldo_pendiente', 'estado_pago', 'actualizado_por', 'fecha_actualizacion'])

    return _auth_response({
        'ok': True,
        'message': 'Abono registrado correctamente.',
        'compra': _serialize_compra(compra, incluir_detalle=True),
        'abono': _serialize_abono_compra(abono),
    }, status=201)

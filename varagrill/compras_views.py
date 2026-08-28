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
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.views.decorators.csrf import csrf_exempt

from .api_views import _finalizar_estado_pago_compra, _serialize_abono_compra, _serialize_compra
from .auth_helpers import _auth_response, _is_admin_user
from .models import (
    VGAbonoCompra,
    VGCompra,
    VGCompraBorrador,
    VGDetalleCompra,
    VGDetalleCompraBorrador,
    VGIngrediente,
    VGMetodoPago,
    VGMovimientoInventario,
)


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
        precio_total = Decimal(str(data.get('precio_total', '')))
    except InvalidOperation:
        return _auth_response({'ok': False, 'message': 'La cantidad y el precio total deben ser numericos.'}, status=400)

    if cantidad <= 0:
        return _auth_response({'ok': False, 'message': 'La cantidad debe ser mayor a cero.'}, status=400)
    if precio_total <= 0:
        return _auth_response({'ok': False, 'message': 'El precio total pagado debe ser mayor a cero.'}, status=400)

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
            creado_por=request.user,
            actualizado_por=request.user,
        )

        total = Decimal('0')
        for detalle in borrador.detalles.select_related('ingrediente'):
            costo_unitario = (detalle.precio_total / detalle.cantidad).quantize(Decimal('0.000001'))
            ingrediente = detalle.ingrediente
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

    compras = (
        VGCompra.objects.filter(estado_pago__in=['pendiente', 'abonada_parcial'])
        .order_by('fecha_creacion')
    )
    return _auth_response({'ok': True, 'compras': [_serialize_compra(compra) for compra in compras]})


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
            compra = VGCompra.objects.select_for_update().get(pk=compra_id)
        except VGCompra.DoesNotExist:
            return _auth_response({'ok': False, 'message': 'La compra no existe.'}, status=404)

        if compra.estado_pago == 'pagada':
            return _auth_response({'ok': False, 'message': 'Esta cuenta ya esta saldada.'}, status=409)

        if monto > compra.saldo_pendiente:
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
            creado_por=request.user,
        )

        compra.saldo_pendiente = compra.saldo_pendiente - monto
        compra.estado_pago = 'pagada' if compra.saldo_pendiente <= 0 else 'abonada_parcial'
        compra.actualizado_por = request.user
        compra.save(update_fields=['saldo_pendiente', 'estado_pago', 'actualizado_por', 'fecha_actualizacion'])

    return _auth_response({
        'ok': True,
        'message': 'Abono registrado correctamente.',
        'compra': _serialize_compra(compra, incluir_detalle=True),
        'abono': _serialize_abono_compra(abono),
    }, status=201)

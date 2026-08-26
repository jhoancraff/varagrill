"""
Vistas de gastos operativos (alquiler, servicios, nomina, mantenimiento...) — espejo de
compras_views.py pero para egresos que no pasan por inventario. Un gasto puede registrarse
ya pagado (crea su VGAbonoGasto por el monto completo en el mismo paso, ver
_registrar_abono_gasto) o pendiente para abonarlo despues, con abonos parciales igual que
las cuentas por pagar de proveedores.
"""
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Sum
from django.views.decorators.csrf import csrf_exempt

from .auth_helpers import _auth_response, _is_admin_user
from .models import VGAbonoGasto, VGCategoriaGasto, VGGasto, VGMetodoPago


def _serialize_categoria_gasto(categoria):
    return {'id': categoria.id, 'nombre': categoria.nombre, 'activo': categoria.activo}


def _serialize_abono_gasto(abono):
    return {
        'id': abono.id,
        'monto': str(abono.monto),
        'metodo_pago': abono.metodo_pago.nombre,
        'metodo_pago_id': abono.metodo_pago_id,
        'referencia': abono.referencia,
        'fecha_pago': abono.fecha_pago.isoformat(),
        'creado_por': (abono.creado_por.get_full_name() or abono.creado_por.username) if abono.creado_por else '',
    }


def _serialize_gasto(gasto, incluir_detalle=False):
    data = {
        'id': gasto.id,
        'categoria_id': gasto.categoria_id,
        'categoria_nombre': gasto.categoria.nombre,
        'descripcion': gasto.descripcion,
        'proveedor_nombre': gasto.proveedor_nombre,
        'numero_comprobante': gasto.numero_comprobante,
        'monto': str(gasto.monto),
        'saldo_pendiente': str(gasto.saldo_pendiente),
        'estado_pago': gasto.estado_pago,
        'fecha_gasto': gasto.fecha_gasto.isoformat(),
        'fecha_creacion': gasto.fecha_creacion.isoformat(),
        'notas': gasto.notas,
        'creado_por': (gasto.creado_por.get_full_name() or gasto.creado_por.username) if gasto.creado_por else '',
    }
    if incluir_detalle:
        data['abonos'] = [
            _serialize_abono_gasto(abono) for abono in gasto.abonos.select_related('metodo_pago').order_by('fecha_pago')
        ]
    return data


def _registrar_abono_gasto(gasto, monto, metodo_pago, referencia, operator):
    """
    Aplica un abono a un gasto: crea el VGAbonoGasto y deja saldo_pendiente/estado_pago
    consistentes. Usado tanto por gasto_abono_view (abono suelto) como por
    admin_gastos_view al crear un gasto ya pagado (abono por el monto completo en el mismo
    paso). El caller es responsable de validar monto > 0 y monto <= gasto.saldo_pendiente
    antes de llamar esta funcion, y de envolverla en una transaccion.
    """
    abono = VGAbonoGasto.objects.create(
        gasto=gasto, monto=monto, metodo_pago=metodo_pago, referencia=referencia, creado_por=operator,
    )
    gasto.saldo_pendiente = gasto.saldo_pendiente - monto
    gasto.estado_pago = 'pagado' if gasto.saldo_pendiente <= 0 else 'abonada_parcial'
    gasto.actualizado_por = operator
    gasto.save(update_fields=['saldo_pendiente', 'estado_pago', 'actualizado_por', 'fecha_actualizacion'])
    return abono


@csrf_exempt
def admin_categorias_gasto_view(request):
    if request.method not in ('GET', 'POST'):
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    if request.method == 'GET':
        categorias = VGCategoriaGasto.objects.order_by('nombre')
        return _auth_response({'ok': True, 'categorias': [_serialize_categoria_gasto(c) for c in categorias]})

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    action = str(data.get('action', '')).strip().lower()

    if action == 'create':
        nombre = str(data.get('nombre', '')).strip()
        if not nombre:
            return _auth_response({'ok': False, 'message': 'El nombre es obligatorio.'}, status=400)
        if VGCategoriaGasto.objects.filter(nombre__iexact=nombre).exists():
            return _auth_response({'ok': False, 'message': 'Ya existe una categoria con ese nombre.'}, status=400)

        categoria = VGCategoriaGasto.objects.create(nombre=nombre, creado_por=request.user, actualizado_por=request.user)
        return _auth_response({
            'ok': True, 'message': 'Categoria creada correctamente.', 'categoria': _serialize_categoria_gasto(categoria),
        }, status=201)

    if action == 'toggle':
        try:
            categoria = VGCategoriaGasto.objects.get(pk=int(data.get('id')))
        except (ValueError, TypeError, VGCategoriaGasto.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'La categoria no existe.'}, status=400)
        categoria.activo = not categoria.activo
        categoria.actualizado_por = request.user
        categoria.save(update_fields=['activo', 'actualizado_por', 'fecha_actualizacion'])
        return _auth_response({'ok': True, 'categoria': _serialize_categoria_gasto(categoria)})

    return _auth_response({'ok': False, 'message': 'Accion invalida.'}, status=400)


def _parse_fecha(raw, default=None):
    text = str(raw or '').strip()
    if not text:
        return default
    try:
        return date.fromisoformat(text)
    except ValueError:
        return default


@csrf_exempt
def admin_gastos_view(request):
    if request.method not in ('GET', 'POST'):
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    if request.method == 'GET':
        hoy = date.today()
        fecha_desde = _parse_fecha(request.GET.get('fecha_desde'), default=hoy.replace(day=1))
        fecha_hasta = _parse_fecha(request.GET.get('fecha_hasta'), default=hoy)
        categoria_id = request.GET.get('categoria_id')
        estado_pago = str(request.GET.get('estado_pago', '') or '').strip().lower()

        gastos = VGGasto.objects.select_related('categoria').filter(
            fecha_gasto__gte=fecha_desde, fecha_gasto__lte=fecha_hasta,
        )
        if categoria_id:
            try:
                gastos = gastos.filter(categoria_id=int(categoria_id))
            except (ValueError, TypeError):
                pass
        if estado_pago in {'pendiente', 'abonada_parcial', 'pagado'}:
            gastos = gastos.filter(estado_pago=estado_pago)

        gastos = list(gastos.order_by('-fecha_gasto', '-fecha_creacion'))

        totales_por_categoria = {}
        for gasto in gastos:
            entry = totales_por_categoria.setdefault(
                gasto.categoria_id, {'categoria_id': gasto.categoria_id, 'categoria_nombre': gasto.categoria.nombre, 'total': Decimal('0')},
            )
            entry['total'] += gasto.monto

        return _auth_response({
            'ok': True,
            'fecha_desde': fecha_desde.isoformat(),
            'fecha_hasta': fecha_hasta.isoformat(),
            'gastos': [_serialize_gasto(gasto) for gasto in gastos],
            'total_general': str(sum((gasto.monto for gasto in gastos), Decimal('0'))),
            'totales_por_categoria': [
                {**entry, 'total': str(entry['total'])} for entry in sorted(totales_por_categoria.values(), key=lambda e: e['categoria_nombre'])
            ],
        })

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    try:
        categoria = VGCategoriaGasto.objects.get(pk=int(data.get('categoria_id')))
    except (ValueError, TypeError, VGCategoriaGasto.DoesNotExist):
        return _auth_response({'ok': False, 'message': 'La categoria es invalida.'}, status=400)

    descripcion = str(data.get('descripcion', '') or '').strip()
    if not descripcion:
        return _auth_response({'ok': False, 'message': 'La descripcion es obligatoria.'}, status=400)

    try:
        monto = Decimal(str(data.get('monto', '')))
    except InvalidOperation:
        return _auth_response({'ok': False, 'message': 'El monto no es valido.'}, status=400)
    if monto <= 0:
        return _auth_response({'ok': False, 'message': 'El monto debe ser mayor a cero.'}, status=400)

    fecha_gasto = _parse_fecha(data.get('fecha_gasto'), default=date.today())

    pagado_de_una_vez = bool(data.get('pagado_de_una_vez'))
    metodo_pago = None
    if pagado_de_una_vez:
        try:
            metodo_pago = VGMetodoPago.objects.get(pk=int(data.get('metodo_pago_id')), activo=True)
        except (TypeError, ValueError, VGMetodoPago.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'El metodo de pago es invalido.'}, status=400)

    with transaction.atomic():
        gasto = VGGasto.objects.create(
            categoria=categoria,
            descripcion=descripcion,
            proveedor_nombre=str(data.get('proveedor_nombre', '') or '').strip(),
            numero_comprobante=str(data.get('numero_comprobante', '') or '').strip(),
            monto=monto,
            saldo_pendiente=monto,
            estado_pago='pendiente',
            fecha_gasto=fecha_gasto,
            notas=str(data.get('notas', '') or '').strip(),
            creado_por=request.user,
            actualizado_por=request.user,
        )
        if pagado_de_una_vez:
            _registrar_abono_gasto(gasto, monto, metodo_pago, '', request.user)

    return _auth_response({
        'ok': True,
        'message': 'Gasto registrado correctamente.',
        'gasto': _serialize_gasto(gasto, incluir_detalle=True),
    }, status=201)


def gasto_detail_view(request, gasto_id):
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    try:
        gasto = VGGasto.objects.select_related('categoria').get(pk=gasto_id)
    except VGGasto.DoesNotExist:
        return _auth_response({'ok': False, 'message': 'El gasto no existe.'}, status=404)

    return _auth_response({'ok': True, 'gasto': _serialize_gasto(gasto, incluir_detalle=True)})


@csrf_exempt
def gasto_abono_view(request, gasto_id):
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
            gasto = VGGasto.objects.select_for_update().get(pk=gasto_id)
        except VGGasto.DoesNotExist:
            return _auth_response({'ok': False, 'message': 'El gasto no existe.'}, status=404)

        if gasto.estado_pago == 'pagado':
            return _auth_response({'ok': False, 'message': 'Este gasto ya esta saldado.'}, status=409)

        if monto > gasto.saldo_pendiente:
            return _auth_response({
                'ok': False,
                'message': f'El monto excede el saldo pendiente (${gasto.saldo_pendiente}).',
            }, status=400)

        referencia = str(data.get('referencia', '') or '').strip()
        abono = _registrar_abono_gasto(gasto, monto, metodo_pago, referencia, request.user)

    return _auth_response({
        'ok': True,
        'message': 'Abono registrado correctamente.',
        'gasto': _serialize_gasto(gasto, incluir_detalle=True),
        'abono': _serialize_abono_gasto(abono),
    }, status=201)

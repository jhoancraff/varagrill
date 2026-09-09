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
from .tasa_cambio import obtener_tasa_actual, tasa_cambio_para_registro


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
        'tasa_cambio_referencia': str(abono.tasa_cambio_referencia) if abono.tasa_cambio_referencia is not None else None,
        'creado_por': (abono.creado_por.get_full_name() or abono.creado_por.username) if abono.creado_por else '',
    }


def _serialize_gasto(gasto, incluir_detalle=False):
    # saldo_pendiente se guarda con solo 2 decimales (ver docstring de VGGasto),
    # asi que reconvertirlo a bolivares pierde los centimos de monto (6
    # decimales) frente al total en bs del reporte de gastos, mostrando un
    # monto distinto para la misma deuda en cuentas por pagar. Para que
    # coincidan, el saldo en bs se calcula desde monto con toda su precision
    # menos lo realmente abonado (abono.monto tambien usa 6 decimales), en vez
    # de partir del saldo_pendiente ya redondeado.
    saldo_preciso = gasto.monto - sum((abono.monto for abono in gasto.abonos.all()), Decimal('0'))

    # Un gasto registrado en bolivares queda fijo en ese monto de bs (siempre
    # se reconstruye con la tasa del dia que se registro, tasa_cambio_referencia)
    # sin importar que el BCV cambie despues. Uno registrado en dolares, en
    # cambio, debe mostrar su equivalente en bs actualizado con la tasa ACTUAL
    # mientras siga pendiente, para reflejar lo que realmente costaria saldarlo hoy.
    if gasto.moneda_origen == 'VES':
        tasa_para_bs = gasto.tasa_cambio_referencia
    else:
        tasa_actual = obtener_tasa_actual()
        tasa_para_bs = tasa_actual.tasa if tasa_actual else gasto.tasa_cambio_referencia

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
        'moneda_origen': gasto.moneda_origen,
        'tasa_cambio_referencia': str(gasto.tasa_cambio_referencia) if gasto.tasa_cambio_referencia is not None else None,
        'total_bs': str((gasto.monto * tasa_para_bs).quantize(Decimal('0.01'))) if tasa_para_bs else None,
        'saldo_pendiente_bs': str((saldo_preciso * tasa_para_bs).quantize(Decimal('0.01'))) if tasa_para_bs else None,
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
        tasa_cambio_referencia=tasa_cambio_para_registro(),
    )
    # Redondeado a 2 decimales (y nunca negativo): monto puede traer 6
    # decimales de precision (ver VGGasto.monto) pero saldo_pendiente siempre
    # es un monto "limpio" en dolares — sin este redondeo, pagar un gasto
    # completo con un monto convertido de bolivares podia dejar un saldo
    # como "0.000007" en vez de un 0.00 exacto.
    gasto.saldo_pendiente = max(
        (gasto.saldo_pendiente - monto).quantize(Decimal('0.01')),
        Decimal('0.00'),
    )
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

    # El gasto se ingresa en UNA sola moneda — en dolares (`monto`) o en
    # bolivares (`monto_bs`), nunca las dos a la vez, para no dejar ambiguo
    # cual de los dos numeros es el que de verdad se gasto.
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
        return _auth_response({'ok': False, 'message': 'Indica el monto del gasto.'}, status=400)

    tasa_gasto = None
    if tiene_monto_bs:
        try:
            monto_bs = Decimal(str(monto_bs_raw))
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'El monto en bolívares no es válido.'}, status=400)
        if monto_bs <= 0:
            return _auth_response({'ok': False, 'message': 'El monto en bolívares debe ser mayor a cero.'}, status=400)

        # Tasa BCV de HOY, congelada en el momento en que se registra el gasto —
        # el mismo criterio que el resto del sistema (ver
        # _tasa_conversion_vigente en facturacion_views.py): un gasto se
        # registra y convierte en el mismo instante, así que no hay "cotizado
        # antes, pagado después" que pueda desfasarse por un refresco del
        # cache del BCV — lo que se convierte es exactamente lo que se contó.
        tasa_actual = obtener_tasa_actual()
        tasa_gasto = tasa_actual.tasa if tasa_actual else None
        if not tasa_gasto or tasa_gasto <= 0:
            return _auth_response({
                'ok': False,
                'message': 'No hay tasa de cambio disponible para convertir el monto a dólares.',
            }, status=400)
        # 6 decimales, no 2 (ver el docstring de VGGasto.monto): con la tasa
        # BCV actual, redondear a centavos de dolar aca perdia varios
        # bolivares al reconvertir el monto para mostrarlo despues.
        monto = (monto_bs / tasa_gasto).quantize(Decimal('0.000001'))
    else:
        try:
            monto = Decimal(str(monto_raw))
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
            saldo_pendiente=monto.quantize(Decimal('0.01')),
            estado_pago='pendiente',
            fecha_gasto=fecha_gasto,
            notas=str(data.get('notas', '') or '').strip(),
            # Si se ingreso en bolivares, la tasa que de verdad se uso para
            # convertirlo (ver arriba) — asi el monto en bolivares que se
            # muestre despues siempre reconstruye exactamente lo que se
            # contó, sin importar que el BCV cambie más tarde.
            tasa_cambio_referencia=tasa_gasto if tiene_monto_bs else tasa_cambio_para_registro(data.get('tasa_cambio_referencia')),
            moneda_origen='VES' if tiene_monto_bs else 'USD',
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

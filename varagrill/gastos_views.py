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
from .models import VGAbonoGasto, VGCategoriaGasto, VGCorreccionGasto, VGGasto, VGMetodoPago
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


def _serialize_correccion_gasto(correccion):
    return {
        'motivo': correccion.motivo,
        'monto_anterior': str(correccion.monto_anterior) if correccion.monto_anterior is not None else None,
        'monto_nuevo': str(correccion.monto_nuevo) if correccion.monto_nuevo is not None else None,
        'fecha_gasto_anterior': correccion.fecha_gasto_anterior.isoformat() if correccion.fecha_gasto_anterior else None,
        'fecha_gasto_nueva': correccion.fecha_gasto_nueva.isoformat() if correccion.fecha_gasto_nueva else None,
        'metodo_anterior': correccion.metodo_anterior.nombre if correccion.metodo_anterior else None,
        'metodo_nuevo': correccion.metodo_nuevo.nombre if correccion.metodo_nuevo else None,
        'corregido_por': (correccion.creado_por.get_full_name() or correccion.creado_por.username) if correccion.creado_por else '',
        'fecha_creacion': correccion.fecha_creacion.isoformat(),
    }


def _ultimas_correcciones_gasto(gasto_ids):
    """
    Ultima VGCorreccionGasto de cada gasto — para mostrar junto a la fila del
    reporte de gastos el motivo de la ultima edicion manual (monto, metodo
    de pago o fecha), igual que _ultimas_correcciones_por_registro hace para
    los pagos del cuadre de caja (ver contabilidad_views.py).
    """
    if not gasto_ids:
        return {}
    correcciones = (
        VGCorreccionGasto.objects
        .filter(gasto_id__in=gasto_ids)
        .select_related('metodo_anterior', 'metodo_nuevo', 'creado_por')
        .order_by('gasto_id', '-fecha_creacion')
    )
    resultado = {}
    for correccion in correcciones:
        if correccion.gasto_id not in resultado:
            resultado[correccion.gasto_id] = _serialize_correccion_gasto(correccion)
    return resultado


def _serialize_gasto(gasto, incluir_detalle=False, ultima_correccion=None):
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
        'ultima_correccion': ultima_correccion,
    }
    if incluir_detalle:
        data['abonos'] = [
            _serialize_abono_gasto(abono) for abono in gasto.abonos.select_related('metodo_pago').order_by('fecha_pago')
        ]
    return data


def _registrar_abono_gasto(gasto, monto, metodo_pago, referencia, operator, tasa_cambio_referencia=None):
    """
    Aplica un abono a un gasto: crea el VGAbonoGasto y deja saldo_pendiente/estado_pago
    consistentes. Usado tanto por gasto_abono_view (abono suelto) como por
    admin_gastos_view al crear un gasto ya pagado (abono por el monto completo en el mismo
    paso). El caller es responsable de validar monto > 0 y monto <= gasto.saldo_pendiente
    antes de llamar esta funcion, y de envolverla en una transaccion.
    """
    abono = VGAbonoGasto.objects.create(
        gasto=gasto, monto=monto, metodo_pago=metodo_pago, referencia=referencia, creado_por=operator,
        tasa_cambio_referencia=tasa_cambio_referencia if tasa_cambio_referencia is not None else tasa_cambio_para_registro(),
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
        correcciones = _ultimas_correcciones_gasto([gasto.id for gasto in gastos])

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
            'gastos': [_serialize_gasto(gasto, ultima_correccion=correcciones.get(gasto.id)) for gasto in gastos],
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


@csrf_exempt
def gasto_detail_view(request, gasto_id):
    """
    GET devuelve el detalle completo de un gasto (con sus abonos). POST edita
    manualmente monto, metodo de pago (solo si el gasto tiene un unico abono,
    ver mas abajo) y/o fecha del gasto ya registrado — usado desde el modal
    de edicion del reporte de gastos operativos. El motivo es obligatorio a
    proposito (ver VGCorreccionGasto): deja un rastro auditable de por que se
    corrigio el gasto, no solo que se corrigio.
    """
    if request.method not in ('GET', 'POST'):
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    if request.method == 'GET':
        try:
            gasto = VGGasto.objects.select_related('categoria').get(pk=gasto_id)
        except VGGasto.DoesNotExist:
            return _auth_response({'ok': False, 'message': 'El gasto no existe.'}, status=404)
        ultima_correccion = _ultimas_correcciones_gasto([gasto.id]).get(gasto.id)
        return _auth_response({'ok': True, 'gasto': _serialize_gasto(gasto, incluir_detalle=True, ultima_correccion=ultima_correccion)})

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    if str(data.get('action', '')).strip().lower() != 'editar':
        return _auth_response({'ok': False, 'message': 'Accion invalida.'}, status=400)

    # Obligatorio a proposito, igual que 'cambiar_metodo_pago' en
    # contabilidad_views.py: es lo que deja un rastro auditable de POR QUE se
    # corrigio el gasto, no solo que se corrigio.
    motivo = str(data.get('motivo', '') or '').strip()
    if not motivo:
        return _auth_response({'ok': False, 'message': 'La descripcion para auditoria es obligatoria.'}, status=400)

    with transaction.atomic():
        try:
            gasto = VGGasto.objects.select_for_update().select_related('categoria').get(pk=gasto_id)
        except VGGasto.DoesNotExist:
            return _auth_response({'ok': False, 'message': 'El gasto no existe.'}, status=404)

        abonos = list(gasto.abonos.select_related('metodo_pago').order_by('fecha_pago'))
        # El metodo de pago vive en el VGAbonoGasto, no en el VGGasto (ver su
        # docstring) — solo tiene sentido "cambiar el metodo de pago de un
        # gasto" cuando hay exactamente un abono (el caso comun de "pagado de
        # una vez"); con varios abonos o ninguno, a cual moverle la plata es
        # ambiguo, asi que esa edicion se rechaza mas abajo.
        abono_unico = abonos[0] if len(abonos) == 1 else None
        # Se decide ANTES de tocar nada: si el unico abono ya cubria el gasto
        # completo (estado 'pagado'), el monto editado representa "cuanto se
        # pago de verdad" y el abono se resincroniza para que se quede
        # pagado — evaluar esto DESPUES de recalcular saldo_pendiente con el
        # monto nuevo (comparando contra 0) fallaba: con un abono aun con su
        # monto viejo, esa comparacion casi siempre da un saldo > 0 y dejaba
        # el gasto en 'abonada_parcial' con un saldo fantasma en vez de
        # mantenerlo pagado.
        abono_cubria_completo = abono_unico is not None and gasto.estado_pago == 'pagado'

        correccion_kwargs = {}
        gasto_update_fields = []
        cambios = []

        monto_raw = data.get('monto')
        if monto_raw not in (None, ''):
            try:
                monto_nuevo = Decimal(str(monto_raw))
            except InvalidOperation:
                return _auth_response({'ok': False, 'message': 'El monto no es valido.'}, status=400)
            if monto_nuevo <= 0:
                return _auth_response({'ok': False, 'message': 'El monto debe ser mayor a cero.'}, status=400)

            monto_abonado = sum((a.monto for a in abonos), Decimal('0'))
            # Si el unico abono cubria el gasto completo se va a resincronizar
            # con el monto nuevo (ver abajo), asi que no hay "abonado" que
            # actue como piso — sin este salto, bajar el monto de un gasto ya
            # pagado por debajo de su abono viejo se rechazaba aunque el
            # abono estuviera a punto de ajustarse exactamente a ese mismo monto.
            if not abono_cubria_completo and monto_nuevo < monto_abonado:
                return _auth_response({
                    'ok': False,
                    'message': f'El nuevo monto (${monto_nuevo}) es menor a lo ya abonado (${monto_abonado}).',
                }, status=400)

            if monto_nuevo != gasto.monto:
                correccion_kwargs['monto_anterior'] = gasto.monto
                correccion_kwargs['monto_nuevo'] = monto_nuevo
                gasto.monto = monto_nuevo
                gasto_update_fields += ['monto', 'saldo_pendiente', 'estado_pago']
                if abono_cubria_completo:
                    # El unico abono representaba "todo lo que se pago" — se
                    # resincroniza con el nuevo monto para que el gasto se
                    # quede pagado, en vez de recalcular un saldo contra su
                    # monto viejo.
                    abono_unico.monto = monto_nuevo
                    abono_unico.save(update_fields=['monto'])
                    gasto.saldo_pendiente = Decimal('0.00')
                    gasto.estado_pago = 'pagado'
                else:
                    gasto.saldo_pendiente = (monto_nuevo - monto_abonado).quantize(Decimal('0.01'))
                    gasto.estado_pago = (
                        'pagado' if gasto.saldo_pendiente <= 0 else ('abonada_parcial' if abonos else 'pendiente')
                    )
                cambios.append('el monto')

        fecha_raw = data.get('fecha_gasto')
        if fecha_raw not in (None, ''):
            fecha_nueva = _parse_fecha(fecha_raw)
            if fecha_nueva is None:
                return _auth_response({'ok': False, 'message': 'La fecha del gasto no es valida.'}, status=400)
            if fecha_nueva != gasto.fecha_gasto:
                correccion_kwargs['fecha_gasto_anterior'] = gasto.fecha_gasto
                correccion_kwargs['fecha_gasto_nueva'] = fecha_nueva
                gasto.fecha_gasto = fecha_nueva
                gasto_update_fields.append('fecha_gasto')
                cambios.append('la fecha')

        metodo_pago_id = data.get('metodo_pago_id')
        if metodo_pago_id not in (None, ''):
            if abono_unico is None:
                return _auth_response({
                    'ok': False,
                    'message': 'Solo se puede cambiar el metodo de pago de un gasto con un unico abono.',
                }, status=400)
            try:
                metodo_nuevo = VGMetodoPago.objects.get(pk=int(metodo_pago_id), activo=True)
            except (TypeError, ValueError, VGMetodoPago.DoesNotExist):
                return _auth_response({'ok': False, 'message': 'El metodo de pago es invalido.'}, status=400)

            if metodo_nuevo.id != abono_unico.metodo_pago_id:
                correccion_kwargs['metodo_anterior'] = abono_unico.metodo_pago
                correccion_kwargs['metodo_nuevo'] = metodo_nuevo
                abono_unico.metodo_pago = metodo_nuevo
                abono_update_fields = ['metodo_pago']
                # Mismo criterio que 'cambiar_metodo_pago' en
                # contabilidad_views.py: si pasa a una cuenta en bolivares y
                # el abono no tenia tasa congelada, se congela la de ahora —
                # sin esto no habria con que mostrar su equivalente en bs.
                if metodo_nuevo.moneda == 'VES' and not abono_unico.tasa_cambio_referencia:
                    tasa_nueva = tasa_cambio_para_registro()
                    if tasa_nueva:
                        abono_unico.tasa_cambio_referencia = tasa_nueva
                        abono_update_fields.append('tasa_cambio_referencia')
                abono_unico.save(update_fields=abono_update_fields)
                cambios.append('el metodo de pago')

        if not correccion_kwargs:
            return _auth_response({'ok': False, 'message': 'No hay cambios que guardar.'}, status=400)

        gasto.actualizado_por = request.user
        gasto.save(update_fields=[*gasto_update_fields, 'actualizado_por', 'fecha_actualizacion'])

        correccion = VGCorreccionGasto.objects.create(
            gasto=gasto, motivo=motivo, creado_por=request.user, actualizado_por=request.user, **correccion_kwargs,
        )

    return _auth_response({
        'ok': True,
        'message': f'Se actualizó {" y ".join(cambios)} del gasto.',
        'gasto': _serialize_gasto(gasto, incluir_detalle=True, ultima_correccion=_serialize_correccion_gasto(correccion)),
    })


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

    # Mismo criterio que admin_gastos_view al crear el gasto: el abono se paga
    # en UNA sola moneda — en dolares (`monto`) o en bolivares (`monto_bs`),
    # nunca las dos a la vez. Pagado en bolivares, ese es el monto EXACTO que
    # se registra (se congela con la tasa BCV de hoy y nunca se recalcula
    # despues); pagado en dolares, el bolivar que se muestre despues se deriva
    # de esa misma tasa congelada.
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
            gasto = VGGasto.objects.select_for_update().get(pk=gasto_id)
        except VGGasto.DoesNotExist:
            return _auth_response({'ok': False, 'message': 'El gasto no existe.'}, status=404)

        if gasto.estado_pago == 'pagado':
            return _auth_response({'ok': False, 'message': 'Este gasto ya esta saldado.'}, status=409)

        # Misma tolerancia que TOLERANCIA_REDONDEO_ABONO en facturacion_views.py:
        # un pago que salda el gasto COMPLETO convertido de bolivares puede
        # traer 6 decimales de precision que redondean una fraccion de
        # centavo por ENCIMA del saldo (2 decimales) — sin esta tolerancia,
        # ese pago legitimo por el total exacto se rechazaba con este error.
        if monto > gasto.saldo_pendiente + Decimal('0.00001'):
            return _auth_response({
                'ok': False,
                'message': f'El monto excede el saldo pendiente (${gasto.saldo_pendiente}).',
            }, status=400)

        referencia = str(data.get('referencia', '') or '').strip()
        abono = _registrar_abono_gasto(gasto, monto, metodo_pago, referencia, request.user, tasa_cambio_referencia=tasa_abono)

    return _auth_response({
        'ok': True,
        'message': 'Abono registrado correctamente.',
        'gasto': _serialize_gasto(gasto, incluir_detalle=True),
        'abono': _serialize_abono_gasto(abono),
    }, status=201)

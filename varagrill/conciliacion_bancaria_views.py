"""
Endpoints de la conciliacion bancaria por movimiento (ver conciliacion_bancaria.py). Solo
administrador y contador (_is_admin_user): sin sesion 401, con sesion pero sin permiso 403.
"""
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from . import conciliacion_bancaria as motor
from .auth_helpers import _auth_response, _is_admin_user
from .banco_excel import ExtractoInvalido, parsear_extracto
from .models import (
    VGAbonoCompra, VGAbonoGasto, VGCierreConciliacion, VGConciliacionMovimiento, VGExtractoBancario, VGGasto, VGIngresoExtra,
    VGMovimientoBancario, VGPago, VGTransferenciaCuenta,
)

MAX_TAMANO_EXTRACTO_BYTES = 5 * 1024 * 1024
MAX_DIAS_RANGO = 366
MAX_ERRORES_VISTA_PREVIA = 25


def _sin_permiso(request):
    if not request.user.is_authenticated:
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion.'}, status=401)
    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Solo el administrador o el contador pueden conciliar con el banco.'}, status=403)
    return None


def _metodo_no_permitido():
    return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)


def _leer_json(request):
    try:
        return json.loads(request.body.decode('utf-8')) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _rango(origen):
    """(desde, hasta) desde un dict con 'desde' y 'hasta' ISO, o None si algo esta mal."""
    try:
        desde = date.fromisoformat(str(origen.get('desde')))
        hasta = date.fromisoformat(str(origen.get('hasta')))
    except (TypeError, ValueError):
        return None
    if desde > hasta or (hasta - desde).days + 1 > MAX_DIAS_RANGO:
        return None
    return desde, hasta


def _cuenta_valida(nombre):
    """El nombre normalizado de una cuenta que existe, o None."""
    nombre = motor.normalizar_cuenta(nombre)
    return nombre if any(c['nombre'] == nombre for c in motor.cuentas_disponibles()) else None


def _money(valor):
    return None if valor is None else str(Decimal(valor).quantize(Decimal('0.01')))


# ---------------------------------------------------------------------------
# Serializacion
# ---------------------------------------------------------------------------
def _etiquetas_origenes(vinculos):
    """{(origen_tipo, origen_id): texto} leyendo cada tabla una sola vez."""
    ids = defaultdict(set)
    for v in vinculos:
        ids[v.origen_tipo].add(v.origen_id)
    etiquetas = {}
    for p in VGPago.objects.filter(id__in=ids['pago']).select_related('nota_entrega', 'factura', 'metodo_pago'):
        doc = (
            f'Nota de entrega {p.nota_entrega.codigo}' if p.nota_entrega_id
            else f'Factura {p.factura.numero_factura}' if p.factura_id else f'Pedido #{p.pedido_id}'
        )
        etiquetas[('pago', p.id)] = f'{doc} · {p.metodo_pago.nombre}'
    for a in VGAbonoGasto.objects.filter(id__in=ids['abono_gasto']).select_related('gasto'):
        etiquetas[('abono_gasto', a.id)] = f'Gasto: {a.gasto.descripcion}'
    for a in VGAbonoCompra.objects.filter(id__in=ids['abono_compra']).select_related('compra'):
        etiquetas[('abono_compra', a.id)] = f'Compra: {a.compra.proveedor_nombre}'
    for g in VGGasto.objects.filter(id__in=ids['gasto']):
        etiquetas[('gasto', g.id)] = f'Gasto: {g.descripcion}'
    for t in VGTransferenciaCuenta.objects.filter(id__in=ids['transferencia']):
        etiquetas[('transferencia', t.id)] = f'Transferencia entre cuentas: {t.concepto}'
    for i in VGIngresoExtra.objects.filter(id__in=ids['ingreso_extra']):
        etiquetas[('ingreso_extra', i.id)] = f'{i.get_tipo_display()}: {i.descripcion}'
    return etiquetas


def _serializar_vinculo(v, etiquetas):
    return {
        'id': v.id, 'estado': v.estado, 'origen_tipo': v.origen_tipo, 'origen_id': v.origen_id,
        'etiqueta': etiquetas.get((v.origen_tipo, v.origen_id), f'{v.get_origen_tipo_display()} #{v.origen_id}'),
        'monto_sistema': _money(v.monto_sistema), 'diferencia': _money(v.diferencia),
        'metodo': v.metodo, 'metodo_texto': v.get_metodo_display(), 'puntaje': v.puntaje, 'nota': v.nota,
    }


def _serializar_movimientos(movs):
    movs = list(movs)
    vinculos = list(
        VGConciliacionMovimiento.objects.filter(movimiento__in=movs).exclude(estado='rechazado')
    )
    etiquetas = _etiquetas_origenes(vinculos)
    por_mov = defaultdict(list)
    for v in vinculos:
        por_mov[v.movimiento_id].append(_serializar_vinculo(v, etiquetas))
    cerrados = set()
    if movs:
        fechas = [timezone.localtime(m.fecha).date() for m in movs]
        cerrados = set(
            VGCierreConciliacion.objects.filter(
                cuenta_bancaria__in={m.cuenta_bancaria for m in movs}, estado='vigente',
                fecha__range=(min(fechas), max(fechas)),
            ).values_list('cuenta_bancaria', 'fecha')
        )
    return [
        {
            'dia_cerrado': (m.cuenta_bancaria, timezone.localtime(m.fecha).date()) in cerrados,
            'id': m.id, 'fecha': timezone.localtime(m.fecha).isoformat(), 'referencia': m.referencia,
            'descripcion': m.descripcion, 'tipo': m.tipo, 'monto': _money(m.monto), 'saldo': _money(m.saldo),
            'observacion': m.observacion, 'clase': m.clase, 'clase_texto': m.get_clase_display(),
            'estado': m.estado, 'motivo_ignorado': m.motivo_ignorado, 'vinculos': por_mov.get(m.id, []),
        }
        for m in movs
    ]


def _serializar_resumen(resumen):
    return {
        'total': resumen['total'], 'creditos': _money(resumen['creditos']), 'debitos': _money(resumen['debitos']),
        'estados': {
            estado: {'cantidad': b['cantidad'], 'creditos': _money(b['creditos']), 'debitos': _money(b['debitos'])}
            for estado, b in resumen['estados'].items()
        },
    }


def _serializar_candidato(c, ev=None):
    data = {
        'tipo': c.tipo, 'id': c.id, 'fecha': c.fecha.isoformat(), 'monto': _money(c.monto),
        'referencia': c.extra.get('referencia_original', ''), 'etiqueta': c.etiqueta,
    }
    if ev is not None:
        data.update({'puntaje': ev.puntaje, 'diferencia': _money(ev.diferencia), 'dias': ev.dias, 'nota': ev.nota})
    return data


def _serializar_extracto(e):
    return {
        'id': e.id, 'cuenta': e.cuenta_bancaria, 'archivo': e.nombre_archivo,
        'desde': e.fecha_desde.isoformat() if e.fecha_desde else None,
        'hasta': e.fecha_hasta.isoformat() if e.fecha_hasta else None,
        'leidos': e.movimientos_leidos, 'nuevos': e.movimientos_nuevos, 'duplicados': e.duplicados_omitidos,
        'omitidos_dia_cerrado': e.omitidos_dia_cerrado,
        'saltos_saldo': e.saltos_saldo,
        'subido_por': (e.creado_por.get_full_name() or e.creado_por.username) if e.creado_por else '',
        'fecha': timezone.localtime(e.fecha_creacion).isoformat(),
    }


def _serializar_cierre(c):
    if c is None:
        return None
    return {
        'id': c.id, 'nota': c.nota, 'movimientos_total': c.movimientos_total, 'conciliados': c.conciliados,
        'ignorados': c.ignorados, 'creditos': _money(c.creditos), 'debitos': _money(c.debitos),
        'saldo_inicial_banco': _money(c.saldo_inicial_banco), 'saldo_final_banco': _money(c.saldo_final_banco),
        'saltos_saldo': c.saltos_saldo, 'registros_sin_banco': c.registros_sin_banco,
        'pos_banco': _money(c.pos_banco), 'pos_sistema': _money(c.pos_sistema),
        'cerrado_por': (c.creado_por.get_full_name() or c.creado_por.username) if c.creado_por else '',
        'fecha_cierre': timezone.localtime(c.fecha_creacion).isoformat(),
    }


def _serializar_dia(d):
    return {
        'fecha': d['fecha'].isoformat(), 'estado': d['estado'], 'total': d['total'], 'conciliados': d['conciliados'],
        'ignorados': d['ignorados'], 'por_revisar': d['por_revisar'], 'sin_coincidencia': d['sin_coincidencia'],
        'pendientes_pos': d['pendientes_pos'], 'pendientes_otros': d['pendientes_otros'], 'bloqueos': d['bloqueos'],
        'creditos': _money(d['creditos']), 'debitos': _money(d['debitos']),
        'saldo_inicial': _money(d['saldo_inicial']), 'saldo_final': _money(d['saldo_final']),
        'saltos_saldo': d['saltos_saldo'], 'registros_sin_banco': d['registros_sin_banco'],
        'pos_banco': _money(d['pos_banco']), 'pos_sistema': _money(d['pos_sistema']),
        'continuidad': d['continuidad'], 'reaperturas': d['reaperturas'], 'cierre': _serializar_cierre(d['cierre']),
    }


def _serializar_resumen_cierres(r):
    return {
        **{k: r[k] for k in ('dias', 'cerrados', 'pendientes', 'listos', 'sin_movimientos', 'discontinuidades', 'completo')},
        'creditos_cerrados': _money(r['creditos_cerrados']), 'debitos_cerrados': _money(r['debitos_cerrados']),
    }


def _aviso_dias_cerrados(cuenta, parseado):
    r = motor.movimientos_en_dias_cerrados(cuenta, parseado)
    return {'cantidad': r['cantidad'], 'dias': [d.isoformat() for d in r['dias']]}


# ---------------------------------------------------------------------------
# Vistas
# ---------------------------------------------------------------------------
@csrf_exempt
def conciliacion_cuentas_view(request):
    if request.method != 'GET':
        return _metodo_no_permitido()
    error = _sin_permiso(request)
    if error:
        return error
    return _auth_response({'ok': True, 'cuentas': motor.cuentas_disponibles()})


@csrf_exempt
def conciliacion_importar_view(request):
    """
    Sube el archivo del banco. action=preview solo lo lee y cuenta que traeria (no guarda nada);
    action=confirm lo guarda y corre el cruce para el rango de fechas del archivo. Los dos reciben
    el archivo (multipart) para que el servidor nunca dependa de filas que mande el navegador.
    """
    if request.method != 'POST':
        return _metodo_no_permitido()
    error = _sin_permiso(request)
    if error:
        return error

    accion = str(request.POST.get('action', 'preview')).strip().lower()
    if accion not in ('preview', 'confirm'):
        return _auth_response({'ok': False, 'message': 'Accion invalida.'}, status=400)
    cuenta = _cuenta_valida(request.POST.get('cuenta'))
    if cuenta is None:
        return _auth_response({'ok': False, 'message': 'Elige la cuenta bancaria del archivo.'}, status=400)
    archivo = request.FILES.get('archivo')
    if archivo is None:
        return _auth_response({'ok': False, 'message': 'Adjunta el archivo de movimientos del banco (.xlsx o .csv).'}, status=400)
    if archivo.size > MAX_TAMANO_EXTRACTO_BYTES:
        return _auth_response({'ok': False, 'message': 'El archivo no debe superar los 5MB.'}, status=400)

    try:
        parseado = parsear_extracto(archivo.read(), archivo.name)
    except ExtractoInvalido as exc:
        return _auth_response({'ok': False, 'message': str(exc)}, status=400)
    if not parseado['movimientos']:
        return _auth_response({'ok': False, 'message': 'El archivo no tiene movimientos para importar.'}, status=400)

    movimientos = parseado['movimientos']
    existentes = set(
        VGMovimientoBancario.objects.filter(
            cuenta_bancaria=cuenta, huella__in=[m['huella'] for m in movimientos],
        ).values_list('huella', flat=True)
    )
    fechas = [m['fecha'].date() for m in movimientos]
    resumen = {
        'archivo': archivo.name, 'cuenta': cuenta,
        'leidos': len(movimientos), 'nuevos': len(movimientos) - len(existentes), 'ya_cargados': len(existentes),
        'repetidas_en_archivo': parseado['repetidas_en_archivo'],
        'desde': min(fechas).isoformat(), 'hasta': max(fechas).isoformat(),
        'creditos': _money(sum((m['monto'] for m in movimientos if m['tipo'] == 'credito'), Decimal('0'))),
        'debitos': _money(sum((m['monto'] for m in movimientos if m['tipo'] == 'debito'), Decimal('0'))),
        'saltos_saldo': parseado['saltos_saldo'],
        'hojas': parseado['hojas'], 'hojas_omitidas': parseado['hojas_omitidas'],
        'errores': parseado['errores'][:MAX_ERRORES_VISTA_PREVIA], 'total_errores': len(parseado['errores']),
        'por_clase': {
            clase: sum(1 for m in movimientos if m['clase'] == clase) for clase in {m['clase'] for m in movimientos}
        },
        # lineas NUEVAS de dias ya cerrados: no se importan (hay que reabrir el cierre de ese dia)
        'en_dias_cerrados': _aviso_dias_cerrados(cuenta, parseado),
    }
    if accion == 'preview':
        return _auth_response({'ok': True, 'resumen': resumen})

    extracto = motor.importar_extracto(cuenta, parseado, archivo.name, request.user)
    desde, hasta = extracto.fecha_desde, extracto.fecha_hasta
    resultado = motor.conciliar(cuenta, desde, hasta, request.user)
    return _auth_response({
        'ok': True, 'resumen': resumen, 'extracto': _serializar_extracto(extracto), 'resultado': resultado,
        'message': f'Se importaron {extracto.movimientos_nuevos} movimientos nuevos.'
        + (f' {extracto.omitidos_dia_cerrado} línea(s) de días cerrados no se importaron.' if extracto.omitidos_dia_cerrado else ''),
    }, status=201)


@csrf_exempt
def conciliacion_movimientos_view(request):
    """Los movimientos de una cuenta en un rango, con su estado y sus vinculos, mas los resumenes."""
    if request.method != 'GET':
        return _metodo_no_permitido()
    error = _sin_permiso(request)
    if error:
        return error
    cuenta = _cuenta_valida(request.GET.get('cuenta'))
    rango = _rango(request.GET)
    if cuenta is None or rango is None:
        return _auth_response({'ok': False, 'message': 'Indica la cuenta y un rango de fechas válido (hasta 12 meses).'}, status=400)
    desde, hasta = rango

    movs = VGMovimientoBancario.objects.filter(cuenta_bancaria=cuenta, fecha__date__gte=desde, fecha__date__lte=hasta)
    estados = [e for e in str(request.GET.get('estado', '')).split(',') if e]
    if estados:
        movs = movs.filter(estado__in=estados)
    if request.GET.get('tipo') in ('debito', 'credito'):
        movs = movs.filter(tipo=request.GET['tipo'])
    if request.GET.get('clase'):
        movs = movs.filter(clase=request.GET['clase'])
    q = str(request.GET.get('q', '')).strip()
    if q:
        movs = movs.filter(Q(descripcion__icontains=q) | Q(referencia__icontains=q) | Q(observacion__icontains=q))
    movs = movs.order_by('fecha', 'id')

    pos = [
        {'fecha': f['fecha'].isoformat(), 'banco': _money(f['banco']), 'sistema': _money(f['sistema']),
         'diferencia': _money(f['diferencia']), 'porcentaje': _money(f['porcentaje'])}
        for f in motor.resumen_pos(cuenta, desde, hasta)
    ]
    return _auth_response({
        'ok': True, 'cuenta': cuenta, 'desde': desde.isoformat(), 'hasta': hasta.isoformat(),
        'resumen': _serializar_resumen(motor.resumen_movimientos(cuenta, desde, hasta)),
        'pos': pos, 'movimientos': _serializar_movimientos(movs),
    })


@csrf_exempt
def conciliacion_extractos_view(request):
    if request.method != 'GET':
        return _metodo_no_permitido()
    error = _sin_permiso(request)
    if error:
        return error
    cuenta = _cuenta_valida(request.GET.get('cuenta'))
    if cuenta is None:
        return _auth_response({'ok': False, 'message': 'Elige la cuenta.'}, status=400)
    extractos = VGExtractoBancario.objects.filter(cuenta_bancaria=cuenta).select_related('creado_por')[:30]
    return _auth_response({'ok': True, 'extractos': [_serializar_extracto(e) for e in extractos]})


@csrf_exempt
def conciliacion_conciliar_view(request):
    """Vuelve a correr el cruce sobre lo que aun no esta resuelto en el rango."""
    if request.method != 'POST':
        return _metodo_no_permitido()
    error = _sin_permiso(request)
    if error:
        return error
    data = _leer_json(request)
    if data is None:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)
    cuenta, rango = _cuenta_valida(data.get('cuenta')), _rango(data)
    if cuenta is None or rango is None:
        return _auth_response({'ok': False, 'message': 'Indica la cuenta y un rango de fechas válido.'}, status=400)
    try:
        resultado = motor.conciliar(cuenta, rango[0], rango[1], request.user)
    except motor.CuentaNoSoportada as exc:
        return _auth_response({'ok': False, 'message': str(exc)}, status=400)
    return _auth_response({'ok': True, 'resultado': resultado})


@csrf_exempt
def conciliacion_confirmar_probables_view(request):
    if request.method != 'POST':
        return _metodo_no_permitido()
    error = _sin_permiso(request)
    if error:
        return error
    data = _leer_json(request)
    if data is None:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)
    cuenta, rango = _cuenta_valida(data.get('cuenta')), _rango(data)
    if cuenta is None or rango is None:
        return _auth_response({'ok': False, 'message': 'Indica la cuenta y un rango de fechas válido.'}, status=400)
    confirmados = motor.confirmar_probables(cuenta, rango[0], rango[1], request.user)
    return _auth_response({'ok': True, 'confirmados': confirmados})


@csrf_exempt
def conciliacion_movimiento_accion_view(request, movimiento_id):
    """accion: confirmar (vinculo_id) | rechazar (vinculo_id) | elegir (tipo, origen_id) | ignorar (motivo) | reabrir."""
    if request.method != 'POST':
        return _metodo_no_permitido()
    error = _sin_permiso(request)
    if error:
        return error
    data = _leer_json(request)
    if data is None:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)
    try:
        mov = VGMovimientoBancario.objects.get(pk=movimiento_id)
    except VGMovimientoBancario.DoesNotExist:
        return _auth_response({'ok': False, 'message': 'El movimiento no existe.'}, status=404)

    accion = str(data.get('accion', '')).strip().lower()
    try:
        if accion in ('confirmar', 'rechazar'):
            try:
                vinculo = mov.vinculos.get(pk=int(data.get('vinculo_id')))
            except (TypeError, ValueError, VGConciliacionMovimiento.DoesNotExist):
                return _auth_response({'ok': False, 'message': 'El vínculo no existe.'}, status=404)
            if accion == 'confirmar':
                motor.confirmar_vinculo(vinculo, request.user)
            else:
                motor.rechazar_vinculo(vinculo, request.user)
        elif accion == 'elegir':
            motor.vincular_manual(mov, str(data.get('tipo', '')), data.get('origen_id'), request.user)
        elif accion == 'ignorar':
            motor.ignorar_movimiento(mov, data.get('motivo'), request.user)
        elif accion == 'reabrir':
            motor.reabrir_movimiento(mov, request.user)
        else:
            return _auth_response({'ok': False, 'message': 'Accion invalida.'}, status=400)
    except motor.AccionInvalida as exc:
        return _auth_response({'ok': False, 'message': str(exc)}, status=400)
    except (TypeError, ValueError):
        return _auth_response({'ok': False, 'message': 'Datos invalidos.'}, status=400)

    mov.refresh_from_db()
    return _auth_response({'ok': True, 'movimiento': _serializar_movimientos([mov])[0]})


@csrf_exempt
def conciliacion_candidatos_view(request, movimiento_id):
    if request.method != 'GET':
        return _metodo_no_permitido()
    error = _sin_permiso(request)
    if error:
        return error
    try:
        mov = VGMovimientoBancario.objects.get(pk=movimiento_id)
    except VGMovimientoBancario.DoesNotExist:
        return _auth_response({'ok': False, 'message': 'El movimiento no existe.'}, status=404)
    if mov.clase == 'comision':
        return _auth_response({'ok': True, 'candidatos': []})
    return _auth_response({
        'ok': True, 'candidatos': [_serializar_candidato(c, ev) for c, ev in motor.candidatos_para(mov)],
    })


@csrf_exempt
def conciliacion_reverso_view(request):
    """Lo registrado en el sistema para esa cuenta que no aparece en el banco."""
    if request.method != 'GET':
        return _metodo_no_permitido()
    error = _sin_permiso(request)
    if error:
        return error
    cuenta, rango = _cuenta_valida(request.GET.get('cuenta')), _rango(request.GET)
    if cuenta is None or rango is None:
        return _auth_response({'ok': False, 'message': 'Indica la cuenta y un rango de fechas válido.'}, status=400)
    filas = motor.registros_sin_movimiento(cuenta, rango[0], rango[1])
    return _auth_response({
        'ok': True,
        'registros': [{'sentido': f['sentido'], **_serializar_candidato(f['candidato'])} for f in filas],
    })


@csrf_exempt
def conciliacion_cierres_view(request):
    """Estado de cada dia del rango (cerrado, pendiente, listo, sin movimientos) y el resumen del periodo."""
    if request.method != 'GET':
        return _metodo_no_permitido()
    error = _sin_permiso(request)
    if error:
        return error
    cuenta, rango = _cuenta_valida(request.GET.get('cuenta')), _rango(request.GET)
    if cuenta is None or rango is None:
        return _auth_response({'ok': False, 'message': 'Indica la cuenta y un rango de fechas válido.'}, status=400)
    dias, resumen = motor.listar_cierres(cuenta, rango[0], rango[1])
    return _auth_response({
        'ok': True, 'dias': [_serializar_dia(d) for d in dias], 'resumen': _serializar_resumen_cierres(resumen),
    })


@csrf_exempt
def conciliacion_cerrar_dia_view(request):
    """Confirma la conciliacion de un dia: guarda su foto y lo bloquea. Exige marcar que se reviso."""
    if request.method != 'POST':
        return _metodo_no_permitido()
    error = _sin_permiso(request)
    if error:
        return error
    data = _leer_json(request)
    if data is None:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)
    cuenta = _cuenta_valida(data.get('cuenta'))
    try:
        fecha = date.fromisoformat(str(data.get('fecha')))
    except (TypeError, ValueError):
        fecha = None
    if cuenta is None or fecha is None:
        return _auth_response({'ok': False, 'message': 'Indica la cuenta y la fecha del día a cerrar.'}, status=400)
    if data.get('confirmo') is not True:
        return _auth_response(
            {'ok': False, 'message': 'Debes confirmar que revisaste la conciliación de este día.'}, status=400,
        )
    try:
        motor.cerrar_dia(cuenta, fecha, data.get('nota'), request.user)
    except (motor.AccionInvalida, motor.CuentaNoSoportada) as exc:
        return _auth_response({'ok': False, 'message': str(exc)}, status=400)
    dias, resumen = motor.listar_cierres(cuenta, fecha, fecha)
    return _auth_response({'ok': True, 'dia': _serializar_dia(dias[0])}, status=201)


@csrf_exempt
def conciliacion_reabrir_cierre_view(request, cierre_id):
    if request.method != 'POST':
        return _metodo_no_permitido()
    error = _sin_permiso(request)
    if error:
        return error
    data = _leer_json(request)
    if data is None:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)
    try:
        cierre = VGCierreConciliacion.objects.get(pk=cierre_id)
    except VGCierreConciliacion.DoesNotExist:
        return _auth_response({'ok': False, 'message': 'El cierre no existe.'}, status=404)
    try:
        motor.reabrir_cierre(cierre, data.get('motivo'), request.user)
    except motor.AccionInvalida as exc:
        return _auth_response({'ok': False, 'message': str(exc)}, status=400)
    dias, resumen = motor.listar_cierres(cierre.cuenta_bancaria, cierre.fecha, cierre.fecha)
    return _auth_response({'ok': True, 'dia': _serializar_dia(dias[0])})

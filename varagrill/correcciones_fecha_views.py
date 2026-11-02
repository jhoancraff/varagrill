"""
Corregir la fecha de un abono (de gasto o de compra) o de una compra ya registrados.

Al registrar, quien carga elige la fecha real (ver fechas_registro.py); si se equivoco, esta seccion la
corrige. Cada correccion es un cambio con efecto en los reportes de caja, banco y conciliacion de los
dias involucrados, asi que tiene tres seguros:
  1. Motivo obligatorio (minimo MOTIVO_MINIMO caracteres), guardado en VGCorreccionFecha.
  2. Advertencias que hay que aceptar expresamente (`aceptadas` = codigos): dia con caja o conciliacion
     cerrada, cambio de mes, pago anterior al documento, movimiento ya conciliado con el banco. Sin eso la
     API responde 409 con `requiere_confirmacion` y no cambia nada.
  3. Auditoria permanente: quien, cuando, fecha anterior y nueva, motivo y lo que acepto.

  GET  ?tipo=abono_gasto|abono_compra|compra  &desde &hasta &q   lo que se puede corregir en ese rango
  GET  ?tipo=historial                                            las correcciones ya hechas
  POST {tipo, objeto_id, fecha_nueva, motivo, aceptadas}          corrige una fecha

El momento exacto del registro (fecha_pago / fecha_creacion) nunca se toca. La fecha del gasto en si se
corrige desde el reporte de gastos (VGCorreccionGasto).
"""
import json
from datetime import date

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from . import fechas_registro
from .auth_helpers import _auth_response, _is_admin_user
from .models import (
    VGAbonoCompra,
    VGAbonoGasto,
    VGCompra,
    VGConciliacionMovimiento,
    VGCorreccionFecha,
)

MOTIVO_MINIMO = 10
TIPOS = {'abono_gasto', 'abono_compra', 'compra'}
LIMITE_FILAS = 300


def _nombre_usuario(usuario):
    return (usuario.get_full_name() or usuario.username) if usuario else ''


def _serialize_correccion(correccion):
    return {
        'id': correccion.id,
        'tipo': correccion.tipo,
        'objeto_id': correccion.objeto_id,
        'descripcion': correccion.descripcion,
        'fecha_anterior': correccion.fecha_anterior.isoformat(),
        'fecha_nueva': correccion.fecha_nueva.isoformat(),
        'motivo': correccion.motivo,
        'advertencias_aceptadas': correccion.advertencias_aceptadas,
        'por': _nombre_usuario(correccion.creado_por),
        'fecha': correccion.fecha_creacion.isoformat(),
    }


def _fecha_compra(compra):
    return compra.fecha_factura or timezone.localtime(compra.fecha_creacion).date()


def _texto_abono_gasto(abono):
    gasto = abono.gasto
    return f'Abono de ${abono.monto:.2f} ({abono.metodo_pago.nombre}) — Gasto #{gasto.id}: {gasto.descripcion}'[:255]


def _texto_abono_compra(abono):
    compra = abono.compra
    return f'Abono de ${abono.monto:.2f} ({abono.metodo_pago.nombre}) — Compra #{compra.id}: {compra.proveedor_nombre}'[:255]


def _texto_compra(compra):
    factura = f' (factura {compra.numero_factura_proveedor})' if compra.numero_factura_proveedor else ''
    return f'Compra #{compra.id}: {compra.proveedor_nombre}{factura}'[:255]


def _serialize_item(tipo, objeto, correcciones):
    if tipo == 'abono_gasto':
        gasto = objeto.gasto
        bloqueo = 'El gasto está inhabilitado.' if gasto.inhabilitado else ''
        return {
            'tipo': tipo, 'id': objeto.id,
            'titulo': f'Gasto #{gasto.id} — {gasto.descripcion}',
            'detalle': ' · '.join(p for p in (gasto.proveedor_nombre, gasto.numero_comprobante, objeto.referencia and f'ref. {objeto.referencia}') if p),
            'monto': str(objeto.monto), 'metodo_pago': objeto.metodo_pago.nombre,
            'fecha': objeto.fecha_abono.isoformat(), 'fecha_registro': objeto.fecha_pago.isoformat(),
            'fecha_documento': gasto.fecha_gasto.isoformat(),
            'correcciones': correcciones, 'editable': not bloqueo, 'motivo_bloqueo': bloqueo,
        }
    if tipo == 'abono_compra':
        compra = objeto.compra
        bloqueo = 'La compra está anulada.' if compra.estado == 'cancelado' else ''
        return {
            'tipo': tipo, 'id': objeto.id,
            'titulo': f'Compra #{compra.id} — {compra.proveedor_nombre}',
            'detalle': ' · '.join(p for p in (compra.numero_factura_proveedor and f'factura {compra.numero_factura_proveedor}', objeto.referencia and f'ref. {objeto.referencia}') if p),
            'monto': str(objeto.monto), 'metodo_pago': objeto.metodo_pago.nombre,
            'fecha': objeto.fecha_abono.isoformat(), 'fecha_registro': objeto.fecha_pago.isoformat(),
            'fecha_documento': _fecha_compra(compra).isoformat(),
            'correcciones': correcciones, 'editable': not bloqueo, 'motivo_bloqueo': bloqueo,
        }
    bloqueo = 'La compra está anulada.' if objeto.estado == 'cancelado' else ''
    return {
        'tipo': tipo, 'id': objeto.id,
        'titulo': f'Compra #{objeto.id} — {objeto.proveedor_nombre}',
        'detalle': f'factura {objeto.numero_factura_proveedor}' if objeto.numero_factura_proveedor else '',
        'monto': str(objeto.total), 'metodo_pago': None,
        'fecha': _fecha_compra(objeto).isoformat(), 'fecha_registro': objeto.fecha_creacion.isoformat(),
        'fecha_documento': None,
        'correcciones': correcciones, 'editable': not bloqueo, 'motivo_bloqueo': bloqueo,
    }


def _rango(request):
    hoy = timezone.localdate()
    try:
        desde_raw = request.GET.get('desde')
        hasta_raw = request.GET.get('hasta')
        desde = date.fromisoformat(desde_raw) if desde_raw else hoy.replace(day=1)
        hasta = date.fromisoformat(hasta_raw) if hasta_raw else hoy
    except ValueError:
        return None
    if desde > hasta:
        return None
    return desde, hasta


def _consulta(tipo, desde, hasta, q):
    """(queryset, campo de fecha) de lo corregible de ese tipo en el rango."""
    if tipo == 'abono_gasto':
        consulta = VGAbonoGasto.objects.select_related('gasto', 'metodo_pago').filter(fecha_abono__range=(desde, hasta))
        if q:
            filtro = (
                Q(gasto__descripcion__icontains=q) | Q(gasto__proveedor_nombre__icontains=q)
                | Q(gasto__numero_comprobante__icontains=q) | Q(referencia__icontains=q)
                | Q(metodo_pago__nombre__icontains=q)
            )
            if q.isdigit():
                filtro |= Q(gasto_id=int(q))
            consulta = consulta.filter(filtro)
        return consulta.order_by('-fecha_abono', '-id')
    if tipo == 'abono_compra':
        consulta = VGAbonoCompra.objects.select_related('compra', 'metodo_pago').filter(fecha_abono__range=(desde, hasta))
        if q:
            filtro = (
                Q(compra__proveedor_nombre__icontains=q) | Q(compra__numero_factura_proveedor__icontains=q)
                | Q(referencia__icontains=q) | Q(metodo_pago__nombre__icontains=q)
            )
            if q.isdigit():
                filtro |= Q(compra_id=int(q))
            consulta = consulta.filter(filtro)
        return consulta.order_by('-fecha_abono', '-id')
    consulta = VGCompra.objects.filter(
        Q(fecha_factura__range=(desde, hasta))
        | Q(fecha_factura__isnull=True, fecha_creacion__date__range=(desde, hasta))
    )
    if q:
        filtro = Q(proveedor_nombre__icontains=q) | Q(numero_factura_proveedor__icontains=q)
        if q.isdigit():
            filtro |= Q(pk=int(q))
        consulta = consulta.filter(filtro)
    return consulta.order_by('-fecha_factura', '-id')


def _listar(request, tipo):
    rango = _rango(request)
    if rango is None:
        return _auth_response({'ok': False, 'message': 'Las fechas no son validas.'}, status=400)
    desde, hasta = rango
    q = str(request.GET.get('q', '') or '').strip().lstrip('#').strip()

    if tipo == 'historial':
        historial = VGCorreccionFecha.objects.select_related('creado_por').filter(
            fecha_creacion__date__range=(desde, hasta),
        )
        if q:
            filtro = Q(descripcion__icontains=q) | Q(motivo__icontains=q)
            if q.isdigit():
                filtro |= Q(objeto_id=int(q))
            historial = historial.filter(filtro)
        filas = list(historial[:LIMITE_FILAS + 1])
        return _auth_response({
            'ok': True, 'tipo': tipo, 'truncado': len(filas) > LIMITE_FILAS,
            'items': [_serialize_correccion(c) for c in filas[:LIMITE_FILAS]],
        })

    filas = list(_consulta(tipo, desde, hasta, q)[:LIMITE_FILAS + 1])
    truncado = len(filas) > LIMITE_FILAS
    filas = filas[:LIMITE_FILAS]
    corregidos = dict(
        VGCorreccionFecha.objects.filter(tipo=tipo, objeto_id__in=[f.id for f in filas])
        .values_list('objeto_id').annotate(total=Count('id'))
    )
    return _auth_response({
        'ok': True, 'tipo': tipo, 'truncado': truncado, 'motivo_minimo': MOTIVO_MINIMO,
        'items': [_serialize_item(tipo, fila, corregidos.get(fila.id, 0)) for fila in filas],
    })


def _hay_vinculo_banco(origen_tipo, origen_id):
    return VGConciliacionMovimiento.objects.filter(
        origen_tipo=origen_tipo, origen_id=origen_id, estado='confirmado',
    ).exists()


def _advertencias(tipo, objeto, anterior, nueva):
    """Todo lo que cambia (y hay que aceptar) al mover la fecha de `anterior` a `nueva`."""
    advertencias = []
    metodo = getattr(objeto, 'metodo_pago', None)
    advertencias += fechas_registro.advertencias_dias_cerrados([anterior, nueva], metodo)

    if (anterior.year, anterior.month) != (nueva.year, nueva.month):
        advertencias.append({
            'codigo': 'cambia_periodo',
            'mensaje': (
                f'La fecha pasa de {anterior.month:02d}/{anterior.year} a {nueva.month:02d}/{nueva.year}: '
                'cambian los totales de ambos meses.'
            ),
            'detalle': [],
        })

    if tipo == 'abono_gasto' and nueva < objeto.gasto.fecha_gasto:
        advertencias.append({
            'codigo': 'pago_antes_del_documento',
            'mensaje': f'El pago quedaría antes de la fecha del gasto ({fechas_registro.fecha_texto(objeto.gasto.fecha_gasto)}).',
            'detalle': [],
        })
    if tipo == 'abono_compra' and nueva < _fecha_compra(objeto.compra):
        advertencias.append({
            'codigo': 'pago_antes_del_documento',
            'mensaje': f'El pago quedaría antes de la fecha de la compra ({fechas_registro.fecha_texto(_fecha_compra(objeto.compra))}).',
            'detalle': [],
        })
    if tipo == 'compra':
        primer_pago = objeto.abonos.order_by('fecha_abono').values_list('fecha_abono', flat=True).first()
        if primer_pago is not None and nueva > primer_pago:
            advertencias.append({
                'codigo': 'compra_despues_de_pagos',
                'mensaje': f'La compra quedaría después de su primer pago ({fechas_registro.fecha_texto(primer_pago)}).',
                'detalle': [],
            })

    if tipo in ('abono_gasto', 'abono_compra') and _hay_vinculo_banco(tipo, objeto.id):
        advertencias.append({
            'codigo': 'conciliado',
            'mensaje': (
                'Este pago ya está conciliado con un movimiento del banco: con la nueva fecha puede dejar de '
                'coincidir con él.'
            ),
            'detalle': [],
        })
    return advertencias


def _corregir(request):
    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    tipo = str(data.get('tipo', '') or '').strip()
    if tipo not in TIPOS:
        return _auth_response({'ok': False, 'message': 'Tipo invalido.'}, status=400)
    try:
        objeto_id = int(data.get('objeto_id'))
    except (TypeError, ValueError):
        return _auth_response({'ok': False, 'message': 'Indica que registro corregir.'}, status=400)

    motivo = str(data.get('motivo', '') or '').strip()
    if len(motivo) < MOTIVO_MINIMO:
        return _auth_response({
            'ok': False, 'message': f'Escribe el motivo para la auditoria (minimo {MOTIVO_MINIMO} caracteres).',
        }, status=400)
    if not str(data.get('fecha_nueva', '') or '').strip():
        return _auth_response({'ok': False, 'message': 'Elige la nueva fecha.'}, status=400)
    try:
        nueva = fechas_registro.parse_fecha_real(data.get('fecha_nueva'), 'nueva fecha')
    except fechas_registro.FechaInvalida as exc:
        return _auth_response({'ok': False, 'message': str(exc)}, status=400)

    try:
        with transaction.atomic():
            if tipo == 'abono_gasto':
                objeto = VGAbonoGasto.objects.select_for_update(of=('self',)).select_related('gasto', 'metodo_pago').get(pk=objeto_id)
                if objeto.gasto.inhabilitado:
                    return _auth_response({'ok': False, 'message': 'El gasto esta inhabilitado: rehabilitalo para corregir su pago.'}, status=409)
                anterior, campo, descripcion = objeto.fecha_abono, 'fecha_abono', _texto_abono_gasto(objeto)
                parientes = {'gasto': objeto.gasto}
            elif tipo == 'abono_compra':
                objeto = VGAbonoCompra.objects.select_for_update(of=('self',)).select_related('compra', 'metodo_pago').get(pk=objeto_id)
                if objeto.compra.estado == 'cancelado':
                    return _auth_response({'ok': False, 'message': 'La compra esta anulada: no se puede corregir su pago.'}, status=409)
                anterior, campo, descripcion = objeto.fecha_abono, 'fecha_abono', _texto_abono_compra(objeto)
                parientes = {'compra': objeto.compra}
            else:
                objeto = VGCompra.objects.select_for_update().get(pk=objeto_id)
                if objeto.estado == 'cancelado':
                    return _auth_response({'ok': False, 'message': 'La compra esta anulada: no se puede corregir su fecha.'}, status=409)
                anterior, campo, descripcion = _fecha_compra(objeto), 'fecha_factura', _texto_compra(objeto)
                parientes = {'compra': objeto}

            if nueva == anterior:
                return _auth_response({'ok': False, 'message': 'La nueva fecha es igual a la actual.'}, status=400)

            advertencias = _advertencias(tipo, objeto, anterior, nueva)
            fechas_registro.exigir_aceptadas(advertencias, data.get('aceptadas'))

            setattr(objeto, campo, nueva)
            if tipo == 'compra':
                objeto.actualizado_por = request.user
                objeto.save(update_fields=[campo, 'actualizado_por', 'fecha_actualizacion'])
            else:
                objeto.save(update_fields=[campo])
            correccion = VGCorreccionFecha.objects.create(
                tipo=tipo, objeto_id=objeto.id, descripcion=descripcion,
                fecha_anterior=anterior, fecha_nueva=nueva, motivo=motivo,
                advertencias_aceptadas=[a['codigo'] for a in advertencias],
                creado_por=request.user, actualizado_por=request.user, **parientes,
            )
    except (VGAbonoGasto.DoesNotExist, VGAbonoCompra.DoesNotExist, VGCompra.DoesNotExist):
        return _auth_response({'ok': False, 'message': 'Ese registro no existe.'}, status=404)
    except fechas_registro.RequiereConfirmacion as exc:
        return fechas_registro.respuesta_confirmacion(exc)

    return _auth_response({
        'ok': True,
        'message': f'Fecha corregida: {fechas_registro.fecha_texto(anterior)} → {fechas_registro.fecha_texto(nueva)}.',
        'correccion': _serialize_correccion(correccion),
    })


@csrf_exempt
def admin_correcciones_fecha_view(request):
    if request.method not in ('GET', 'POST'):
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    if request.method == 'POST':
        return _corregir(request)

    tipo = str(request.GET.get('tipo', '') or 'abono_gasto').strip()
    if tipo != 'historial' and tipo not in TIPOS:
        return _auth_response({'ok': False, 'message': 'Tipo invalido.'}, status=400)
    return _listar(request, tipo)

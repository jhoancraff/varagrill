"""
Vistas del modulo de Contabilidad: metodos de pago configurables y el
cuadre de caja diario (totales por metodo, consignaciones y cierre).
Separado de api_views.py (que cubre todo lo propio del restaurante:
menu, inventario, pedidos, cocina, checkout...) para que ninguno de los
dos archivos seguiera creciendo junto por cosas sin relacion.
"""
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .auth_helpers import _auth_response, _is_admin_user, _is_cajera_user
from .models import VGCierreCaja, VGConsignacionCaja, VGMetodoPago
from .reportes import (
    desglose_caja_por_moneda,
    efectivo_esperado_dia,
    tasa_para_fecha,
    total_consignado,
    totales_pagos_por_metodo,
)


def _serialize_metodo_pago(metodo):
    return {
        'id': metodo.id,
        'nombre': metodo.nombre,
        'moneda': metodo.moneda,
        'es_efectivo': metodo.es_efectivo,
        'activo': metodo.activo,
    }


def metodos_pago_activos_view(request):
    """Metodos de pago activos, para el selector de cobro. Cualquier usuario autenticado."""
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not request.user.is_authenticated:
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion.'}, status=401)

    metodos = VGMetodoPago.objects.filter(activo=True).order_by('nombre')
    return _auth_response({'ok': True, 'metodos_pago': [_serialize_metodo_pago(metodo) for metodo in metodos]})


@csrf_exempt
def admin_metodos_pago_view(request):
    """Gestion de los tipos de metodo de pago disponibles al cobrar. Solo administrador."""
    if request.method not in ['GET', 'POST']:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    if request.method == 'GET':
        metodos = VGMetodoPago.objects.order_by('nombre')
        return _auth_response({'ok': True, 'metodos_pago': [_serialize_metodo_pago(metodo) for metodo in metodos]})

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    action = str(data.get('action', '')).strip().lower()

    if action == 'create':
        nombre = str(data.get('nombre', '')).strip()
        if not nombre:
            return _auth_response({'ok': False, 'message': 'El nombre es obligatorio.'}, status=400)
        if VGMetodoPago.objects.filter(nombre__iexact=nombre).exists():
            return _auth_response({'ok': False, 'message': 'Ya existe un metodo de pago con ese nombre.'}, status=400)

        moneda = str(data.get('moneda', 'USD')).strip().upper()
        if moneda not in {clave for clave, _ in VGMetodoPago.MONEDAS}:
            return _auth_response({'ok': False, 'message': 'La moneda debe ser USD o VES.'}, status=400)

        metodo = VGMetodoPago.objects.create(
            nombre=nombre,
            moneda=moneda,
            es_efectivo=bool(data.get('es_efectivo')),
            creado_por=request.user,
        )
        return _auth_response({
            'ok': True,
            'message': 'Metodo de pago creado correctamente.',
            'metodo_pago': _serialize_metodo_pago(metodo),
        }, status=201)

    if action == 'toggle_activo':
        try:
            metodo = VGMetodoPago.objects.get(pk=int(data.get('id')))
        except (TypeError, ValueError, VGMetodoPago.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'El metodo de pago no existe.'}, status=400)

        metodo.activo = not metodo.activo
        metodo.actualizado_por = request.user
        metodo.save(update_fields=['activo', 'actualizado_por', 'fecha_actualizacion'])
        return _auth_response({
            'ok': True,
            'message': 'Metodo de pago actualizado correctamente.',
            'metodo_pago': _serialize_metodo_pago(metodo),
        })

    return _auth_response({'ok': False, 'message': 'Accion invalida.'}, status=400)


def _parse_fecha_reporte(raw_value):
    if not raw_value:
        return timezone.localdate()
    try:
        return date.fromisoformat(str(raw_value))
    except ValueError:
        return None


def _serialize_consignacion(consignacion):
    return {
        'id': consignacion.id,
        'monto': str(consignacion.monto),
        'notas': consignacion.notas,
        'creado_por': consignacion.creado_por.get_full_name() or consignacion.creado_por.username if consignacion.creado_por else '',
        'fecha_creacion': consignacion.fecha_creacion.isoformat(),
    }


def _serialize_desglose_caja(desglose):
    def _serialize_balde(balde):
        data = {'total_usd': str(balde['total_usd'])}
        if 'total_bs' in balde:
            data['total_bs'] = str(balde['total_bs']) if balde['total_bs'] is not None else None
        return data

    return {clave: _serialize_balde(balde) for clave, balde in desglose.items()}


def _serialize_cierre_caja(cierre):
    if cierre is None:
        return None
    return {
        'efectivo_esperado': str(cierre.efectivo_esperado),
        'total_consignado': str(cierre.total_consignado),
        'efectivo_contado_final': str(cierre.efectivo_contado_final),
        'diferencia': str(cierre.diferencia),
        'notas': cierre.notas,
        'cerrado_por': cierre.creado_por.get_full_name() or cierre.creado_por.username if cierre.creado_por else '',
        'fecha_creacion': cierre.fecha_creacion.isoformat(),
    }


@csrf_exempt
def reporte_cuadre_caja_view(request):
    """
    Cuadre de caja diario: totales cobrados por metodo de pago (VGPago),
    consignaciones parciales del turno y el cierre final del dia (unico por
    fecha, lo hace la ultima persona del turno).
    """
    if request.method not in ['GET', 'POST']:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not (_is_admin_user(request.user) or _is_cajera_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para ver este reporte.'}, status=401)

    if request.method == 'GET':
        fecha = _parse_fecha_reporte(request.GET.get('fecha'))
        if fecha is None:
            return _auth_response({'ok': False, 'message': 'Fecha invalida.'}, status=400)

        totales = totales_pagos_por_metodo(fecha)
        consignaciones = VGConsignacionCaja.objects.filter(fecha=fecha).select_related('creado_por')
        cierre = VGCierreCaja.objects.filter(fecha=fecha).select_related('creado_por').first()
        tasa = tasa_para_fecha(fecha)

        return _auth_response({
            'ok': True,
            'fecha': fecha.isoformat(),
            'tasa_bcv': str(tasa) if tasa is not None else None,
            'totales_por_metodo': [
                {
                    **item,
                    'total': str(item['total']),
                    'total_bs': str(item['total_bs']) if item['total_bs'] is not None else None,
                }
                for item in totales
            ],
            'total_general': str(sum(item['total'] for item in totales)),
            'desglose_caja': _serialize_desglose_caja(desglose_caja_por_moneda(fecha)),
            'consignaciones': [_serialize_consignacion(item) for item in consignaciones],
            'total_consignado': str(total_consignado(fecha)),
            'cierre': _serialize_cierre_caja(cierre),
        })

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    action = str(data.get('action', '')).strip().lower()
    fecha = _parse_fecha_reporte(data.get('fecha'))
    if fecha is None:
        return _auth_response({'ok': False, 'message': 'Fecha invalida.'}, status=400)

    if action == 'agregar_consignacion':
        try:
            monto = Decimal(str(data.get('monto', '')))
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'El monto no es valido.'}, status=400)
        if monto <= 0:
            return _auth_response({'ok': False, 'message': 'El monto debe ser mayor a cero.'}, status=400)

        if VGCierreCaja.objects.filter(fecha=fecha).exists():
            return _auth_response({'ok': False, 'message': 'La caja de ese dia ya esta cerrada.'}, status=400)

        consignacion = VGConsignacionCaja.objects.create(
            fecha=fecha,
            monto=monto,
            notas=str(data.get('notas', '') or '').strip(),
            creado_por=request.user,
        )
        return _auth_response({
            'ok': True,
            'message': 'Consignacion registrada correctamente.',
            'consignacion': _serialize_consignacion(consignacion),
        }, status=201)

    if action == 'cerrar_caja':
        if VGCierreCaja.objects.filter(fecha=fecha).exists():
            return _auth_response({'ok': False, 'message': 'La caja de ese dia ya esta cerrada.'}, status=400)

        try:
            efectivo_contado_final = Decimal(str(data.get('efectivo_contado_final', '')))
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'El monto contado no es valido.'}, status=400)
        if efectivo_contado_final < 0:
            return _auth_response({'ok': False, 'message': 'El monto contado no puede ser negativo.'}, status=400)

        efectivo_esperado = efectivo_esperado_dia(fecha)
        consignado = total_consignado(fecha)
        diferencia = (consignado + efectivo_contado_final) - efectivo_esperado

        cierre = VGCierreCaja.objects.create(
            fecha=fecha,
            efectivo_esperado=efectivo_esperado,
            total_consignado=consignado,
            efectivo_contado_final=efectivo_contado_final,
            diferencia=diferencia,
            notas=str(data.get('notas', '') or '').strip(),
            creado_por=request.user,
        )
        return _auth_response({
            'ok': True,
            'message': 'Caja cerrada correctamente.',
            'cierre': _serialize_cierre_caja(cierre),
        }, status=201)

    return _auth_response({'ok': False, 'message': 'Accion invalida.'}, status=400)

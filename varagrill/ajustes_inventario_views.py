"""
Vistas del modulo de ajuste de inventario: un borrador (VGAjusteInventario) al que el
analista va agregando lineas indicando cuanto sumar o restar del stock_actual de un
ingrediente (VGDetalleAjusteInventario). Nada afecta el stock real hasta que se
presiona "Guardar" (ver admin_ajuste_inventario_guardar_view) — calcado del patron de
VGCompraBorrador/compras_views.py, pero con dos diferencias de negocio propias:

- El ajuste NO se cierra solo al guardar: sigue "abierto" para agregarle mas lineas
  despues (dentro del mismo mes), y cada guardado subsiguiente solo aplica las lineas
  nuevas o modificadas, sin retocar lo que ya se aplico (ver la comparacion
  cantidad != cantidad_aplicada en admin_ajuste_inventario_guardar_view).
- Existe un cierre mensual (VGCierreInventario) que congela el mes completo a solo
  lectura — ver _mes_cerrado.
"""
import json
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .auth_helpers import _auth_response, _is_admin_user
from .models import (
    VGAjusteInventario,
    VGCierreInventario,
    VGDetalleAjusteInventario,
    VGIngrediente,
    VGMovimientoInventario,
)

TIPOS_VALIDOS = dict(VGDetalleAjusteInventario.TIPOS)


def _mes_actual():
    ahora = timezone.localtime(timezone.now())
    return ahora.year, ahora.month


def _mes_cerrado(anio, mes):
    return VGCierreInventario.objects.filter(anio=anio, mes=mes).exists()


def _get_ajuste_abierto(anio, mes):
    # OJO: no se filtra por estado='abierto' — 'confirmado' solo indica que el
    # ajuste ya tiene alguna linea aplicada al stock (ver VGAjusteInventario),
    # no que este cerrado a mas ediciones. El ajuste del mes sigue siendo EL
    # MISMO (mismo ID de nota) para agregarle/editarle/quitarle lineas hasta
    # que se cierre el mes completo (ver VGCierreInventario) — filtrar por
    # 'abierto' aca hacia que cada guardado disparara sin querer un ajuste
    # nuevo en vez de reusar el existente.
    return (
        VGAjusteInventario.objects.filter(anio=anio, mes=mes)
        .order_by('-fecha_creacion')
        .first()
    )


def _signo(tipo):
    return Decimal('1') if tipo == 'suma' else Decimal('-1')


def _serialize_detalle_ajuste(detalle):
    return {
        'id': detalle.id,
        'ingrediente_id': detalle.ingrediente_id,
        'ingrediente_nombre': detalle.ingrediente.nombre,
        'unidad_medida': detalle.ingrediente.unidad_medida,
        'tipo': detalle.tipo,
        'cantidad': str(detalle.cantidad),
        'cantidad_aplicada': str(detalle.cantidad_aplicada),
        'motivo': detalle.motivo,
        'aplicado': detalle.aplicado,
    }


def _serialize_ajuste(ajuste, incluir_detalles=True):
    data = {
        'id': ajuste.id,
        'estado': ajuste.estado,
        'anio': ajuste.anio,
        'mes': ajuste.mes,
        'notas': ajuste.notas,
        'fecha_creacion': ajuste.fecha_creacion.isoformat(),
    }
    if incluir_detalles:
        detalles = list(ajuste.detalles.select_related('ingrediente').order_by('fecha_creacion'))
        data['detalles'] = [_serialize_detalle_ajuste(detalle) for detalle in detalles]
    else:
        data['total_lineas'] = ajuste.detalles.count()
    return data


@csrf_exempt
def admin_ajuste_inventario_view(request):
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    anio, mes = _mes_actual()
    ajuste_abierto = _get_ajuste_abierto(anio, mes)

    historico_qs = VGAjusteInventario.objects.filter(anio=anio, mes=mes)
    if ajuste_abierto is not None:
        historico_qs = historico_qs.exclude(pk=ajuste_abierto.pk)
    historico = historico_qs.order_by('-fecha_creacion')

    return _auth_response({
        'ok': True,
        'anio': anio,
        'mes': mes,
        'mes_cerrado': _mes_cerrado(anio, mes),
        'ajuste': _serialize_ajuste(ajuste_abierto) if ajuste_abierto is not None else None,
        'historico': [_serialize_ajuste(ajuste, incluir_detalles=False) for ajuste in historico],
    })


@csrf_exempt
def admin_ajuste_inventario_agregar_view(request):
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    anio, mes = _mes_actual()
    if _mes_cerrado(anio, mes):
        return _auth_response({
            'ok': False,
            'message': f'El mes {mes:02d}/{anio} ya fue cerrado, no se pueden hacer mas ajustes.',
        }, status=400)

    tipo = str(data.get('tipo', '') or '').strip()
    if tipo not in TIPOS_VALIDOS:
        return _auth_response({'ok': False, 'message': 'El tipo debe ser "suma" o "resta".'}, status=400)

    try:
        cantidad = Decimal(str(data.get('cantidad', '')))
    except InvalidOperation:
        return _auth_response({'ok': False, 'message': 'La cantidad debe ser numerica.'}, status=400)
    if cantidad <= 0:
        return _auth_response({'ok': False, 'message': 'La cantidad debe ser mayor a cero.'}, status=400)

    try:
        ingrediente = VGIngrediente.objects.get(pk=int(data.get('ingrediente_id')))
    except (TypeError, ValueError, VGIngrediente.DoesNotExist):
        return _auth_response({'ok': False, 'message': 'El ingrediente seleccionado no existe.'}, status=400)

    motivo = str(data.get('motivo', '') or '').strip()

    with transaction.atomic():
        ajuste = _get_ajuste_abierto(anio, mes)
        if ajuste is None:
            ajuste = VGAjusteInventario.objects.create(
                anio=anio, mes=mes, creado_por=request.user, actualizado_por=request.user,
            )
        VGDetalleAjusteInventario.objects.create(
            ajuste=ajuste, ingrediente=ingrediente, tipo=tipo, cantidad=cantidad, motivo=motivo,
            creado_por=request.user,
        )

    return _auth_response({'ok': True, 'ajuste': _serialize_ajuste(ajuste)}, status=201)


@csrf_exempt
def admin_ajuste_inventario_editar_view(request):
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    anio, mes = _mes_actual()
    if _mes_cerrado(anio, mes):
        return _auth_response({
            'ok': False,
            'message': f'El mes {mes:02d}/{anio} ya fue cerrado, no se pueden editar ajustes.',
        }, status=400)

    try:
        detalle = VGDetalleAjusteInventario.objects.select_related('ajuste', 'ingrediente').get(
            pk=int(data.get('detalle_id')), ajuste__anio=anio, ajuste__mes=mes,
        )
    except (TypeError, ValueError, VGDetalleAjusteInventario.DoesNotExist):
        return _auth_response({'ok': False, 'message': 'Esa linea del ajuste no existe.'}, status=400)

    try:
        nueva_cantidad = Decimal(str(data.get('cantidad', '')))
    except InvalidOperation:
        return _auth_response({'ok': False, 'message': 'La cantidad debe ser numerica.'}, status=400)
    if nueva_cantidad <= 0:
        return _auth_response({'ok': False, 'message': 'La cantidad debe ser mayor a cero.'}, status=400)

    motivo_raw = data.get('motivo')
    ajuste = detalle.ajuste

    with transaction.atomic():
        if not detalle.aplicado:
            # Todavia no se guardo al stock real: es una simple edicion del
            # borrador, sin generar ningun movimiento.
            detalle.cantidad = nueva_cantidad
            if motivo_raw is not None:
                detalle.motivo = str(motivo_raw).strip()
            detalle.save(update_fields=['cantidad', 'motivo'])
        else:
            # Ya se habia aplicado al stock: solo se mueve la DIFERENCIA contra
            # lo que ya se aplico (nunca se revierte todo para re-crear desde
            # cero), para no perder la trazabilidad de lo que ya paso.
            delta_cantidad = nueva_cantidad - detalle.cantidad_aplicada
            if delta_cantidad != 0:
                ingrediente = detalle.ingrediente
                delta_stock = delta_cantidad * _signo(detalle.tipo)
                ingrediente.stock_actual = Decimal(str(ingrediente.stock_actual)) + delta_stock
                ingrediente.actualizado_por = request.user
                ingrediente.save(update_fields=['stock_actual', 'actualizado_por', 'fecha_actualizacion'])
                VGMovimientoInventario.objects.create(
                    ingrediente=ingrediente,
                    tipo_movimiento='ajuste',
                    cantidad=delta_stock,
                    motivo=f'Correccion de ajuste #{ajuste.id} (linea #{detalle.id})',
                    id_referencia=ajuste.id,
                    creado_por=request.user,
                )
            detalle.cantidad = nueva_cantidad
            detalle.cantidad_aplicada = nueva_cantidad
            if motivo_raw is not None:
                detalle.motivo = str(motivo_raw).strip()
            detalle.save(update_fields=['cantidad', 'cantidad_aplicada', 'motivo'])

    return _auth_response({'ok': True, 'ajuste': _serialize_ajuste(ajuste)})


@csrf_exempt
def admin_ajuste_inventario_quitar_view(request):
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    anio, mes = _mes_actual()
    if _mes_cerrado(anio, mes):
        return _auth_response({
            'ok': False,
            'message': f'El mes {mes:02d}/{anio} ya fue cerrado, no se pueden quitar lineas.',
        }, status=400)

    try:
        detalle = VGDetalleAjusteInventario.objects.select_related('ajuste', 'ingrediente').get(
            pk=int(data.get('detalle_id')), ajuste__anio=anio, ajuste__mes=mes,
        )
    except (TypeError, ValueError, VGDetalleAjusteInventario.DoesNotExist):
        return _auth_response({'ok': False, 'message': 'Esa linea del ajuste no existe.'}, status=400)

    ajuste = detalle.ajuste

    with transaction.atomic():
        if detalle.aplicado:
            # Ya se habia aplicado al stock: se revierte EXACTAMENTE lo que se
            # habia aplicado (signo contrario) y queda registrado como un
            # movimiento aparte, nunca se borra el rastro de lo que ya paso.
            ingrediente = detalle.ingrediente
            delta_stock = -(detalle.cantidad_aplicada * _signo(detalle.tipo))
            ingrediente.stock_actual = Decimal(str(ingrediente.stock_actual)) + delta_stock
            ingrediente.actualizado_por = request.user
            ingrediente.save(update_fields=['stock_actual', 'actualizado_por', 'fecha_actualizacion'])
            VGMovimientoInventario.objects.create(
                ingrediente=ingrediente,
                tipo_movimiento='ajuste',
                cantidad=delta_stock,
                motivo=f'Reverso de ajuste #{ajuste.id} (linea #{detalle.id} eliminada)',
                id_referencia=ajuste.id,
                creado_por=request.user,
            )
        # Si nunca se habia aplicado (se agrego al borrador pero nunca se
        # guardo), simplemente se borra sin generar ningun movimiento.
        detalle.delete()

    return _auth_response({'ok': True, 'ajuste': _serialize_ajuste(ajuste)})


@csrf_exempt
def admin_ajuste_inventario_guardar_view(request):
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    anio, mes = _mes_actual()
    if _mes_cerrado(anio, mes):
        return _auth_response({
            'ok': False,
            'message': f'El mes {mes:02d}/{anio} ya fue cerrado, no se pueden guardar ajustes.',
        }, status=400)

    ajuste = _get_ajuste_abierto(anio, mes)
    if ajuste is None:
        return _auth_response({'ok': False, 'message': 'No hay ningun ajuste abierto para guardar.'}, status=400)

    with transaction.atomic():
        detalles = list(ajuste.detalles.select_related('ingrediente'))
        # Solo se procesan las lineas nuevas (aplicado=False) o las que el
        # analista modifico despues de aplicadas (cantidad != cantidad_aplicada)
        # — las demas quedan "congeladas", tal como ya se aplicaron antes.
        pendientes = [d for d in detalles if not d.aplicado or d.cantidad != d.cantidad_aplicada]
        if not pendientes:
            return _auth_response({
                'ok': False,
                'message': 'No hay lineas pendientes por guardar en este ajuste.',
            }, status=400)

        for detalle in pendientes:
            delta_cantidad = detalle.cantidad - detalle.cantidad_aplicada
            if delta_cantidad == 0:
                continue
            ingrediente = detalle.ingrediente
            delta_stock = delta_cantidad * _signo(detalle.tipo)
            ingrediente.stock_actual = Decimal(str(ingrediente.stock_actual)) + delta_stock
            ingrediente.actualizado_por = request.user
            ingrediente.save(update_fields=['stock_actual', 'actualizado_por', 'fecha_actualizacion'])
            VGMovimientoInventario.objects.create(
                ingrediente=ingrediente,
                tipo_movimiento='ajuste',
                cantidad=delta_stock,
                motivo=detalle.motivo or f'Ajuste de inventario #{ajuste.id}',
                id_referencia=ajuste.id,
                creado_por=request.user,
            )
            detalle.cantidad_aplicada = detalle.cantidad
            detalle.aplicado = True
            detalle.save(update_fields=['cantidad_aplicada', 'aplicado'])

        # El ajuste sigue existiendo y disponible para agregarle mas lineas
        # despues — 'confirmado' solo indica que ya tiene lineas aplicadas,
        # el cierre mensual (no este guardado) es lo unico que lo bloquea.
        ajuste.estado = 'confirmado'
        ajuste.actualizado_por = request.user
        ajuste.save(update_fields=['estado', 'actualizado_por', 'fecha_actualizacion'])

    return _auth_response({
        'ok': True,
        'message': f'Ajuste #{ajuste.id} guardado.',
        'ajuste': _serialize_ajuste(ajuste),
    })


@csrf_exempt
def admin_ajuste_inventario_descartar_view(request):
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    anio, mes = _mes_actual()
    ajuste = _get_ajuste_abierto(anio, mes)
    if ajuste is None:
        return _auth_response({'ok': True, 'ajuste': None})

    if _mes_cerrado(anio, mes):
        return _auth_response({
            'ok': False,
            'message': f'El mes {mes:02d}/{anio} ya fue cerrado, no se puede descartar el ajuste.',
        }, status=400)

    if ajuste.detalles.filter(aplicado=True).exists():
        return _auth_response({
            'ok': False,
            'message': 'Este ajuste ya tiene lineas aplicadas al stock — quita cada linea individualmente en vez de descartar todo.',
        }, status=400)

    ajuste.delete()
    return _auth_response({'ok': True, 'ajuste': None})


@csrf_exempt
def admin_cierre_inventario_view(request):
    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    if request.method == 'GET':
        anio, mes = _mes_actual()
        recientes = VGCierreInventario.objects.order_by('-anio', '-mes')[:12]
        return _auth_response({
            'ok': True,
            'anio': anio,
            'mes': mes,
            'mes_cerrado': _mes_cerrado(anio, mes),
            'cierres_recientes': [
                {'anio': cierre.anio, 'mes': cierre.mes, 'fecha_cierre': cierre.fecha_cierre.isoformat(), 'notas': cierre.notas}
                for cierre in recientes
            ],
        })

    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    anio, mes = _mes_actual()
    if _mes_cerrado(anio, mes):
        return _auth_response({'ok': False, 'message': f'El mes {mes:02d}/{anio} ya estaba cerrado.'}, status=400)

    ajuste = _get_ajuste_abierto(anio, mes)
    if ajuste is not None and ajuste.detalles.filter(aplicado=False).exists():
        return _auth_response({
            'ok': False,
            'message': 'Hay lineas del ajuste sin guardar en este mes — guardalas o quitalas antes de cerrar el mes.',
        }, status=400)

    notas = str(data.get('notas', '') or '').strip()
    with transaction.atomic():
        cierre = VGCierreInventario.objects.create(
            anio=anio, mes=mes, notas=notas, creado_por=request.user, actualizado_por=request.user,
        )

    return _auth_response({
        'ok': True,
        'message': f'Mes {mes:02d}/{anio} cerrado correctamente.',
        'cierre': {'anio': cierre.anio, 'mes': cierre.mes, 'fecha_cierre': cierre.fecha_cierre.isoformat()},
    }, status=201)

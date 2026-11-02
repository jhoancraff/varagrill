"""
Vistas del modulo de ajuste de inventario. Cada "hoja" (VGAjusteInventario) es un borrador
al que el analista va agregando lineas indicando cuanto sumar o restar del stock_actual de
un ingrediente (VGDetalleAjusteInventario). Un mismo dia puede tener varias hojas, cada una
para una tarea distinta (ej. "Conteo cocina", "Merma pork belly"). Nada afecta el stock real
hasta que se presiona "Guardar" (ver admin_ajuste_inventario_guardar_view) — calcado del
patron de VGCompraBorrador/compras_views.py, pero con dos diferencias de negocio propias:

- La hoja NO se cierra sola al guardar: sigue "abierta" para agregarle mas lineas despues
  (mientras su mes no se cierre), y cada guardado subsiguiente solo aplica las lineas nuevas
  o modificadas, sin retocar lo que ya se aplico (ver la comparacion
  cantidad != cantidad_aplicada en admin_ajuste_inventario_guardar_view).
- Existe un cierre mensual (VGCierreInventario) que congela todas las hojas del mes a solo
  lectura — ver _mes_cerrado.
"""
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import F, Q
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
TITULO_MAX = VGAjusteInventario._meta.get_field('titulo').max_length


def _mes_actual():
    ahora = timezone.localtime(timezone.now())
    return ahora.year, ahora.month


def _mes_cerrado(anio, mes):
    return VGCierreInventario.objects.filter(anio=anio, mes=mes).exists()


def _signo(tipo):
    return Decimal('1') if tipo == 'suma' else Decimal('-1')


def _lineas_pendientes(detalles):
    # Pendiente = linea nueva (nunca aplicada) o ya aplicada pero editada despues.
    return [d for d in detalles if not d.aplicado or d.cantidad != d.cantidad_aplicada]


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


def _serialize_ajuste(ajuste, incluir_detalles=True, meses_cerrados=None):
    """
    `meses_cerrados`: conjunto de (anio, mes) ya calculado por quien serializa varias hojas
    a la vez (el listado), para no consultar el cierre una vez por hoja.
    """
    if incluir_detalles:
        detalles = list(ajuste.detalles.select_related('ingrediente').order_by('fecha_creacion'))
    else:
        # El listado trae las lineas con prefetch_related('detalles').
        detalles = list(ajuste.detalles.all())
    if meses_cerrados is None:
        mes_cerrado = _mes_cerrado(ajuste.anio, ajuste.mes)
    else:
        mes_cerrado = (ajuste.anio, ajuste.mes) in meses_cerrados
    data = {
        'id': ajuste.id,
        'estado': ajuste.estado,
        'anio': ajuste.anio,
        'mes': ajuste.mes,
        'titulo': ajuste.titulo,
        'notas': ajuste.notas,
        'fecha_creacion': ajuste.fecha_creacion.isoformat(),
        'total_lineas': len(detalles),
        'lineas_pendientes': len(_lineas_pendientes(detalles)),
        'mes_cerrado': mes_cerrado,
    }
    if incluir_detalles:
        data['detalles'] = [_serialize_detalle_ajuste(detalle) for detalle in detalles]
    return data


def _rechazo(request, metodo):
    """Respuesta de error si el metodo no corresponde o no es un administrador; si no, None."""
    if request.method != metodo:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)
    return None


def _leer_json(request):
    """(data, error_response)."""
    try:
        return (json.loads(request.body.decode('utf-8')) if request.body else {}), None
    except json.JSONDecodeError:
        return None, _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)


def _hoja_o_error(data):
    """(ajuste, error_response) a partir del `ajuste_id` del cuerpo."""
    try:
        return VGAjusteInventario.objects.get(pk=int(data.get('ajuste_id'))), None
    except (TypeError, ValueError, VGAjusteInventario.DoesNotExist):
        return None, _auth_response({'ok': False, 'message': 'Esa hoja de ajuste no existe.'}, status=400)


def _mes_cerrado_error(ajuste, accion):
    """Respuesta de error si el mes de la hoja ya fue cerrado; si no, None."""
    if _mes_cerrado(ajuste.anio, ajuste.mes):
        return _auth_response({
            'ok': False,
            'message': f'El mes {ajuste.mes:02d}/{ajuste.anio} ya fue cerrado, no se pueden {accion}.',
        }, status=400)
    return None


def _titulo_o_error(data):
    """(titulo, error_response)."""
    titulo = str(data.get('titulo', '') or '').strip()
    if len(titulo) > TITULO_MAX:
        return None, _auth_response({
            'ok': False, 'message': f'El titulo no puede pasar de {TITULO_MAX} caracteres.',
        }, status=400)
    return titulo, None


def _detalle_o_error(data):
    """(detalle, error_response) a partir del `detalle_id` del cuerpo."""
    try:
        detalle = VGDetalleAjusteInventario.objects.select_related('ajuste', 'ingrediente').get(
            pk=int(data.get('detalle_id')),
        )
        return detalle, None
    except (TypeError, ValueError, VGDetalleAjusteInventario.DoesNotExist):
        return None, _auth_response({'ok': False, 'message': 'Esa linea del ajuste no existe.'}, status=400)


@csrf_exempt
def admin_ajuste_inventario_view(request):
    """
    Listado de hojas. `desde`/`hasta` (fecha de creacion; por defecto del dia 1 del mes en curso a
    hoy) y `q` (numero, titulo, notas o nombre de un ingrediente de la hoja) para encontrar una.
    """
    error = _rechazo(request, 'GET')
    if error:
        return error

    anio, mes = _mes_actual()
    hoy = timezone.localdate()
    try:
        desde_raw = request.GET.get('desde')
        hasta_raw = request.GET.get('hasta')
        desde = date.fromisoformat(desde_raw) if desde_raw else hoy.replace(day=1)
        hasta = date.fromisoformat(hasta_raw) if hasta_raw else hoy
    except ValueError:
        return _auth_response({'ok': False, 'message': 'Las fechas no son validas.'}, status=400)
    if desde > hasta:
        return _auth_response({'ok': False, 'message': 'La fecha inicial no puede ser mayor a la final.'}, status=400)

    hojas = VGAjusteInventario.objects.filter(
        fecha_creacion__date__gte=desde, fecha_creacion__date__lte=hasta,
    )
    q = str(request.GET.get('q', '') or '').strip().lstrip('#').strip()
    if q:
        filtro = (
            Q(titulo__icontains=q)
            | Q(notas__icontains=q)
            | Q(pk__in=VGDetalleAjusteInventario.objects.filter(
                ingrediente__nombre__icontains=q,
            ).values('ajuste_id'))
        )
        if q.isdigit():
            filtro |= Q(pk=int(q))
        hojas = hojas.filter(filtro)
    hojas = hojas.prefetch_related('detalles').order_by('-fecha_creacion')

    meses_cerrados = set(VGCierreInventario.objects.values_list('anio', 'mes'))
    return _auth_response({
        'ok': True,
        'anio': anio,
        'mes': mes,
        'mes_cerrado': (anio, mes) in meses_cerrados,
        'hojas': [_serialize_ajuste(h, incluir_detalles=False, meses_cerrados=meses_cerrados) for h in hojas],
    })


@csrf_exempt
def admin_ajuste_inventario_detalle_view(request, ajuste_id):
    error = _rechazo(request, 'GET')
    if error:
        return error
    try:
        ajuste = VGAjusteInventario.objects.get(pk=ajuste_id)
    except VGAjusteInventario.DoesNotExist:
        return _auth_response({'ok': False, 'message': 'Esa hoja de ajuste no existe.'}, status=404)
    return _auth_response({'ok': True, 'ajuste': _serialize_ajuste(ajuste)})


@csrf_exempt
def admin_ajuste_inventario_crear_view(request):
    error = _rechazo(request, 'POST')
    if error:
        return error
    data, error = _leer_json(request)
    if error:
        return error

    anio, mes = _mes_actual()
    if _mes_cerrado(anio, mes):
        return _auth_response({
            'ok': False,
            'message': f'El mes {mes:02d}/{anio} ya fue cerrado, no se pueden crear mas hojas de ajuste.',
        }, status=400)

    titulo, error = _titulo_o_error(data)
    if error:
        return error

    ajuste = VGAjusteInventario.objects.create(
        anio=anio, mes=mes, titulo=titulo, notas=str(data.get('notas', '') or '').strip(),
        creado_por=request.user, actualizado_por=request.user,
    )
    return _auth_response({'ok': True, 'ajuste': _serialize_ajuste(ajuste)}, status=201)


@csrf_exempt
def admin_ajuste_inventario_actualizar_view(request):
    """Cambia el titulo y/o las notas de una hoja (no toca sus lineas ni el stock)."""
    error = _rechazo(request, 'POST')
    if error:
        return error
    data, error = _leer_json(request)
    if error:
        return error
    ajuste, error = _hoja_o_error(data)
    if error:
        return error
    error = _mes_cerrado_error(ajuste, 'editar hojas')
    if error:
        return error

    if 'titulo' in data:
        ajuste.titulo, error = _titulo_o_error(data)
        if error:
            return error
    if 'notas' in data:
        ajuste.notas = str(data.get('notas', '') or '').strip()
    ajuste.actualizado_por = request.user
    ajuste.save(update_fields=['titulo', 'notas', 'actualizado_por', 'fecha_actualizacion'])
    return _auth_response({'ok': True, 'ajuste': _serialize_ajuste(ajuste)})


@csrf_exempt
def admin_ajuste_inventario_agregar_view(request):
    error = _rechazo(request, 'POST')
    if error:
        return error
    data, error = _leer_json(request)
    if error:
        return error
    ajuste, error = _hoja_o_error(data)
    if error:
        return error
    error = _mes_cerrado_error(ajuste, 'hacer mas ajustes')
    if error:
        return error

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

    VGDetalleAjusteInventario.objects.create(
        ajuste=ajuste, ingrediente=ingrediente, tipo=tipo, cantidad=cantidad, motivo=motivo,
        creado_por=request.user,
    )

    return _auth_response({'ok': True, 'ajuste': _serialize_ajuste(ajuste)}, status=201)


@csrf_exempt
def admin_ajuste_inventario_editar_view(request):
    error = _rechazo(request, 'POST')
    if error:
        return error
    data, error = _leer_json(request)
    if error:
        return error
    detalle, error = _detalle_o_error(data)
    if error:
        return error
    ajuste = detalle.ajuste
    error = _mes_cerrado_error(ajuste, 'editar ajustes')
    if error:
        return error

    try:
        nueva_cantidad = Decimal(str(data.get('cantidad', '')))
    except InvalidOperation:
        return _auth_response({'ok': False, 'message': 'La cantidad debe ser numerica.'}, status=400)
    if nueva_cantidad <= 0:
        return _auth_response({'ok': False, 'message': 'La cantidad debe ser mayor a cero.'}, status=400)

    motivo_raw = data.get('motivo')

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
    error = _rechazo(request, 'POST')
    if error:
        return error
    data, error = _leer_json(request)
    if error:
        return error
    detalle, error = _detalle_o_error(data)
    if error:
        return error
    ajuste = detalle.ajuste
    error = _mes_cerrado_error(ajuste, 'quitar lineas')
    if error:
        return error

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
    error = _rechazo(request, 'POST')
    if error:
        return error
    data, error = _leer_json(request)
    if error:
        return error
    ajuste, error = _hoja_o_error(data)
    if error:
        return error
    error = _mes_cerrado_error(ajuste, 'guardar ajustes')
    if error:
        return error

    with transaction.atomic():
        # Se bloquea la hoja mientras se aplica para que un doble clic (o dos
        # pestanas) no aplique las mismas lineas dos veces al stock.
        ajuste = VGAjusteInventario.objects.select_for_update().get(pk=ajuste.pk)
        detalles = list(ajuste.detalles.select_related('ingrediente'))
        # Solo se procesan las lineas nuevas (aplicado=False) o las que el
        # analista modifico despues de aplicadas (cantidad != cantidad_aplicada)
        # — las demas quedan "congeladas", tal como ya se aplicaron antes.
        pendientes = _lineas_pendientes(detalles)
        if not pendientes:
            return _auth_response({
                'ok': False,
                'message': 'No hay lineas pendientes por guardar en esta hoja.',
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

        # La hoja sigue existiendo y disponible para agregarle mas lineas
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
    error = _rechazo(request, 'POST')
    if error:
        return error
    data, error = _leer_json(request)
    if error:
        return error
    ajuste, error = _hoja_o_error(data)
    if error:
        return error
    error = _mes_cerrado_error(ajuste, 'descartar hojas')
    if error:
        return error

    if ajuste.detalles.filter(aplicado=True).exists():
        return _auth_response({
            'ok': False,
            'message': 'Esta hoja ya tiene lineas aplicadas al stock — quita cada linea individualmente en vez de descartar todo.',
        }, status=400)

    ajuste.delete()
    return _auth_response({'ok': True})


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

    hay_pendientes = VGDetalleAjusteInventario.objects.filter(
        ajuste__anio=anio, ajuste__mes=mes,
    ).filter(Q(aplicado=False) | ~Q(cantidad=F('cantidad_aplicada'))).exists()
    if hay_pendientes:
        return _auth_response({
            'ok': False,
            'message': 'Hay lineas de ajuste sin guardar en este mes — guardalas o quitalas antes de cerrar el mes.',
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

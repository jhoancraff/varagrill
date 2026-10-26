"""
Vistas de los servicios adicionales (ver servicios_adicionales.py): el catálogo, que solo crean y editan el administrador o el
contador, y los servicios de un pedido, que puede agregar cualquier usuario con sesión mientras el pedido no esté pagado.
"""
import json
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import transaction
from django.views.decorators.csrf import csrf_exempt

from .auth_helpers import _auth_response, _is_admin_user
from .models import VGPedido, VGServicioAdicional
from .servicios_adicionales import (
    ServiciosInvalidos, aplicar_servicios, resolver_servicios, serializar_lineas, serializar_servicio,
)

PRECIO_MAXIMO = Decimal('99999.99')


def _leer_json(request):
    try:
        return json.loads(request.body.decode('utf-8')) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _precio(valor):
    try:
        precio = Decimal(str(valor).strip().replace(',', '.'))
    except (InvalidOperation, ValueError):
        return None
    if not precio.is_finite() or precio < 0 or precio > PRECIO_MAXIMO:
        return None
    return precio.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _campos_validos(data, servicio=None):
    """Valida lo que llegó al crear o editar. Devuelve (campos, error); al editar solo trae lo que se mandó."""
    campos = {}
    if servicio is None or 'nombre' in data:
        nombre = str(data.get('nombre', '') or '').strip()
        if not nombre:
            return None, 'El nombre del servicio es obligatorio.'
        if len(nombre) > 120:
            return None, 'El nombre del servicio es demasiado largo.'
        existe = VGServicioAdicional.objects.filter(nombre__iexact=nombre)
        if servicio is not None:
            existe = existe.exclude(pk=servicio.pk)
        if existe.exists():
            return None, 'Ya existe un servicio con ese nombre.'
        campos['nombre'] = nombre
    if servicio is None or 'precio' in data:
        precio = _precio(data.get('precio'))
        if precio is None:
            return None, 'El precio del servicio no es valido.'
        campos['precio'] = precio
    if 'descripcion' in data:
        campos['descripcion'] = str(data.get('descripcion', '') or '').strip()[:255]
    if 'activo' in data:
        campos['activo'] = bool(data.get('activo'))
    if 'orden' in data:
        try:
            campos['orden'] = max(0, min(int(data.get('orden')), 32000))
        except (TypeError, ValueError):
            return None, 'El orden no es valido.'
    return campos, None


@csrf_exempt
def servicios_adicionales_view(request):
    """
    GET: los servicios activos para ofrecerlos al armar un pedido (cualquier usuario con sesión). El administrador o el
    contador pueden pedir todos con ?todos=1 (para configurarlos).
    POST: crea un servicio (solo administrador o contador).
    """
    if request.method not in ('GET', 'POST'):
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not request.user.is_authenticated:
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion.'}, status=401)

    if request.method == 'GET':
        servicios = VGServicioAdicional.objects.all()
        if not (request.GET.get('todos') in ('1', 'true') and _is_admin_user(request.user)):
            servicios = servicios.filter(activo=True)
        return _auth_response({'ok': True, 'servicios': [serializar_servicio(s) for s in servicios]})

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Solo el administrador o el contador pueden crear servicios.'}, status=401)
    data = _leer_json(request)
    if data is None:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)
    campos, error = _campos_validos(data)
    if error:
        return _auth_response({'ok': False, 'message': error}, status=400)
    servicio = VGServicioAdicional.objects.create(creado_por=request.user, actualizado_por=request.user, **campos)
    return _auth_response({'ok': True, 'message': 'Servicio creado.', 'servicio': serializar_servicio(servicio)}, status=201)


@csrf_exempt
def servicio_adicional_detail_view(request, servicio_id):
    """POST: edita nombre, descripción, precio, orden o si está activo (solo administrador o contador). No se borra."""
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Solo el administrador o el contador pueden editar servicios.'}, status=401)
    data = _leer_json(request)
    if data is None:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)
    try:
        servicio = VGServicioAdicional.objects.get(pk=servicio_id)
    except VGServicioAdicional.DoesNotExist:
        return _auth_response({'ok': False, 'message': 'El servicio no existe.'}, status=404)
    campos, error = _campos_validos(data, servicio)
    if error:
        return _auth_response({'ok': False, 'message': error}, status=400)
    if not campos:
        return _auth_response({'ok': False, 'message': 'No hay nada que cambiar.'}, status=400)
    for nombre, valor in campos.items():
        setattr(servicio, nombre, valor)
    servicio.actualizado_por = request.user
    servicio.save()
    return _auth_response({'ok': True, 'message': 'Servicio actualizado.', 'servicio': serializar_servicio(servicio)})


@csrf_exempt
def pedido_servicios_view(request, pedido_id):
    """
    POST {servicios: [{servicio_id, cantidad}, ...]}: deja en el pedido exactamente esos servicios (lista vacía = quitarlos
    todos) mientras no esté pagado. Cualquier usuario con sesión puede hacerlo: es lo que usa caja al cobrar si el cliente
    pide un servicio de último momento.
    """
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not request.user.is_authenticated:
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion.'}, status=401)
    data = _leer_json(request)
    if data is None or 'servicios' not in data:
        return _auth_response({'ok': False, 'message': 'Indica los servicios del pedido.'}, status=400)

    from .api_views import _recalcular_totales_pedido  # evita el import circular al cargar los modulos

    with transaction.atomic():
        try:
            pedido = VGPedido.objects.select_for_update().get(pk=pedido_id)
        except VGPedido.DoesNotExist:
            return _auth_response({'ok': False, 'message': 'El pedido no existe.'}, status=404)
        if pedido.estado in ('pagado', 'cancelado'):
            return _auth_response({'ok': False, 'message': 'Este pedido ya no se puede modificar.'}, status=409)
        if pedido.facturas.exclude(estado='anulada').exists():
            return _auth_response({'ok': False, 'message': 'Este pedido ya tiene una factura emitida.'}, status=409)
        try:
            resueltos = resolver_servicios(data.get('servicios'), pedido_actual=pedido)
        except ServiciosInvalidos as error:
            return _auth_response({'ok': False, 'message': str(error)}, status=400)
        aplicar_servicios(pedido, resueltos)
        pedido.save(update_fields=['cargo_servicios'])
        _recalcular_totales_pedido(pedido, request.user)

    return _auth_response({
        'ok': True,
        'message': 'Servicios actualizados.',
        'pedido': {
            'id': pedido.id, 'cargo_servicios': str(pedido.cargo_servicios), 'subtotal': str(pedido.subtotal),
            'total': str(pedido.total), 'servicios': serializar_lineas(pedido),
        },
    })

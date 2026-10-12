"""
Vistas del delivery: las zonas con su tarifa (las configura el administrador) y el cambio del
cargo de un pedido ya registrado (lo hace caja o el administrador, p. ej. cuando el cliente
reclama que le cobraron mucho). La logica del cargo vive en delivery.py.
"""
import json
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import transaction
from django.views.decorators.csrf import csrf_exempt

from .auth_helpers import _auth_response, _is_admin_user, _is_cajera_user
from .delivery import (
    CargoDeliveryInvalido, aplicar_cargo, puede_cambiar_monto, resolver_cargo_delivery, serializar_zona,
)
from .models import VGPedido, VGZonaDelivery


def _leer_json(request):
    try:
        return json.loads(request.body.decode('utf-8')) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _tarifa(valor):
    try:
        tarifa = Decimal(str(valor).strip().replace(',', '.'))
    except (InvalidOperation, ValueError):
        return None
    if not tarifa.is_finite() or tarifa < 0 or tarifa > Decimal('99999.99'):
        return None
    return tarifa.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


@csrf_exempt
def zonas_delivery_view(request):
    """
    GET: las zonas activas para ofrecerlas al registrar un pedido (cualquier usuario con sesion).
    Un administrador puede pedir todas con ?todas=1 (para configurarlas).
    POST (solo administrador): action create | update | toggle.
    """
    if request.method not in ('GET', 'POST'):
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not request.user.is_authenticated:
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion.'}, status=401)

    if request.method == 'GET':
        zonas = VGZonaDelivery.objects.all()
        if not (_is_admin_user(request.user) and request.GET.get('todas')):
            zonas = zonas.filter(activo=True)
        return _auth_response({
            'ok': True,
            'zonas': [serializar_zona(zona) for zona in zonas],
            'puede_cambiar_monto': puede_cambiar_monto(request.user),
        })

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)
    data = _leer_json(request)
    if data is None:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    action = str(data.get('action', '')).strip().lower()

    if action in ('create', 'update'):
        nombre = str(data.get('nombre', '') or '').strip()
        if not nombre:
            return _auth_response({'ok': False, 'message': 'El nombre de la zona es obligatorio.'}, status=400)
        if len(nombre) > 80:
            return _auth_response({'ok': False, 'message': 'El nombre de la zona es demasiado largo.'}, status=400)
        tarifa = _tarifa(data.get('tarifa'))
        if tarifa is None:
            return _auth_response({'ok': False, 'message': 'La tarifa no es valida (debe ser 0 o mayor).'}, status=400)

        if action == 'create':
            if VGZonaDelivery.objects.filter(nombre__iexact=nombre).exists():
                return _auth_response({'ok': False, 'message': 'Ya existe una zona con ese nombre.'}, status=400)
            ultimo = VGZonaDelivery.objects.order_by('-orden').first()
            zona = VGZonaDelivery.objects.create(
                nombre=nombre, tarifa=tarifa, activo=True, orden=(ultimo.orden + 1) if ultimo else 1,
                creado_por=request.user, actualizado_por=request.user,
            )
            return _auth_response({'ok': True, 'message': 'Zona creada.', 'zona': serializar_zona(zona)}, status=201)

        try:
            zona = VGZonaDelivery.objects.get(pk=int(data.get('id')))
        except (TypeError, ValueError, VGZonaDelivery.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'La zona no existe.'}, status=404)
        if VGZonaDelivery.objects.filter(nombre__iexact=nombre).exclude(pk=zona.pk).exists():
            return _auth_response({'ok': False, 'message': 'Ya existe otra zona con ese nombre.'}, status=400)
        zona.nombre = nombre
        zona.tarifa = tarifa
        zona.actualizado_por = request.user
        zona.save(update_fields=['nombre', 'tarifa', 'actualizado_por', 'fecha_actualizacion'])
        return _auth_response({'ok': True, 'message': 'Zona actualizada.', 'zona': serializar_zona(zona)})

    if action == 'toggle':
        try:
            zona = VGZonaDelivery.objects.get(pk=int(data.get('id')))
        except (TypeError, ValueError, VGZonaDelivery.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'La zona no existe.'}, status=404)
        zona.activo = not zona.activo
        zona.actualizado_por = request.user
        zona.save(update_fields=['activo', 'actualizado_por', 'fecha_actualizacion'])
        return _auth_response({'ok': True, 'zona': serializar_zona(zona)})

    return _auth_response({'ok': False, 'message': 'Accion invalida.'}, status=400)


@csrf_exempt
def pedido_cargo_delivery_view(request, pedido_id):
    """
    Cambia el cargo de delivery de un pedido ya registrado (zona y/o monto) mientras no este
    pagado. Es lo que usa caja al cobrar cuando el cliente reclama el precio: no hace falta
    editar el pedido (que solo se puede mientras esta pendiente en cocina).
    """
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
    if not (_is_admin_user(request.user) or _is_cajera_user(request.user)):
        return _auth_response({'ok': False, 'message': 'Solo caja o administracion puede cambiar el delivery.'}, status=401)
    data = _leer_json(request)
    if data is None:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    from .api_views import _recalcular_totales_pedido  # evita el import circular al cargar los modulos

    with transaction.atomic():
        try:
            pedido = VGPedido.objects.select_for_update().get(pk=pedido_id)
        except VGPedido.DoesNotExist:
            return _auth_response({'ok': False, 'message': 'El pedido no existe.'}, status=404)
        if pedido.tipo_pedido != 'delivery':
            return _auth_response({'ok': False, 'message': 'Este pedido no es un delivery.'}, status=400)
        if pedido.estado in ('pagado', 'cancelado'):
            return _auth_response({'ok': False, 'message': 'Este pedido ya no se puede modificar.'}, status=409)
        if pedido.grupo_pedido_id is not None:
            return _auth_response({
                'ok': False, 'message': 'El delivery se cobra en el pedido original, no en las rondas que se le agregaron.',
            }, status=400)
        if data.get('zona_delivery_id') in (None, '') and data.get('cargo_delivery') in (None, ''):
            return _auth_response({'ok': False, 'message': 'Indica la zona o el monto del delivery.'}, status=400)
        try:
            cargo = resolver_cargo_delivery(data, 'delivery', request.user, pedido_actual=pedido)
        except CargoDeliveryInvalido as error:
            return _auth_response({'ok': False, 'message': str(error)}, status=400)

        aplicar_cargo(pedido, cargo)
        pedido.save(update_fields=['cargo_delivery', 'zona_delivery', 'zona_delivery_nombre', 'tarifa_delivery'])
        _recalcular_totales_pedido(pedido, request.user)

    return _auth_response({
        'ok': True,
        'message': 'Delivery actualizado.',
        'pedido': {
            'id': pedido.id,
            'cargo_delivery': str(pedido.cargo_delivery),
            'zona_delivery_id': pedido.zona_delivery_id,
            'zona_delivery_nombre': pedido.zona_delivery_nombre,
            'tarifa_delivery': str(pedido.tarifa_delivery) if pedido.tarifa_delivery is not None else None,
            'subtotal': str(pedido.subtotal),
            'total': str(pedido.total),
        },
    })

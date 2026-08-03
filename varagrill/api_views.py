import json
from decimal import Decimal, InvalidOperation

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework import generics

from .models import (
    VGCategoriaProducto,
    VGCliente,
    VGDetallePedido,
    VGIngrediente,
    VGMesa,
    VGPedido,
    VGPreparacion,
    VGProducto,
    VGRecetaPreparacion,
)
from .notifications import send_whatsapp_new_order_alert
from .serializers import MesaSerializer, ProductoSerializer


def _auth_response(payload, status=200):
    response = JsonResponse(payload, status=status)
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    response['Vary'] = 'Cookie'
    return response


def _get_role_name(user):
    return str(getattr(getattr(user, 'id_role', None), 'nombre_role', '') or '').strip()


def _is_mesero_user(user):
    return _get_role_name(user).lower() == 'mesero'


def _notify_cocina_event(event_name, pedido, actor_user):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    payload = {
        'event': event_name,
        'pedido_id': pedido.id,
        'mesa': pedido.mesa.numero if pedido.mesa else None,
        'estado': pedido.estado,
        'tipo_pedido': pedido.tipo_pedido,
        'total': str(pedido.total),
        'creado_en': pedido.fecha_creacion.isoformat(),
        'actor': actor_user.username,
        'actor_role': _get_role_name(actor_user),
    }

    async_to_sync(channel_layer.group_send)(
        'role_cocinero_notifications',
        {
            'type': 'cocina_order_notification',
            'payload': payload,
        },
    )

    # Alertas opcionales por WhatsApp para nuevos pedidos.
    if event_name == 'NUEVA_COMANDAS':
        try:
            send_whatsapp_new_order_alert(pedido, actor_user)
        except Exception:
            pass


class MesaListView(generics.ListAPIView):
    queryset = VGMesa.objects.all().order_by('numero')
    serializer_class = MesaSerializer


class ProductoListView(generics.ListAPIView):
    queryset = VGProducto.objects.filter(disponible=True).select_related('categoria').order_by('nombre')
    serializer_class = ProductoSerializer


@csrf_exempt
def pedido_create_view(request):
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not request.user.is_authenticated:
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion para registrar pedidos.'}, status=401)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    items = data.get('items', [])
    if not isinstance(items, list) or len(items) == 0:
        return _auth_response({'ok': False, 'message': 'Debes enviar al menos un item en el pedido.'}, status=400)

    tipo_pedido = str(data.get('tipo_pedido', 'local')).strip().lower()
    tipo_keys = {tipo for tipo, _ in VGPedido.TIPOS}
    if tipo_pedido not in tipo_keys:
        return _auth_response({'ok': False, 'message': 'Tipo de pedido invalido.'}, status=400)

    mesa = None
    mesa_id = data.get('mesa_id')
    if mesa_id not in [None, '']:
        try:
            mesa = VGMesa.objects.get(pk=int(mesa_id))
        except (ValueError, TypeError, VGMesa.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'La mesa seleccionada no existe.'}, status=400)

    try:
        impuesto = Decimal(str(data.get('impuesto', '0') or '0'))
        descuento = Decimal(str(data.get('descuento', '0') or '0'))
        propina = Decimal(str(data.get('propina', '0') or '0'))
    except InvalidOperation:
        return _auth_response({'ok': False, 'message': 'Hay montos invalidos en impuesto, descuento o propina.'}, status=400)

    parsed_lines = []
    product_ids = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            return _auth_response({'ok': False, 'message': f'El item #{index} tiene formato invalido.'}, status=400)

        raw_product_id = item.get('product_id')
        try:
            product_id = int(raw_product_id)
        except (TypeError, ValueError):
            return _auth_response({'ok': False, 'message': f'El item #{index} no tiene producto valido.'}, status=400)

        raw_quantity = item.get('cantidad', 1)
        try:
            quantity = int(raw_quantity)
        except (TypeError, ValueError):
            return _auth_response({'ok': False, 'message': f'La cantidad del item #{index} es invalida.'}, status=400)

        if quantity <= 0:
            return _auth_response({'ok': False, 'message': f'La cantidad del item #{index} debe ser mayor a cero.'}, status=400)

        notes = str(item.get('notas', '') or '').strip()
        parsed_lines.append({'product_id': product_id, 'cantidad': quantity, 'notas': notes})
        product_ids.append(product_id)

    products_map = {
        product.id: product
        for product in VGProducto.objects.filter(id__in=product_ids, disponible=True)
    }

    for index, line in enumerate(parsed_lines, start=1):
        if line['product_id'] not in products_map:
            return _auth_response(
                {'ok': False, 'message': f'El producto del item #{index} no existe o no esta disponible.'},
                status=400,
            )

    cliente = None
    cliente_nombre = str(data.get('cliente_nombre', '') or '').strip()
    if cliente_nombre:
        cliente, _ = VGCliente.objects.get_or_create(nombre=cliente_nombre)

    notas = str(data.get('notas', '') or '').strip()

    with transaction.atomic():
        pedido = VGPedido.objects.create(
            mesa=mesa,
            usuario=request.user,
            cliente=cliente,
            tipo_pedido=tipo_pedido,
            estado='pendiente',
            notas=notas,
            impuesto=impuesto,
            descuento=descuento,
            propina=propina,
            creado_por=request.user,
            actualizado_por=request.user,
        )

        subtotal = Decimal('0')
        for line in parsed_lines:
            product = products_map[line['product_id']]
            line_total = product.precio_venta * line['cantidad']
            subtotal += line_total
            VGDetallePedido.objects.create(
                pedido=pedido,
                producto=product,
                cantidad=line['cantidad'],
                precio_unitario=product.precio_venta,
                estado='pendiente',
                notas=line['notas'],
            )

        total = subtotal + impuesto + propina - descuento
        pedido.subtotal = subtotal
        pedido.total = total
        pedido.actualizado_por = request.user
        pedido.save(update_fields=['subtotal', 'total', 'actualizado_por'])

    if _is_mesero_user(request.user):
        _notify_cocina_event('NUEVA_COMANDAS', pedido, request.user)

    return _auth_response(
        {
            'ok': True,
            'message': 'Pedido registrado correctamente.',
            'pedido': {
                'id': pedido.id,
                'estado': pedido.estado,
                'tipo_pedido': pedido.tipo_pedido,
                'subtotal': str(pedido.subtotal),
                'total': str(pedido.total),
                'items': len(parsed_lines),
            },
        },
        status=201,
    )


@csrf_exempt
def admin_catalog_view(request):
    if request.method not in ['GET', 'POST']:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not request.user.is_authenticated or not request.user.is_staff:
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    if request.method == 'GET':
        inventory = list(
            VGIngrediente.objects.order_by('-fecha_creacion', 'nombre').values('id', 'nombre', 'stock_actual', 'unidad_medida', 'ultimo_proveedor', 'costo_unitario')
        )
        recipes = list(
            VGPreparacion.objects.order_by('-fecha_creacion', 'nombre').values('id', 'nombre', 'rendimiento_cantidad', 'rendimiento_unidad')
        )
        beverages = list(
            VGProducto.objects.filter(disponible=True).select_related('categoria').order_by('-fecha_creacion', 'nombre').values('id', 'nombre', 'precio_venta', 'categoria__nombre')
        )
        return _auth_response({
            'ok': True,
            'inventory': inventory,
            'recipes': recipes,
            'beverages': beverages,
        })

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    tipo = str(data.get('tipo', '')).strip().lower()

    if tipo == 'eliminar_inventario':
        ingredient_id = data.get('id')
        try:
            ingredient = VGIngrediente.objects.get(pk=int(ingredient_id))
        except (ValueError, TypeError, VGIngrediente.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'El insumo a eliminar no existe.'}, status=400)
        ingredient.delete()
        return _auth_response({'ok': True, 'message': 'Insumo eliminado correctamente.'})

    if tipo == 'eliminar_receta':
        preparation_id = data.get('id')
        try:
            preparation = VGPreparacion.objects.get(pk=int(preparation_id))
        except (ValueError, TypeError, VGPreparacion.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'La receta a eliminar no existe.'}, status=400)
        preparation.delete()
        return _auth_response({'ok': True, 'message': 'Receta eliminada correctamente.'})

    if tipo == 'eliminar_bebida':
        beverage_id = data.get('id')
        try:
            beverage = VGProducto.objects.get(pk=int(beverage_id))
        except (ValueError, TypeError, VGProducto.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'La bebida a eliminar no existe.'}, status=400)
        beverage.delete()
        return _auth_response({'ok': True, 'message': 'Bebida eliminada correctamente.'})

    if tipo == 'inventario':
        nombre = str(data.get('nombre', '')).strip()
        if not nombre:
            return _auth_response({'ok': False, 'message': 'El nombre del insumo es obligatorio.'}, status=400)

        categoria = str(data.get('categoria', '')).strip() or 'Otros'
        unidad = str(data.get('unidad', '')).strip() or 'unidad'
        proveedor = str(data.get('proveedor', '')).strip() or 'Sin proveedor'
        cantidad = data.get('cantidad', 0)
        try:
            cantidad_value = Decimal(str(cantidad))
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'La cantidad del insumo es inválida.'}, status=400)

        ingredient_id = data.get('id')
        ingredient = None
        if ingredient_id not in [None, '']:
            try:
                ingredient = VGIngrediente.objects.get(pk=int(ingredient_id))
            except (ValueError, TypeError, VGIngrediente.DoesNotExist):
                return _auth_response({'ok': False, 'message': 'El insumo a editar no existe.'}, status=400)

        if ingredient is None:
            ingredient, created = VGIngrediente.objects.get_or_create(
                nombre__iexact=nombre,
                defaults={
                    'nombre': nombre,
                    'unidad_medida': unidad,
                    'stock_actual': cantidad_value,
                    'stock_minimo': 0,
                    'costo_unitario': 0,
                    'ultimo_proveedor': proveedor,
                    'creado_por': request.user,
                    'actualizado_por': request.user,
                },
            )
            if not created:
                ingredient.unidad_medida = unidad
                ingredient.stock_actual = cantidad_value
                ingredient.ultimo_proveedor = proveedor
                ingredient.actualizado_por = request.user
                ingredient.save(update_fields=['unidad_medida', 'stock_actual', 'ultimo_proveedor', 'actualizado_por', 'fecha_actualizacion'])
        else:
            ingredient.nombre = nombre
            ingredient.unidad_medida = unidad
            ingredient.stock_actual = cantidad_value
            ingredient.ultimo_proveedor = proveedor
            ingredient.actualizado_por = request.user
            ingredient.save(update_fields=['nombre', 'unidad_medida', 'stock_actual', 'ultimo_proveedor', 'actualizado_por', 'fecha_actualizacion'])

        return _auth_response({'ok': True, 'message': 'Insumo guardado correctamente.', 'item': {'id': ingredient.id, 'nombre': ingredient.nombre}})

    if tipo == 'recetas':
        nombre = str(data.get('nombre', '')).strip()
        if not nombre:
            return _auth_response({'ok': False, 'message': 'El nombre de la receta es obligatorio.'}, status=400)

        rendimiento_cantidad = data.get('rendimiento_cantidad', '1')
        rendimiento_unidad = str(data.get('rendimiento_unidad', 'unidad')).strip() or 'unidad'
        try:
            rendimiento = Decimal(str(rendimiento_cantidad))
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'El rendimiento de la receta es inválido.'}, status=400)

        preparation_id = data.get('id')
        preparation = None
        if preparation_id not in [None, '']:
            try:
                preparation = VGPreparacion.objects.get(pk=int(preparation_id))
            except (ValueError, TypeError, VGPreparacion.DoesNotExist):
                return _auth_response({'ok': False, 'message': 'La receta a editar no existe.'}, status=400)

        if preparation is None:
            preparation, created = VGPreparacion.objects.get_or_create(
                nombre__iexact=nombre,
                defaults={
                    'nombre': nombre,
                    'rendimiento_cantidad': rendimiento,
                    'rendimiento_unidad': rendimiento_unidad,
                    'creado_por': request.user,
                    'actualizado_por': request.user,
                },
            )
            if not created:
                preparation.rendimiento_cantidad = rendimiento
                preparation.rendimiento_unidad = rendimiento_unidad
                preparation.actualizado_por = request.user
                preparation.save(update_fields=['rendimiento_cantidad', 'rendimiento_unidad', 'actualizado_por', 'fecha_actualizacion'])
        else:
            preparation.nombre = nombre
            preparation.rendimiento_cantidad = rendimiento
            preparation.rendimiento_unidad = rendimiento_unidad
            preparation.actualizado_por = request.user
            preparation.save(update_fields=['nombre', 'rendimiento_cantidad', 'rendimiento_unidad', 'actualizado_por', 'fecha_actualizacion'])

        preparation.componentes.all().delete()
        for component in data.get('componentes', []) or []:
            if not isinstance(component, dict):
                continue
            component_type = str(component.get('tipo', '')).strip().lower()
            component_name = str(component.get('nombre', '')).strip()
            if not component_name:
                continue
            try:
                component_amount = Decimal(str(component.get('cantidad', '0')))
            except InvalidOperation:
                continue

            if component_type == 'ingrediente':
                ingredient = VGIngrediente.objects.filter(nombre__iexact=component_name).first()
                if ingredient is None:
                    ingredient = VGIngrediente.objects.create(
                        nombre=component_name,
                        unidad_medida='unidad',
                        stock_actual=0,
                        stock_minimo=0,
                        costo_unitario=0,
                        creado_por=request.user,
                        actualizado_por=request.user,
                    )
                VGRecetaPreparacion.objects.create(
                    preparacion=preparation,
                    ingrediente=ingredient,
                    cantidad_requerida=component_amount,
                )
            elif component_type == 'sub_preparacion':
                sub_preparation, _ = VGPreparacion.objects.get_or_create(
                    nombre__iexact=component_name,
                    defaults={
                        'nombre': component_name,
                        'rendimiento_cantidad': 1,
                        'rendimiento_unidad': 'unidad',
                        'creado_por': request.user,
                        'actualizado_por': request.user,
                    },
                )
                VGRecetaPreparacion.objects.create(
                    preparacion=preparation,
                    sub_preparacion=sub_preparation,
                    cantidad_requerida=component_amount,
                )

        return _auth_response({'ok': True, 'message': 'Receta guardada correctamente.', 'item': {'id': preparation.id, 'nombre': preparation.nombre}})

    if tipo == 'bebidas':
        nombre = str(data.get('nombre', '')).strip()
        if not nombre:
            return _auth_response({'ok': False, 'message': 'El nombre de la bebida es obligatorio.'}, status=400)

        category_name = str(data.get('categoria', '')).strip() or 'Bebidas'
        precio = data.get('precio', '0')
        try:
            price_value = Decimal(str(precio))
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'El precio de la bebida es inválido.'}, status=400)

        beverage_id = data.get('id')
        category, _ = VGCategoriaProducto.objects.get_or_create(nombre=category_name)
        beverage = None
        if beverage_id not in [None, '']:
            try:
                beverage = VGProducto.objects.get(pk=int(beverage_id))
            except (ValueError, TypeError, VGProducto.DoesNotExist):
                return _auth_response({'ok': False, 'message': 'La bebida a editar no existe.'}, status=400)

        if beverage is None:
            beverage, created = VGProducto.objects.get_or_create(
                nombre__iexact=nombre,
                defaults={
                    'nombre': nombre,
                    'descripcion': 'Creado desde el panel administrativo',
                    'categoria': category,
                    'precio_venta': price_value,
                    'costo_estimado': price_value,
                    'disponible': True,
                    'tiempo_preparacion_min': 0,
                    'creado_por': request.user,
                    'actualizado_por': request.user,
                },
            )
            if not created:
                beverage.categoria = category
                beverage.precio_venta = price_value
                beverage.costo_estimado = price_value
                beverage.actualizado_por = request.user
                beverage.save(update_fields=['categoria', 'precio_venta', 'costo_estimado', 'actualizado_por', 'fecha_actualizacion'])
        else:
            beverage.nombre = nombre
            beverage.categoria = category
            beverage.precio_venta = price_value
            beverage.costo_estimado = price_value
            beverage.actualizado_por = request.user
            beverage.save(update_fields=['nombre', 'categoria', 'precio_venta', 'costo_estimado', 'actualizado_por', 'fecha_actualizacion'])

        return _auth_response({'ok': True, 'message': 'Bebida guardada correctamente.', 'item': {'id': beverage.id, 'nombre': beverage.nombre}})

    return _auth_response({'ok': False, 'message': 'Tipo de catálogo inválido.'}, status=400)


def kitchen_orders_view(request):
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not request.user.is_authenticated:
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion para ver pedidos.'}, status=401)

    status_filter = str(request.GET.get('estado', 'activos')).strip().lower()
    limit_raw = request.GET.get('limit', 60)

    try:
        limit = max(1, min(int(limit_raw), 200))
    except (TypeError, ValueError):
        limit = 60

    active_statuses = ['pendiente', 'en_preparacion', 'listo']
    if status_filter == 'todos':
        statuses = [
            'pendiente',
            'en_preparacion',
            'listo',
            'entregado',
            'pagado',
            'cancelado',
        ]
    else:
        statuses = active_statuses

    base_queryset = VGPedido.objects.filter(estado__in=statuses)

    status_counts = {
        row['estado']: row['total']
        for row in (
            base_queryset
            .values('estado')
            .annotate(total=Count('id'))
        )
    }
    counts = {
        'pendiente': int(status_counts.get('pendiente', 0)),
        'en_preparacion': int(status_counts.get('en_preparacion', 0)),
        'listo': int(status_counts.get('listo', 0)),
    }

    pedidos = (
        base_queryset
        .select_related('mesa', 'usuario')
        .prefetch_related('detalles__producto')
        .order_by('fecha_creacion')[:limit]
    )

    payload_orders = []

    for pedido in pedidos:

        payload_orders.append({
            'id': pedido.id,
            'estado': pedido.estado,
            'tipo_pedido': pedido.tipo_pedido,
            'mesa': pedido.mesa.numero if pedido.mesa else None,
            'mesero': pedido.usuario.username,
            'cliente': pedido.cliente.nombre if pedido.cliente else '',
            'notas': pedido.notas,
            'total': str(pedido.total),
            'creado_en': pedido.fecha_creacion.isoformat(),
            'items': [
                {
                    'id': detalle.id,
                    'producto': detalle.producto.nombre,
                    'cantidad': detalle.cantidad,
                    'estado': detalle.estado,
                    'notas': detalle.notas,
                }
                for detalle in pedido.detalles.all()
            ],
        })

    return _auth_response({
        'ok': True,
        'server_time': timezone.now().isoformat(),
        'counts': counts,
        'orders': payload_orders,
    })


@csrf_exempt
def kitchen_order_status_update_view(request, pedido_id):
    if request.method not in ['POST', 'PATCH']:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not request.user.is_authenticated:
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion para actualizar pedidos.'}, status=401)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    next_state = str(data.get('estado', '')).strip().lower()
    allowed_states = {'pendiente', 'en_preparacion', 'listo', 'entregado', 'cancelado'}
    if next_state not in allowed_states:
        return _auth_response({'ok': False, 'message': 'Estado de destino invalido.'}, status=400)

    try:
        pedido = VGPedido.objects.prefetch_related('detalles').get(pk=pedido_id)
    except VGPedido.DoesNotExist:
        return _auth_response({'ok': False, 'message': 'El pedido no existe.'}, status=404)

    transitions = {
        'pendiente': {'en_preparacion', 'cancelado'},
        'en_preparacion': {'listo', 'cancelado'},
        'listo': {'entregado', 'en_preparacion'},
        'entregado': set(),
        'pagado': set(),
        'cancelado': set(),
    }

    allowed_next = transitions.get(pedido.estado, set())
    if next_state not in allowed_next:
        return _auth_response(
            {'ok': False, 'message': f'No se puede cambiar de {pedido.estado} a {next_state}.'},
            status=400,
        )

    with transaction.atomic():
        pedido.estado = next_state
        pedido.actualizado_por = request.user
        pedido.save(update_fields=['estado', 'actualizado_por', 'fecha_actualizacion'])

        if next_state == 'en_preparacion':
            pedido.detalles.filter(estado='pendiente').update(estado='en_preparacion')
        elif next_state == 'listo':
            pedido.detalles.filter(estado__in=['pendiente', 'en_preparacion']).update(estado='listo')
        elif next_state == 'entregado':
            pedido.detalles.filter(estado='listo').update(estado='entregado')

    _notify_cocina_event('PEDIDO_ACTUALIZADO', pedido, request.user)

    return _auth_response({
        'ok': True,
        'message': 'Estado actualizado correctamente.',
        'pedido': {
            'id': pedido.id,
            'estado': pedido.estado,
        },
    })


@method_decorator(csrf_exempt, name='dispatch')
class LoginView(generics.GenericAPIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request, *args, **kwargs):
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body.decode('utf-8')) if request.body else {}
        else:
            data = request.POST.dict()

        username = str(data.get('username', '')).strip()
        password = str(data.get('password', ''))

        user = authenticate(request, username=username, password=password)
        if user is None:
            return _auth_response({'authenticated': False, 'message': 'Credenciales inválidas'}, status=401)

        login(request, user)
        return _auth_response({
            'authenticated': True,
            'message': 'Bienvenido al sistema',
            'user': {
                'username': user.username,
                'email': user.email,
                'role': _get_role_name(user),
            },
        })


class SessionStatusView(generics.GenericAPIView):
    permission_classes = []

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return _auth_response({
                'authenticated': True,
                'user': {
                    'username': request.user.username,
                    'email': request.user.email,
                    'role': _get_role_name(request.user),
                },
            })

        return _auth_response({'authenticated': False})


@method_decorator(csrf_exempt, name='dispatch')
class LogoutView(generics.GenericAPIView):
    permission_classes = []

    def get(self, request, *args, **kwargs):
        logout(request)
        return _auth_response({'authenticated': False, 'message': 'Sesion cerrada'})

    def post(self, request, *args, **kwargs):
        logout(request)
        return _auth_response({'authenticated': False, 'message': 'Sesion cerrada'})

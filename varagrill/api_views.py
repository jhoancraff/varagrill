import json
from datetime import date, timedelta
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
    VGCompra,
    VGDetalleCompra,
    VGDetallePedido,
    VGIngrediente,
    VGMesa,
    VGMovimientoInventario,
    VGPedido,
    VGPreparacion,
    VGPromocion,
    VGProducto,
    VGRecetaProducto,
    VGRecetaPreparacion,
    VGRecomendacionChef,
    VGRol,
    VGUsuario,
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


def _is_admin_user(user):
    if not getattr(user, 'is_authenticated', False):
        return False
    role_name = _get_role_name(user).lower()
    return role_name == 'administrador' or bool(getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False))


def _serialize_role(role):
    return {
        'id': role.id,
        'nombre_role': role.nombre_role,
        'descripcion': role.descripcion,
    }


def _serialize_user(user):
    birth_date = user.fecha_nacimiento
    return {
        'id': user.id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
        'cedula': user.cedula,
        'telefono': user.telefono,
        'fecha_nacimiento': birth_date.isoformat() if hasattr(birth_date, 'isoformat') else str(birth_date or ''),
        'is_active': user.is_active,
        'is_staff': user.is_staff,
        'role': _serialize_role(user.id_role) if user.id_role else None,
    }


def _serialize_recipe_component(component):
    ingredient = component.ingrediente
    preparation = component.preparacion
    if ingredient is not None:
        return {
            'id': component.id,
            'tipo': 'ingrediente',
            'referencia_id': ingredient.id,
            'nombre': ingredient.nombre,
            'unidad': ingredient.unidad_medida,
            'cantidad': str(component.cantidad_requerida),
        }
    return {
        'id': component.id,
        'tipo': 'sub_preparacion',
        'referencia_id': preparation.id if preparation else None,
        'nombre': preparation.nombre if preparation else '',
        'unidad': preparation.rendimiento_unidad if preparation else 'unidad',
        'cantidad': str(component.cantidad_requerida),
    }


def _serialize_recipe_product(product):
    components = [
        _serialize_recipe_component(component)
        for component in product.receta.select_related('ingrediente', 'preparacion').order_by('id')
    ]
    return {
        'id': product.id,
        'nombre': product.nombre,
        'descripcion': product.descripcion,
        'categoria': product.categoria.nombre if product.categoria else '',
        'disponible': product.disponible,
        'componentes': components,
        'componentes_total': len(components),
    }


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


def _active_promotions_by_product(product_ids=None):
    today = timezone.localdate()
    queryset = VGPromocion.objects.filter(activo=True, fecha_inicio__lte=today, fecha_fin__gte=today)
    if product_ids is not None:
        queryset = queryset.filter(producto_id__in=product_ids)
    return {promotion.producto_id: promotion for promotion in queryset}


def _compute_discounted_price(precio_original, promotion):
    if promotion.tipo_descuento == 'porcentaje':
        descuento = precio_original * promotion.valor_descuento / Decimal('100')
    else:
        descuento = promotion.valor_descuento
    precio_final = precio_original - descuento
    return precio_final if precio_final > 0 else Decimal('0')


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
    active_promotions = _active_promotions_by_product(product_ids)

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
            promotion = active_promotions.get(product.id)
            unit_price = _compute_discounted_price(product.precio_venta, promotion) if promotion else product.precio_venta
            line_total = unit_price * line['cantidad']
            subtotal += line_total
            VGDetallePedido.objects.create(
                pedido=pedido,
                producto=product,
                cantidad=line['cantidad'],
                precio_unitario=unit_price,
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

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    if request.method == 'GET':
        recipe_components_by_preparation = {}
        for component in VGRecetaPreparacion.objects.select_related('preparacion', 'ingrediente', 'sub_preparacion').order_by('id'):
            preparation_id = component.preparacion_id
            if preparation_id not in recipe_components_by_preparation:
                recipe_components_by_preparation[preparation_id] = []

            if component.ingrediente_id:
                recipe_components_by_preparation[preparation_id].append({
                    'tipo': 'ingrediente',
                    'referencia_id': component.ingrediente_id,
                    'nombre': component.ingrediente.nombre if component.ingrediente else '',
                    'cantidad': str(component.cantidad_requerida),
                })
            elif component.sub_preparacion_id:
                recipe_components_by_preparation[preparation_id].append({
                    'tipo': 'sub_preparacion',
                    'referencia_id': component.sub_preparacion_id,
                    'nombre': component.sub_preparacion.nombre if component.sub_preparacion else '',
                    'cantidad': str(component.cantidad_requerida),
                })

        inventory = list(
            VGIngrediente.objects.order_by('-fecha_creacion', 'nombre').values('id', 'nombre', 'stock_actual', 'unidad_medida', 'ultimo_proveedor', 'costo_unitario', 'stock_minimo')
        )
        recipes = []
        for preparation in VGPreparacion.objects.order_by('-fecha_creacion', 'nombre').values('id', 'nombre', 'rendimiento_cantidad', 'rendimiento_unidad'):
            components = recipe_components_by_preparation.get(preparation['id'], [])
            recipes.append({
                **preparation,
                'componentes': components,
                'componentes_total': len(components),
            })
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

    if tipo == 'crear_ingrediente':
        nombre = str(data.get('nombre', '')).strip()
        if not nombre:
            return _auth_response({'ok': False, 'message': 'El nombre del ingrediente es obligatorio.'}, status=400)

        unidad = str(data.get('unidad', '')).strip() or 'unidad'
        proveedor = str(data.get('proveedor', '')).strip() or 'Sin proveedor'
        stock_actual = data.get('stock_actual', 0)
        stock_minimo = data.get('stock_minimo', 0)
        costo_unitario = data.get('costo_unitario', 0)

        try:
            stock_actual_value = Decimal(str(stock_actual or 0))
            stock_minimo_value = Decimal(str(stock_minimo or 0))
            costo_unitario_value = Decimal(str(costo_unitario or 0))
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'Los valores numéricos del ingrediente son inválidos.'}, status=400)

        existing = VGIngrediente.objects.filter(nombre__iexact=nombre).first()
        if existing is not None:
            return _auth_response({'ok': False, 'message': 'Ya existe un ingrediente con ese nombre.'}, status=400)

        ingredient = VGIngrediente.objects.create(
            nombre=nombre,
            unidad_medida=unidad,
            stock_actual=stock_actual_value,
            stock_minimo=stock_minimo_value,
            costo_unitario=costo_unitario_value,
            ultimo_proveedor=proveedor,
            creado_por=request.user,
            actualizado_por=request.user,
        )

        return _auth_response({'ok': True, 'message': 'Ingrediente creado correctamente.', 'item': {'id': ingredient.id, 'nombre': ingredient.nombre}}, status=201)

    if tipo == 'actualizar_ingrediente':
        ingredient_id = data.get('id')
        try:
            ingredient = VGIngrediente.objects.get(pk=int(ingredient_id))
        except (ValueError, TypeError, VGIngrediente.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'El ingrediente a actualizar no existe.'}, status=400)

        nombre = str(data.get('nombre', '')).strip()
        if not nombre:
            return _auth_response({'ok': False, 'message': 'El nombre del ingrediente es obligatorio.'}, status=400)

        unidad = str(data.get('unidad', '')).strip() or 'unidad'
        proveedor = str(data.get('proveedor', '')).strip() or 'Sin proveedor'
        stock_actual = data.get('stock_actual', ingredient.stock_actual)
        stock_minimo = data.get('stock_minimo', ingredient.stock_minimo)
        costo_unitario = data.get('costo_unitario', ingredient.costo_unitario)

        try:
            stock_actual_value = Decimal(str(stock_actual or 0))
            stock_minimo_value = Decimal(str(stock_minimo or 0))
            costo_unitario_value = Decimal(str(costo_unitario or 0))
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'Los valores numéricos del ingrediente son inválidos.'}, status=400)

        duplicate = VGIngrediente.objects.filter(nombre__iexact=nombre).exclude(pk=ingredient.pk).exists()
        if duplicate:
            return _auth_response({'ok': False, 'message': 'Ya existe otro ingrediente con ese nombre.'}, status=400)

        ingredient.nombre = nombre
        ingredient.unidad_medida = unidad
        ingredient.ultimo_proveedor = proveedor
        ingredient.stock_actual = stock_actual_value
        ingredient.stock_minimo = stock_minimo_value
        ingredient.costo_unitario = costo_unitario_value
        ingredient.actualizado_por = request.user
        ingredient.save(update_fields=['nombre', 'unidad_medida', 'ultimo_proveedor', 'stock_actual', 'stock_minimo', 'costo_unitario', 'actualizado_por', 'fecha_actualizacion'])

        return _auth_response({'ok': True, 'message': 'Ingrediente actualizado correctamente.', 'item': {'id': ingredient.id, 'nombre': ingredient.nombre}})

    if tipo == 'crear_preparacion':
        nombre = str(data.get('nombre', '')).strip()
        if not nombre:
            return _auth_response({'ok': False, 'message': 'El nombre de la subreceta es obligatorio.'}, status=400)

        rendimiento_cantidad = data.get('rendimiento_cantidad', '1')
        rendimiento_unidad = str(data.get('rendimiento_unidad', 'unidad')).strip() or 'unidad'
        componentes = data.get('componentes') or []

        try:
            rendimiento = Decimal(str(rendimiento_cantidad))
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'El rendimiento de la subreceta es inválido.'}, status=400)

        if rendimiento <= 0:
            return _auth_response({'ok': False, 'message': 'El rendimiento debe ser mayor a cero.'}, status=400)

        if VGPreparacion.objects.filter(nombre__iexact=nombre).exists():
            return _auth_response({'ok': False, 'message': 'Ya existe una subreceta con ese nombre.'}, status=400)

        with transaction.atomic():
            preparation = VGPreparacion.objects.create(
                nombre=nombre,
                rendimiento_cantidad=rendimiento,
                rendimiento_unidad=rendimiento_unidad,
                creado_por=request.user,
                actualizado_por=request.user,
            )

            for component in componentes:
                if not isinstance(component, dict):
                    continue
                component_type = str(component.get('tipo', '')).strip().lower()
                reference_id = component.get('referencia_id')
                try:
                    amount = Decimal(str(component.get('cantidad', '0') or '0'))
                except InvalidOperation:
                    return _auth_response({'ok': False, 'message': 'Hay una cantidad inválida en la subreceta.'}, status=400)
                if amount <= 0:
                    return _auth_response({'ok': False, 'message': 'Todas las cantidades deben ser mayores a cero.'}, status=400)

                if component_type == 'ingrediente':
                    try:
                        ingredient = VGIngrediente.objects.get(pk=int(reference_id))
                    except (ValueError, TypeError, VGIngrediente.DoesNotExist):
                        return _auth_response({'ok': False, 'message': 'Uno de los ingredientes seleccionados no existe.'}, status=400)
                    VGRecetaPreparacion.objects.create(
                        preparacion=preparation,
                        ingrediente=ingredient,
                        cantidad_requerida=amount,
                    )
                elif component_type == 'sub_preparacion':
                    try:
                        sub_preparation = VGPreparacion.objects.get(pk=int(reference_id))
                    except (ValueError, TypeError, VGPreparacion.DoesNotExist):
                        return _auth_response({'ok': False, 'message': 'Una subreceta seleccionada no existe.'}, status=400)
                    VGRecetaPreparacion.objects.create(
                        preparacion=preparation,
                        sub_preparacion=sub_preparation,
                        cantidad_requerida=amount,
                    )

        return _auth_response({'ok': True, 'message': 'Subreceta creada correctamente.', 'item': {'id': preparation.id, 'nombre': preparation.nombre}}, status=201)

    if tipo == 'actualizar_preparacion':
        preparation_id = data.get('id')
        try:
            preparation = VGPreparacion.objects.get(pk=int(preparation_id))
        except (ValueError, TypeError, VGPreparacion.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'La subreceta a actualizar no existe.'}, status=400)

        nombre = str(data.get('nombre', '')).strip()
        if not nombre:
            return _auth_response({'ok': False, 'message': 'El nombre de la subreceta es obligatorio.'}, status=400)

        rendimiento_cantidad = data.get('rendimiento_cantidad', preparation.rendimiento_cantidad)
        rendimiento_unidad = str(data.get('rendimiento_unidad', preparation.rendimiento_unidad or 'unidad')).strip() or 'unidad'
        componentes = data.get('componentes') or []

        try:
            rendimiento = Decimal(str(rendimiento_cantidad))
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'El rendimiento de la subreceta es inválido.'}, status=400)

        if rendimiento <= 0:
            return _auth_response({'ok': False, 'message': 'El rendimiento debe ser mayor a cero.'}, status=400)

        if VGPreparacion.objects.filter(nombre__iexact=nombre).exclude(pk=preparation.pk).exists():
            return _auth_response({'ok': False, 'message': 'Ya existe otra subreceta con ese nombre.'}, status=400)

        with transaction.atomic():
            preparation.nombre = nombre
            preparation.rendimiento_cantidad = rendimiento
            preparation.rendimiento_unidad = rendimiento_unidad
            preparation.actualizado_por = request.user
            preparation.save(update_fields=['nombre', 'rendimiento_cantidad', 'rendimiento_unidad', 'actualizado_por', 'fecha_actualizacion'])

            preparation.componentes.all().delete()

            for component in componentes:
                if not isinstance(component, dict):
                    continue
                component_type = str(component.get('tipo', '')).strip().lower()
                reference_id = component.get('referencia_id')
                try:
                    amount = Decimal(str(component.get('cantidad', '0') or '0'))
                except InvalidOperation:
                    return _auth_response({'ok': False, 'message': 'Hay una cantidad inválida en la subreceta.'}, status=400)
                if amount <= 0:
                    return _auth_response({'ok': False, 'message': 'Todas las cantidades deben ser mayores a cero.'}, status=400)

                if component_type == 'ingrediente':
                    try:
                        ingredient = VGIngrediente.objects.get(pk=int(reference_id))
                    except (ValueError, TypeError, VGIngrediente.DoesNotExist):
                        return _auth_response({'ok': False, 'message': 'Uno de los ingredientes seleccionados no existe.'}, status=400)
                    VGRecetaPreparacion.objects.create(
                        preparacion=preparation,
                        ingrediente=ingredient,
                        cantidad_requerida=amount,
                    )
                elif component_type == 'sub_preparacion':
                    try:
                        sub_preparation = VGPreparacion.objects.get(pk=int(reference_id))
                    except (ValueError, TypeError, VGPreparacion.DoesNotExist):
                        return _auth_response({'ok': False, 'message': 'Una subreceta seleccionada no existe.'}, status=400)
                    VGRecetaPreparacion.objects.create(
                        preparacion=preparation,
                        sub_preparacion=sub_preparation,
                        cantidad_requerida=amount,
                    )

        return _auth_response({'ok': True, 'message': 'Subreceta actualizada correctamente.', 'item': {'id': preparation.id, 'nombre': preparation.nombre}})

    if tipo == 'inventario':
        ingredient_id = data.get('ingrediente_id') or data.get('id')
        nombre = str(data.get('nombre', '')).strip()
        if not nombre:
            return _auth_response({'ok': False, 'message': 'El nombre del insumo es obligatorio.'}, status=400)

        unidad = str(data.get('unidad', '')).strip() or 'unidad'
        proveedor = str(data.get('proveedor', '')).strip() or 'Sin proveedor'
        cantidad = data.get('cantidad', 0)
        stock_minimo = data.get('stock_minimo', 0)
        costo_unitario = data.get('costo_unitario', 0)
        try:
            cantidad_value = Decimal(str(cantidad))
            stock_minimo_value = Decimal(str(stock_minimo or 0))
            costo_unitario_value = Decimal(str(costo_unitario or 0))
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'Los datos numéricos del insumo son inválidos.'}, status=400)

        if cantidad_value <= 0:
            return _auth_response({'ok': False, 'message': 'La cantidad del ingreso debe ser mayor a cero.'}, status=400)

        ingredient = None
        if ingredient_id not in [None, '']:
            try:
                ingredient = VGIngrediente.objects.get(pk=int(ingredient_id))
            except (ValueError, TypeError, VGIngrediente.DoesNotExist):
                return _auth_response({'ok': False, 'message': 'El insumo a editar no existe.'}, status=400)

        with transaction.atomic():
            if ingredient is None:
                ingredient, created = VGIngrediente.objects.get_or_create(
                    nombre__iexact=nombre,
                    defaults={
                        'nombre': nombre,
                        'unidad_medida': unidad,
                        'stock_actual': 0,
                        'stock_minimo': stock_minimo_value,
                        'costo_unitario': costo_unitario_value,
                        'ultimo_proveedor': proveedor,
                        'creado_por': request.user,
                        'actualizado_por': request.user,
                    },
                )
                if not created:
                    ingredient.nombre = nombre
                    ingredient.unidad_medida = unidad
                    ingredient.stock_minimo = stock_minimo_value
                    ingredient.costo_unitario = costo_unitario_value
                    ingredient.ultimo_proveedor = proveedor
                    ingredient.actualizado_por = request.user
                    ingredient.save(update_fields=['nombre', 'unidad_medida', 'stock_minimo', 'costo_unitario', 'ultimo_proveedor', 'actualizado_por', 'fecha_actualizacion'])
            else:
                ingredient.nombre = nombre
                ingredient.unidad_medida = unidad
                ingredient.stock_minimo = stock_minimo_value
                ingredient.costo_unitario = costo_unitario_value
                ingredient.ultimo_proveedor = proveedor
                ingredient.actualizado_por = request.user
                ingredient.save(update_fields=['nombre', 'unidad_medida', 'stock_minimo', 'costo_unitario', 'ultimo_proveedor', 'actualizado_por', 'fecha_actualizacion'])

            ingredient.stock_actual = Decimal(str(ingredient.stock_actual)) + cantidad_value
            ingredient.actualizado_por = request.user
            ingredient.save(update_fields=['stock_actual', 'actualizado_por', 'fecha_actualizacion'])

            total_compra = cantidad_value * costo_unitario_value
            compra = VGCompra.objects.create(
                proveedor_nombre=proveedor,
                total=total_compra,
                estado='recibido',
                creado_por=request.user,
                actualizado_por=request.user,
            )
            VGDetalleCompra.objects.create(
                compra=compra,
                ingrediente=ingredient,
                cantidad=cantidad_value,
                costo_unitario=costo_unitario_value,
            )
            VGMovimientoInventario.objects.create(
                ingrediente=ingredient,
                tipo_movimiento='entrada',
                cantidad=cantidad_value,
                motivo=f'Compra registrada #{compra.id}',
                id_referencia=compra.id,
                creado_por=request.user,
            )

        return _auth_response({
            'ok': True,
            'message': 'Ingreso de inventario registrado correctamente.',
            'item': {
                'id': ingredient.id,
                'nombre': ingredient.nombre,
                'stock_actual': str(ingredient.stock_actual),
            },
        })

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


@csrf_exempt
def admin_users_view(request):
    if request.method not in ['GET', 'POST']:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    if request.method == 'GET':
        roles = VGRol.objects.order_by('nombre_role')
        users = VGUsuario.objects.select_related('id_role').order_by('username')
        return _auth_response({
            'ok': True,
            'roles': [_serialize_role(role) for role in roles],
            'users': [_serialize_user(user) for user in users],
        })

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    action = str(data.get('action', '')).strip().lower()

    if action == 'delete':
        user_id = data.get('id')
        try:
            target_user = VGUsuario.objects.get(pk=int(user_id))
        except (ValueError, TypeError, VGUsuario.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'El usuario a eliminar no existe.'}, status=400)

        if target_user.id == request.user.id:
            return _auth_response({'ok': False, 'message': 'No puedes eliminar tu propio usuario.'}, status=400)

        target_user.delete()
        return _auth_response({'ok': True, 'message': 'Usuario eliminado correctamente.'})

    if action not in {'create', 'update'}:
        return _auth_response({'ok': False, 'message': 'Accion de usuarios inválida.'}, status=400)

    username = str(data.get('username', '')).strip()
    cedula = str(data.get('cedula', '')).strip()
    password = str(data.get('password', '') or '')
    first_name = str(data.get('first_name', '') or '').strip()
    last_name = str(data.get('last_name', '') or '').strip()
    email = str(data.get('email', '') or '').strip()
    telefono = str(data.get('telefono', '') or '').strip()
    fecha_nacimiento = data.get('fecha_nacimiento') or None
    role_id = data.get('role_id')
    is_active = bool(data.get('is_active', True))

    if not username:
        return _auth_response({'ok': False, 'message': 'El nombre de usuario es obligatorio.'}, status=400)
    if not cedula:
        return _auth_response({'ok': False, 'message': 'La cédula es obligatoria.'}, status=400)
    if action == 'create' and not password:
        return _auth_response({'ok': False, 'message': 'La contraseña es obligatoria para crear el usuario.'}, status=400)

    role = None
    if role_id not in [None, '']:
        try:
            role = VGRol.objects.get(pk=int(role_id))
        except (ValueError, TypeError, VGRol.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'El rol seleccionado no existe.'}, status=400)

    target_user = None
    if action == 'update':
        user_id = data.get('id')
        try:
            target_user = VGUsuario.objects.get(pk=int(user_id))
        except (ValueError, TypeError, VGUsuario.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'El usuario a editar no existe.'}, status=400)

    username_query = VGUsuario.objects.filter(username__iexact=username)
    cedula_query = VGUsuario.objects.filter(cedula__iexact=cedula)
    if target_user is not None:
        username_query = username_query.exclude(pk=target_user.pk)
        cedula_query = cedula_query.exclude(pk=target_user.pk)

    if username_query.exists():
        return _auth_response({'ok': False, 'message': 'Ya existe un usuario con ese nombre.'}, status=400)
    if cedula_query.exists():
        return _auth_response({'ok': False, 'message': 'Ya existe un usuario con esa cédula.'}, status=400)

    role_name = str(role.nombre_role if role else '').strip().lower()
    should_be_staff = role_name == 'administrador'

    if action == 'create':
        target_user = VGUsuario.objects.create_user(
            username=username,
            password=password,
            cedula=cedula,
            first_name=first_name,
            last_name=last_name,
            email=email,
            telefono=telefono,
            fecha_nacimiento=fecha_nacimiento or None,
            id_role=role,
            is_active=is_active,
            is_staff=should_be_staff,
        )
        message = 'Usuario creado correctamente.'
    else:
        target_user.username = username
        target_user.cedula = cedula
        target_user.first_name = first_name
        target_user.last_name = last_name
        target_user.email = email
        target_user.telefono = telefono
        target_user.fecha_nacimiento = fecha_nacimiento or None
        target_user.id_role = role
        target_user.is_active = is_active
        target_user.is_staff = should_be_staff or target_user.is_superuser
        if password:
            target_user.set_password(password)
        target_user.save()
        message = 'Usuario actualizado correctamente.'

    return _auth_response({
        'ok': True,
        'message': message,
        'user': _serialize_user(target_user),
    }, status=201 if action == 'create' else 200)


@csrf_exempt
def admin_recipes_view(request):
    if request.method not in ['GET', 'POST']:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    if request.method == 'GET':
        recipes = VGProducto.objects.filter(categoria__nombre__iexact='Recetas').select_related('categoria').prefetch_related('receta__ingrediente', 'receta__preparacion').order_by('nombre')
        inventory = list(
            VGIngrediente.objects.order_by('nombre').values('id', 'nombre', 'unidad_medida', 'stock_actual')
        )
        preparations = list(
            VGPreparacion.objects.order_by('nombre').values('id', 'nombre', 'rendimiento_unidad', 'rendimiento_cantidad')
        )
        return _auth_response({
            'ok': True,
            'recipes': [_serialize_recipe_product(recipe) for recipe in recipes],
            'ingredients': inventory,
            'preparations': preparations,
        })

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    action = str(data.get('action', '')).strip().lower()

    if action == 'delete':
        recipe_id = data.get('id')
        try:
            recipe = VGProducto.objects.filter(categoria__nombre__iexact='Recetas').get(pk=int(recipe_id))
        except (ValueError, TypeError, VGProducto.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'La receta a eliminar no existe.'}, status=400)

        recipe.delete()
        return _auth_response({'ok': True, 'message': 'Receta eliminada correctamente.'})

    if action not in {'create', 'update'}:
        return _auth_response({'ok': False, 'message': 'Accion de receta invalida.'}, status=400)

    nombre = str(data.get('nombre', '') or '').strip()
    descripcion = str(data.get('descripcion', '') or '').strip()
    componentes = data.get('componentes') or []

    if not nombre:
        return _auth_response({'ok': False, 'message': 'El nombre de la receta es obligatorio.'}, status=400)
    if not isinstance(componentes, list) or len(componentes) == 0:
        return _auth_response({'ok': False, 'message': 'Debes agregar al menos un ingrediente o subreceta.'}, status=400)

    recipe = None
    if action == 'update':
        recipe_id = data.get('id')
        try:
            recipe = VGProducto.objects.filter(categoria__nombre__iexact='Recetas').get(pk=int(recipe_id))
        except (ValueError, TypeError, VGProducto.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'La receta a editar no existe.'}, status=400)

    existing_name_query = VGProducto.objects.filter(categoria__nombre__iexact='Recetas', nombre__iexact=nombre)
    if recipe is not None:
        existing_name_query = existing_name_query.exclude(pk=recipe.pk)
    if existing_name_query.exists():
        return _auth_response({'ok': False, 'message': 'Ya existe una receta con ese nombre.'}, status=400)

    parsed_components = []
    duplicate_guard = set()
    for raw_component in componentes:
        if not isinstance(raw_component, dict):
            continue

        component_type = str(raw_component.get('tipo', '')).strip().lower()
        reference_id = raw_component.get('referencia_id')
        try:
            amount = Decimal(str(raw_component.get('cantidad', '0') or '0'))
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'Hay una cantidad inválida en los componentes de la receta.'}, status=400)

        if amount <= 0:
            return _auth_response({'ok': False, 'message': 'Todas las cantidades de la receta deben ser mayores a cero.'}, status=400)

        if component_type not in {'ingrediente', 'sub_preparacion'}:
            return _auth_response({'ok': False, 'message': 'Tipo de componente inválido en la receta.'}, status=400)

        if reference_id in [None, '']:
            return _auth_response({'ok': False, 'message': 'Falta seleccionar un ingrediente o subreceta.'}, status=400)

        try:
            reference_id = int(reference_id)
        except (TypeError, ValueError):
            return _auth_response({'ok': False, 'message': 'Referencia inválida en los componentes de la receta.'}, status=400)

        duplicate_key = f'{component_type}:{reference_id}'
        if duplicate_key in duplicate_guard:
            return _auth_response({'ok': False, 'message': 'No puedes repetir el mismo componente en la receta.'}, status=400)
        duplicate_guard.add(duplicate_key)

        parsed_components.append({
            'tipo': component_type,
            'referencia_id': reference_id,
            'cantidad': amount,
        })

    if len(parsed_components) == 0:
        return _auth_response({'ok': False, 'message': 'No se encontraron componentes válidos para la receta.'}, status=400)

    category, _ = VGCategoriaProducto.objects.get_or_create(
        nombre='Recetas',
        defaults={'descripcion': 'Recetas administrativas de producción'},
    )

    with transaction.atomic():
        if recipe is None:
            recipe = VGProducto.objects.create(
                nombre=nombre,
                descripcion=descripcion,
                categoria=category,
                precio_venta=Decimal('0'),
                costo_estimado=Decimal('0'),
                disponible=False,
                tiempo_preparacion_min=0,
                creado_por=request.user,
                actualizado_por=request.user,
            )
            message = 'Receta creada correctamente.'
            status_code = 201
        else:
            recipe.nombre = nombre
            recipe.descripcion = descripcion
            recipe.categoria = category
            recipe.disponible = False
            recipe.actualizado_por = request.user
            recipe.save(update_fields=['nombre', 'descripcion', 'categoria', 'disponible', 'actualizado_por', 'fecha_actualizacion'])
            message = 'Receta actualizada correctamente.'
            status_code = 200

        recipe.receta.all().delete()

        for component in parsed_components:
            if component['tipo'] == 'ingrediente':
                try:
                    ingredient = VGIngrediente.objects.get(pk=component['referencia_id'])
                except VGIngrediente.DoesNotExist:
                    return _auth_response({'ok': False, 'message': 'Uno de los ingredientes seleccionados no existe.'}, status=400)
                VGRecetaProducto.objects.create(
                    producto=recipe,
                    ingrediente=ingredient,
                    cantidad_requerida=component['cantidad'],
                )
            else:
                try:
                    preparation = VGPreparacion.objects.get(pk=component['referencia_id'])
                except VGPreparacion.DoesNotExist:
                    return _auth_response({'ok': False, 'message': 'Una de las subrecetas seleccionadas no existe.'}, status=400)
                VGRecetaProducto.objects.create(
                    producto=recipe,
                    preparacion=preparation,
                    cantidad_requerida=component['cantidad'],
                )

    recipe = VGProducto.objects.filter(pk=recipe.pk).select_related('categoria').prefetch_related('receta__ingrediente', 'receta__preparacion').first()
    return _auth_response({
        'ok': True,
        'message': message,
        'recipe': _serialize_recipe_product(recipe),
    }, status=status_code)


def _parse_promotion_discount_fields(data):
    """Valida tipo_descuento/valor_descuento/duracion_dias, compartido entre alta individual y masiva."""
    tipo_descuento = str(data.get('tipo_descuento', '')).strip().lower()
    tipo_keys = {tipo for tipo, _ in VGPromocion.TIPOS_DESCUENTO}
    if tipo_descuento not in tipo_keys:
        return None, 'El tipo de descuento es invalido.'

    try:
        valor_descuento = Decimal(str(data.get('valor_descuento', '')))
    except InvalidOperation:
        return None, 'El valor del descuento es invalido.'

    if valor_descuento <= 0:
        return None, 'El valor del descuento debe ser mayor a cero.'

    if tipo_descuento == 'porcentaje' and valor_descuento > 100:
        return None, 'El porcentaje de descuento no puede superar 100.'

    try:
        duracion_dias = int(data.get('duracion_dias', 0))
    except (TypeError, ValueError):
        return None, 'La duracion de la promocion es invalida.'

    if duracion_dias <= 0:
        return None, 'La duracion de la promocion debe ser de al menos 1 dia.'

    return {
        'tipo_descuento': tipo_descuento,
        'valor_descuento': valor_descuento,
        'duracion_dias': duracion_dias,
    }, None


def _serialize_promotion(promotion):
    return {
        'id': promotion.id,
        'titulo': promotion.titulo,
        'descripcion': promotion.descripcion,
        'tipo_descuento': promotion.tipo_descuento,
        'valor_descuento': str(promotion.valor_descuento),
        'duracion_dias': promotion.duracion_dias,
        'fecha_inicio': promotion.fecha_inicio.isoformat(),
        'fecha_fin': promotion.fecha_fin.isoformat() if promotion.fecha_fin else None,
    }


@csrf_exempt
def admin_promotions_view(request):
    if request.method not in ['GET', 'POST']:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    if request.method == 'GET':
        today = timezone.localdate()
        products = (
            VGProducto.objects.filter(disponible=True)
            .select_related('categoria')
            .order_by('nombre')
        )
        active_promotions = {
            promotion.producto_id: promotion
            for promotion in VGPromocion.objects.filter(
                activo=True, fecha_inicio__lte=today, fecha_fin__gte=today,
            )
        }
        return _auth_response({
            'ok': True,
            'products': [
                {
                    'id': product.id,
                    'nombre': product.nombre,
                    'categoria': product.categoria.nombre if product.categoria else '',
                    'precio_venta': str(product.precio_venta),
                    'promocion_activa': product.id in active_promotions,
                    'promocion': (
                        _serialize_promotion(active_promotions[product.id])
                        if product.id in active_promotions else None
                    ),
                }
                for product in products
            ],
        })

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    action = str(data.get('action', '')).strip().lower()
    if action not in {'create', 'create_bulk', 'update', 'delete'}:
        return _auth_response({'ok': False, 'message': 'Accion de promocion invalida.'}, status=400)

    if action == 'delete':
        promotion_id = data.get('id')
        try:
            promotion = VGPromocion.objects.get(pk=int(promotion_id))
        except (ValueError, TypeError, VGPromocion.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'La promoción a eliminar no existe.'}, status=400)

        promotion.delete()
        return _auth_response({'ok': True, 'message': 'Promoción eliminada correctamente.'})

    fields, error = _parse_promotion_discount_fields(data)
    if error:
        return _auth_response({'ok': False, 'message': error}, status=400)

    descripcion = str(data.get('descripcion', '') or '').strip()
    fecha_inicio = timezone.localdate()
    fecha_fin = fecha_inicio + timedelta(days=fields['duracion_dias'])

    if action == 'update':
        promotion_id = data.get('id')
        try:
            promotion = VGPromocion.objects.get(pk=int(promotion_id))
        except (ValueError, TypeError, VGPromocion.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'La promoción a actualizar no existe.'}, status=400)

        titulo = str(data.get('titulo', '') or '').strip() or promotion.titulo

        promotion.titulo = titulo
        promotion.descripcion = descripcion
        promotion.tipo_descuento = fields['tipo_descuento']
        promotion.valor_descuento = fields['valor_descuento']
        promotion.duracion_dias = fields['duracion_dias']
        promotion.fecha_inicio = fecha_inicio
        promotion.fecha_fin = fecha_fin
        promotion.activo = True
        promotion.actualizado_por = request.user
        promotion.save(update_fields=[
            'titulo', 'descripcion', 'tipo_descuento', 'valor_descuento', 'duracion_dias',
            'fecha_inicio', 'fecha_fin', 'activo', 'actualizado_por', 'fecha_actualizacion',
        ])

        return _auth_response({
            'ok': True,
            'message': 'Promoción actualizada correctamente.',
            'item': {
                'id': promotion.id,
                'producto_id': promotion.producto_id,
                'fecha_inicio': promotion.fecha_inicio.isoformat(),
                'fecha_fin': promotion.fecha_fin.isoformat(),
            },
        })

    if action == 'create':
        product_id = data.get('producto_id')
        try:
            product = VGProducto.objects.get(pk=int(product_id), disponible=True)
        except (ValueError, TypeError, VGProducto.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'El producto seleccionado no existe.'}, status=400)

        titulo = str(data.get('titulo', '') or '').strip() or f'Promoción {product.nombre}'

        promotion = VGPromocion.objects.create(
            titulo=titulo,
            descripcion=descripcion,
            producto=product,
            tipo_descuento=fields['tipo_descuento'],
            valor_descuento=fields['valor_descuento'],
            duracion_dias=fields['duracion_dias'],
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            activo=True,
            creado_por=request.user,
            actualizado_por=request.user,
        )

        return _auth_response({
            'ok': True,
            'message': 'Promoción creada correctamente.',
            'item': {
                'id': promotion.id,
                'producto_id': product.id,
                'fecha_inicio': promotion.fecha_inicio.isoformat(),
                'fecha_fin': promotion.fecha_fin.isoformat(),
            },
        }, status=201)

    # action == 'create_bulk'
    raw_ids = data.get('producto_ids')
    if not isinstance(raw_ids, list) or len(raw_ids) == 0:
        return _auth_response({'ok': False, 'message': 'Debes seleccionar al menos un producto.'}, status=400)

    try:
        product_ids = sorted({int(raw_id) for raw_id in raw_ids})
    except (TypeError, ValueError):
        return _auth_response({'ok': False, 'message': 'Hay un producto invalido en la selección.'}, status=400)

    products_by_id = {
        product.id: product
        for product in VGProducto.objects.filter(id__in=product_ids, disponible=True)
    }
    active_product_ids = set(
        VGPromocion.objects.filter(
            producto_id__in=product_ids, activo=True, fecha_inicio__lte=fecha_inicio, fecha_fin__gte=fecha_inicio,
        ).values_list('producto_id', flat=True)
    )

    omitted = []
    to_create = []
    for product_id in product_ids:
        product = products_by_id.get(product_id)
        if product is None:
            omitted.append({'id': product_id, 'nombre': '', 'motivo': 'Producto no encontrado o no disponible.'})
            continue
        if product_id in active_product_ids:
            omitted.append({'id': product_id, 'nombre': product.nombre, 'motivo': 'Ya tiene una promoción activa.'})
            continue
        to_create.append(product)

    if not to_create:
        return _auth_response({
            'ok': False,
            'message': 'Ningún producto seleccionado pudo recibir la promoción.',
            'omitidas': omitted,
        }, status=400)

    created_items = []
    with transaction.atomic():
        for product in to_create:
            promotion = VGPromocion.objects.create(
                titulo=f'Promoción {product.nombre}',
                descripcion=descripcion,
                producto=product,
                tipo_descuento=fields['tipo_descuento'],
                valor_descuento=fields['valor_descuento'],
                duracion_dias=fields['duracion_dias'],
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                activo=True,
                creado_por=request.user,
                actualizado_por=request.user,
            )
            created_items.append({'id': promotion.id, 'producto_id': product.id, 'nombre': product.nombre})

    return _auth_response({
        'ok': True,
        'message': f'{len(created_items)} promoción(es) creada(s) correctamente.',
        'creadas': created_items,
        'omitidas': omitted,
    }, status=201)


def promociones_activas_view(request):
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not request.user.is_authenticated:
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion.'}, status=401)

    today = timezone.localdate()
    promotions = (
        VGPromocion.objects
        .filter(activo=True, fecha_inicio__lte=today, fecha_fin__gte=today, producto__isnull=False)
        .select_related('producto', 'producto__categoria')
        .order_by('-fecha_creacion')
    )

    payload = []
    for promotion in promotions:
        product = promotion.producto
        precio_original = product.precio_venta
        precio_descuento = _compute_discounted_price(precio_original, promotion)

        if promotion.tipo_descuento == 'porcentaje':
            porcentaje = promotion.valor_descuento
        else:
            porcentaje = (
                (promotion.valor_descuento / precio_original * Decimal('100'))
                if precio_original else Decimal('0')
            )

        payload.append({
            'id': promotion.id,
            'titulo': promotion.titulo,
            'descripcion': promotion.descripcion,
            'producto_id': product.id,
            'producto_nombre': product.nombre,
            'categoria': product.categoria.nombre if product.categoria else '',
            'precio_original': str(precio_original.quantize(Decimal('0.01'))),
            'precio_descuento': str(precio_descuento.quantize(Decimal('0.01'))),
            'porcentaje_descuento': str(porcentaje.quantize(Decimal('0.1'))),
            'fecha_fin': promotion.fecha_fin.isoformat() if promotion.fecha_fin else None,
        })

    return _auth_response({'ok': True, 'promotions': payload})


def recomendaciones_chef_activas_view(request):
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not request.user.is_authenticated:
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion.'}, status=401)

    today = timezone.localdate()
    recommendations = (
        VGRecomendacionChef.objects
        .filter(activo=True, fecha=today, producto__isnull=False)
        .select_related('producto', 'producto__categoria')
        .order_by('producto__nombre')
    )

    payload = [
        {
            'id': recommendation.id,
            'producto_id': recommendation.producto.id,
            'producto_nombre': recommendation.producto.nombre,
            'categoria': recommendation.producto.categoria.nombre if recommendation.producto.categoria else '',
            'precio_venta': str(recommendation.producto.precio_venta),
            'comentario_chef': recommendation.comentario_chef,
            'fecha': recommendation.fecha.isoformat(),
        }
        for recommendation in recommendations
    ]

    return _auth_response({'ok': True, 'recommendations': payload})


@csrf_exempt
def admin_chef_recommendations_view(request):
    if request.method not in ['GET', 'POST']:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    if request.method == 'GET':
        recommendations = (
            VGRecomendacionChef.objects
            .select_related('producto', 'producto__categoria')
            .order_by('-fecha', 'producto__nombre')
        )
        products = list(
            VGProducto.objects.filter(disponible=True).order_by('nombre').values('id', 'nombre', 'precio_venta')
        )
        return _auth_response({
            'ok': True,
            'recommendations': [
                {
                    'id': recommendation.id,
                    'producto_id': recommendation.producto_id,
                    'producto_nombre': recommendation.producto.nombre if recommendation.producto else '',
                    'categoria': (
                        recommendation.producto.categoria.nombre
                        if recommendation.producto and recommendation.producto.categoria else ''
                    ),
                    'comentario_chef': recommendation.comentario_chef,
                    'fecha': recommendation.fecha.isoformat(),
                    'activo': recommendation.activo,
                }
                for recommendation in recommendations
            ],
            'products': [
                {**product, 'precio_venta': str(product['precio_venta'])}
                for product in products
            ],
        })

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    action = str(data.get('action', '')).strip().lower()

    if action == 'delete':
        recommendation_id = data.get('id')
        try:
            recommendation = VGRecomendacionChef.objects.get(pk=int(recommendation_id))
        except (ValueError, TypeError, VGRecomendacionChef.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'La recomendación a eliminar no existe.'}, status=400)

        recommendation.delete()
        return _auth_response({'ok': True, 'message': 'Recomendación eliminada correctamente.'})

    if action != 'create':
        return _auth_response({'ok': False, 'message': 'Accion de recomendacion invalida.'}, status=400)

    product_id = data.get('producto_id')
    try:
        product = VGProducto.objects.get(pk=int(product_id), disponible=True)
    except (ValueError, TypeError, VGProducto.DoesNotExist):
        return _auth_response({'ok': False, 'message': 'El producto seleccionado no existe.'}, status=400)

    fecha_raw = str(data.get('fecha', '') or '').strip()
    try:
        fecha = date.fromisoformat(fecha_raw) if fecha_raw else timezone.localdate()
    except ValueError:
        return _auth_response({'ok': False, 'message': 'La fecha indicada es invalida.'}, status=400)

    comentario_chef = str(data.get('comentario_chef', '') or '').strip()

    if VGRecomendacionChef.objects.filter(producto=product, fecha=fecha).exists():
        return _auth_response(
            {'ok': False, 'message': 'Ese producto ya tiene una recomendación registrada para esa fecha.'},
            status=400,
        )

    recommendation = VGRecomendacionChef.objects.create(
        producto=product,
        comentario_chef=comentario_chef,
        fecha=fecha,
        activo=True,
        creado_por=request.user,
        actualizado_por=request.user,
    )

    return _auth_response({
        'ok': True,
        'message': 'Recomendación creada correctamente.',
        'item': {
            'id': recommendation.id,
            'producto_id': product.id,
            'fecha': recommendation.fecha.isoformat(),
        },
    }, status=201)


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
                'is_admin': _is_admin_user(user),
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
                    'is_admin': _is_admin_user(request.user),
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

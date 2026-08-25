import ipaddress
import json
import mimetypes
import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from django.conf import settings
from django.core.files.storage import default_storage
from django.utils.text import get_valid_filename
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import authenticate, login, logout
from django.http import FileResponse, Http404
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
    VGDetallePedidoAdicional,
    VGDetallePedidoOpcion,
    VGGrupoOpcionProducto,
    VGImpresoraCaja,
    VGIngrediente,
    VGMesa,
    VGMetodoPago,
    VGMovimientoInventario,
    VGOpcionProducto,
    VGPedido,
    VGPago,
    VGPreparacion,
    VGPromocion,
    VGProducto,
    VGRecetaProducto,
    VGRecetaPreparacion,
    VGRecomendacionChef,
    VGRol,
    VGUsuario,
)
from .auth_helpers import _auth_response, _get_role_name, _is_admin_user, _is_cajera_user, _is_mesero_user
from .impresion_lpd import imprimir_recibo_caja
from .impresion_termica import imprimir_comandas_pedido
from .ingredientes_excel import (
    InvalidExcelError,
    normalize_unidad,
    parse_cantidad,
    parse_ingredientes_workbook,
    parse_precio_total,
)
from .notifications import send_whatsapp_new_order_alert
from .serializers import MesaSerializer, ProductoSerializer
from .tasa_cambio import obtener_tasa_actual

logger = logging.getLogger(__name__)


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


_UNIDAD_FAMILIA = {
    'kg': ('masa', Decimal('1000')),
    'g': ('masa', Decimal('1')),
    'l': ('volumen', Decimal('1000')),
    'ml': ('volumen', Decimal('1')),
    'unidad': ('conteo', Decimal('1')),
}


def _convertir_cantidad_a_unidad_ingrediente(cantidad, unidad_ingresada, unidad_ingrediente):
    """
    Convierte `cantidad` desde `unidad_ingresada` (la unidad que tecleó el analista al
    armar la receta, ej. 'g') a `unidad_ingrediente` (la unidad en la que vive el stock
    del ingrediente, ej. 'kg'), para que `cantidad_requerida` siempre quede guardada en
    la unidad del inventario y el descuento al cobrar (_compute_pedido_ingredient_needs)
    no necesite saber nada de conversión. Sin unidad_ingresada (caso de /api/admin/recetas/,
    que no la envía) se asume que la cantidad ya viene en la unidad del ingrediente.

    Devuelve None si las unidades son de familias incompatibles (ej. kg vs unidad).
    """
    unidad_ingresada = unidad_ingresada or unidad_ingrediente
    if unidad_ingresada == unidad_ingrediente:
        return cantidad
    origen = _UNIDAD_FAMILIA.get(unidad_ingresada)
    destino = _UNIDAD_FAMILIA.get(unidad_ingrediente)
    if not origen or not destino or origen[0] != destino[0]:
        return None
    return (cantidad * origen[1]) / destino[1]


def _parse_recipe_components(componentes, *, require_at_least_one):
    """
    Valida y normaliza la lista `componentes` que manda el buscador de ingredientes/
    subrecetas del frontend a [{tipo, referencia_id, cantidad, unidad}, ...]. Compartido
    entre /api/admin/recetas/ (recetas del catálogo) y /api/admin/productos/ (ingredientes
    propios de un producto vendible). `unidad` es opcional: la unidad en la que el analista
    tecleó la cantidad (ver _convertir_cantidad_a_unidad_ingrediente).

    Devuelve (lista_de_componentes, None) o (None, mensaje_error).
    """
    if not isinstance(componentes, list):
        return None, 'Formato inválido de ingredientes/subrecetas.'
    if require_at_least_one and len(componentes) == 0:
        return None, 'Debes agregar al menos un ingrediente o subreceta.'

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
            return None, 'Hay una cantidad inválida en los componentes de la receta.'

        if amount <= 0:
            return None, 'Todas las cantidades de la receta deben ser mayores a cero.'

        if component_type not in {'ingrediente', 'sub_preparacion'}:
            return None, 'Tipo de componente inválido en la receta.'

        if reference_id in [None, '']:
            return None, 'Falta seleccionar un ingrediente o subreceta.'

        try:
            reference_id = int(reference_id)
        except (TypeError, ValueError):
            return None, 'Referencia inválida en los componentes de la receta.'

        duplicate_key = f'{component_type}:{reference_id}'
        if duplicate_key in duplicate_guard:
            return None, 'No puedes repetir el mismo componente en la receta.'
        duplicate_guard.add(duplicate_key)

        parsed_components.append({
            'tipo': component_type,
            'referencia_id': reference_id,
            'cantidad': amount,
            'unidad': str(raw_component.get('unidad') or '').strip().lower() or None,
        })

    if require_at_least_one and len(parsed_components) == 0:
        return None, 'No se encontraron componentes válidos para la receta.'

    return parsed_components, None


def _resolve_recipe_components_for_save(parsed_components):
    """
    Resuelve cada componente ya validado por _parse_recipe_components contra la base de
    datos (VGIngrediente/VGPreparacion) y convierte la cantidad de ingredientes a la
    unidad base del ingrediente. Se resuelve todo ANTES de que el caller borre/reescriba
    las filas de VGRecetaProducto, para no dejar una receta a medio borrar si algún
    componente ya no existe o su unidad es incompatible.

    Devuelve (filas_listas, None) — cada fila es {'ingrediente', 'preparacion',
    'cantidad_requerida'} lista para instanciar VGRecetaProducto — o (None, mensaje_error).
    """
    resolved = []
    for component in parsed_components:
        if component['tipo'] == 'ingrediente':
            try:
                ingredient = VGIngrediente.objects.get(pk=component['referencia_id'])
            except VGIngrediente.DoesNotExist:
                return None, 'Uno de los ingredientes seleccionados no existe.'
            cantidad = _convertir_cantidad_a_unidad_ingrediente(
                component['cantidad'], component['unidad'], ingredient.unidad_medida,
            )
            if cantidad is None:
                return None, (
                    f'La unidad seleccionada para "{ingredient.nombre}" no es compatible con su '
                    f'unidad de inventario ({ingredient.unidad_medida}).'
                )
            resolved.append({'ingrediente': ingredient, 'preparacion': None, 'cantidad_requerida': cantidad})
        else:
            try:
                preparation = VGPreparacion.objects.get(pk=component['referencia_id'])
            except VGPreparacion.DoesNotExist:
                return None, 'Una de las subrecetas seleccionadas no existe.'
            resolved.append({
                'ingrediente': None, 'preparacion': preparation, 'cantidad_requerida': component['cantidad'],
            })
    return resolved, None


def _notify_cocina_event(event_name, pedido, actor_user):
    # Se imprime la comanda física solo al pasar el pedido a "en preparación"
    # (cocina confirma que arranca a cocinarlo), no al registrarlo. No debe
    # depender de que el canal de WebSocket esté disponible: se intenta
    # siempre, aunque channel_layer sea None.
    if event_name == 'PEDIDO_ACTUALIZADO' and pedido.estado == 'en_preparacion':
        try:
            imprimir_comandas_pedido(pedido)
        except Exception:
            logger.exception('Fallo al imprimir comandas para pedido %s', pedido.id)

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
            logger.exception('Fallo al enviar alerta WhatsApp para pedido %s', pedido.id)


def _notify_usuario_event(event_name, pedido, actor_user):
    """Avisa por el grupo personal del mesero dueño del pedido (ej: cocina lo marcó listo)."""
    channel_layer = get_channel_layer()
    if channel_layer is None or not pedido.usuario_id:
        return

    payload = {
        'event': event_name,
        'pedido_id': pedido.id,
        'mesa': pedido.mesa.numero if pedido.mesa else None,
        'estado': pedido.estado,
        'tipo_pedido': pedido.tipo_pedido,
        'actor': actor_user.username,
        'actor_role': _get_role_name(actor_user),
    }

    async_to_sync(channel_layer.group_send)(
        f'usuario_{pedido.usuario_id}_notifications',
        {
            'type': 'usuario_order_notification',
            'payload': payload,
        },
    )


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


def _compute_addon_sale_price(costo_unitario, margen_ganancia):
    """Precio de venta de un adicional: costo_unitario + margen_ganancia% de ganancia sobre ese costo."""
    margen = margen_ganancia if margen_ganancia is not None else Decimal('0')
    precio = costo_unitario * (Decimal('1') + margen / Decimal('100'))
    return precio.quantize(Decimal('0.01'))


def _compute_preparation_cost_map(components_by_preparation, ingredient_costs, yields_by_preparation):
    """
    Costea cada VGPreparacion sumando (cantidad_requerida x costo) de sus ingredientes y
    sub-preparaciones, resolviendo el árbol de forma recursiva y memoizada. Si una
    sub-preparación se referencia a sí misma indirectamente (ciclo), esa rama se costea en 0
    en vez de recursar infinitamente.

    components_by_preparation: {prep_id: [{'tipo': 'ingrediente'|'sub_preparacion', 'referencia_id': int, 'cantidad': Decimal}, ...]}
    ingredient_costs: {ingrediente_id: Decimal costo_unitario}
    yields_by_preparation: {prep_id: Decimal rendimiento_cantidad}

    Devuelve {prep_id: {'costo_total': Decimal, 'costo_unitario': Decimal}} para cada preparación conocida.
    """
    results = {}
    resolving = set()

    def resolve(prep_id):
        if prep_id in results:
            return results[prep_id]
        if prep_id in resolving:
            return {'costo_total': Decimal('0'), 'costo_unitario': Decimal('0')}
        resolving.add(prep_id)

        total = Decimal('0')
        for component in components_by_preparation.get(prep_id, []):
            if component['tipo'] == 'ingrediente':
                total += component['cantidad'] * ingredient_costs.get(component['referencia_id'], Decimal('0'))
            else:
                total += component['cantidad'] * resolve(component['referencia_id'])['costo_unitario']

        rendimiento = yields_by_preparation.get(prep_id) or Decimal('1')
        unit_cost = (total / rendimiento) if rendimiento > 0 else Decimal('0')
        result = {'costo_total': total, 'costo_unitario': unit_cost}
        results[prep_id] = result
        resolving.discard(prep_id)
        return result

    for prep_id in set(components_by_preparation.keys()) | set(yields_by_preparation.keys()):
        resolve(prep_id)

    return results


def _load_preparation_structure():
    """
    Consulta VGRecetaPreparacion/VGPreparacion y arma la estructura del árbol de subrecetas,
    compartida por el costeo (_load_preparation_cost_map) y el descuento de inventario al cobrar
    (_compute_pedido_ingredient_needs).

    Devuelve (components_by_preparation, yields_by_preparation).
    """
    components_by_preparation = {}
    for component in VGRecetaPreparacion.objects.all():
        preparation_id = component.preparacion_id
        components_by_preparation.setdefault(preparation_id, [])
        if component.ingrediente_id:
            components_by_preparation[preparation_id].append({
                'tipo': 'ingrediente',
                'referencia_id': component.ingrediente_id,
                'cantidad': component.cantidad_requerida,
            })
        elif component.sub_preparacion_id:
            components_by_preparation[preparation_id].append({
                'tipo': 'sub_preparacion',
                'referencia_id': component.sub_preparacion_id,
                'cantidad': component.cantidad_requerida,
            })

    yields_by_preparation = dict(VGPreparacion.objects.values_list('id', 'rendimiento_cantidad'))
    return components_by_preparation, yields_by_preparation


def _load_preparation_cost_map():
    """Consulta VGRecetaPreparacion/VGIngrediente/VGPreparacion y devuelve el costo calculado de cada subreceta."""
    components_by_preparation, yields_by_preparation = _load_preparation_structure()
    ingredient_costs = dict(VGIngrediente.objects.values_list('id', 'costo_unitario'))
    return _compute_preparation_cost_map(components_by_preparation, ingredient_costs, yields_by_preparation)


def _product_recipe_components(product):
    """
    Componentes (ingrediente o subreceta) que se descuentan al vender 1 unidad de `product`.
    Si el producto está vinculado a una receta o a una subreceta (receta_vinculada /
    subreceta_vinculada), usa los componentes de esa receta/subreceta en vez de su propia tabla
    `receta`, que para productos vinculados está vacía — así una misma receta maestra puede
    venderse bajo varios productos (ej. distintas presentaciones o precios) sin duplicarla.
    """
    if product.receta_vinculada_id:
        source = product.receta_vinculada.receta.all()
        return [
            {
                'tipo': 'ingrediente' if component.ingrediente_id else 'preparacion',
                'referencia_id': component.ingrediente_id or component.preparacion_id,
                'cantidad': component.cantidad_requerida,
            }
            for component in source
        ]
    if product.subreceta_vinculada_id:
        source = product.subreceta_vinculada.componentes.all()
        return [
            {
                'tipo': 'ingrediente' if component.ingrediente_id else 'preparacion',
                'referencia_id': component.ingrediente_id or component.sub_preparacion_id,
                'cantidad': component.cantidad_requerida,
            }
            for component in source
        ]
    return [
        {
            'tipo': 'ingrediente' if component.ingrediente_id else 'preparacion',
            'referencia_id': component.ingrediente_id or component.preparacion_id,
            'cantidad': component.cantidad_requerida,
        }
        for component in product.receta.all()
    ]


def _add_preparation_needs(prep_id, quantity_needed, components_by_preparation, yields_by_preparation, needs, resolving):
    """
    Descompone `quantity_needed` unidades de la subreceta `prep_id` en ingredientes crudos,
    prorrateando cada componente por rendimiento_cantidad (ej: si el plato lleva 200g de una
    salsa cuyo lote rinde 1000g, se descuenta 1/5 de cada ingrediente de esa salsa), y
    recursando en sub-subrecetas anidadas. Acumula el resultado en `needs`
    ({ingrediente_id: Decimal}). Si hay un ciclo, esa rama se ignora en vez de recursar infinito.
    """
    if prep_id in resolving:
        return
    resolving.add(prep_id)

    rendimiento = yields_by_preparation.get(prep_id) or Decimal('1')
    factor = (quantity_needed / rendimiento) if rendimiento > 0 else Decimal('0')
    for component in components_by_preparation.get(prep_id, []):
        amount = factor * component['cantidad']
        if component['tipo'] == 'ingrediente':
            needs[component['referencia_id']] = needs.get(component['referencia_id'], Decimal('0')) + amount
        else:
            _add_preparation_needs(
                component['referencia_id'], amount, components_by_preparation, yields_by_preparation, needs, resolving,
            )

    resolving.discard(prep_id)


def _compute_pedido_ingredient_needs(pedido, components_by_preparation, yields_by_preparation):
    """
    Cuánto de cada VGIngrediente hay que descontar del inventario al cobrar `pedido`: recorre
    cada línea (VGDetallePedido), sus adicionales (VGDetallePedidoAdicional) y sus opciones
    elegidas (VGDetallePedidoOpcion, ej. "Acompañante: Arepas"), expandiendo recetas/subrecetas
    hasta llegar a ingredientes crudos.

    Devuelve {ingrediente_id: Decimal cantidad}.
    """
    needs = {}
    for detalle in pedido.detalles.all():
        peso_factor = (detalle.peso_gramos / Decimal('1000')) if detalle.peso_gramos else Decimal('1')
        cantidad_platos = Decimal(detalle.cantidad) * peso_factor
        for component in _product_recipe_components(detalle.producto):
            amount = component['cantidad'] * cantidad_platos
            if component['tipo'] == 'ingrediente':
                needs[component['referencia_id']] = needs.get(component['referencia_id'], Decimal('0')) + amount
            else:
                _add_preparation_needs(
                    component['referencia_id'], amount, components_by_preparation, yields_by_preparation, needs, set(),
                )

        for addon in detalle.adicionales.all():
            _add_preparation_needs(
                addon.preparacion_id, Decimal(addon.cantidad),
                components_by_preparation, yields_by_preparation, needs, set(),
            )

        for opcion in detalle.opciones.all():
            _add_preparation_needs(
                opcion.preparacion_id, cantidad_platos,
                components_by_preparation, yields_by_preparation, needs, set(),
            )

    return needs


def _compute_product_recipe_cost(product, preparation_cost_map):
    """Costea un VGProducto (receta) sumando (cantidad_requerida x costo) de sus ingredientes y subrecetas."""
    total = Decimal('0')
    for component in product.receta.all():
        if component.ingrediente_id:
            ingredient_cost = component.ingrediente.costo_unitario if component.ingrediente else Decimal('0')
            total += component.cantidad_requerida * ingredient_cost
        elif component.preparacion_id:
            costs = preparation_cost_map.get(component.preparacion_id, {'costo_unitario': Decimal('0')})
            total += component.cantidad_requerida * costs['costo_unitario']
    return total


def _compute_product_unit_cost(product, ingredient_costs, preparation_cost_map):
    """
    Costea 1 unidad vendible de `product` (o 1 kg si es venta_por_peso, mismo
    criterio que _compute_pedido_ingredient_needs) usando _product_recipe_components
    — a diferencia de _compute_product_recipe_cost, sí resuelve productos vinculados
    a una receta/subreceta (receta_vinculada/subreceta_vinculada), cuya tabla propia
    `receta` está vacía.
    """
    total = Decimal('0')
    for component in _product_recipe_components(product):
        if component['tipo'] == 'ingrediente':
            total += component['cantidad'] * ingredient_costs.get(component['referencia_id'], Decimal('0'))
        else:
            costs = preparation_cost_map.get(component['referencia_id'], {'costo_unitario': Decimal('0')})
            total += component['cantidad'] * costs['costo_unitario']
    return total


def _snapshot_costo_venta_detalles(pedido, ingredient_costs, preparation_cost_map, unit_cost_cache=None):
    """
    Congela en cada VGDetallePedido de `pedido` el costo de receta por unidad
    (VGDetallePedido.costo_unitario_venta) usando los costos de ingredientes
    VIGENTES en este momento. Se llama justo en el momento del cobro —el mismo
    punto donde ya se descuenta inventario en pedidos_cobro_view / _emitir_factura—
    para que el margen de ganancia de una venta ya cobrada no cambie después si
    sube o baja el costo de un ingrediente. `unit_cost_cache` es opcional, para
    reusar costos ya calculados entre pedidos de un mismo cobro combinado.
    """
    if unit_cost_cache is None:
        unit_cost_cache = {}
    detalles = list(pedido.detalles.all())
    for detalle in detalles:
        if detalle.producto_id not in unit_cost_cache:
            unit_cost_cache[detalle.producto_id] = _compute_product_unit_cost(
                detalle.producto, ingredient_costs, preparation_cost_map,
            )
        detalle.costo_unitario_venta = unit_cost_cache[detalle.producto_id]
    if detalles:
        VGDetallePedido.objects.bulk_update(detalles, ['costo_unitario_venta'])


def reporte_margen_ganancia_view(request):
    """
    Margen de ganancia por plato vendido en un rango de fechas: cuánto entró
    (precio de venta x cantidad), cuánto costó y la ganancia resultante,
    agrupado por producto. Usa el costo histórico congelado al momento del
    cobro (VGDetallePedido.costo_unitario_venta, ver _snapshot_costo_venta_detalles)
    cuando existe; para ventas de antes de que ese campo existiera (o cualquier
    fila vieja sin snapshot), cae al costo_unitario ACTUAL de los ingredientes
    como estimación — mismo criterio "último costo" que el reporte de
    referencia (Profit Plus) — y esa fila queda marcada con 'costo_estimado':
    true para que quede claro que no es un costo histórico real.
    """
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    desde_raw = request.GET.get('desde')
    hasta_raw = request.GET.get('hasta')
    try:
        desde = date.fromisoformat(desde_raw) if desde_raw else timezone.localdate()
        hasta = date.fromisoformat(hasta_raw) if hasta_raw else timezone.localdate()
    except ValueError:
        return _auth_response({'ok': False, 'message': 'Las fechas no son validas.'}, status=400)
    if desde > hasta:
        return _auth_response({'ok': False, 'message': '"Desde" no puede ser posterior a "Hasta".'}, status=400)

    detalles = (
        VGDetallePedido.objects
        .filter(
            pedido__estado='pagado',
            pedido__fecha_creacion__date__gte=desde,
            pedido__fecha_creacion__date__lte=hasta,
        )
        .select_related('producto__categoria')
    )

    ingredient_costs = dict(VGIngrediente.objects.values_list('id', 'costo_unitario'))
    preparation_cost_map = _load_preparation_cost_map()
    unit_cost_cache = {}

    filas_por_producto = {}
    for detalle in detalles:
        producto = detalle.producto
        peso_factor = (detalle.peso_gramos / Decimal('1000')) if detalle.peso_gramos else Decimal('1')
        cantidad_equivalente = Decimal(detalle.cantidad) * peso_factor

        if detalle.costo_unitario_venta is not None:
            costo_unitario = detalle.costo_unitario_venta
            es_estimado = False
        else:
            if producto.id not in unit_cost_cache:
                unit_cost_cache[producto.id] = _compute_product_unit_cost(producto, ingredient_costs, preparation_cost_map)
            costo_unitario = unit_cost_cache[producto.id]
            es_estimado = True

        fila = filas_por_producto.setdefault(producto.id, {
            'producto_id': producto.id,
            'nombre': producto.nombre,
            'categoria': producto.categoria.nombre if producto.categoria_id else '',
            'venta_por_peso': producto.venta_por_peso,
            'cantidad_vendida': Decimal('0'),
            'ingreso_total': Decimal('0'),
            'costo_total': Decimal('0'),
            'costo_estimado': False,
        })
        fila['cantidad_vendida'] += cantidad_equivalente
        fila['ingreso_total'] += detalle.subtotal
        fila['costo_total'] += costo_unitario * cantidad_equivalente
        if es_estimado:
            fila['costo_estimado'] = True

    filas = []
    total_ingreso = Decimal('0')
    total_costo = Decimal('0')
    for fila in filas_por_producto.values():
        ganancia_monto = fila['ingreso_total'] - fila['costo_total']
        ganancia_pct = (ganancia_monto / fila['ingreso_total'] * Decimal('100')) if fila['ingreso_total'] > 0 else Decimal('0')
        total_ingreso += fila['ingreso_total']
        total_costo += fila['costo_total']
        filas.append({
            'producto_id': fila['producto_id'],
            'nombre': fila['nombre'],
            'categoria': fila['categoria'],
            'cantidad_vendida': str(fila['cantidad_vendida'].quantize(Decimal('0.01'))),
            'unidad': 'kg' if fila['venta_por_peso'] else 'unidad',
            'ingreso_total': str(fila['ingreso_total'].quantize(Decimal('0.01'))),
            'costo_total': str(fila['costo_total'].quantize(Decimal('0.01'))),
            'ganancia_monto': str(ganancia_monto.quantize(Decimal('0.01'))),
            'ganancia_pct': str(ganancia_pct.quantize(Decimal('0.01'))),
            'costo_estimado': fila['costo_estimado'],
        })

    filas.sort(key=lambda item: Decimal(item['ingreso_total']), reverse=True)

    total_ganancia = total_ingreso - total_costo
    total_ganancia_pct = (total_ganancia / total_ingreso * Decimal('100')) if total_ingreso > 0 else Decimal('0')

    return _auth_response({
        'ok': True,
        'desde': desde.isoformat(),
        'hasta': hasta.isoformat(),
        'platos': filas,
        'totales': {
            'ingreso_total': str(total_ingreso.quantize(Decimal('0.01'))),
            'costo_total': str(total_costo.quantize(Decimal('0.01'))),
            'ganancia_monto': str(total_ganancia.quantize(Decimal('0.01'))),
            'ganancia_pct': str(total_ganancia_pct.quantize(Decimal('0.01'))),
        },
    })


class MesaListView(generics.ListAPIView):
    queryset = VGMesa.objects.all().order_by('numero')
    serializer_class = MesaSerializer


class ProductoListView(generics.ListAPIView):
    queryset = (
        VGProducto.objects.filter(disponible=True)
        .select_related('categoria')
        .prefetch_related(
            'receta_vinculada__receta__ingrediente',
            'receta_vinculada__receta__preparacion',
            'subreceta_vinculada__componentes__ingrediente',
            'subreceta_vinculada__componentes__sub_preparacion',
            'grupos_opciones__opciones__preparacion',
        )
        .order_by('nombre')
    )
    serializer_class = ProductoSerializer


def adicionales_disponibles_view(request):
    """Catálogo de subrecetas marcadas como adicional, con su precio de venta ya calculado, para que el mesero las ofrezca en cualquier plato."""
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    preparation_cost_map = _load_preparation_cost_map()
    adicionales = []
    for preparation in VGPreparacion.objects.filter(es_adicional=True).order_by('nombre'):
        costo_unitario = preparation_cost_map.get(preparation.id, {'costo_unitario': Decimal('0')})['costo_unitario']
        adicionales.append({
            'id': preparation.id,
            'nombre': preparation.nombre,
            'unidad': preparation.rendimiento_unidad,
            'precio': str(_compute_addon_sale_price(costo_unitario, preparation.margen_ganancia)),
        })

    return _auth_response({'ok': True, 'adicionales': adicionales})


def _resolve_opciones_linea(product, grupos, opciones_seleccionadas):
    """
    Valida las opciones elegidas para una línea de pedido de `product` contra
    sus VGGrupoOpcionProducto (grupos propios de ESE producto, ej. "Acompañante"
    con Arepas/Casabe) — distinto de los adicionales globales (es_adicional=True).
    Revisa que cada grupo obligatorio tenga al menos una opción elegida, que un
    grupo sin selección múltiple no reciba más de una, y que cada opción elegida
    pertenezca al grupo indicado. Devuelve (opciones_resueltas, error_message);
    opciones_resueltas es [{'grupo_nombre': str, 'opcion': VGOpcionProducto}, ...].
    """
    opciones_validas_por_grupo = {
        grupo.id: {opcion.preparacion_id: opcion for opcion in grupo.opciones.all()}
        for grupo in grupos
    }

    seleccion_por_grupo = {}
    for seleccion in opciones_seleccionadas:
        grupo_id = seleccion['grupo_id']
        if grupo_id not in opciones_validas_por_grupo:
            return None, f'"{product.nombre}" no tiene ese grupo de opciones.'
        opciones_del_grupo = opciones_validas_por_grupo[grupo_id]
        if seleccion['preparacion_id'] not in opciones_del_grupo:
            return None, f'Esa opción no pertenece al grupo indicado para "{product.nombre}".'
        seleccion_por_grupo.setdefault(grupo_id, []).append(opciones_del_grupo[seleccion['preparacion_id']])

    resueltas = []
    for grupo in grupos:
        elegidas = seleccion_por_grupo.get(grupo.id, [])
        if grupo.obligatorio and not elegidas:
            return None, f'Debes elegir una opción de "{grupo.nombre}" para "{product.nombre}".'
        if not grupo.seleccion_multiple and len(elegidas) > 1:
            return None, f'Solo puedes elegir una opción de "{grupo.nombre}" para "{product.nombre}".'
        for opcion in elegidas:
            resueltas.append({'grupo_nombre': grupo.nombre, 'opcion': opcion})

    return resueltas, None


def _parse_order_payload(data):
    """Valida cabecera + items de un pedido. Compartido entre alta y edición."""
    items = data.get('items', [])
    if not isinstance(items, list) or len(items) == 0:
        return None, 'Debes enviar al menos un item en el pedido.'

    tipo_pedido = str(data.get('tipo_pedido', 'local')).strip().lower()
    tipo_keys = {tipo for tipo, _ in VGPedido.TIPOS}
    if tipo_pedido not in tipo_keys:
        return None, 'Tipo de pedido invalido.'

    mesa = None
    mesa_id = data.get('mesa_id')
    if mesa_id not in [None, '']:
        try:
            mesa = VGMesa.objects.get(pk=int(mesa_id))
        except (ValueError, TypeError, VGMesa.DoesNotExist):
            return None, 'La mesa seleccionada no existe.'

    try:
        impuesto = Decimal(str(data.get('impuesto', '0') or '0'))
        descuento = Decimal(str(data.get('descuento', '0') or '0'))
        propina = Decimal(str(data.get('propina', '0') or '0'))
    except InvalidOperation:
        return None, 'Hay montos invalidos en impuesto, descuento o propina.'

    parsed_lines = []
    product_ids = []
    preparacion_ids = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            return None, f'El item #{index} tiene formato invalido.'

        raw_product_id = item.get('product_id')
        try:
            product_id = int(raw_product_id)
        except (TypeError, ValueError):
            return None, f'El item #{index} no tiene producto valido.'

        raw_quantity = item.get('cantidad', 1)
        try:
            quantity = int(raw_quantity)
        except (TypeError, ValueError):
            return None, f'La cantidad del item #{index} es invalida.'

        if quantity <= 0:
            return None, f'La cantidad del item #{index} debe ser mayor a cero.'

        peso_gramos = None
        raw_peso_gramos = item.get('peso_gramos')
        if raw_peso_gramos not in [None, '']:
            try:
                peso_gramos = Decimal(str(raw_peso_gramos))
            except InvalidOperation:
                return None, f'El peso del item #{index} es invalido.'
            if peso_gramos <= 0:
                return None, f'El peso del item #{index} debe ser mayor a cero.'

        grupo_armado = None
        raw_grupo_armado = item.get('grupo_armado')
        if raw_grupo_armado not in [None, '']:
            try:
                grupo_armado = int(raw_grupo_armado)
            except (TypeError, ValueError):
                return None, f'El grupo del item #{index} es invalido.'
            if grupo_armado <= 0:
                return None, f'El grupo del item #{index} debe ser mayor a cero.'

        notes = str(item.get('notas', '') or '').strip()

        raw_addons = item.get('adicionales') or []
        if not isinstance(raw_addons, list):
            return None, f'Los adicionales del item #{index} tienen formato invalido.'

        parsed_addons = []
        for addon_index, addon in enumerate(raw_addons, start=1):
            if not isinstance(addon, dict):
                return None, f'Un adicional del item #{index} tiene formato invalido.'
            try:
                addon_preparacion_id = int(addon.get('preparacion_id'))
            except (TypeError, ValueError):
                return None, f'El adicional #{addon_index} del item #{index} no tiene subreceta valida.'
            try:
                addon_quantity = int(addon.get('cantidad', 1))
            except (TypeError, ValueError):
                return None, f'La cantidad del adicional #{addon_index} del item #{index} es invalida.'
            if addon_quantity <= 0:
                return None, f'La cantidad del adicional #{addon_index} del item #{index} debe ser mayor a cero.'
            parsed_addons.append({'preparacion_id': addon_preparacion_id, 'cantidad': addon_quantity})
            preparacion_ids.append(addon_preparacion_id)

        raw_opciones = item.get('opciones') or []
        if not isinstance(raw_opciones, list):
            return None, f'Las opciones del item #{index} tienen formato invalido.'
        parsed_opciones = []
        for opcion_index, opcion in enumerate(raw_opciones, start=1):
            if not isinstance(opcion, dict):
                return None, f'Una opción del item #{index} tiene formato invalido.'
            try:
                opcion_grupo_id = int(opcion.get('grupo_id'))
                opcion_preparacion_id = int(opcion.get('preparacion_id'))
            except (TypeError, ValueError):
                return None, f'Una opción del item #{index} no es valida.'
            parsed_opciones.append({'grupo_id': opcion_grupo_id, 'preparacion_id': opcion_preparacion_id})

        parsed_lines.append({
            'product_id': product_id,
            'cantidad': quantity,
            'peso_gramos': peso_gramos,
            'grupo_armado': grupo_armado,
            'notas': notes,
            'adicionales': parsed_addons,
            'opciones': parsed_opciones,
        })
        product_ids.append(product_id)

    products_map = {
        product.id: product
        for product in VGProducto.objects.filter(id__in=product_ids, disponible=True)
    }
    preparaciones_map = {
        preparacion.id: preparacion
        for preparacion in VGPreparacion.objects.filter(id__in=preparacion_ids, es_adicional=True)
    }

    grupos_opciones_by_producto = {}
    for index, line in enumerate(parsed_lines, start=1):
        if line['product_id'] not in products_map:
            return None, f'El producto del item #{index} no existe o no esta disponible.'
        product = products_map[line['product_id']]
        if product.venta_por_peso and not line['peso_gramos']:
            return None, f'Debes indicar el peso (gramos) del item #{index}, "{product.nombre}" se vende por peso.'
        if not product.venta_por_peso:
            line['peso_gramos'] = None
        for addon in line['adicionales']:
            if addon['preparacion_id'] not in preparaciones_map:
                return None, f'Un adicional del item #{index} no existe o ya no esta disponible como adicional.'

        if product.id not in grupos_opciones_by_producto:
            grupos_opciones_by_producto[product.id] = list(
                VGGrupoOpcionProducto.objects.filter(producto=product).prefetch_related('opciones__preparacion')
            )
        grupos = grupos_opciones_by_producto[product.id]
        opciones_resueltas, error = _resolve_opciones_linea(product, grupos, line['opciones'])
        if error:
            return None, f'Item #{index}: {error}'
        line['opciones_resueltas'] = opciones_resueltas

    return {
        'parsed_lines': parsed_lines,
        'products_map': products_map,
        'preparaciones_map': preparaciones_map,
        'tipo_pedido': tipo_pedido,
        'mesa': mesa,
        'impuesto': impuesto,
        'descuento': descuento,
        'propina': propina,
    }, None


def _build_order_lines(parsed_lines, products_map, preparaciones_map):
    """
    Aplica promociones activas y calcula el precio de cada adicional (server-side, nunca
    confiando en lo que mande el cliente) para armar las lineas listas para guardar.
    Devuelve (lineas, subtotal).
    """
    active_promotions = _active_promotions_by_product(list(products_map.keys()))
    preparation_cost_map = _load_preparation_cost_map()
    subtotal = Decimal('0')
    built_lines = []
    for line in parsed_lines:
        product = products_map[line['product_id']]
        promotion = active_promotions.get(product.id)
        unit_price = _compute_discounted_price(product.precio_venta, promotion) if promotion else product.precio_venta
        peso_factor = (line['peso_gramos'] / Decimal('1000')) if product.venta_por_peso and line['peso_gramos'] else Decimal('1')
        line_subtotal = unit_price * peso_factor * line['cantidad']

        built_addons = []
        for addon in line['adicionales']:
            preparation = preparaciones_map[addon['preparacion_id']]
            costo_unitario = preparation_cost_map.get(preparation.id, {'costo_unitario': Decimal('0')})['costo_unitario']
            addon_price = _compute_addon_sale_price(costo_unitario, preparation.margen_ganancia)
            line_subtotal += addon_price * addon['cantidad']
            built_addons.append({
                'preparacion': preparation,
                'cantidad': addon['cantidad'],
                'precio_unitario': addon_price,
            })

        built_opciones = []
        for resuelta in line.get('opciones_resueltas', []):
            opcion = resuelta['opcion']
            precio_opcion_total = (opcion.precio_adicional * peso_factor * line['cantidad']).quantize(Decimal('0.01'))
            line_subtotal += precio_opcion_total
            built_opciones.append({
                'grupo_nombre': resuelta['grupo_nombre'],
                'preparacion': opcion.preparacion,
                'precio_unitario': precio_opcion_total,
            })

        subtotal += line_subtotal
        built_lines.append({
            'producto': product,
            'cantidad': line['cantidad'],
            'precio_unitario': unit_price,
            'peso_gramos': line['peso_gramos'],
            'grupo_armado': line['grupo_armado'],
            'notas': line['notas'],
            'adicionales': built_addons,
            'opciones': built_opciones,
        })
    return built_lines, subtotal


def _serialize_detalle_adicionales(detalle):
    return [
        {
            'id': adicional.id,
            'preparacion_id': adicional.preparacion_id,
            'nombre': adicional.preparacion.nombre,
            'cantidad': adicional.cantidad,
            'precio_unitario': str(adicional.precio_unitario),
            'subtotal': str(adicional.subtotal),
        }
        for adicional in detalle.adicionales.all()
    ]


def _serialize_detalle_opciones(detalle):
    return [
        {
            'id': opcion.id,
            'grupo_nombre': opcion.grupo_nombre,
            'preparacion_id': opcion.preparacion_id,
            'nombre': opcion.preparacion.nombre,
            'precio_unitario': str(opcion.precio_unitario),
            'subtotal': str(opcion.subtotal),
        }
        for opcion in detalle.opciones.all()
    ]


def _serialize_order_detail(pedido):
    return {
        'id': pedido.id,
        'estado': pedido.estado,
        'tipo_pedido': pedido.tipo_pedido,
        'mesa_id': pedido.mesa_id,
        'mesa': pedido.mesa.numero if pedido.mesa else None,
        'cliente_nombre': pedido.cliente.nombre if pedido.cliente else '',
        'notas': pedido.notas,
        'impuesto': str(pedido.impuesto),
        'descuento': str(pedido.descuento),
        'propina': str(pedido.propina),
        'subtotal': str(pedido.subtotal),
        'total': str(pedido.total),
        'items': [
            {
                'id': detalle.id,
                'product_id': detalle.producto_id,
                'producto_nombre': detalle.producto.nombre,
                'cantidad': detalle.cantidad,
                'precio_unitario': str(detalle.precio_unitario),
                'peso_gramos': str(detalle.peso_gramos) if detalle.peso_gramos is not None else None,
                'grupo_armado': detalle.grupo_armado,
                'venta_por_peso': detalle.producto.venta_por_peso,
                'subtotal': str(detalle.subtotal),
                'notas': detalle.notas,
                'adicionales': _serialize_detalle_adicionales(detalle),
                'opciones': _serialize_detalle_opciones(detalle),
            }
            for detalle in pedido.detalles.all()
        ],
    }


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

    parsed, error = _parse_order_payload(data)
    if error:
        return _auth_response({'ok': False, 'message': error}, status=400)

    cliente = None
    cliente_nombre = str(data.get('cliente_nombre', '') or '').strip()
    if cliente_nombre:
        cliente, _ = VGCliente.objects.get_or_create(nombre=cliente_nombre)

    notas = str(data.get('notas', '') or '').strip()

    with transaction.atomic():
        pedido = VGPedido.objects.create(
            mesa=parsed['mesa'],
            usuario=request.user,
            cliente=cliente,
            tipo_pedido=parsed['tipo_pedido'],
            estado='pendiente',
            notas=notas,
            impuesto=parsed['impuesto'],
            descuento=parsed['descuento'],
            propina=parsed['propina'],
            creado_por=request.user,
            actualizado_por=request.user,
        )

        built_lines, subtotal = _build_order_lines(parsed['parsed_lines'], parsed['products_map'], parsed['preparaciones_map'])
        for line in built_lines:
            detalle = VGDetallePedido.objects.create(
                pedido=pedido,
                producto=line['producto'],
                cantidad=line['cantidad'],
                precio_unitario=line['precio_unitario'],
                peso_gramos=line['peso_gramos'],
                grupo_armado=line['grupo_armado'],
                estado='pendiente',
                notas=line['notas'],
            )
            for addon in line['adicionales']:
                VGDetallePedidoAdicional.objects.create(
                    detalle_pedido=detalle,
                    preparacion=addon['preparacion'],
                    cantidad=addon['cantidad'],
                    precio_unitario=addon['precio_unitario'],
                )
            for opcion in line['opciones']:
                VGDetallePedidoOpcion.objects.create(
                    detalle_pedido=detalle,
                    grupo_nombre=opcion['grupo_nombre'],
                    preparacion=opcion['preparacion'],
                    precio_unitario=opcion['precio_unitario'],
                )

        total = subtotal + parsed['impuesto'] + parsed['propina'] - parsed['descuento']
        pedido.subtotal = subtotal
        pedido.total = total
        pedido.actualizado_por = request.user
        pedido.save(update_fields=['subtotal', 'total', 'actualizado_por'])

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
                'items': len(parsed['parsed_lines']),
            },
        },
        status=201,
    )


def pedido_detail_view(request, pedido_id):
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not request.user.is_authenticated:
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion.'}, status=401)

    try:
        pedido = (
            VGPedido.objects
            .select_related('mesa', 'cliente')
            .prefetch_related('detalles__producto', 'detalles__adicionales__preparacion', 'detalles__opciones__preparacion')
            .get(pk=pedido_id)
        )
    except VGPedido.DoesNotExist:
        return _auth_response({'ok': False, 'message': 'El pedido no existe.'}, status=404)

    return _auth_response({'ok': True, 'pedido': _serialize_order_detail(pedido)})


@csrf_exempt
def pedido_update_view(request, pedido_id):
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not request.user.is_authenticated:
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion para editar pedidos.'}, status=401)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    parsed, error = _parse_order_payload(data)
    if error:
        return _auth_response({'ok': False, 'message': error}, status=400)

    cliente = None
    cliente_nombre = str(data.get('cliente_nombre', '') or '').strip()
    if cliente_nombre:
        cliente, _ = VGCliente.objects.get_or_create(nombre=cliente_nombre)

    notas = str(data.get('notas', '') or '').strip()

    with transaction.atomic():
        try:
            pedido = VGPedido.objects.select_for_update().get(pk=pedido_id)
        except VGPedido.DoesNotExist:
            return _auth_response({'ok': False, 'message': 'El pedido no existe.'}, status=404)

        if pedido.estado != 'pendiente':
            return _auth_response(
                {'ok': False, 'message': 'Solo se pueden editar pedidos en estado pendiente. Este pedido ya avanzó a cocina.'},
                status=409,
            )

        pedido.mesa = parsed['mesa']
        pedido.tipo_pedido = parsed['tipo_pedido']
        pedido.cliente = cliente
        pedido.notas = notas
        pedido.impuesto = parsed['impuesto']
        pedido.descuento = parsed['descuento']
        pedido.propina = parsed['propina']

        pedido.detalles.all().delete()

        built_lines, subtotal = _build_order_lines(parsed['parsed_lines'], parsed['products_map'], parsed['preparaciones_map'])
        for line in built_lines:
            detalle = VGDetallePedido.objects.create(
                pedido=pedido,
                producto=line['producto'],
                cantidad=line['cantidad'],
                precio_unitario=line['precio_unitario'],
                peso_gramos=line['peso_gramos'],
                grupo_armado=line['grupo_armado'],
                estado='pendiente',
                notas=line['notas'],
            )
            for addon in line['adicionales']:
                VGDetallePedidoAdicional.objects.create(
                    detalle_pedido=detalle,
                    preparacion=addon['preparacion'],
                    cantidad=addon['cantidad'],
                    precio_unitario=addon['precio_unitario'],
                )
            for opcion in line['opciones']:
                VGDetallePedidoOpcion.objects.create(
                    detalle_pedido=detalle,
                    grupo_nombre=opcion['grupo_nombre'],
                    preparacion=opcion['preparacion'],
                    precio_unitario=opcion['precio_unitario'],
                )

        total = subtotal + parsed['impuesto'] + parsed['propina'] - parsed['descuento']
        pedido.subtotal = subtotal
        pedido.total = total
        pedido.actualizado_por = request.user
        pedido.save()

    pedido = VGPedido.objects.select_related('mesa', 'cliente').prefetch_related('detalles__producto', 'detalles__adicionales__preparacion', 'detalles__opciones__preparacion').get(pk=pedido.id)
    _notify_cocina_event('PEDIDO_ACTUALIZADO', pedido, request.user)

    return _auth_response({
        'ok': True,
        'message': 'Pedido actualizado correctamente.',
        'pedido': _serialize_order_detail(pedido),
    })


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
        preparation_cost_map = _load_preparation_cost_map()
        recipes = []
        for preparation in VGPreparacion.objects.order_by('-fecha_creacion', 'nombre').values(
            'id', 'nombre', 'rendimiento_cantidad', 'rendimiento_unidad', 'es_adicional', 'margen_ganancia',
        ):
            components = recipe_components_by_preparation.get(preparation['id'], [])
            costs = preparation_cost_map.get(preparation['id'], {'costo_total': Decimal('0'), 'costo_unitario': Decimal('0')})
            costo_unitario = costs['costo_unitario']
            recipes.append({
                **preparation,
                'componentes': components,
                'componentes_total': len(components),
                'costo_total': str(costs['costo_total'].quantize(Decimal('0.01'))),
                'costo_unitario_calculado': str(costo_unitario.quantize(Decimal('0.01'))),
                'precio_venta_calculado': (
                    str(_compute_addon_sale_price(costo_unitario, preparation['margen_ganancia']))
                    if preparation['es_adicional'] else None
                ),
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
        es_adicional = bool(data.get('es_adicional', False))

        try:
            rendimiento = Decimal(str(rendimiento_cantidad))
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'El rendimiento de la subreceta es inválido.'}, status=400)

        if rendimiento <= 0:
            return _auth_response({'ok': False, 'message': 'El rendimiento debe ser mayor a cero.'}, status=400)

        margen_ganancia = None
        if es_adicional:
            try:
                margen_ganancia = Decimal(str(data.get('margen_ganancia', '0') or '0'))
            except InvalidOperation:
                return _auth_response({'ok': False, 'message': 'El margen de ganancia es inválido.'}, status=400)
            if margen_ganancia < 0:
                return _auth_response({'ok': False, 'message': 'El margen de ganancia no puede ser negativo.'}, status=400)

        if VGPreparacion.objects.filter(nombre__iexact=nombre).exists():
            return _auth_response({'ok': False, 'message': 'Ya existe una subreceta con ese nombre.'}, status=400)

        with transaction.atomic():
            preparation = VGPreparacion.objects.create(
                nombre=nombre,
                rendimiento_cantidad=rendimiento,
                rendimiento_unidad=rendimiento_unidad,
                es_adicional=es_adicional,
                margen_ganancia=margen_ganancia,
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
        es_adicional = bool(data.get('es_adicional', preparation.es_adicional))

        try:
            rendimiento = Decimal(str(rendimiento_cantidad))
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'El rendimiento de la subreceta es inválido.'}, status=400)

        if rendimiento <= 0:
            return _auth_response({'ok': False, 'message': 'El rendimiento debe ser mayor a cero.'}, status=400)

        margen_ganancia = None
        if es_adicional:
            try:
                margen_ganancia = Decimal(str(data.get('margen_ganancia', preparation.margen_ganancia or '0') or '0'))
            except InvalidOperation:
                return _auth_response({'ok': False, 'message': 'El margen de ganancia es inválido.'}, status=400)
            if margen_ganancia < 0:
                return _auth_response({'ok': False, 'message': 'El margen de ganancia no puede ser negativo.'}, status=400)

        if VGPreparacion.objects.filter(nombre__iexact=nombre).exclude(pk=preparation.pk).exists():
            return _auth_response({'ok': False, 'message': 'Ya existe otra subreceta con ese nombre.'}, status=400)

        with transaction.atomic():
            preparation.nombre = nombre
            preparation.rendimiento_cantidad = rendimiento
            preparation.rendimiento_unidad = rendimiento_unidad
            preparation.es_adicional = es_adicional
            preparation.margen_ganancia = margen_ganancia
            preparation.actualizado_por = request.user
            preparation.save(update_fields=['nombre', 'rendimiento_cantidad', 'rendimiento_unidad', 'es_adicional', 'margen_ganancia', 'actualizado_por', 'fecha_actualizacion'])

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
        numero_factura_proveedor = str(data.get('numero_factura_proveedor', '') or '').strip()
        fecha_factura_raw = str(data.get('fecha_factura', '') or '').strip()
        fecha_factura = None
        if fecha_factura_raw:
            try:
                fecha_factura = date.fromisoformat(fecha_factura_raw)
            except ValueError:
                return _auth_response({'ok': False, 'message': 'La fecha de la factura no es valida.'}, status=400)
        cantidad = data.get('cantidad', 0)
        stock_minimo = data.get('stock_minimo', 0)
        precio_total = data.get('precio_total', 0)
        try:
            cantidad_value = Decimal(str(cantidad))
            stock_minimo_value = Decimal(str(stock_minimo or 0))
            precio_total_value = Decimal(str(precio_total or 0))
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'Los datos numéricos del insumo son inválidos.'}, status=400)

        if cantidad_value <= 0:
            return _auth_response({'ok': False, 'message': 'La cantidad del ingreso debe ser mayor a cero.'}, status=400)

        # El costo unitario nunca se recibe precalculado: se deriva siempre del precio
        # total pagado dividido entre la cantidad realmente recibida, para que
        # presentaciones no redondas (ej. potes de 910 g) queden bien costeadas.
        costo_unitario_value = (precio_total_value / cantidad_value).quantize(Decimal('0.0001'))

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

            total_compra = precio_total_value
            compra = VGCompra.objects.create(
                proveedor_nombre=proveedor,
                numero_factura_proveedor=numero_factura_proveedor,
                fecha_factura=fecha_factura,
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
                compra=compra,
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


MAX_INGREDIENTES_IMPORT_SIZE_BYTES = 5 * 1024 * 1024


def _preview_ingrediente_row(row):
    """
    Clasifica una fila ya parseada del Excel (ver ingredientes_excel.parse_ingredientes_workbook)
    contra el inventario actual, sin tocar la base de datos — es lo que ve el analista en la
    pantalla de "mapeo"/revisión antes de confirmar la importación.
    """
    nombre = row['nombre']
    unidad_normalizada = normalize_unidad(row['unidad'])
    cantidad, error_cantidad = parse_cantidad(row['cantidad'])
    precio_total, error_precio = parse_precio_total(row.get('precio_total'))
    ingrediente = VGIngrediente.objects.filter(nombre__iexact=nombre).first()

    resultado = {
        'fila': row['fila'],
        'nombre': nombre,
        'unidad': unidad_normalizada or row['unidad'],
        'cantidad': str(cantidad) if cantidad is not None else row['cantidad'],
        'precio_total': str(precio_total) if precio_total is not None else (row.get('precio_total') or ''),
        'ingrediente_id': ingrediente.id if ingrediente else None,
        'stock_actual': str(ingrediente.stock_actual) if ingrediente else None,
        'unidad_actual': ingrediente.unidad_medida if ingrediente else None,
    }

    if error_precio:
        resultado['accion'] = 'error'
        resultado['mensaje'] = error_precio
    elif error_cantidad:
        resultado['accion'] = 'error'
        resultado['mensaje'] = error_cantidad
    elif cantidad == 0:
        resultado['accion'] = 'ignorado'
        resultado['mensaje'] = 'Cantidad vacía o en 0: no se toca este ingrediente.'
    elif ingrediente is not None:
        if cantidad == ingrediente.stock_actual:
            resultado['accion'] = 'sin_cambios'
            resultado['mensaje'] = 'El stock ya coincide, no hay nada que actualizar.'
        else:
            resultado['accion'] = 'actualizar'
            resultado['mensaje'] = ''
    elif not unidad_normalizada:
        resultado['accion'] = 'error'
        resultado['mensaje'] = 'Ingrediente nuevo: falta una unidad válida (kg, g, l, ml o unidad).'
    else:
        resultado['accion'] = 'nuevo'
        resultado['mensaje'] = ''

    return resultado


def _importar_ingredientes(items, operator, proveedor_nombre='', numero_factura_proveedor='', fecha_factura=None):
    """
    Aplica la carga de ingredientes ya revisada/editada por el analista (ver
    _preview_ingrediente_row): por cada fila, si el ingrediente existe se actualiza su
    stock_actual y se registra un movimiento de 'ajuste' con el delta; si no existe se
    crea con ese stock inicial y se registra un movimiento de 'entrada'. Cantidad vacía o
    en 0 se ignora — mismo criterio que sync_inventario_pesaje (management command).

    La parte de "cantidad" (sincronizar el stock al valor de la planilla) se comporta
    exactamente igual que antes — no se toca ese comportamiento para no romper el uso de
    esta pantalla como reconteo físico. Lo nuevo: cuando una fila resulta en un aumento de
    stock (ingrediente nuevo, o existente cuyo delta es positivo), esa porción SÍ se
    registra como una compra real — un único VGCompra (el "lote") para todo el archivo,
    con un VGDetalleCompra por cada fila que aumentó stock, costeado con precio_total/
    cantidad_agregada si se dio un precio (mismo criterio que el alta manual de un
    ingrediente). Si ninguna fila aumenta stock, no se crea ningún VGCompra.
    """
    creados, actualizados, ignorados = 0, 0, 0
    errores = []
    compra = None

    def _obtener_compra():
        nonlocal compra
        if compra is None:
            compra = VGCompra.objects.create(
                proveedor_nombre=proveedor_nombre or 'Sin proveedor',
                numero_factura_proveedor=numero_factura_proveedor,
                fecha_factura=fecha_factura,
                estado='recibido',
                creado_por=operator,
                actualizado_por=operator,
            )
        return compra

    with transaction.atomic():
        for item in items:
            nombre = str(item.get('nombre', '') or '').strip()
            if not nombre:
                continue

            cantidad, error_cantidad = parse_cantidad(item.get('cantidad'))
            if error_cantidad:
                errores.append(f'{nombre}: {error_cantidad}')
                continue
            if cantidad == 0:
                ignorados += 1
                continue

            precio_total, error_precio = parse_precio_total(item.get('precio_total'))
            if error_precio:
                errores.append(f'{nombre}: {error_precio}')
                continue

            ingrediente = VGIngrediente.objects.filter(nombre__iexact=nombre).first()
            if ingrediente is not None:
                if cantidad == ingrediente.stock_actual:
                    continue
                stock_anterior = ingrediente.stock_actual
                delta = cantidad - stock_anterior
                ingrediente.stock_actual = cantidad
                update_fields = ['stock_actual', 'actualizado_por', 'fecha_actualizacion']
                if delta > 0 and precio_total is not None:
                    ingrediente.costo_unitario = (precio_total / delta).quantize(Decimal('0.0001'))
                    update_fields.append('costo_unitario')
                ingrediente.actualizado_por = operator
                ingrediente.save(update_fields=update_fields)

                movimiento_compra = None
                if delta > 0:
                    lote = _obtener_compra()
                    costo_linea = (precio_total / delta).quantize(Decimal('0.0001')) if precio_total is not None else Decimal('0')
                    VGDetalleCompra.objects.create(
                        compra=lote, ingrediente=ingrediente, cantidad=delta, costo_unitario=costo_linea,
                    )
                    lote.total = lote.total + (delta * costo_linea)
                    lote.save(update_fields=['total'])
                    movimiento_compra = lote

                VGMovimientoInventario.objects.create(
                    ingrediente=ingrediente,
                    tipo_movimiento='entrada' if movimiento_compra else 'ajuste',
                    cantidad=delta,
                    motivo=f'Carga por Excel: {stock_anterior} -> {cantidad} {ingrediente.unidad_medida}',
                    compra=movimiento_compra,
                    creado_por=operator,
                )
                actualizados += 1
            else:
                unidad_normalizada = normalize_unidad(item.get('unidad'))
                if not unidad_normalizada:
                    errores.append(f'{nombre}: falta una unidad válida (kg, g, l, ml o unidad) para crearlo.')
                    continue
                costo_inicial = (precio_total / cantidad).quantize(Decimal('0.0001')) if precio_total is not None else Decimal('0')
                nuevo = VGIngrediente.objects.create(
                    nombre=nombre,
                    unidad_medida=unidad_normalizada,
                    stock_actual=cantidad,
                    stock_minimo=Decimal('0'),
                    costo_unitario=costo_inicial,
                    creado_por=operator,
                    actualizado_por=operator,
                )
                lote = _obtener_compra()
                VGDetalleCompra.objects.create(
                    compra=lote, ingrediente=nuevo, cantidad=cantidad, costo_unitario=costo_inicial,
                )
                lote.total = lote.total + (cantidad * costo_inicial)
                lote.save(update_fields=['total'])
                VGMovimientoInventario.objects.create(
                    ingrediente=nuevo,
                    tipo_movimiento='entrada',
                    cantidad=cantidad,
                    motivo='Carga inicial por Excel (importación de ingredientes)',
                    compra=lote,
                    creado_por=operator,
                )
                creados += 1

    return {
        'creados': creados, 'actualizados': actualizados, 'ignorados': ignorados, 'errores': errores,
        'compra_id': compra.id if compra else None,
    }


@csrf_exempt
def admin_ingredientes_import_view(request):
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    is_multipart = bool(request.content_type) and request.content_type.startswith('multipart/form-data')
    if is_multipart:
        action = str(request.POST.get('action', '')).strip().lower()
        data = {}
    else:
        try:
            data = json.loads(request.body.decode('utf-8')) if request.body else {}
        except json.JSONDecodeError:
            return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)
        action = str(data.get('action', '')).strip().lower()

    if action == 'preview':
        uploaded_file = request.FILES.get('archivo')
        if uploaded_file is None:
            return _auth_response({'ok': False, 'message': 'Debes adjuntar un archivo .xlsx.'}, status=400)
        if uploaded_file.size > MAX_INGREDIENTES_IMPORT_SIZE_BYTES:
            return _auth_response({'ok': False, 'message': 'El archivo no debe superar los 5MB.'}, status=400)

        try:
            filas = parse_ingredientes_workbook(uploaded_file)
        except InvalidExcelError as error:
            return _auth_response({'ok': False, 'message': str(error)}, status=400)

        if not filas:
            return _auth_response({'ok': False, 'message': 'El archivo no tiene filas de ingredientes para importar.'}, status=400)

        return _auth_response({'ok': True, 'filas': [_preview_ingrediente_row(row) for row in filas]})

    if action == 'confirm':
        items = data.get('items')
        if not isinstance(items, list) or not items:
            return _auth_response({'ok': False, 'message': 'No hay filas para importar.'}, status=400)

        proveedor_nombre = str(data.get('proveedor_nombre', '') or '').strip()
        numero_factura_proveedor = str(data.get('numero_factura_proveedor', '') or '').strip()
        fecha_factura_raw = str(data.get('fecha_factura', '') or '').strip()
        fecha_factura = None
        if fecha_factura_raw:
            try:
                fecha_factura = date.fromisoformat(fecha_factura_raw)
            except ValueError:
                return _auth_response({'ok': False, 'message': 'La fecha de la factura no es valida.'}, status=400)

        resumen = _importar_ingredientes(
            items, request.user,
            proveedor_nombre=proveedor_nombre,
            numero_factura_proveedor=numero_factura_proveedor,
            fecha_factura=fecha_factura,
        )
        return _auth_response({'ok': True, **resumen})

    return _auth_response({'ok': False, 'message': 'Accion invalida.'}, status=400)


def _serialize_compra(compra, incluir_detalle=False):
    data = {
        'id': compra.id,
        'proveedor_nombre': compra.proveedor_nombre,
        'numero_factura_proveedor': compra.numero_factura_proveedor,
        'fecha_factura': compra.fecha_factura.isoformat() if compra.fecha_factura else None,
        'fecha_creacion': compra.fecha_creacion.isoformat(),
        'total': str(compra.total),
        'estado': compra.estado,
        'creado_por': (compra.creado_por.get_full_name() or compra.creado_por.username) if compra.creado_por else '',
        'cantidad_items': compra.detalles.count() if incluir_detalle else None,
    }
    if incluir_detalle:
        data['detalles'] = [
            {
                'id': detalle.id,
                'ingrediente_id': detalle.ingrediente_id,
                'ingrediente_nombre': detalle.ingrediente.nombre,
                'unidad_medida': detalle.ingrediente.unidad_medida,
                'cantidad': str(detalle.cantidad),
                'costo_unitario': str(detalle.costo_unitario),
                'subtotal': str(detalle.subtotal),
            }
            for detalle in compra.detalles.select_related('ingrediente').all()
        ]
    return data


def admin_compras_view(request):
    """Historial de lotes de compra (VGCompra): de qué proveedor/factura vino cada carga de inventario."""
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    compras = VGCompra.objects.select_related('creado_por').prefetch_related('detalles').order_by('-fecha_creacion')
    return _auth_response({
        'ok': True,
        'compras': [_serialize_compra(compra, incluir_detalle=True) for compra in compras[:200]],
    })


def compra_detail_view(request, compra_id):
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    try:
        compra = VGCompra.objects.select_related('creado_por').prefetch_related('detalles__ingrediente').get(pk=compra_id)
    except VGCompra.DoesNotExist:
        return _auth_response({'ok': False, 'message': 'El lote de compra no existe.'}, status=404)

    return _auth_response({'ok': True, 'compra': _serialize_compra(compra, incluir_detalle=True)})


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


def _serialize_mesa(mesa):
    return MesaSerializer(mesa).data


@csrf_exempt
def admin_mesas_view(request):
    if request.method not in ['GET', 'POST']:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    if request.method == 'GET':
        mesas = VGMesa.objects.all().order_by('numero')
        return _auth_response({
            'ok': True,
            'mesas': [_serialize_mesa(mesa) for mesa in mesas],
            'estados': [{'value': value, 'label': label} for value, label in VGMesa.ESTADOS],
        })

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    action = str(data.get('action', '')).strip().lower()

    if action == 'delete':
        mesa_id = data.get('id')
        try:
            mesa = VGMesa.objects.get(pk=int(mesa_id))
        except (ValueError, TypeError, VGMesa.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'La mesa a eliminar no existe.'}, status=400)

        mesa.delete()
        return _auth_response({'ok': True, 'message': 'Mesa eliminada correctamente.'})

    if action not in {'create', 'update'}:
        return _auth_response({'ok': False, 'message': 'Accion de mesas invalida.'}, status=400)

    numero = data.get('numero')
    capacidad = data.get('capacidad')
    ubicacion = str(data.get('ubicacion', '') or '').strip()
    estado = str(data.get('estado', '') or 'libre').strip().lower()

    try:
        numero = int(numero)
        if numero <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return _auth_response({'ok': False, 'message': 'El número de mesa debe ser un entero positivo.'}, status=400)

    if capacidad in [None, '']:
        capacidad = 4
    try:
        capacidad = int(capacidad)
        if capacidad <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return _auth_response({'ok': False, 'message': 'La capacidad debe ser un entero positivo.'}, status=400)

    valid_estados = {value for value, _ in VGMesa.ESTADOS}
    if estado not in valid_estados:
        return _auth_response({'ok': False, 'message': 'El estado de la mesa no es válido.'}, status=400)

    mesa = None
    if action == 'update':
        mesa_id = data.get('id')
        try:
            mesa = VGMesa.objects.get(pk=int(mesa_id))
        except (ValueError, TypeError, VGMesa.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'La mesa a editar no existe.'}, status=400)

    numero_query = VGMesa.objects.filter(numero=numero)
    if mesa is not None:
        numero_query = numero_query.exclude(pk=mesa.pk)
    if numero_query.exists():
        return _auth_response({'ok': False, 'message': 'Ya existe una mesa con ese número.'}, status=400)

    if action == 'create':
        mesa = VGMesa.objects.create(
            numero=numero,
            capacidad=capacidad,
            ubicacion=ubicacion,
            estado=estado,
            creado_por=request.user,
        )
        message = 'Mesa creada correctamente.'
    else:
        mesa.numero = numero
        mesa.capacidad = capacidad
        mesa.ubicacion = ubicacion
        mesa.estado = estado
        mesa.actualizado_por = request.user
        mesa.save()
        message = 'Mesa actualizada correctamente.'

    return _auth_response({
        'ok': True,
        'message': message,
        'mesa': _serialize_mesa(mesa),
    }, status=201 if action == 'create' else 200)


def _serialize_categoria_impresora(categoria):
    return {
        'id': categoria.id,
        'nombre': categoria.nombre,
        'ip_impresora': categoria.ip_impresora,
        'puerto_impresora': categoria.puerto_impresora,
    }


@csrf_exempt
def admin_categorias_view(request):
    """Asigna qué impresora térmica (IP:puerto en la LAN) imprime las comandas de cada categoría."""
    if request.method not in ['GET', 'POST']:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    if request.method == 'GET':
        categorias = VGCategoriaProducto.objects.order_by('nombre')
        return _auth_response({
            'ok': True,
            'categorias': [_serialize_categoria_impresora(categoria) for categoria in categorias],
        })

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    action = str(data.get('action', '')).strip().lower()
    if action != 'update':
        return _auth_response({'ok': False, 'message': 'Accion de categorias invalida.'}, status=400)

    categoria_id = data.get('id')
    try:
        categoria = VGCategoriaProducto.objects.get(pk=int(categoria_id))
    except (ValueError, TypeError, VGCategoriaProducto.DoesNotExist):
        return _auth_response({'ok': False, 'message': 'La categoría no existe.'}, status=400)

    ip_impresora = str(data.get('ip_impresora', '') or '').strip()
    if ip_impresora:
        try:
            ipaddress.ip_address(ip_impresora)
        except ValueError:
            return _auth_response({'ok': False, 'message': 'La IP de la impresora no es válida.'}, status=400)

    puerto_raw = data.get('puerto_impresora', categoria.puerto_impresora)
    try:
        puerto_impresora = int(puerto_raw)
    except (TypeError, ValueError):
        return _auth_response({'ok': False, 'message': 'El puerto de la impresora no es válido.'}, status=400)
    if not (1 <= puerto_impresora <= 65535):
        return _auth_response({'ok': False, 'message': 'El puerto debe estar entre 1 y 65535.'}, status=400)

    categoria.ip_impresora = ip_impresora
    categoria.puerto_impresora = puerto_impresora
    categoria.actualizado_por = request.user
    categoria.save(update_fields=['ip_impresora', 'puerto_impresora', 'actualizado_por', 'fecha_actualizacion'])

    return _auth_response({
        'ok': True,
        'message': 'Impresora asignada correctamente.',
        'categoria': _serialize_categoria_impresora(categoria),
    })


def _serialize_impresora_caja(config):
    return {
        'ip': config.ip if config else '',
        'puerto': config.puerto if config else 515,
        'cola': config.cola if config else '',
        'activo': config.activo if config else False,
    }


@csrf_exempt
def admin_impresora_caja_view(request):
    """
    Configura la impresora de caja (recibo del cliente al cobrar) — no es por categoría
    como las de cocina, es una sola impresora USB compartida vía LPD desde la PC de caja
    (ver impresion_lpd.py). Fila única (singleton): siempre se lee/edita la primera.
    """
    if request.method not in ['GET', 'POST']:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    if request.method == 'GET':
        return _auth_response({'ok': True, 'impresora_caja': _serialize_impresora_caja(VGImpresoraCaja.obtener_config())})

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    ip = str(data.get('ip', '') or '').strip()
    if ip:
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            return _auth_response({'ok': False, 'message': 'La IP de la impresora no es válida.'}, status=400)

    try:
        puerto = int(data.get('puerto', 515))
    except (TypeError, ValueError):
        return _auth_response({'ok': False, 'message': 'El puerto no es válido.'}, status=400)
    if not (1 <= puerto <= 65535):
        return _auth_response({'ok': False, 'message': 'El puerto debe estar entre 1 y 65535.'}, status=400)

    cola = str(data.get('cola', '') or '').strip()
    activo = bool(data.get('activo'))

    if activo and (not ip or not cola):
        return _auth_response(
            {'ok': False, 'message': 'Para activar la impresora de caja necesitas indicar IP y nombre de cola.'},
            status=400,
        )

    config = VGImpresoraCaja.obtener_config()
    if config is None:
        config = VGImpresoraCaja(creado_por=request.user)
    config.ip = ip
    config.puerto = puerto
    config.cola = cola
    config.activo = activo
    config.actualizado_por = request.user
    config.save()

    return _auth_response({
        'ok': True,
        'message': 'Impresora de caja guardada correctamente.',
        'impresora_caja': _serialize_impresora_caja(config),
    })


ALLOWED_PRODUCT_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'gif'}
MAX_PRODUCT_IMAGE_SIZE_BYTES = 5 * 1024 * 1024


def _save_product_image(uploaded_file):
    safe_name = get_valid_filename(uploaded_file.name)
    extension = safe_name.rsplit('.', 1)[-1].lower() if '.' in safe_name else ''
    if extension not in ALLOWED_PRODUCT_IMAGE_EXTENSIONS:
        raise ValueError('Formato de imagen no permitido. Usa JPG, PNG, WEBP o GIF.')
    if uploaded_file.size > MAX_PRODUCT_IMAGE_SIZE_BYTES:
        raise ValueError('La imagen no debe superar los 5MB.')

    # default_storage.save agrega un sufijo automaticamente si el nombre ya existe,
    # asi que dos productos nunca pueden pisarse el archivo de imagen entre si.
    saved_path = default_storage.save(f'productos/{safe_name}', uploaded_file)
    return default_storage.url(saved_path)


def _delete_product_image(image_url):
    if not image_url:
        return

    relative_path = image_url
    media_url = settings.MEDIA_URL or '/media/'
    if relative_path.startswith(media_url):
        relative_path = relative_path[len(media_url):]

    try:
        if default_storage.exists(relative_path):
            default_storage.delete(relative_path)
    except Exception:
        pass


def _product_image_url(product):
    """
    URL publica de la imagen del producto, con la fecha de actualizacion como
    query param. El endpoint es siempre /api/productos/<id>/imagen/ sin importar
    el archivo real, asi que sin este "cache-bust" el navegador (y el
    Cache-Control de product_image_view) siguen sirviendo la imagen vieja
    despues de reemplazarla.
    """
    if not product.imagen_url:
        return ''
    version = int(product.fecha_actualizacion.timestamp()) if product.fecha_actualizacion else 0
    return f'/api/productos/{product.id}/imagen/?v={version}'


def _serialize_product_category(category):
    return {
        'id': category.id,
        'nombre': category.nombre,
    }


def _serialize_product(product):
    return {
        'id': product.id,
        'nombre': product.nombre,
        'descripcion': product.descripcion,
        'categoria_id': product.categoria_id,
        'categoria_nombre': product.categoria.nombre if product.categoria else '',
        'precio_venta': str(product.precio_venta),
        'costo_estimado': str(product.costo_estimado) if product.costo_estimado is not None else '',
        'disponible': product.disponible,
        'venta_por_peso': product.venta_por_peso,
        'tiempo_preparacion_min': product.tiempo_preparacion_min,
        'imagen_url': _product_image_url(product),
        'receta_vinculada_id': product.receta_vinculada_id,
        'receta_vinculada_nombre': product.receta_vinculada.nombre if product.receta_vinculada_id else '',
        'subreceta_vinculada_id': product.subreceta_vinculada_id,
        'subreceta_vinculada_nombre': product.subreceta_vinculada.nombre if product.subreceta_vinculada_id else '',
        'ingredientes': [_serialize_recipe_component(component) for component in product.receta.all()],
        'grupos_opciones': [
            {
                'id': grupo.id,
                'nombre': grupo.nombre,
                'obligatorio': grupo.obligatorio,
                'seleccion_multiple': grupo.seleccion_multiple,
                'opciones': [
                    {
                        'id': opcion.id,
                        'preparacion_id': opcion.preparacion_id,
                        'preparacion_nombre': opcion.preparacion.nombre,
                        'precio_adicional': str(opcion.precio_adicional),
                    }
                    for opcion in grupo.opciones.all()
                ],
            }
            for grupo in product.grupos_opciones.all()
        ],
    }


def _resolve_media_path_from_url(image_url):
    if not image_url:
        return None

    media_url = settings.MEDIA_URL or '/media/'
    if not image_url.startswith(media_url):
        return None

    relative_path = image_url[len(media_url):].lstrip('/')
    media_root = Path(settings.MEDIA_ROOT).resolve()
    candidate = (media_root / relative_path).resolve()

    if media_root not in candidate.parents and candidate != media_root:
        return None
    return candidate


def product_image_view(request, product_id):
    try:
        product = VGProducto.objects.get(pk=int(product_id))
    except (ValueError, TypeError, VGProducto.DoesNotExist):
        raise Http404('Producto no encontrado.')

    file_path = _resolve_media_path_from_url(product.imagen_url)
    if file_path is None or not file_path.is_file():
        raise Http404('Imagen no disponible.')

    content_type, _ = mimetypes.guess_type(str(file_path))
    response = FileResponse(file_path.open('rb'), content_type=content_type or 'application/octet-stream')
    response['Cache-Control'] = 'public, max-age=3600'
    return response


def _parse_grupos_opciones(raw_grupos):
    """
    Valida el payload de grupos de opciones de un producto (ver admin_products_view):
    [{"nombre": str, "obligatorio": bool, "seleccion_multiple": bool,
      "opciones": [{"preparacion_id": int, "precio_adicional": str}, ...]}, ...]
    Cada opción se apoya en una VGPreparacion ya existente. Devuelve
    (grupos_parseados, error_message); cada grupo trae sus opciones ya
    resueltas a objetos VGPreparacion, listas para crear en bulk.
    """
    if not isinstance(raw_grupos, list):
        return None, 'Formato inválido de grupos de opciones.'

    preparacion_ids = set()
    parsed_grupos = []
    for grupo_index, grupo in enumerate(raw_grupos, start=1):
        if not isinstance(grupo, dict):
            return None, f'El grupo de opciones #{grupo_index} tiene formato inválido.'
        nombre = str(grupo.get('nombre', '') or '').strip()
        if not nombre:
            return None, f'El grupo de opciones #{grupo_index} necesita un nombre.'
        obligatorio = bool(grupo.get('obligatorio', True))
        seleccion_multiple = bool(grupo.get('seleccion_multiple', False))
        raw_opciones = grupo.get('opciones') or []
        if not isinstance(raw_opciones, list) or not raw_opciones:
            return None, f'El grupo "{nombre}" necesita al menos una opción.'

        parsed_opciones = []
        for opcion in raw_opciones:
            if not isinstance(opcion, dict):
                return None, f'Una opción del grupo "{nombre}" tiene formato inválido.'
            try:
                preparacion_id = int(opcion.get('preparacion_id'))
            except (TypeError, ValueError):
                return None, f'Una opción del grupo "{nombre}" no tiene una subreceta válida.'
            try:
                precio_adicional = Decimal(str(opcion.get('precio_adicional', '0') or '0'))
            except InvalidOperation:
                return None, f'El precio de una opción del grupo "{nombre}" no es válido.'
            if precio_adicional < 0:
                return None, f'El precio de una opción del grupo "{nombre}" no puede ser negativo.'
            parsed_opciones.append({'preparacion_id': preparacion_id, 'precio_adicional': precio_adicional})
            preparacion_ids.add(preparacion_id)

        parsed_grupos.append({
            'nombre': nombre,
            'obligatorio': obligatorio,
            'seleccion_multiple': seleccion_multiple,
            'opciones': parsed_opciones,
        })

    preparaciones_map = {
        preparacion.id: preparacion for preparacion in VGPreparacion.objects.filter(id__in=preparacion_ids)
    }
    for grupo in parsed_grupos:
        for opcion in grupo['opciones']:
            preparacion = preparaciones_map.get(opcion['preparacion_id'])
            if preparacion is None:
                return None, f'Una de las subrecetas elegidas para "{grupo["nombre"]}" no existe.'
            opcion['preparacion'] = preparacion

    return parsed_grupos, None


@csrf_exempt
def admin_products_view(request):
    if request.method not in ['GET', 'POST']:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    if request.method == 'GET':
        VGCategoriaProducto.objects.get_or_create(
            nombre='Otros',
            defaults={'descripcion': 'Productos que no encajan en ninguna otra categoría.'},
        )
        categories = VGCategoriaProducto.objects.exclude(nombre__iexact='Recetas').order_by('nombre')
        products = (
            VGProducto.objects.exclude(categoria__nombre__iexact='Recetas')
            .select_related('categoria', 'receta_vinculada', 'subreceta_vinculada')
            .prefetch_related('receta__ingrediente', 'receta__preparacion', 'grupos_opciones__opciones__preparacion')
            .order_by('nombre')
        )
        preparation_cost_map = _load_preparation_cost_map()
        ingredients = list(
            VGIngrediente.objects.order_by('nombre').values('id', 'nombre', 'unidad_medida', 'stock_actual', 'costo_unitario')
        )
        recetas = [
            {
                'id': receta.id,
                'nombre': receta.nombre,
                'costo_unitario_calculado': str(
                    _compute_product_recipe_cost(receta, preparation_cost_map).quantize(Decimal('0.01'))
                ),
            }
            for receta in (
                VGProducto.objects.filter(categoria__nombre__iexact='Recetas')
                .prefetch_related('receta__ingrediente', 'receta__preparacion')
                .order_by('nombre')
            )
        ]
        subrecetas = [
            {
                'id': preparation['id'],
                'nombre': preparation['nombre'],
                'costo_unitario_calculado': str(
                    preparation_cost_map.get(preparation['id'], {'costo_unitario': Decimal('0')})['costo_unitario']
                    .quantize(Decimal('0.01'))
                ),
            }
            for preparation in VGPreparacion.objects.order_by('nombre').values('id', 'nombre')
        ]
        return _auth_response({
            'ok': True,
            'products': [_serialize_product(product) for product in products],
            'categories': [_serialize_product_category(category) for category in categories],
            'recetas': recetas,
            'subrecetas': subrecetas,
            'ingredients': ingredients,
        })

    is_multipart = bool(request.content_type) and request.content_type.startswith('multipart/form-data')
    if is_multipart:
        data = request.POST
        uploaded_image = request.FILES.get('imagen')
    else:
        try:
            data = json.loads(request.body.decode('utf-8')) if request.body else {}
        except json.JSONDecodeError:
            return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)
        uploaded_image = None

    action = str(data.get('action', '')).strip().lower()

    if action == 'delete':
        product_id = data.get('id')
        try:
            product = VGProducto.objects.exclude(categoria__nombre__iexact='Recetas').get(pk=int(product_id))
        except (ValueError, TypeError, VGProducto.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'El producto a eliminar no existe.'}, status=400)

        _delete_product_image(product.imagen_url)
        product.delete()
        return _auth_response({'ok': True, 'message': 'Producto eliminado correctamente.'})

    if action not in {'create', 'update'}:
        return _auth_response({'ok': False, 'message': 'Accion de productos invalida.'}, status=400)

    nombre = str(data.get('nombre', '') or '').strip()
    descripcion = str(data.get('descripcion', '') or '').strip()
    categoria_id = data.get('categoria_id')
    precio_venta_raw = data.get('precio_venta')
    costo_estimado_raw = data.get('costo_estimado')
    disponible = str(data.get('disponible', 'true')).strip().lower() not in {'false', '0', ''}
    venta_por_peso = str(data.get('venta_por_peso', 'false')).strip().lower() not in {'false', '0', ''}
    tiempo_preparacion_raw = data.get('tiempo_preparacion_min') or 0

    if not nombre:
        return _auth_response({'ok': False, 'message': 'El nombre del producto es obligatorio.'}, status=400)

    if categoria_id in [None, '']:
        return _auth_response({'ok': False, 'message': 'Debes seleccionar una categoría para el producto.'}, status=400)
    try:
        categoria = VGCategoriaProducto.objects.exclude(nombre__iexact='Recetas').get(pk=int(categoria_id))
    except (ValueError, TypeError, VGCategoriaProducto.DoesNotExist):
        return _auth_response({'ok': False, 'message': 'La categoría seleccionada no existe.'}, status=400)

    try:
        precio_venta = Decimal(str(precio_venta_raw or '0'))
        if precio_venta < 0:
            raise InvalidOperation
    except InvalidOperation:
        return _auth_response({'ok': False, 'message': 'El precio de venta no es válido.'}, status=400)

    costo_estimado = None
    if costo_estimado_raw not in [None, '']:
        try:
            costo_estimado = Decimal(str(costo_estimado_raw))
            if costo_estimado < 0:
                raise InvalidOperation
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'El costo estimado no es válido.'}, status=400)

    try:
        tiempo_preparacion = int(tiempo_preparacion_raw)
        if tiempo_preparacion < 0:
            raise ValueError
    except (TypeError, ValueError):
        return _auth_response({'ok': False, 'message': 'El tiempo de preparación no es válido.'}, status=400)

    vinculo_tipo = str(data.get('vinculo_tipo', '') or '').strip().lower()
    vinculo_id = data.get('vinculo_id')
    receta_vinculada = None
    subreceta_vinculada = None
    if vinculo_tipo == 'receta':
        try:
            receta_vinculada = VGProducto.objects.filter(categoria__nombre__iexact='Recetas').get(pk=int(vinculo_id))
        except (ValueError, TypeError, VGProducto.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'La receta seleccionada no existe.'}, status=400)
    elif vinculo_tipo == 'subreceta':
        try:
            subreceta_vinculada = VGPreparacion.objects.get(pk=int(vinculo_id))
        except (ValueError, TypeError, VGPreparacion.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'La subreceta seleccionada no existe.'}, status=400)

    componentes_raw = data.get('componentes')
    if is_multipart:
        try:
            componentes = json.loads(componentes_raw) if componentes_raw else []
        except json.JSONDecodeError:
            return _auth_response({'ok': False, 'message': 'Formato inválido de ingredientes del producto.'}, status=400)
    else:
        componentes = componentes_raw or []

    if venta_por_peso:
        # En un producto que se vende por peso, la cantidad real la define el mesero al
        # tomar el pedido (peso_gramos), no el analista de antemano — el descuento ya
        # escala solo con ese peso (ver peso_factor en _compute_pedido_ingredient_needs).
        # Si el analista no especifica cantidad, se asume 1:1 con el peso vendido: el
        # caso típico de un producto que ES el ingrediente crudo (ej. un corte de carne).
        for raw_component in componentes:
            if isinstance(raw_component, dict) and not raw_component.get('cantidad'):
                raw_component['cantidad'] = '1'
                raw_component['unidad'] = None

    parsed_components, error = _parse_recipe_components(componentes, require_at_least_one=False)
    if error:
        return _auth_response({'ok': False, 'message': error}, status=400)

    if parsed_components and (receta_vinculada is not None or subreceta_vinculada is not None):
        return _auth_response({
            'ok': False,
            'message': 'No puedes vincular una receta/subreceta y agregar ingredientes propios al mismo tiempo. Elige una sola opción.',
        }, status=400)

    resolved_components, error = _resolve_recipe_components_for_save(parsed_components)
    if error:
        return _auth_response({'ok': False, 'message': error}, status=400)

    grupos_opciones_raw = data.get('grupos_opciones')
    if is_multipart:
        try:
            grupos_opciones_data = json.loads(grupos_opciones_raw) if grupos_opciones_raw else []
        except json.JSONDecodeError:
            return _auth_response({'ok': False, 'message': 'Formato inválido de las opciones del producto.'}, status=400)
    else:
        grupos_opciones_data = grupos_opciones_raw or []

    parsed_grupos_opciones, error = _parse_grupos_opciones(grupos_opciones_data)
    if error:
        return _auth_response({'ok': False, 'message': error}, status=400)

    product = None
    if action == 'update':
        product_id = data.get('id')
        try:
            product = VGProducto.objects.exclude(categoria__nombre__iexact='Recetas').get(pk=int(product_id))
        except (ValueError, TypeError, VGProducto.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'El producto a editar no existe.'}, status=400)

    eliminar_imagen = str(data.get('eliminar_imagen', 'false')).strip().lower() in {'true', '1'}

    imagen_url = product.imagen_url if product else ''
    if uploaded_image is not None:
        try:
            new_imagen_url = _save_product_image(uploaded_image)
        except ValueError as error:
            return _auth_response({'ok': False, 'message': str(error)}, status=400)
        if product is not None:
            _delete_product_image(product.imagen_url)
        imagen_url = new_imagen_url
    elif eliminar_imagen and product is not None and product.imagen_url:
        _delete_product_image(product.imagen_url)
        imagen_url = ''

    with transaction.atomic():
        if action == 'create':
            product = VGProducto.objects.create(
                nombre=nombre,
                descripcion=descripcion,
                categoria=categoria,
                precio_venta=precio_venta,
                costo_estimado=costo_estimado,
                imagen_url=imagen_url,
                disponible=disponible,
                venta_por_peso=venta_por_peso,
                tiempo_preparacion_min=tiempo_preparacion,
                receta_vinculada=receta_vinculada,
                subreceta_vinculada=subreceta_vinculada,
                creado_por=request.user,
                actualizado_por=request.user,
            )
            message = 'Producto creado correctamente.'
        else:
            product.nombre = nombre
            product.descripcion = descripcion
            product.categoria = categoria
            product.precio_venta = precio_venta
            product.costo_estimado = costo_estimado
            product.imagen_url = imagen_url
            product.disponible = disponible
            product.venta_por_peso = venta_por_peso
            product.tiempo_preparacion_min = tiempo_preparacion
            product.receta_vinculada = receta_vinculada
            product.subreceta_vinculada = subreceta_vinculada
            product.actualizado_por = request.user
            product.save()
            message = 'Producto actualizado correctamente.'

        product.receta.all().delete()
        VGRecetaProducto.objects.bulk_create([
            VGRecetaProducto(
                producto=product,
                ingrediente=row['ingrediente'],
                preparacion=row['preparacion'],
                cantidad_requerida=row['cantidad_requerida'],
            )
            for row in resolved_components
        ])

        product.grupos_opciones.all().delete()
        for orden, grupo_data in enumerate(parsed_grupos_opciones):
            grupo = VGGrupoOpcionProducto.objects.create(
                producto=product,
                nombre=grupo_data['nombre'],
                obligatorio=grupo_data['obligatorio'],
                seleccion_multiple=grupo_data['seleccion_multiple'],
                orden=orden,
            )
            VGOpcionProducto.objects.bulk_create([
                VGOpcionProducto(
                    grupo=grupo,
                    preparacion=opcion['preparacion'],
                    precio_adicional=opcion['precio_adicional'],
                    orden=opcion_orden,
                )
                for opcion_orden, opcion in enumerate(grupo_data['opciones'])
            ])

    return _auth_response({
        'ok': True,
        'message': message,
        'product': _serialize_product(product),
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
            VGIngrediente.objects.order_by('nombre').values('id', 'nombre', 'unidad_medida', 'stock_actual', 'costo_unitario')
        )
        preparation_cost_map = _load_preparation_cost_map()
        preparations = []
        for preparation in VGPreparacion.objects.order_by('nombre').values('id', 'nombre', 'rendimiento_unidad', 'rendimiento_cantidad'):
            costs = preparation_cost_map.get(preparation['id'], {'costo_unitario': Decimal('0')})
            preparations.append({**preparation, 'costo_unitario_calculado': str(costs['costo_unitario'].quantize(Decimal('0.01')))})

        recipe_payloads = []
        for recipe in recipes:
            payload = _serialize_recipe_product(recipe)
            payload['costo_calculado'] = str(_compute_product_recipe_cost(recipe, preparation_cost_map).quantize(Decimal('0.01')))
            recipe_payloads.append(payload)

        return _auth_response({
            'ok': True,
            'recipes': recipe_payloads,
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

    parsed_components, error = _parse_recipe_components(componentes, require_at_least_one=True)
    if error:
        return _auth_response({'ok': False, 'message': error}, status=400)

    resolved_components, error = _resolve_recipe_components_for_save(parsed_components)
    if error:
        return _auth_response({'ok': False, 'message': error}, status=400)

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
        VGRecetaProducto.objects.bulk_create([
            VGRecetaProducto(
                producto=recipe,
                ingrediente=row['ingrediente'],
                preparacion=row['preparacion'],
                cantidad_requerida=row['cantidad_requerida'],
            )
            for row in resolved_components
        ])

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
                    'imagen_url': _product_image_url(product),
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
            'imagen_url': _product_image_url(product),
            'precio_original': str(precio_original.quantize(Decimal('0.01'))),
            'precio_descuento': str(precio_descuento.quantize(Decimal('0.01'))),
            'porcentaje_descuento': str(porcentaje.quantize(Decimal('0.1'))),
            'fecha_fin': promotion.fecha_fin.isoformat() if promotion.fecha_fin else None,
        })

    return _auth_response({'ok': True, 'promotions': payload})


def tasa_cambio_view(request):
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not request.user.is_authenticated:
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion.'}, status=401)

    tasa_actual = obtener_tasa_actual()
    if tasa_actual is None:
        return _auth_response({'ok': False, 'message': 'La tasa de cambio no esta disponible por ahora.'}, status=503)

    return _auth_response({
        'ok': True,
        'tasa': str(tasa_actual.tasa),
        'fuente': tasa_actual.fuente,
        'fecha': tasa_actual.fecha.isoformat(),
        'fecha_actualizacion': tasa_actual.fecha_actualizacion.isoformat(),
    })


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
            'imagen_url': _product_image_url(recommendation.producto),
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
                    'imagen_url': (
                        _product_image_url(recommendation.producto) if recommendation.producto else ''
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
        .prefetch_related(
            'detalles__producto',
            'detalles__adicionales__preparacion',
            'detalles__opciones__preparacion',
            'detalles__producto__receta_vinculada__receta__ingrediente',
            'detalles__producto__receta_vinculada__receta__preparacion',
            'detalles__producto__subreceta_vinculada__componentes__ingrediente',
            'detalles__producto__subreceta_vinculada__componentes__sub_preparacion',
        )
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
                    'peso_gramos': str(detalle.peso_gramos) if detalle.peso_gramos is not None else None,
                    'grupo_armado': detalle.grupo_armado,
                    'venta_por_peso': detalle.producto.venta_por_peso,
                    'estado': detalle.estado,
                    'notas': detalle.notas,
                    'adicionales': _serialize_detalle_adicionales(detalle),
                    'opciones': _serialize_detalle_opciones(detalle),
                    'composicion': detalle.producto.nombres_composicion(),
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

    transitions = {
        'pendiente': {'en_preparacion', 'cancelado'},
        'en_preparacion': {'listo', 'cancelado'},
        'listo': {'entregado', 'en_preparacion'},
        'entregado': set(),
        'pagado': set(),
        'cancelado': set(),
    }

    with transaction.atomic():
        try:
            pedido = VGPedido.objects.select_for_update().prefetch_related('detalles').get(pk=pedido_id)
        except VGPedido.DoesNotExist:
            return _auth_response({'ok': False, 'message': 'El pedido no existe.'}, status=404)

        allowed_next = transitions.get(pedido.estado, set())
        if next_state not in allowed_next:
            return _auth_response(
                {'ok': False, 'message': f'No se puede cambiar de {pedido.estado} a {next_state}.'},
                status=400,
            )

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
    if next_state == 'listo':
        _notify_usuario_event('PEDIDO_LISTO', pedido, request.user)

    return _auth_response({
        'ok': True,
        'message': 'Estado actualizado correctamente.',
        'pedido': {
            'id': pedido.id,
            'estado': pedido.estado,
        },
    })


@csrf_exempt
def pedido_reimprimir_comanda_view(request, pedido_id):
    """Reimprime la comanda de cocina de un pedido a pedido del mesero/cocina, por ejemplo tras un fallo de impresora."""
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not request.user.is_authenticated:
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion para reimprimir comandas.'}, status=401)

    try:
        pedido = VGPedido.objects.prefetch_related('detalles').get(pk=pedido_id)
    except VGPedido.DoesNotExist:
        return _auth_response({'ok': False, 'message': 'El pedido no existe.'}, status=404)

    try:
        imprimir_comandas_pedido(pedido)
    except Exception:
        logger.exception('Fallo al reimprimir comandas para pedido %s', pedido.id)
        return _auth_response({'ok': False, 'message': 'No se pudo reimprimir la comanda. Revisa la impresora.'}, status=502)

    return _auth_response({'ok': True, 'message': 'Comanda reimpresa correctamente.'})


BILLABLE_ORDER_STATES = ['listo', 'entregado']


@csrf_exempt
def pedidos_cobro_view(request):
    if request.method not in ['GET', 'POST']:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not request.user.is_authenticated:
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion.'}, status=401)

    if request.method == 'GET':
        pedidos = (
            VGPedido.objects.filter(estado__in=BILLABLE_ORDER_STATES)
            .select_related('mesa', 'cliente', 'usuario')
            .prefetch_related('detalles__producto', 'detalles__adicionales__preparacion', 'detalles__opciones__preparacion')
            .order_by('mesa__numero', 'fecha_creacion')
        )
        return _auth_response({
            'ok': True,
            'pedidos': [
                {
                    'id': pedido.id,
                    'mesa_id': pedido.mesa_id,
                    'mesa': pedido.mesa.numero if pedido.mesa else None,
                    'tipo_pedido': pedido.tipo_pedido,
                    'estado': pedido.estado,
                    'cliente': pedido.cliente.nombre if pedido.cliente else '',
                    'mesero': pedido.usuario.username,
                    'notas': pedido.notas,
                    'subtotal': str(pedido.subtotal),
                    'impuesto': str(pedido.impuesto),
                    'descuento': str(pedido.descuento),
                    'propina': str(pedido.propina),
                    'total': str(pedido.total),
                    'creado_en': pedido.fecha_creacion.isoformat(),
                    'items': [
                        {
                            'id': detalle.id,
                            'producto': detalle.producto.nombre,
                            'cantidad': detalle.cantidad,
                            'precio_unitario': str(detalle.precio_unitario),
                            'peso_gramos': str(detalle.peso_gramos) if detalle.peso_gramos is not None else None,
                            'grupo_armado': detalle.grupo_armado,
                            'venta_por_peso': detalle.producto.venta_por_peso,
                            'subtotal': str(detalle.subtotal),
                            'notas': detalle.notas,
                            'adicionales': _serialize_detalle_adicionales(detalle),
                            'opciones': _serialize_detalle_opciones(detalle),
                        }
                        for detalle in pedido.detalles.all()
                    ],
                }
                for pedido in pedidos
            ],
        })

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    raw_ids = data.get('pedido_ids')
    if not isinstance(raw_ids, list) or len(raw_ids) == 0:
        return _auth_response({'ok': False, 'message': 'Debes seleccionar al menos un pedido para cobrar.'}, status=400)

    try:
        pedido_ids = sorted({int(raw_id) for raw_id in raw_ids})
    except (TypeError, ValueError):
        return _auth_response({'ok': False, 'message': 'Hay un pedido invalido en la selección.'}, status=400)

    try:
        metodo_pago = VGMetodoPago.objects.get(pk=int(data.get('metodo_pago_id')), activo=True)
    except (TypeError, ValueError, VGMetodoPago.DoesNotExist):
        return _auth_response({'ok': False, 'message': 'El metodo de pago es invalido.'}, status=400)

    referencia = f'COBRO-{timezone.now().strftime("%Y%m%d%H%M%S")}-{pedido_ids[0]}'

    with transaction.atomic():
        pedidos = list(
            VGPedido.objects.select_for_update()
            .filter(pk__in=pedido_ids)
            .prefetch_related(
                'detalles__producto__receta__ingrediente',
                'detalles__producto__receta__preparacion',
                'detalles__producto__receta_vinculada__receta__ingrediente',
                'detalles__producto__receta_vinculada__receta__preparacion',
                'detalles__producto__subreceta_vinculada__componentes__ingrediente',
                'detalles__producto__subreceta_vinculada__componentes__sub_preparacion',
                'detalles__adicionales__preparacion',
                'detalles__opciones__preparacion',
            )
        )
        found_ids = {pedido.id for pedido in pedidos}
        missing_ids = sorted(set(pedido_ids) - found_ids)
        if missing_ids:
            return _auth_response(
                {'ok': False, 'message': f'Los pedidos {missing_ids} no existen.'},
                status=400,
            )

        not_billable = sorted(pedido.id for pedido in pedidos if pedido.estado not in BILLABLE_ORDER_STATES)
        if not_billable:
            return _auth_response(
                {
                    'ok': False,
                    'message': f'Los pedidos {not_billable} ya no están listos para cobrar (revisa su estado actual).',
                },
                status=409,
            )

        components_by_preparation, yields_by_preparation = _load_preparation_structure()
        ingredient_costs = dict(VGIngrediente.objects.values_list('id', 'costo_unitario'))
        preparation_cost_map = _compute_preparation_cost_map(components_by_preparation, ingredient_costs, yields_by_preparation)
        unit_cost_cache = {}

        total_cobrado = Decimal('0')
        for pedido in pedidos:
            VGPago.objects.create(
                pedido=pedido,
                monto=pedido.total,
                metodo_pago=metodo_pago,
                referencia=referencia,
                estado='completado',
                creado_por=request.user,
            )
            pedido.estado = 'pagado'
            pedido.actualizado_por = request.user
            pedido.save(update_fields=['estado', 'actualizado_por', 'fecha_actualizacion'])
            total_cobrado += pedido.total

            _snapshot_costo_venta_detalles(pedido, ingredient_costs, preparation_cost_map, unit_cost_cache)

            needs = _compute_pedido_ingredient_needs(pedido, components_by_preparation, yields_by_preparation)
            if needs:
                ingredients_by_id = {
                    ingredient.id: ingredient
                    for ingredient in VGIngrediente.objects.select_for_update().filter(id__in=needs.keys())
                }
                for ingrediente_id, cantidad in needs.items():
                    ingredient = ingredients_by_id.get(ingrediente_id)
                    if ingredient is None or cantidad <= 0:
                        continue
                    ingredient.stock_actual = ingredient.stock_actual - cantidad
                    ingredient.save(update_fields=['stock_actual'])
                    VGMovimientoInventario.objects.create(
                        ingrediente=ingredient,
                        tipo_movimiento='salida',
                        cantidad=cantidad,
                        motivo=f'Venta — Pedido #{pedido.id}',
                        id_referencia=pedido.id,
                        creado_por=request.user,
                    )

    try:
        imprimir_recibo_caja(pedidos, metodo_pago, referencia, total_cobrado)
    except Exception:
        logger.exception('Fallo al imprimir el recibo de caja para el cobro %s', referencia)

    return _auth_response({
        'ok': True,
        'message': f'Se cobraron {len(pedidos)} pedido(s) correctamente.',
        'factura': {
            'referencia': referencia,
            'total': str(total_cobrado),
            'pedidos': [pedido.id for pedido in pedidos],
        },
    }, status=201)


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
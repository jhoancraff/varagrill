import ipaddress
import json
import mimetypes
import logging
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
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
    VGAbonoCompra,
    VGCategoriaProducto,
    VGCliente,
    VGCompra,
    VGConfiguracionCosteo,
    VGDetalleCompra,
    VGDetallePedido,
    VGDetallePedidoAdicional,
    VGDetallePedidoOpcion,
    VGFactura,
    VGGrupoOpcionProducto,
    VGImpresoraCaja,
    VGIngrediente,
    VGMesa,
    VGMetodoPago,
    VGMovimientoInventario,
    VGNotaEntrega,
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
from .auth_helpers import (
    _auth_response,
    _get_role_name,
    _is_admin_user,
    _is_analista_user,
    _is_cajera_user,
    _is_mesero_user,
    _is_owner_or_contador_user,
    _is_owner_user,
)
from .impresion_lpd import imprimir_nota_entrega_caja
from .impresion_termica import imprimir_comandas_pedido
from .ingredientes_excel import (
    InvalidExcelError,
    normalize_unidad,
    parse_cantidad,
    parse_decimal_opcional,
    parse_ingredientes_workbook,
    parse_precio_total,
)
from .notifications import send_whatsapp_new_order_alert
from .reportes import tasa_para_fecha
from .serializers import MesaSerializer, ProductoSerializer
from .tasa_cambio import obtener_tasa_actual, tasa_cambio_para_registro

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


# Solo g/ml/unidad (el negocio ya no maneja kg/l — ver migración
# 0025_solo_gramos_ml_unidad). Cada familia queda con un único miembro, así
# que _convertir_cantidad_a_unidad_ingrediente ahora siempre es un factor 1
# que no cambia nada; se deja la tabla (en vez de eliminar la función) porque
# sigue siendo el único punto de validación de "familia compatible" — evita
# mezclar, por ejemplo, una cantidad en 'unidad' contra un ingrediente en 'g'.
_UNIDAD_FAMILIA = {
    'g': ('masa', Decimal('1')),
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


def _notify_cocina_event(event_name, pedido, actor_user, previous_estado=None):
    # Se imprime la comanda física solo al pasar el pedido a "en preparación"
    # (cocina confirma que arranca a cocinarlo), no al registrarlo. No debe
    # depender de que el canal de WebSocket esté disponible: se intenta
    # siempre, aunque channel_layer sea None.
    # Excepción: si viene de "listo" (el mesero le dio "Volver a preparar" por
    # un error), no se reimprime la comanda — ya se imprimió la primera vez y
    # no se quiere duplicar el ticket en cocina por una corrección de estado.
    if event_name == 'PEDIDO_ACTUALIZADO' and pedido.estado == 'en_preparacion' and previous_estado != 'listo':
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


def _compute_addon_sale_price(costo_total, margen_ganancia):
    """
    Precio de venta de UN LOTE completo de un adicional: costo_total del lote (todo lo que
    rinde su receta, ver VGPreparacion.rendimiento_cantidad) + margen_ganancia% de ganancia
    sobre ese costo — nunca sobre el costo por gramo/ml/unidad. La cantidad que el mesero
    agrega en el pedido (VGDetallePedidoAdicional.cantidad) cuenta lotes, no gramos, así que
    mezclar un precio por gramo con esa cantidad daba precios absurdamente bajos.
    """
    margen = margen_ganancia if margen_ganancia is not None else Decimal('0')
    precio = costo_total * (Decimal('1') + margen / Decimal('100'))
    return precio.quantize(Decimal('0.01'))


def _aplicar_rendimiento_receta(costo, config=None):
    """
    Suma el porcentaje de rendimiento global (VGConfiguracionCosteo.rendimiento_receta_pct)
    a un costo de RECETA ya calculado — nunca a un costo de subreceta, ver el docstring
    del modelo. `config` es opcional para evitar N+1 queries cuando se llama en un loop
    (ver admin_products_view/admin_recipes_view, que lo cargan una sola vez).
    """
    config = config or VGConfiguracionCosteo.obtener_config()
    pct = config.rendimiento_receta_pct or Decimal('0')
    return costo * (Decimal('1') + pct / Decimal('100'))


def _resolver_margen_ganancia_producto(product, config=None):
    """Margen de ganancia efectivo de un producto: el propio si lo definio, si no el defecto global."""
    if product.margen_ganancia_pct is not None:
        return product.margen_ganancia_pct
    config = config or VGConfiguracionCosteo.obtener_config()
    return config.margen_ganancia_defecto_pct or Decimal('0')


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


def _resolver_multiplicador_acompanante(opcion, detalle, cantidad_platos):
    """
    Cuánto multiplicar la receta propia del acompañante elegido (`opcion`, ej. "Yuca al vapor"
    o "Arepas") para saber qué descontar de inventario. Si su grupo define gramos_base_racion,
    el acompañante se sirve en RACIONES completas según el peso del plato principal (ej: 250g
    de carne = 1 ración), redondeando a la ración más cercana con un mínimo de 1 — así un corte
    de 490g (casi 2 raciones) no se queda corto solo porque le faltaron 10g para el siguiente
    umbral, ni un corte de 1000g se queda en una sola ración de acompañante. Sin
    gramos_base_racion configurado, cae al comportamiento de siempre: escalar a la par del
    peso/cantidad del plato principal.
    """
    gramos_base = opcion.grupo.gramos_base_racion if opcion.grupo_id else None
    if not gramos_base or not detalle.peso_gramos:
        return cantidad_platos

    raciones_exactas = detalle.peso_gramos / Decimal(gramos_base)
    raciones = raciones_exactas.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    if raciones < 1:
        raciones = Decimal('1')
    return Decimal(detalle.cantidad) * raciones


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
            multiplicador = _resolver_multiplicador_acompanante(opcion, detalle, cantidad_platos)
            if opcion.producto_id:
                # Acompañante de un grupo dinámico (ej. "Yuca al vapor" elegida de
                # Guarniciones): descuenta según SU PROPIA receta, escalada por raciones
                # (ver _resolver_multiplicador_acompanante) si el grupo las define.
                for component in _product_recipe_components(opcion.producto):
                    amount = component['cantidad'] * multiplicador
                    if component['tipo'] == 'ingrediente':
                        needs[component['referencia_id']] = needs.get(component['referencia_id'], Decimal('0')) + amount
                    else:
                        _add_preparation_needs(
                            component['referencia_id'], amount,
                            components_by_preparation, yields_by_preparation, needs, set(),
                        )
                continue
            _add_preparation_needs(
                opcion.preparacion_id, multiplicador,
                components_by_preparation, yields_by_preparation, needs, set(),
            )

    return needs


def _compute_product_recipe_cost(product, preparation_cost_map, config=None):
    """
    Costea un VGProducto (receta) sumando (cantidad_requerida x costo) de sus
    ingredientes y subrecetas, y le suma el % de rendimiento global — esta
    función solo se usa para costear RECETAS (VGProducto de categoría
    'Recetas' o el `receta` propio de cualquier producto), nunca subrecetas,
    así que el buffer siempre aplica aquí (ver _aplicar_rendimiento_receta).
    """
    total = Decimal('0')
    for component in product.receta.all():
        if component.ingrediente_id:
            ingredient_cost = component.ingrediente.costo_unitario if component.ingrediente else Decimal('0')
            total += component.cantidad_requerida * ingredient_cost
        elif component.preparacion_id:
            costs = preparation_cost_map.get(component.preparacion_id, {'costo_unitario': Decimal('0')})
            total += component.cantidad_requerida * costs['costo_unitario']
    return _aplicar_rendimiento_receta(total, config)


def _compute_product_unit_cost(product, ingredient_costs, preparation_cost_map, config=None):
    """
    Costea 1 unidad vendible de `product` (o 1 kg si es venta_por_peso, mismo
    criterio que _compute_pedido_ingredient_needs) usando _product_recipe_components
    — a diferencia de _compute_product_recipe_cost, sí resuelve productos vinculados
    a una receta/subreceta (receta_vinculada/subreceta_vinculada), cuya tabla propia
    `receta` está vacía.

    El % de rendimiento global se suma SIEMPRE QUE el costo represente una
    receta (`receta_vinculada` o la tabla `receta` propia del producto) — pero
    NO cuando el producto está vinculado directamente a una subreceta
    (`subreceta_vinculada`), porque ahí el costo es el de la subreceta en sí,
    no el de una receta de plato. Ver el docstring de VGConfiguracionCosteo.
    """
    total = Decimal('0')
    for component in _product_recipe_components(product):
        if component['tipo'] == 'ingrediente':
            total += component['cantidad'] * ingredient_costs.get(component['referencia_id'], Decimal('0'))
        else:
            costs = preparation_cost_map.get(component['referencia_id'], {'costo_unitario': Decimal('0')})
            total += component['cantidad'] * costs['costo_unitario']
    if product.subreceta_vinculada_id:
        return total
    return _aplicar_rendimiento_receta(total, config)


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


def _tasas_venta_por_pedido(pedido_ids):
    """
    Resuelve, para cada pedido en `pedido_ids`, la tasa de cambio a la que se
    congeló su venta — para poder sumar ventas históricas en bolívares sin que
    el total dependa de la tasa vigente en el momento en que alguien mira el
    reporte (ver _calcular_margen_periodo). Prioridad:
      1. El VGPago directo del pedido (flujo "mesero cobra directo", ya no se
         genera para pedidos nuevos pero se conserva para el histórico) — su
         propia tasa_cambio_referencia, congelada al cobrar.
      2. Si el pedido quedó facturado, la tasa_cambio_referencia de esa
         VGFactura, congelada al emitirla.
      3. Si el pedido se cobró con nota de entrega, la tasa_cambio_referencia
         de esa VGNotaEntrega, congelada al emitirla — mismo criterio que la
         factura: la tasa de LA VENTA es la de emisión, no la de los abonos
         que se cobren después.
      4. Si ninguno de los anteriores tiene tasa (dato viejo sin backfill, o
         pedido marcado pagado sin pasar por ninguno de esos flujos), la
         última VGTasaCambio conocida en o antes de la fecha del pedido —
         mismo criterio que usa migrations.0031 para rellenar historicos.
    Devuelve {pedido_id: Decimal|None} — None solo si tampoco hay ninguna
    VGTasaCambio anterior a la fecha del pedido (instalación sin historial).
    """
    pedido_ids = set(pedido_ids)
    if not pedido_ids:
        return {}

    tasa_por_pedido = {}
    for pedido_id, tasa in (
        VGPago.objects
        .filter(pedido_id__in=pedido_ids, estado='completado', tasa_cambio_referencia__isnull=False)
        .order_by('fecha_pago')
        .values_list('pedido_id', 'tasa_cambio_referencia')
    ):
        tasa_por_pedido.setdefault(pedido_id, tasa)

    faltantes = pedido_ids - tasa_por_pedido.keys()
    if faltantes:
        for factura_id, tasa, pedido_id in (
            VGFactura.objects
            .filter(pedidos__id__in=faltantes, tasa_cambio_referencia__isnull=False)
            .order_by('fecha_emision')
            .values_list('id', 'tasa_cambio_referencia', 'pedidos__id')
        ):
            tasa_por_pedido.setdefault(pedido_id, tasa)

    faltantes = pedido_ids - tasa_por_pedido.keys()
    if faltantes:
        for nota_id, tasa, pedido_id in (
            VGNotaEntrega.objects
            .filter(pedidos__id__in=faltantes, tasa_cambio_referencia__isnull=False)
            .order_by('fecha_emision')
            .values_list('id', 'tasa_cambio_referencia', 'pedidos__id')
        ):
            tasa_por_pedido.setdefault(pedido_id, tasa)

    faltantes = pedido_ids - tasa_por_pedido.keys()
    if faltantes:
        fechas_por_pedido = dict(VGPedido.objects.filter(id__in=faltantes).values_list('id', 'fecha_creacion'))
        for pedido_id in faltantes:
            fecha = fechas_por_pedido.get(pedido_id)
            tasa_por_pedido[pedido_id] = tasa_para_fecha(fecha.date()) if fecha else None

    return tasa_por_pedido


def _calcular_margen_periodo(desde, hasta):
    """
    Ventas, costo de ingredientes y ganancia por producto vendido (pedidos
    pagados) entre `desde` y `hasta`, ambos inclusive. Extraido de
    reporte_margen_ganancia_view para que reporte_estado_resultados_view
    (contabilidad_views.py) pueda reusar el mismo calculo de "ventas totales"
    y "costo de ingredientes" sin duplicar la logica de costeo — ver el
    docstring de esa vista para el criterio de costo historico vs. estimado.

    total_ingreso_bs suma, registro por registro, ingreso_del_detalle x
    tasa_de_SU_pedido (ver _tasas_venta_por_pedido) — nunca ingreso_total (en
    USD) x una tasa única del momento en que se pide el reporte, que es lo
    que hacía que el mismo período mostrara un total en bolívares distinto
    según cuándo se consultara. costo_ingredientes_total NO tiene un
    equivalente per-record: el costeo de ingredientes es un costo unitario
    corriente (VGIngrediente.costo_unitario, promedio móvil), no una
    transacción con su propia tasa congelada, así que no hay de dónde sacar
    "la tasa de esta porción de costo" — su versión en bolívares se calcula
    aparte en reporte_estado_resultados_view con la tasa del cierre del
    período, no aquí.

    Devuelve (filas, total_ingreso, total_costo, total_ingreso_bs).
    """
    detalles = list(
        VGDetallePedido.objects
        .filter(
            pedido__estado='pagado',
            pedido__fecha_creacion__date__gte=desde,
            pedido__fecha_creacion__date__lte=hasta,
        )
        .select_related('producto__categoria')
    )

    tasas_por_pedido = _tasas_venta_por_pedido({detalle.pedido_id for detalle in detalles})

    ingredient_costs = dict(VGIngrediente.objects.values_list('id', 'costo_unitario'))
    preparation_cost_map = _load_preparation_cost_map()
    config_costeo = VGConfiguracionCosteo.obtener_config()
    unit_cost_cache = {}

    total_ingreso_bs = Decimal('0')
    filas_por_producto = {}
    for detalle in detalles:
        tasa_pedido = tasas_por_pedido.get(detalle.pedido_id)
        if tasa_pedido:
            total_ingreso_bs += detalle.subtotal * tasa_pedido
        producto = detalle.producto
        peso_factor = (detalle.peso_gramos / Decimal('1000')) if detalle.peso_gramos else Decimal('1')
        cantidad_equivalente = Decimal(detalle.cantidad) * peso_factor

        if detalle.costo_unitario_venta is not None:
            costo_unitario = detalle.costo_unitario_venta
            es_estimado = False
        else:
            if producto.id not in unit_cost_cache:
                unit_cost_cache[producto.id] = _compute_product_unit_cost(
                    producto, ingredient_costs, preparation_cost_map, config_costeo,
                )
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

    return filas, total_ingreso, total_costo, total_ingreso_bs


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

    filas, total_ingreso, total_costo, _total_ingreso_bs = _calcular_margen_periodo(desde, hasta)

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
            'grupos_opciones__categoria_opciones',
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
        costo_total = preparation_cost_map.get(preparation.id, {'costo_total': Decimal('0')})['costo_total']
        adicionales.append({
            'id': preparation.id,
            'nombre': preparation.nombre,
            'unidad': preparation.rendimiento_unidad,
            'precio': str(_compute_addon_sale_price(costo_total, preparation.margen_ganancia)),
        })

    return _auth_response({'ok': True, 'adicionales': adicionales})


def _resolve_opciones_linea(product, grupos, opciones_seleccionadas, dynamic_products_map):
    """
    Valida las opciones elegidas para una línea de pedido de `product` contra
    sus VGGrupoOpcionProducto (grupos propios de ESE producto) — distinto de los
    adicionales globales (es_adicional=True). Cada grupo es de uno de dos tipos
    (ver VGGrupoOpcionProducto.categoria_opciones):

    - Curado: la selección trae preparacion_id, validado contra las VGOpcionProducto
      del grupo (ej. "Acompañante" con Arepas/Casabe). Revisa obligatorio/seleccion_multiple
      igual que siempre.
    - Dinámico (categoria_opciones definida, ej. Guarniciones): la selección trae
      producto_id, validado contra `dynamic_products_map` (VGProducto disponibles,
      ya filtrados por _parse_order_payload) y contra que pertenezca a esa categoría.
      Nunca bloquea por "obligatorio" (se fuerza a False al guardar el grupo) — solo
      limita cuántas se pueden elegir vía maximo_selecciones.

    Devuelve (opciones_resueltas, error_message); cada fila resuelta es
    {'grupo_nombre': str, 'opcion': VGOpcionProducto} (curado) o
    {'grupo_nombre': str, 'producto': VGProducto} (dinámico).
    """
    grupos_by_id = {grupo.id: grupo for grupo in grupos}
    opciones_validas_por_grupo = {
        grupo.id: {opcion.preparacion_id: opcion for opcion in grupo.opciones.all()}
        for grupo in grupos if grupo.categoria_opciones_id is None
    }

    seleccion_por_grupo = {}
    for seleccion in opciones_seleccionadas:
        grupo_id = seleccion['grupo_id']
        grupo = grupos_by_id.get(grupo_id)
        if grupo is None:
            return None, f'"{product.nombre}" no tiene ese grupo de opciones.'

        if grupo.categoria_opciones_id is not None:
            producto_id = seleccion.get('producto_id')
            elegido = dynamic_products_map.get(producto_id) if producto_id else None
            if elegido is None or elegido.categoria_id != grupo.categoria_opciones_id:
                return None, f'Esa opción ya no está disponible en "{grupo.nombre}" para "{product.nombre}".'
            seleccion_por_grupo.setdefault(grupo_id, []).append(elegido)
        else:
            opciones_del_grupo = opciones_validas_por_grupo.get(grupo_id, {})
            preparacion_id = seleccion.get('preparacion_id')
            if preparacion_id not in opciones_del_grupo:
                return None, f'Esa opción no pertenece al grupo indicado para "{product.nombre}".'
            seleccion_por_grupo.setdefault(grupo_id, []).append(opciones_del_grupo[preparacion_id])

    resueltas = []
    for grupo in grupos:
        elegidas = seleccion_por_grupo.get(grupo.id, [])

        if grupo.categoria_opciones_id is not None:
            if grupo.maximo_selecciones and len(elegidas) > grupo.maximo_selecciones:
                return None, (
                    f'Solo puedes elegir hasta {grupo.maximo_selecciones} opciones '
                    f'de "{grupo.nombre}" para "{product.nombre}".'
                )
            for producto_elegido in elegidas:
                resueltas.append({'grupo_nombre': grupo.nombre, 'grupo': grupo, 'producto': producto_elegido})
            continue

        if grupo.obligatorio and not elegidas:
            return None, f'Debes elegir una opción de "{grupo.nombre}" para "{product.nombre}".'
        if not grupo.seleccion_multiple and len(elegidas) > 1:
            return None, f'Solo puedes elegir una opción de "{grupo.nombre}" para "{product.nombre}".'
        for opcion in elegidas:
            resueltas.append({'grupo_nombre': grupo.nombre, 'grupo': grupo, 'opcion': opcion})

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
            except (TypeError, ValueError):
                return None, f'Una opción del item #{index} no es valida.'
            # Una opción curada trae preparacion_id (subreceta fija del grupo); una opción de
            # un grupo dinámico (categoria_opciones) trae producto_id (elegido entre lo
            # disponible de esa categoría en ese momento) — exactamente uno de los dos.
            opcion_preparacion_id = opcion.get('preparacion_id')
            opcion_producto_id = opcion.get('producto_id')
            try:
                opcion_preparacion_id = int(opcion_preparacion_id) if opcion_preparacion_id not in [None, ''] else None
                opcion_producto_id = int(opcion_producto_id) if opcion_producto_id not in [None, ''] else None
            except (TypeError, ValueError):
                return None, f'Una opción del item #{index} no es valida.'
            if (opcion_preparacion_id is None) == (opcion_producto_id is None):
                return None, f'Una opción del item #{index} no es valida.'
            parsed_opciones.append({
                'grupo_id': opcion_grupo_id,
                'preparacion_id': opcion_preparacion_id,
                'producto_id': opcion_producto_id,
            })
            if opcion_producto_id is not None:
                product_ids.append(opcion_producto_id)

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
        # select_related('categoria'): pedido_create_view/pedido_update_view necesitan
        # producto.categoria.no_requiere_cocina para decidir si el pedido salta cocina.
        for product in VGProducto.objects.filter(id__in=product_ids, disponible=True).select_related('categoria')
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
        opciones_resueltas, error = _resolve_opciones_linea(product, grupos, line['opciones'], products_map)
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
            costo_total = preparation_cost_map.get(preparation.id, {'costo_total': Decimal('0')})['costo_total']
            addon_price = _compute_addon_sale_price(costo_total, preparation.margen_ganancia)
            line_subtotal += addon_price * addon['cantidad']
            built_addons.append({
                'preparacion': preparation,
                'cantidad': addon['cantidad'],
                'precio_unitario': addon_price,
            })

        built_opciones = []
        for resuelta in line.get('opciones_resueltas', []):
            if 'producto' in resuelta:
                # Acompañante de un grupo dinámico (categoria_opciones, ej. Guarniciones):
                # viene incluido en el precio del corte, sin cargo adicional — ver acuerdo
                # con el usuario ("puedes acompañar tus cortes con 2 de las siguientes
                # opciones", sin mencionar recargo.
                built_opciones.append({
                    'grupo_nombre': resuelta['grupo_nombre'],
                    'grupo': resuelta['grupo'],
                    'producto': resuelta['producto'],
                    'preparacion': None,
                    'precio_unitario': Decimal('0.00'),
                })
                continue
            opcion = resuelta['opcion']
            precio_opcion_total = (opcion.precio_adicional * peso_factor * line['cantidad']).quantize(Decimal('0.01'))
            line_subtotal += precio_opcion_total
            built_opciones.append({
                'grupo_nombre': resuelta['grupo_nombre'],
                'grupo': resuelta['grupo'],
                'preparacion': opcion.preparacion,
                'producto': None,
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
            'producto_id': opcion.producto_id,
            'nombre': opcion.nombre,
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
        'cliente_cedula': pedido.cliente.numero_documento if pedido.cliente else '',
        'cliente_telefono': pedido.cliente.telefono if pedido.cliente else '',
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


def _resolve_or_create_cliente(nombre, cedula, telefono):
    """
    Resuelve el cliente por cédula cuando se da (identificador confiable para
    historial de movimientos y futuros sorteos): si ya existe un VGCliente con
    esa cédula, se reutiliza tal cual (no se pisa nombre/teléfono ya guardados
    con lo que haya escrito el mesero esta vez). Si no existe, se crea con los
    datos capturados ahora. Sin cédula, cae al comportamiento previo
    (get_or_create solo por nombre), ya que no hay forma confiable de saber si
    es el mismo cliente.
    """
    cedula = cedula.strip()
    if cedula:
        cliente, _ = VGCliente.objects.get_or_create(
            tipo_documento='V',
            numero_documento=cedula,
            defaults={'nombre': nombre, 'telefono': telefono},
        )
        return cliente
    cliente, _ = VGCliente.objects.get_or_create(nombre=nombre)
    return cliente


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

    # Cajera/admin/contador quedan exentos de este bloqueo: son justo quienes entran
    # a la mesa de un mesero desbordado (ver mesas_atendidas_view) para registrarle
    # una ronda cuando pide ayuda — bloquearlos igual que a otro mesero cualquiera
    # rompería ese flujo. Sigue aplicando normal entre dos meseros.
    if parsed['mesa'] is not None and not (_is_cajera_user(request.user) or _is_admin_user(request.user)):
        otro_mesero_pedido = (
            VGPedido.objects
            .filter(mesa=parsed['mesa'], estado__in=MESA_ABIERTA_ORDER_STATES)
            .exclude(usuario=request.user)
            .select_related('usuario')
            .order_by('fecha_creacion')
            .first()
        )
        if otro_mesero_pedido:
            mesero_nombre = otro_mesero_pedido.usuario.get_full_name() or otro_mesero_pedido.usuario.username
            return _auth_response({
                'ok': False,
                'message': f'La Mesa {parsed["mesa"].numero} ya la está atendiendo {mesero_nombre}.',
            }, status=409)

    cliente_nombre = str(data.get('cliente_nombre', '') or '').strip()
    if not cliente_nombre:
        return _auth_response({'ok': False, 'message': 'El nombre del cliente es obligatorio.'}, status=400)
    cliente_cedula = str(data.get('cliente_cedula', '') or '').strip()
    cliente_telefono = str(data.get('cliente_telefono', '') or '').strip()
    cliente = _resolve_or_create_cliente(cliente_nombre, cliente_cedula, cliente_telefono)

    notas = str(data.get('notas', '') or '').strip()

    with transaction.atomic():
        built_lines, subtotal = _build_order_lines(parsed['parsed_lines'], parsed['products_map'], parsed['preparaciones_map'])
        # Si TODOS los productos del pedido son de categorías "no_requiere_cocina" (ej.
        # empacados para llevar), el pedido nace 'entregado': nunca pasa por el panel de
        # cocina (kitchen_orders_view solo lista pendiente/en_preparacion/listo) ni imprime
        # comanda (imprimir_comandas_pedido solo se dispara al pasar a en_preparacion), y
        # aparece de inmediato en Cobro (BILLABLE_ORDER_STATES). Si se mezcla con un plato
        # normal, todo el pedido sigue el flujo de cocina de siempre.
        requiere_cocina = any(not line['producto'].categoria.no_requiere_cocina for line in built_lines)
        estado_inicial = 'pendiente' if requiere_cocina else 'entregado'

        pedido = VGPedido.objects.create(
            mesa=parsed['mesa'],
            usuario=request.user,
            cliente=cliente,
            tipo_pedido=parsed['tipo_pedido'],
            estado=estado_inicial,
            notas=notas,
            impuesto=parsed['impuesto'],
            descuento=parsed['descuento'],
            propina=parsed['propina'],
            creado_por=request.user,
            actualizado_por=request.user,
        )

        for line in built_lines:
            detalle = VGDetallePedido.objects.create(
                pedido=pedido,
                producto=line['producto'],
                cantidad=line['cantidad'],
                precio_unitario=line['precio_unitario'],
                peso_gramos=line['peso_gramos'],
                grupo_armado=line['grupo_armado'],
                estado=estado_inicial,
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
                    grupo=opcion['grupo'],
                    preparacion=opcion['preparacion'],
                    producto=opcion['producto'],
                    precio_unitario=opcion['precio_unitario'],
                )

        total = subtotal + parsed['impuesto'] + parsed['propina'] - parsed['descuento']
        pedido.subtotal = subtotal.quantize(Decimal('0.01'))
        pedido.total = total.quantize(Decimal('0.01'))
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
            .prefetch_related('detalles__producto', 'detalles__adicionales__preparacion', 'detalles__opciones__preparacion', 'detalles__opciones__producto', 'detalles__opciones__grupo')
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

    cliente_nombre = str(data.get('cliente_nombre', '') or '').strip()
    if not cliente_nombre:
        return _auth_response({'ok': False, 'message': 'El nombre del cliente es obligatorio.'}, status=400)
    cliente_cedula = str(data.get('cliente_cedula', '') or '').strip()
    cliente_telefono = str(data.get('cliente_telefono', '') or '').strip()
    cliente = _resolve_or_create_cliente(cliente_nombre, cliente_cedula, cliente_telefono)

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

        # Misma excepción que pedido_create_view: cajera/admin/contador pueden mover el
        # pedido de un mesero a una mesa que otro mesero ya tiene abierta, sin el
        # bloqueo — ver ahí el porqué.
        if parsed['mesa'] is not None and not (_is_cajera_user(request.user) or _is_admin_user(request.user)):
            otro_mesero_pedido = (
                VGPedido.objects
                .filter(mesa=parsed['mesa'], estado__in=MESA_ABIERTA_ORDER_STATES)
                .exclude(pk=pedido.pk)
                .exclude(usuario=pedido.usuario)
                .select_related('usuario')
                .order_by('fecha_creacion')
                .first()
            )
            if otro_mesero_pedido:
                mesero_nombre = otro_mesero_pedido.usuario.get_full_name() or otro_mesero_pedido.usuario.username
                return _auth_response({
                    'ok': False,
                    'message': f'La Mesa {parsed["mesa"].numero} ya la está atendiendo {mesero_nombre}.',
                }, status=409)

        built_lines, subtotal = _build_order_lines(parsed['parsed_lines'], parsed['products_map'], parsed['preparaciones_map'])
        # Mismo criterio que pedido_create_view: si el pedido editado queda compuesto
        # solo por categorías "no_requiere_cocina", pasa a 'entregado' de una vez.
        requiere_cocina = any(not line['producto'].categoria.no_requiere_cocina for line in built_lines)
        estado_inicial = 'pendiente' if requiere_cocina else 'entregado'

        pedido.mesa = parsed['mesa']
        pedido.tipo_pedido = parsed['tipo_pedido']
        pedido.cliente = cliente
        pedido.notas = notas
        pedido.impuesto = parsed['impuesto']
        pedido.descuento = parsed['descuento']
        pedido.propina = parsed['propina']
        pedido.estado = estado_inicial

        pedido.detalles.all().delete()

        for line in built_lines:
            detalle = VGDetallePedido.objects.create(
                pedido=pedido,
                producto=line['producto'],
                cantidad=line['cantidad'],
                precio_unitario=line['precio_unitario'],
                peso_gramos=line['peso_gramos'],
                grupo_armado=line['grupo_armado'],
                estado=estado_inicial,
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
                    grupo=opcion['grupo'],
                    preparacion=opcion['preparacion'],
                    producto=opcion['producto'],
                    precio_unitario=opcion['precio_unitario'],
                )

        total = subtotal + parsed['impuesto'] + parsed['propina'] - parsed['descuento']
        pedido.subtotal = subtotal.quantize(Decimal('0.01'))
        pedido.total = total.quantize(Decimal('0.01'))
        pedido.actualizado_por = request.user
        pedido.save()

    pedido = VGPedido.objects.select_related('mesa', 'cliente').prefetch_related('detalles__producto', 'detalles__adicionales__preparacion', 'detalles__opciones__preparacion', 'detalles__opciones__producto', 'detalles__opciones__grupo').get(pk=pedido.id)
    _notify_cocina_event('PEDIDO_ACTUALIZADO', pedido, request.user)

    return _auth_response({
        'ok': True,
        'message': 'Pedido actualizado correctamente.',
        'pedido': _serialize_order_detail(pedido),
    })


@csrf_exempt
def pedido_detalle_eliminar_view(request, pedido_id, detalle_id):
    """
    Quita UN item de un pedido ya en curso — para cuando el mesero eligió mal un plato
    y ya es tarde para que él mismo lo reordene desde cero (pedido_update_view exige
    'pendiente'; esto no). Reservado a cajera/admin/contador — el mismo criterio que la
    excepción de mesa en pedido_create_view: son quienes atienden la mesa desde caja,
    no el mesero dueño del pedido.
    """
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not request.user.is_authenticated:
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion.'}, status=401)

    if not (_is_cajera_user(request.user) or _is_admin_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para quitar items de un pedido.'}, status=401)

    with transaction.atomic():
        try:
            pedido = VGPedido.objects.select_for_update().get(pk=pedido_id)
        except VGPedido.DoesNotExist:
            return _auth_response({'ok': False, 'message': 'El pedido no existe.'}, status=404)

        if pedido.estado not in MESA_ABIERTA_ORDER_STATES:
            return _auth_response(
                {'ok': False, 'message': 'Solo se pueden quitar items de un pedido todavía abierto (ni pagado ni cancelado).'},
                status=409,
            )

        try:
            detalle = pedido.detalles.select_related('producto').get(pk=detalle_id)
        except VGDetallePedido.DoesNotExist:
            return _auth_response({'ok': False, 'message': 'Ese item no pertenece a este pedido.'}, status=404)

        if pedido.detalles.count() <= 1:
            return _auth_response(
                {'ok': False, 'message': 'No puedes quitar el único item del pedido — cancela el pedido completo en su lugar.'},
                status=409,
            )

        producto_nombre = detalle.producto.nombre
        detalle.delete()

        # Mismo total que serializa cada item (ver VGDetallePedido.subtotal): precio
        # base del item + sus adicionales + sus opciones — nunca hace falta recalcular
        # precios desde cero, solo sumar lo que queda.
        subtotal = sum(
            (
                d.subtotal
                + sum((a.subtotal for a in d.adicionales.all()), Decimal('0'))
                + sum((o.subtotal for o in d.opciones.all()), Decimal('0'))
            )
            for d in pedido.detalles.all()
        )
        total = subtotal + pedido.impuesto + pedido.propina - pedido.descuento
        pedido.subtotal = subtotal.quantize(Decimal('0.01'))
        pedido.total = total.quantize(Decimal('0.01'))
        pedido.actualizado_por = request.user
        pedido.save(update_fields=['subtotal', 'total', 'actualizado_por', 'fecha_actualizacion'])

    pedido = (
        VGPedido.objects
        .select_related('mesa', 'cliente')
        .prefetch_related(
            'detalles__producto', 'detalles__adicionales__preparacion',
            'detalles__opciones__preparacion', 'detalles__opciones__producto', 'detalles__opciones__grupo',
        )
        .get(pk=pedido.id)
    )
    _notify_cocina_event('PEDIDO_ACTUALIZADO', pedido, request.user)

    return _auth_response({
        'ok': True,
        'message': f'Se quitó "{producto_nombre}" del pedido #{pedido.id}.',
        'pedido': _serialize_order_detail(pedido),
    })


def _costo_unitario_por_compra(precio_total, cantidad, ingrediente):
    """
    Precio de compra ÷ cantidad REALMENTE utilizable. Si el ingrediente tiene
    contenido_envase y peso_real cargados, la cantidad comprada se ajusta por esa razón
    (peso_real / contenido_envase) antes de dividir — así una compra de 5000g de algo que
    rinde 85% por envase cuesta lo mismo por gramo útil que una de 1000g (ver
    VGIngrediente.contenido_envase/peso_real). Sin esos dos datos, se divide por la
    cantidad comprada tal cual, igual que antes de que existiera este ajuste.
    """
    if ingrediente.contenido_envase and ingrediente.peso_real:
        cantidad_utilizable = cantidad * (ingrediente.peso_real / ingrediente.contenido_envase)
    else:
        cantidad_utilizable = cantidad
    if not cantidad_utilizable:
        return Decimal('0')
    return (precio_total / cantidad_utilizable).quantize(Decimal('0.000001'))


def _costo_unitario_desde_precio(precio_compra, peso_real):
    """
    precio_compra ÷ peso_real: caso particular de _costo_unitario_por_compra cuando se
    compra un solo envase de referencia (cantidad == contenido_envase). Es la fórmula que
    se usa para mantener VGIngrediente.costo_unitario siempre sincronizado con el trío
    contenido_envase/peso_real/precio_compra cargado directamente en el ingrediente,
    fuera del flujo de compras por lote (VGCompraBorrador).
    """
    if not peso_real:
        return Decimal('0')
    return (precio_compra / peso_real).quantize(Decimal('0.000001'))


def _validar_envase_peso_precio(contenido_envase, peso_real, precio_compra):
    """
    Valida el trío contenido_envase/peso_real/precio_compra ya parseado a Decimal (no
    None). Devuelve un mensaje de error en español, o None si todo está en regla.
    Comparte esta regla crear_ingrediente, actualizar_ingrediente y la importación por
    Excel para no repetir el mismo chequeo tres veces.
    """
    if contenido_envase <= 0 or peso_real <= 0:
        return 'El contenido del envase y el peso real deben ser mayores a cero.'
    if peso_real > contenido_envase:
        return 'El peso real no puede ser mayor que el contenido del envase.'
    if precio_compra < 0:
        return 'El precio de compra no puede ser negativo.'
    return None


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
            VGIngrediente.objects.order_by('-fecha_creacion', 'nombre').values(
                'id', 'nombre', 'stock_actual', 'unidad_medida', 'ultimo_proveedor', 'costo_unitario',
                'stock_minimo', 'contenido_envase', 'peso_real', 'precio_compra',
                'ingrediente_crudo_equivalente', 'rendimiento_ingrediente_crudo',
            )
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
                # 6 decimales (igual que VGIngrediente.costo_unitario), no 2: una subreceta con
                # rendimiento grande (ej. 900g) puede costar centavos por gramo — redondear a 2
                # decimales acá lo deja en $0.00 y cualquier cantidad de esa subreceta usada en
                # otra receta se calcula como gratis. El total en dólares sí se redondea a 2 para
                # mostrar, pero la TASA por unidad necesita más precisión porque después se
                # multiplica por cantidades potencialmente grandes.
                'costo_unitario_calculado': str(costo_unitario.quantize(Decimal('0.000001'))),
                'precio_venta_calculado': (
                    str(_compute_addon_sale_price(costs['costo_total'], preparation['margen_ganancia']))
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
        contenido_envase = data.get('contenido_envase')
        peso_real = data.get('peso_real')
        precio_compra = data.get('precio_compra')

        try:
            stock_actual_value = Decimal(str(stock_actual or 0))
            stock_minimo_value = Decimal(str(stock_minimo or 0))
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'Los valores numéricos del ingrediente son inválidos.'}, status=400)

        if contenido_envase in [None, ''] or peso_real in [None, ''] or precio_compra in [None, '']:
            return _auth_response(
                {
                    'ok': False,
                    'message': (
                        'El contenido del envase, el peso real y el precio de compra son obligatorios '
                        'para calcular el costo correctamente.'
                    ),
                },
                status=400,
            )
        try:
            contenido_envase_value = Decimal(str(contenido_envase))
            peso_real_value = Decimal(str(peso_real))
            precio_compra_value = Decimal(str(precio_compra))
        except InvalidOperation:
            return _auth_response(
                {'ok': False, 'message': 'El contenido del envase, el peso real y el precio de compra deben ser numéricos.'},
                status=400,
            )
        error_trio = _validar_envase_peso_precio(contenido_envase_value, peso_real_value, precio_compra_value)
        if error_trio:
            return _auth_response({'ok': False, 'message': error_trio}, status=400)
        costo_unitario_value = _costo_unitario_desde_precio(precio_compra_value, peso_real_value)

        # Opcional: solo aplica a ingredientes empacados para reventa (ver
        # VGIngrediente.ingrediente_crudo_equivalente). Van juntos igual que envase/peso real.
        ingrediente_crudo_equivalente_id = data.get('ingrediente_crudo_equivalente_id')
        rendimiento_ingrediente_crudo = data.get('rendimiento_ingrediente_crudo')
        ingrediente_crudo_equivalente = None
        rendimiento_ingrediente_crudo_value = None
        if ingrediente_crudo_equivalente_id not in [None, ''] or rendimiento_ingrediente_crudo not in [None, '']:
            if ingrediente_crudo_equivalente_id in [None, ''] or rendimiento_ingrediente_crudo in [None, '']:
                return _auth_response(
                    {'ok': False, 'message': 'El ingrediente crudo equivalente y su rendimiento van juntos: completá los dos o dejá los dos vacíos.'},
                    status=400,
                )
            try:
                ingrediente_crudo_equivalente = VGIngrediente.objects.get(pk=int(ingrediente_crudo_equivalente_id))
            except (ValueError, TypeError, VGIngrediente.DoesNotExist):
                return _auth_response({'ok': False, 'message': 'El ingrediente crudo equivalente no existe.'}, status=400)
            try:
                rendimiento_ingrediente_crudo_value = Decimal(str(rendimiento_ingrediente_crudo))
            except InvalidOperation:
                return _auth_response({'ok': False, 'message': 'El rendimiento del ingrediente crudo debe ser numérico.'}, status=400)
            if rendimiento_ingrediente_crudo_value <= 0:
                return _auth_response({'ok': False, 'message': 'El rendimiento del ingrediente crudo debe ser mayor a cero.'}, status=400)

        existing = VGIngrediente.objects.filter(nombre__iexact=nombre).first()
        if existing is not None:
            return _auth_response({'ok': False, 'message': 'Ya existe un ingrediente con ese nombre.'}, status=400)

        ingredient = VGIngrediente.objects.create(
            nombre=nombre,
            unidad_medida=unidad,
            stock_actual=stock_actual_value,
            stock_minimo=stock_minimo_value,
            costo_unitario=costo_unitario_value,
            contenido_envase=contenido_envase_value,
            peso_real=peso_real_value,
            precio_compra=precio_compra_value,
            ingrediente_crudo_equivalente=ingrediente_crudo_equivalente,
            rendimiento_ingrediente_crudo=rendimiento_ingrediente_crudo_value,
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
        contenido_envase = data.get('contenido_envase', ingredient.contenido_envase)
        peso_real = data.get('peso_real', ingredient.peso_real)
        precio_compra = data.get('precio_compra', ingredient.precio_compra)

        try:
            stock_actual_value = Decimal(str(stock_actual or 0))
            stock_minimo_value = Decimal(str(stock_minimo or 0))
            costo_unitario_value = Decimal(str(costo_unitario or 0))
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'Los valores numéricos del ingrediente son inválidos.'}, status=400)

        # A diferencia de crear_ingrediente, acá contenido_envase/peso_real quedan
        # opcionales (pueden venir vacíos si el ingrediente es viejo y todavía no se
        # completó este dato) — solo se validan entre sí si se cargó alguno de los dos.
        # Nota: el frontend siempre manda las tres claves (con null si el campo está
        # vacío), así que NO se puede exigir que precio_compra venga junto con estos dos
        # como un trío obligatorio — eso bloquearía para siempre cualquier edición (ni
        # siquiera cambiar el nombre) de todo ingrediente que ya tenga envase/peso
        # cargados de antes de que existiera este campo. En cambio, precio_compra se
        # valida por su cuenta y solo dispara el cálculo automático cuando los tres
        # datos efectivos (recién editados o ya guardados) están disponibles a la vez;
        # si falta alguno, costo_unitario sigue siendo el valor manual de siempre.
        contenido_envase_value = ingredient.contenido_envase
        peso_real_value = ingredient.peso_real
        if contenido_envase not in [None, ''] or peso_real not in [None, '']:
            if contenido_envase in [None, ''] or peso_real in [None, '']:
                return _auth_response(
                    {'ok': False, 'message': 'El contenido del envase y el peso real van juntos: completá los dos o dejá los dos vacíos.'},
                    status=400,
                )
            try:
                contenido_envase_value = Decimal(str(contenido_envase))
                peso_real_value = Decimal(str(peso_real))
            except InvalidOperation:
                return _auth_response({'ok': False, 'message': 'El contenido del envase y el peso real deben ser numéricos.'}, status=400)
            if contenido_envase_value <= 0 or peso_real_value <= 0:
                return _auth_response({'ok': False, 'message': 'El contenido del envase y el peso real deben ser mayores a cero.'}, status=400)
            if peso_real_value > contenido_envase_value:
                return _auth_response({'ok': False, 'message': 'El peso real no puede ser mayor que el contenido del envase.'}, status=400)

        precio_compra_value = ingredient.precio_compra
        if precio_compra not in [None, '']:
            try:
                precio_compra_value = Decimal(str(precio_compra))
            except InvalidOperation:
                return _auth_response({'ok': False, 'message': 'El precio de compra debe ser numérico.'}, status=400)
            if precio_compra_value < 0:
                return _auth_response({'ok': False, 'message': 'El precio de compra no puede ser negativo.'}, status=400)
        elif precio_compra in ['']:
            precio_compra_value = None

        if contenido_envase_value and peso_real_value and precio_compra_value is not None:
            costo_unitario_value = _costo_unitario_desde_precio(precio_compra_value, peso_real_value)

        # Mismo criterio opcional que envase/peso real — solo aplica a empacados.
        ingrediente_crudo_equivalente_id = data.get('ingrediente_crudo_equivalente_id', ingredient.ingrediente_crudo_equivalente_id)
        rendimiento_ingrediente_crudo = data.get('rendimiento_ingrediente_crudo', ingredient.rendimiento_ingrediente_crudo)
        ingrediente_crudo_equivalente = ingredient.ingrediente_crudo_equivalente
        rendimiento_ingrediente_crudo_value = ingredient.rendimiento_ingrediente_crudo
        if ingrediente_crudo_equivalente_id not in [None, ''] or rendimiento_ingrediente_crudo not in [None, '']:
            if ingrediente_crudo_equivalente_id in [None, ''] or rendimiento_ingrediente_crudo in [None, '']:
                return _auth_response(
                    {'ok': False, 'message': 'El ingrediente crudo equivalente y su rendimiento van juntos: completá los dos o dejá los dos vacíos.'},
                    status=400,
                )
            if str(ingrediente_crudo_equivalente_id) == str(ingredient.pk):
                return _auth_response({'ok': False, 'message': 'Un ingrediente no puede ser su propio equivalente crudo.'}, status=400)
            try:
                ingrediente_crudo_equivalente = VGIngrediente.objects.get(pk=int(ingrediente_crudo_equivalente_id))
            except (ValueError, TypeError, VGIngrediente.DoesNotExist):
                return _auth_response({'ok': False, 'message': 'El ingrediente crudo equivalente no existe.'}, status=400)
            try:
                rendimiento_ingrediente_crudo_value = Decimal(str(rendimiento_ingrediente_crudo))
            except InvalidOperation:
                return _auth_response({'ok': False, 'message': 'El rendimiento del ingrediente crudo debe ser numérico.'}, status=400)
            if rendimiento_ingrediente_crudo_value <= 0:
                return _auth_response({'ok': False, 'message': 'El rendimiento del ingrediente crudo debe ser mayor a cero.'}, status=400)

        duplicate = VGIngrediente.objects.filter(nombre__iexact=nombre).exclude(pk=ingredient.pk).exists()
        if duplicate:
            return _auth_response({'ok': False, 'message': 'Ya existe otro ingrediente con ese nombre.'}, status=400)

        ingredient.nombre = nombre
        ingredient.unidad_medida = unidad
        ingredient.ultimo_proveedor = proveedor
        ingredient.stock_actual = stock_actual_value
        ingredient.stock_minimo = stock_minimo_value
        ingredient.costo_unitario = costo_unitario_value
        ingredient.contenido_envase = contenido_envase_value
        ingredient.peso_real = peso_real_value
        ingredient.precio_compra = precio_compra_value
        ingredient.ingrediente_crudo_equivalente = ingrediente_crudo_equivalente
        ingredient.rendimiento_ingrediente_crudo = rendimiento_ingrediente_crudo_value
        ingredient.actualizado_por = request.user
        ingredient.save(update_fields=[
            'nombre', 'unidad_medida', 'ultimo_proveedor', 'stock_actual', 'stock_minimo', 'costo_unitario',
            'contenido_envase', 'peso_real', 'precio_compra', 'ingrediente_crudo_equivalente', 'rendimiento_ingrediente_crudo',
            'actualizado_por', 'fecha_actualizacion',
        ])

        return _auth_response({'ok': True, 'message': 'Ingrediente actualizado correctamente.', 'item': {'id': ingredient.id, 'nombre': ingredient.nombre}})

    if tipo == 'reponer_desde_empacado':
        # "Abrir" N paquetes de un ingrediente empacado (ver VGIngrediente.
        # ingrediente_crudo_equivalente/rendimiento_ingrediente_crudo) para sumar su
        # contenido al ingrediente crudo de cocina — independiente de facturar: esto NO
        # crea ninguna VGFactura ni consume numeración fiscal, es un ajuste de inventario
        # interno, trazable via VGMovimientoInventario (misma tabla que compras/ajustes).
        empacado_id = data.get('empacado_id')
        try:
            empacado = VGIngrediente.objects.select_related('ingrediente_crudo_equivalente').get(pk=int(empacado_id))
        except (ValueError, TypeError, VGIngrediente.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'El ingrediente empacado no existe.'}, status=400)

        crudo = empacado.ingrediente_crudo_equivalente
        if crudo is None or not empacado.rendimiento_ingrediente_crudo:
            return _auth_response(
                {
                    'ok': False,
                    'message': f'"{empacado.nombre}" no tiene configurado un ingrediente crudo equivalente. '
                    + 'Completalo desde "Editar ingrediente" antes de reponer.',
                },
                status=400,
            )

        try:
            cantidad_paquetes = Decimal(str(data.get('cantidad_paquetes')))
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'La cantidad de paquetes no es válida.'}, status=400)
        if cantidad_paquetes <= 0:
            return _auth_response({'ok': False, 'message': 'La cantidad de paquetes debe ser mayor a cero.'}, status=400)
        if cantidad_paquetes > empacado.stock_actual:
            return _auth_response(
                {'ok': False, 'message': f'Solo hay {empacado.stock_actual} {empacado.unidad_medida} de "{empacado.nombre}" en stock.'},
                status=400,
            )

        cantidad_credito = cantidad_paquetes * empacado.rendimiento_ingrediente_crudo

        with transaction.atomic():
            empacado.stock_actual = empacado.stock_actual - cantidad_paquetes
            empacado.actualizado_por = request.user
            empacado.save(update_fields=['stock_actual', 'actualizado_por', 'fecha_actualizacion'])

            crudo.stock_actual = crudo.stock_actual + cantidad_credito
            crudo.actualizado_por = request.user
            crudo.save(update_fields=['stock_actual', 'actualizado_por', 'fecha_actualizacion'])

            VGMovimientoInventario.objects.create(
                ingrediente=empacado,
                tipo_movimiento='salida',
                cantidad=cantidad_paquetes,
                motivo=f'Reposición de cocina: se abrieron para reponer "{crudo.nombre}".',
                creado_por=request.user,
            )
            VGMovimientoInventario.objects.create(
                ingrediente=crudo,
                tipo_movimiento='entrada',
                cantidad=cantidad_credito,
                motivo=f'Reposición desde empacados: se abrieron {cantidad_paquetes} {empacado.unidad_medida} de "{empacado.nombre}".',
                creado_por=request.user,
            )

        return _auth_response({
            'ok': True,
            'message': f'Se repuso {cantidad_credito} {crudo.unidad_medida} de "{crudo.nombre}" desde {cantidad_paquetes} {empacado.unidad_medida} de "{empacado.nombre}".',
        })

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
            if margen_ganancia > Decimal('9999.99'):
                return _auth_response({'ok': False, 'message': 'El margen de ganancia no puede ser mayor a 9999.99%.'}, status=400)

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
            if margen_ganancia > Decimal('9999.99'):
                return _auth_response({'ok': False, 'message': 'El margen de ganancia no puede ser mayor a 9999.99%.'}, status=400)

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
        costo_unitario_value = (precio_total_value / cantidad_value).quantize(Decimal('0.000001'))

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
                    # A diferencia de la creación (arriba), acá el ingrediente ya existe:
                    # si tiene contenido_envase/peso_real cargados hay que respetar esa
                    # merma en vez de la división simple, o se desincroniza el costo_unitario
                    # calculado en "Nuevo/Editar ingrediente" (ver _costo_unitario_por_compra).
                    ingredient.nombre = nombre
                    ingredient.unidad_medida = unidad
                    ingredient.stock_minimo = stock_minimo_value
                    ingredient.costo_unitario = _costo_unitario_por_compra(precio_total_value, cantidad_value, ingredient)
                    ingredient.ultimo_proveedor = proveedor
                    ingredient.actualizado_por = request.user
                    ingredient.save(update_fields=['nombre', 'unidad_medida', 'stock_minimo', 'costo_unitario', 'ultimo_proveedor', 'actualizado_por', 'fecha_actualizacion'])
            else:
                ingredient.nombre = nombre
                ingredient.unidad_medida = unidad
                ingredient.stock_minimo = stock_minimo_value
                ingredient.costo_unitario = _costo_unitario_por_compra(precio_total_value, cantidad_value, ingredient)
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
                tasa_cambio_referencia=tasa_cambio_para_registro(),
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
            _finalizar_estado_pago_compra(compra)

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


def _parse_trio_envase_peso_precio(row):
    """
    Parsea las 3 columnas opcionales del Excel "peso neto"/"peso real"/"precio de
    compra" (ver ingredientes_excel.HEADER_ALIASES) de un `row`/`item` ya extraído.
    Devuelve (trio, error):
    - los 3 vacíos -> ({}, None): la fila no toca estos datos.
    - los 3 presentes y válidos -> ({'contenido_envase':D,'peso_real':D,'precio_compra':D}, None)
    - cualquier combinación parcial, o algún valor fuera de rango -> (None, mensaje_error)
    """
    contenido_envase, error = parse_decimal_opcional(row.get('contenido_envase'), 'peso neto')
    if error:
        return None, error
    peso_real, error = parse_decimal_opcional(row.get('peso_real'), 'peso real')
    if error:
        return None, error
    precio_compra, error = parse_decimal_opcional(row.get('precio_compra'), 'precio de compra')
    if error:
        return None, error

    valores = (contenido_envase, peso_real, precio_compra)
    if all(valor is None for valor in valores):
        return {}, None
    if any(valor is None for valor in valores):
        return None, 'El peso neto, el peso real y el precio de compra van juntos: completá los tres o dejá los tres vacíos.'

    error_rango = _validar_envase_peso_precio(contenido_envase, peso_real, precio_compra)
    if error_rango:
        return None, error_rango

    return {'contenido_envase': contenido_envase, 'peso_real': peso_real, 'precio_compra': precio_compra}, None


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
    trio, error_trio = _parse_trio_envase_peso_precio(row)
    ingrediente = VGIngrediente.objects.filter(nombre__iexact=nombre).first()

    resultado = {
        'fila': row['fila'],
        'nombre': nombre,
        'unidad': unidad_normalizada or row['unidad'],
        'cantidad': str(cantidad) if cantidad is not None else row['cantidad'],
        'precio_total': str(precio_total) if precio_total is not None else (row.get('precio_total') or ''),
        'contenido_envase': str(trio['contenido_envase']) if trio else (row.get('contenido_envase') or ''),
        'peso_real': str(trio['peso_real']) if trio else (row.get('peso_real') or ''),
        'precio_compra': str(trio['precio_compra']) if trio else (row.get('precio_compra') or ''),
        'ingrediente_id': ingrediente.id if ingrediente else None,
        'stock_actual': str(ingrediente.stock_actual) if ingrediente else None,
        'unidad_actual': ingrediente.unidad_medida if ingrediente else None,
        'contenido_envase_actual': str(ingrediente.contenido_envase) if ingrediente and ingrediente.contenido_envase is not None else None,
        'peso_real_actual': str(ingrediente.peso_real) if ingrediente and ingrediente.peso_real is not None else None,
        'precio_compra_actual': str(ingrediente.precio_compra) if ingrediente and ingrediente.precio_compra is not None else None,
    }

    if error_precio:
        resultado['accion'] = 'error'
        resultado['mensaje'] = error_precio
    elif error_cantidad:
        resultado['accion'] = 'error'
        resultado['mensaje'] = error_cantidad
    elif error_trio:
        resultado['accion'] = 'error'
        resultado['mensaje'] = error_trio
    elif ingrediente is not None:
        cambia_stock = cantidad != 0 and cantidad != ingrediente.stock_actual
        if cambia_stock or trio:
            resultado['accion'] = 'actualizar'
            partes = []
            if cambia_stock:
                partes.append('el stock')
            if trio:
                partes.append('el peso neto, el peso real y el precio de compra')
            resultado['mensaje'] = 'Va a actualizar ' + ' y '.join(partes) + '.'
        elif cantidad == 0:
            resultado['accion'] = 'ignorado'
            resultado['mensaje'] = 'Cantidad vacía o en 0: no se toca este ingrediente.'
        else:
            resultado['accion'] = 'sin_cambios'
            resultado['mensaje'] = 'El stock ya coincide, no hay nada que actualizar.'
    elif cantidad == 0:
        resultado['accion'] = 'ignorado'
        resultado['mensaje'] = 'Cantidad vacía o en 0: no se toca este ingrediente.'
    elif not unidad_normalizada:
        resultado['accion'] = 'error'
        resultado['mensaje'] = 'Ingrediente nuevo: falta una unidad válida (g, ml o unidad).'
    elif not trio:
        resultado['accion'] = 'error'
        resultado['mensaje'] = 'Ingrediente nuevo: faltan el peso neto, el peso real y el precio de compra para calcular el costo.'
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
    en 0 se ignora para ingredientes NUEVOS — mismo criterio que sync_inventario_pesaje
    (management command). Para un ingrediente EXISTENTE, en cambio, una fila puede traer
    solo peso neto/peso real/precio de compra (ver _parse_trio_envase_peso_precio) sin
    tocar el stock — sirve para refrescar el costeo sin hacer un reconteo físico.

    La parte de "cantidad" (sincronizar el stock al valor de la planilla) se comporta
    exactamente igual que antes para reconteos puros — no se toca ese comportamiento.
    Cuando una fila resulta en un aumento de stock (ingrediente nuevo, o existente cuyo
    delta es positivo), esa porción SÍ se registra como una compra real — un único
    VGCompra (el "lote") para todo el archivo, con un VGDetalleCompra por cada fila que
    aumentó stock. El costeo de esa línea prioriza el trío nuevo
    (costo_unitario = precio_compra/peso_real) sobre el criterio viejo de precio_total/
    delta ajustado por el envase ya guardado (_costo_unitario_por_compra) si una fila
    trajera los dos. Si ninguna fila aumenta stock, no se crea ningún VGCompra.
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
                tasa_cambio_referencia=tasa_cambio_para_registro(),
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

            precio_total, error_precio = parse_precio_total(item.get('precio_total'))
            if error_precio:
                errores.append(f'{nombre}: {error_precio}')
                continue

            trio, error_trio = _parse_trio_envase_peso_precio(item)
            if error_trio:
                errores.append(f'{nombre}: {error_trio}')
                continue

            ingrediente = VGIngrediente.objects.filter(nombre__iexact=nombre).first()

            if ingrediente is not None:
                stock_anterior = ingrediente.stock_actual
                cambia_stock = cantidad != 0 and cantidad != stock_anterior
                if not cambia_stock and not trio:
                    if cantidad == 0:
                        ignorados += 1
                    # cantidad dada pero igual al stock actual, y sin trío: nada que
                    # hacer en esta fila — no se cuenta ni como ignorada ni actualizada,
                    # igual que el comportamiento de siempre.
                    continue

                delta = (cantidad - stock_anterior) if cambia_stock else Decimal('0')
                update_fields = ['actualizado_por', 'fecha_actualizacion']

                if trio:
                    ingrediente.contenido_envase = trio['contenido_envase']
                    ingrediente.peso_real = trio['peso_real']
                    ingrediente.precio_compra = trio['precio_compra']
                    ingrediente.costo_unitario = _costo_unitario_desde_precio(trio['precio_compra'], trio['peso_real'])
                    update_fields += ['contenido_envase', 'peso_real', 'precio_compra', 'costo_unitario']
                elif delta > 0 and precio_total is not None:
                    ingrediente.costo_unitario = _costo_unitario_por_compra(precio_total, delta, ingrediente)
                    update_fields.append('costo_unitario')

                if cambia_stock:
                    ingrediente.stock_actual = cantidad
                    update_fields.append('stock_actual')

                ingrediente.actualizado_por = operator
                ingrediente.save(update_fields=update_fields)

                movimiento_compra = None
                if delta > 0:
                    lote = _obtener_compra()
                    costo_linea = ingrediente.costo_unitario if (trio or precio_total is not None) else Decimal('0')
                    VGDetalleCompra.objects.create(
                        compra=lote, ingrediente=ingrediente, cantidad=delta, costo_unitario=costo_linea,
                    )
                    lote.total = lote.total + (delta * costo_linea)
                    lote.save(update_fields=['total'])
                    movimiento_compra = lote

                if delta != 0:
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
                if cantidad == 0:
                    ignorados += 1
                    continue
                unidad_normalizada = normalize_unidad(item.get('unidad'))
                if not unidad_normalizada:
                    errores.append(f'{nombre}: falta una unidad válida (g, ml o unidad) para crearlo.')
                    continue
                if not trio:
                    errores.append(f'{nombre}: faltan el peso neto, el peso real y el precio de compra para crearlo.')
                    continue
                costo_inicial = _costo_unitario_desde_precio(trio['precio_compra'], trio['peso_real'])
                nuevo = VGIngrediente.objects.create(
                    nombre=nombre,
                    unidad_medida=unidad_normalizada,
                    stock_actual=cantidad,
                    stock_minimo=Decimal('0'),
                    costo_unitario=costo_inicial,
                    contenido_envase=trio['contenido_envase'],
                    peso_real=trio['peso_real'],
                    precio_compra=trio['precio_compra'],
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

        if compra is not None:
            _finalizar_estado_pago_compra(compra)

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


def _preview_ingrediente_simple_row(row, vistos):
    """
    Clasifica una fila para la carga masiva SIN costo/cantidad (alta inicial de
    ingredientes al montar el restaurante, ver AnalystIngredientsBulkCreatePage.jsx):
    solo importa si el nombre ya existe o no. `vistos` acumula (en minúsculas) los
    nombres ya vistos en filas anteriores del mismo archivo, para detectar duplicados
    dentro del propio Excel.
    """
    nombre = row['nombre']
    clave = nombre.strip().lower()
    ingrediente = VGIngrediente.objects.filter(nombre__iexact=nombre).first()

    resultado = {'fila': row['fila'], 'nombre': nombre, 'ingrediente_id': ingrediente.id if ingrediente else None}

    if ingrediente is not None:
        resultado['accion'] = 'existente'
        resultado['mensaje'] = 'Ya existe en el inventario, no se vuelve a crear.'
    elif clave in vistos:
        resultado['accion'] = 'duplicado'
        resultado['mensaje'] = 'Nombre repetido en el archivo, ya se creará con la primera fila.'
    else:
        resultado['accion'] = 'nuevo'
        resultado['mensaje'] = ''

    vistos.add(clave)
    return resultado


def _crear_ingredientes_simple(nombres, motivo, operator):
    """
    Crea ingredientes nuevos sin stock, costo ni proveedor — solo para dejar
    registrada su existencia en el catálogo (ej: inversión inicial al abrir el
    restaurante, antes de que haya nada que inventariar). Cada alta queda registrada
    como un movimiento de tipo 'ajuste' en cantidad 0 con el motivo dado, para que
    quede el rastro de auditoría de por qué se creó sin pasar por una compra real.
    """
    creados, omitidos = 0, 0
    creados_nombres = set()

    with transaction.atomic():
        for nombre in nombres:
            nombre = str(nombre or '').strip()
            if not nombre or nombre.lower() in creados_nombres:
                continue

            if VGIngrediente.objects.filter(nombre__iexact=nombre).exists():
                omitidos += 1
                continue

            nuevo = VGIngrediente.objects.create(
                nombre=nombre,
                unidad_medida='unidad',
                stock_actual=Decimal('0'),
                stock_minimo=Decimal('0'),
                costo_unitario=Decimal('0'),
                creado_por=operator,
                actualizado_por=operator,
            )
            VGMovimientoInventario.objects.create(
                ingrediente=nuevo,
                tipo_movimiento='ajuste',
                cantidad=Decimal('0'),
                motivo=f'Alta inicial sin inventariar: {motivo}',
                creado_por=operator,
            )
            creados_nombres.add(nombre.lower())
            creados += 1

    return {'creados': creados, 'omitidos': omitidos}


@csrf_exempt
def admin_ingredientes_bulk_create_view(request):
    """
    Carga masiva de ingredientes SIN costo ni cantidad/unidad, pensada para el
    montaje inicial del inventario (apertura de restaurante): solo crea el registro
    del ingrediente si su nombre no existe todavía, con un motivo general obligatorio
    para toda la carga. A diferencia de admin_ingredientes_import_view, esto nunca
    actualiza un ingrediente existente ni genera compras/movimientos de stock real.
    """
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

        vistos = set()
        return _auth_response({'ok': True, 'filas': [_preview_ingrediente_simple_row(row, vistos) for row in filas]})

    if action == 'confirm':
        items = data.get('items')
        if not isinstance(items, list) or not items:
            return _auth_response({'ok': False, 'message': 'No hay filas para crear.'}, status=400)

        motivo = str(data.get('motivo', '') or '').strip()
        if not motivo:
            return _auth_response({'ok': False, 'message': 'El motivo de la carga es obligatorio.'}, status=400)

        nombres = [str(item.get('nombre', '') or '').strip() for item in items]
        resumen = _crear_ingredientes_simple(nombres, motivo, request.user)
        return _auth_response({'ok': True, **resumen})

    return _auth_response({'ok': False, 'message': 'Accion invalida.'}, status=400)


def _serialize_abono_compra(abono):
    return {
        'id': abono.id,
        'monto': str(abono.monto),
        'metodo_pago': abono.metodo_pago.nombre,
        'metodo_pago_id': abono.metodo_pago_id,
        'referencia': abono.referencia,
        'fecha_pago': abono.fecha_pago.isoformat(),
        'tasa_cambio_referencia': str(abono.tasa_cambio_referencia) if abono.tasa_cambio_referencia is not None else None,
        'creado_por': (abono.creado_por.get_full_name() or abono.creado_por.username) if abono.creado_por else '',
    }


def _serialize_compra(compra, incluir_detalle=False):
    data = {
        'id': compra.id,
        'proveedor_nombre': compra.proveedor_nombre,
        'numero_factura_proveedor': compra.numero_factura_proveedor,
        'fecha_factura': compra.fecha_factura.isoformat() if compra.fecha_factura else None,
        'fecha_creacion': compra.fecha_creacion.isoformat(),
        'total': str(compra.total),
        'estado': compra.estado,
        'saldo_pendiente': str(compra.saldo_pendiente),
        'estado_pago': compra.estado_pago,
        'tasa_cambio_referencia': str(compra.tasa_cambio_referencia) if compra.tasa_cambio_referencia is not None else None,
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
        data['abonos'] = [
            _serialize_abono_compra(abono) for abono in compra.abonos.select_related('metodo_pago').order_by('fecha_pago')
        ]
    return data


def _finalizar_estado_pago_compra(compra):
    """
    Deja lista la cuenta por pagar de una VGCompra recien creada: el saldo pendiente
    arranca en el total del lote (nadie ha abonado todavia) y el estado de pago en
    'pendiente' — salvo un lote en cero, que no genera deuda real. Se llama al final de
    cada flujo que crea una VGCompra (alta manual, importacion por Excel, carga por
    lote), una vez que compra.total ya quedo calculado.
    """
    compra.saldo_pendiente = compra.total
    compra.estado_pago = 'pagada' if compra.total <= 0 else 'pendiente'
    compra.save(update_fields=['saldo_pendiente', 'estado_pago'])


def admin_compras_view(request):
    """
    Historial completo de lotes de compra (VGCompra): de qué proveedor/factura vino cada
    carga de inventario. A diferencia de compra_detail_view (que también usa Cuentas por
    Pagar y por eso queda abierto a admin/contador), este historial completo es la
    tarjeta "Historial de compras" del Panel Analista, restringida a dueño/contador.
    """
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_owner_or_contador_user(request.user):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para ver el historial de compras.'}, status=401)

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
        'ip_impresora_secundaria': categoria.ip_impresora_secundaria,
        'puerto_impresora_secundaria': categoria.puerto_impresora_secundaria,
        'arma_plato_automatico': categoria.arma_plato_automatico,
        'prioridad_comanda': categoria.prioridad_comanda,
        'no_requiere_cocina': categoria.no_requiere_cocina,
    }


@csrf_exempt
def admin_categorias_view(request):
    """
    Asigna qué impresora térmica (IP:puerto en la LAN) imprime las comandas de cada
    categoría — la primaria (ticket completo) y, opcionalmente, una secundaria (copia
    reducida, ver impresion_termica._build_ticket_secundario_bytes). También activa
    arma_plato_automatico por categoría (ver NewOrderPage/EditOrderPage).
    """
    if request.method not in ['GET', 'POST']:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_owner_or_contador_user(request.user):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para configurar las impresoras.'}, status=401)

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

    ip_impresora_secundaria = str(data.get('ip_impresora_secundaria', '') or '').strip()
    if ip_impresora_secundaria:
        try:
            ipaddress.ip_address(ip_impresora_secundaria)
        except ValueError:
            return _auth_response({'ok': False, 'message': 'La IP de la impresora secundaria no es válida.'}, status=400)

    puerto_secundario_raw = data.get('puerto_impresora_secundaria', categoria.puerto_impresora_secundaria)
    try:
        puerto_impresora_secundaria = int(puerto_secundario_raw)
    except (TypeError, ValueError):
        return _auth_response({'ok': False, 'message': 'El puerto de la impresora secundaria no es válido.'}, status=400)
    if not (1 <= puerto_impresora_secundaria <= 65535):
        return _auth_response({'ok': False, 'message': 'El puerto secundario debe estar entre 1 y 65535.'}, status=400)

    categoria.ip_impresora = ip_impresora
    categoria.puerto_impresora = puerto_impresora
    categoria.ip_impresora_secundaria = ip_impresora_secundaria
    categoria.puerto_impresora_secundaria = puerto_impresora_secundaria
    categoria.arma_plato_automatico = bool(data.get('arma_plato_automatico', categoria.arma_plato_automatico))
    categoria.prioridad_comanda = bool(data.get('prioridad_comanda', categoria.prioridad_comanda))
    categoria.no_requiere_cocina = bool(data.get('no_requiere_cocina', categoria.no_requiere_cocina))
    categoria.actualizado_por = request.user
    categoria.save(update_fields=[
        'ip_impresora', 'puerto_impresora',
        'ip_impresora_secundaria', 'puerto_impresora_secundaria',
        'arma_plato_automatico', 'prioridad_comanda', 'no_requiere_cocina', 'actualizado_por', 'fecha_actualizacion',
    ])

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

    if not _is_owner_or_contador_user(request.user):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para configurar las impresoras.'}, status=401)

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
        'margen_ganancia_pct': str(product.margen_ganancia_pct) if product.margen_ganancia_pct is not None else '',
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
                'categoria_opciones_id': grupo.categoria_opciones_id,
                'categoria_opciones_nombre': grupo.categoria_opciones.nombre if grupo.categoria_opciones_id else '',
                'maximo_selecciones': grupo.maximo_selecciones,
                'gramos_base_racion': grupo.gramos_base_racion,
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
    Valida el payload de grupos de opciones de un producto (ver admin_products_view). Cada
    grupo es de uno de dos tipos:

    - Curado (de siempre): {"nombre": str, "obligatorio": bool, "seleccion_multiple": bool,
      "opciones": [{"preparacion_id": int, "precio_adicional": str}, ...]}. Cada opción se
      apoya en una VGPreparacion ya existente, curada a mano por el analista (ej. Arepas o
      Casabe).
    - Dinámico: {"nombre": str, "categoria_opciones_id": int, "maximo_selecciones": int|null}.
      El pool de opciones NO se guarda aquí: se arma en el momento del pedido con los
      VGProducto disponibles de esa categoría (ej. Guarniciones), así que agregar/quitar
      productos de esa categoría cambia el pool sin tocar este producto. Estos grupos nunca
      bloquean el pedido (obligatorio se fuerza a False) y siempre permiten varias
      selecciones hasta maximo_selecciones (seleccion_multiple se fuerza a True) — ver el
      acuerdo con el usuario: "el cliente a veces no va a querer el acompañante".

    Ambos tipos aceptan "gramos_base_racion": int|null — ver VGGrupoOpcionProducto.gramos_base_racion.

    Devuelve (grupos_parseados, error_message); cada grupo curado trae sus opciones ya
    resueltas a objetos VGPreparacion, listas para crear en bulk.
    """
    if not isinstance(raw_grupos, list):
        return None, 'Formato inválido de grupos de opciones.'

    preparacion_ids = set()
    categoria_ids = set()
    parsed_grupos = []
    for grupo_index, grupo in enumerate(raw_grupos, start=1):
        if not isinstance(grupo, dict):
            return None, f'El grupo de opciones #{grupo_index} tiene formato inválido.'
        nombre = str(grupo.get('nombre', '') or '').strip()
        if not nombre:
            return None, f'El grupo de opciones #{grupo_index} necesita un nombre.'

        gramos_base_racion = None
        gramos_base_racion_raw = grupo.get('gramos_base_racion')
        if gramos_base_racion_raw not in [None, '']:
            try:
                gramos_base_racion = int(gramos_base_racion_raw)
            except (TypeError, ValueError):
                return None, f'Los gramos por ración del grupo "{nombre}" no son válidos.'
            if gramos_base_racion <= 0:
                return None, f'Los gramos por ración del grupo "{nombre}" deben ser mayores a cero.'

        categoria_opciones_id = grupo.get('categoria_opciones_id')
        if categoria_opciones_id not in [None, '']:
            try:
                categoria_opciones_id = int(categoria_opciones_id)
            except (TypeError, ValueError):
                return None, f'La categoría de opciones del grupo "{nombre}" no es válida.'

            maximo_selecciones = None
            maximo_raw = grupo.get('maximo_selecciones')
            if maximo_raw not in [None, '']:
                try:
                    maximo_selecciones = int(maximo_raw)
                except (TypeError, ValueError):
                    return None, f'El máximo de selecciones del grupo "{nombre}" no es válido.'
                if maximo_selecciones <= 0:
                    return None, f'El máximo de selecciones del grupo "{nombre}" debe ser mayor a cero.'

            categoria_ids.add(categoria_opciones_id)
            parsed_grupos.append({
                'nombre': nombre,
                'obligatorio': False,
                'seleccion_multiple': True,
                'categoria_opciones_id': categoria_opciones_id,
                'maximo_selecciones': maximo_selecciones,
                'gramos_base_racion': gramos_base_racion,
                'opciones': [],
            })
            continue

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
            'categoria_opciones_id': None,
            'maximo_selecciones': None,
            'gramos_base_racion': gramos_base_racion,
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

    if categoria_ids:
        categorias_map = {
            categoria.id: categoria for categoria in VGCategoriaProducto.objects.filter(id__in=categoria_ids)
        }
        for grupo in parsed_grupos:
            if grupo['categoria_opciones_id'] is not None and grupo['categoria_opciones_id'] not in categorias_map:
                return None, f'La categoría de opciones del grupo "{grupo["nombre"]}" no existe.'

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
            .prefetch_related(
                'receta__ingrediente', 'receta__preparacion',
                'grupos_opciones__opciones__preparacion', 'grupos_opciones__categoria_opciones',
            )
            .order_by('nombre')
        )
        preparation_cost_map = _load_preparation_cost_map()
        config_costeo = VGConfiguracionCosteo.obtener_config()
        ingredients = list(
            VGIngrediente.objects.order_by('nombre').values('id', 'nombre', 'unidad_medida', 'stock_actual', 'costo_unitario')
        )
        recetas = [
            {
                'id': receta.id,
                'nombre': receta.nombre,
                'costo_unitario_calculado': str(
                    _compute_product_recipe_cost(receta, preparation_cost_map, config_costeo).quantize(Decimal('0.01'))
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
                # 6 decimales, no 2 — ver comentario equivalente más arriba (mismo motivo).
                'costo_unitario_calculado': str(
                    preparation_cost_map.get(preparation['id'], {'costo_unitario': Decimal('0')})['costo_unitario']
                    .quantize(Decimal('0.000001'))
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
            'configuracion_costeo': {
                'rendimiento_receta_pct': str(config_costeo.rendimiento_receta_pct),
                'margen_ganancia_defecto_pct': str(config_costeo.margen_ganancia_defecto_pct),
            },
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

    margen_ganancia_raw = data.get('margen_ganancia_pct')
    margen_ganancia_pct = None
    if margen_ganancia_raw not in [None, '']:
        try:
            margen_ganancia_pct = Decimal(str(margen_ganancia_raw))
            if margen_ganancia_pct < 0 or margen_ganancia_pct > Decimal('9999.99'):
                raise InvalidOperation
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'El margen de ganancia debe estar entre 0 y 9999.99.'}, status=400)

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
                margen_ganancia_pct=margen_ganancia_pct,
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
            product.margen_ganancia_pct = margen_ganancia_pct
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
                categoria_opciones_id=grupo_data['categoria_opciones_id'],
                maximo_selecciones=grupo_data['maximo_selecciones'],
                gramos_base_racion=grupo_data['gramos_base_racion'],
                orden=orden,
            )
            if grupo_data['opciones']:
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
        config_costeo = VGConfiguracionCosteo.obtener_config()
        preparations = []
        for preparation in VGPreparacion.objects.order_by('nombre').values('id', 'nombre', 'rendimiento_unidad', 'rendimiento_cantidad'):
            costs = preparation_cost_map.get(preparation['id'], {'costo_unitario': Decimal('0')})
            # 6 decimales, no 2 — ver comentario equivalente en admin_catalogo_view (mismo motivo).
            preparations.append({**preparation, 'costo_unitario_calculado': str(costs['costo_unitario'].quantize(Decimal('0.000001')))})

        recipe_payloads = []
        for recipe in recipes:
            payload = _serialize_recipe_product(recipe)
            payload['costo_calculado'] = str(
                _compute_product_recipe_cost(recipe, preparation_cost_map, config_costeo).quantize(Decimal('0.01')),
            )
            recipe_payloads.append(payload)

        return _auth_response({
            'ok': True,
            'recipes': recipe_payloads,
            'ingredients': inventory,
            'preparations': preparations,
            'configuracion_costeo': {
                'rendimiento_receta_pct': str(config_costeo.rendimiento_receta_pct),
                'margen_ganancia_defecto_pct': str(config_costeo.margen_ganancia_defecto_pct),
            },
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


@csrf_exempt
def admin_configuracion_costeo_view(request):
    """
    Configuración global de costeo (fila única, ver VGConfiguracionCosteo.obtener_config):
    el % de rendimiento que se suma al costo de toda receta de producto, y el % de
    margen de ganancia que se sugiere por defecto para productos nuevos que no
    definen el suyo propio (VGProducto.margen_ganancia_pct).
    """
    if request.method not in ['GET', 'POST']:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    config = VGConfiguracionCosteo.obtener_config()

    if request.method == 'GET':
        return _auth_response({
            'ok': True,
            'rendimiento_receta_pct': str(config.rendimiento_receta_pct),
            'margen_ganancia_defecto_pct': str(config.margen_ganancia_defecto_pct),
        })

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    try:
        rendimiento_receta_pct = Decimal(str(data.get('rendimiento_receta_pct', '0')))
        if rendimiento_receta_pct < 0:
            raise InvalidOperation
    except InvalidOperation:
        return _auth_response({'ok': False, 'message': 'El porcentaje de rendimiento no es válido.'}, status=400)

    try:
        margen_ganancia_defecto_pct = Decimal(str(data.get('margen_ganancia_defecto_pct', '0')))
        if margen_ganancia_defecto_pct < 0:
            raise InvalidOperation
    except InvalidOperation:
        return _auth_response({'ok': False, 'message': 'El porcentaje de margen por defecto no es válido.'}, status=400)

    config.rendimiento_receta_pct = rendimiento_receta_pct
    config.margen_ganancia_defecto_pct = margen_ganancia_defecto_pct
    config.actualizado_por = request.user
    config.save()

    return _auth_response({
        'ok': True,
        'message': 'Configuración de costeo actualizada correctamente.',
        'rendimiento_receta_pct': str(config.rendimiento_receta_pct),
        'margen_ganancia_defecto_pct': str(config.margen_ganancia_defecto_pct),
    })


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


MINUTOS_AUTO_AVANCE_PREPARACION = 10
MINUTOS_AUTO_AVANCE_LISTO = 10


def _avanzar_pedidos_en_preparacion_vencidos(actor_user):
    """
    Pasa a 'listo' cualquier pedido que lleve más de MINUTOS_AUTO_AVANCE_PREPARACION
    minutos en 'en_preparacion' — para que el mesero (o la cocina) no tenga que estar
    pendiente de marcarlo a mano, pedido por pedido.

    Se dispara desde kitchen_orders_view (GET) en vez de un cron/Celery aparte: el
    tablero de cocina ya hace polling cada 12s mientras está visible (ver
    KitchenOrdersPage.jsx), así que cualquier pedido vencido se detecta y avanza
    dentro de ese mismo margen, sin necesitar infraestructura de tareas en segundo
    plano nueva para este proyecto. select_for_update(skip_locked=True) evita que dos
    pantallas de cocina abiertas a la vez (dos tablets, por ejemplo) procesen el mismo
    pedido dos veces — a la segunda simplemente no le toca ninguna fila.

    `actor_user` queda registrado como autor del cambio en las notificaciones (quien
    tenía el tablero de cocina abierto en ese momento) — no existe un "usuario
    sistema" en la app, y esto es solo informativo, no afecta permisos.
    """
    limite = timezone.now() - timedelta(minutes=MINUTOS_AUTO_AVANCE_PREPARACION)
    with transaction.atomic():
        vencidos = list(
            VGPedido.objects.select_for_update(skip_locked=True)
            .filter(estado='en_preparacion', fecha_inicio_preparacion__lte=limite)
        )
        for pedido in vencidos:
            pedido.estado = 'listo'
            pedido.fecha_listo = timezone.now()
            pedido.actualizado_por = actor_user
            pedido.save(update_fields=['estado', 'fecha_listo', 'actualizado_por', 'fecha_actualizacion'])
            pedido.detalles.filter(estado__in=['pendiente', 'en_preparacion']).update(estado='listo')

    for pedido in vencidos:
        _notify_cocina_event('PEDIDO_ACTUALIZADO', pedido, actor_user, previous_estado='en_preparacion')
        _notify_usuario_event('PEDIDO_LISTO', pedido, actor_user)

    return vencidos


def _avanzar_pedidos_listos_vencidos(actor_user):
    """
    Pasa a 'entregado' cualquier pedido que lleve más de MINUTOS_AUTO_AVANCE_LISTO
    minutos en 'listo' — continúa la misma cadena de avance automático que
    _avanzar_pedidos_en_preparacion_vencidos, para que un pedido llegue solo hasta
    Cobro (BILLABLE_ORDER_STATES incluye 'entregado') sin que nadie tenga que
    presionar "Entregado" a mano.

    OJO: 'entregado' representa que el mesero ya lo llevó físicamente a la mesa —
    automatizar este paso es una decisión explícita del negocio (ver acuerdo con el
    usuario, 2026-09) de que ese tiempo de espera es suficiente para asumirlo
    entregado, no una confirmación real de que el plato ya llegó.

    Misma mecánica que la función hermana: se dispara desde el polling de
    kitchen_orders_view, select_for_update(skip_locked=True) evita procesar el mismo
    pedido dos veces desde dos tableros abiertos a la vez, y `actor_user` es solo
    informativo para las notificaciones.
    """
    limite = timezone.now() - timedelta(minutes=MINUTOS_AUTO_AVANCE_LISTO)
    with transaction.atomic():
        vencidos = list(
            VGPedido.objects.select_for_update(skip_locked=True)
            .filter(estado='listo', fecha_listo__lte=limite)
        )
        for pedido in vencidos:
            pedido.estado = 'entregado'
            pedido.actualizado_por = actor_user
            pedido.save(update_fields=['estado', 'actualizado_por', 'fecha_actualizacion'])
            pedido.detalles.filter(estado='listo').update(estado='entregado')

    for pedido in vencidos:
        _notify_cocina_event('PEDIDO_ACTUALIZADO', pedido, actor_user, previous_estado='listo')

    return vencidos


def kitchen_orders_view(request):
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not request.user.is_authenticated:
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion para ver pedidos.'}, status=401)

    _avanzar_pedidos_en_preparacion_vencidos(request.user)
    _avanzar_pedidos_listos_vencidos(request.user)

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
    if _is_mesero_user(request.user):
        # Un mesero solo debe ver sus propios pedidos, no los de sus compañeros.
        # Cajera/administrador/dueño sí necesitan visibilidad completa para
        # cobrar o supervisar cualquier mesa.
        base_queryset = base_queryset.filter(usuario=request.user)

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
            'detalles__opciones__preparacion', 'detalles__opciones__producto', 'detalles__opciones__grupo',
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
            'mesa_id': pedido.mesa_id,
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


# Estados que mantienen una mesa "abierta" en el reporte de mesas atendidas: si
# algún pedido de la mesa sigue en uno de estos, todavía falta que caja lo cobre
# o facture. Una mesa pasa a "cerrada" cuando ningún pedido queda en este
# conjunto (todos terminaron en 'pagado', o se cancelaron antes de cocina).
MESA_ABIERTA_ORDER_STATES = {'pendiente', 'en_preparacion', 'listo', 'entregado'}


def mesas_atendidas_view(request):
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not request.user.is_authenticated:
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion para ver tus mesas atendidas.'}, status=401)

    hoy = timezone.localdate()
    # Cajera/admin/contador ven las mesas de TODOS los meseros (no solo las propias) —
    # así pueden entrar a la mesa de un mesero desbordado y registrarle una ronda desde
    # ahí (ver el mismo criterio en pedido_create_view/pedido_update_view, que además
    # los exime del bloqueo de "esta mesa ya la atiende otro mesero"). Un mesero, en
    # cambio, solo ve las suyas — ese filtro por `usuario` es lo que le da privacidad
    # frente a las mesas de sus compañeros.
    ver_todas_las_mesas = _is_cajera_user(request.user) or _is_admin_user(request.user)

    # Solo pedidos todavía abiertos (ni pagados ni cancelados): en cuanto caja cobra
    # el último pedido abierto de una mesa, esa mesa deja de aparecer acá para el
    # mesero. Si más tarde llega gente nueva a esa misma mesa y se le crea un pedido,
    # arranca una entrada nueva y limpia — sin arrastrar ni sumar la ronda ya cobrada
    # de antes (eso era lo que confundía al mesero: veía el total viejo sumado al de
    # la mesa recién ocupada).
    pedidos_qs = VGPedido.objects.filter(
        mesa__isnull=False, fecha_creacion__date=hoy,
        estado__in=MESA_ABIERTA_ORDER_STATES,
    )
    if not ver_todas_las_mesas:
        pedidos_qs = pedidos_qs.filter(usuario=request.user)
    pedidos = (
        pedidos_qs
        .select_related('mesa', 'cliente', 'usuario')
        .order_by('mesa__numero', 'fecha_creacion')
    )

    mesas_por_id = {}
    for pedido in pedidos:
        entry = mesas_por_id.setdefault(pedido.mesa_id, {
            'mesa_id': pedido.mesa_id,
            'mesa_numero': pedido.mesa.numero,
            'pedidos': [],
        })
        entry['pedidos'].append(pedido)

    mesas_payload = []
    for entry in mesas_por_id.values():
        pedidos_mesa = entry['pedidos']
        # Toda mesa que llega hasta acá tiene al menos un pedido abierto (por el
        # filtro de arriba), así que siempre es 'abierta' — ya no existe el caso
        # 'cerrada' que antes se calculaba mezclando pedidos ya cobrados con los
        # nuevos de una mesa reutilizada.
        total = sum((p.total for p in pedidos_mesa), Decimal('0.00'))
        mesas_payload.append({
            'mesa_id': entry['mesa_id'],
            'mesa_numero': entry['mesa_numero'],
            'estado': 'abierta',
            'total': str(total),
            'pedidos': [
                {
                    'id': p.id,
                    'cliente': p.cliente.nombre if p.cliente else '',
                    'estado': p.estado,
                    'total': str(p.total),
                    'creado_en': p.fecha_creacion.isoformat(),
                    'mesero': p.usuario.get_full_name() or p.usuario.username,
                }
                for p in pedidos_mesa
            ],
        })

    mesas_payload.sort(key=lambda m: m['mesa_numero'])

    return _auth_response({
        'ok': True,
        'server_time': timezone.now().isoformat(),
        'mesas': mesas_payload,
        'todas_las_mesas': ver_todas_las_mesas,
    })


@csrf_exempt
def mesa_atendida_mover_view(request):
    """
    Mueve TODOS los pedidos abiertos (no pagados/cancelados) de una mesa del
    mesero a otra mesa — para cuando el cliente cambia de puesto. Solo mueve
    los pedidos del propio mesero (mismo criterio de privacidad que el resto
    de "mesas atendidas"); los ya pagados/cancelados de esa mesa se quedan
    donde estaban, son historial cerrado.
    """
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not request.user.is_authenticated:
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion.'}, status=401)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    try:
        mesa_origen_id = int(data.get('mesa_origen_id'))
        mesa_destino_id = int(data.get('mesa_destino_id'))
    except (TypeError, ValueError):
        return _auth_response({'ok': False, 'message': 'Mesa origen o destino invalida.'}, status=400)

    if mesa_origen_id == mesa_destino_id:
        return _auth_response({'ok': False, 'message': 'La mesa destino debe ser distinta a la actual.'}, status=400)

    try:
        mesa_destino = VGMesa.objects.get(pk=mesa_destino_id)
    except VGMesa.DoesNotExist:
        return _auth_response({'ok': False, 'message': 'La mesa destino no existe.'}, status=404)

    with transaction.atomic():
        ocupada = (
            VGPedido.objects
            .select_for_update()
            .filter(mesa_id=mesa_destino_id, estado__in=MESA_ABIERTA_ORDER_STATES)
            .exists()
        )
        if ocupada:
            return _auth_response(
                {'ok': False, 'message': f'La mesa {mesa_destino.numero} ya tiene un pedido abierto.'},
                status=409,
            )

        pedidos = list(
            VGPedido.objects
            .select_for_update()
            .filter(usuario=request.user, mesa_id=mesa_origen_id, estado__in=MESA_ABIERTA_ORDER_STATES)
        )
        if not pedidos:
            return _auth_response(
                {'ok': False, 'message': 'No hay pedidos abiertos en esa mesa para mover.'},
                status=404,
            )

        for pedido in pedidos:
            pedido.mesa = mesa_destino
            pedido.actualizado_por = request.user
            pedido.save(update_fields=['mesa', 'actualizado_por', 'fecha_actualizacion'])

    return _auth_response({
        'ok': True,
        'message': f'{len(pedidos)} pedido(s) movido(s) a la Mesa {mesa_destino.numero}.',
        'mesa_destino_id': mesa_destino.id,
        'mesa_destino_numero': mesa_destino.numero,
        'pedidos_movidos': len(pedidos),
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
        'entregado': {'cancelado'},
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

        # Cancelar desde 'entregado' (el pedido ya llegó a la mesa) es la cancelación
        # "desde caja" — solo antes de cobrar, nunca después: 'pagado' no admite
        # ninguna transición (ver `transitions` arriba), así que un pedido ya
        # facturado/cobrado no se puede tocar por acá. Reservada a quien maneja caja,
        # no a cualquier mesero — ver acuerdo con el usuario, 2026-09.
        if pedido.estado == 'entregado' and next_state == 'cancelado':
            if not (_is_admin_user(request.user) or _is_cajera_user(request.user) or _is_analista_user(request.user)):
                return _auth_response({
                    'ok': False,
                    'message': 'No tienes permiso para cancelar un pedido desde caja.',
                }, status=403)

        previous_estado = pedido.estado
        pedido.estado = next_state
        pedido.actualizado_por = request.user
        update_fields = ['estado', 'actualizado_por', 'fecha_actualizacion']
        if next_state == 'en_preparacion':
            # Arranca (o reinicia, si viene de "Volver a preparar" desde 'listo')
            # el cronómetro del avance automático — ver
            # _avanzar_pedidos_en_preparacion_vencidos.
            pedido.fecha_inicio_preparacion = timezone.now()
            update_fields.append('fecha_inicio_preparacion')
        elif next_state == 'listo':
            # Arranca el cronómetro del avance automático a 'entregado' — ver
            # _avanzar_pedidos_listos_vencidos.
            pedido.fecha_listo = timezone.now()
            update_fields.append('fecha_listo')
        pedido.save(update_fields=update_fields)

        if next_state == 'en_preparacion':
            pedido.detalles.filter(estado='pendiente').update(estado='en_preparacion')
        elif next_state == 'listo':
            pedido.detalles.filter(estado__in=['pendiente', 'en_preparacion']).update(estado='listo')
        elif next_state == 'entregado':
            pedido.detalles.filter(estado='listo').update(estado='entregado')

    _notify_cocina_event('PEDIDO_ACTUALIZADO', pedido, request.user, previous_estado=previous_estado)
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


# Caja solo debe poder cobrar/facturar un pedido una vez que el mesero
# confirmó que ya llegó a la mesa (estado 'entregado') — no apenas cocina lo
# marca 'listo', porque en ese punto todavía puede estar esperando a que lo
# sirvan y no debería poder cobrarse.
BILLABLE_ORDER_STATES = ['entregado']


@csrf_exempt
def pedidos_cobro_view(request):
    if request.method not in ['GET', 'POST']:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not (_is_admin_user(request.user) or _is_cajera_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para cobrar pedidos.'}, status=401)

    if request.method == 'GET':
        pedidos = (
            VGPedido.objects.filter(estado__in=BILLABLE_ORDER_STATES)
            .select_related('mesa', 'cliente', 'usuario')
            .prefetch_related('detalles__producto', 'detalles__adicionales__preparacion', 'detalles__opciones__preparacion', 'detalles__opciones__producto', 'detalles__opciones__grupo')
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
                'detalles__opciones__preparacion', 'detalles__opciones__producto', 'detalles__opciones__grupo',
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

        tasa_cambio_pago = tasa_cambio_para_registro()
        total_cobrado = Decimal('0')
        for pedido in pedidos:
            # El dinero de la nota de entrega se cobra aparte, en uno o varios
            # abonos (ver nota_entrega_abono_view) — acá solo se cierra el
            # pedido (inventario descontado, cocina cerrada), igual que ya
            # hacía _emitir_factura para una factura con saldo pendiente.
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

        # El cobro directo (mesero o cajera) siempre genera una nota de entrega —
        # el recibo de venta sin efecto fiscal que hoy reemplaza a la factura
        # mientras el SENIAT termina de homologar el sistema (ver VGNotaEntrega).
        # Igual que una factura, nace con saldo pendiente por el total: el
        # dinero se registra aparte como uno o varios abonos
        # (nota_entrega_abono_view), no en el momento de la emisión.
        nota_entrega = VGNotaEntrega.objects.create(
            metodo_pago=metodo_pago,
            total=total_cobrado,
            saldo_pendiente=total_cobrado,
            estado='pendiente_pago',
            moneda=metodo_pago.moneda,
            tasa_cambio_referencia=tasa_cambio_pago,
            referencia=referencia,
            creado_por=request.user,
            actualizado_por=request.user,
        )
        nota_entrega.pedidos.set(pedidos)

    try:
        imprimir_nota_entrega_caja(nota_entrega)
    except Exception:
        logger.exception('Fallo al imprimir la nota de entrega %s', nota_entrega.codigo)

    return _auth_response({
        'ok': True,
        'message': f'Se cobraron {len(pedidos)} pedido(s) correctamente.',
        'nota_entrega': {
            'id': nota_entrega.id,
            'codigo': nota_entrega.codigo,
            'referencia': referencia,
            'total': str(total_cobrado),
            'saldo_pendiente': str(nota_entrega.saldo_pendiente),
            'estado': nota_entrega.estado,
            'moneda': metodo_pago.moneda,
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
                'is_owner': _is_owner_user(user),
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
                    'is_owner': _is_owner_user(request.user),
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
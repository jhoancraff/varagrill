"""
Servicios adicionales: lo que se le cobra al cliente junto con su pedido y no es un plato (descorche, decoración,
alquiler de salón, torta de cumpleaños...).

Se parecen al cargo de delivery (ver delivery.py): viven en el propio pedido (VGPedido.cargo_servicios, ya sumado en su
total, con una línea por servicio en VGPedidoServicio), así que cobro, cuenta del cliente, nota de entrega y factura
funcionan igual que siempre. No son productos ni ingredientes: no salen en cocina, no descuentan inventario, no
aparecen en los reportes de productos y margen y NO llevan IVA. Como no tienen costo, lo que se cobra es una entrada neta:
en el estado de resultados pasan completos a la utilidad bruta.

El catálogo (VGServicioAdicional) lo crean el administrador o el contador; el precio es siempre el del catálogo y cada línea
guarda el precio con el que se cobró. Cualquier rol puede agregar servicios a un pedido, uno o varios, y el mismo servicio
más de una vez (cantidad). Un descuento rebaja el total del pedido completo, servicios incluidos.
"""
from decimal import Decimal

from .models import VGPedidoServicio, VGServicioAdicional

CENTAVO = Decimal('0.01')
CANTIDAD_MAXIMA = 99


class ServiciosInvalidos(Exception):
    """Los servicios que llegaron no se pueden usar; el mensaje es para mostrarle a quien registra."""


def serializar_servicio(servicio):
    return {
        'id': servicio.id,
        'nombre': servicio.nombre,
        'descripcion': servicio.descripcion,
        'precio': str(servicio.precio),
        'activo': servicio.activo,
        'orden': servicio.orden,
    }


def serializar_linea(linea):
    return {
        'id': linea.id,
        'servicio_id': linea.servicio_id,
        'nombre': linea.nombre,
        'cantidad': linea.cantidad,
        'precio_unitario': str(linea.precio_unitario),
        'subtotal': str(linea.subtotal),
    }


def serializar_lineas(pedido):
    return [serializar_linea(linea) for linea in pedido.servicios.all()]


def resolver_servicios(raw, pedido_actual=None):
    """
    Valida lo que mandó la pantalla (`servicios`: [{servicio_id, cantidad}, ...]) y decide nombre y precio de cada línea.
    Devuelve una lista de dicts {servicio, nombre, cantidad, precio_unitario, subtotal}; vacía si no llegó nada.

    - El mismo servicio repetido se junta en una sola línea (las cantidades se suman).
    - Un servicio nuevo tiene que existir y estar activo, y se cobra al precio actual del catálogo.
    - Al editar un pedido, un servicio que el pedido YA tenía se conserva con el precio con el que se agregó,
      aunque después se haya desactivado o cambiado de precio.
    """
    if raw in (None, ''):
        return []
    if not isinstance(raw, list):
        raise ServiciosInvalidos('Los servicios adicionales no tienen un formato valido.')

    existentes = {}
    if pedido_actual is not None:
        existentes = {linea.servicio_id: linea for linea in pedido_actual.servicios.all() if linea.servicio_id}

    cantidades = {}
    for entrada in raw:
        if not isinstance(entrada, dict):
            raise ServiciosInvalidos('Los servicios adicionales no tienen un formato valido.')
        try:
            servicio_id = int(entrada.get('servicio_id'))
            cantidad = int(entrada.get('cantidad', 1))
        except (TypeError, ValueError):
            raise ServiciosInvalidos('Hay un servicio adicional con datos invalidos.')
        if cantidad < 1:
            raise ServiciosInvalidos('La cantidad de un servicio adicional debe ser al menos 1.')
        cantidades[servicio_id] = cantidades.get(servicio_id, 0) + cantidad

    catalogo = {s.id: s for s in VGServicioAdicional.objects.filter(pk__in=cantidades.keys())}
    resueltos = []
    for servicio_id, cantidad in cantidades.items():
        if cantidad > CANTIDAD_MAXIMA:
            raise ServiciosInvalidos(f'La cantidad de un servicio adicional no puede pasar de {CANTIDAD_MAXIMA}.')
        servicio = catalogo.get(servicio_id)
        previa = existentes.get(servicio_id)
        if previa is not None:
            nombre, precio = previa.nombre, previa.precio_unitario
        elif servicio is None:
            raise ServiciosInvalidos('Uno de los servicios adicionales ya no existe.')
        elif not servicio.activo:
            raise ServiciosInvalidos(f'El servicio "{servicio.nombre}" ya no esta disponible.')
        else:
            nombre, precio = servicio.nombre, servicio.precio
        resueltos.append({
            'servicio': servicio, 'nombre': nombre, 'cantidad': cantidad, 'precio_unitario': precio,
            'subtotal': (precio * cantidad).quantize(CENTAVO),
        })
    return resueltos


def total_servicios(resueltos):
    return sum((r['subtotal'] for r in resueltos), Decimal('0.00')).quantize(CENTAVO)


def aplicar_servicios(pedido, resueltos):
    """
    Deja en el pedido exactamente estas líneas (borra las que tenía) y actualiza `pedido.cargo_servicios`.
    No guarda el pedido: quien llama recalcula el total y lo guarda.
    """
    pedido.servicios.all().delete()
    for r in resueltos:
        VGPedidoServicio.objects.create(
            pedido=pedido, servicio=r['servicio'], nombre=r['nombre'], cantidad=r['cantidad'],
            precio_unitario=r['precio_unitario'], subtotal=r['subtotal'],
        )
    pedido.cargo_servicios = total_servicios(resueltos)
    return pedido.cargo_servicios

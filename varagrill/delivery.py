"""
Cargo de delivery: lo que se cobra por el envio de un pedido delivery.

No es un producto ni un ingrediente: vive en el propio pedido (VGPedido.cargo_delivery), ya
sumado en su total, asi que cobro, pre-factura y nota de entrega funcionan igual que siempre y
el cargo no aparece en cocina ni en los reportes de productos y margen.

Las tarifas por zona (VGZonaDelivery) las configura el administrador. Al registrar el pedido se
elige una zona y su tarifa se copia al pedido; la cajera (o el administrador) puede cambiar el
monto libremente. Un delivery se cobra una sola vez: las rondas que se agregan despues no lo repiten.
"""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .auth_helpers import _is_admin_user, _is_cajera_user
from .models import VGZonaDelivery

CENTAVO = Decimal('0.01')
MONTO_MAXIMO = Decimal('99999.99')


class CargoDeliveryInvalido(Exception):
    """El cargo o la zona que llegaron no se pueden usar; el mensaje es para mostrarle a quien registra."""


def serializar_zona(zona):
    return {
        'id': zona.id,
        'nombre': zona.nombre,
        'tarifa': str(zona.tarifa),
        'activo': zona.activo,
        'orden': zona.orden,
    }


def puede_cambiar_monto(usuario):
    return _is_admin_user(usuario) or _is_cajera_user(usuario)


def _monto(valor):
    try:
        monto = Decimal(str(valor).strip().replace(',', '.'))
    except (InvalidOperation, ValueError):
        raise CargoDeliveryInvalido('El monto del delivery no es valido.')
    if not monto.is_finite() or monto < 0:
        raise CargoDeliveryInvalido('El monto del delivery no puede ser negativo.')
    if monto > MONTO_MAXIMO:
        raise CargoDeliveryInvalido('El monto del delivery es demasiado grande.')
    return monto.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def resolver_cargo_delivery(data, tipo_pedido, usuario, es_ronda=False, pedido_actual=None):
    """
    Decide cuanto se cobra de delivery en un pedido a partir de lo que mando la pantalla
    (`zona_delivery_id` y/o `cargo_delivery`). Devuelve un dict con los campos del pedido:
    cargo_delivery, zona_delivery, zona_delivery_nombre y tarifa_delivery.

    - Solo un pedido delivery cobra envio; en cualquier otro tipo, y en una ronda agregada a un
      delivery (ya lo pago el pedido original), todo queda en cero.
    - Con una zona y sin monto: se cobra la tarifa de la zona.
    - Con un monto: se cobra ese monto (si hay zona, queda registrada junto con su tarifa, para
      saber que se cambio a mano). Solo caja y administracion pueden cambiarlo; un mesero solo
      puede mandar la tarifa de la zona.
    - Si al editar un pedido no llega ni zona ni monto, se conserva lo que ya tenia.
    Lanza CargoDeliveryInvalido si algo no se puede usar.
    """
    vacio = {'cargo_delivery': Decimal('0.00'), 'zona_delivery': None, 'zona_delivery_nombre': '', 'tarifa_delivery': None}
    if tipo_pedido != 'delivery' or es_ronda:
        return vacio

    manda_zona = data.get('zona_delivery_id') not in (None, '')
    manda_monto = data.get('cargo_delivery') not in (None, '')
    if not manda_zona and not manda_monto:
        if pedido_actual is not None:
            return {
                'cargo_delivery': pedido_actual.cargo_delivery,
                'zona_delivery': pedido_actual.zona_delivery,
                'zona_delivery_nombre': pedido_actual.zona_delivery_nombre,
                'tarifa_delivery': pedido_actual.tarifa_delivery,
            }
        return vacio

    if manda_zona:
        try:
            zona_id = int(data.get('zona_delivery_id'))
        except (TypeError, ValueError):
            raise CargoDeliveryInvalido('La zona de delivery no es valida.')
        misma_zona = pedido_actual is not None and pedido_actual.zona_delivery_id == zona_id
        zona = VGZonaDelivery.objects.filter(pk=zona_id).first()
        if zona is None or (not zona.activo and not misma_zona):
            raise CargoDeliveryInvalido('La zona de delivery no existe o esta inactiva.')
        nombre, tarifa = zona.nombre, zona.tarifa
    elif pedido_actual is not None:
        # Solo cambia el monto: la zona (y su tarifa) que ya tenia el pedido se conservan.
        zona = pedido_actual.zona_delivery
        nombre, tarifa = pedido_actual.zona_delivery_nombre, pedido_actual.tarifa_delivery
    else:
        zona, nombre, tarifa = None, '', None

    if manda_monto:
        cargo = _monto(data.get('cargo_delivery'))
        if not puede_cambiar_monto(usuario) and (tarifa is None or cargo != tarifa):
            raise CargoDeliveryInvalido('Solo caja o administracion puede cambiar el monto del delivery.')
    else:
        cargo = tarifa
    return {
        'cargo_delivery': cargo,
        'zona_delivery': zona,
        'zona_delivery_nombre': nombre,
        'tarifa_delivery': tarifa,
    }


def aplicar_cargo(pedido, cargo):
    """Copia al pedido (sin guardarlo) lo que devolvio resolver_cargo_delivery."""
    pedido.cargo_delivery = cargo['cargo_delivery']
    pedido.zona_delivery = cargo['zona_delivery']
    pedido.zona_delivery_nombre = cargo['zona_delivery_nombre']
    pedido.tarifa_delivery = cargo['tarifa_delivery']


def texto_cargo(pedido):
    """'Delivery (Media)' o 'Delivery' cuando el monto se puso a mano sin zona."""
    if pedido.zona_delivery_nombre:
        return f'Delivery ({pedido.zona_delivery_nombre})'
    return 'Delivery'

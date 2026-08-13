"""
Impresión del recibo de caja (detalle del pedido + montos, para el cliente) en la
impresora térmica USB compartida desde la PC de caja. A diferencia de las 3 impresoras
de cocina —ESC/POS crudo directo por socket al puerto 9100, ver impresion_termica.py—,
esta impresora no tiene puerto de red propio: está conectada por USB a la PC de caja y
compartida a la red mediante el "LPD Print Service" de Windows, que escucha en el
puerto 515 y habla el protocolo LPD/RFC 1179 en vez de aceptar bytes crudos.

El protocolo LPD envuelve el trabajo en un archivo de control (metadatos del trabajo) y
un archivo de datos (el contenido a imprimir), cada uno anunciado con su tamaño y
confirmado por el servidor antes de mandar el siguiente. El archivo de control usa el
formato 'l' ("print file leaving control characters") para pedirle a la cola que imprima
los bytes ESC/POS tal cual, sin reformatear — el equivalente LPD de "impresión cruda".

Sin dependencias externas: solo `socket`, igual que impresion_termica.py.
"""
import logging
import socket

from django.utils import timezone

from .impresion_termica import (
    ALIGN_CENTER,
    ALIGN_LEFT,
    BOLD_OFF,
    BOLD_ON,
    CUT,
    ESC_POS_WCP1252,
    FEED,
    INIT,
    KANJI_OFF,
    LINE_WIDTH,
    _cantidad_label,
    _text,
    _tipo_pedido_label,
)
from .models import VGImpresoraCaja

logger = logging.getLogger(__name__)

LPD_ORIGIN_HOST = 'varagrill'
LPD_CONNECT_TIMEOUT_SECONDS = 5

METODO_PAGO_LABELS = {
    'efectivo': 'Efectivo',
    'tarjeta': 'Tarjeta',
    'transferencia': 'Transferencia',
    'pago_movil': 'Pago móvil',
}


class LpdError(Exception):
    """La impresora/servidor LPD rechazó o cortó la transferencia del trabajo."""


def _recv_ack(sock):
    ack = sock.recv(1)
    if not ack:
        raise LpdError('La impresora cerró la conexión sin responder.')
    if ack != b'\x00':
        raise LpdError(f'La impresora rechazó la operación (código {ack[0]}).')


def enviar_trabajo_lpd(host, puerto, cola, datos, job_id=1, usuario='varagrill', nombre_trabajo='Recibo'):
    """
    Envía `datos` (bytes ESC/POS ya armados) como trabajo de impresión crudo a una cola
    LPD remota (RFC 1179): anuncia y transfiere primero el archivo de control (formato
    'l' = crudo, sin reformatear) y luego el archivo de datos, confirmando cada paso con
    el servidor. `cola` es el nombre exacto de la cola/impresora compartida en Windows.
    """
    job_suffix = f'{job_id % 1000:03d}{LPD_ORIGIN_HOST}'
    data_filename = f'dfA{job_suffix}'
    control_filename = f'cfA{job_suffix}'
    control_file = (
        f'H{LPD_ORIGIN_HOST}\n'
        f'P{usuario}\n'
        f'J{nombre_trabajo}\n'
        f'l{data_filename}\n'
        f'U{data_filename}\n'
        f'N{nombre_trabajo}\n'
    ).encode('ascii', errors='replace')

    with socket.create_connection((host, puerto), timeout=LPD_CONNECT_TIMEOUT_SECONDS) as sock:
        sock.settimeout(LPD_CONNECT_TIMEOUT_SECONDS)

        sock.sendall(b'\x02' + cola.encode('ascii', errors='replace') + b'\n')
        _recv_ack(sock)

        sock.sendall(f'\x02{len(control_file)} {control_filename}\n'.encode('ascii'))
        _recv_ack(sock)
        sock.sendall(control_file + b'\x00')
        _recv_ack(sock)

        sock.sendall(f'\x03{len(datos)} {data_filename}\n'.encode('ascii'))
        _recv_ack(sock)
        sock.sendall(datos + b'\x00')
        _recv_ack(sock)


def _render_recibo_item(detalle):
    out = bytearray()
    out += _text(f'{_cantidad_label(detalle)} {detalle.producto.nombre}') + FEED
    if detalle.notas:
        out += _text(f'  - {detalle.notas}') + FEED
    out += _text(f'  ${detalle.subtotal:.2f}') + FEED
    for adicional in detalle.adicionales.all():
        out += _text(f'  + {adicional.cantidad}x {adicional.preparacion.nombre}  ${adicional.subtotal:.2f}') + FEED
    return bytes(out)


def _build_recibo_bytes(pedidos, metodo_pago, referencia, total):
    hora = timezone.localtime().strftime('%d/%m/%Y %H:%M')
    metodo_label = METODO_PAGO_LABELS.get(metodo_pago, metodo_pago)

    out = bytearray()
    out += INIT
    out += KANJI_OFF
    out += ESC_POS_WCP1252
    out += ALIGN_CENTER
    out += _text('VARAGRILL') + FEED
    out += _text('RECIBO DE CAJA') + FEED
    out += ALIGN_LEFT
    out += _text('-' * LINE_WIDTH) + FEED
    out += _text(f'Referencia: {referencia}') + FEED
    out += _text(hora) + FEED

    subtotal_total = 0
    impuesto_total = 0
    descuento_total = 0
    propina_total = 0

    for pedido in pedidos:
        mesa_label = f'Mesa {pedido.mesa.numero}' if pedido.mesa else 'Sin mesa'
        out += _text('-' * LINE_WIDTH) + FEED
        out += _text(f'Pedido #{pedido.id} - {mesa_label} - {_tipo_pedido_label(pedido.tipo_pedido)}') + FEED
        for detalle in pedido.detalles.all():
            out += _render_recibo_item(detalle)
        subtotal_total += pedido.subtotal
        impuesto_total += pedido.impuesto
        descuento_total += pedido.descuento
        propina_total += pedido.propina

    out += _text('-' * LINE_WIDTH) + FEED
    out += _text(f'Subtotal: ${subtotal_total:.2f}') + FEED
    if impuesto_total > 0:
        out += _text(f'Impuesto: ${impuesto_total:.2f}') + FEED
    if descuento_total > 0:
        out += _text(f'Descuento: -${descuento_total:.2f}') + FEED
    if propina_total > 0:
        out += _text(f'Propina: ${propina_total:.2f}') + FEED
    out += BOLD_ON
    out += _text(f'TOTAL: ${total:.2f}') + FEED
    out += BOLD_OFF
    out += _text(f'Metodo de pago: {metodo_label}') + FEED
    out += ALIGN_CENTER
    out += _text('¡Gracias por su visita!') + FEED
    out += ALIGN_LEFT

    out += FEED + FEED + FEED + FEED
    out += CUT
    return bytes(out)


def imprimir_recibo_caja(pedidos, metodo_pago, referencia, total):
    """
    Imprime el recibo combinado de caja para los `pedidos` cobrados en una misma
    operación. Si la impresora de caja no está configurada o está apagada, no hace
    nada (silencioso) — llamar siempre envuelto en try/except desde el caller, igual
    que imprimir_comandas_pedido, para que un fallo de impresión no eche para atrás el
    cobro ya registrado.
    """
    config = VGImpresoraCaja.obtener_config()
    if config is None or not config.activo:
        return
    if not config.ip or not config.cola:
        logger.warning('Impresora de caja activa pero sin IP/cola configurada; se omite el recibo.')
        return

    destino = f'{config.ip}:{config.puerto} (cola "{config.cola}")'
    try:
        ticket = _build_recibo_bytes(pedidos, metodo_pago, referencia, total)
        logger.info('Enviando recibo de caja %s a %s (%s bytes)', referencia, destino, len(ticket))
        enviar_trabajo_lpd(
            config.ip, config.puerto, config.cola, ticket,
            job_id=pedidos[0].id if pedidos else 1,
            nombre_trabajo=f'Recibo {referencia}',
        )
        logger.info('Recibo de caja %s enviado a %s', referencia, destino)
    except Exception:
        logger.exception('No se pudo imprimir el recibo de caja %s hacia %s', referencia, destino)
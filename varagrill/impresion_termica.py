"""
Impresión de comandas en impresoras térmicas de red (ESC/POS crudo por TCP/9100),
una por categoría de producto (ej: barra para Jugos/Licores, cocina para Carnes/Pollos).

Sin dependencias externas: solo `socket` de la librería estándar. Cada impresora vive
en la misma LAN que el servidor, así que basta con abrir un socket a su IP fija y
mandarle los bytes ESC/POS — el mismo mecanismo que `printf ... | nc <ip> 9100`.
"""
import socket
import logging

logger = logging.getLogger(__name__)

ESC = b'\x1b'
GS = b'\x1d'
FS = b'\x1c'
INIT = ESC + b'@'
BOLD_ON = ESC + b'E' + b'\x01'
BOLD_OFF = ESC + b'E' + b'\x00'
ALIGN_CENTER = ESC + b'a' + b'\x01'
ALIGN_LEFT = ESC + b'a' + b'\x00'
DOUBLE_SIZE = GS + b'!' + b'\x11'
NORMAL_SIZE = GS + b'!' + b'\x00'
CUT = b''
FEED = b'\n'

ENCODING = 'cp1252'
LINE_WIDTH = 32
CONNECT_TIMEOUT_SECONDS = 4

# Según la página web del equipo DP80UL-01, el code page activo es WCP1252 (16).
ESC_POS_WCP1252 = ESC + b't' + b'\x10'
KANJI_OFF = FS + b'.'


def _text(value):
    return str(value or '').encode(ENCODING, errors='replace')


def _tipo_pedido_label(tipo_pedido):
    return {'llevar': 'Para llevar', 'delivery': 'Delivery'}.get(tipo_pedido, 'Local')


def _group_detalles_por_plato(detalles):
    """Agrupa por grupo_armado (ver 'armar plato'), igual que kitchenTicket.js en el frontend."""
    grupos = {}
    sueltos = []
    for detalle in detalles:
        if detalle.grupo_armado:
            grupos.setdefault(detalle.grupo_armado, []).append(detalle)
        else:
            sueltos.append(detalle)
    platos = [(grupo_id, grupos[grupo_id]) for grupo_id in sorted(grupos)]
    return platos, sueltos


def _cantidad_label(detalle):
    if detalle.peso_gramos:
        return f'{int(detalle.peso_gramos)} g'
    return f'{detalle.cantidad}x'


def _render_detalle(detalle):
    out = bytearray()
    out += _text(f'{_cantidad_label(detalle)} {detalle.producto.nombre}') + FEED
    if detalle.notas:
        out += _text(f'  - {detalle.notas}') + FEED
    for adicional in detalle.adicionales.all():
        out += _text(f'  + {adicional.cantidad}x {adicional.preparacion.nombre}') + FEED
    return bytes(out)


def _build_ticket_bytes(pedido, categoria, detalles):
    mesa_label = f'Mesa {pedido.mesa.numero}' if pedido.mesa else 'Sin mesa'
    hora = pedido.fecha_creacion.strftime('%d/%m %H:%M')

    out = bytearray()
    # Secuencia mínima robusta para este equipo: reset ESC/POS + salir de modo
    # Kanji + fijar code page Windows-1252 antes de enviar texto.
    out += INIT
    out += KANJI_OFF
    out += ESC_POS_WCP1252
    out += _text('VARAGRILL') + FEED
    out += _text(categoria.nombre.upper()) + FEED
    out += _text('-' * LINE_WIDTH) + FEED
    out += _text(f'Pedido #{pedido.id}') + FEED
    out += _text(f'{mesa_label} - {_tipo_pedido_label(pedido.tipo_pedido)}') + FEED
    out += _text(f'Mesero: {pedido.usuario.username}') + FEED
    out += _text(hora) + FEED
    out += _text('-' * LINE_WIDTH) + FEED

    platos, sueltos = _group_detalles_por_plato(detalles)
    for grupo_id, items in platos:
        out += _text(f'-- Plato {grupo_id} --') + FEED
        for detalle in items:
            out += _render_detalle(detalle)
    for detalle in sueltos:
        out += _render_detalle(detalle)

    if pedido.notas:
        out += _text('-' * LINE_WIDTH) + FEED
        out += _text(f'Nota: {pedido.notas}') + FEED

    out += FEED + FEED + FEED + FEED
    out += CUT
    return bytes(out)


def imprimir_comandas_pedido(pedido):
    """
    Imprime una comanda por cada categoría con impresora asignada, con solo las líneas
    de esa categoría. Si una impresora está apagada o inalcanzable, esa comanda se
    omite sin afectar a las demás ni al registro del pedido (llamar siempre envuelto
    en try/except desde el caller, igual que send_whatsapp_new_order_alert).
    """
    detalles = list(
        pedido.detalles
        .select_related('producto__categoria')
        .prefetch_related('adicionales__preparacion')
        .all()
    )
    if not detalles:
        return

    por_categoria = {}
    for detalle in detalles:
        categoria = detalle.producto.categoria
        if categoria is None:
            continue
        por_categoria.setdefault(categoria.id, (categoria, []))[1].append(detalle)

    for categoria, items in por_categoria.values():
        if not categoria.ip_impresora:
            continue
        try:
            ticket = _build_ticket_bytes(pedido, categoria, items)
            with socket.create_connection(
                (categoria.ip_impresora, categoria.puerto_impresora),
                timeout=CONNECT_TIMEOUT_SECONDS,
            ) as conexion:
                conexion.sendall(ticket)
        except OSError as error:
            logger.warning(
                'No se pudo imprimir pedido %s en categoria %s hacia %s:%s (%s)',
                pedido.id,
                categoria.nombre,
                categoria.ip_impresora,
                categoria.puerto_impresora,
                error,
            )
            continue
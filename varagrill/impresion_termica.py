"""
Impresión de comandas en impresoras térmicas de red (ESC/POS crudo por TCP/9100),
una por impresora física (ip:puerto). Las categorías de producto que comparten la
misma impresora (ej: Carnes y Guarniciones apuntando a la impresora de cocina) se
combinan en un solo ticket, para que un plato armado con líneas de varias categorías
no salga partido en dos comandas.

Sin dependencias externas: solo `socket` de la librería estándar. Cada impresora vive
en la misma LAN que el servidor, así que basta con abrir un socket a su IP fija y
mandarle los bytes ESC/POS — el mismo mecanismo que `printf ... | nc <ip> 9100`.
"""
import socket
import time
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
DOUBLE_HEIGHT = GS + b'!' + b'\x01'
NORMAL_SIZE = GS + b'!' + b'\x00'
CUT = GS + b'V' + b'\x00'
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
        out += _text(f'  * {detalle.notas}') + FEED
    for adicional in detalle.adicionales.all():
        out += _text(f'  + {adicional.cantidad}x {adicional.preparacion.nombre}') + FEED
    return bytes(out)


def _build_ticket_bytes(pedido, categorias, detalles):
    mesa_label = f'Mesa {pedido.mesa.numero}' if pedido.mesa else 'Sin mesa'
    hora = pedido.fecha_creacion.strftime('%d/%m %H:%M')
    # Un mismo ticket puede combinar varias categorías cuando comparten impresora
    # (ej: Carnes + Guarniciones + Entradas en la impresora de cocina). Ya no se
    # etiqueta cada línea con su categoría (el título "PLATO N" en negrita ya separa
    # cada plato); este encabezado solo indica qué estación imprimió el ticket.
    encabezado = ' / '.join(sorted(c.nombre.upper() for c in categorias))

    out = bytearray()
    # Secuencia mínima robusta para este equipo: reset ESC/POS + salir de modo
    # Kanji + fijar code page Windows-1252 antes de enviar texto.
    out += INIT
    out += KANJI_OFF
    out += ESC_POS_WCP1252
    out += ALIGN_CENTER
    out += BOLD_ON
    out += _text('VARAGRILL') + FEED
    out += BOLD_OFF
    out += _text(encabezado) + FEED
    out += ALIGN_LEFT
    out += _text('=' * LINE_WIDTH) + FEED
    # Pedido y mesa en negrita y doble alto: son el primer dato que ubica el cocinero
    # al recibir la comanda.
    out += BOLD_ON + DOUBLE_HEIGHT
    out += _text(f'Pedido #{pedido.id}') + FEED
    out += _text(mesa_label) + FEED
    out += NORMAL_SIZE + BOLD_OFF
    out += _text(_tipo_pedido_label(pedido.tipo_pedido)) + FEED
    out += _text(f'Mesero: {pedido.usuario.username}') + FEED
    out += _text(hora) + FEED
    out += _text('=' * LINE_WIDTH) + FEED

    # Solo los platos armados (grupo_armado) llevan título "PLATO N" grande y en
    # negrita; los ítems sueltos que no se armaron como plato se listan tal cual, sin
    # ese título, para no confundirlos con un plato armado. Cada bloque se separa del
    # siguiente por una línea punteada.
    platos, sueltos = _group_detalles_por_plato(detalles)
    primer_bloque = True
    for numero_plato, (_grupo_id, items) in enumerate(platos, start=1):
        if not primer_bloque:
            out += _text('-' * LINE_WIDTH) + FEED
        primer_bloque = False
        out += BOLD_ON + DOUBLE_HEIGHT
        out += _text(f'PLATO {numero_plato}') + FEED
        out += NORMAL_SIZE + BOLD_OFF
        for detalle in items:
            out += _render_detalle(detalle)
    for detalle in sueltos:
        if not primer_bloque:
            out += _text('-' * LINE_WIDTH) + FEED
        primer_bloque = False
        out += _render_detalle(detalle)

    if pedido.notas:
        out += _text('=' * LINE_WIDTH) + FEED
        out += _text(f'Nota: {pedido.notas}') + FEED

    out += FEED + FEED + FEED + FEED
    out += CUT
    return bytes(out)


def imprimir_comandas_pedido(pedido):
    """
    Imprime una comanda por cada impresora física con categorías asignadas (ip:puerto),
    combinando en un solo ticket todas las categorías que comparten esa impresora —
    así un plato armado con líneas de varias categorías (ej: churrasco de Carnes +
    yuca de Guarniciones) sale en un único ticket en vez de uno por categoría. Si una
    impresora está apagada o inalcanzable, esa comanda se omite sin afectar a las
    demás ni al registro del pedido (llamar siempre envuelto en try/except desde el
    caller, igual que send_whatsapp_new_order_alert).
    """
    detalles = list(
        pedido.detalles
        .select_related('producto__categoria')
        .prefetch_related('adicionales__preparacion')
        .all()
    )
    if not detalles:
        return

    por_destino = {}
    for detalle in detalles:
        categoria = detalle.producto.categoria
        if categoria is None or not categoria.ip_impresora:
            continue
        destino_key = (categoria.ip_impresora, categoria.puerto_impresora)
        entry = por_destino.setdefault(destino_key, {'categorias': {}, 'detalles': []})
        entry['categorias'][categoria.id] = categoria
        entry['detalles'].append(detalle)

    for (ip_impresora, puerto_impresora), datos in por_destino.items():
        categorias = list(datos['categorias'].values())
        items = datos['detalles']
        destino = f'{ip_impresora}:{puerto_impresora}'
        nombres_categorias = ', '.join(c.nombre for c in categorias)
        try:
            ticket = _build_ticket_bytes(pedido, categorias, items)
            logger.info(
                'Enviando comanda pedido %s categorias [%s] a %s (%s bytes)',
                pedido.id, nombres_categorias, destino, len(ticket),
            )
            with socket.create_connection(
                (ip_impresora, puerto_impresora),
                timeout=CONNECT_TIMEOUT_SECONDS,
            ) as conexion:
                conexion.sendall(ticket)
                # Algunas impresoras térmicas de red (controladores clon) necesitan un
                # respiro entre el sendall() y el cierre del socket para volcar su
                # buffer de recepción al cabezal antes de que la conexión se corte;
                # cerrar de inmediato puede producir un ticket en blanco.
                conexion.shutdown(socket.SHUT_WR)
                time.sleep(0.3)
            logger.info('Comanda pedido %s categorias [%s] enviada a %s', pedido.id, nombres_categorias, destino)
        except Exception:
            logger.exception(
                'No se pudo imprimir pedido %s en categorias [%s] hacia %s',
                pedido.id, nombres_categorias, destino,
            )
            continue
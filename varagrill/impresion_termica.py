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


def _cantidad_label(detalle):
    if detalle.peso_gramos:
        return f'{int(detalle.peso_gramos)} g'
    return f'{detalle.cantidad}x'


def _group_detalles_por_plato(detalles):
    """Agrupa VGDetallePedido por grupo_armado (ver 'armar plato'). Usado por el recibo de
    caja (impresion_lpd.py), que es un solo ticket consolidado sin repartir por estación —
    a diferencia de _group_items_por_plato, que agrupa los ítems YA separados por destino
    de esta comanda de cocina."""
    grupos = {}
    sueltos = []
    for detalle in detalles:
        if detalle.grupo_armado:
            grupos.setdefault(detalle.grupo_armado, []).append(detalle)
        else:
            sueltos.append(detalle)
    platos = [(grupo_id, grupos[grupo_id]) for grupo_id in sorted(grupos)]
    return platos, sueltos


def _destino_categoria(categoria):
    """(ip, puerto) de la impresora de esta categoría, o None si no tiene una asignada
    (una categoría sin IP simplemente no imprime nada — mismo criterio ya usado en toda
    la app, ver AnalysPrintersPage)."""
    if categoria is None or not categoria.ip_impresora:
        return None
    return (categoria.ip_impresora, categoria.puerto_impresora)


def _render_detalle_principal(detalle):
    """
    Línea principal de un detalle (cantidad/peso + nombre + notas + adicionales +
    opciones de grupos CURADOS). Las opciones de grupos DINÁMICOS (categoria_opciones,
    ej. un acompañante elegido de Guarniciones) quedan afuera a propósito: esas se
    imprimen aparte, en la comanda de la categoría de ESE acompañante, ver
    _render_acompanante y _collect_print_items.
    """
    out = bytearray()
    out += _text(f'{_cantidad_label(detalle)} {detalle.producto.nombre}') + FEED
    if detalle.notas:
        out += _text(f'  * {detalle.notas}') + FEED
    for opcion in detalle.opciones.all():
        if opcion.producto_id:
            continue
        out += _text(f'  » {opcion.grupo_nombre}: {opcion.preparacion.nombre}') + FEED
    for adicional in detalle.adicionales.all():
        out += _text(f'  + {adicional.cantidad}x {adicional.preparacion.nombre}') + FEED
    return bytes(out)


def _render_acompanante(opcion):
    """Línea de un acompañante de grupo dinámico (VGDetallePedidoOpcion.producto), que
    imprime en su propia comanda en vez de pegado a la línea principal del plato."""
    out = bytearray()
    out += _text(f'{opcion.grupo_nombre}: {opcion.producto.nombre}') + FEED
    return bytes(out)


def _collect_print_items(detalles):
    """
    Arma la lista de ítems a imprimir a partir de los detalles del pedido: uno por línea
    principal (ruteado según la categoría de ESE producto) y uno aparte por cada
    acompañante de un grupo dinámico (ej. "Yuca al vapor" elegida de Guarniciones para
    acompañar una Punta trasera) — así la carne sale en la comanda de Parrilla y el
    acompañante en la de Cocina, aunque vengan en la misma línea de pedido. Los
    acompañantes de grupos curados (preparacion, sin producto — ej. Arepas/Casabe) NO
    generan un ítem aparte: siguen impresos pegados a la línea principal, igual que
    siempre, dentro de _render_detalle_principal.

    Cada ítem: {'destino': (ip, puerto) | None, 'categoria': VGCategoriaProducto | None,
                'grupo_armado': int | None, 'render': bytes}.
    """
    items = []
    for detalle in detalles:
        categoria = detalle.producto.categoria
        items.append({
            'destino': _destino_categoria(categoria),
            'categoria': categoria,
            'grupo_armado': detalle.grupo_armado,
            'render': _render_detalle_principal(detalle),
        })
        for opcion in detalle.opciones.all():
            if not opcion.producto_id:
                continue
            acomp_categoria = opcion.producto.categoria
            items.append({
                'destino': _destino_categoria(acomp_categoria),
                'categoria': acomp_categoria,
                'grupo_armado': detalle.grupo_armado,
                'render': _render_acompanante(opcion),
            })
    return items


def _group_items_por_plato(items):
    """Agrupa por grupo_armado (ver 'armar plato'), igual que kitchenTicket.js en el frontend."""
    grupos = {}
    sueltos = []
    for item in items:
        if item['grupo_armado']:
            grupos.setdefault(item['grupo_armado'], []).append(item)
        else:
            sueltos.append(item)
    platos = [(grupo_id, grupos[grupo_id]) for grupo_id in sorted(grupos)]
    return platos, sueltos


def _build_ticket_bytes(pedido, categorias, items):
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
    # siguiente por una línea punteada. El número de plato usado en el título es el
    # grupo_armado real (no una posición relativa a este ticket): un plato puede
    # repartirse entre varias comandas (ej. carne en Parrilla, acompañante en Cocina) y
    # así el cocinero y el parrillero ven el mismo "PLATO N" para el mismo plato.
    platos, sueltos = _group_items_por_plato(items)
    primer_bloque = True
    for grupo_id, plato_items in platos:
        if not primer_bloque:
            out += _text('-' * LINE_WIDTH) + FEED
        primer_bloque = False
        out += BOLD_ON + DOUBLE_HEIGHT
        out += _text(f'PLATO {grupo_id}') + FEED
        out += NORMAL_SIZE + BOLD_OFF
        for item in plato_items:
            out += item['render']
    for item in sueltos:
        if not primer_bloque:
            out += _text('-' * LINE_WIDTH) + FEED
        primer_bloque = False
        out += item['render']

    if pedido.notas:
        out += _text('=' * LINE_WIDTH) + FEED
        out += _text(f'Nota: {pedido.notas}') + FEED

    out += FEED + FEED + FEED + FEED
    out += CUT
    return bytes(out)


def imprimir_comandas_pedido(pedido):
    """
    Imprime una comanda por cada impresora física con ítems asignados (ip:puerto),
    combinando en un solo ticket todo lo que comparte esa impresora — así un plato
    armado con líneas de varias categorías (ej: churrasco de Carnes + yuca de
    Guarniciones) sale en un único ticket cuando comparten impresora, o repartido en
    varios cuando cada parte tiene su propia estación (ej: carne en Parrilla,
    acompañante dinámico en Cocina — ver _collect_print_items). Si una impresora está
    apagada o inalcanzable, esa comanda se omite sin afectar a las demás ni al registro
    del pedido (llamar siempre envuelto en try/except desde el caller, igual que
    send_whatsapp_new_order_alert).
    """
    detalles = list(
        pedido.detalles
        .select_related('producto__categoria')
        .prefetch_related(
            'adicionales__preparacion', 'opciones__preparacion', 'opciones__producto__categoria',
        )
        .all()
    )
    if not detalles:
        return

    items = _collect_print_items(detalles)

    por_destino = {}
    for item in items:
        if item['destino'] is None:
            continue
        entry = por_destino.setdefault(item['destino'], {'categorias': {}, 'items': []})
        if item['categoria'] is not None:
            entry['categorias'][item['categoria'].id] = item['categoria']
        entry['items'].append(item)

    for (ip_impresora, puerto_impresora), datos in por_destino.items():
        categorias = list(datos['categorias'].values())
        items_destino = datos['items']
        destino = f'{ip_impresora}:{puerto_impresora}'
        nombres_categorias = ', '.join(c.nombre for c in categorias)
        try:
            ticket = _build_ticket_bytes(pedido, categorias, items_destino)
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

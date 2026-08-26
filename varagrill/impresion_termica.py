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


def _render_detalle_principal(detalle, cantidad_override=None):
    """
    Línea principal de un detalle (cantidad/peso + nombre + notas + adicionales +
    opciones de grupos CURADOS). Las opciones de grupos DINÁMICOS (categoria_opciones,
    ej. un acompañante elegido de Guarniciones) quedan afuera a propósito: esas se
    imprimen aparte, en la comanda de la categoría de ESE acompañante, ver
    _render_acompanante y _collect_print_items.

    `cantidad_override`, si viene, reemplaza la cantidad/peso propios de ESTE detalle por
    un conteo consolidado (ver _consolidar_items) — usado cuando el mismo ítem suelto se
    repite varias veces en el pedido y se quiere imprimir una sola línea "Nx nombre" en
    vez de una línea por repetición.
    """
    out = bytearray()
    etiqueta = f'{cantidad_override}x' if cantidad_override is not None else _cantidad_label(detalle)
    out += _text(f'{etiqueta} {detalle.producto.nombre}') + FEED
    if detalle.notas:
        out += _text(f'  * {detalle.notas}') + FEED
    for opcion in detalle.opciones.all():
        if opcion.producto_id:
            continue
        out += _text(f'  » {opcion.grupo_nombre}: {opcion.preparacion.nombre}') + FEED
    for adicional in detalle.adicionales.all():
        out += _text(f'  + {adicional.cantidad}x {adicional.preparacion.nombre}') + FEED
    return bytes(out)


def _render_acompanante(opcion, cantidad=1):
    """Línea de un acompañante de grupo dinámico (VGDetallePedidoOpcion.producto), que
    imprime en su propia comanda en vez de pegado a la línea principal del plato.
    `cantidad` > 1 cuando el mismo acompañante se consolidó porque varios platos armados
    del mismo pedido eligieron la misma guarnición (ver _consolidar_items) — ej. 4 platos
    con "Yuca al vapor" de acompañante imprimen una sola línea "4x Yuca al vapor" en vez
    de repetirse dentro de cada bloque "PLATO N"."""
    out = bytearray()
    prefijo = f'{cantidad}x ' if cantidad != 1 else ''
    out += _text(f'{prefijo}{opcion.producto.nombre}') + FEED
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
                'grupo_armado': int | None, 'tipo': 'principal' | 'acompanante',
                'detalle': VGDetallePedido | None, 'opcion': VGDetallePedidoOpcion | None}.
    """
    items = []
    for detalle in detalles:
        categoria = detalle.producto.categoria
        items.append({
            'destino': _destino_categoria(categoria),
            'categoria': categoria,
            'grupo_armado': detalle.grupo_armado,
            'tipo': 'principal',
            'detalle': detalle,
            'opcion': None,
        })
        for opcion in detalle.opciones.all():
            if not opcion.producto_id:
                continue
            acomp_categoria = opcion.producto.categoria
            items.append({
                'destino': _destino_categoria(acomp_categoria),
                'categoria': acomp_categoria,
                'grupo_armado': detalle.grupo_armado,
                'tipo': 'acompanante',
                'detalle': None,
                'opcion': opcion,
            })
    return items


def _render_item_individual(item):
    """Renderiza un ítem tal cual (sin consolidar), para cuando va dentro de un bloque
    "PLATO N" — ver _split_items_para_ticket."""
    if item['tipo'] == 'acompanante':
        return _render_acompanante(item['opcion'])
    return _render_detalle_principal(item['detalle'])


def _split_items_para_ticket(items):
    """
    Separa los ítems YA filtrados para un ticket (una impresora/estación) en bloques
    "PLATO N" y en un grupo consolidable.

    Un plato armado (grupo_armado) solo conserva su bloque "PLATO N" en ESTE ticket
    cuando aporta más de un ítem a este mismo ticket — el caso real es una impresora que
    combina varias categorías (ej. Carnes + Guarniciones en una sola impresora de cocina),
    donde vale la pena ver "PLATO 1: Churrasco / Yuca al vapor" junto para no partir la
    composición del plato. Si en cambio cada categoría tiene su propia impresora (lo más
    común), esta estación solo recibe UN ítem de cada plato armado (ej. solo la guarnición,
    porque la carne se fue a la impresora de Parrilla) — ese ítem suelto en este ticket
    entra al grupo consolidable igual que cualquier guarnición pedida aparte, así 1, 2, 3
    o 4 platos que eligieron la misma guarnición terminan en una sola línea "Nx nombre" en
    vez de un "PLATO N" por cada uno.
    """
    por_grupo = {}
    consolidables = []
    for item in items:
        if item['grupo_armado']:
            por_grupo.setdefault(item['grupo_armado'], []).append(item)
        else:
            consolidables.append(item)

    platos = []
    for grupo_id, grupo_items in por_grupo.items():
        if len(grupo_items) > 1:
            platos.append((grupo_id, grupo_items))
        else:
            consolidables.extend(grupo_items)
    platos.sort(key=lambda par: par[0])
    return platos, consolidables


def _clave_consolidacion(item):
    """Identidad de un ítem consolidable para agrupar repeticiones: mismo producto y
    mismas personalizaciones (notas/adicionales/opciones curadas) — si algo lo distingue
    (ej. "sin sal" en una sola de cuatro yucas), esa fila queda en su propio grupo en vez
    de mezclarse con las demás."""
    if item['tipo'] == 'acompanante':
        return ('acompanante', item['opcion'].producto_id)
    detalle = item['detalle']
    adicionales = tuple(sorted((a.preparacion_id, a.cantidad) for a in detalle.adicionales.all()))
    opciones_curadas = tuple(sorted(
        (o.grupo_nombre, o.preparacion_id) for o in detalle.opciones.all() if not o.producto_id
    ))
    return ('principal', detalle.producto_id, detalle.notas or '', adicionales, opciones_curadas)


def _cantidad_item(item):
    if item['tipo'] == 'acompanante':
        return 1
    return item['detalle'].cantidad or 1


def _consolidar_items(items):
    """
    Agrupa ítems consolidables idénticos (mismo producto y misma personalización) y los
    combina en una sola línea "Nx nombre" — así si el mismo pedido pide 1, 2, 3 o 4
    guarniciones del mismo tipo, sea como plato suelto o como acompañante de platos
    armados distintos, la comanda de esa estación imprime un solo renglón consolidado en
    vez de repetirlo una vez por cada aparición. Si solo hay una fila para ese producto,
    se imprime igual que siempre (con su cantidad/peso propio, sin forzar el prefijo "1x").
    Devuelve la lista de renders (bytes), en el orden en que cada producto apareció primero.
    """
    grupos = {}
    orden = []
    for item in items:
        clave = _clave_consolidacion(item)
        if clave not in grupos:
            grupos[clave] = {'item': item, 'cantidad_total': 0, 'num_filas': 0}
            orden.append(clave)
        grupos[clave]['cantidad_total'] += _cantidad_item(item)
        grupos[clave]['num_filas'] += 1

    renders = []
    for clave in orden:
        grupo = grupos[clave]
        item = grupo['item']
        hay_repeticion = grupo['num_filas'] > 1
        if item['tipo'] == 'acompanante':
            cantidad = grupo['cantidad_total'] if hay_repeticion else 1
            renders.append(_render_acompanante(item['opcion'], cantidad))
        else:
            cantidad_override = grupo['cantidad_total'] if hay_repeticion else None
            renders.append(_render_detalle_principal(item['detalle'], cantidad_override=cantidad_override))
    return renders


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

    # Un plato armado solo conserva su título "PLATO N" en este ticket cuando aporta más
    # de un ítem a ESTE ticket (ver _split_items_para_ticket) — el caso de una impresora
    # que combina varias categorías del mismo plato. Todo lo demás (sueltos, y platos
    # armados de los que este ticket solo recibió una línea) se consolida (ver
    # _consolidar_items): si el mismo producto se repite varias veces en el pedido — sea
    # la guarnición de 4 platos distintos o 4 yucas pedidas sueltas — se imprime una sola
    # línea "Nx nombre" en vez de repetirla.
    platos, consolidables = _split_items_para_ticket(items)
    renders_consolidados = _consolidar_items(consolidables)

    primer_bloque = True
    for grupo_id, plato_items in platos:
        if not primer_bloque:
            out += _text('-' * LINE_WIDTH) + FEED
        primer_bloque = False
        out += BOLD_ON + DOUBLE_HEIGHT
        out += _text(f'PLATO {grupo_id}') + FEED
        out += NORMAL_SIZE + BOLD_OFF
        for item in plato_items:
            out += _render_item_individual(item)
    for render in renders_consolidados:
        if not primer_bloque:
            out += _text('-' * LINE_WIDTH) + FEED
        primer_bloque = False
        out += render

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

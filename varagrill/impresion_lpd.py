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
import re
import socket
from decimal import Decimal

from django.utils import timezone

from .delivery import texto_cargo
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
    _group_detalles_por_plato,
    _text,
    _tipo_pedido_label,
)
from .models import VGDatosFiscalesEmisor, VGImpresoraCaja, VGTasaCambio
from .ticket_grafico import Ticket

logger = logging.getLogger(__name__)

# Referencias que el sistema inventa al cobrar sin referencia del cliente: no dicen nada, no se imprimen.
_REFERENCIA_AUTOGENERADA = re.compile(r'^(COBRO|ABONO)-\d{14}-\d+$')

LPD_ORIGIN_HOST = 'varagrill'
# Windows puede tardar varios segundos en despertar el spooler LPD y confirmar
# cada archivo del trabajo; el límite aplica a conexión y a cada confirmación.
LPD_CONNECT_TIMEOUT_SECONDS = 15


class LpdError(Exception):
    """La impresora/servidor LPD rechazó o cortó la transferencia del trabajo."""


def _recv_ack(sock, etapa):
    try:
        ack = sock.recv(1)
    except socket.timeout as exc:
        raise LpdError(f'Tiempo de espera agotado esperando confirmación en la etapa "{etapa}".') from exc
    except OSError as exc:
        raise LpdError(f'Error de red en la etapa "{etapa}": {exc}.') from exc
    if not ack:
        raise LpdError(f'El servidor LPD cerró la conexión sin responder en la etapa "{etapa}".')
    if ack != b'\x00':
        raise LpdError(
            f'El servidor LPD rechazó la etapa "{etapa}" con código {ack[0]} '
            f'(0x{ack[0]:02x}).'
        )


def _enviar_y_confirmar(sock, payload, etapa):
    try:
        sock.sendall(payload)
    except socket.timeout as exc:
        raise LpdError(f'Tiempo de espera agotado enviando la etapa "{etapa}".') from exc
    except OSError as exc:
        raise LpdError(f'Error de red enviando la etapa "{etapa}": {exc}.') from exc
    _recv_ack(sock, etapa)


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

    try:
        sock_context = socket.create_connection((host, puerto), timeout=LPD_CONNECT_TIMEOUT_SECONDS)
    except socket.timeout as exc:
        raise LpdError(
            f'Tiempo de espera agotado conectando al servidor LPD {host}:{puerto} '
            f'(cola "{cola}").'
        ) from exc
    except OSError as exc:
        raise LpdError(
            f'No se pudo conectar al servidor LPD {host}:{puerto} '
            f'(cola "{cola}"): {exc}.'
        ) from exc

    with sock_context as sock:
        sock.settimeout(LPD_CONNECT_TIMEOUT_SECONDS)

        _enviar_y_confirmar(
            sock,
            b'\x02' + cola.encode('ascii', errors='replace') + b'\n',
            'seleccionar cola',
        )

        _enviar_y_confirmar(
            sock,
            f'\x02{len(control_file)} {control_filename}\n'.encode('ascii'),
            'anunciar archivo de control',
        )
        _enviar_y_confirmar(sock, control_file + b'\x00', 'enviar archivo de control')

        _enviar_y_confirmar(
            sock,
            f'\x03{len(datos)} {data_filename}\n'.encode('ascii'),
            'anunciar archivo de datos',
        )
        _enviar_y_confirmar(sock, datos + b'\x00', 'enviar archivo de datos')


def _formatear_bs(monto):
    """Formatea un monto con separador de miles '.' y decimal ',' (estilo es-VE)."""
    entero, _, decimales = f'{monto:,.2f}'.partition('.')
    return f"{entero.replace(',', '.')},{decimales}"


def _monto_texto(valor_usd, moneda, tasa):
    """
    La cuenta se muestra en UNA sola moneda, nunca en las dos a la vez: si la
    cuenta es en bolívares se convierte con la tasa y solo se ve "Bs.";
    si es en dólares se ve solo "$". Si la cuenta es en bolívares pero no hay
    ninguna tasa cacheada (caso raro), se cae a dólares para no imprimir un
    monto sin sentido.
    """
    if moneda == 'VES' and tasa:
        return f'Bs. {_formatear_bs(valor_usd * tasa)}'
    return f'${valor_usd:.2f}'


def _monto_texto_ambas_monedas(valor_usd, tasa):
    """
    Como _monto_texto, pero mostrando dólares Y bolívares juntos — usado solo
    en la cuenta (pre-factura) que se le entrega al cliente en la mesa antes
    de decidir cómo va a pagar: ahí todavía no se eligió método de pago (ver
    handleGenerarPrefactura en el frontend), así que no hay una sola moneda
    "correcta" que mostrar. Si no hay tasa cacheada se cae a solo dólares,
    igual que _monto_texto.
    """
    if tasa:
        return f'${valor_usd:.2f} / Bs. {_formatear_bs(valor_usd * tasa)}'
    return f'${valor_usd:.2f}'


def _bs_texto(valor_usd, tasa):
    """Monto en bolívares de un valor en dólares ('Bs. 1.234,56'), o None si no hay tasa o el monto es 0."""
    if not tasa or not valor_usd:
        return None
    return f'Bs. {_formatear_bs(valor_usd * tasa)}'


def _agregar_encabezado_empresa(ticket, datos_fiscales, con_telefono=False):
    """
    Logo, el nombre VARAGRILL y los datos fiscales de la empresa (lo que hay cargado en VGDatosFiscalesEmisor).
    El título es siempre VARAGRILL: el nombre comercial de los datos fiscales ("VARA GRILL") no se imprime.
    """
    ticket.logo()
    ticket.centro('VARAGRILL', negrita=True, grande=True)
    if datos_fiscales:
        if datos_fiscales.razon_social:
            ticket.centro(datos_fiscales.razon_social)
        if datos_fiscales.rif:
            ticket.centro(f'RIF: {datos_fiscales.rif}')
        if datos_fiscales.domicilio_fiscal:
            ticket.centro(datos_fiscales.domicilio_fiscal)
        if con_telefono and datos_fiscales.telefono:
            ticket.centro(f'Tel: {datos_fiscales.telefono}')


# Etiqueta del documento del cliente según su tipo (V/E cédula, J/G RIF, P pasaporte).
ETIQUETAS_DOCUMENTO = {'V': 'Cédula', 'E': 'Cédula', 'J': 'RIF', 'G': 'RIF', 'P': 'Pasaporte'}


def _agregar_cliente(ticket, cliente):
    """Cliente y cédula/RIF del documento (no imprime nada si no hay cliente)."""
    if cliente is None:
        return
    nombre = ' '.join(parte for parte in (cliente.nombre, cliente.apellido) if parte and parte.strip())
    if nombre:
        ticket.campo('Cliente:', nombre)
    if cliente.numero_documento:
        etiqueta = ETIQUETAS_DOCUMENTO.get(cliente.tipo_documento, 'Documento')
        prefijo = f'{cliente.tipo_documento}-' if cliente.tipo_documento else ''
        ticket.campo(f'{etiqueta}:', f'{prefijo}{cliente.numero_documento}')


def _producto_label(detalle):
    producto = getattr(detalle, 'producto', None)
    if producto is None:
        return 'Plato eliminado'
    nombre = getattr(producto, 'nombre', None)
    return nombre or 'Plato eliminado'


def _agregar_item_recibo(ticket, detalle, moneda, tasa, con_bs=False):
    """
    `con_bs`: cada renglón lleva el monto en dólares y, debajo, el equivalente en bolívares con la tasa
    del documento (para poder sacar el Bs de cada elemento); sin tasa se imprime solo en dólares.
    """
    con_bs = con_bs and bool(tasa)
    monto_opcional = (lambda valor: _monto_texto_ambas_monedas(valor, tasa)) if con_bs \
        else (lambda valor: _monto_texto(valor, moneda, tasa))
    ticket.item(
        f'{_cantidad_label(detalle)} {_producto_label(detalle)}',
        f'${detalle.subtotal:.2f}' if con_bs else _monto_texto(detalle.subtotal, moneda, tasa),
        _bs_texto(detalle.subtotal, tasa) if con_bs else None,
    )
    if detalle.notas:
        ticket.detalle(f'  - {detalle.notas}')
    for opcion in detalle.opciones.all():
        nombre_opcion = getattr(opcion, 'nombre', None) or 'Opción eliminada'
        if opcion.precio_unitario:
            ticket.detalle(f'  » {opcion.grupo_nombre}: {nombre_opcion}  {monto_opcional(opcion.subtotal)}')
        else:
            ticket.detalle(f'  » {opcion.grupo_nombre}: {nombre_opcion}')
    for adicional in detalle.adicionales.all():
        preparacion = getattr(adicional, 'preparacion', None)
        nombre_adicional = getattr(preparacion, 'nombre', None) or 'Adicional eliminado'
        ticket.detalle(f'  + {adicional.cantidad}x {nombre_adicional}  {monto_opcional(adicional.subtotal)}')


def _agregar_detalle_pedido(ticket, pedido, moneda, tasa, con_bs=False):
    """Platos, sueltos y servicios adicionales de un pedido, cada renglón con su monto (y su Bs si `con_bs`)."""
    con_bs = con_bs and bool(tasa)
    # Mismo criterio que la comanda de cocina: los ítems de un plato armado se
    # agrupan bajo "PLATO N" (para no confundir, por ejemplo, dos yucas de
    # gramajes distintos que vinieron en platos diferentes); lo que no se armó
    # como plato se lista igual que antes, sin ese título.
    platos, sueltos = _group_detalles_por_plato(pedido.detalles.all())
    for numero_plato, (_grupo_id, items) in enumerate(platos, start=1):
        ticket.izq(f'PLATO {numero_plato}', negrita=True)
        for detalle in items:
            _agregar_item_recibo(ticket, detalle, moneda, tasa, con_bs)
    for detalle in sueltos:
        _agregar_item_recibo(ticket, detalle, moneda, tasa, con_bs)
    # Servicios adicionales (no son platos: ver servicios_adicionales.py), cada uno con su cantidad y monto.
    servicios_pedido = list(pedido.servicios.all())
    if servicios_pedido:
        ticket.izq('SERVICIOS ADICIONALES', negrita=True)
        for servicio in servicios_pedido:
            ticket.item(
                f'{servicio.cantidad}x {servicio.nombre}',
                f'${servicio.subtotal:.2f}' if con_bs else _monto_texto(servicio.subtotal, moneda, tasa),
                _bs_texto(servicio.subtotal, tasa) if con_bs else None,
            )


def _ticket_recibo(
    pedidos, metodo_pago, referencia, total, tasa, titulo='RECIBO DE CAJA', codigo=None,
    descuento_manual=None, descuento_manual_motivo='',
    moneda=None, cliente=None, total_ambas_monedas=False, fecha=None, datos_fiscales=None,
):
    """
    `metodo_pago` puede ser None (la nota de entrega se emite antes de saber con qué paga el cliente: no
    se imprime método ni referencia). Con `total_ambas_monedas` el TOTAL sale en dólares y en bolívares.
    Con `total_ambas_monedas` cada producto también sale con su monto en bolívares debajo del de dólares.
    `fecha` es la de emisión del documento; sin ella, la de ahora. `datos_fiscales` (VGDatosFiscalesEmisor)
    pone bajo el logo el nombre comercial, razón social, RIF, domicilio y teléfono de la empresa.
    """
    hora = timezone.localtime(fecha).strftime('%d/%m/%Y %H:%M') if fecha else timezone.localtime().strftime('%d/%m/%Y %H:%M')
    metodo_label = metodo_pago.nombre if metodo_pago is not None else None
    if moneda is None:
        moneda = metodo_pago.moneda

    ticket = Ticket()
    _agregar_encabezado_empresa(ticket, datos_fiscales, con_telefono=True)
    ticket.separador()
    ticket.centro(titulo, negrita=True)
    if codigo:
        ticket.centro(f'Nº {codigo}')
    ticket.separador()
    if referencia and not _REFERENCIA_AUTOGENERADA.match(referencia):
        ticket.campo('Referencia:', referencia)
    ticket.campo('Fecha:', hora)
    _agregar_cliente(ticket, cliente)

    subtotal_total = 0
    impuesto_total = 0
    descuento_total = 0
    propina_total = 0
    delivery_total = 0
    delivery_etiquetas = []
    servicios_total = 0

    for pedido in pedidos:
        mesa_label = f'Mesa {pedido.mesa.numero}' if pedido.mesa else 'Sin mesa'
        ticket.separador()
        ticket.izq(f'Pedido #{pedido.id} - {mesa_label} - {_tipo_pedido_label(pedido.tipo_pedido)}', negrita=True)
        _agregar_detalle_pedido(ticket, pedido, moneda, tasa, con_bs=total_ambas_monedas)
        if pedido.servicios.all():
            servicios_total += pedido.cargo_servicios
        subtotal_total += pedido.subtotal
        impuesto_total += pedido.impuesto
        descuento_total += pedido.descuento
        propina_total += pedido.propina
        if pedido.cargo_delivery and pedido.cargo_delivery > 0:
            delivery_total += pedido.cargo_delivery
            delivery_etiquetas.append(texto_cargo(pedido))

    ticket.separador()
    ticket.fila('Subtotal:', _monto_texto(subtotal_total, moneda, tasa))
    if servicios_total > 0:
        ticket.fila('Servicios:', _monto_texto(servicios_total, moneda, tasa))
    if delivery_total > 0:
        # El envio va en su propia linea (no es un producto): sin ella el ticket no sumaria al TOTAL.
        etiqueta = delivery_etiquetas[0] if len(delivery_etiquetas) == 1 else 'Delivery'
        ticket.fila(f'{etiqueta}:', _monto_texto(delivery_total, moneda, tasa))
    if impuesto_total > 0:
        ticket.fila('Impuesto:', _monto_texto(impuesto_total, moneda, tasa))
    if descuento_total > 0:
        ticket.fila('Descuento:', f'-{_monto_texto(descuento_total, moneda, tasa)}')
    if descuento_manual:
        # Descuento manual aplicado al cobrar (ver VGNotaEntrega.descuento_monto),
        # distinto del descuento por pedido de arriba — se imprime con su
        # motivo para que quede constancia en el ticket físico, no solo en la
        # base de datos (auditoría, ver pedidos_cobro_view).
        ticket.fila('Descuento aplicado:', f'-{_monto_texto(descuento_manual, moneda, tasa)}')
        if descuento_manual_motivo:
            ticket.campo('Motivo:', descuento_manual_motivo)
    if propina_total > 0:
        ticket.fila('Propina:', _monto_texto(propina_total, moneda, tasa))
    ticket.separador()
    if total_ambas_monedas:
        ticket.total_dual(f'${total:.2f}', f'Bs. {_formatear_bs(total * tasa)}' if tasa else None)
    else:
        ticket.fila('TOTAL:', _monto_texto(total, moneda, tasa), negrita=True, grande=True)
    if metodo_label:
        ticket.campo('Método de pago:', metodo_label)
    ticket.centro('¡Gracias por su visita!')
    return ticket


def _build_recibo_bytes(*args, **kwargs):
    """Nota de entrega / recibo de caja en ESC/POS de texto (respaldo del ticket gráfico y pruebas)."""
    return _ticket_recibo(*args, **kwargs).to_text_bytes()


def imprimir_nota_entrega_caja(nota, es_reimpresion=False):
    """
    Imprime (o reimprime) el ticket de una VGNotaEntrega — el recibo de venta
    sin efecto fiscal que hoy reemplaza a la factura mientras el SENIAT
    termina de homologar el sistema (ver VGNotaEntrega). No hay lineas
    propias guardadas: el detalle (platos, acompañantes, adicionales, notas,
    mesa) se relee en vivo desde los VGPedido relacionados, igual que hacia
    el recibo de caja de siempre — así una reimpresión días o solo minutos
    despues sale identica al ticket original.

    Devuelve (exito: bool, motivo: str|None), igual que imprimir_factura_caja:
    quien llama desde el cobro normal puede ignorar el resultado (no debe
    tumbar un cobro ya registrado por un problema de impresora), pero
    notas_entrega_reimprimir_view SI necesita saber si el reenvio realmente
    llego a la cola.
    """
    config = VGImpresoraCaja.obtener_config()
    if config is None or not config.activo:
        return False, 'No hay una impresora de caja activa configurada.'
    if not config.ip or not config.cola:
        logger.warning('Impresora de caja activa pero sin IP/cola configurada; se omite la nota de entrega.')
        return False, 'La impresora de caja no tiene IP o cola configurada.'

    # La nota se emite antes de saber con qué paga el cliente (cada abono lleva su propio método): el ticket
    # no menciona método ni referencia, muestra los precios en dólares y el total en dólares y en bolívares.
    tasa = nota.tasa_cambio_referencia
    if tasa is None:
        tasa_actual = VGTasaCambio.objects.order_by('-fecha_actualizacion').first()
        tasa = tasa_actual.tasa if tasa_actual else None
    pedidos = list(
        nota.pedidos.select_related('mesa')
        .prefetch_related('detalles__producto', 'detalles__opciones', 'detalles__adicionales__preparacion', 'servicios')
        .all()
    )

    titulo = 'NOTA DE ENTREGA' + (' (REIMPRESION)' if es_reimpresion else '')
    destino = f'{config.ip}:{config.puerto} (cola "{config.cola}")'
    try:
        ticket = _ticket_recibo(
            pedidos, None, None, nota.total, tasa,
            titulo=titulo, codigo=nota.codigo,
            descuento_manual=nota.descuento_monto, descuento_manual_motivo=nota.descuento_motivo,
            moneda='USD', cliente=nota.cliente, total_ambas_monedas=True, fecha=nota.fecha_emision,
            datos_fiscales=VGDatosFiscalesEmisor.objects.first(),
        ).to_bytes()
        logger.info('Enviando nota de entrega %s a %s (%s bytes)', nota.codigo, destino, len(ticket))
        enviar_trabajo_lpd(
            config.ip, config.puerto, config.cola, ticket,
            job_id=nota.id, nombre_trabajo=f'Nota {nota.codigo}',
        )
        logger.info('Nota de entrega %s enviada a %s', nota.codigo, destino)
        return True, None
    except Exception as exc:
        logger.exception('No se pudo imprimir la nota de entrega %s hacia %s', nota.codigo, destino)
        return False, f'No se pudo enviar el trabajo de impresion: {exc}'


# ---------------------------------------------------------------------------
# Nota de cobro (ticket de cada abono a una nota de entrega)
# ---------------------------------------------------------------------------
def _ticket_nota_cobro(pago, es_reimpresion=False):
    """
    Ticket de la NOTA DE COBRO de un abono (VGPago) a una nota de entrega:
    datos fiscales de la empresa, numero de cobro, nota de entrega a la que
    hace referencia, metodo, y el monto en la moneda REAL con la que se cobro
    (dolares o bolivares — nunca las dos juntas). Todo lo que depende de la
    tasa usa la que quedo congelada en el pago (`pago.tasa_cambio_referencia`,
    la del dia del cobro), nunca la de hoy, para que una reimpresion salga
    identica al ticket original. La fecha/hora es la del cobro en hora local.
    """
    nota = pago.nota_entrega
    metodo = pago.metodo_pago
    en_bs = metodo.moneda == 'VES' and pago.tasa_cambio_referencia
    tasa = pago.tasa_cambio_referencia

    def monto_texto(valor_usd):
        if en_bs:
            return f'Bs. {_formatear_bs((valor_usd * tasa).quantize(Decimal("0.01")))}'
        return f'${valor_usd:.2f}'

    datos_fiscales = VGDatosFiscalesEmisor.objects.first()
    fecha_hora = timezone.localtime(pago.fecha_pago).strftime('%d/%m/%Y %H:%M:%S')
    codigo_cobro = f'COB-{pago.numero_cobro:06d}' if pago.numero_cobro else f'PAGO-{pago.id}'
    cajero = ''
    if pago.creado_por:
        cajero = pago.creado_por.get_full_name() or pago.creado_por.username

    ticket = Ticket()
    _agregar_encabezado_empresa(ticket, datos_fiscales, con_telefono=True)
    ticket.separador()
    ticket.centro('NOTA DE COBRO', negrita=True)
    ticket.centro(f'Nº {codigo_cobro}' + (' (REIMPRESION)' if es_reimpresion else ''))
    ticket.separador()
    ticket.campo('Fecha:', fecha_hora)
    ticket.campo('Nota de entrega:', nota.codigo)
    _agregar_cliente(ticket, nota.cliente)
    # Detalle de lo que se cobra: cada producto en dólares y en bolívares (con la tasa del cobro) para poder
    # sacar el Bs de cada elemento sin importar en qué moneda se pague.
    tasa_detalle = pago.tasa_cambio_referencia or nota.tasa_cambio_referencia
    pedidos = list(
        nota.pedidos.select_related('mesa')
        .prefetch_related('detalles__producto', 'detalles__opciones', 'detalles__adicionales__preparacion', 'servicios')
        .all()
    )
    if pedidos:
        ticket.separador()
        ticket.centro('DETALLE DE LA NOTA', negrita=True)
        for pedido in pedidos:
            if len(pedidos) > 1:
                ticket.izq(f'Pedido #{pedido.id}', negrita=True)
            _agregar_detalle_pedido(ticket, pedido, 'USD', tasa_detalle, con_bs=True)
    ticket.separador()
    ticket.campo('Método de pago:', metodo.nombre)
    ticket.campo('Moneda:', 'Bolívares' if en_bs else 'Dólares')
    if pago.referencia and not _REFERENCIA_AUTOGENERADA.match(pago.referencia):
        ticket.campo('Referencia:', pago.referencia)
    if en_bs:
        ticket.campo('Tasa:', f'Bs. {_formatear_bs(tasa)} por $1')
    ticket.separador()
    ticket.fila('Total de la nota:', monto_texto(nota.total))
    ticket.fila('MONTO COBRADO:', monto_texto(pago.monto), negrita=True)
    if pago.saldo_posterior is not None:
        if pago.saldo_posterior > 0:
            ticket.fila('Saldo pendiente:', monto_texto(pago.saldo_posterior))
        else:
            ticket.centro('Nota de entrega SALDADA', negrita=True)
    if cajero:
        ticket.campo('Cajero:', cajero)
    ticket.separador()
    ticket.centro('Documento sin efecto fiscal')
    ticket.centro('¡Gracias por su visita!')
    return ticket


def _build_cobro_nota_entrega_bytes(pago, es_reimpresion=False):
    """Nota de cobro en ESC/POS de texto (respaldo del ticket gráfico y pruebas)."""
    return _ticket_nota_cobro(pago, es_reimpresion).to_text_bytes()


def imprimir_cobro_nota_entrega_caja(pago, es_reimpresion=False):
    """
    Imprime (o reimprime) la nota de cobro de un abono a una nota de entrega.
    Devuelve (exito, motivo) igual que imprimir_nota_entrega_caja: el abono
    ya quedo registrado, un fallo de impresora nunca debe tumbarlo.
    """
    config = VGImpresoraCaja.obtener_config()
    if config is None or not config.activo:
        return False, 'No hay una impresora de caja activa configurada.'
    if not config.ip or not config.cola:
        logger.warning('Impresora de caja activa pero sin IP/cola configurada; se omite la nota de cobro.')
        return False, 'La impresora de caja no tiene IP o cola configurada.'

    destino = f'{config.ip}:{config.puerto} (cola "{config.cola}")'
    try:
        ticket = _ticket_nota_cobro(pago, es_reimpresion=es_reimpresion).to_bytes()
        enviar_trabajo_lpd(
            config.ip, config.puerto, config.cola, ticket,
            job_id=pago.id, nombre_trabajo=f'Cobro {pago.numero_cobro or pago.id}',
        )
        logger.info('Nota de cobro %s enviada a %s', pago.numero_cobro, destino)
        return True, None
    except Exception as exc:
        logger.exception('No se pudo imprimir la nota de cobro %s hacia %s', pago.numero_cobro, destino)
        return False, f'No se pudo enviar el trabajo de impresion: {exc}'


# ---------------------------------------------------------------------------
# Pre-factura / factura (modulo de facturacion)
# ---------------------------------------------------------------------------
def _agregar_linea_documento(ticket, linea, monto_fn, ambas_monedas, tasa):
    texto = f'{linea.cantidad}x {linea.descripcion}'
    if ambas_monedas:
        # Dólares a la derecha y bolívares debajo: los dos montos juntos no caben en el renglón.
        ticket.item(texto, f'${linea.subtotal:.2f}', _bs_texto(linea.subtotal, tasa))
        return
    ticket.item(texto, monto_fn(linea.subtotal))
    if linea.cantidad != 1:
        ticket.detalle(f'{monto_fn(linea.precio_unitario)} c/u')


def _ticket_documento_venta(
    titulo, subtitulo, cliente, lineas, subtotal, total_iva, total, moneda, tasa, datos_fiscales,
    extra_lineas=None, mostrar_iva=True, info_encabezado=None, mostrar_ambas_monedas=False,
):
    hora = timezone.localtime().strftime('%d/%m/%Y %H:%M')

    ticket = Ticket()
    _agregar_encabezado_empresa(ticket, datos_fiscales)
    ticket.separador()
    ticket.centro(titulo, negrita=True)
    if subtitulo:
        ticket.centro(subtitulo)
    ticket.separador()
    ticket.campo('Fecha:', hora)
    for texto in (info_encabezado or []):
        ticket.izq(texto)
    _agregar_cliente(ticket, cliente)
    ticket.separador()

    monto_fn = (lambda valor: _monto_texto_ambas_monedas(valor, tasa)) if mostrar_ambas_monedas \
        else (lambda valor: _monto_texto(valor, moneda, tasa))

    for linea in lineas:
        _agregar_linea_documento(ticket, linea, monto_fn, mostrar_ambas_monedas, tasa)

    ticket.separador()
    if mostrar_iva:
        ticket.fila('Subtotal:', monto_fn(subtotal))
        ticket.fila('IVA:', monto_fn(total_iva))
    if mostrar_ambas_monedas:
        ticket.total_dual(f'${total:.2f}', f'Bs. {_formatear_bs(total * tasa)}' if tasa else None)
    else:
        ticket.fila('TOTAL:', monto_fn(total), negrita=True, grande=True)

    for texto in (extra_lineas or []):
        ticket.izq(texto)

    ticket.centro('¡Gracias por su visita!')
    return ticket


def _build_documento_venta_bytes(*args, **kwargs):
    """Cuenta/factura en ESC/POS de texto (respaldo del ticket gráfico y pruebas)."""
    return _ticket_documento_venta(*args, **kwargs).to_text_bytes()


def imprimir_prefactura_caja(prefactura):
    """
    Imprime la vista previa de cuenta (pre-factura) en la impresora de caja
    — es solo la cuenta que el cliente pide ver antes de pagar, sin
    numeracion fiscal ni validez legal. Silencioso ante fallos: llamar
    siempre envuelto en try/except desde el caller, igual que
    imprimir_recibo_caja, para que un fallo de impresion no eche para atras
    la pre-factura ya generada.
    """
    config = VGImpresoraCaja.obtener_config()
    if config is None or not config.activo:
        return
    if not config.ip or not config.cola:
        logger.warning('Impresora de caja activa pero sin IP/cola configurada; se omite la pre-factura.')
        return

    tasa = prefactura.tasa_cambio_referencia
    if tasa is None:
        tasa_actual = VGTasaCambio.objects.order_by('-fecha_actualizacion').first()
        tasa = tasa_actual.tasa if tasa_actual else None
    datos_fiscales = VGDatosFiscalesEmisor.objects.first()
    codigo = f'PF-{prefactura.numero:06d}'

    # Mesa y mesero de origen: para que el cajero (u otro mesero) pueda ver de
    # dónde salió esta cuenta sin tener que ir a preguntar. Todos los pedidos
    # de una cuenta vienen de la misma mesa (se genera por mesa desde Cobro),
    # así que basta con leerlos del primero; si el pedido es para llevar/sin
    # mesa asignada, simplemente no hay mesa que mostrar.
    pedidos = list(prefactura.pedidos.select_related('mesa', 'usuario').all())
    info_encabezado = []
    if pedidos:
        primero = pedidos[0]
        if primero.mesa:
            info_encabezado.append(f'Mesa: {primero.mesa.numero}')
        if primero.usuario:
            mesero_nombre = primero.usuario.get_full_name() or primero.usuario.username
            info_encabezado.append(f'Mesero: {mesero_nombre}')

    destino = f'{config.ip}:{config.puerto} (cola "{config.cola}")'
    try:
        ticket = _ticket_documento_venta(
            'CUENTA (no es factura fiscal)', codigo, prefactura.cliente,
            list(prefactura.lineas.all()), prefactura.subtotal, prefactura.total_iva, prefactura.total,
            prefactura.moneda, tasa, datos_fiscales, mostrar_iva=False,
            info_encabezado=info_encabezado, mostrar_ambas_monedas=True,
        ).to_bytes()
        logger.info('Enviando pre-factura %s a %s (%s bytes)', codigo, destino, len(ticket))
        enviar_trabajo_lpd(
            config.ip, config.puerto, config.cola, ticket,
            job_id=prefactura.id, nombre_trabajo=f'PreFactura {codigo}',
        )
        logger.info('Pre-factura %s enviada a %s', codigo, destino)
    except Exception:
        logger.exception('No se pudo imprimir la pre-factura %s hacia %s', codigo, destino)


def imprimir_factura_caja(factura, es_reimpresion=False):
    """
    Imprime la factura fiscal (con su numero de control) en la impresora de
    caja. Usa la tasa de cambio guardada como referencia al momento de
    emitir la factura (no la tasa actual), para que el monto en bolivares
    impreso coincida con el que quedo registrado.

    Devuelve (exito: bool, motivo: str|None) en vez de propagar la excepcion
    — quien llama desde la emision normal puede seguir ignorando el
    resultado (silencioso ante fallos, para no tumbar una factura ya
    generada por un problema de impresora), pero factura_reimprimir_view SI
    necesita saber si el reenvio realmente llego a la cola, para avisarle al
    cajero en vez de que crea que se imprimio y no sea asi.
    """
    config = VGImpresoraCaja.obtener_config()
    if config is None or not config.activo:
        return False, 'No hay una impresora de caja activa configurada.'
    if not config.ip or not config.cola:
        logger.warning('Impresora de caja activa pero sin IP/cola configurada; se omite la factura.')
        return False, 'La impresora de caja no tiene IP o cola configurada.'

    datos_fiscales = VGDatosFiscalesEmisor.objects.first()
    codigo = f'{factura.numero_factura:08d}'
    extra_lineas = []
    if es_reimpresion:
        extra_lineas.append('*** REIMPRESION ***')
    if factura.saldo_pendiente > 0:
        saldo_texto = _monto_texto(factura.saldo_pendiente, factura.moneda, factura.tasa_cambio_referencia)
        extra_lineas.append(f'Saldo pendiente: {saldo_texto}')

    destino = f'{config.ip}:{config.puerto} (cola "{config.cola}")'
    try:
        ticket = _ticket_documento_venta(
            f'FACTURA {codigo}', f'Control: {factura.numero_control:08d}', factura.cliente,
            list(factura.lineas.all()), factura.subtotal, factura.total_iva, factura.total,
            factura.moneda, factura.tasa_cambio_referencia, datos_fiscales, extra_lineas=extra_lineas,
        ).to_bytes()
        logger.info('Enviando factura %s a %s (%s bytes)', codigo, destino, len(ticket))
        enviar_trabajo_lpd(
            config.ip, config.puerto, config.cola, ticket,
            job_id=factura.id, nombre_trabajo=f'Factura {codigo}',
        )
        logger.info('Factura %s enviada a %s', codigo, destino)
        return True, None
    except Exception as exc:
        logger.exception('No se pudo imprimir la factura %s hacia %s', codigo, destino)
        return False, f'No se pudo enviar el trabajo de impresion: {exc}'

# ---------------------------------------------------------------------------
# Cierre de lote de punto de venta (POS)
# ---------------------------------------------------------------------------
def _fila_izq_der(izquierda, derecha):
    """Una linea de LINE_WIDTH caracteres con texto a la izquierda y monto a la derecha."""
    derecha = str(derecha)
    espacio = max(LINE_WIDTH - len(derecha) - 1, 0)
    return f'{str(izquierda)[:espacio]:<{espacio}} {derecha}'


def _origen_pago_corto(pago):
    if pago.nota_entrega_id:
        return pago.nota_entrega.codigo
    if pago.factura_id:
        return f'FAC {pago.factura.numero_factura}' if pago.factura.numero_factura else f'FAC #{pago.factura_id}'
    return f'PED #{pago.pedido_id}'


def _cliente_pago_corto(pago):
    cliente = pago.nota_entrega.cliente if pago.nota_entrega_id else None
    if cliente is None:
        return ''
    return f'{cliente.nombre} {cliente.apellido}'.strip()


def _build_cierre_lote_pos_bytes(lote, es_reimpresion=False):
    """
    Ticket del CIERRE DE LOTE de punto de venta: un renglon por cada cobro del lote
    con su nota de entrega (u otro origen), hora, cliente, referencia/voucher y monto
    en bolivares, y el total del lote. Sirve para comparar, cobro por cobro, lo que
    registro el sistema contra el cierre de lote que imprime el punto fisico. Los
    montos en Bs usan la tasa congelada de cada cobro (nunca la de hoy).
    """
    from .lotes_pos import _tasa_de_ingreso_extra, _tasa_de_pago  # import tardio: evita ciclos entre modulos

    datos_fiscales = VGDatosFiscalesEmisor.objects.first()
    pagos = list(
        lote.pagos.filter(estado='completado')
        .select_related('nota_entrega__cliente', 'factura', 'creado_por')
        .order_by('fecha_pago')
    )
    ingresos_extra = list(
        lote.ingresos_extra.filter(tipo__in=('propina', 'pago_extra'))
        .select_related('nota_entrega', 'creado_por')
        .order_by('fecha_creacion')
    )
    movimientos = sorted(
        [(pago.fecha_pago, 'pago', pago) for pago in pagos]
        + [(ingreso.fecha_creacion, 'ingreso_extra', ingreso) for ingreso in ingresos_extra],
        key=lambda item: item[0],
    )
    titulo = 'CIERRE DE LOTE POS'
    if lote.estado == 'abierto':
        titulo = 'LOTE POS ABIERTO (PARCIAL)'
    if es_reimpresion:
        titulo += ' (REIMPRESION)'

    out = bytearray()
    out += INIT
    out += KANJI_OFF
    out += ESC_POS_WCP1252
    out += ALIGN_CENTER
    out += BOLD_ON
    out += _text((datos_fiscales.nombre_comercial if datos_fiscales and datos_fiscales.nombre_comercial else None) or 'VARAGRILL') + FEED
    out += _text(titulo) + FEED
    out += _text(f'LOTE-{lote.numero:06d}') + FEED
    out += BOLD_OFF
    out += ALIGN_LEFT
    out += _text('-' * LINE_WIDTH) + FEED
    out += _text(f'Metodo: {lote.metodo_pago.nombre}') + FEED
    if lote.cuenta_bancaria:
        out += _text(f'Banco: {lote.cuenta_bancaria}') + FEED
    out += _text(f'Operacion: {lote.fecha_operacion.strftime("%d/%m/%Y")}') + FEED
    if lote.fecha_cierre:
        out += _text(f'Cerrado: {timezone.localtime(lote.fecha_cierre).strftime("%d/%m/%Y %H:%M")}') + FEED
        if lote.cerrado_por:
            out += _text(f'Por: {lote.cerrado_por.get_full_name() or lote.cerrado_por.username}') + FEED
    out += _text('-' * LINE_WIDTH) + FEED
    out += BOLD_ON
    out += _text(f'MOVIMIENTOS DEL LOTE ({len(movimientos)})') + FEED
    out += BOLD_OFF
    out += _text('Compara con el cierre del punto') + FEED
    out += _text('-' * LINE_WIDTH) + FEED

    total_bs = Decimal('0')
    total_usd = Decimal('0')
    for fecha_movimiento, tipo_movimiento, movimiento in movimientos:
        if tipo_movimiento == 'pago':
            monto = movimiento.monto
            tasa = _tasa_de_pago(movimiento)
            origen = _origen_pago_corto(movimiento)
            detalle = _cliente_pago_corto(movimiento)
            referencia = movimiento.referencia if movimiento.referencia and not movimiento.referencia.startswith('ABONO-') else ''
            if referencia:
                detalle = f'{detalle[:14]} Ref:{referencia[:12]}'.strip()
        else:
            monto = movimiento.monto
            tasa = _tasa_de_ingreso_extra(movimiento)
            origen = movimiento.get_tipo_display()
            detalle = f'Nota {movimiento.nota_entrega.codigo}' if movimiento.nota_entrega_id else ''
            if movimiento.descripcion:
                detalle = f'{detalle} {movimiento.descripcion}'.strip()
        monto_bs = (monto * tasa).quantize(Decimal('0.01')) if tasa else None
        total_usd += monto
        if monto_bs is not None:
            total_bs += monto_bs
        hora = timezone.localtime(fecha_movimiento).strftime('%H:%M')
        monto_txt = f'Bs.{_formatear_bs(monto_bs)}' if monto_bs is not None else f'${monto:.2f}'
        out += _text(_fila_izq_der(f'{hora} {origen}', monto_txt)) + FEED
        if detalle:
            out += _text(f'  {detalle}'[:LINE_WIDTH]) + FEED

    out += _text('-' * LINE_WIDTH) + FEED
    out += BOLD_ON
    out += _text(_fila_izq_der('TOTAL Bs.', _formatear_bs(total_bs))) + FEED
    out += BOLD_OFF
    out += _text(_fila_izq_der('Total en dolares', f'${total_usd:.2f}')) + FEED
    out += _text(_fila_izq_der('Cantidad de movimientos', len(movimientos))) + FEED
    out += _text('-' * LINE_WIDTH) + FEED
    out += ALIGN_CENTER
    out += _text('Documento sin efecto fiscal') + FEED
    out += ALIGN_LEFT
    out += FEED + FEED + FEED + FEED
    out += CUT
    return bytes(out)


def imprimir_cierre_lote_pos(lote, es_reimpresion=False):
    """
    Imprime (o reimprime) el cierre de un lote POS en la impresora de caja. Devuelve
    (exito, motivo) igual que imprimir_cobro_nota_entrega_caja: el lote ya quedo
    cerrado, un fallo de impresora nunca debe tumbar el cierre.
    """
    config = VGImpresoraCaja.obtener_config()
    if config is None or not config.activo:
        return False, 'No hay una impresora de caja activa configurada.'
    if not config.ip or not config.cola:
        logger.warning('Impresora de caja activa pero sin IP/cola configurada; se omite el cierre de lote.')
        return False, 'La impresora de caja no tiene IP o cola configurada.'

    destino = f'{config.ip}:{config.puerto} (cola "{config.cola}")'
    try:
        ticket = _build_cierre_lote_pos_bytes(lote, es_reimpresion=es_reimpresion)
        enviar_trabajo_lpd(
            config.ip, config.puerto, config.cola, ticket,
            job_id=lote.id, nombre_trabajo=f'Lote POS {lote.numero}',
        )
        logger.info('Cierre del lote POS %s enviado a %s', lote.numero, destino)
        return True, None
    except Exception as exc:
        logger.exception('No se pudo imprimir el lote POS %s hacia %s', lote.numero, destino)
        return False, f'No se pudo enviar el trabajo de impresion: {exc}'

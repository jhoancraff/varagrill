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
    _group_detalles_por_plato,
    _text,
    _tipo_pedido_label,
)
from .models import VGDatosFiscalesEmisor, VGImpresoraCaja, VGTasaCambio

logger = logging.getLogger(__name__)

LPD_ORIGIN_HOST = 'varagrill'
LPD_CONNECT_TIMEOUT_SECONDS = 5


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


def _render_recibo_item(detalle):
    out = bytearray()
    out += _text(f'{_cantidad_label(detalle)} {detalle.producto.nombre}') + FEED
    if detalle.notas:
        out += _text(f'  - {detalle.notas}') + FEED
    out += _text(f'  ${detalle.subtotal:.2f}') + FEED
    for opcion in detalle.opciones.all():
        if opcion.precio_unitario:
            out += _text(f'  » {opcion.grupo_nombre}: {opcion.nombre}  ${opcion.subtotal:.2f}') + FEED
        else:
            out += _text(f'  » {opcion.grupo_nombre}: {opcion.nombre}') + FEED
    for adicional in detalle.adicionales.all():
        out += _text(f'  + {adicional.cantidad}x {adicional.preparacion.nombre}  ${adicional.subtotal:.2f}') + FEED
    return bytes(out)


def _build_recibo_bytes(pedidos, metodo_pago, referencia, total, tasa, titulo='RECIBO DE CAJA', codigo=None):
    hora = timezone.localtime().strftime('%d/%m/%Y %H:%M')
    metodo_label = metodo_pago.nombre
    moneda = metodo_pago.moneda

    out = bytearray()
    out += INIT
    out += KANJI_OFF
    out += ESC_POS_WCP1252
    out += ALIGN_CENTER
    out += _text('VARAGRILL') + FEED
    out += BOLD_ON
    out += _text(titulo) + FEED
    out += BOLD_OFF
    if codigo:
        out += _text(f'Nº {codigo}') + FEED
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
        # Mismo criterio que la comanda de cocina: los ítems de un plato armado se
        # agrupan bajo "PLATO N" (para no confundir, por ejemplo, dos yucas de
        # gramajes distintos que vinieron en platos diferentes); lo que no se armó
        # como plato se lista igual que antes, sin ese título.
        platos, sueltos = _group_detalles_por_plato(pedido.detalles.all())
        for numero_plato, (_grupo_id, items) in enumerate(platos, start=1):
            out += BOLD_ON
            out += _text(f'PLATO {numero_plato}') + FEED
            out += BOLD_OFF
            for detalle in items:
                out += _render_recibo_item(detalle)
        for detalle in sueltos:
            out += _render_recibo_item(detalle)
        subtotal_total += pedido.subtotal
        impuesto_total += pedido.impuesto
        descuento_total += pedido.descuento
        propina_total += pedido.propina

    out += _text('-' * LINE_WIDTH) + FEED
    out += _text(f'Subtotal: {_monto_texto(subtotal_total, moneda, tasa)}') + FEED
    if impuesto_total > 0:
        out += _text(f'Impuesto: {_monto_texto(impuesto_total, moneda, tasa)}') + FEED
    if descuento_total > 0:
        out += _text(f'Descuento: -{_monto_texto(descuento_total, moneda, tasa)}') + FEED
    if propina_total > 0:
        out += _text(f'Propina: {_monto_texto(propina_total, moneda, tasa)}') + FEED
    out += BOLD_ON
    out += _text(f'TOTAL: {_monto_texto(total, moneda, tasa)}') + FEED
    out += BOLD_OFF
    out += _text(f'Metodo de pago: {metodo_label}') + FEED
    out += ALIGN_CENTER
    out += _text('¡Gracias por su visita!') + FEED
    out += ALIGN_LEFT

    out += FEED + FEED + FEED + FEED
    out += CUT
    return bytes(out)


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

    pedidos = list(
        nota.pedidos.select_related('mesa')
        .prefetch_related('detalles__producto', 'detalles__opciones', 'detalles__adicionales__preparacion')
        .all()
    )

    titulo = 'NOTA DE ENTREGA' + (' (REIMPRESION)' if es_reimpresion else '')
    destino = f'{config.ip}:{config.puerto} (cola "{config.cola}")'
    try:
        ticket = _build_recibo_bytes(
            pedidos, nota.metodo_pago, nota.referencia, nota.total, nota.tasa_cambio_referencia,
            titulo=titulo, codigo=nota.codigo,
        )
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
# Pre-factura / factura (modulo de facturacion)
# ---------------------------------------------------------------------------
def _render_documento_linea(linea, moneda, tasa):
    out = bytearray()
    out += _text(f'{linea.cantidad}x {linea.descripcion}') + FEED
    precio_texto = _monto_texto(linea.precio_unitario, moneda, tasa)
    subtotal_texto = _monto_texto(linea.subtotal, moneda, tasa)
    out += _text(f'  {precio_texto} c/u  {subtotal_texto}') + FEED
    return bytes(out)


def _build_documento_venta_bytes(
    titulo, subtitulo, cliente, lineas, subtotal, total_iva, total, moneda, tasa, datos_fiscales,
    extra_lineas=None, mostrar_iva=True,
):
    hora = timezone.localtime().strftime('%d/%m/%Y %H:%M')

    out = bytearray()
    out += INIT
    out += KANJI_OFF
    out += ESC_POS_WCP1252
    out += ALIGN_CENTER
    out += BOLD_ON
    out += _text((datos_fiscales.nombre_comercial if datos_fiscales and datos_fiscales.nombre_comercial else None) or 'VARAGRILL') + FEED
    out += BOLD_OFF
    if datos_fiscales:
        if datos_fiscales.razon_social:
            out += _text(datos_fiscales.razon_social) + FEED
        if datos_fiscales.rif:
            out += _text(f'RIF: {datos_fiscales.rif}') + FEED
        if datos_fiscales.domicilio_fiscal:
            out += _text(datos_fiscales.domicilio_fiscal) + FEED
    out += _text('-' * LINE_WIDTH) + FEED
    out += BOLD_ON
    out += _text(titulo) + FEED
    out += BOLD_OFF
    if subtitulo:
        out += _text(subtitulo) + FEED
    out += ALIGN_LEFT
    out += _text('-' * LINE_WIDTH) + FEED
    out += _text(hora) + FEED
    if cliente is not None:
        out += _text(f'Cliente: {cliente.nombre}') + FEED
        if cliente.numero_documento:
            out += _text(f'{cliente.tipo_documento}-{cliente.numero_documento}') + FEED
    out += _text('-' * LINE_WIDTH) + FEED

    for linea in lineas:
        out += _render_documento_linea(linea, moneda, tasa)

    out += _text('-' * LINE_WIDTH) + FEED
    if mostrar_iva:
        out += _text(f'Subtotal: {_monto_texto(subtotal, moneda, tasa)}') + FEED
        out += _text(f'IVA: {_monto_texto(total_iva, moneda, tasa)}') + FEED
    out += BOLD_ON
    out += _text(f'TOTAL: {_monto_texto(total, moneda, tasa)}') + FEED
    out += BOLD_OFF

    for texto in (extra_lineas or []):
        out += _text(texto) + FEED

    out += ALIGN_CENTER
    out += _text('¡Gracias por su visita!') + FEED
    out += ALIGN_LEFT

    out += FEED + FEED + FEED + FEED
    out += CUT
    return bytes(out)


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

    destino = f'{config.ip}:{config.puerto} (cola "{config.cola}")'
    try:
        ticket = _build_documento_venta_bytes(
            'CUENTA (no es factura fiscal)', codigo, prefactura.cliente,
            list(prefactura.lineas.all()), prefactura.subtotal, prefactura.total_iva, prefactura.total,
            prefactura.moneda, tasa, datos_fiscales, mostrar_iva=False,
        )
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
        ticket = _build_documento_venta_bytes(
            f'FACTURA {codigo}', f'Control: {factura.numero_control:08d}', factura.cliente,
            list(factura.lineas.all()), factura.subtotal, factura.total_iva, factura.total,
            factura.moneda, factura.tasa_cambio_referencia, datos_fiscales, extra_lineas=extra_lineas,
        )
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
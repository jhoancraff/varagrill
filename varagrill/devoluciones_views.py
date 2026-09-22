"""
Vistas del modulo de Devolucion y Reversion de Pedidos Cobrados.

Cuando un cliente devuelve comida o pide un cambio DESPUES de haber sido
cobrado, no se edita el documento original (VGNotaEntrega o VGFactura): se
anula al 100% (nunca una modificacion parcial) y se emite una VGNotaCredito
que ancla:
  1. las VGMerma de los platos devueltos (sin reingresar inventario: el
     insumo ya se desconto de stock al cobrar el pedido original),
  2. los VGPago del documento original, que quedan en estado 'anulado' SOLO
     si tipo_resolucion='reembolso' (dejan de contarse en el cuadre de caja
     diario — reportes.py filtra `estado='completado'` en todas sus consultas,
     ver VGPago.anulado_por_nota_credito),
  3. si tipo_resolucion='canje', el/los VGPedido que la cajera arma despues
     desde Nuevo Pedido (no se clonan aca — ver pedido_create_view en
     api_views.py, que liga VGPedido.nota_credito_origen a esta NC cuando
     recibe `nota_credito_id`),
  4. si tipo_resolucion='credito_futuro', el VGCreditoCliente con el saldo.

Requiere autorizacion de Gerente/Supervisor (usuario+contraseña propios,
distintos de quien esta operando la caja) y un motivo obligatorio del
catalogo VGNotaCredito.MOTIVOS.
"""
import json
import logging
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import authenticate
from django.db import transaction
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .auth_helpers import _auth_response, _is_admin_user, _is_cajera_user, _is_gerente_user
from .facturacion_views import _tasa_conversion_vigente
from .models import (
    VGCorrelativoFiscal,
    VGCreditoCliente,
    VGDetallePedido,
    VGFactura,
    VGMerma,
    VGNotaCredito,
    VGNotaEntrega,
    VGPago,
)
from .tasa_cambio import obtener_tasa_actual

logger = logging.getLogger(__name__)

# Tolerancia para el tope "el ajuste no puede superar el saldo pendiente":
# el campo que la cajera ve y escribe (Bs, 2 decimales) es un REDONDEO del
# saldo real (guardado en USD a 6 decimales) — invertir esa conversion no
# siempre reproduce exactamente el mismo valor (ej. saldo real $2.214325,
# convertido a Bs para mostrar => 1887.53, pero 1887.53 Bs convertido de
# vuelta a USD => $2.214328: 3 millonesimas de dolar de diferencia, muy por
# debajo de un centimo). Sin esta tolerancia, escribir a mano el mismo monto
# que la pantalla ya muestra se rechazaba por ese residuo — "usa Saldar
# completo" no siempre es la respuesta si el monto SI es exacto salvo por
# este redondeo de ida y vuelta. Un centimo de dolar sigue siendo minimo
# frente a cualquier error real de tipeo, y nunca se cobra de mas: si el
# monto excede el saldo por esto, se recorta al saldo real, nunca al reves.
TOLERANCIA_AJUSTE_USD = Decimal('0.01')


def _validar_autorizacion_y_documento(documento_tipo, documento_id, motivo, tipo_resolucion,
                                       autorizador_username, autorizador_password):
    """
    Pasos comunes a cualquier tipo_resolucion: autenticar al Gerente/Supervisor,
    validar motivo/tipo_resolucion, y bloquear el documento a ajustar. Separado
    de revertir_y_reabrir_pedido/aplicar_ajuste_parcial porque ambos lo necesitan
    igual.
    """
    autorizador = authenticate(username=autorizador_username, password=autorizador_password)
    if autorizador is None:
        raise PermissionError('Credenciales de autorización inválidas.')
    if not _is_gerente_user(autorizador):
        raise PermissionError('El usuario autorizador no tiene rango de Gerente/Supervisor.')

    if motivo not in dict(VGNotaCredito.MOTIVOS):
        raise ValueError('Debes seleccionar un motivo de devolución válido.')
    if tipo_resolucion not in dict(VGNotaCredito.TIPOS_RESOLUCION):
        raise ValueError('Debes indicar qué pasa con el dinero.')

    if documento_tipo == 'nota_entrega':
        try:
            documento = VGNotaEntrega.objects.select_for_update().get(pk=documento_id)
        except VGNotaEntrega.DoesNotExist:
            raise ValueError('La nota de entrega no existe.')
    elif documento_tipo == 'factura':
        try:
            documento = VGFactura.objects.select_for_update().get(pk=documento_id)
        except VGFactura.DoesNotExist:
            raise ValueError('La factura no existe.')
    else:
        raise ValueError('Tipo de documento inválido.')

    if documento.estado == 'anulada':
        raise ValueError('Este documento ya fue anulado.')

    return autorizador, documento


def _convertir_monto_ajuste_a_usd(documento, monto_input):
    """
    `monto_input` llega en la moneda EN LA QUE ESTÁ EL DOCUMENTO (nota.moneda:
    'USD' o 'VES') — igual que un abono (ver nota_entrega_abono_view), pero
    acá no hay un método de pago de por medio (no se cobra nada nuevo), así
    que se convierte contra la moneda propia del documento con la misma tasa
    que se usaría para cobrarle un saldo pendiente hoy (ver
    _tasa_conversion_vigente: congelada si es de hoy, BCV de hoy si es
    fiado de días anteriores).
    """
    # No se redondea a centavos de dolar aca a proposito (mismo motivo que
    # VGPago.monto usa 6 decimales, no 2): redondear ANTES de restarlo del
    # total dejaba un residuo de varios bolivares al reconvertir para
    # mostrarlo (reportado 2026-09 — un ajuste de Bs cuyo total nuevo, visto
    # en bolivares, ya no cuadraba exacto con lo que el cliente pago). El
    # unico redondeo a 2 decimales ocurre una sola vez, al final, sobre
    # documento.total/saldo_pendiente (que si son de 2 decimales en la BD).
    if getattr(documento, 'moneda', 'USD') != 'VES':
        return monto_input.quantize(Decimal('0.000001'))
    tasa_pago_actual = obtener_tasa_actual()
    tasa_conversion = _tasa_conversion_vigente(
        documento.moneda, documento.fecha_emision, documento.tasa_cambio_referencia, tasa_pago_actual,
    )
    if not tasa_conversion or tasa_conversion <= 0:
        raise ValueError('No hay tasa de cambio disponible para convertir el monto a dólares.')
    return (monto_input / tasa_conversion).quantize(Decimal('0.000001'))


@transaction.atomic
def aplicar_ajuste_parcial(documento_tipo, documento_id, usuario, motivo, motivo_detalle,
                            monto_ajuste, autorizador_username, autorizador_password, saldar_completo=False):
    """
    'ajuste_parcial': a diferencia de reembolso/canje/credito_futuro, NO anula
    el documento — le baja el total y el saldo_pendiente por `monto_ajuste` y
    lo deja vivo. Para cuando parte del pedido tuvo un problema (ej. medio
    pollo dañado) y se cobró de menos, pero el cliente ya se fue: no hay nada
    que reabrir, ni reembolsar, ni ningun VGPago que revertir — la plata que
    sí entró se queda tal cual en su cuenta.

    `monto_ajuste` nunca puede superar el saldo_pendiente actual del
    documento: este mecanismo solo puede descontar lo que TODAVÍA no se ha
    cobrado, nunca plata que ya está en caja (para devolver dinero ya cobrado
    existe 'reembolso', que sí revierte el VGPago correspondiente).

    `saldar_completo=True` ignora `monto_ajuste` y usa directamente
    documento.saldo_pendiente (ya en USD, sin pasar por ninguna conversión a
    bolívares) — la única forma de dejar el saldo en exactamente $0.00 sin
    arrastrar el redondeo de convertir un monto en Bs escrito a mano. Úsalo
    cuando el cliente ya pagó lo que faltaba y solo queda "cerrar" la nota,
    en vez de pedirle a la cajera que calcule cuántos Bs faltan.
    """
    autorizador, documento = _validar_autorizacion_y_documento(
        documento_tipo, documento_id, motivo, 'ajuste_parcial', autorizador_username, autorizador_password,
    )

    if saldar_completo:
        monto_ajuste = documento.saldo_pendiente
        if monto_ajuste <= 0:
            raise ValueError('Esta nota ya no tiene saldo pendiente que saldar.')
    else:
        try:
            monto_ajuste_input = Decimal(str(monto_ajuste))
        except Exception:
            raise ValueError('El monto del ajuste no es válido.')
        if monto_ajuste_input <= 0:
            raise ValueError('El monto del ajuste debe ser mayor a cero.')
        # monto_ajuste_input llega en la moneda del documento (Bs si nota.moneda
        # es VES) — se convierte a USD, que es como se guardan total/saldo_pendiente.
        monto_ajuste = _convertir_monto_ajuste_a_usd(documento, monto_ajuste_input)
        if monto_ajuste > documento.saldo_pendiente:
            if monto_ajuste - documento.saldo_pendiente <= TOLERANCIA_AJUSTE_USD:
                monto_ajuste = documento.saldo_pendiente
            else:
                raise ValueError(
                    f'El ajuste (${monto_ajuste}) no puede ser mayor al saldo pendiente (${documento.saldo_pendiente}) — '
                    'para descontar dinero que ya se cobró, usa "Reembolso" en su lugar.'
                )

    numero_nc = VGCorrelativoFiscal.siguiente('NOTA_CREDITO')
    nota_credito = VGNotaCredito.objects.create(
        numero=numero_nc,
        documento_tipo=documento_tipo,
        nota_entrega=documento if documento_tipo == 'nota_entrega' else None,
        factura=documento if documento_tipo == 'factura' else None,
        monto=monto_ajuste.quantize(Decimal('0.000001')),
        moneda=getattr(documento, 'moneda', 'USD'),
        motivo=motivo,
        motivo_detalle=motivo_detalle,
        tipo_resolucion='ajuste_parcial',
        autorizado_por=autorizador,
        numero_control_referenciado=(
            f'{documento.numero_control:08d}' if documento_tipo == 'factura' else documento.codigo
        ),
        creado_por=usuario,
        actualizado_por=usuario,
    )

    # 6 decimales, no 2 — ver el comentario en VGNotaEntrega.total/saldo_pendiente
    # sobre por que (con 2 decimales, "saldar completo" seguia dejando un
    # residuo de varios bolivares frente a lo que el cliente de verdad pago).
    documento.total = (documento.total - monto_ajuste).quantize(Decimal('0.000001'))
    documento.saldo_pendiente = (documento.saldo_pendiente - monto_ajuste).quantize(Decimal('0.000001'))
    if documento.saldo_pendiente <= 0:
        documento.estado = 'pagada'
    elif documento.saldo_pendiente < documento.total:
        documento.estado = 'abonada_parcial'
    else:
        documento.estado = 'pendiente_pago'
    documento.actualizado_por = usuario
    documento.save(update_fields=['total', 'saldo_pendiente', 'estado', 'actualizado_por', 'fecha_actualizacion'])

    orden = getattr(documento, 'orden_cobro', None)
    if orden is not None:
        orden.monto_total = documento.total
        orden.saldo_pendiente = documento.saldo_pendiente
        orden.estado = 'saldada' if documento.saldo_pendiente <= 0 else 'parcial'
        orden.actualizado_por = usuario
        orden.save(update_fields=['monto_total', 'saldo_pendiente', 'estado', 'actualizado_por', 'fecha_actualizacion'])

    return nota_credito


@transaction.atomic
def aplicar_canje_item(documento_tipo, documento_id, usuario, motivo, motivo_detalle,
                        detalle_pedido_id, monto_ajuste, autorizador_username, autorizador_password,
                        saldar_completo=False):
    """
    'canje_item': para cuando SOLO uno de los platos de un pedido con varios
    items tiene un problema (ej. 1 de 5 platos) — a diferencia de 'canje', NO
    anula la nota completa ni cancela el pedido ni marca como merma platos
    que el cliente sí se comió bien. Solo:
      - registra la merma del item puntual (`detalle_pedido_id`),
      - dejar una nota en el pedido de qué item se cambió y por qué NC,
      - opcionalmente baja el total/saldo_pendiente del documento por
        `monto_ajuste` si el plato de reemplazo vale menos (0 = mismo valor,
        no toca el total — el caso más común).
    El VGPago NUNCA se toca aquí (el dinero ya cobrado se queda igual que en
    'canje'). El pedido de reemplazo se arma después desde Nuevo Pedido
    pasando `nota_credito_id` (ver pedido_create_view en api_views.py), igual
    que en 'canje' — la diferencia es que aquí el resto del pedido original
    queda intacto en vez de cancelado.

    `saldar_completo=True` — ver aplicar_ajuste_parcial: usa
    documento.saldo_pendiente directo, sin pasar por conversión de Bs.
    """
    autorizador, documento = _validar_autorizacion_y_documento(
        documento_tipo, documento_id, motivo, 'canje_item', autorizador_username, autorizador_password,
    )

    try:
        detalle = VGDetallePedido.objects.select_related('pedido', 'producto').get(pk=detalle_pedido_id)
    except VGDetallePedido.DoesNotExist:
        raise ValueError('El ítem seleccionado ya no existe.')
    if not documento.pedidos.filter(pk=detalle.pedido_id).exists():
        raise ValueError('Ese ítem no pertenece a este documento.')

    if saldar_completo:
        monto_ajuste = documento.saldo_pendiente
        if monto_ajuste <= 0:
            raise ValueError('Esta nota ya no tiene saldo pendiente que saldar.')
    else:
        try:
            monto_ajuste_input = Decimal(str(monto_ajuste)) if monto_ajuste not in (None, '') else Decimal('0')
        except Exception:
            raise ValueError('El monto del ajuste no es válido.')
        if monto_ajuste_input < 0:
            raise ValueError('El monto del ajuste no puede ser negativo.')
        # Igual que en aplicar_ajuste_parcial: llega en la moneda del documento.
        monto_ajuste = (
            _convertir_monto_ajuste_a_usd(documento, monto_ajuste_input) if monto_ajuste_input > 0 else Decimal('0')
        )
    if monto_ajuste > documento.saldo_pendiente:
        if monto_ajuste - documento.saldo_pendiente <= TOLERANCIA_AJUSTE_USD:
            monto_ajuste = documento.saldo_pendiente
        else:
            raise ValueError(
                f'El ajuste (${monto_ajuste}) no puede ser mayor al saldo pendiente (${documento.saldo_pendiente}) — '
                'para descontar dinero que ya se cobró, usa "Reembolso" en su lugar.'
            )

    numero_nc = VGCorrelativoFiscal.siguiente('NOTA_CREDITO')
    nota_credito = VGNotaCredito.objects.create(
        numero=numero_nc,
        documento_tipo=documento_tipo,
        nota_entrega=documento if documento_tipo == 'nota_entrega' else None,
        factura=documento if documento_tipo == 'factura' else None,
        monto=(monto_ajuste if monto_ajuste > 0 else detalle.subtotal).quantize(Decimal('0.000001')),
        moneda=getattr(documento, 'moneda', 'USD'),
        motivo=motivo,
        motivo_detalle=motivo_detalle,
        tipo_resolucion='canje_item',
        autorizado_por=autorizador,
        detalle_pedido_origen=detalle,
        numero_control_referenciado=(
            f'{documento.numero_control:08d}' if documento_tipo == 'factura' else documento.codigo
        ),
        creado_por=usuario,
        actualizado_por=usuario,
    )

    VGMerma.objects.create(
        nota_credito=nota_credito,
        producto=detalle.producto,
        cantidad=detalle.cantidad,
        motivo='devolucion_cliente',
        registrado_por=usuario,
    )

    pedido = detalle.pedido
    pedido.notas = f'{pedido.notas}\n[{detalle.producto.nombre} cambiado por devolución {nota_credito.codigo}]'.strip()
    pedido.actualizado_por = usuario
    pedido.save(update_fields=['notas', 'actualizado_por', 'fecha_actualizacion'])

    if monto_ajuste > 0:
        documento.total = (documento.total - monto_ajuste).quantize(Decimal('0.000001'))
        documento.saldo_pendiente = (documento.saldo_pendiente - monto_ajuste).quantize(Decimal('0.000001'))
        if documento.saldo_pendiente <= 0:
            documento.estado = 'pagada'
        elif documento.saldo_pendiente < documento.total:
            documento.estado = 'abonada_parcial'
        documento.actualizado_por = usuario
        documento.save(update_fields=['total', 'saldo_pendiente', 'estado', 'actualizado_por', 'fecha_actualizacion'])

        orden = getattr(documento, 'orden_cobro', None)
        if orden is not None:
            orden.monto_total = documento.total
            orden.saldo_pendiente = documento.saldo_pendiente
            orden.estado = 'saldada' if documento.saldo_pendiente <= 0 else 'parcial'
            orden.actualizado_por = usuario
            orden.save(update_fields=['monto_total', 'saldo_pendiente', 'estado', 'actualizado_por', 'fecha_actualizacion'])

    return nota_credito


@transaction.atomic
def revertir_y_reabrir_pedido(documento_tipo, documento_id, usuario, motivo, motivo_detalle,
                               tipo_resolucion, autorizador_username, autorizador_password):
    """
    Nucleo transaccional de la devolucion TOTAL (para 'ajuste_parcial' ver
    aplicar_ajuste_parcial). `motivo` responde POR QUE se anulo;
    `tipo_resolucion` responde QUE PASA CON EL DINERO, y son independientes:

      - 'reembolso': se le devuelve la plata al cliente de verdad -> se anulan
        los VGPago del documento (sale del banco/caja) y el pedido NO se
        reabre (no hay nada mas que preparar ni cobrar).
      - 'canje': el cliente se lleva otro plato del mismo valor -> la plata
        NUNCA salio del negocio, asi que los VGPago quedan intactos; el
        pedido se reabre pero directo en estado 'pagado' (ya esta cubierto
        por el pago original, no debe volver a pedirsele cobro a la cajera).
      - 'credito_futuro': tampoco sale plata, pero el cliente no se lleva
        nada hoy -> se guarda un VGCreditoCliente con el saldo, y no se
        reabre ningun pedido todavia.

    En los tres casos se anula el documento original al 100% (nunca una
    modificacion parcial) y se registra la merma de los platos devueltos
    (esa comida no vuelve a inventario sin importar que pasa con el dinero).

    Lanza:
      - PermissionError si la autorizacion del Gerente/Supervisor falla,
      - ValueError para cualquier otra condicion de rechazo (motivo o tipo de
        resolucion invalidos, documento inexistente/ya anulado, sin pedidos
        que reabrir, credito_futuro sin cliente identificado),
    para que el caller (la vista) los traduzca a la respuesta HTTP.
    """
    autorizador, documento = _validar_autorizacion_y_documento(
        documento_tipo, documento_id, motivo, tipo_resolucion, autorizador_username, autorizador_password,
    )

    pedidos_originales = list(
        documento.pedidos.select_for_update().prefetch_related('detalles__producto')
    )
    if not pedidos_originales:
        raise ValueError('El documento no tiene pedidos asociados para reabrir.')

    cliente_credito = None
    if tipo_resolucion == 'credito_futuro':
        cliente_credito = getattr(documento, 'cliente', None) or next(
            (pedido.cliente for pedido in pedidos_originales if pedido.cliente_id), None,
        )
        if cliente_credito is None:
            raise ValueError(
                'Para dejar un crédito a favor debes identificar al cliente en el pedido original.'
            )

    documento.estado = 'anulada'
    if hasattr(documento, 'motivo_anulacion'):
        documento.motivo_anulacion = (
            f'{dict(VGNotaCredito.MOTIVOS)[motivo]} — devolución autorizada por {autorizador.username}'
        )
        documento.actualizado_por = usuario
        documento.save(update_fields=['estado', 'motivo_anulacion', 'actualizado_por', 'fecha_actualizacion'])
    else:
        documento.actualizado_por = usuario
        documento.save(update_fields=['estado', 'actualizado_por', 'fecha_actualizacion'])

    orden = getattr(documento, 'orden_cobro', None)
    if orden is not None:
        orden.estado = 'anulada'
        orden.actualizado_por = usuario
        orden.save(update_fields=['estado', 'actualizado_por', 'fecha_actualizacion'])

    numero_nc = VGCorrelativoFiscal.siguiente('NOTA_CREDITO')
    total_documento = sum((pedido.total for pedido in pedidos_originales), Decimal('0'))
    nota_credito = VGNotaCredito.objects.create(
        numero=numero_nc,
        documento_tipo=documento_tipo,
        nota_entrega=documento if documento_tipo == 'nota_entrega' else None,
        factura=documento if documento_tipo == 'factura' else None,
        monto=total_documento,
        moneda=getattr(documento, 'moneda', 'USD'),
        motivo=motivo,
        motivo_detalle=motivo_detalle,
        tipo_resolucion=tipo_resolucion,
        autorizado_por=autorizador,
        numero_control_referenciado=(
            f'{documento.numero_control:08d}' if documento_tipo == 'factura' else documento.codigo
        ),
        creado_por=usuario,
        actualizado_por=usuario,
    )

    # Revierte el DINERO ya cobrado del documento original SOLO si de verdad
    # sale del negocio ('reembolso'): en vez de crear movimientos negativos,
    # se anula cada VGPago completado (mismo patron que factura_anular_view
    # usa para la orden de cobro) — reportes.py filtra `estado='completado'`
    # en cada consulta de cuadre de caja, asi que esto descuenta
    # automaticamente lo devuelto de la cuenta/metodo de pago exacto que se
    # uso para cobrar, sin tocar reportes.py. En 'canje'/'credito_futuro' la
    # plata nunca salio del negocio (el cliente se lleva otro plato o un
    # credito, no efectivo), asi que los VGPago quedan intactos a proposito.
    pagos_revertidos = []
    if tipo_resolucion == 'reembolso':
        pagos_revertidos = list(documento.pagos.filter(estado='completado'))
        for pago in pagos_revertidos:
            pago.estado = 'anulado'
            pago.anulado_por_nota_credito = nota_credito
            pago.save(update_fields=['estado', 'anulado_por_nota_credito'])

    # 'canje' NO clona el pedido aca: en vez de adivinar que plato nuevo
    # quiere el cliente (el original ya no sirve, por eso lo esta devolviendo),
    # la cajera arma el pedido de reemplazo desde Nuevo Pedido — como
    # cualquier pedido normal, con su propio catalogo — pasandole
    # `nota_credito_id` (ver pedido_create_view en api_views.py). Ese endpoint
    # fuerza mesa=None y liga nota_credito_origen, y pedidos_cobro_view/
    # pedidos_delivery_view excluyen esos pedidos de la lista de cobro porque
    # ya estan pagados con el dinero del documento anulado arriba. 'reembolso'
    # y 'credito_futuro' no generan ningun pedido: el cliente ya se fue con
    # su plata o con un credito, no con comida por preparar.
    pedidos_reabiertos = []
    for pedido_original in pedidos_originales:
        for detalle in pedido_original.detalles.all():
            VGMerma.objects.create(
                nota_credito=nota_credito,
                producto=detalle.producto,
                cantidad=detalle.cantidad,
                motivo='devolucion_cliente',
                registrado_por=usuario,
            )
        pedido_original.estado = 'cancelado'
        pedido_original.notas = (
            f'{pedido_original.notas}\n[Reemplazado por devolución {nota_credito.codigo}]'.strip()
        )
        pedido_original.actualizado_por = usuario
        pedido_original.save(update_fields=['estado', 'notas', 'actualizado_por', 'fecha_actualizacion'])

    if pedidos_reabiertos:
        nota_credito.pedido_nuevo = pedidos_reabiertos[0]
        nota_credito.save(update_fields=['pedido_nuevo'])

    credito_generado = None
    if tipo_resolucion == 'credito_futuro':
        credito_generado = VGCreditoCliente.objects.create(
            nota_credito=nota_credito,
            cliente=cliente_credito,
            monto=total_documento,
            saldo_disponible=total_documento,
            moneda=nota_credito.moneda,
            creado_por=usuario,
            actualizado_por=usuario,
        )

    return nota_credito, pedidos_reabiertos, pagos_revertidos, credito_generado


# ---------------------------------------------------------------------------
# Serializacion para el reporte interactivo
# ---------------------------------------------------------------------------
def _serialize_nota_credito_resumen(nota_credito):
    documento = nota_credito.documento_original
    return {
        'id': nota_credito.id,
        'codigo': nota_credito.codigo,
        'numero': nota_credito.numero,
        'documento_tipo': nota_credito.documento_tipo,
        'documento_codigo': (
            f'{documento.numero_factura:08d}' if nota_credito.documento_tipo == 'factura' and documento else
            (documento.codigo if documento else '')
        ),
        'monto': str(nota_credito.monto),
        'moneda': nota_credito.moneda,
        'motivo': nota_credito.motivo,
        'motivo_display': dict(VGNotaCredito.MOTIVOS).get(nota_credito.motivo, nota_credito.motivo),
        'motivo_detalle': nota_credito.motivo_detalle,
        'tipo_resolucion': nota_credito.tipo_resolucion,
        'tipo_resolucion_display': dict(VGNotaCredito.TIPOS_RESOLUCION).get(
            nota_credito.tipo_resolucion, nota_credito.tipo_resolucion,
        ),
        'autorizado_por': nota_credito.autorizado_por.get_full_name() or nota_credito.autorizado_por.username,
        'creado_por': (nota_credito.creado_por.get_full_name() or nota_credito.creado_por.username) if nota_credito.creado_por_id else '',
        'fecha_emision': nota_credito.fecha_emision.isoformat(),
        'pedido_nuevo_id': nota_credito.pedido_nuevo_id,
    }


def _serialize_nota_credito_detalle(nota_credito):
    data = _serialize_nota_credito_resumen(nota_credito)
    documento = nota_credito.documento_original

    pedidos_reabiertos = list(nota_credito.pedidos_reabiertos.select_related('mesa').prefetch_related('detalles__producto'))
    pedidos_originales = list(documento.pedidos.all()) if documento else []

    data.update({
        'numero_control_referenciado': nota_credito.numero_control_referenciado,
        'item_cambiado': (
            {
                'pedido_id': nota_credito.detalle_pedido_origen.pedido_id,
                'producto': nota_credito.detalle_pedido_origen.producto.nombre,
                'cantidad': nota_credito.detalle_pedido_origen.cantidad,
                'subtotal': str(nota_credito.detalle_pedido_origen.subtotal),
            }
            if nota_credito.detalle_pedido_origen_id else None
        ),
        'documento_original': {
            'id': documento.id,
            'estado': documento.estado,
            'total': str(documento.total),
            'motivo_anulacion': getattr(documento, 'motivo_anulacion', ''),
            'fecha_emision': documento.fecha_emision.isoformat(),
        } if documento else None,
        'pedidos_originales': [
            {
                'id': pedido.id,
                'estado': pedido.estado,
                'tipo_pedido': pedido.tipo_pedido,
                'total': str(pedido.total),
                'items': [
                    {'producto': detalle.producto.nombre, 'cantidad': detalle.cantidad, 'subtotal': str(detalle.subtotal)}
                    for detalle in pedido.detalles.all()
                ],
            }
            for pedido in pedidos_originales
        ],
        'pedidos_reabiertos': [
            {
                'id': pedido.id,
                'estado': pedido.estado,
                'total': str(pedido.total),
                'creado_en': pedido.fecha_creacion.isoformat(),
            }
            for pedido in pedidos_reabiertos
        ],
        'pagos_revertidos': [
            {
                'id': pago.id,
                'monto': str(pago.monto),
                'metodo_pago': pago.metodo_pago.nombre,
                'moneda': pago.metodo_pago.moneda,
                'referencia': pago.referencia,
                'fecha_pago': pago.fecha_pago.isoformat(),
            }
            for pago in nota_credito.pagos_revertidos.select_related('metodo_pago').all()
        ],
        'mermas': [
            {
                'id': merma.id,
                'producto': merma.producto.nombre,
                'cantidad': merma.cantidad,
                'motivo': merma.motivo,
                'registrado_por': (merma.registrado_por.get_full_name() or merma.registrado_por.username) if merma.registrado_por_id else '',
                'fecha_registro': merma.fecha_registro.isoformat(),
            }
            for merma in nota_credito.mermas.select_related('producto', 'registrado_por').all()
        ],
        'credito_generado': (
            {
                'id': nota_credito.credito_generado.id,
                'cliente': nota_credito.credito_generado.cliente.nombre,
                'monto': str(nota_credito.credito_generado.monto),
                'saldo_disponible': str(nota_credito.credito_generado.saldo_disponible),
                'estado': nota_credito.credito_generado.estado,
            }
            if hasattr(nota_credito, 'credito_generado') else None
        ),
    })
    return data


def _parse_fecha(valor):
    try:
        return date.fromisoformat(valor)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Vistas HTTP
# ---------------------------------------------------------------------------
@csrf_exempt
def devolucion_crear_view(request):
    if request.method != 'POST':
        return _auth_response({'ok': False, 'message': 'Método no permitido.'}, status=405)
    if not (_is_admin_user(request.user) or _is_cajera_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para iniciar una devolución.'}, status=401)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON inválido.'}, status=400)

    documento_tipo = str(data.get('documento_tipo', '') or '').strip()
    documento_id = data.get('documento_id')
    motivo = str(data.get('motivo', '') or '').strip()
    motivo_detalle = str(data.get('motivo_detalle', '') or '').strip()
    tipo_resolucion = str(data.get('tipo_resolucion', '') or '').strip()
    autorizador_username = str(data.get('autorizador_username', '') or '').strip()
    autorizador_password = str(data.get('autorizador_password', '') or '')

    if not documento_id or not tipo_resolucion or not autorizador_username or not autorizador_password:
        return _auth_response({'ok': False, 'message': 'Faltan datos obligatorios.'}, status=400)

    try:
        documento_id = int(documento_id)
    except (TypeError, ValueError):
        return _auth_response({'ok': False, 'message': 'Documento inválido.'}, status=400)

    if tipo_resolucion == 'ajuste_parcial':
        saldar_completo = bool(data.get('saldar_completo'))
        monto_ajuste = data.get('monto_ajuste')
        if not saldar_completo and not monto_ajuste:
            return _auth_response({'ok': False, 'message': 'Indica el monto del ajuste.'}, status=400)
        try:
            nota_credito = aplicar_ajuste_parcial(
                documento_tipo=documento_tipo,
                documento_id=documento_id,
                usuario=request.user,
                motivo=motivo,
                motivo_detalle=motivo_detalle,
                monto_ajuste=monto_ajuste,
                autorizador_username=autorizador_username,
                autorizador_password=autorizador_password,
                saldar_completo=saldar_completo,
            )
        except PermissionError as error:
            return _auth_response({'ok': False, 'message': str(error)}, status=403)
        except ValueError as error:
            return _auth_response({'ok': False, 'message': str(error)}, status=400)

        documento = nota_credito.documento_original
        return _auth_response({
            'ok': True,
            'message': f'Ajuste registrado — {nota_credito.codigo}.',
            'nota_credito': _serialize_nota_credito_resumen(nota_credito),
            'documento_nuevo_total': str(documento.total),
            'documento_nuevo_saldo_pendiente': str(documento.saldo_pendiente),
        }, status=201)

    if tipo_resolucion == 'canje_item':
        detalle_pedido_id = data.get('detalle_pedido_id')
        if not detalle_pedido_id:
            return _auth_response({'ok': False, 'message': 'Selecciona el ítem a cambiar.'}, status=400)
        try:
            detalle_pedido_id = int(detalle_pedido_id)
        except (TypeError, ValueError):
            return _auth_response({'ok': False, 'message': 'Ítem inválido.'}, status=400)
        try:
            nota_credito = aplicar_canje_item(
                documento_tipo=documento_tipo,
                documento_id=documento_id,
                usuario=request.user,
                motivo=motivo,
                motivo_detalle=motivo_detalle,
                detalle_pedido_id=detalle_pedido_id,
                monto_ajuste=data.get('monto_ajuste'),
                autorizador_username=autorizador_username,
                autorizador_password=autorizador_password,
                saldar_completo=bool(data.get('saldar_completo')),
            )
        except PermissionError as error:
            return _auth_response({'ok': False, 'message': str(error)}, status=403)
        except ValueError as error:
            return _auth_response({'ok': False, 'message': str(error)}, status=400)

        documento = nota_credito.documento_original
        return _auth_response({
            'ok': True,
            'message': f'Canje de ítem registrado — {nota_credito.codigo}.',
            'nota_credito': _serialize_nota_credito_resumen(nota_credito),
            'documento_nuevo_total': str(documento.total),
            'documento_nuevo_saldo_pendiente': str(documento.saldo_pendiente),
        }, status=201)

    try:
        nota_credito, pedidos_reabiertos, pagos_revertidos, credito_generado = revertir_y_reabrir_pedido(
            documento_tipo=documento_tipo,
            documento_id=documento_id,
            usuario=request.user,
            motivo=motivo,
            motivo_detalle=motivo_detalle,
            tipo_resolucion=tipo_resolucion,
            autorizador_username=autorizador_username,
            autorizador_password=autorizador_password,
        )
    except PermissionError as error:
        return _auth_response({'ok': False, 'message': str(error)}, status=403)
    except ValueError as error:
        return _auth_response({'ok': False, 'message': str(error)}, status=400)

    return _auth_response({
        'ok': True,
        'message': f'Devolución registrada — {nota_credito.codigo}.',
        'nota_credito': _serialize_nota_credito_resumen(nota_credito),
        'pedidos_reabiertos': [pedido.id for pedido in pedidos_reabiertos],
        'pagos_revertidos': len(pagos_revertidos),
        'credito_generado': (
            {'id': credito_generado.id, 'saldo_disponible': str(credito_generado.saldo_disponible)}
            if credito_generado else None
        ),
    }, status=201)


def notas_credito_view(request):
    """
    Reporte interactivo de devoluciones: lista filtrable por rango de fecha
    y motivo, mas un bloque `analisis` con los agregados fundamentales
    (total devuelto, cantidad, motivo mas frecuente, producto con mas
    mermas, tendencia por dia) — para responder de un vistazo "cuanto se
    esta devolviendo y por que" sin tener que sumarlo a mano fila por fila.
    """
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Método no permitido.'}, status=405)
    if not (_is_admin_user(request.user) or _is_cajera_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para ver este reporte.'}, status=401)

    hoy = timezone.localdate()
    desde = _parse_fecha(request.GET.get('desde')) or (hoy - timedelta(days=30))
    hasta = _parse_fecha(request.GET.get('hasta')) or hoy
    if desde > hasta:
        return _auth_response({'ok': False, 'message': '"Desde" no puede ser posterior a "Hasta".'}, status=400)

    motivo_filtro = str(request.GET.get('motivo', '') or '').strip()

    queryset = (
        VGNotaCredito.objects
        .filter(fecha_emision__date__gte=desde, fecha_emision__date__lte=hasta)
        .select_related('nota_entrega', 'factura', 'autorizado_por', 'creado_por')
    )
    if motivo_filtro:
        queryset = queryset.filter(motivo=motivo_filtro)
    queryset = queryset.order_by('-fecha_emision')

    notas = list(queryset)

    total_devuelto = sum((nc.monto for nc in notas), Decimal('0'))
    por_motivo = (
        VGNotaCredito.objects
        .filter(fecha_emision__date__gte=desde, fecha_emision__date__lte=hasta)
        .values('motivo')
        .annotate(cantidad=Count('id'), monto=Sum('monto'))
        .order_by('-monto')
    )
    por_dia = (
        VGNotaCredito.objects
        .filter(fecha_emision__date__gte=desde, fecha_emision__date__lte=hasta)
        .annotate(dia=TruncDate('fecha_emision'))
        .values('dia')
        .annotate(cantidad=Count('id'), monto=Sum('monto'))
        .order_by('dia')
    )
    top_productos_merma = (
        VGMerma.objects
        .filter(nota_credito__fecha_emision__date__gte=desde, nota_credito__fecha_emision__date__lte=hasta)
        .values('producto__nombre')
        .annotate(cantidad=Sum('cantidad'), veces=Count('id'))
        .order_by('-cantidad')[:10]
    )
    top_autorizadores = (
        VGNotaCredito.objects
        .filter(fecha_emision__date__gte=desde, fecha_emision__date__lte=hasta)
        .values('autorizado_por__username', 'autorizado_por__first_name', 'autorizado_por__last_name')
        .annotate(cantidad=Count('id'), monto=Sum('monto'))
        .order_by('-cantidad')
    )

    return _auth_response({
        'ok': True,
        'desde': desde.isoformat(),
        'hasta': hasta.isoformat(),
        'notas_credito': [_serialize_nota_credito_resumen(nc) for nc in notas],
        'motivos_catalogo': [{'valor': valor, 'etiqueta': etiqueta} for valor, etiqueta in VGNotaCredito.MOTIVOS],
        'tipos_resolucion_catalogo': [
            {'valor': valor, 'etiqueta': etiqueta} for valor, etiqueta in VGNotaCredito.TIPOS_RESOLUCION
        ],
        'analisis': {
            'total_devuelto': str(total_devuelto),
            'cantidad_total': len(notas),
            'por_motivo': [
                {
                    'motivo': fila['motivo'],
                    'motivo_display': dict(VGNotaCredito.MOTIVOS).get(fila['motivo'], fila['motivo']),
                    'cantidad': fila['cantidad'],
                    'monto': str(fila['monto'] or Decimal('0')),
                }
                for fila in por_motivo
            ],
            'por_dia': [
                {'dia': str(fila['dia']), 'cantidad': fila['cantidad'], 'monto': str(fila['monto'] or Decimal('0'))}
                for fila in por_dia
            ],
            'top_productos_merma': [
                {
                    'producto': fila['producto__nombre'],
                    'cantidad': fila['cantidad'],
                    'veces': fila['veces'],
                }
                for fila in top_productos_merma
            ],
            'top_autorizadores': [
                {
                    'usuario': fila['autorizado_por__username'],
                    'nombre': (
                        f"{fila['autorizado_por__first_name']} {fila['autorizado_por__last_name']}".strip()
                        or fila['autorizado_por__username']
                    ),
                    'cantidad': fila['cantidad'],
                    'monto': str(fila['monto'] or Decimal('0')),
                }
                for fila in top_autorizadores
            ],
        },
    })


def nota_credito_detail_view(request, nota_credito_id):
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Método no permitido.'}, status=405)
    if not (_is_admin_user(request.user) or _is_cajera_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para ver esta nota de crédito.'}, status=401)

    try:
        nota_credito = (
            VGNotaCredito.objects
            .select_related('nota_entrega', 'factura', 'autorizado_por', 'creado_por', 'detalle_pedido_origen__producto')
            .get(pk=nota_credito_id)
        )
    except VGNotaCredito.DoesNotExist:
        return _auth_response({'ok': False, 'message': 'La nota de crédito no existe.'}, status=404)

    return _auth_response({'ok': True, 'nota_credito': _serialize_nota_credito_detalle(nota_credito)})

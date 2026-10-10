"""
Tasa de la cuenta (pre-factura): respeta la tasa que se le dijo al cliente.

Problema que resuelve: se le entrega al cliente la pre-factura con un monto en Bs a la tasa
del momento; si mientras espera cambia la tasa BCV, la nota de entrega (o la factura) nacia con
la tasa NUEVA y el cliente veia otro monto. Ahora, mientras la pre-factura este vigente y dentro
de la ventana (VENTANA_TASA_PREFACTURA_MIN, 60 min por defecto) el documento que se emite
hereda la tasa de la pre-factura. Pasada la ventana, o si no hay pre-factura, se usa la tasa
actual como siempre.

La ventana cuenta desde `tasa_fijada_en` (cuando se congelo la tasa), NO desde la emision de la
pre-factura: reimprimirla dentro de la ventana conserva la misma tasa y la misma hora de
congelado, asi que reimprimir nunca "estira" la tasa vieja (ver prefacturas_view).
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Count, F, Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import VGPreFactura
from .tasa_cambio import tasa_cambio_para_registro


def ventana_tasa_cuenta():
    return timedelta(minutes=int(getattr(settings, 'VENTANA_TASA_PREFACTURA_MIN', 60)))


def fijada_en(prefactura):
    """Cuando se congelo su tasa. Las pre-facturas anteriores a este cambio no lo tienen: usan su emision."""
    return prefactura.tasa_fijada_en or prefactura.fecha_emision


def minutos_restantes(prefactura, ahora=None):
    """Minutos que le quedan a la tasa de esta pre-factura (0 si ya vencio)."""
    ahora = ahora or timezone.now()
    restante = fijada_en(prefactura) + ventana_tasa_cuenta() - ahora
    return max(int(restante.total_seconds() // 60), 0)


def _vigentes_con_tasa(ahora):
    limite = ahora - ventana_tasa_cuenta()
    return (
        VGPreFactura.objects
        .filter(estado='vigente', tasa_cambio_referencia__isnull=False)
        .annotate(tasa_desde=Coalesce(F('tasa_fijada_en'), F('fecha_emision')))
        .filter(tasa_desde__gte=limite)
    )


def prefactura_que_cubre(pedido_ids, ahora=None):
    """
    La pre-factura vigente y dentro de la ventana, mas reciente, cuyos pedidos incluyen TODOS
    `pedido_ids`. Si solo cubre una parte de lo que se esta cobrando (o es de otra mesa) no
    aplica: no se mezclan cuentas. Devuelve la pre-factura o None.
    """
    ids = sorted({int(pedido_id) for pedido_id in pedido_ids})
    if not ids:
        return None
    ahora = ahora or timezone.now()
    return (
        _vigentes_con_tasa(ahora)
        .annotate(cubiertos=Count('pedidos', filter=Q(pedidos__id__in=ids), distinct=True))
        .filter(cubiertos=len(ids))
        .order_by('-fecha_emision', '-id')
        .first()
    )


def prefacturas_con_tasa_vigente(ahora=None):
    """Para la pantalla de cobro: pre-facturas con tasa todavia valida, con sus pedidos y minutos restantes."""
    ahora = ahora or timezone.now()
    resultado = []
    for prefactura in _vigentes_con_tasa(ahora).prefetch_related('pedidos').order_by('-fecha_emision', '-id'):
        resultado.append({
            'id': prefactura.id,
            'codigo': f'PF-{prefactura.numero:06d}',
            'tasa': str(prefactura.tasa_cambio_referencia),
            'moneda': prefactura.moneda,
            'pedido_ids': [pedido.id for pedido in prefactura.pedidos.all()],
            'minutos_restantes': minutos_restantes(prefactura, ahora),
        })
    return resultado


def resolver_tasa_cuenta(pedido_ids, usar_tasa_actual=False, prefactura=None, ahora=None):
    """
    Tasa con la que se debe emitir una nota de entrega / factura de estos pedidos.

    prefactura: si el documento nace de una pre-factura concreta (convertirla en factura), esa es
    la candidata; si no, se busca la que cubra los pedidos. usar_tasa_actual=True salta la
    pre-factura a proposito (la cajera decidio cobrar a la tasa de hoy).

    Devuelve un dict: tasa (Decimal o None si no hay ninguna), origen ('prefactura' | 'actual'),
    prefactura (la usada, o None) y vencio (True si habia una pre-factura vigente de estos pedidos pero ya paso la ventana).
    """
    ahora = ahora or timezone.now()
    candidata = None
    vencida = False
    if not usar_tasa_actual:
        if prefactura is not None:
            if prefactura.estado == 'vigente' and prefactura.tasa_cambio_referencia is not None:
                if minutos_restantes(prefactura, ahora) > 0:
                    candidata = prefactura
                else:
                    vencida = True
        else:
            candidata = prefactura_que_cubre(pedido_ids, ahora)

    if candidata is not None:
        return {'tasa': Decimal(candidata.tasa_cambio_referencia), 'origen': 'prefactura', 'prefactura': candidata, 'vencio': False}

    if not usar_tasa_actual and prefactura is None and not vencida:
        # Sin candidata por busqueda: puede que si haya una pre-factura de estos pedidos pero ya vencida.
        ids = sorted({int(pedido_id) for pedido_id in pedido_ids})
        vencida = bool(ids) and (
            VGPreFactura.objects
            .filter(estado='vigente', tasa_cambio_referencia__isnull=False)
            .annotate(cubiertos=Count('pedidos', filter=Q(pedidos__id__in=ids), distinct=True))
            .filter(cubiertos=len(ids))
            .exists()
        )
    return {'tasa': tasa_cambio_para_registro(), 'origen': 'actual', 'prefactura': None, 'vencio': vencida}

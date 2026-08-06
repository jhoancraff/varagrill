import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

import requests
from django.utils import timezone

from .models import VGTasaCambio

logger = logging.getLogger(__name__)

BCV_API_URL = "https://ve.dolarapi.com/v1/dolares/oficial"
BCV_REQUEST_TIMEOUT = 5
TASA_TTL = timedelta(hours=6)


def _fetch_tasa_bcv():
    """Consulta el proveedor externo que replica la tasa oficial del BCV."""
    response = requests.get(BCV_API_URL, timeout=BCV_REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    return Decimal(str(data["promedio"]))


def obtener_tasa_actual(forzar_actualizacion=False):
    """
    Devuelve la última VGTasaCambio conocida, refrescándola contra la fuente
    externa si está vencida (o si no hay ninguna todavía). Si la fuente
    externa falla, se devuelve silenciosamente la última tasa cacheada
    (o None si nunca se pudo obtener una) en vez de romper al usuario.
    """
    ultima = VGTasaCambio.objects.order_by("-fecha_actualizacion").first()
    vencida = ultima is None or timezone.now() - ultima.fecha_actualizacion > TASA_TTL

    if not (forzar_actualizacion or vencida):
        return ultima

    try:
        tasa = _fetch_tasa_bcv()
    except (requests.RequestException, InvalidOperation, KeyError, TypeError, ValueError) as exc:
        logger.warning("No se pudo actualizar la tasa BCV, se usa la última cacheada: %s", exc)
        return ultima

    hoy = timezone.localdate()
    ultima, _created = VGTasaCambio.objects.update_or_create(
        fecha=hoy, defaults={"tasa": tasa, "fuente": "BCV"},
    )
    return ultima
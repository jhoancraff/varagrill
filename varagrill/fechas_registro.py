"""
Fecha REAL de un gasto, una compra o un abono, frente al momento en que se registran.

En la base de datos siempre queda el momento exacto del registro (fecha_creacion / fecha_pago, automaticos).
Pero quien registra elige ademas la fecha en que de verdad ocurrio la compra, el gasto o el pago — por ejemplo
cuando se le olvido cargar algo de ayer — y esa es la que usan los reportes de caja, banco y conciliacion:

  VGGasto.fecha_gasto   VGCompra.fecha_factura   VGAbonoGasto.fecha_abono   VGAbonoCompra.fecha_abono

Este modulo reune lo que comparten los lugares donde se elige o se corrige una de esas fechas:
  - parse_fecha_real: la fecha elegida debe ser valida y no futura (sin fecha = hoy).
  - advertencias_dias_cerrados: avisos cuando la fecha cae en un dia con la caja o la conciliacion bancaria
    ya cerradas (los totales de ese dia cambiarian despues del cierre).
  - exigir_aceptadas / respuesta_confirmacion: mismo protocolo que gastos_inhabilitacion — la primera vez la
    API responde 409 con `requiere_confirmacion` y las advertencias; el cliente las muestra y reenvia con
    `aceptadas: [codigos]`.
"""
from datetime import date

from django.utils import timezone

from . import conciliacion_bancaria as motor
from .auth_helpers import _auth_response
from .models import VGCierreCaja


class FechaInvalida(Exception):
    """La fecha no es valida o es futura. Se responde 400."""


class RequiereConfirmacion(Exception):
    """Faltan advertencias por aceptar (`advertencias`). Se responde 409."""

    def __init__(self, advertencias):
        super().__init__('Faltan advertencias por aceptar.')
        self.advertencias = advertencias


def fecha_texto(valor):
    return valor.strftime('%d/%m/%Y')


def parse_fecha_real(raw, nombre='fecha'):
    """
    La fecha elegida como `date`. Vacia = hoy (la fecha por defecto de todos los formularios). Lanza
    FechaInvalida si no es una fecha ISO o si es posterior a hoy: nada se puede haber hecho en el futuro.
    """
    texto = str(raw or '').strip()
    hoy = timezone.localdate()
    if not texto:
        return hoy
    try:
        fecha = date.fromisoformat(texto)
    except ValueError:
        raise FechaInvalida(f'La {nombre} no es valida.')
    if fecha > hoy:
        raise FechaInvalida(f'La {nombre} no puede ser posterior a hoy.')
    return fecha


def advertencias_dias_cerrados(fechas, metodo_pago):
    """
    Advertencias por cada dia de `fechas` que ya esta cerrado para el metodo de pago: la caja del dia (si se
    paga en efectivo) o la conciliacion bancaria de su cuenta (si tiene cuenta bancaria). El codigo incluye la
    fecha para que aceptar un dia no acepte otro.
    """
    advertencias = []
    if metodo_pago is None:
        return advertencias
    cuenta = motor.normalizar_cuenta(metodo_pago.cuenta_bancaria)
    for fecha in sorted(set(fechas)):
        if metodo_pago.es_efectivo and VGCierreCaja.objects.filter(fecha=fecha).exists():
            advertencias.append({
                'codigo': f'caja_cerrada_{fecha.isoformat()}',
                'mensaje': (
                    f'La caja del {fecha_texto(fecha)} ya fue cerrada: este pago en efectivo cambia el efectivo '
                    'esperado de ese dia, pero el cierre ya guardado no se recalcula.'
                ),
                'detalle': [],
            })
        if cuenta and not metodo_pago.es_efectivo and fecha in motor.fechas_cerradas(cuenta, fecha, fecha):
            advertencias.append({
                'codigo': f'conciliacion_cerrada_{fecha.isoformat()}',
                'mensaje': (
                    f'La conciliacion bancaria de {cuenta} del {fecha_texto(fecha)} ya esta cerrada: este pago '
                    'cambia los movimientos de ese dia ya revisados.'
                ),
                'detalle': [],
            })
    return advertencias


def exigir_aceptadas(advertencias, aceptadas):
    """Lanza RequiereConfirmacion si alguna advertencia no esta en `aceptadas` (lista de codigos)."""
    aceptadas = {str(codigo) for codigo in (aceptadas or [])}
    faltan = [a for a in advertencias if a['codigo'] not in aceptadas]
    if faltan:
        raise RequiereConfirmacion(faltan)


def respuesta_confirmacion(exc):
    return _auth_response({
        'ok': False,
        'requiere_confirmacion': True,
        'advertencias': exc.advertencias,
        'message': 'Confirma las advertencias para continuar.',
    }, status=409)

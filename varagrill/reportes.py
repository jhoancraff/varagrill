"""
Agregaciones de solo lectura para el modulo de Contabilidad. Cada reporte nuevo
agrega una funcion aqui que lee de las tablas operativas existentes (VGPago,
VGPedido, VGCompra, ...) sin duplicar datos en tablas de reporte aparte.
"""
from decimal import Decimal

from django.db.models import Sum

from .models import VGAbonoGasto, VGConsignacionCaja, VGMetodoPago, VGPago, VGTasaCambio


def tasa_para_fecha(fecha):
    """Tasa BCV vigente en `fecha`: la ultima conocida en o antes de ese dia (o None si no hay ninguna)."""
    fila = VGTasaCambio.objects.filter(fecha__lte=fecha).order_by('-fecha').first()
    return fila.tasa if fila else None


def totales_pagos_por_metodo(fecha):
    """
    Lista de {id, nombre, es_efectivo, moneda, total, total_bs} por cada
    metodo de pago activo, con lo cobrado (VGPago completados) en `fecha`.
    Un metodo desactivado que igual tuvo pagos ese dia se incluye tambien,
    para no ocultar historico.

    `total` siempre esta en USD (asi se guarda VGPago.monto). Para un metodo
    en bolivares (moneda='VES'), `total_bs` trae ese mismo monto convertido
    con la tasa BCV vigente en `fecha` — None si no hay ninguna tasa
    registrada para esa fecha o antes.
    """
    metodos_por_id = {
        metodo.id: {
            'id': metodo.id,
            'nombre': metodo.nombre,
            'es_efectivo': metodo.es_efectivo,
            'moneda': metodo.moneda,
            'total': Decimal('0'),
        }
        for metodo in VGMetodoPago.objects.filter(activo=True)
    }

    filas = (
        VGPago.objects
        .filter(fecha_pago__date=fecha, estado='completado')
        .values('metodo_pago_id', 'metodo_pago__nombre', 'metodo_pago__es_efectivo', 'metodo_pago__moneda')
        .annotate(total=Sum('monto'))
    )
    for fila in filas:
        metodo_id = fila['metodo_pago_id']
        if metodo_id not in metodos_por_id:
            metodos_por_id[metodo_id] = {
                'id': metodo_id,
                'nombre': fila['metodo_pago__nombre'],
                'es_efectivo': fila['metodo_pago__es_efectivo'],
                'moneda': fila['metodo_pago__moneda'],
                'total': Decimal('0'),
            }
        metodos_por_id[metodo_id]['total'] = fila['total'] or Decimal('0')

    tasa = tasa_para_fecha(fecha)
    for metodo in metodos_por_id.values():
        if metodo['moneda'] == 'VES' and tasa:
            metodo['total_bs'] = (metodo['total'] * tasa).quantize(Decimal('0.01'))
        else:
            metodo['total_bs'] = None

    return sorted(metodos_por_id.values(), key=lambda item: item['nombre'])


def desglose_caja_por_moneda(fecha):
    """
    Agrupa lo cobrado en `fecha` (mismo criterio que totales_pagos_por_metodo)
    en las 4 combinaciones que le interesan a un cierre de caja: moneda
    (USD/VES) x tipo (fisico/digital, segun VGMetodoPago.es_efectivo) — para
    poder darle a alguien un desglose tipo "cuanto entro en bolivares en
    digital, cuanto en bolivares en fisico, cuanto en dolares en fisico y
    cuanto en dolares en digital", igual que se clasifica cada cuenta
    (nota de entrega/pre-factura/factura) por su metodo de pago.

    Los baldes en bolivares llevan total_usd (el monto tal cual se guarda en
    VGPago) y total_bs (convertido con la tasa BCV de `fecha`, None si algun
    metodo de ese balde no tiene tasa disponible ese dia). Los baldes en
    dolares no necesitan conversion.
    """
    buckets = {
        'bs_fisico': {'total_usd': Decimal('0'), 'total_bs': Decimal('0'), '_falta_tasa': False},
        'bs_digital': {'total_usd': Decimal('0'), 'total_bs': Decimal('0'), '_falta_tasa': False},
        'usd_fisico': {'total_usd': Decimal('0')},
        'usd_digital': {'total_usd': Decimal('0')},
    }

    for metodo in totales_pagos_por_metodo(fecha):
        if metodo['moneda'] == 'VES':
            clave = 'bs_fisico' if metodo['es_efectivo'] else 'bs_digital'
            buckets[clave]['total_usd'] += metodo['total']
            if metodo['total_bs'] is not None:
                buckets[clave]['total_bs'] += metodo['total_bs']
            else:
                buckets[clave]['_falta_tasa'] = True
        else:
            clave = 'usd_fisico' if metodo['es_efectivo'] else 'usd_digital'
            buckets[clave]['total_usd'] += metodo['total']

    for clave in ('bs_fisico', 'bs_digital'):
        if buckets[clave].pop('_falta_tasa'):
            buckets[clave]['total_bs'] = None

    return buckets


def gastos_efectivo_dia(fecha):
    """Suma de VGAbonoGasto en `fecha` pagados con un metodo que cuenta como efectivo fisico."""
    total = (
        VGAbonoGasto.objects
        .filter(fecha_pago__date=fecha, metodo_pago__es_efectivo=True)
        .aggregate(total=Sum('monto'))
        .get('total')
    )
    return total or Decimal('0')


def efectivo_esperado_dia(fecha):
    """
    Efectivo fisico que deberia haber en caja al final de `fecha`: lo cobrado en efectivo
    (VGPago) menos lo pagado en efectivo por gastos operativos (VGAbonoGasto) — si un gasto
    sale de la caja física y no se descuenta aquí, el cierre marcaría un faltante fantasma.
    """
    ingresos = (
        VGPago.objects
        .filter(fecha_pago__date=fecha, estado='completado', metodo_pago__es_efectivo=True)
        .aggregate(total=Sum('monto'))
        .get('total')
    ) or Decimal('0')
    return ingresos - gastos_efectivo_dia(fecha)


def total_consignado(fecha):
    total = (
        VGConsignacionCaja.objects
        .filter(fecha=fecha)
        .aggregate(total=Sum('monto'))
        .get('total')
    )
    return total or Decimal('0')

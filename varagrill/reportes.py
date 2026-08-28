"""
Agregaciones de solo lectura para el modulo de Contabilidad. Cada reporte nuevo
agrega una funcion aqui que lee de las tablas operativas existentes (VGPago,
VGPedido, VGCompra, ...) sin duplicar datos en tablas de reporte aparte.
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum

from .models import (
    VGAbonoCompra,
    VGAbonoGasto,
    VGCierreCaja,
    VGConsignacionCaja,
    VGMetodoPago,
    VGPago,
    VGTasaCambio,
)


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


def _rango_fechas(desde, hasta):
    fecha = desde
    while fecha <= hasta:
        yield fecha
        fecha += timedelta(days=1)


def resumen_cuadre_caja_rango(desde, hasta):
    """
    Cuadre de caja para un rango de fechas (`desde`/`hasta` inclusive):
    recorre cada dia reusando exactamente la misma logica del cuadre diario
    (totales_pagos_por_metodo, total_consignado, gastos_efectivo_dia,
    efectivo_esperado_dia) y devuelve tanto el desglose dia por dia — cada
    uno con su cierre si ya lo tiene, para que se vea cuales dias del rango
    faltan por cerrar — como los totales acumulados de todo el rango.

    La conversion a bolivares se hace dia por dia con la tasa BCV vigente
    ESE dia (nunca una tasa unica para todo el rango), asi el total en Bs
    del rango completo sigue siendo exacto aunque la tasa haya cambiado a
    mitad de camino. Este reporte es de solo lectura — cerrar caja sigue
    siendo una accion por dia individual, atada a un conteo fisico de
    efectivo de ese dia especifico.
    """
    dias = []
    metodos_acumulados = {}
    bs_fisico = {'total_usd': Decimal('0'), 'total_bs': Decimal('0'), '_falta_tasa': False}
    bs_digital = {'total_usd': Decimal('0'), 'total_bs': Decimal('0'), '_falta_tasa': False}
    usd_fisico = Decimal('0')
    usd_digital = Decimal('0')
    total_consignado_acum = Decimal('0')
    gastos_efectivo_acum = Decimal('0')
    efectivo_esperado_acum = Decimal('0')

    cierres_por_fecha = {
        cierre.fecha: cierre
        for cierre in VGCierreCaja.objects.filter(fecha__gte=desde, fecha__lte=hasta).select_related('creado_por')
    }

    for fecha in _rango_fechas(desde, hasta):
        totales_dia = totales_pagos_por_metodo(fecha)
        total_general_dia = sum((item['total'] for item in totales_dia), Decimal('0'))
        consignado_dia = total_consignado(fecha)
        gastos_dia = gastos_efectivo_dia(fecha)
        efectivo_esperado_dia_valor = efectivo_esperado_dia(fecha)

        for item in totales_dia:
            entry = metodos_acumulados.setdefault(item['id'], {
                'id': item['id'],
                'nombre': item['nombre'],
                'es_efectivo': item['es_efectivo'],
                'moneda': item['moneda'],
                'total': Decimal('0'),
                'total_bs': Decimal('0') if item['moneda'] == 'VES' else None,
                '_falta_tasa': False,
            })
            entry['total'] += item['total']
            if item['moneda'] == 'VES':
                if item['total_bs'] is not None:
                    entry['total_bs'] += item['total_bs']
                else:
                    entry['_falta_tasa'] = True

                bucket = bs_fisico if item['es_efectivo'] else bs_digital
                bucket['total_usd'] += item['total']
                if item['total_bs'] is not None:
                    bucket['total_bs'] += item['total_bs']
                else:
                    bucket['_falta_tasa'] = True
            else:
                if item['es_efectivo']:
                    usd_fisico += item['total']
                else:
                    usd_digital += item['total']

        total_consignado_acum += consignado_dia
        gastos_efectivo_acum += gastos_dia
        efectivo_esperado_acum += efectivo_esperado_dia_valor

        dias.append({
            'fecha': fecha,
            'tasa_bcv': tasa_para_fecha(fecha),
            'total_general': total_general_dia,
            'total_consignado': consignado_dia,
            'gastos_efectivo': gastos_dia,
            'efectivo_esperado': efectivo_esperado_dia_valor,
            'cierre': cierres_por_fecha.get(fecha),
        })

    for entry in metodos_acumulados.values():
        if entry['moneda'] == 'VES' and entry['_falta_tasa']:
            entry['total_bs'] = None
        entry.pop('_falta_tasa', None)

    for bucket in (bs_fisico, bs_digital):
        if bucket.pop('_falta_tasa'):
            bucket['total_bs'] = None

    return {
        'dias': dias,
        'totales_por_metodo': sorted(metodos_acumulados.values(), key=lambda item: item['nombre']),
        'desglose_caja': {
            'bs_fisico': bs_fisico,
            'bs_digital': bs_digital,
            'usd_fisico': {'total_usd': usd_fisico},
            'usd_digital': {'total_usd': usd_digital},
        },
        'total_general': sum((item['total'] for item in metodos_acumulados.values()), Decimal('0')),
        'total_consignado': total_consignado_acum,
        'gastos_efectivo': gastos_efectivo_acum,
        'efectivo_esperado': efectivo_esperado_acum,
    }


def disponibilidad_por_cuenta(fecha):
    """
    Saldo acumulado disponible en cada metodo de pago ("cuenta") hasta
    `fecha` inclusive — como un estado de cuenta: todo lo cobrado con ese
    metodo (VGPago completados) menos todo lo pagado con ese metodo a
    gastos operativos (VGAbonoGasto) y a proveedores (VGAbonoCompra),
    acumulado desde que existe el sistema (no solo el movimiento de un dia).

    El metodo marcado como efectivo fisico ademas resta lo consignado
    (VGConsignacionCaja) hasta esa fecha, porque ese dinero ya salio
    fisicamente de la caja. VGConsignacionCaja no distingue de cual metodo
    salio (en la practica el negocio solo tiene una caja fisica), asi que el
    total consignado se resta completo del primer metodo marcado como
    efectivo que exista — si algun dia hubiera mas de uno, habria que sumar
    aqui un criterio para repartirlo.
    """
    metodos = list(VGMetodoPago.objects.all().order_by('nombre'))

    def _totales_por_metodo(queryset):
        filas = queryset.values('metodo_pago_id').annotate(total=Sum('monto'))
        return {fila['metodo_pago_id']: fila['total'] for fila in filas}

    ingresos_por_metodo = _totales_por_metodo(
        VGPago.objects.filter(fecha_pago__date__lte=fecha, estado='completado')
    )
    gastos_por_metodo = _totales_por_metodo(
        VGAbonoGasto.objects.filter(fecha_pago__date__lte=fecha)
    )
    compras_por_metodo = _totales_por_metodo(
        VGAbonoCompra.objects.filter(fecha_pago__date__lte=fecha)
    )
    consignado_acumulado = (
        VGConsignacionCaja.objects
        .filter(fecha__lte=fecha)
        .aggregate(total=Sum('monto'))
        .get('total')
    ) or Decimal('0')

    primer_efectivo_id = next((metodo.id for metodo in metodos if metodo.es_efectivo), None)

    resultado = []
    for metodo in metodos:
        ingresos = ingresos_por_metodo.get(metodo.id) or Decimal('0')
        gastos = gastos_por_metodo.get(metodo.id) or Decimal('0')
        compras = compras_por_metodo.get(metodo.id) or Decimal('0')
        consignado = consignado_acumulado if metodo.id == primer_efectivo_id else Decimal('0')
        resultado.append({
            'id': metodo.id,
            'nombre': metodo.nombre,
            'moneda': metodo.moneda,
            'es_efectivo': metodo.es_efectivo,
            'activo': metodo.activo,
            'ingresos_acumulados': ingresos,
            'gastos_acumulados': gastos,
            'compras_acumuladas': compras,
            'consignado_acumulado': consignado,
            'saldo_disponible': ingresos - gastos - compras - consignado,
        })
    return resultado

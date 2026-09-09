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
    VGIngresoExtra,
    VGMetodoPago,
    VGNotaEntrega,
    VGPago,
    VGTasaCambio,
)


def tasa_para_fecha(fecha):
    """Tasa BCV vigente en `fecha`: la ultima conocida en o antes de ese dia (o None si no hay ninguna)."""
    fila = VGTasaCambio.objects.filter(fecha__lte=fecha).order_by('-fecha').first()
    return fila.tasa if fila else None


def totales_pagos_por_metodo(fecha):
    """
    Lista de {id, nombre, es_efectivo, moneda, ventas, ingresos_extra, total,
    total_bs} por cada metodo de pago activo, con lo cobrado (VGPago
    completados) en `fecha`. Un metodo desactivado que igual tuvo movimiento
    ese dia se incluye tambien, para no ocultar historico.

    `total` = `ventas` + `ingresos_extra`: las propinas y "pagos extra"
    (VGIngresoExtra) de ese metodo ese dia se suman al total de la cuenta
    igual que una venta — es la misma plata que entro por ahi, solo que no
    vino de un VGPago. `ventas` e `ingresos_extra` quedan aparte para poder
    mostrar el detalle (ver reporte_cuadre_caja_view). Todo siempre en USD
    (asi se guardan los montos).

    Para un metodo en bolivares (moneda='VES'), `total_bs` NO es `total *
    tasa_de_fecha` — cada VGPago se convierte con SU PROPIA tasa congelada
    (pago.tasa_cambio_referencia), que nota_entrega_abono_view/
    factura_abono_view sellan con el BCV del dia en que ese pago en concreto
    se registro (ver esas vistas: para una nota/factura pendiente en
    bolivares, se cobra al valor del dolar del dia del cobro, no al del dia
    en que se emitio, para que el fiado no pierda valor mientras esta
    pendiente). Si el documento (nota_entrega/factura) no tiene tasa propia
    en el pago (dato viejo previo a este cambio), se cae a la tasa congelada
    del documento, y en ultimo caso a la de `fecha`. Los ingresos extra usan
    su propia tasa (o la de `fecha`) igual que siempre: por diseño siempre se
    registran el mismo dia que aparecen aca (ver VGIngresoExtra), asi que no
    hay tasa vieja de la que arrastrar un desfase. `total_bs` es None solo si
    algun pago en bolivares de ese metodo ese dia no tiene ninguna tasa
    resoluble (ni la propia, ni la del documento, ni la de `fecha`).
    """
    tasa_fecha = tasa_para_fecha(fecha)

    metodos_por_id = {
        metodo.id: {
            'id': metodo.id,
            'nombre': metodo.nombre,
            'es_efectivo': metodo.es_efectivo,
            'moneda': metodo.moneda,
            'cuenta_bancaria': metodo.cuenta_bancaria,
            'ventas': Decimal('0'),
            'ingresos_extra': Decimal('0'),
            'ventas_bs': Decimal('0'),
            '_bs_incompleto': False,
        }
        for metodo in VGMetodoPago.objects.filter(activo=True)
    }

    def _metodo_entry(metodo_id, nombre, es_efectivo, moneda, cuenta_bancaria=''):
        if metodo_id not in metodos_por_id:
            metodos_por_id[metodo_id] = {
                'id': metodo_id,
                'nombre': nombre,
                'es_efectivo': es_efectivo,
                'moneda': moneda,
                'cuenta_bancaria': cuenta_bancaria,
                'ventas': Decimal('0'),
                'ingresos_extra': Decimal('0'),
                'ventas_bs': Decimal('0'),
                '_bs_incompleto': False,
            }
        return metodos_por_id[metodo_id]

    pagos = (
        VGPago.objects
        .filter(fecha_pago__date=fecha, estado='completado')
        .select_related('metodo_pago', 'nota_entrega', 'factura')
    )
    for pago in pagos:
        metodo = pago.metodo_pago
        entry = _metodo_entry(metodo.id, metodo.nombre, metodo.es_efectivo, metodo.moneda, metodo.cuenta_bancaria)
        entry['ventas'] += pago.monto
        if metodo.moneda == 'VES':
            tasa_pago = (
                pago.tasa_cambio_referencia
                or (pago.nota_entrega.tasa_cambio_referencia if pago.nota_entrega_id else None)
                or (pago.factura.tasa_cambio_referencia if pago.factura_id else None)
                or tasa_fecha
            )
            if tasa_pago:
                entry['ventas_bs'] += (pago.monto * tasa_pago).quantize(Decimal('0.01'))
            else:
                entry['_bs_incompleto'] = True

    ingresos_extra_dia = VGIngresoExtra.objects.filter(fecha_creacion__date=fecha).select_related('metodo_pago')
    for ingreso in ingresos_extra_dia:
        metodo = ingreso.metodo_pago
        entry = _metodo_entry(metodo.id, metodo.nombre, metodo.es_efectivo, metodo.moneda, metodo.cuenta_bancaria)
        entry['ingresos_extra'] += ingreso.monto
        if metodo.moneda == 'VES':
            # Igual que con los VGPago de arriba: cada ingreso extra congela su
            # propia tasa al registrarse (ver ingresos_extra_view) — se usa esa,
            # no la de `fecha`, para que el monto en bolivares coincida con lo
            # que la cajera de verdad contó, incluso si el BCV se refrescó otra
            # vez mas tarde ese mismo dia.
            tasa_ingreso = ingreso.tasa_cambio_referencia or tasa_fecha
            if tasa_ingreso:
                entry['ventas_bs'] += (ingreso.monto * tasa_ingreso).quantize(Decimal('0.01'))
            else:
                entry['_bs_incompleto'] = True

    for metodo in metodos_por_id.values():
        metodo['total'] = metodo['ventas'] + metodo['ingresos_extra']
        metodo['total_bs'] = metodo['ventas_bs'] if (metodo['moneda'] == 'VES' and not metodo['_bs_incompleto']) else None
        del metodo['ventas_bs']
        del metodo['_bs_incompleto']

    return sorted(metodos_por_id.values(), key=lambda item: item['nombre'])


def resumen_ventas_rango(desde, hasta):
    """
    Total vendido del rango (Notas de Entrega emitidas entre `desde` y
    `hasta` inclusive, pendientes y pagadas por igual) frente a lo que de
    verdad entro al banco (ver totales_pagos_por_metodo) — para poder
    explicar la diferencia. Generaliza lo que antes era resumen_ventas_dia
    (un dia es sencillamente el caso desde == hasta) para que el cuadre de
    caja diario y el cuadre por rango compartan la misma logica.

    - `total_pendiente` es el fiado generado DENTRO del rango nomás: notas
      emitidas en [desde, hasta] que todavia no se terminan de cobrar (no
      arrastra el pendiente de fechas anteriores al rango — ver
      detalle_cuentas_por_cobrar_rango). Si el banco subio MENOS que
      `total_vendido`, la explicacion mas probable es que parte de esa venta
      quedo fiada.
    - `cuentas_cobradas_hoy` es el recaudo DENTRO del rango de notas emitidas
      en una fecha ANTERIOR al rango (el pendiente de antes que se cobro
      ahora) — ese monto sale del acumulado de `total_pendiente` de su propio
      periodo (porque su saldo_pendiente ya bajo) y se reporta aca en vez de
      sumarse a `total_vendido`: esa venta ya se conto el dia que se emitio
      la nota, contarla otra vez aca la duplicaria.
    - `total_propinas_excedentes` es dinero que SI entro al banco en el rango
      (via VGIngresoExtra) pero que NO es venta — si el banco subio MAS que
      `total_vendido`, esta es la explicacion mas probable. Nunca se suma a
      `total_vendido` a proposito, para no inflar la venta real.
    """
    total_vendido = (
        VGNotaEntrega.objects
        .filter(fecha_emision__date__gte=desde, fecha_emision__date__lte=hasta)
        .aggregate(total=Sum('total'))
        .get('total')
    ) or Decimal('0')

    total_pendiente = (
        VGNotaEntrega.objects
        .filter(fecha_emision__date__gte=desde, fecha_emision__date__lte=hasta)
        .aggregate(total=Sum('saldo_pendiente'))
        .get('total')
    ) or Decimal('0')

    total_propinas_excedentes = (
        VGIngresoExtra.objects
        .filter(fecha_creacion__date__gte=desde, fecha_creacion__date__lte=hasta)
        .aggregate(total=Sum('monto'))
        .get('total')
    ) or Decimal('0')

    cuentas_cobradas_hoy = (
        VGPago.objects
        .filter(fecha_pago__date__gte=desde, fecha_pago__date__lte=hasta, estado='completado', nota_entrega__isnull=False)
        .exclude(nota_entrega__fecha_emision__date__gte=desde, nota_entrega__fecha_emision__date__lte=hasta)
        .aggregate(total=Sum('monto'))
        .get('total')
    ) or Decimal('0')

    return {
        'total_vendido': total_vendido,
        'total_pendiente': total_pendiente,
        'total_propinas_excedentes': total_propinas_excedentes,
        'cuentas_cobradas_hoy': cuentas_cobradas_hoy,
    }


def detalle_ventas_rango(desde, hasta):
    """
    Detalle fila por fila de cada Nota de Entrega emitida entre `desde` y
    `hasta` inclusive — el desglose de "Total vendido" (ver
    resumen_ventas_rango): para saber exactamente que notas se hicieron,
    cuanto es en dolares, cuanto se pago en bolivares (si aplica), con que
    metodo, en que banco (VGMetodoPago.cuenta_bancaria) y con que
    referencia. Un dia individual es sencillamente el caso desde == hasta.

    Una nota puede tener varios pagos (abonos parciales) o ninguno todavia
    (pendiente); se listan todos los pagos completados de esa nota, sin
    importar el dia en que se cobraron (una nota del rango solo puede tener
    pagos de esa fecha en adelante, nunca de antes).
    """
    notas = (
        VGNotaEntrega.objects
        .filter(fecha_emision__date__gte=desde, fecha_emision__date__lte=hasta)
        .select_related('cliente')
        .prefetch_related('pagos__metodo_pago')
        .order_by('fecha_emision')
    )

    resultado = []
    for nota in notas:
        pagos = []
        for pago in nota.pagos.all():
            if pago.estado != 'completado':
                continue
            metodo = pago.metodo_pago
            monto_bs = None
            if metodo.moneda == 'VES':
                tasa = pago.tasa_cambio_referencia or nota.tasa_cambio_referencia
                if tasa:
                    monto_bs = (pago.monto * tasa).quantize(Decimal('0.01'))
            pagos.append({
                'id': pago.id,
                'monto': pago.monto,
                'monto_bs': monto_bs,
                'metodo_pago_id': metodo.id,
                'metodo_pago_nombre': metodo.nombre,
                'cuenta_bancaria': metodo.cuenta_bancaria,
                'referencia': pago.referencia,
                'fecha_pago': pago.fecha_pago,
            })
        resultado.append({
            'id': nota.id,
            'codigo': nota.codigo,
            'cliente': nota.cliente.nombre if nota.cliente_id else '',
            'total': nota.total,
            'moneda': nota.moneda,
            'estado': nota.estado,
            'saldo_pendiente': nota.saldo_pendiente,
            'pagos': pagos,
        })
    return resultado


def detalle_cuentas_por_cobrar_rango(desde, hasta):
    """
    Detalle fila por fila de "Pendiente por cobrar" (ver
    resumen_ventas_rango): las Notas de Entrega emitidas entre `desde` y
    `hasta` inclusive que todavia tienen saldo pendiente — solo el fiado
    generado dentro del rango, no lo arrastrado de fechas anteriores. Un dia
    individual es sencillamente el caso desde == hasta.

    Este reporte es un registro HISTORICO de lo que se generó en el periodo,
    no una proyección de cuánto habría que cobrar hoy — `tasa_cambio_referencia`
    es la tasa BCV que se congeló al EMITIR cada nota (la misma que se le
    cotizó al cliente ese día), no la de hoy. El recálculo a la tasa vigente
    (para saber cuánto cobrar de verdad si el fiado sigue pendiente) sólo
    corresponde en el momento de cobrar — ver
    nota_entrega_abono_view/_tasa_conversion_vigente en facturacion_views.py.
    """
    notas = (
        VGNotaEntrega.objects
        .filter(fecha_emision__date__gte=desde, fecha_emision__date__lte=hasta, saldo_pendiente__gt=0)
        .select_related('cliente')
        .order_by('fecha_emision')
    )
    return [
        {
            'id': nota.id,
            'codigo': nota.codigo,
            'cliente': nota.cliente.nombre if nota.cliente_id else '',
            'total': nota.total,
            'saldo_pendiente': nota.saldo_pendiente,
            'moneda': nota.moneda,
            'tasa_cambio_referencia': nota.tasa_cambio_referencia,
            'estado': nota.estado,
            'fecha_emision': nota.fecha_emision,
        }
        for nota in notas
    ]


def detalle_cuentas_cobradas_rango(desde, hasta):
    """
    Detalle fila por fila de "Cuentas cobradas" (ver resumen_ventas_rango):
    pagos entre `desde` y `hasta` inclusive contra una Nota de Entrega
    emitida en una fecha ANTERIOR al rango — el pendiente de antes que se
    cobro ahora. Un dia individual es sencillamente el caso desde == hasta.

    Para una nota en bolivares, muestra la diferencia entre lo que hubiera
    sido en bolivares a la tasa del dia en que se emitio (`bs_a_tasa_emision`)
    y lo que realmente se cobro a la tasa vigente al momento del pago
    (`bs_a_tasa_cobro`) — la plata sigue siendo el mismo monto en dolares (la
    deuda nunca cambia), pero como el bolivar se devalua mientras el fiado
    esta pendiente, el monto en bolivares que hay que cobrar sube (ver
    nota_entrega_abono_view). Para una nota pagada directo en dolares no
    aplica ninguna tasa (las claves `*_bs`/`tasa_*`/`diferencia_bs` quedan en
    None).
    """
    pagos = (
        VGPago.objects
        .filter(fecha_pago__date__gte=desde, fecha_pago__date__lte=hasta, estado='completado', nota_entrega__isnull=False)
        .exclude(nota_entrega__fecha_emision__date__gte=desde, nota_entrega__fecha_emision__date__lte=hasta)
        .select_related('nota_entrega__cliente', 'metodo_pago')
        .order_by('fecha_pago')
    )

    resultado = []
    for pago in pagos:
        nota = pago.nota_entrega
        metodo = pago.metodo_pago

        tasa_emision = None
        tasa_cobro = None
        bs_a_tasa_emision = None
        bs_a_tasa_cobro = None
        diferencia_bs = None
        if nota.moneda == 'VES':
            tasa_emision = nota.tasa_cambio_referencia
            tasa_cobro = pago.tasa_cambio_referencia
            if tasa_emision:
                bs_a_tasa_emision = (pago.monto * tasa_emision).quantize(Decimal('0.01'))
            if tasa_cobro:
                bs_a_tasa_cobro = (pago.monto * tasa_cobro).quantize(Decimal('0.01'))
            if bs_a_tasa_emision is not None and bs_a_tasa_cobro is not None:
                diferencia_bs = bs_a_tasa_cobro - bs_a_tasa_emision

        resultado.append({
            'pago_id': pago.id,
            'nota_id': nota.id,
            'nota_codigo': nota.codigo,
            'cliente': nota.cliente.nombre if nota.cliente_id else '',
            'monto': pago.monto,
            'moneda': nota.moneda,
            'fecha_emision_nota': nota.fecha_emision,
            'fecha_pago': pago.fecha_pago,
            'tasa_emision': tasa_emision,
            'tasa_cobro': tasa_cobro,
            'bs_a_tasa_emision': bs_a_tasa_emision,
            'bs_a_tasa_cobro': bs_a_tasa_cobro,
            'diferencia_bs': diferencia_bs,
            'metodo_pago_nombre': metodo.nombre,
            'cuenta_bancaria': metodo.cuenta_bancaria,
            'referencia': pago.referencia,
        })
    return resultado


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
    VGPago) y total_bs (la suma de cada pago ya convertido con SU tasa
    congelada — ver totales_pagos_por_metodo — no con la de `fecha`; None si
    algun metodo de ese balde no tiene ninguna tasa resoluble ese dia). Los
    baldes en dolares no necesitan conversion.
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
    (VGPago) mas las propinas/pagos extra (VGIngresoExtra) cobrados en efectivo, menos lo
    pagado en efectivo por gastos operativos (VGAbonoGasto) — si una propina en efectivo no
    se suma aqui (o un gasto no se resta), el cierre marcaria una diferencia fantasma con lo
    que en verdad hay contado en la caja fisica.
    """
    ingresos = (
        VGPago.objects
        .filter(fecha_pago__date=fecha, estado='completado', metodo_pago__es_efectivo=True)
        .aggregate(total=Sum('monto'))
        .get('total')
    ) or Decimal('0')
    ingresos_extra = (
        VGIngresoExtra.objects
        .filter(fecha_creacion__date=fecha, metodo_pago__es_efectivo=True)
        .aggregate(total=Sum('monto'))
        .get('total')
    ) or Decimal('0')
    return ingresos + ingresos_extra - gastos_efectivo_dia(fecha)


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

    Tambien suma las propinas y "pagos extra" (VGIngresoExtra) cobrados con ese
    metodo — no pasan por VGPago (no son parte de ninguna venta) pero son
    dinero real que entro por esa cuenta igual.

    Devuelve (cuentas, bancos): `cuentas` es la lista de siempre, una fila por
    metodo de pago; `bancos` agrupa esas mismas filas por VGMetodoPago.cuenta_bancaria
    (varios metodos pueden caer en el mismo banco real, ej. Pago Movil y Punto
    de Venta ambos en Banesco) sumando sus saldos, con el detalle de cada
    metodo debajo. Un metodo sin cuenta_bancaria se agrupa solo, bajo su
    propio nombre.
    """
    # Los metodos desactivados no deben aparecer en la disponibilidad de
    # cuentas: si un banco/metodo esta deshabilitado, el usuario no quiere
    # verlo en este reporte (aunque tenga movimientos historicos).
    metodos = list(VGMetodoPago.objects.filter(activo=True).order_by('nombre'))

    def _totales_por_metodo(queryset):
        filas = queryset.values('metodo_pago_id').annotate(total=Sum('monto'))
        return {fila['metodo_pago_id']: fila['total'] for fila in filas}

    ingresos_por_metodo = _totales_por_metodo(
        VGPago.objects.filter(fecha_pago__date__lte=fecha, estado='completado')
    )
    ingresos_extra_por_metodo = _totales_por_metodo(
        VGIngresoExtra.objects.filter(fecha_creacion__date__lte=fecha)
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
        ingresos_extra = ingresos_extra_por_metodo.get(metodo.id) or Decimal('0')
        gastos = gastos_por_metodo.get(metodo.id) or Decimal('0')
        compras = compras_por_metodo.get(metodo.id) or Decimal('0')
        consignado = consignado_acumulado if metodo.id == primer_efectivo_id else Decimal('0')
        resultado.append({
            'id': metodo.id,
            'nombre': metodo.nombre,
            'moneda': metodo.moneda,
            'es_efectivo': metodo.es_efectivo,
            'cuenta_bancaria': metodo.cuenta_bancaria,
            'activo': metodo.activo,
            'ingresos_acumulados': ingresos,
            'ingresos_extra_acumulados': ingresos_extra,
            'gastos_acumulados': gastos,
            'compras_acumuladas': compras,
            'consignado_acumulado': consignado,
            'saldo_disponible': ingresos + ingresos_extra - gastos - compras - consignado,
        })

    # Agrupa por cuenta_bancaria — varias filas de `resultado` con el mismo
    # texto (ej. "Banesco") son en la vida real un solo banco recibiendo por
    # metodos distintos (Pago Movil, Punto de Venta...). Sin cuenta_bancaria,
    # cada metodo forma su propio grupo de un solo elemento, bajo su nombre.
    bancos_por_clave = {}
    orden_claves = []
    for cuenta in resultado:
        clave = cuenta['cuenta_bancaria'] or f"__metodo_{cuenta['id']}"
        if clave not in bancos_por_clave:
            bancos_por_clave[clave] = {
                'nombre': cuenta['cuenta_bancaria'] or cuenta['nombre'],
                'agrupado': bool(cuenta['cuenta_bancaria']),
                'metodos': [],
                'ingresos_acumulados': Decimal('0'),
                'ingresos_extra_acumulados': Decimal('0'),
                'gastos_acumulados': Decimal('0'),
                'compras_acumuladas': Decimal('0'),
                'consignado_acumulado': Decimal('0'),
                'saldo_disponible': Decimal('0'),
            }
            orden_claves.append(clave)
        banco = bancos_por_clave[clave]
        banco['metodos'].append(cuenta)
        banco['ingresos_acumulados'] += cuenta['ingresos_acumulados']
        banco['ingresos_extra_acumulados'] += cuenta['ingresos_extra_acumulados']
        banco['gastos_acumulados'] += cuenta['gastos_acumulados']
        banco['compras_acumuladas'] += cuenta['compras_acumuladas']
        banco['consignado_acumulado'] += cuenta['consignado_acumulado']
        banco['saldo_disponible'] += cuenta['saldo_disponible']
        # Un banco agrupado con monedas mixtas no deberia pasar en la
        # practica (una cuenta bancaria real tiene una sola moneda) — se dej
        # a la del primer metodo, y se marca la inconsistencia si aparece.
        banco.setdefault('moneda', cuenta['moneda'])
        if banco['moneda'] != cuenta['moneda']:
            banco['moneda_mixta'] = True

    bancos = [bancos_por_clave[clave] for clave in orden_claves]
    return resultado, bancos

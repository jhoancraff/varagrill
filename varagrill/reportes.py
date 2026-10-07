"""
Agregaciones de solo lectura para el modulo de Contabilidad. Cada reporte nuevo
agrega una funcion aqui que lee de las tablas operativas existentes (VGPago,
VGPedido, VGCompra, ...) sin duplicar datos en tablas de reporte aparte.
"""
import calendar
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from .models import (
    VGAbonoCompra,
    VGAbonoGasto,
    VGCierreCaja,
    VGConsignacionCaja,
    VGIngresoExtra,
    VGLotePOS,
    VGMetodoPago,
    VGNotaCredito,
    VGNotaEntrega,
    VGPago,
    VGTasaCambio,
    VGTransferenciaCuenta,
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

    # El cuadre de caja es lo que se vendio / entro por ventas: un "ingreso no
    # facturado" (deposito directo a una cuenta, ver VGIngresoExtra.TIPOS) no es
    # venta, solo cuenta en disponibilidad por cuenta y flujo bancario.
    ingresos_extra_dia = (
        VGIngresoExtra.objects.filter(fecha_creacion__date=fecha)
        .exclude(tipo='ingreso_no_facturado')
        .select_related('metodo_pago')
    )
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
    - `total_devuelto` suma el `monto` de toda VGNotaCredito emitida en el
      rango, sin importar tipo_resolucion — es informativo (cuanto se
      devolvio/ajusto en total), no se resta de `total_vendido` ni de ningun
      otro campo de aqui: cada tipo_resolucion ya decide por su cuenta si
      afecta el banco/caja (ver VGPago.anulado_por_nota_credito en
      devoluciones_views.py) o el propio total_vendido (ajuste_parcial baja
      el total de la VGNotaEntrega directamente, asi que ya se refleja solo).
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
        .exclude(tipo='ingreso_no_facturado')
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

    total_devuelto = (
        VGNotaCredito.objects
        .filter(fecha_emision__date__gte=desde, fecha_emision__date__lte=hasta)
        .aggregate(total=Sum('monto'))
        .get('total')
    ) or Decimal('0')

    return {
        'total_vendido': total_vendido,
        'total_pendiente': total_pendiente,
        'total_propinas_excedentes': total_propinas_excedentes,
        'cuentas_cobradas_hoy': cuentas_cobradas_hoy,
        'total_devuelto': total_devuelto,
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
                'metodo_pago_moneda': metodo.moneda,
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
            'fecha_emision': nota.fecha_emision,
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
        .exclude(tipo='ingreso_no_facturado')
        .aggregate(total=Sum('monto'))
        .get('total')
    ) or Decimal('0')
    return ingresos + ingresos_extra - gastos_efectivo_dia(fecha)


def efectivo_esperado_por_moneda(fecha):
    """
    El efectivo esperado de `fecha` (mismo criterio que efectivo_esperado_dia: cobros
    y propinas/extra en efectivo menos gastos pagados en efectivo) separado por
    moneda — lo que debe haber fisicamente en la gaveta en dolares y en bolivares.

      - usd: efectivo de metodos en dolares (cobros + extras − gastos pagados con ellos).
      - bs: efectivo de metodos en bolivares, en bolivares REALES: cada cobro a su
        tasa congelada (nunca la de hoy) y cada gasto pagado en bs por el mismo monto
        de bolivares con que se registro. None si algun movimiento no tiene tasa.
      - bs_en_usd: lo mismo que `bs` pero en dolares (la parte del efectivo esperado
        que viene de metodos en bolivares), para que usd + bs_en_usd == efectivo_esperado_dia.
    """
    usd = Decimal('0')
    bs = Decimal('0')
    bs_en_usd = Decimal('0')
    falta_tasa = False
    gastos_usd = Decimal('0')
    gastos_bs = Decimal('0')

    for metodo in totales_pagos_por_metodo(fecha):
        if not metodo['es_efectivo']:
            continue
        if metodo['moneda'] == 'VES':
            bs_en_usd += metodo['total']
            if metodo['total_bs'] is None:
                falta_tasa = True
            else:
                bs += metodo['total_bs']
        else:
            usd += metodo['total']

    for abono in (
        VGAbonoGasto.objects
        .filter(fecha_pago__date=fecha, metodo_pago__es_efectivo=True)
        .select_related('metodo_pago')
    ):
        if abono.metodo_pago.moneda == 'VES':
            tasa = abono.tasa_cambio_referencia or tasa_para_fecha(fecha)
            bs_en_usd -= abono.monto
            gastos_usd += abono.monto
            if tasa:
                monto_bs = (abono.monto * tasa).quantize(Decimal('0.01'))
                bs -= monto_bs
                gastos_bs += monto_bs
            else:
                falta_tasa = True
        else:
            usd -= abono.monto
            gastos_usd += abono.monto

    return {
        'usd': usd,
        'bs': None if falta_tasa else bs,
        'bs_en_usd': bs_en_usd,
        'gastos_usd': gastos_usd,
        'gastos_bs': None if falta_tasa else gastos_bs,
    }


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


def _lote_acreditado_a_fecha(lote, fecha):
    return lote.estado == 'acreditado' and lote.fecha_abono_real is not None and lote.fecha_abono_real <= fecha


def lotes_pos_por_acreditar(fecha, metodo_ids=None):
    """
    Lotes POS que a `fecha` todavia NO estan acreditados: abiertos, cerrados, y
    los acreditados despues de `fecha` (al mirar una fecha pasada). Es la cuenta
    transitoria "POS por cobrar" — un saldo calculado, no una tabla.
    """
    lotes = VGLotePOS.objects.filter(fecha_operacion__lte=fecha).exclude(estado='anulado').select_related('metodo_pago')
    if metodo_ids is not None:
        lotes = lotes.filter(metodo_pago_id__in=metodo_ids)
    return [lote for lote in lotes.order_by('fecha_operacion', 'numero') if not _lote_acreditado_a_fecha(lote, fecha)]


def _serialize_lote_resumen(lote):
    return {
        'id': lote.id,
        'numero': lote.numero,
        'estado': lote.estado,
        'fecha_operacion': lote.fecha_operacion,
        'monto_bruto_usd': lote.monto_bruto_usd,
        'monto_bruto_bs': lote.monto_bruto_sistema_bs,
    }


def pos_por_cobrar_transitorio(fecha):
    """
    Cuenta transitoria "POS por cobrar" a `fecha` (CALCULADA, sin asientos): por
    banco, cuantos lotes siguen abiertos o cerrados sin acreditar y cuanto suman
    (USD). Es la plata cobrada por punto de venta que todavia no esta disponible.
    """
    items = {}
    total = Decimal('0')
    for lote in lotes_pos_por_acreditar(fecha):
        metodo = lote.metodo_pago
        clave = metodo.cuenta_bancaria or f'__metodo_{metodo.id}'
        item = items.setdefault(clave, {
            'banco': metodo.cuenta_bancaria or metodo.nombre,
            'lotes_abiertos': 0, 'lotes_cerrados': 0, 'monto_usd': Decimal('0'),
        })
        if lote.estado == 'abierto':
            item['lotes_abiertos'] += 1
        else:
            item['lotes_cerrados'] += 1
        item['monto_usd'] += lote.monto_bruto_usd
        total += lote.monto_bruto_usd
    return {
        'fecha': fecha,
        'total_usd': total,
        'por_banco': sorted(items.values(), key=lambda item: item['banco']),
    }


def _resumen_lotes_pos(fecha, metodo_ids):
    """
    Agrega, por metodo POS, lo ya acreditado (lo unico que cuenta como DISPONIBLE,
    ver disponibilidad_por_cuenta) y lo que sigue por acreditar con su desglose.
    """
    resumen = {
        metodo_id: {
            'acreditado_usd': Decimal('0'), 'acreditado_bs': Decimal('0'),
            'por_acreditar_usd': Decimal('0'), 'por_acreditar_bs': Decimal('0'),
            'lotes_por_acreditar': [],
        }
        for metodo_id in metodo_ids
    }
    if not metodo_ids:
        return resumen

    lotes = (
        VGLotePOS.objects.filter(metodo_pago_id__in=metodo_ids, fecha_operacion__lte=fecha)
        .exclude(estado='anulado').order_by('fecha_operacion', 'numero')
    )
    for lote in lotes:
        fila = resumen[lote.metodo_pago_id]
        if _lote_acreditado_a_fecha(lote, fecha):
            fila['acreditado_usd'] += lote.monto_bruto_usd
            fila['acreditado_bs'] += lote.monto_bruto_sistema_bs
        else:
            fila['por_acreditar_usd'] += lote.monto_bruto_usd
            fila['por_acreditar_bs'] += lote.monto_bruto_sistema_bs
            fila['lotes_por_acreditar'].append(_serialize_lote_resumen(lote))
    return resumen


CAMPOS_POS_SUMABLES = ('por_acreditar_usd', 'por_acreditar_bs')


def fila_pos_a_cuenta(fila_pos):
    """Campos POS de una fila de disponibilidad (todo en cero/vacio para un metodo que no es POS)."""
    fila_pos = fila_pos or {}
    datos = {campo: fila_pos.get(campo, Decimal('0')) for campo in CAMPOS_POS_SUMABLES}
    datos['lotes_por_acreditar'] = fila_pos.get('lotes_por_acreditar', [])
    return datos


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

    Las VGTransferenciaCuenta (dinero movido entre cuentas propias, ej. sacar
    de Zelle para depositar en Banesco) se suman a la cuenta destino y se
    restan de la cuenta origen — en USD via monto_usd, y en bolivares (si esa
    cuenta puntual es VES) via monto_origen/monto_destino DIRECTO, sin pasar
    por ninguna tasa: esos montos ya estan en la moneda real de cada cuenta,
    tal como el analista los escribio, asi que convertirlos de nuevo con una
    tasa (BCV o la manual de la transferencia) los desviaria del monto real
    movido. Nunca se cuentan como ingreso ni como gasto (ver
    VGTransferenciaCuenta) — son un movimiento aparte, con su propio total
    acumulado por cuenta.

    Metodos de PUNTO DE VENTA (VGMetodoPago.es_punto_venta): su saldo es
    "lote-driven" — solo cuentan los VGLotePOS acreditados con fecha_abono_real <=
    `fecha` (el monto que el sistema registro, tal cual), y NO cada cobro el dia
    de la venta. Lo que sigue en lotes abiertos/cerrados va aparte en
    `por_acreditar_usd`, con el desglose de lotes. Un cobro de metodo POS sin lote
    (historico previo a marcar el metodo como POS) sigue contando como siempre
    hasta que se agrupe en lotes.

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

    def _monto_bs(monto, tasa):
        return monto * tasa if tasa is not None else None

    saldo_bs_por_metodo = {}
    saldo_bs_incompleto = set()
    movimientos_bs = (
        VGPago.objects.filter(fecha_pago__date__lte=fecha, estado='completado')
        .select_related('metodo_pago', 'nota_entrega', 'factura')
    )
    for pago in movimientos_bs:
        if pago.metodo_pago.moneda != 'VES':
            continue
        if pago.metodo_pago.es_punto_venta and pago.lote_pos_id:
            continue  # lote-driven: se suma abajo, por lote acreditado
        tasa = pago.tasa_cambio_referencia
        if tasa is None and pago.nota_entrega_id:
            tasa = pago.nota_entrega.tasa_cambio_referencia
        if tasa is None and pago.factura_id:
            tasa = pago.factura.tasa_cambio_referencia
        if tasa is None:
            # localtime(...).date(), no .date() a secas — mismo bug que en
            # flujo_bancario_mensual: fecha_pago se guarda en UTC, y en
            # America/Caracas (UTC-4) un pago de la noche cae en la fecha UTC
            # del dia siguiente, lo que buscaria la tasa BCV del dia que no es.
            tasa = tasa_para_fecha(timezone.localtime(pago.fecha_pago).date())
        if tasa is not None:
            saldo_bs_por_metodo[pago.metodo_pago_id] = saldo_bs_por_metodo.get(pago.metodo_pago_id, Decimal('0')) + _monto_bs(pago.monto, tasa)
        else:
            saldo_bs_incompleto.add(pago.metodo_pago_id)

    pos_ids = [metodo.id for metodo in metodos if metodo.es_punto_venta]
    resumen_pos = _resumen_lotes_pos(fecha, pos_ids)
    for metodo_id, fila_pos in resumen_pos.items():
        if fila_pos['acreditado_bs']:
            saldo_bs_por_metodo[metodo_id] = saldo_bs_por_metodo.get(metodo_id, Decimal('0')) + fila_pos['acreditado_bs']

    for ingreso in VGIngresoExtra.objects.filter(fecha_creacion__date__lte=fecha).select_related('metodo_pago'):
        if ingreso.metodo_pago.moneda != 'VES':
            continue
        tasa = ingreso.tasa_cambio_referencia or tasa_para_fecha(timezone.localtime(ingreso.fecha_creacion).date())
        if tasa is not None:
            saldo_bs_por_metodo[ingreso.metodo_pago_id] = saldo_bs_por_metodo.get(ingreso.metodo_pago_id, Decimal('0')) + _monto_bs(ingreso.monto, tasa)
        else:
            saldo_bs_incompleto.add(ingreso.metodo_pago_id)

    for abono in VGAbonoGasto.objects.filter(fecha_pago__date__lte=fecha).select_related('metodo_pago'):
        if abono.metodo_pago.moneda != 'VES':
            continue
        tasa = abono.tasa_cambio_referencia or tasa_para_fecha(timezone.localtime(abono.fecha_pago).date())
        if tasa is not None:
            saldo_bs_por_metodo[abono.metodo_pago_id] = saldo_bs_por_metodo.get(abono.metodo_pago_id, Decimal('0')) - _monto_bs(abono.monto, tasa)
        else:
            saldo_bs_incompleto.add(abono.metodo_pago_id)

    for abono in VGAbonoCompra.objects.filter(fecha_pago__date__lte=fecha).select_related('metodo_pago'):
        if abono.metodo_pago.moneda != 'VES':
            continue
        tasa = abono.tasa_cambio_referencia or tasa_para_fecha(timezone.localtime(abono.fecha_pago).date())
        if tasa is not None:
            saldo_bs_por_metodo[abono.metodo_pago_id] = saldo_bs_por_metodo.get(abono.metodo_pago_id, Decimal('0')) - _monto_bs(abono.monto, tasa)
        else:
            saldo_bs_incompleto.add(abono.metodo_pago_id)

    primer_efectivo = next((metodo for metodo in metodos if metodo.es_efectivo), None)
    primer_efectivo_id = primer_efectivo.id if primer_efectivo else None
    for consignacion in VGConsignacionCaja.objects.filter(fecha__lte=fecha):
        if primer_efectivo is None:
            break
        tasa = tasa_para_fecha(consignacion.fecha)
        if tasa is not None:
            saldo_bs_por_metodo[primer_efectivo.id] = saldo_bs_por_metodo.get(primer_efectivo.id, Decimal('0')) - _monto_bs(consignacion.monto, tasa)
        elif primer_efectivo.moneda == 'VES':
            saldo_bs_incompleto.add(primer_efectivo.id)

    for transferencia in (
        VGTransferenciaCuenta.objects.filter(fecha__lte=fecha)
        .select_related('cuenta_origen', 'cuenta_destino')
    ):
        if transferencia.moneda_origen == 'VES':
            saldo_bs_por_metodo[transferencia.cuenta_origen_id] = (
                saldo_bs_por_metodo.get(transferencia.cuenta_origen_id, Decimal('0')) - transferencia.monto_origen
            )
        if transferencia.moneda_destino == 'VES':
            saldo_bs_por_metodo[transferencia.cuenta_destino_id] = (
                saldo_bs_por_metodo.get(transferencia.cuenta_destino_id, Decimal('0')) + transferencia.monto_destino
            )

    ingresos_por_metodo = _totales_por_metodo(
        VGPago.objects
        .filter(fecha_pago__date__lte=fecha, estado='completado')
        .exclude(metodo_pago__es_punto_venta=True, lote_pos__isnull=False)
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
    # VGTransferenciaCuenta tiene dos FK a VGMetodoPago (origen/destino), no
    # una sola `metodo_pago` — no encaja en _totales_por_metodo, se agrupa
    # aparte por cada lado.
    transferencias_entrantes_por_metodo = {
        fila['cuenta_destino_id']: fila['total']
        for fila in (
            VGTransferenciaCuenta.objects.filter(fecha__lte=fecha)
            .values('cuenta_destino_id').annotate(total=Sum('monto_usd'))
        )
    }
    transferencias_salientes_por_metodo = {
        fila['cuenta_origen_id']: fila['total']
        for fila in (
            VGTransferenciaCuenta.objects.filter(fecha__lte=fecha)
            .values('cuenta_origen_id').annotate(total=Sum('monto_usd'))
        )
    }

    resultado = []
    for metodo in metodos:
        ingresos = ingresos_por_metodo.get(metodo.id) or Decimal('0')
        ingresos_extra = ingresos_extra_por_metodo.get(metodo.id) or Decimal('0')
        gastos = gastos_por_metodo.get(metodo.id) or Decimal('0')
        compras = compras_por_metodo.get(metodo.id) or Decimal('0')
        consignado = consignado_acumulado if metodo.id == primer_efectivo_id else Decimal('0')
        transferencias_entrantes = transferencias_entrantes_por_metodo.get(metodo.id) or Decimal('0')
        transferencias_salientes = transferencias_salientes_por_metodo.get(metodo.id) or Decimal('0')
        fila_pos = resumen_pos.get(metodo.id)
        if fila_pos is not None:
            # Metodo POS: los cobros con lote ya se excluyeron arriba; lo disponible
            # es el neto de los lotes que el banco ya acredito.
            ingresos += fila_pos['acreditado_usd']
        resultado.append({
            'id': metodo.id,
            'nombre': metodo.nombre,
            'moneda': metodo.moneda,
            'es_efectivo': metodo.es_efectivo,
            'cuenta_bancaria': metodo.cuenta_bancaria,
            'activo': metodo.activo,
            'ingresos_acumulados': ingresos,
            'ingresos_extra_acumulados': ingresos_extra,
            'transferencias_entrantes_acumuladas': transferencias_entrantes,
            'gastos_acumulados': gastos,
            'compras_acumuladas': compras,
            'transferencias_salientes_acumuladas': transferencias_salientes,
            'consignado_acumulado': consignado,
            'saldo_disponible': (
                ingresos + ingresos_extra + transferencias_entrantes
                - gastos - compras - transferencias_salientes - consignado
            ),
            'saldo_disponible_bs': (
                None if metodo.id in saldo_bs_incompleto
                else saldo_bs_por_metodo.get(metodo.id, Decimal('0'))
            ) if metodo.moneda == 'VES' else None,
            'es_punto_venta': metodo.es_punto_venta,
            **(fila_pos_a_cuenta(fila_pos) if fila_pos is not None else fila_pos_a_cuenta(None)),
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
                'transferencias_entrantes_acumuladas': Decimal('0'),
                'gastos_acumulados': Decimal('0'),
                'compras_acumuladas': Decimal('0'),
                'transferencias_salientes_acumuladas': Decimal('0'),
                'consignado_acumulado': Decimal('0'),
                'saldo_disponible': Decimal('0'),
                'saldo_disponible_bs': Decimal('0') if cuenta['moneda'] == 'VES' else None,
                **{campo: Decimal('0') for campo in CAMPOS_POS_SUMABLES},
                'lotes_por_acreditar': [],
                'tiene_punto_venta': False,
            }
            orden_claves.append(clave)
        banco = bancos_por_clave[clave]
        banco['metodos'].append(cuenta)
        banco['ingresos_acumulados'] += cuenta['ingresos_acumulados']
        banco['ingresos_extra_acumulados'] += cuenta['ingresos_extra_acumulados']
        banco['transferencias_entrantes_acumuladas'] += cuenta['transferencias_entrantes_acumuladas']
        banco['gastos_acumulados'] += cuenta['gastos_acumulados']
        banco['compras_acumuladas'] += cuenta['compras_acumuladas']
        banco['transferencias_salientes_acumuladas'] += cuenta['transferencias_salientes_acumuladas']
        banco['consignado_acumulado'] += cuenta['consignado_acumulado']
        banco['saldo_disponible'] += cuenta['saldo_disponible']
        for campo in CAMPOS_POS_SUMABLES:
            banco[campo] += cuenta[campo]
        banco['lotes_por_acreditar'].extend(cuenta['lotes_por_acreditar'])
        banco['tiene_punto_venta'] = banco['tiene_punto_venta'] or cuenta['es_punto_venta']
        if banco['saldo_disponible_bs'] is not None and cuenta['saldo_disponible_bs'] is not None:
            banco['saldo_disponible_bs'] += cuenta['saldo_disponible_bs']
        elif banco['saldo_disponible_bs'] is not None:
            banco['saldo_disponible_bs'] = None
        # Un banco agrupado con monedas mixtas no deberia pasar en la
        # practica (una cuenta bancaria real tiene una sola moneda) — se dej
        # a la del primer metodo, y se marca la inconsistencia si aparece.
        banco.setdefault('moneda', cuenta['moneda'])
        if banco['moneda'] != cuenta['moneda']:
            banco['moneda_mixta'] = True

    bancos = [bancos_por_clave[clave] for clave in orden_claves]
    return resultado, bancos


def _bancos_seleccionables():
    """
    Lista de "bancos" para el selector del flujo bancario diario (ver
    flujo_bancario_mensual): agrupa VGMetodoPago activos por cuenta_bancaria,
    mismo criterio que disponibilidad_por_cuenta — un metodo sin
    cuenta_bancaria forma su propio grupo bajo su propio nombre. Cada entrada
    es {clave, nombre, metodo_ids}; `clave` es lo que viaja en la URL del
    reporte (?banco=clave).
    """
    bancos_por_clave = {}
    orden = []
    for metodo in VGMetodoPago.objects.filter(activo=True).order_by('nombre'):
        clave = metodo.cuenta_bancaria or f"__metodo_{metodo.id}"
        if clave not in bancos_por_clave:
            bancos_por_clave[clave] = {
                'clave': clave,
                'nombre': metodo.cuenta_bancaria or metodo.nombre,
                'metodo_ids': [],
            }
            orden.append(clave)
        bancos_por_clave[clave]['metodo_ids'].append(metodo.id)
    return [bancos_por_clave[clave] for clave in orden]


def _metodo_ids_de_banco(banco_clave):
    """(metodo_ids, nombre_banco) del banco con esa clave, o ([], None) si no existe/no tiene metodos activos."""
    for banco in _bancos_seleccionables():
        if banco['clave'] == banco_clave:
            return banco['metodo_ids'], banco['nombre']
    return [], None


def _monto_bs_historico(monto, moneda, tasa):
    """
    Equivalente en bolivares de `monto` (en USD) usando LA TASA YA RESUELTA
    que le pasen (normalmente la congelada de ese registro puntual, nunca la
    vigente hoy) — None si el metodo no es en bolivares, o si no hay tasa
    resoluble. Compartida por flujo_bancario_mensual y
    detalle_flujo_bancario_dia para no resolver esta conversion dos veces
    con criterios distintos.
    """
    if moneda != 'VES' or tasa is None:
        return None
    return (monto * tasa).quantize(Decimal('0.01'))


def flujo_bancario_mensual(anio, mes, banco_clave):
    """
    Entradas y salidas dia por dia de un mes calendario completo, para los
    metodos de pago agrupados bajo `banco_clave` (ver _bancos_seleccionables)
    — el resumen que abre el reporte de "Flujo bancario diario" antes de
    entrar al detalle de un dia puntual (ver detalle_flujo_bancario_dia).

    - `entrada` de cada dia = VGPago completados + VGIngresoExtra (propinas/
      pagos extra) de ese metodo/banco ese dia — la misma nocion de "dinero
      que entro" que usa disponibilidad_por_cuenta. Se agrupan por fecha_pago/
      fecha_creacion (automaticas): una venta se cobra en el momento, no hay
      "carga tardia" que desalinee esa fecha de la real.
    - `salida` de cada dia = VGAbonoGasto + VGAbonoCompra (lo pagado a gastos
      operativos y a proveedores) de ese metodo/banco ese dia:
        - VGAbonoGasto se agrupa por la fecha REAL del gasto (VGGasto.fecha_gasto),
          nunca por fecha_pago (cuando se cargo el abono al sistema,
          automatica): es comun cargar una semana de gastos de una sola vez
          (un solo abono por gasto, por el monto completo), y ahi fecha_pago
          de todos seria "hoy" aunque cada uno haya pasado en un dia distinto.
        - VGAbonoCompra, en cambio, se agrupa por SU PROPIA fecha_pago (cada
          abono, en su propia fecha) — a diferencia de un gasto, una compra
          se puede pagar en varios abonos parciales en fechas bien distintas
          (ver compras_views.compra_abono_view); agruparlas por la fecha de
          la factura (un solo dia) mostraria todos esos abonos como si
          hubieran salido del banco ese mismo dia, cuando la plata de verdad
          salio en cada fecha de abono. fecha_pago aca SI es la fecha real
          de cada salida, porque cada abono se registra el mismo dia en que
          se paga (no se cargan "atrasados" como los gastos).
    Todos los dias del mes aparecen en `dias`, tengan o no movimiento (para
    que el calendario del reporte quede completo), con entrada/salida en 0
    cuando no hubo nada.

    Cada dia trae tambien `entrada_bs`/`salida_bs`: la suma en bolivares de
    SOLO los movimientos de ese dia que son en bolivares, cada uno con SU
    PROPIA tasa congelada (mismo criterio y misma cadena de prioridad que
    detalle_flujo_bancario_dia — nunca la tasa vigente hoy). Por eso esta
    funcion itera objeto por objeto en vez de agregar por SQL (Sum): la tasa
    de cada fila puede salir del pago mismo, de su nota/factura, o de la
    vigente ese dia, y ese fallback no se puede expresar como un solo
    annotate. None si ese dia no tuvo ningun movimiento en bolivares con
    tasa resoluble.
    """
    metodo_ids, nombre_banco = _metodo_ids_de_banco(banco_clave)
    if not metodo_ids:
        return {'banco': None, 'dias': [], 'total_entrada': Decimal('0'), 'total_salida': Decimal('0')}

    desde = date(anio, mes, 1)
    hasta = date(anio, mes, calendar.monthrange(anio, mes)[1])

    entradas_usd = {}
    entradas_bs = {}

    for pago in (
        VGPago.objects
        .filter(fecha_pago__date__gte=desde, fecha_pago__date__lte=hasta, estado='completado', metodo_pago_id__in=metodo_ids)
        .exclude(metodo_pago__es_punto_venta=True, lote_pos__isnull=False)
        .select_related('metodo_pago', 'nota_entrega', 'factura')
    ):
        # timezone.localtime(...).date(), NUNCA .date() a secas — fecha_pago
        # se guarda en UTC internamente (USE_TZ=True); en America/Caracas
        # (UTC-4) un pago de la noche cae en la fecha UTC del dia SIGUIENTE,
        # lo que desalineaba esta tabla (agrupada aca en Python) contra
        # detalle_flujo_bancario_dia, que filtra por fecha_pago__date=fecha
        # y ese lookup del ORM SI convierte a hora local solo.
        dia = timezone.localtime(pago.fecha_pago).date()
        entradas_usd[dia] = entradas_usd.get(dia, Decimal('0')) + pago.monto
        tasa_pago = (
            pago.tasa_cambio_referencia
            or (pago.nota_entrega.tasa_cambio_referencia if pago.nota_entrega_id else None)
            or (pago.factura.tasa_cambio_referencia if pago.factura_id else None)
            or tasa_para_fecha(dia)
        )
        monto_bs = _monto_bs_historico(pago.monto, pago.metodo_pago.moneda, tasa_pago)
        if monto_bs is not None:
            entradas_bs[dia] = entradas_bs.get(dia, Decimal('0')) + monto_bs

    # Un metodo POS no entra al banco el dia de la venta sino cuando se acredita
    # el lote: se muestra el dia de la ACREDITACION, no el del cobro.
    for lote in (
        VGLotePOS.objects
        .filter(estado='acreditado', fecha_abono_real__gte=desde, fecha_abono_real__lte=hasta, metodo_pago_id__in=metodo_ids, metodo_pago__es_punto_venta=True)
    ):
        dia = lote.fecha_abono_real
        entradas_usd[dia] = entradas_usd.get(dia, Decimal('0')) + lote.monto_bruto_usd
        entradas_bs[dia] = entradas_bs.get(dia, Decimal('0')) + lote.monto_bruto_sistema_bs

    for ingreso in (
        VGIngresoExtra.objects
        .filter(fecha_creacion__date__gte=desde, fecha_creacion__date__lte=hasta, metodo_pago_id__in=metodo_ids)
        .select_related('metodo_pago')
    ):
        dia = timezone.localtime(ingreso.fecha_creacion).date()
        entradas_usd[dia] = entradas_usd.get(dia, Decimal('0')) + ingreso.monto
        tasa_ingreso = ingreso.tasa_cambio_referencia or tasa_para_fecha(dia)
        monto_bs = _monto_bs_historico(ingreso.monto, ingreso.metodo_pago.moneda, tasa_ingreso)
        if monto_bs is not None:
            entradas_bs[dia] = entradas_bs.get(dia, Decimal('0')) + monto_bs

    salidas_usd = {}
    salidas_bs = {}

    # Los gastos se agrupan por la fecha REAL del gasto (VGGasto.fecha_gasto)
    # — la que el analista escribe a mano al registrar, y puede ser bien
    # distinta de cuando de verdad se cargo el abono al sistema (fecha_pago,
    # automatica): es comun cargar gastos de una semana atras de una sola
    # vez. Usar fecha_pago aca hacia que esas salidas aparecieran en el dia
    # en que se tipearon, no en el dia en que de verdad salio la plata.
    for abono in (
        VGAbonoGasto.objects
        .filter(gasto__fecha_gasto__gte=desde, gasto__fecha_gasto__lte=hasta, metodo_pago_id__in=metodo_ids)
        .select_related('metodo_pago', 'gasto')
    ):
        dia = abono.gasto.fecha_gasto
        salidas_usd[dia] = salidas_usd.get(dia, Decimal('0')) + abono.monto
        tasa_abono = abono.tasa_cambio_referencia or tasa_para_fecha(dia)
        monto_bs = _monto_bs_historico(abono.monto, abono.metodo_pago.moneda, tasa_abono)
        if monto_bs is not None:
            salidas_bs[dia] = salidas_bs.get(dia, Decimal('0')) + monto_bs

    # Las compras, a diferencia de los gastos, se agrupan por la fecha REAL
    # de CADA ABONO (fecha_pago) — una compra se puede pagar en varios
    # abonos parciales en fechas distintas, y cada uno sale del banco el dia
    # en que de verdad se registra (no se cargan "atrasados" como un gasto),
    # asi que fecha_pago ya es la fecha real de esa salida puntual. Agrupar
    # por fecha_factura (un solo dia) juntaria todos los abonos de una misma
    # compra en un solo dia, aunque hayan salido del banco en dias distintos.
    for abono in (
        VGAbonoCompra.objects
        .filter(fecha_pago__date__gte=desde, fecha_pago__date__lte=hasta, metodo_pago_id__in=metodo_ids)
        .select_related('metodo_pago', 'compra')
    ):
        dia = timezone.localtime(abono.fecha_pago).date()
        salidas_usd[dia] = salidas_usd.get(dia, Decimal('0')) + abono.monto
        tasa_abono = abono.tasa_cambio_referencia or tasa_para_fecha(dia)
        monto_bs = _monto_bs_historico(abono.monto, abono.metodo_pago.moneda, tasa_abono)
        if monto_bs is not None:
            salidas_bs[dia] = salidas_bs.get(dia, Decimal('0')) + monto_bs

    dias = []
    total_entrada = Decimal('0')
    total_salida = Decimal('0')
    total_entrada_bs = Decimal('0')
    total_salida_bs = Decimal('0')
    for fecha in _rango_fechas(desde, hasta):
        entrada = entradas_usd.get(fecha, Decimal('0'))
        salida = salidas_usd.get(fecha, Decimal('0'))
        entrada_bs = entradas_bs.get(fecha)
        salida_bs = salidas_bs.get(fecha)
        total_entrada += entrada
        total_salida += salida
        if entrada_bs is not None:
            total_entrada_bs += entrada_bs
        if salida_bs is not None:
            total_salida_bs += salida_bs
        dias.append({
            'fecha': fecha, 'entrada': entrada, 'salida': salida,
            'entrada_bs': entrada_bs, 'salida_bs': salida_bs,
        })

    return {
        'banco': nombre_banco, 'dias': dias,
        'total_entrada': total_entrada, 'total_salida': total_salida,
        'total_entrada_bs': total_entrada_bs, 'total_salida_bs': total_salida_bs,
    }


def detalle_flujo_bancario_dia(fecha, banco_clave, tipo):
    """
    Movimientos individuales de `tipo` ('entrada'|'salida') en `fecha`, para
    los metodos agrupados bajo `banco_clave` — el detalle detras de una
    celda de flujo_bancario_mensual, para cuando el analista hace click en
    el total de un dia puntual y quiere ver de que se compuso.

    'entrada': cada VGPago completado trae su origen (nota de entrega,
    factura, o el flujo historico de "mesero cobra directo" ligado
    directo a un VGPedido), mas cada VGIngresoExtra (propina/pago extra).
    'salida': cada VGAbonoGasto (con el nombre del gasto) y cada
    VGAbonoCompra (con el proveedor de la compra) — para un VGAbonoGasto,
    `fecha` es la fecha real del gasto (VGGasto.fecha_gasto), nunca cuando
    se cargo el abono; para un VGAbonoCompra, `fecha` SI es fecha_pago (cada
    abono, en su propia fecha) — ver flujo_bancario_mensual para el porque
    de esta diferencia entre los dos.

    Cada fila trae tambien `monto_bs`: el equivalente en bolivares que de
    verdad se cobro/pago, calculado con LA TASA CONGELADA de ese registro
    puntual (nunca la tasa vigente hoy) — mismo criterio y misma cadena de
    prioridad que totales_pagos_por_metodo/detalle_ventas_rango (tasa propia
    del registro, si no la del documento asociado, si no la vigente en
    `fecha`). None si el metodo no es en bolivares, o si ningun de esas tasas
    se pudo resolver.
    """
    metodo_ids, _nombre_banco = _metodo_ids_de_banco(banco_clave)
    if not metodo_ids:
        return []

    _monto_bs = _monto_bs_historico
    movimientos = []
    if tipo == 'entrada':
        pagos = (
            VGPago.objects
            .filter(fecha_pago__date=fecha, estado='completado', metodo_pago_id__in=metodo_ids)
            .exclude(metodo_pago__es_punto_venta=True, lote_pos__isnull=False)
            .select_related('metodo_pago', 'nota_entrega', 'factura')
        )
        for pago in pagos:
            if pago.nota_entrega_id:
                origen = f"Nota de entrega {pago.nota_entrega.codigo}"
                if pago.numero_cobro:
                    origen = f"Cobro COB-{pago.numero_cobro:06d} — {origen}"
                # Una nota cobrada dias despues de emitirse entra al banco el dia
                # del ABONO (no el de la emision) — se aclara cuando difieren para
                # que ese cobro de una venta anterior se reconozca de un vistazo.
                fecha_emision = timezone.localtime(pago.nota_entrega.fecha_emision).date()
                if fecha_emision != fecha:
                    origen += f" (emitida el {fecha_emision.strftime('%d/%m')})"
            elif pago.factura_id:
                origen = f"Factura {pago.factura.numero_factura:06d}"
            elif pago.pedido_id:
                origen = f"Abono directo — Pedido #{pago.pedido_id}"
            else:
                origen = "Pago"
            tasa_pago = (
                pago.tasa_cambio_referencia
                or (pago.nota_entrega.tasa_cambio_referencia if pago.nota_entrega_id else None)
                or (pago.factura.tasa_cambio_referencia if pago.factura_id else None)
                or tasa_para_fecha(fecha)
            )
            movimientos.append({
                'id': pago.id,
                'tipo_registro': 'pago',
                'fecha_hora': pago.fecha_pago,
                'nombre': origen,
                'metodo_pago_nombre': pago.metodo_pago.nombre,
                'monto': pago.monto,
                'monto_bs': _monto_bs(pago.monto, pago.metodo_pago.moneda, tasa_pago),
                'referencia': pago.referencia,
            })

        for lote in (
            VGLotePOS.objects
            .filter(estado='acreditado', fecha_abono_real=fecha, metodo_pago_id__in=metodo_ids, metodo_pago__es_punto_venta=True)
            .select_related('metodo_pago')
        ):
            fecha_hora_abono = timezone.make_aware(datetime.combine(fecha, time.min), timezone.get_current_timezone())
            movimientos.append({
                'id': lote.id,
                'tipo_registro': 'lote_pos',
                'fecha_hora': fecha_hora_abono,
                'nombre': f"Lote POS #{lote.numero} acreditado",
                'metodo_pago_nombre': lote.metodo_pago.nombre,
                'monto': lote.monto_bruto_usd,
                'monto_bs': lote.monto_bruto_sistema_bs,
                'referencia': f"LOTE-{lote.numero:06d}",
            })

        for ingreso in (
            VGIngresoExtra.objects
            .filter(fecha_creacion__date=fecha, metodo_pago_id__in=metodo_ids)
            .select_related('metodo_pago')
        ):
            nombre = ingreso.get_tipo_display()
            if ingreso.descripcion:
                nombre = f"{nombre} — {ingreso.descripcion}"
            tasa_ingreso = ingreso.tasa_cambio_referencia or tasa_para_fecha(fecha)
            movimientos.append({
                'id': ingreso.id,
                'tipo_registro': 'ingreso_extra',
                'fecha_hora': ingreso.fecha_creacion,
                'nombre': nombre,
                'metodo_pago_nombre': ingreso.metodo_pago.nombre,
                'monto': ingreso.monto,
                'monto_bs': _monto_bs(ingreso.monto, ingreso.metodo_pago.moneda, tasa_ingreso),
                'referencia': '',
            })
    else:
        # `fecha` aca es la fecha REAL del gasto/factura, no fecha_pago (ver
        # el docstring de flujo_bancario_mensual para el motivo). fecha_hora
        # se arma a medianoche de esa fecha solo para poder ordenar/serializar
        # junto a los demas movimientos — no hay hora real que mostrar, un
        # gasto/factura solo tiene fecha.
        fecha_hora_fija = timezone.make_aware(datetime.combine(fecha, time.min), timezone.get_current_timezone())

        for abono in (
            VGAbonoGasto.objects
            .filter(gasto__fecha_gasto=fecha, metodo_pago_id__in=metodo_ids)
            .select_related('metodo_pago', 'gasto')
        ):
            tasa_abono = abono.tasa_cambio_referencia or tasa_para_fecha(fecha)
            movimientos.append({
                'id': abono.id,
                'tipo_registro': 'abono_gasto',
                'documento_id': abono.gasto_id,
                'documento_codigo': f"Gasto #{abono.gasto_id}",
                'fecha_hora': fecha_hora_fija,
                'nombre': f"Gasto — {abono.gasto.descripcion}",
                'metodo_pago_nombre': abono.metodo_pago.nombre,
                'monto': abono.monto,
                'monto_bs': _monto_bs(abono.monto, abono.metodo_pago.moneda, tasa_abono),
                'referencia': abono.referencia,
            })
        # A diferencia de VGAbonoGasto, aca `fecha` SI es fecha_pago (el
        # abono de una compra ya tiene su propia hora real de cuando se
        # registro — no hace falta fecha_hora_fija).
        for abono in (
            VGAbonoCompra.objects
            .filter(fecha_pago__date=fecha, metodo_pago_id__in=metodo_ids)
            .select_related('metodo_pago', 'compra')
        ):
            tasa_abono = abono.tasa_cambio_referencia or tasa_para_fecha(fecha)
            movimientos.append({
                'id': abono.id,
                'tipo_registro': 'abono_compra',
                'documento_id': abono.compra_id,
                'documento_codigo': f"Lote #{abono.compra_id}",
                'fecha_hora': abono.fecha_pago,
                'nombre': f"Compra — {abono.compra.proveedor_nombre}",
                'metodo_pago_nombre': abono.metodo_pago.nombre,
                'monto': abono.monto,
                'monto_bs': _monto_bs(abono.monto, abono.metodo_pago.moneda, tasa_abono),
                'referencia': abono.referencia,
            })

    movimientos.sort(key=lambda item: item['fecha_hora'])
    return movimientos

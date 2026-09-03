"""
Vistas del modulo de Contabilidad: metodos de pago configurables y el
cuadre de caja diario (totales por metodo, consignaciones y cierre).
Separado de api_views.py (que cubre todo lo propio del restaurante:
menu, inventario, pedidos, cocina, checkout...) para que ninguno de los
dos archivos seguiera creciendo junto por cosas sin relacion.
"""
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .api_views import _calcular_margen_periodo
from .auth_helpers import _auth_response, _is_admin_user, _is_cajera_user
from .models import VGCierreCaja, VGConsignacionCaja, VGDetallePedido, VGGasto, VGIngresoExtra, VGMetodoPago
from .tasa_cambio import tasa_cambio_para_registro
from .reportes import (
    desglose_caja_por_moneda,
    disponibilidad_por_cuenta,
    efectivo_esperado_dia,
    gastos_efectivo_dia,
    resumen_cuadre_caja_rango,
    tasa_para_fecha,
    total_consignado,
    totales_pagos_por_metodo,
)


def _serialize_metodo_pago(metodo):
    return {
        'id': metodo.id,
        'nombre': metodo.nombre,
        'moneda': metodo.moneda,
        'es_efectivo': metodo.es_efectivo,
        'activo': metodo.activo,
    }


def metodos_pago_activos_view(request):
    """Metodos de pago activos, para el selector de cobro. Cualquier usuario autenticado."""
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not request.user.is_authenticated:
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion.'}, status=401)

    metodos = VGMetodoPago.objects.filter(activo=True).order_by('nombre')
    return _auth_response({'ok': True, 'metodos_pago': [_serialize_metodo_pago(metodo) for metodo in metodos]})


def _serialize_ingreso_extra(ingreso):
    return {
        'id': ingreso.id,
        'tipo': ingreso.tipo,
        'tipo_label': ingreso.get_tipo_display(),
        'monto': str(ingreso.monto),
        'moneda': ingreso.metodo_pago.moneda,
        'tasa_cambio_referencia': str(ingreso.tasa_cambio_referencia) if ingreso.tasa_cambio_referencia is not None else None,
        'descripcion': ingreso.descripcion,
        'metodo_pago_id': ingreso.metodo_pago_id,
        'metodo_pago_nombre': ingreso.metodo_pago.nombre,
        'registrado_por': ingreso.creado_por.get_full_name() or ingreso.creado_por.username if ingreso.creado_por else '',
        'fecha_creacion': ingreso.fecha_creacion.isoformat(),
    }


@csrf_exempt
def ingresos_extra_view(request):
    """
    Propinas y "pagos extra" (el redondeo que el cliente no pidio de vuelta) que
    la cajera cobra junto con la nota de entrega pero que no son parte de la
    venta — ver VGIngresoExtra. Reservado a cajera/admin/contador, igual que el
    resto de Cobro.
    """
    if request.method not in ['GET', 'POST']:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not (_is_cajera_user(request.user) or _is_admin_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para registrar esto.'}, status=401)

    if request.method == 'GET':
        ingresos = (
            VGIngresoExtra.objects
            .select_related('metodo_pago', 'creado_por')
            .order_by('-fecha_creacion')[:100]
        )
        return _auth_response({'ok': True, 'ingresos': [_serialize_ingreso_extra(ingreso) for ingreso in ingresos]})

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    tipo = str(data.get('tipo', '')).strip().lower()
    if tipo not in {clave for clave, _ in VGIngresoExtra.TIPOS}:
        return _auth_response({'ok': False, 'message': 'Tipo invalido.'}, status=400)

    try:
        monto_input = Decimal(str(data.get('monto', '')))
    except InvalidOperation:
        return _auth_response({'ok': False, 'message': 'El monto no es valido.'}, status=400)
    if monto_input <= 0:
        return _auth_response({'ok': False, 'message': 'El monto debe ser mayor a cero.'}, status=400)

    try:
        metodo_pago = VGMetodoPago.objects.get(pk=int(data.get('metodo_pago_id')), activo=True)
    except (TypeError, ValueError, VGMetodoPago.DoesNotExist):
        return _auth_response({'ok': False, 'message': 'Selecciona una cuenta valida.'}, status=400)

    # Igual que nota_entrega_abono_view/factura_abono_view: monto_input llega en
    # la moneda de la cuenta elegida (lo que la cajera cuenta y escribe), pero
    # VGIngresoExtra.monto se guarda siempre en USD. Si la cuenta es en
    # bolivares, se congela la tasa BCV de este momento — de lo contrario un
    # monto en bolivares se guardaria tal cual como si fueran dolares, inflando
    # el registro (1.000 Bs pasarian a contarse como $1.000).
    if metodo_pago.moneda == 'VES':
        tasa_conversion = tasa_cambio_para_registro()
        if not tasa_conversion or tasa_conversion <= 0:
            return _auth_response({
                'ok': False,
                'message': 'No hay tasa de cambio disponible para convertir el monto a dolares.',
            }, status=400)
        monto = (monto_input / tasa_conversion).quantize(Decimal('0.01'))
    else:
        tasa_conversion = None
        monto = monto_input.quantize(Decimal('0.01'))

    ingreso = VGIngresoExtra.objects.create(
        tipo=tipo,
        monto=monto,
        tasa_cambio_referencia=tasa_conversion,
        descripcion=str(data.get('descripcion', '') or '').strip(),
        metodo_pago=metodo_pago,
        creado_por=request.user,
    )
    return _auth_response({
        'ok': True,
        'message': f'{ingreso.get_tipo_display()} registrada correctamente.',
        'ingreso': _serialize_ingreso_extra(ingreso),
    }, status=201)


@csrf_exempt
def admin_metodos_pago_view(request):
    """Gestion de los tipos de metodo de pago disponibles al cobrar. Solo administrador."""
    if request.method not in ['GET', 'POST']:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    if request.method == 'GET':
        metodos = VGMetodoPago.objects.order_by('nombre')
        return _auth_response({'ok': True, 'metodos_pago': [_serialize_metodo_pago(metodo) for metodo in metodos]})

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    action = str(data.get('action', '')).strip().lower()

    if action == 'create':
        nombre = str(data.get('nombre', '')).strip()
        if not nombre:
            return _auth_response({'ok': False, 'message': 'El nombre es obligatorio.'}, status=400)
        if VGMetodoPago.objects.filter(nombre__iexact=nombre).exists():
            return _auth_response({'ok': False, 'message': 'Ya existe un metodo de pago con ese nombre.'}, status=400)

        moneda = str(data.get('moneda', 'USD')).strip().upper()
        if moneda not in {clave for clave, _ in VGMetodoPago.MONEDAS}:
            return _auth_response({'ok': False, 'message': 'La moneda debe ser USD o VES.'}, status=400)

        metodo = VGMetodoPago.objects.create(
            nombre=nombre,
            moneda=moneda,
            es_efectivo=bool(data.get('es_efectivo')),
            creado_por=request.user,
        )
        return _auth_response({
            'ok': True,
            'message': 'Metodo de pago creado correctamente.',
            'metodo_pago': _serialize_metodo_pago(metodo),
        }, status=201)

    if action == 'toggle_activo':
        try:
            metodo = VGMetodoPago.objects.get(pk=int(data.get('id')))
        except (TypeError, ValueError, VGMetodoPago.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'El metodo de pago no existe.'}, status=400)

        metodo.activo = not metodo.activo
        metodo.actualizado_por = request.user
        metodo.save(update_fields=['activo', 'actualizado_por', 'fecha_actualizacion'])
        return _auth_response({
            'ok': True,
            'message': 'Metodo de pago actualizado correctamente.',
            'metodo_pago': _serialize_metodo_pago(metodo),
        })

    return _auth_response({'ok': False, 'message': 'Accion invalida.'}, status=400)


def _parse_fecha_reporte(raw_value):
    if not raw_value:
        return timezone.localdate()
    try:
        return date.fromisoformat(str(raw_value))
    except ValueError:
        return None


def _serialize_consignacion(consignacion):
    return {
        'id': consignacion.id,
        'monto': str(consignacion.monto),
        'notas': consignacion.notas,
        'creado_por': consignacion.creado_por.get_full_name() or consignacion.creado_por.username if consignacion.creado_por else '',
        'fecha_creacion': consignacion.fecha_creacion.isoformat(),
    }


def _serialize_desglose_caja(desglose):
    def _serialize_balde(balde):
        data = {'total_usd': str(balde['total_usd'])}
        if 'total_bs' in balde:
            data['total_bs'] = str(balde['total_bs']) if balde['total_bs'] is not None else None
        return data

    return {clave: _serialize_balde(balde) for clave, balde in desglose.items()}


def _serialize_cierre_caja(cierre):
    if cierre is None:
        return None
    return {
        'efectivo_esperado': str(cierre.efectivo_esperado),
        'total_consignado': str(cierre.total_consignado),
        'efectivo_contado_final': str(cierre.efectivo_contado_final),
        'diferencia': str(cierre.diferencia),
        'notas': cierre.notas,
        'cerrado_por': cierre.creado_por.get_full_name() or cierre.creado_por.username if cierre.creado_por else '',
        'fecha_creacion': cierre.fecha_creacion.isoformat(),
    }


@csrf_exempt
def reporte_cuadre_caja_view(request):
    """
    Cuadre de caja diario: totales cobrados por metodo de pago (VGPago, mas
    propinas/pagos extra de VGIngresoExtra sumadas ahi mismo — ver
    totales_pagos_por_metodo), consignaciones parciales del turno y el cierre
    final del dia (unico por fecha, lo hace la ultima persona del turno).
    """
    if request.method not in ['GET', 'POST']:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not (_is_admin_user(request.user) or _is_cajera_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para ver este reporte.'}, status=401)

    if request.method == 'GET':
        fecha = _parse_fecha_reporte(request.GET.get('fecha'))
        if fecha is None:
            return _auth_response({'ok': False, 'message': 'Fecha invalida.'}, status=400)

        totales = totales_pagos_por_metodo(fecha)
        consignaciones = VGConsignacionCaja.objects.filter(fecha=fecha).select_related('creado_por')
        ingresos_extra_dia = (
            VGIngresoExtra.objects
            .filter(fecha_creacion__date=fecha)
            .select_related('metodo_pago', 'creado_por')
            .order_by('-fecha_creacion')
        )
        cierre = VGCierreCaja.objects.filter(fecha=fecha).select_related('creado_por').first()
        tasa = tasa_para_fecha(fecha)

        return _auth_response({
            'ok': True,
            'fecha': fecha.isoformat(),
            'tasa_bcv': str(tasa) if tasa is not None else None,
            'totales_por_metodo': [
                {
                    **item,
                    'ventas': str(item['ventas']),
                    'ingresos_extra': str(item['ingresos_extra']),
                    'total': str(item['total']),
                    'total_bs': str(item['total_bs']) if item['total_bs'] is not None else None,
                }
                for item in totales
            ],
            'total_general': str(sum(item['total'] for item in totales)),
            'desglose_caja': _serialize_desglose_caja(desglose_caja_por_moneda(fecha)),
            'consignaciones': [_serialize_consignacion(item) for item in consignaciones],
            'total_consignado': str(total_consignado(fecha)),
            'ingresos_extra_dia': [_serialize_ingreso_extra(item) for item in ingresos_extra_dia],
            'total_ingresos_extra_dia': str(sum((item.monto for item in ingresos_extra_dia), Decimal('0'))),
            'gastos_efectivo_dia': str(gastos_efectivo_dia(fecha)),
            'efectivo_esperado_preview': str(efectivo_esperado_dia(fecha)),
            'cierre': _serialize_cierre_caja(cierre),
        })

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    action = str(data.get('action', '')).strip().lower()
    fecha = _parse_fecha_reporte(data.get('fecha'))
    if fecha is None:
        return _auth_response({'ok': False, 'message': 'Fecha invalida.'}, status=400)

    if action == 'agregar_consignacion':
        try:
            monto = Decimal(str(data.get('monto', '')))
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'El monto no es valido.'}, status=400)
        if monto <= 0:
            return _auth_response({'ok': False, 'message': 'El monto debe ser mayor a cero.'}, status=400)

        if VGCierreCaja.objects.filter(fecha=fecha).exists():
            return _auth_response({'ok': False, 'message': 'La caja de ese dia ya esta cerrada.'}, status=400)

        consignacion = VGConsignacionCaja.objects.create(
            fecha=fecha,
            monto=monto,
            notas=str(data.get('notas', '') or '').strip(),
            creado_por=request.user,
        )
        return _auth_response({
            'ok': True,
            'message': 'Consignacion registrada correctamente.',
            'consignacion': _serialize_consignacion(consignacion),
        }, status=201)

    if action == 'cerrar_caja':
        if VGCierreCaja.objects.filter(fecha=fecha).exists():
            return _auth_response({'ok': False, 'message': 'La caja de ese dia ya esta cerrada.'}, status=400)

        try:
            efectivo_contado_final = Decimal(str(data.get('efectivo_contado_final', '')))
        except InvalidOperation:
            return _auth_response({'ok': False, 'message': 'El monto contado no es valido.'}, status=400)
        if efectivo_contado_final < 0:
            return _auth_response({'ok': False, 'message': 'El monto contado no puede ser negativo.'}, status=400)

        efectivo_esperado = efectivo_esperado_dia(fecha)
        consignado = total_consignado(fecha)
        diferencia = (consignado + efectivo_contado_final) - efectivo_esperado

        cierre = VGCierreCaja.objects.create(
            fecha=fecha,
            efectivo_esperado=efectivo_esperado,
            total_consignado=consignado,
            efectivo_contado_final=efectivo_contado_final,
            diferencia=diferencia,
            notas=str(data.get('notas', '') or '').strip(),
            creado_por=request.user,
        )
        return _auth_response({
            'ok': True,
            'message': 'Caja cerrada correctamente.',
            'cierre': _serialize_cierre_caja(cierre),
        }, status=201)


MAX_DIAS_RANGO_CUADRE_CAJA = 92


def reporte_cuadre_caja_rango_view(request):
    """
    Cuadre de caja para un rango de fechas — de solo lectura (no permite
    agregar consignaciones ni cerrar caja, eso sigue siendo por dia
    individual desde reporte_cuadre_caja_view, atado a un conteo fisico de
    efectivo de ese dia). Pensado para que un dueno/administrador revise
    varios dias o una semana completa de una vez, con el desglose dia por
    dia debajo para ver cuales de esos dias ya se cerraron.
    """
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not (_is_admin_user(request.user) or _is_cajera_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para ver este reporte.'}, status=401)

    desde_raw = request.GET.get('desde')
    hasta_raw = request.GET.get('hasta')
    try:
        desde = date.fromisoformat(desde_raw) if desde_raw else timezone.localdate().replace(day=1)
        hasta = date.fromisoformat(hasta_raw) if hasta_raw else timezone.localdate()
    except ValueError:
        return _auth_response({'ok': False, 'message': 'Las fechas no son validas.'}, status=400)
    if desde > hasta:
        return _auth_response({'ok': False, 'message': '"Desde" no puede ser posterior a "Hasta".'}, status=400)
    if (hasta - desde).days + 1 > MAX_DIAS_RANGO_CUADRE_CAJA:
        return _auth_response({
            'ok': False,
            'message': f'El rango no puede superar {MAX_DIAS_RANGO_CUADRE_CAJA} dias.',
        }, status=400)

    resumen = resumen_cuadre_caja_rango(desde, hasta)

    return _auth_response({
        'ok': True,
        'desde': desde.isoformat(),
        'hasta': hasta.isoformat(),
        'dias': [
            {
                'fecha': dia['fecha'].isoformat(),
                'tasa_bcv': str(dia['tasa_bcv']) if dia['tasa_bcv'] is not None else None,
                'total_general': str(dia['total_general']),
                'total_consignado': str(dia['total_consignado']),
                'gastos_efectivo': str(dia['gastos_efectivo']),
                'efectivo_esperado': str(dia['efectivo_esperado']),
                'cierre': _serialize_cierre_caja(dia['cierre']),
            }
            for dia in resumen['dias']
        ],
        'totales_por_metodo': [
            {
                **item,
                'total': str(item['total']),
                'total_bs': str(item['total_bs']) if item['total_bs'] is not None else None,
            }
            for item in resumen['totales_por_metodo']
        ],
        'total_general': str(resumen['total_general']),
        'desglose_caja': _serialize_desglose_caja(resumen['desglose_caja']),
        'total_consignado': str(resumen['total_consignado']),
        'gastos_efectivo': str(resumen['gastos_efectivo']),
        'efectivo_esperado': str(resumen['efectivo_esperado']),
    })


def reporte_disponibilidad_cuentas_view(request):
    """
    Saldo acumulado disponible en cada cuenta/metodo de pago hasta una
    fecha elegida (por defecto, hoy) — cuanto dinero neto tiene cada cuenta
    contando todo lo cobrado y pagado con ella desde que existe el sistema.
    De solo lectura; no modifica nada (a diferencia del cuadre de caja, aqui
    no hay cierre ni consignacion que registrar).
    """
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    fecha = _parse_fecha_reporte(request.GET.get('fecha'))
    if fecha is None:
        return _auth_response({'ok': False, 'message': 'Fecha invalida.'}, status=400)

    cuentas = disponibilidad_por_cuenta(fecha)
    tasa = tasa_para_fecha(fecha)

    return _auth_response({
        'ok': True,
        'fecha': fecha.isoformat(),
        'tasa_bcv': str(tasa) if tasa is not None else None,
        'cuentas': [
            {
                'id': cuenta['id'],
                'nombre': cuenta['nombre'],
                'moneda': cuenta['moneda'],
                'es_efectivo': cuenta['es_efectivo'],
                'activo': cuenta['activo'],
                'ingresos_acumulados': str(cuenta['ingresos_acumulados']),
                'gastos_acumulados': str(cuenta['gastos_acumulados']),
                'compras_acumuladas': str(cuenta['compras_acumuladas']),
                'consignado_acumulado': str(cuenta['consignado_acumulado']),
                'saldo_disponible': str(cuenta['saldo_disponible']),
                'saldo_disponible_bs': (
                    str((cuenta['saldo_disponible'] * tasa).quantize(Decimal('0.01')))
                    if cuenta['moneda'] == 'VES' and tasa is not None else None
                ),
            }
            for cuenta in cuentas
        ],
        'total_disponible': str(sum((cuenta['saldo_disponible'] for cuenta in cuentas), Decimal('0'))),
    })


# ---------------------------------------------------------------------------
# Estado de resultados
# ---------------------------------------------------------------------------
def reporte_estado_resultados_view(request):
    """
    Ventas − costo de ingredientes = utilidad bruta; utilidad bruta − gastos
    operativos = utilidad neta, para un rango de fechas. Reusa
    _calcular_margen_periodo (api_views.py, la misma logica del reporte de
    margen por plato) para "ventas" y "costo de ingredientes", y suma VGGasto
    por fecha_gasto (no por fecha de pago: un gasto cuenta para el periodo en
    que se incurrio, se haya pagado ya o no) para los gastos operativos.
    """
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    desde_raw = request.GET.get('desde')
    hasta_raw = request.GET.get('hasta')
    try:
        desde = date.fromisoformat(desde_raw) if desde_raw else timezone.localdate().replace(day=1)
        hasta = date.fromisoformat(hasta_raw) if hasta_raw else timezone.localdate()
    except ValueError:
        return _auth_response({'ok': False, 'message': 'Las fechas no son validas.'}, status=400)
    if desde > hasta:
        return _auth_response({'ok': False, 'message': '"Desde" no puede ser posterior a "Hasta".'}, status=400)

    _platos, ventas_total, costo_ingredientes_total, ventas_total_bs = _calcular_margen_periodo(desde, hasta)
    utilidad_bruta = ventas_total - costo_ingredientes_total

    gastos = VGGasto.objects.filter(fecha_gasto__gte=desde, fecha_gasto__lte=hasta).select_related('categoria')

    # gastos_total_bs suma monto x SU PROPIA tasa_cambio_referencia por cada gasto
    # (congelada al crearlo, ver gastos_views.py) — no el total en USD del período
    # multiplicado por la tasa vigente al pedir el reporte. Así el mismo período
    # muestra siempre el mismo total en bolívares sin importar cuándo se consulte.
    gastos_total = Decimal('0')
    gastos_total_bs = Decimal('0')
    totales_por_categoria = {}
    for gasto in gastos:
        gastos_total += gasto.monto
        entry = totales_por_categoria.setdefault(
            gasto.categoria_id, {'categoria_nombre': gasto.categoria.nombre, 'total': Decimal('0'), 'total_bs': Decimal('0')},
        )
        entry['total'] += gasto.monto
        if gasto.tasa_cambio_referencia:
            monto_bs = gasto.monto * gasto.tasa_cambio_referencia
            gastos_total_bs += monto_bs
            entry['total_bs'] += monto_bs
    gastos_por_categoria = sorted(
        [
            {
                **entry,
                'total': str(entry['total'].quantize(Decimal('0.01'))),
                'total_bs': str(entry['total_bs'].quantize(Decimal('0.01'))),
            }
            for entry in totales_por_categoria.values()
        ],
        key=lambda item: Decimal(item['total']), reverse=True,
    )

    # costo_ingredientes_total NO tiene una tasa propia que congelar: es un costo
    # unitario corriente (VGIngrediente.costo_unitario, promedio móvil por
    # VGCompra), no una transacción individual — ver el docstring de
    # _calcular_margen_periodo. Se convierte con la tasa vigente al CIERRE del
    # período (no la de hoy), para que el mismo período reportado no cambie de
    # valor en bolívares según cuándo se consulte, aunque no sea una suma
    # registro-por-registro como ventas_total_bs/gastos_total_bs.
    tasa_fin_periodo = tasa_para_fecha(hasta)
    costo_ingredientes_total_bs = (costo_ingredientes_total * tasa_fin_periodo) if tasa_fin_periodo else None
    utilidad_bruta_bs = (ventas_total_bs - costo_ingredientes_total_bs) if costo_ingredientes_total_bs is not None else None
    utilidad_neta_bs = (utilidad_bruta_bs - gastos_total_bs) if utilidad_bruta_bs is not None else None

    utilidad_neta = utilidad_bruta - gastos_total
    utilidad_neta_pct = (utilidad_neta / ventas_total * Decimal('100')) if ventas_total > 0 else Decimal('0')

    return _auth_response({
        'ok': True,
        'desde': desde.isoformat(),
        'hasta': hasta.isoformat(),
        'ventas_total': str(ventas_total.quantize(Decimal('0.01'))),
        'ventas_total_bs': str(ventas_total_bs.quantize(Decimal('0.01'))),
        'costo_ingredientes_total': str(costo_ingredientes_total.quantize(Decimal('0.01'))),
        'costo_ingredientes_total_bs': str(costo_ingredientes_total_bs.quantize(Decimal('0.01'))) if costo_ingredientes_total_bs is not None else None,
        'utilidad_bruta': str(utilidad_bruta.quantize(Decimal('0.01'))),
        'utilidad_bruta_bs': str(utilidad_bruta_bs.quantize(Decimal('0.01'))) if utilidad_bruta_bs is not None else None,
        'gastos_total': str(gastos_total.quantize(Decimal('0.01'))),
        'gastos_total_bs': str(gastos_total_bs.quantize(Decimal('0.01'))),
        'gastos_por_categoria': gastos_por_categoria,
        'utilidad_neta': str(utilidad_neta.quantize(Decimal('0.01'))),
        'utilidad_neta_bs': str(utilidad_neta_bs.quantize(Decimal('0.01'))) if utilidad_neta_bs is not None else None,
        'utilidad_neta_pct': str(utilidad_neta_pct.quantize(Decimal('0.01'))),
    })

    return _auth_response({'ok': False, 'message': 'Accion invalida.'}, status=400)


def reporte_movimiento_productos_view(request):
    """
    Cuantas unidades (o kg, para productos por peso) de cada producto se
    vendieron en un rango de fechas, agrupado por producto y por categoria.
    A diferencia de reporte_margen_ganancia_view, no calcula costo ni
    ganancia — solo el volumen de movimiento, para responder "cuanto se
    movio cada plato" sin entrar en plata. Solo incluye pedidos pagados
    (mismo criterio de "venta real" que el resto de los reportes de
    contabilidad) y solo productos con al menos una venta en el rango: los
    que no tuvieron movimiento simplemente no aparecen en la lista.
    """
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    desde_raw = request.GET.get('desde')
    hasta_raw = request.GET.get('hasta')
    try:
        desde = date.fromisoformat(desde_raw) if desde_raw else timezone.localdate()
        hasta = date.fromisoformat(hasta_raw) if hasta_raw else timezone.localdate()
    except ValueError:
        return _auth_response({'ok': False, 'message': 'Las fechas no son validas.'}, status=400)
    if desde > hasta:
        return _auth_response({'ok': False, 'message': '"Desde" no puede ser posterior a "Hasta".'}, status=400)

    detalles = (
        VGDetallePedido.objects
        .filter(
            pedido__estado='pagado',
            pedido__fecha_creacion__date__gte=desde,
            pedido__fecha_creacion__date__lte=hasta,
        )
        .select_related('producto__categoria')
    )

    filas_por_producto = {}
    for detalle in detalles:
        producto = detalle.producto
        peso_factor = (detalle.peso_gramos / Decimal('1000')) if detalle.peso_gramos else Decimal('1')
        cantidad_equivalente = Decimal(detalle.cantidad) * peso_factor

        fila = filas_por_producto.setdefault(producto.id, {
            'producto_id': producto.id,
            'nombre': producto.nombre,
            'categoria_id': producto.categoria_id,
            'categoria': producto.categoria.nombre if producto.categoria_id else 'Sin categoria',
            'venta_por_peso': producto.venta_por_peso,
            'cantidad_vendida': Decimal('0'),
            'pedidos': set(),
        })
        fila['cantidad_vendida'] += cantidad_equivalente
        fila['pedidos'].add(detalle.pedido_id)

    productos = []
    total_unidades = Decimal('0')
    total_kg = Decimal('0')
    categorias_totales = {}
    for fila in filas_por_producto.values():
        if fila['venta_por_peso']:
            total_kg += fila['cantidad_vendida']
        else:
            total_unidades += fila['cantidad_vendida']

        productos.append({
            'producto_id': fila['producto_id'],
            'nombre': fila['nombre'],
            'categoria_id': fila['categoria_id'],
            'categoria': fila['categoria'],
            'unidad': 'kg' if fila['venta_por_peso'] else 'unidad',
            'cantidad_vendida': str(fila['cantidad_vendida'].quantize(Decimal('0.01'))),
            'num_ventas': len(fila['pedidos']),
        })

        entry = categorias_totales.setdefault(fila['categoria_id'], {
            'categoria_id': fila['categoria_id'],
            'categoria': fila['categoria'],
            'cantidad_unidades': Decimal('0'),
            'cantidad_kg': Decimal('0'),
            'productos_distintos': 0,
        })
        if fila['venta_por_peso']:
            entry['cantidad_kg'] += fila['cantidad_vendida']
        else:
            entry['cantidad_unidades'] += fila['cantidad_vendida']
        entry['productos_distintos'] += 1

    productos.sort(key=lambda item: Decimal(item['cantidad_vendida']), reverse=True)

    categorias = sorted(
        [
            {
                'categoria_id': entry['categoria_id'],
                'categoria': entry['categoria'],
                'cantidad_unidades': str(entry['cantidad_unidades'].quantize(Decimal('0.01'))),
                'cantidad_kg': str(entry['cantidad_kg'].quantize(Decimal('0.01'))),
                'productos_distintos': entry['productos_distintos'],
            }
            for entry in categorias_totales.values()
        ],
        key=lambda item: (Decimal(item['cantidad_unidades']) + Decimal(item['cantidad_kg'])), reverse=True,
    )

    return _auth_response({
        'ok': True,
        'desde': desde.isoformat(),
        'hasta': hasta.isoformat(),
        'productos': productos,
        'categorias': categorias,
        'total_productos_distintos': len(productos),
        'total_unidades_vendidas': str(total_unidades.quantize(Decimal('0.01'))),
        'total_kg_vendidos': str(total_kg.quantize(Decimal('0.01'))),
    })

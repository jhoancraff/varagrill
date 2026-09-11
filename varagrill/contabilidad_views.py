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

from .api_views import _calcular_margen_periodo, _serialize_detalle_adicionales, _serialize_detalle_opciones
from .auth_helpers import _auth_response, _is_admin_user, _is_cajera_user
from .models import (
    VGAbonoCompra,
    VGCierreCaja,
    VGConciliacionBancaria,
    VGConsignacionCaja,
    VGCorreccionMetodoPago,
    VGDetallePedido,
    VGGasto,
    VGIngresoExtra,
    VGMetodoPago,
    VGNotaEntrega,
    VGPago,
)
from .tasa_cambio import tasa_cambio_para_registro
from .reportes import (
    desglose_caja_por_moneda,
    detalle_cuentas_cobradas_rango,
    detalle_cuentas_por_cobrar_rango,
    detalle_ventas_rango,
    disponibilidad_por_cuenta,
    efectivo_esperado_dia,
    gastos_efectivo_dia,
    resumen_cuadre_caja_rango,
    resumen_ventas_rango,
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
        'cuenta_bancaria': metodo.cuenta_bancaria,
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
        # Solo las de HOY: esta lista vive en Cobro, donde la cajera registra y
        # revisa las propinas/pagos extra de su turno actual — el historial
        # completo por fecha ya se ve en el cuadre de caja (diario o por rango).
        ingresos = (
            VGIngresoExtra.objects
            .filter(fecha_creacion__date=timezone.localdate())
            .select_related('metodo_pago', 'creado_por')
            .order_by('-fecha_creacion')
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
    # el registro (1.000 Bs pasarian a contarse como $1.000). Se redondea a 6
    # decimales, no 2: con la tasa BCV actual, redondear a centavos de dolar
    # perdia varios bolivares al reconvertir para mostrarlo (ver
    # VGIngresoExtra.monto).
    if metodo_pago.moneda == 'VES':
        tasa_conversion = tasa_cambio_para_registro()
        if not tasa_conversion or tasa_conversion <= 0:
            return _auth_response({
                'ok': False,
                'message': 'No hay tasa de cambio disponible para convertir el monto a dolares.',
            }, status=400)
        monto = (monto_input / tasa_conversion).quantize(Decimal('0.000001'))
    else:
        tasa_conversion = None
        monto = monto_input.quantize(Decimal('0.000001'))

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
            cuenta_bancaria=str(data.get('cuenta_bancaria', '') or '').strip(),
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

    if action == 'actualizar_cuenta_bancaria':
        try:
            metodo = VGMetodoPago.objects.get(pk=int(data.get('id')))
        except (TypeError, ValueError, VGMetodoPago.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'El metodo de pago no existe.'}, status=400)

        metodo.cuenta_bancaria = str(data.get('cuenta_bancaria', '') or '').strip()
        metodo.actualizado_por = request.user
        metodo.save(update_fields=['cuenta_bancaria', 'actualizado_por', 'fecha_actualizacion'])
        return _auth_response({
            'ok': True,
            'message': 'Banco actualizado correctamente.',
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


def _parse_rango_o_fecha_reporte(request):
    """
    Los reportes de detalle del cuadre de caja (ventas, cuentas por cobrar,
    cuentas cobradas) se piden con un solo `fecha` desde el cuadre diario, o
    con `desde`/`hasta` cuando se entra desde el cuadre por rango — mismo
    endpoint para los dos casos, reusando toda la logica de reportes.py
    (que ya trabaja en terminos de un rango, siendo un dia solo el caso
    desde == hasta). Devuelve (desde, hasta) o (None, None) si algo es
    invalido.
    """
    desde_raw = request.GET.get('desde')
    hasta_raw = request.GET.get('hasta')
    if desde_raw or hasta_raw:
        try:
            desde = date.fromisoformat(str(desde_raw))
            hasta = date.fromisoformat(str(hasta_raw))
        except (TypeError, ValueError):
            return None, None
        if desde > hasta or (hasta - desde).days + 1 > MAX_DIAS_RANGO_CUADRE_CAJA:
            return None, None
        return desde, hasta

    fecha = _parse_fecha_reporte(request.GET.get('fecha'))
    if fecha is None:
        return None, None
    return fecha, fecha


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


def _serialize_pago_dia(pago):
    tasa_documento_origen = None
    if pago.nota_entrega_id:
        origen = f'Nota {pago.nota_entrega.codigo}'
        tasa_documento_origen = pago.nota_entrega.tasa_cambio_referencia
    elif pago.factura_id:
        origen = f'Factura Nº {pago.factura.numero_factura}' if pago.factura.numero_factura else f'Factura #{pago.factura_id}'
        tasa_documento_origen = pago.factura.tasa_cambio_referencia
    elif pago.pedido_id:
        origen = f'Pedido #{pago.pedido_id}'
    else:
        origen = '—'
    return {
        'id': pago.id,
        'monto': str(pago.monto),
        'metodo_pago_id': pago.metodo_pago_id,
        'metodo_pago_nombre': pago.metodo_pago.nombre,
        'moneda': pago.metodo_pago.moneda,
        'origen': origen,
        'referencia': pago.referencia,
        'registrado_por': (pago.creado_por.get_full_name() or pago.creado_por.username) if pago.creado_por else '',
        'fecha_pago': pago.fecha_pago.isoformat(),
        # tasa_cambio_referencia: la tasa BCV congelada con la que se calculo
        # ESTE pago (ver nota_entrega_abono_view/factura_abono_view). Cuando
        # difiere de tasa_documento_origen es porque el fiado se cobro en un
        # dia distinto al de la nota/factura y se recalculo al BCV del dia
        # del cobro (ver totales_pagos_por_metodo en reportes.py) — el
        # frontend usa esta diferencia para mostrar el aviso de recalculo.
        'tasa_cambio_referencia': str(pago.tasa_cambio_referencia) if pago.tasa_cambio_referencia is not None else None,
        'tasa_documento_origen': str(tasa_documento_origen) if tasa_documento_origen is not None else None,
    }


def _serialize_correccion_metodo(correccion):
    return {
        'motivo': correccion.motivo,
        'metodo_anterior': correccion.metodo_anterior.nombre,
        'metodo_nuevo': correccion.metodo_nuevo.nombre,
        'corregido_por': (correccion.creado_por.get_full_name() or correccion.creado_por.username) if correccion.creado_por else '',
        'fecha_creacion': correccion.fecha_creacion.isoformat(),
    }


def _ultimas_correcciones_por_registro(tipo, registro_ids):
    """
    Ultima VGCorreccionMetodoPago de cada registro (tipo, id) — para mostrar el
    motivo del ultimo cambio de cuenta junto al pago/ingreso extra en el cuadre
    de caja (ver reporte_cuadre_caja_view).
    """
    if not registro_ids:
        return {}
    correcciones = (
        VGCorreccionMetodoPago.objects
        .filter(tipo=tipo, registro_id__in=registro_ids)
        .select_related('metodo_anterior', 'metodo_nuevo', 'creado_por')
        .order_by('registro_id', '-fecha_creacion')
    )
    resultado = {}
    for correccion in correcciones:
        # order_by ya deja la mas reciente primero dentro de cada registro_id —
        # la primera que se ve por id es la ultima corregida.
        if correccion.registro_id not in resultado:
            resultado[correccion.registro_id] = _serialize_correccion_metodo(correccion)
    return resultado


@csrf_exempt
def reporte_cuadre_caja_view(request):
    """
    Cuadre de caja diario: totales cobrados por metodo de pago (VGPago, mas
    propinas/pagos extra de VGIngresoExtra sumadas ahi mismo — ver
    totales_pagos_por_metodo), consignaciones parciales del turno y el cierre
    final del dia (unico por fecha, lo hace la ultima persona del turno).

    Tambien permite corregir la cuenta (metodo_pago) de un pago o un ingreso
    extra de ese dia — ver la accion 'cambiar_metodo_pago' — para cuando la
    cajera se equivoca de cuenta al cobrar y el dinero necesita "moverse" a la
    cuenta correcta para que el cuadre coincida con lo que de verdad hay en el
    banco.
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
        pagos_dia = (
            VGPago.objects
            .filter(fecha_pago__date=fecha, estado='completado')
            .select_related('metodo_pago', 'nota_entrega', 'factura', 'creado_por')
            .order_by('-fecha_pago')
        )
        cierre = VGCierreCaja.objects.filter(fecha=fecha).select_related('creado_por').first()
        tasa = tasa_para_fecha(fecha)

        correcciones_pago = _ultimas_correcciones_por_registro('pago', [item.id for item in pagos_dia])
        correcciones_ingreso = _ultimas_correcciones_por_registro('ingreso_extra', [item.id for item in ingresos_extra_dia])

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
            'resumen_ventas': {
                key: str(value) for key, value in resumen_ventas_rango(fecha, fecha).items()
            },
            'desglose_caja': _serialize_desglose_caja(desglose_caja_por_moneda(fecha)),
            'consignaciones': [_serialize_consignacion(item) for item in consignaciones],
            'total_consignado': str(total_consignado(fecha)),
            'ingresos_extra_dia': [
                {**_serialize_ingreso_extra(item), 'ultima_correccion': correcciones_ingreso.get(item.id)}
                for item in ingresos_extra_dia
            ],
            'total_ingresos_extra_dia': str(sum((item.monto for item in ingresos_extra_dia), Decimal('0'))),
            'pagos_dia': [
                {**_serialize_pago_dia(item), 'ultima_correccion': correcciones_pago.get(item.id)}
                for item in pagos_dia
            ],
            'metodos_pago': [_serialize_metodo_pago(metodo) for metodo in VGMetodoPago.objects.filter(activo=True).order_by('nombre')],
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

    if action == 'cambiar_metodo_pago':
        tipo = str(data.get('tipo', '')).strip().lower()
        if tipo not in ('pago', 'ingreso_extra'):
            return _auth_response({'ok': False, 'message': 'Tipo invalido.'}, status=400)

        # Obligatorio a propósito — ver el docstring de VGCorreccionMetodoPago:
        # es lo que deja un rastro auditable de POR QUÉ se movió cada plata
        # entre cuentas, no solo que se movió.
        motivo = str(data.get('motivo', '') or '').strip()
        if not motivo:
            return _auth_response({'ok': False, 'message': 'El motivo del cambio es obligatorio.'}, status=400)

        try:
            registro_id = int(data.get('id'))
        except (TypeError, ValueError):
            return _auth_response({'ok': False, 'message': 'Registro invalido.'}, status=400)

        try:
            metodo_nuevo = VGMetodoPago.objects.get(pk=int(data.get('metodo_pago_id')), activo=True)
        except (TypeError, ValueError, VGMetodoPago.DoesNotExist):
            return _auth_response({'ok': False, 'message': 'Selecciona una cuenta valida.'}, status=400)

        if tipo == 'pago':
            try:
                pago = VGPago.objects.select_related('metodo_pago').get(
                    pk=registro_id, fecha_pago__date=fecha, estado='completado',
                )
            except VGPago.DoesNotExist:
                return _auth_response({'ok': False, 'message': 'El pago no existe en esta fecha.'}, status=404)

            metodo_anterior = pago.metodo_pago
            if metodo_nuevo.id == pago.metodo_pago_id:
                return _auth_response({'ok': False, 'message': 'Ya está en esa cuenta.'}, status=400)

            pago.metodo_pago = metodo_nuevo
            pago.save(update_fields=['metodo_pago'])
            VGCorreccionMetodoPago.objects.create(
                tipo='pago', registro_id=pago.id, metodo_anterior=metodo_anterior, metodo_nuevo=metodo_nuevo,
                motivo=motivo, creado_por=request.user, actualizado_por=request.user,
            )
            return _auth_response({
                'ok': True,
                'message': f'Se movió el pago de {metodo_anterior.nombre} a {metodo_nuevo.nombre}.',
            })

        # tipo == 'ingreso_extra'
        try:
            ingreso = VGIngresoExtra.objects.select_related('metodo_pago').get(
                pk=registro_id, fecha_creacion__date=fecha,
            )
        except VGIngresoExtra.DoesNotExist:
            return _auth_response({'ok': False, 'message': 'El registro no existe en esta fecha.'}, status=404)

        metodo_anterior = ingreso.metodo_pago
        if metodo_nuevo.id == ingreso.metodo_pago_id:
            return _auth_response({'ok': False, 'message': 'Ya está en esa cuenta.'}, status=400)

        ingreso.metodo_pago = metodo_nuevo
        update_fields = ['metodo_pago']
        # Si pasa a ser una cuenta en bolivares y el registro no tenia tasa
        # congelada (porque se cargo en una cuenta en dolares, sin necesitar
        # ninguna), se congela la de ahora — sin esto, el monto en bolivares
        # que se muestre despues no tendria con que convertirse.
        if metodo_nuevo.moneda == 'VES' and not ingreso.tasa_cambio_referencia:
            tasa_nueva = tasa_cambio_para_registro()
            if tasa_nueva:
                ingreso.tasa_cambio_referencia = tasa_nueva
                update_fields.append('tasa_cambio_referencia')
        ingreso.save(update_fields=update_fields)
        VGCorreccionMetodoPago.objects.create(
            tipo='ingreso_extra', registro_id=ingreso.id, metodo_anterior=metodo_anterior, metodo_nuevo=metodo_nuevo,
            motivo=motivo, creado_por=request.user, actualizado_por=request.user,
        )
        return _auth_response({
            'ok': True,
            'message': f'Se movió de {metodo_anterior.nombre} a {metodo_nuevo.nombre}.',
        })

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

    ingresos_extra_rango = (
        VGIngresoExtra.objects
        .filter(fecha_creacion__date__gte=desde, fecha_creacion__date__lte=hasta)
        .select_related('metodo_pago', 'creado_por')
        .order_by('-fecha_creacion')
    )

    return _auth_response({
        'ok': True,
        'desde': desde.isoformat(),
        'hasta': hasta.isoformat(),
        'resumen_ventas': {
            key: str(value) for key, value in resumen_ventas_rango(desde, hasta).items()
        },
        'ingresos_extra_rango': [_serialize_ingreso_extra(item) for item in ingresos_extra_rango],
        'total_ingresos_extra_rango': str(sum((item.monto for item in ingresos_extra_rango), Decimal('0'))),
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


def _serialize_pago_venta(pago):
    return {
        'id': pago['id'],
        'monto': str(pago['monto']),
        'monto_bs': str(pago['monto_bs']) if pago['monto_bs'] is not None else None,
        'metodo_pago_id': pago['metodo_pago_id'],
        'metodo_pago_nombre': pago['metodo_pago_nombre'],
        'cuenta_bancaria': pago['cuenta_bancaria'],
        'referencia': pago['referencia'],
        'fecha_pago': pago['fecha_pago'].isoformat(),
    }


def _agrupar_items_nota(nota):
    """
    Todas las lineas de pedido (VGDetallePedido) de los VGPedido de esta nota,
    agrupadas por producto + adicionales + opciones exactamente iguales — asi
    "10 cervezas" queda en una sola fila del resumen en vez de una fila por
    cada vez que el mesero la agrego al pedido. Dos lineas del mismo producto
    pero con adicionales/opciones distintas NO se mezclan entre si (son
    platos distintos, aunque compartan producto base).
    """
    grupos = {}
    orden = []
    for pedido in nota.pedidos.all():
        for detalle in pedido.detalles.all():
            adicionales = _serialize_detalle_adicionales(detalle)
            opciones = _serialize_detalle_opciones(detalle)
            clave = (
                detalle.producto_id,
                tuple(sorted((a['nombre'], a['cantidad']) for a in adicionales)),
                tuple(sorted((o['grupo_nombre'], o['nombre']) for o in opciones)),
            )
            if clave not in grupos:
                grupos[clave] = {
                    'producto': detalle.producto.nombre,
                    'venta_por_peso': detalle.producto.venta_por_peso,
                    'cantidad': 0,
                    'peso_gramos': Decimal('0'),
                    'subtotal': Decimal('0'),
                    'adicionales': adicionales,
                    'opciones': opciones,
                }
                orden.append(clave)
            grupo = grupos[clave]
            grupo['cantidad'] += detalle.cantidad
            if detalle.peso_gramos:
                grupo['peso_gramos'] += detalle.peso_gramos
            grupo['subtotal'] += detalle.subtotal
    return [grupos[clave] for clave in orden]


def reporte_venta_nota_detalle_view(request, nota_id):
    """
    Detalle completo de una Nota de Entrega para el reporte de ventas del dia
    (ver reporte_ventas_dia_view): mesa(s), mesero(s) y el resumen de lo
    pedido (sumado por producto — ver _agrupar_items_nota), para saber
    exactamente que se vendio en esa nota sin ir a buscarlo en Pedidos.
    """
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not (_is_admin_user(request.user) or _is_cajera_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para ver este reporte.'}, status=401)

    try:
        nota = (
            VGNotaEntrega.objects
            .select_related('cliente')
            .prefetch_related(
                'pedidos__mesa', 'pedidos__usuario',
                'pedidos__detalles__producto',
                'pedidos__detalles__adicionales__preparacion',
                'pedidos__detalles__opciones',
            )
            .get(pk=nota_id)
        )
    except VGNotaEntrega.DoesNotExist:
        return _auth_response({'ok': False, 'message': 'La nota de entrega no existe.'}, status=404)

    pedidos = list(nota.pedidos.all())
    mesas = sorted({pedido.mesa.numero for pedido in pedidos if pedido.mesa_id})
    meseros = sorted({
        (pedido.usuario.get_full_name() or pedido.usuario.username)
        for pedido in pedidos if pedido.usuario_id
    })

    return _auth_response({
        'ok': True,
        'nota': {
            'id': nota.id,
            'codigo': nota.codigo,
            'cliente': nota.cliente.nombre if nota.cliente_id else '',
            'total': str(nota.total),
            'moneda': nota.moneda,
            'estado': nota.estado,
            'fecha_emision': nota.fecha_emision.isoformat(),
        },
        'mesas': mesas,
        'meseros': meseros,
        'items': [
            {
                'producto': item['producto'],
                'cantidad': item['cantidad'],
                'venta_por_peso': item['venta_por_peso'],
                'peso_gramos': str(item['peso_gramos']) if item['venta_por_peso'] else None,
                'subtotal': str(item['subtotal']),
                'adicionales': [a['nombre'] for a in item['adicionales']],
                'opciones': [f"{o['grupo_nombre']}: {o['nombre']}" for o in item['opciones']],
            }
            for item in _agrupar_items_nota(nota)
        ],
    })


def reporte_ventas_dia_view(request):
    """
    Detalle fila por fila de cada Nota de Entrega emitida en un dia o en un
    rango — el desglose de "Total vendido" del cuadre de caja (ver
    detalle_ventas_rango en reportes.py). De solo lectura. Acepta `fecha`
    (un dia, uso normal desde el cuadre diario) o `desde`/`hasta` (uso desde
    el cuadre por rango) — ver _parse_rango_o_fecha_reporte.
    """
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not (_is_admin_user(request.user) or _is_cajera_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para ver este reporte.'}, status=401)

    desde, hasta = _parse_rango_o_fecha_reporte(request)
    if desde is None:
        return _auth_response({'ok': False, 'message': 'Fecha invalida.'}, status=400)

    notas = detalle_ventas_rango(desde, hasta)

    todos_los_pago_ids = [pago['id'] for nota in notas for pago in nota['pagos']]
    correcciones_pago = _ultimas_correcciones_por_registro('pago', todos_los_pago_ids)

    return _auth_response({
        'ok': True,
        'fecha': hasta.isoformat(),
        'desde': desde.isoformat(),
        'hasta': hasta.isoformat(),
        'notas': [
            {
                'id': nota['id'],
                'codigo': nota['codigo'],
                'cliente': nota['cliente'],
                'total': str(nota['total']),
                'moneda': nota['moneda'],
                'estado': nota['estado'],
                'saldo_pendiente': str(nota['saldo_pendiente']),
                'pagos': [
                    {**_serialize_pago_venta(pago), 'ultima_correccion': correcciones_pago.get(pago['id'])}
                    for pago in nota['pagos']
                ],
            }
            for nota in notas
        ],
        'total_vendido': str(sum((nota['total'] for nota in notas), Decimal('0'))),
        'metodos_pago': [_serialize_metodo_pago(metodo) for metodo in VGMetodoPago.objects.filter(activo=True).order_by('nombre')],
    })


def reporte_cuentas_por_cobrar_view(request):
    """
    Detalle fila por fila de "Pendiente por cobrar" del cuadre de caja (ver
    detalle_cuentas_por_cobrar_rango en reportes.py): las notas de entrega
    emitidas en `fecha`, o en un rango `desde`/`hasta`, que todavia tienen
    saldo pendiente. De solo lectura — cobrar de verdad se sigue haciendo
    desde Cuentas por Cobrar.

    Este es un reporte HISTORICO de lo que se generó en el periodo:
    `saldo_pendiente_bs` se calcula con la tasa que se congeló al EMITIR
    cada nota (nota.tasa_cambio_referencia), no con la tasa BCV de hoy —
    reportado 2026-09: mostrar esto "a valor de hoy" hacía que el mismo
    período pasado se viera distinto cada vez que se refrescaba el cache
    del BCV, aunque nada hubiera cambiado de verdad. El recálculo a la tasa
    vigente (para saber cuánto cobrarle de verdad a un fiado viejo) sólo
    corresponde en el momento de cobrar, no acá — ver nota_entrega_abono_view.
    """
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not (_is_admin_user(request.user) or _is_cajera_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para ver este reporte.'}, status=401)

    desde, hasta = _parse_rango_o_fecha_reporte(request)
    if desde is None:
        return _auth_response({'ok': False, 'message': 'Fecha invalida.'}, status=400)

    notas = detalle_cuentas_por_cobrar_rango(desde, hasta)

    return _auth_response({
        'ok': True,
        'fecha': hasta.isoformat(),
        'desde': desde.isoformat(),
        'hasta': hasta.isoformat(),
        'notas': [
            {
                'id': nota['id'],
                'codigo': nota['codigo'],
                'cliente': nota['cliente'],
                'total': str(nota['total']),
                'saldo_pendiente': str(nota['saldo_pendiente']),
                'tasa_cambio_referencia': (
                    str(nota['tasa_cambio_referencia']) if nota['tasa_cambio_referencia'] is not None else None
                ),
                'saldo_pendiente_bs': (
                    str((nota['saldo_pendiente'] * nota['tasa_cambio_referencia']).quantize(Decimal('0.01')))
                    if nota['moneda'] == 'VES' and nota['tasa_cambio_referencia'] else None
                ),
                'moneda': nota['moneda'],
                'estado': nota['estado'],
                'fecha_emision': nota['fecha_emision'].isoformat(),
            }
            for nota in notas
        ],
        'total_pendiente': str(sum((nota['saldo_pendiente'] for nota in notas), Decimal('0'))),
    })


def reporte_cuentas_cobradas_dia_view(request):
    """
    Detalle fila por fila de "Cuentas cobradas" del cuadre de caja (ver
    detalle_cuentas_cobradas_rango en reportes.py): pagos de `fecha` (o del
    rango `desde`/`hasta`) contra un fiado de una fecha anterior, con la
    diferencia en bolivares entre la tasa del dia de emision y la tasa de
    cobro. De solo lectura.
    """
    if request.method != 'GET':
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not (_is_admin_user(request.user) or _is_cajera_user(request.user)):
        return _auth_response({'ok': False, 'message': 'No tienes permiso para ver este reporte.'}, status=401)

    desde, hasta = _parse_rango_o_fecha_reporte(request)
    if desde is None:
        return _auth_response({'ok': False, 'message': 'Fecha invalida.'}, status=400)

    filas = detalle_cuentas_cobradas_rango(desde, hasta)

    def _str_or_none(value):
        return str(value) if value is not None else None

    return _auth_response({
        'ok': True,
        'fecha': hasta.isoformat(),
        'desde': desde.isoformat(),
        'hasta': hasta.isoformat(),
        'pagos': [
            {
                'pago_id': fila['pago_id'],
                'nota_id': fila['nota_id'],
                'nota_codigo': fila['nota_codigo'],
                'cliente': fila['cliente'],
                'monto': str(fila['monto']),
                'moneda': fila['moneda'],
                'fecha_emision_nota': fila['fecha_emision_nota'].isoformat(),
                'fecha_pago': fila['fecha_pago'].isoformat(),
                'tasa_emision': _str_or_none(fila['tasa_emision']),
                'tasa_cobro': _str_or_none(fila['tasa_cobro']),
                'bs_a_tasa_emision': _str_or_none(fila['bs_a_tasa_emision']),
                'bs_a_tasa_cobro': _str_or_none(fila['bs_a_tasa_cobro']),
                'diferencia_bs': _str_or_none(fila['diferencia_bs']),
                'metodo_pago_nombre': fila['metodo_pago_nombre'],
                'cuenta_bancaria': fila['cuenta_bancaria'],
                'referencia': fila['referencia'],
            }
            for fila in filas
        ],
        'total_cobrado': str(sum((fila['monto'] for fila in filas), Decimal('0'))),
        'total_diferencia_bs': str(sum(
            (fila['diferencia_bs'] for fila in filas if fila['diferencia_bs'] is not None), Decimal('0'),
        )),
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

    cuentas, bancos = disponibilidad_por_cuenta(fecha)
    tasa = tasa_para_fecha(fecha)

    def _saldo_bs(saldo, moneda):
        return (
            str((saldo * tasa).quantize(Decimal('0.01')))
            if moneda == 'VES' and tasa is not None else None
        )

    def _serialize_cuenta(cuenta):
        return {
            'id': cuenta['id'],
            'nombre': cuenta['nombre'],
            'moneda': cuenta['moneda'],
            'es_efectivo': cuenta['es_efectivo'],
            'cuenta_bancaria': cuenta['cuenta_bancaria'],
            'activo': cuenta['activo'],
            'ingresos_acumulados': str(cuenta['ingresos_acumulados']),
            'ingresos_extra_acumulados': str(cuenta['ingresos_extra_acumulados']),
            'gastos_acumulados': str(cuenta['gastos_acumulados']),
            'compras_acumuladas': str(cuenta['compras_acumuladas']),
            'consignado_acumulado': str(cuenta['consignado_acumulado']),
            'saldo_disponible': str(cuenta['saldo_disponible']),
            'saldo_disponible_bs': _saldo_bs(cuenta['saldo_disponible'], cuenta['moneda']),
        }

    return _auth_response({
        'ok': True,
        'fecha': fecha.isoformat(),
        'tasa_bcv': str(tasa) if tasa is not None else None,
        'cuentas': [_serialize_cuenta(cuenta) for cuenta in cuentas],
        'bancos': [
            {
                'nombre': banco['nombre'],
                'agrupado': banco['agrupado'],
                'moneda': banco['moneda'],
                'moneda_mixta': banco.get('moneda_mixta', False),
                'saldo_disponible': str(banco['saldo_disponible']),
                'saldo_disponible_bs': _saldo_bs(banco['saldo_disponible'], banco['moneda']),
                'metodos': [_serialize_cuenta(cuenta) for cuenta in banco['metodos']],
            }
            for banco in bancos
        ],
        'total_disponible': str(sum((cuenta['saldo_disponible'] for cuenta in cuentas), Decimal('0'))),
    })


def _serialize_conciliacion(conciliacion):
    if conciliacion is None:
        return None
    saldo_banco_bs = None
    diferencia_bs = None
    if conciliacion.moneda == 'VES' and conciliacion.tasa_cambio_referencia:
        saldo_banco_bs = (conciliacion.saldo_banco * conciliacion.tasa_cambio_referencia).quantize(Decimal('0.01'))
        diferencia_bs = (conciliacion.diferencia * conciliacion.tasa_cambio_referencia).quantize(Decimal('0.01'))
    return {
        'id': conciliacion.id,
        'saldo_sistema': str(conciliacion.saldo_sistema),
        'saldo_banco': str(conciliacion.saldo_banco),
        'saldo_banco_bs': str(saldo_banco_bs) if saldo_banco_bs is not None else None,
        'diferencia': str(conciliacion.diferencia),
        'diferencia_bs': str(diferencia_bs) if diferencia_bs is not None else None,
        'notas': conciliacion.notas,
        'conciliado_por': (conciliacion.creado_por.get_full_name() or conciliacion.creado_por.username) if conciliacion.creado_por else '',
        'fecha_creacion': conciliacion.fecha_creacion.isoformat(),
    }


@csrf_exempt
def reporte_conciliacion_bancaria_view(request):
    """
    Conciliación bancaria por cuenta: compara, para cada banco real (ver
    disponibilidad_por_cuenta), el saldo que calcula el sistema contra el
    saldo que de verdad muestra el estado de cuenta o la app del banco en
    `fecha` — el equivalente de reporte_cuadre_caja_view pero para las
    cuentas que caen en un banco, no en la gaveta física. Las cuentas 100%
    efectivo (es_efectivo en todos sus métodos) no aparecen aquí: esas ya se
    cuadran en el cuadre de caja diario, no en este reporte.

    Solo administrador: es una revisión de fondo del negocio completo, igual
    que reporte_disponibilidad_cuentas_view (del que este reporte depende
    directamente), no una tarea operativa diaria de cajera.

    Una vez conciliada una cuenta para una fecha, esa fila queda fija (no se
    permite volver a conciliar la misma cuenta/fecha) — mismo criterio que
    VGCierreCaja: si hubo un error, se corrige con una fila nueva en la
    fecha en que se detecta, dejando rastro de ambas, en vez de reescribir
    la historia.
    """
    if request.method not in ['GET', 'POST']:
        return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)

    if not _is_admin_user(request.user):
        return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)

    if request.method == 'GET':
        fecha = _parse_fecha_reporte(request.GET.get('fecha'))
        if fecha is None:
            return _auth_response({'ok': False, 'message': 'Fecha invalida.'}, status=400)

        _cuentas, bancos = disponibilidad_por_cuenta(fecha)
        bancos = [banco for banco in bancos if not all(metodo['es_efectivo'] for metodo in banco['metodos'])]
        tasa = tasa_para_fecha(fecha)

        conciliaciones = {
            item.banco_nombre: item
            for item in VGConciliacionBancaria.objects.filter(
                fecha=fecha, banco_nombre__in=[banco['nombre'] for banco in bancos],
            ).select_related('creado_por')
        }

        def _saldo_bs(saldo, moneda):
            return (
                str((saldo * tasa).quantize(Decimal('0.01')))
                if moneda == 'VES' and tasa is not None else None
            )

        bancos_payload = [
            {
                'nombre': banco['nombre'],
                'agrupado': banco['agrupado'],
                'moneda': banco['moneda'],
                'moneda_mixta': banco.get('moneda_mixta', False),
                'num_metodos': len(banco['metodos']),
                'saldo_sistema': str(banco['saldo_disponible']),
                'saldo_sistema_bs': _saldo_bs(banco['saldo_disponible'], banco['moneda']),
                'conciliacion': _serialize_conciliacion(conciliaciones.get(banco['nombre'])),
            }
            for banco in bancos
        ]

        pendientes = sum(1 for item in bancos_payload if item['conciliacion'] is None)

        return _auth_response({
            'ok': True,
            'fecha': fecha.isoformat(),
            'tasa_bcv': str(tasa) if tasa is not None else None,
            'bancos': bancos_payload,
            'resumen': {
                'total_bancos': len(bancos_payload),
                'conciliados': len(bancos_payload) - pendientes,
                'pendientes': pendientes,
                'suma_diferencias': str(sum(
                    (Decimal(item['conciliacion']['diferencia']) for item in bancos_payload if item['conciliacion']),
                    Decimal('0'),
                )),
            },
        })

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except json.JSONDecodeError:
        return _auth_response({'ok': False, 'message': 'Formato JSON invalido.'}, status=400)

    action = str(data.get('action', '')).strip().lower()
    if action != 'conciliar':
        return _auth_response({'ok': False, 'message': 'Accion invalida.'}, status=400)

    fecha = _parse_fecha_reporte(data.get('fecha'))
    if fecha is None:
        return _auth_response({'ok': False, 'message': 'Fecha invalida.'}, status=400)

    banco_nombre = str(data.get('banco_nombre', '') or '').strip()
    if not banco_nombre:
        return _auth_response({'ok': False, 'message': 'Falta indicar la cuenta a conciliar.'}, status=400)

    try:
        saldo_banco_input = Decimal(str(data.get('saldo_banco', '')))
    except InvalidOperation:
        return _auth_response({'ok': False, 'message': 'El saldo del banco no es valido.'}, status=400)

    if VGConciliacionBancaria.objects.filter(fecha=fecha, banco_nombre=banco_nombre).exists():
        return _auth_response({'ok': False, 'message': 'Esta cuenta ya fue conciliada para esta fecha.'}, status=400)

    _cuentas, bancos = disponibilidad_por_cuenta(fecha)
    banco = next((item for item in bancos if item['nombre'] == banco_nombre), None)
    if banco is None:
        return _auth_response({'ok': False, 'message': 'Esa cuenta no existe.'}, status=404)
    if all(metodo['es_efectivo'] for metodo in banco['metodos']):
        return _auth_response({
            'ok': False,
            'message': 'Esta cuenta es efectivo fisico; se cuadra desde el Cuadre de Caja, no aqui.',
        }, status=400)

    tasa_conversion = None
    if banco['moneda'] == 'VES':
        tasa_conversion = tasa_para_fecha(fecha)
        if not tasa_conversion or tasa_conversion <= 0:
            return _auth_response({
                'ok': False,
                'message': 'No hay tasa BCV registrada para esta fecha; no se puede convertir el saldo a dolares.',
            }, status=400)
        saldo_banco_usd = (saldo_banco_input / tasa_conversion).quantize(Decimal('0.000001'))
    else:
        saldo_banco_usd = saldo_banco_input.quantize(Decimal('0.000001'))

    saldo_sistema = banco['saldo_disponible']
    diferencia = saldo_banco_usd - saldo_sistema

    conciliacion = VGConciliacionBancaria.objects.create(
        fecha=fecha,
        banco_nombre=banco_nombre,
        moneda=banco['moneda'],
        saldo_sistema=saldo_sistema,
        saldo_banco=saldo_banco_usd,
        tasa_cambio_referencia=tasa_conversion,
        diferencia=diferencia,
        notas=str(data.get('notas', '') or '').strip(),
        creado_por=request.user,
        actualizado_por=request.user,
    )
    return _auth_response({
        'ok': True,
        'message': 'Conciliacion registrada correctamente.',
        'conciliacion': _serialize_conciliacion(conciliacion),
    }, status=201)


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

    Las facturas de compra a proveedores (VGCompra, inventario subido por Excel)
    tambien se suman aca como si fueran un gasto mas — a diferencia de VGGasto,
    por fecha_pago de cada VGAbonoCompra (cuando de verdad se abono/pago, no
    cuando se cargo la factura): asi decidio el usuario tratarlas (2026-09),
    aceptando que un ingrediente ya vendido se cuenta dos veces (una vez aca al
    pagarlo, otra vez en costo_ingredientes_total via el costeo por receta) —
    ver la decision registrada en la conversacion de esa fecha.
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
    # Abonos a compras de proveedores pagados DENTRO del rango (por fecha_pago,
    # no por cuándo se cargó la factura) — se agrupan bajo una categoría
    # sintética para que aparezcan en el mismo desglose que los gastos.
    abonos_compra = VGAbonoCompra.objects.filter(
        fecha_pago__date__gte=desde, fecha_pago__date__lte=hasta,
    ).select_related('compra')
    compras_pagadas_total = Decimal('0')
    compras_pagadas_total_bs = Decimal('0')
    for abono in abonos_compra:
        compras_pagadas_total += abono.monto
        if abono.tasa_cambio_referencia:
            compras_pagadas_total_bs += abono.monto * abono.tasa_cambio_referencia
    if compras_pagadas_total > 0:
        gastos_total += compras_pagadas_total
        gastos_total_bs += compras_pagadas_total_bs
        totales_por_categoria['__compras_proveedores'] = {
            'categoria_nombre': 'Compras a proveedores (pagadas)',
            'total': compras_pagadas_total,
            'total_bs': compras_pagadas_total_bs,
        }

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

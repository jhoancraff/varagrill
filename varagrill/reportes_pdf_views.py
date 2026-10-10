"""
Vistas que responden reportes en PDF. La generacion del documento vive en pdf_reportes/.

Un reporte nuevo solo agrega una vista como reporte_inventario_pdf_view: usa
@pdf_solo_admin para el permiso, consulta sus datos, llama a su generar_pdf_* y
entrega el resultado con responder_pdf().
"""
from datetime import date
from functools import wraps

from django.db.models.functions import Coalesce, TruncDate
from django.http import HttpResponse
from django.utils import timezone

from .api_views import HIDDEN_INGREDIENT_IDS, _costo_unitario_efectivo, _serialize_compra
from .auth_helpers import _auth_response, _is_admin_user, _is_cajera_user
from .contabilidad_views import MAX_DIAS_RANGO_CUADRE_CAJA, _parse_rango_o_fecha_reporte
from .gastos_views import _parse_fecha, _serialize_gasto
from .models import VGCompra, VGGasto, VGIngrediente
from .pdf_reportes import (
    generar_pdf_cuentas_por_pagar, generar_pdf_facturado, generar_pdf_gastos, generar_pdf_inventario,
)
from .reportes import detalle_ventas_rango
from .tasa_cambio import obtener_tasa_actual


def _pdf_get_con_permiso(tiene_permiso, mensaje_sin_permiso):
    """Solo GET y solo a quien cumpla tiene_permiso(usuario); con la misma respuesta de error que el resto de la API."""
    def decorador(vista):
        @wraps(vista)
        def envuelta(request, *args, **kwargs):
            if request.method != 'GET':
                return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
            if not tiene_permiso(request.user):
                return _auth_response({'ok': False, 'message': mensaje_sin_permiso}, status=401)
            return vista(request, *args, **kwargs)
        return envuelta
    return decorador


# Administradores/contadores.
pdf_solo_admin = _pdf_get_con_permiso(_is_admin_user, 'Debes iniciar sesion como administrador.')
# Quien puede ver el cuadre de caja: administradores y cajeras.
pdf_admin_o_cajera = _pdf_get_con_permiso(
    lambda usuario: _is_admin_user(usuario) or _is_cajera_user(usuario),
    'Debes iniciar sesion como administrador o cajera.',
)


def responder_pdf(pdf, nombre_base, fecha=None, con_fecha=True):
    """
    Respuesta de descarga, sin cache (son datos en vivo): 'nombre_base-AAAA-MM-DD.pdf' con la fecha de
    hoy, o 'nombre_base.pdf' si con_fecha=False (cuando el nombre ya dice de que fechas es).
    """
    fecha = fecha or timezone.localtime()
    nombre = f'{nombre_base}-{fecha:%Y-%m-%d}' if con_fecha else nombre_base
    respuesta = HttpResponse(pdf, content_type='application/pdf')
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre}.pdf"'
    respuesta['Cache-Control'] = 'no-store'
    return respuesta


@pdf_solo_admin
def reporte_inventario_pdf_view(request):
    """
    PDF del stock actual de ingredientes: nombre, unidad, costo unitario, valor total
    (stock x costo) y stock actual. Usa el mismo costo "efectivo" y la misma lista (sin
    los ingredientes ocultos) que "Ver inventario actual", asi el PDF coincide con la pantalla.
    """
    ingredientes = list(
        VGIngrediente.objects.exclude(id__in=HIDDEN_INGREDIENT_IDS).values(
            'nombre', 'unidad_medida', 'stock_actual', 'costo_unitario', 'peso_real', 'precio_compra',
        )
    )
    for ingrediente in ingredientes:
        ingrediente['costo_unitario'] = _costo_unitario_efectivo(
            ingrediente['costo_unitario'], ingrediente['precio_compra'], ingrediente['peso_real'],
        )

    ahora = timezone.localtime()
    return responder_pdf(generar_pdf_inventario(ingredientes, generado_en=ahora), 'inventario-actual', ahora)


@pdf_solo_admin
def reporte_gastos_pdf_view(request):
    """
    PDF de gastos de un rango de fechas (fecha_desde / fecha_hasta, por la fecha del gasto),
    agrupados por categoria. Los montos en Bs y las tasas salen de _serialize_gasto, los mismos
    numeros del reporte de gastos en pantalla. Sin fechas usa el mes en curso, igual que la pantalla.
    """
    hoy = timezone.localdate()
    fecha_desde = _parse_fecha(request.GET.get('fecha_desde'), default=hoy.replace(day=1))
    fecha_hasta = _parse_fecha(request.GET.get('fecha_hasta'), default=hoy)
    if fecha_desde > fecha_hasta:
        return _auth_response({'ok': False, 'message': 'La fecha inicial no puede ser mayor que la final.'}, status=400)

    gastos = list(
        VGGasto.objects.select_related('categoria', 'creado_por').prefetch_related('abonos')
        .filter(fecha_gasto__gte=fecha_desde, fecha_gasto__lte=fecha_hasta)
        .order_by('categoria__nombre', 'fecha_gasto', 'id')
    )
    tasa_actual = obtener_tasa_actual() if any(g.moneda_origen == 'USD' for g in gastos) else None
    serializados = [_serialize_gasto(gasto, tasa_actual=tasa_actual) for gasto in gastos]

    pdf = generar_pdf_gastos(serializados, fecha_desde, fecha_hasta, generado_en=timezone.localtime())
    return responder_pdf(pdf, f'gastos-{fecha_desde:%Y-%m-%d}-al-{fecha_hasta:%Y-%m-%d}', con_fecha=False)


@pdf_admin_o_cajera
def reporte_facturado_pdf_view(request):
    """
    PDF de lo facturado (notas de entrega emitidas) de un dia (`fecha`, hoy por defecto) o de un rango
    (`desde`/`hasta`): el detalle de la tarjeta "Facturado" del cuadre de caja, con las mismas notas y
    montos que "Ventas del dia — detalle". Lo descargan administradores y cajeras, como el cuadre.
    """
    desde, hasta = _parse_rango_o_fecha_reporte(request)
    if desde is None:
        return _auth_response({
            'ok': False,
            'message': (
                'Fechas invalidas: "Desde" no puede ser posterior a "Hasta" '
                f'y el rango no puede superar {MAX_DIAS_RANGO_CUADRE_CAJA} dias.'
            ),
        }, status=400)

    notas = detalle_ventas_rango(desde, hasta)
    for nota in notas:
        nota['fecha_emision'] = timezone.localtime(nota['fecha_emision'])

    pdf = generar_pdf_facturado(notas, desde, hasta, generado_en=timezone.localtime())
    if desde == hasta:
        return responder_pdf(pdf, 'facturado', desde)
    return responder_pdf(pdf, f'facturado-{desde:%Y-%m-%d}-al-{hasta:%Y-%m-%d}', con_fecha=False)


def _en_rango(consulta, campo, desde, hasta):
    """Aplica el rango (cada extremo es opcional) sobre `campo`, un DateField o `algo__date`."""
    if desde:
        consulta = consulta.filter(**{f'{campo}__gte': desde})
    if hasta:
        consulta = consulta.filter(**{f'{campo}__lte': hasta})
    return consulta


def _cuenta_de_compra(compra):
    """Un lote como lo pide el PDF; los montos son los mismos de la pantalla (_serialize_compra)."""
    datos = _serialize_compra(compra)
    pagada = compra.estado_pago == 'pagada'
    return {
        'tipo': 'compra',
        'id': compra.id,
        'titulo': compra.proveedor_nombre,
        'detalle': f'Factura {compra.numero_factura_proveedor}' if compra.numero_factura_proveedor else '',
        'fecha': compra.fecha_factura or timezone.localtime(compra.fecha_creacion).date(),
        'estado': compra.estado_pago,
        'total': datos['total'],
        'total_bs': datos['total_bs'],
        'saldo': datos['saldo_pendiente'],
        'saldo_bs': datos['saldo_pendiente_bs'],
        'fecha_pago': timezone.localtime(compra.fecha_actualizacion).date() if pagada else None,
    }


def _cuenta_de_gasto(gasto, tasa_actual):
    """Un gasto como lo pide el PDF; los montos son los mismos de la pantalla (_serialize_gasto)."""
    datos = _serialize_gasto(gasto, tasa_actual=tasa_actual)
    pagado = gasto.estado_pago == 'pagado'
    detalle = gasto.descripcion
    if gasto.proveedor_nombre:
        detalle += f' · {gasto.proveedor_nombre}'
    if gasto.numero_comprobante:
        detalle += f' · Comp. {gasto.numero_comprobante}'
    return {
        'tipo': 'gasto',
        'id': gasto.id,
        'titulo': gasto.categoria.nombre,
        'detalle': detalle,
        'fecha': gasto.fecha_gasto,
        'estado': 'pagada' if pagado else gasto.estado_pago,
        'total': datos['monto'],
        'total_bs': datos['total_bs'],
        'saldo': datos['saldo_pendiente'],
        'saldo_bs': datos['saldo_pendiente_bs'],
        'fecha_pago': timezone.localtime(gasto.fecha_actualizacion).date() if pagado else None,
    }


@pdf_solo_admin
def reporte_cuentas_por_pagar_pdf_view(request):
    """
    PDF de cuentas por pagar (lotes de compra y gastos) con los filtros de la pantalla:

      tipo    todos | compra (lotes) | gasto
      estado  pendientes (por defecto: pendientes y abonadas) | pagadas | todos
      desde / hasta   opcionales, cada uno por separado

    El rango se aplica como en la pantalla de Cuentas por pagar: a las pendientes por la fecha de
    la cuenta (la de la factura en un lote, la del gasto) y a las pagadas por la fecha en que se
    terminaron de pagar (la pestana "Facturas pagadas").
    """
    tipo = str(request.GET.get('tipo') or 'todos').strip().lower()
    estado = str(request.GET.get('estado') or 'pendientes').strip().lower()
    if tipo not in ('todos', 'compra', 'gasto'):
        return _auth_response({'ok': False, 'message': 'El tipo debe ser todos, compra o gasto.'}, status=400)
    if estado not in ('pendientes', 'pagadas', 'todos'):
        return _auth_response({'ok': False, 'message': 'El estado debe ser pendientes, pagadas o todos.'}, status=400)
    try:
        desde = date.fromisoformat(request.GET['desde']) if request.GET.get('desde') else None
        hasta = date.fromisoformat(request.GET['hasta']) if request.GET.get('hasta') else None
    except ValueError:
        return _auth_response({'ok': False, 'message': 'Las fechas no son validas.'}, status=400)
    if desde and hasta and desde > hasta:
        return _auth_response({'ok': False, 'message': '"Desde" no puede ser posterior a "Hasta".'}, status=400)

    cuentas = []
    if tipo in ('todos', 'compra'):
        base = VGCompra.objects.select_related('creado_por').prefetch_related('abonos', 'notas_credito')
        if estado in ('pendientes', 'todos'):
            pendientes = base.filter(estado_pago__in=['pendiente', 'abonada_parcial']).annotate(
                fecha_cuenta=Coalesce('fecha_factura', TruncDate('fecha_creacion')),
            )
            cuentas += [_cuenta_de_compra(c) for c in _en_rango(pendientes, 'fecha_cuenta', desde, hasta)]
        if estado in ('pagadas', 'todos'):
            pagadas = base.filter(estado_pago='pagada')
            cuentas += [_cuenta_de_compra(c) for c in _en_rango(pagadas, 'fecha_actualizacion__date', desde, hasta)]
    if tipo in ('todos', 'gasto'):
        base = VGGasto.objects.select_related('categoria', 'creado_por').prefetch_related('abonos')
        gastos = []
        if estado in ('pendientes', 'todos'):
            pendientes = base.filter(estado_pago__in=['pendiente', 'abonada_parcial'])
            gastos += list(_en_rango(pendientes, 'fecha_gasto', desde, hasta))
        if estado in ('pagadas', 'todos'):
            pagadas = base.filter(estado_pago='pagado')
            gastos += list(_en_rango(pagadas, 'fecha_actualizacion__date', desde, hasta))
        # La tasa de hoy se consulta una sola vez para todos los gastos en dolares.
        tasa_actual = obtener_tasa_actual() if any(g.moneda_origen == 'USD' for g in gastos) else None
        cuentas += [_cuenta_de_gasto(g, tasa_actual) for g in gastos]

    ahora = timezone.localtime()
    pdf = generar_pdf_cuentas_por_pagar(cuentas, tipo, estado, desde, hasta, generado_en=ahora)

    nombre = ['cuentas-por-pagar', {'pendientes': 'pendientes', 'pagadas': 'pagadas', 'todos': 'todas'}[estado]]
    if tipo != 'todos':
        nombre.append('lotes' if tipo == 'compra' else 'gastos')
    if desde and hasta:
        nombre.append(f'{desde:%Y-%m-%d}-al-{hasta:%Y-%m-%d}')
    elif desde:
        nombre.append(f'desde-{desde:%Y-%m-%d}')
    elif hasta:
        nombre.append(f'hasta-{hasta:%Y-%m-%d}')
    else:
        nombre.append(f'{ahora:%Y-%m-%d}')
    return responder_pdf(pdf, '-'.join(nombre), con_fecha=False)

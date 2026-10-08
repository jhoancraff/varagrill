"""
Vistas que responden reportes en PDF. La generacion del documento vive en pdf_reportes/.

Un reporte nuevo solo agrega una vista como reporte_inventario_pdf_view: usa
@pdf_solo_admin para el permiso, consulta sus datos, llama a su generar_pdf_* y
entrega el resultado con responder_pdf().
"""
from datetime import date
from functools import wraps

from django.http import HttpResponse
from django.utils import timezone

from .api_views import HIDDEN_INGREDIENT_IDS, _costo_unitario_efectivo
from .auth_helpers import _auth_response, _is_admin_user
from .gastos_views import _parse_fecha, _serialize_gasto
from .models import VGGasto, VGIngrediente
from .pdf_reportes import generar_pdf_gastos, generar_pdf_inventario
from .tasa_cambio import obtener_tasa_actual


def pdf_solo_admin(vista):
    """Solo GET y solo administradores/contadores; con la misma respuesta de error que el resto de la API."""
    @wraps(vista)
    def envuelta(request, *args, **kwargs):
        if request.method != 'GET':
            return _auth_response({'ok': False, 'message': 'Metodo no permitido.'}, status=405)
        if not _is_admin_user(request.user):
            return _auth_response({'ok': False, 'message': 'Debes iniciar sesion como administrador.'}, status=401)
        return vista(request, *args, **kwargs)
    return envuelta


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

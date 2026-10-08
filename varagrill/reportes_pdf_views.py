"""
Vistas que responden reportes en PDF. La generacion del documento vive en pdf_reportes/.

Un reporte nuevo solo agrega una vista como reporte_inventario_pdf_view: usa
@pdf_solo_admin para el permiso, consulta sus datos, llama a su generar_pdf_* y
entrega el resultado con responder_pdf().
"""
from functools import wraps

from django.http import HttpResponse
from django.utils import timezone

from .api_views import HIDDEN_INGREDIENT_IDS, _costo_unitario_efectivo
from .auth_helpers import _auth_response, _is_admin_user
from .models import VGIngrediente
from .pdf_reportes import generar_pdf_inventario


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


def responder_pdf(pdf, nombre_base, fecha=None):
    """Respuesta de descarga: 'nombre_base-AAAA-MM-DD.pdf', sin cache (son datos en vivo)."""
    fecha = fecha or timezone.localtime()
    respuesta = HttpResponse(pdf, content_type='application/pdf')
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre_base}-{fecha:%Y-%m-%d}.pdf"'
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

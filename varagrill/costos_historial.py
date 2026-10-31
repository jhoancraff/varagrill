"""
Historial de costos de ingredientes y alertas de precio.

Los costos de las recetas se calculan en vivo a partir del costo de cada ingrediente, asi que un precio mal
cargado (un cero de mas, un total escrito como precio unitario) daña el costo de todas las recetas que lo usan
sin avisar. Este modulo lo hace visible: cada vez que cambia el costo de un ingrediente queda una fila en
VGHistorialCostoIngrediente (de donde vino, quien y cuanto cambio) y, si la variacion pasa el umbral de
VGConfiguracionCosteo.alerta_variacion_costo_pct, esa fila es una ALERTA pendiente de revision.

El registro sale de una senal de VGIngrediente (pre_save/post_save), no de cada pantalla: asi cubre cualquier via
que cambie el costo —lote manual, importacion por Excel, edicion del ingrediente, ingreso administrativo— y
las que se agreguen despues. Las vistas importantes indican el origen con `origen_costo(...)`; sin eso queda
como "Otro".

"Costo" aqui es el costo EFECTIVO (el que usan los reportes y las recetas: precio de compra / peso real cuando
estan cargados, y si no el costo guardado), no solo la columna costo_unitario.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal

from django.db.models.signals import post_save, pre_save

CAMPOS_COSTO = {'costo_unitario', 'precio_compra', 'peso_real'}
SEIS = Decimal('0.000001')
CENT = Decimal('0.01')

_contexto = ContextVar('origen_costo', default=None)


@contextmanager
def origen_costo(origen, compra=None):
    """Indica de donde viene el cambio de costo que ocurra dentro del bloque (y la compra, si la hay)."""
    token = _contexto.set({'origen': origen, 'compra': compra})
    try:
        yield
    finally:
        _contexto.reset(token)


def _decimal_o_none(valor):
    if valor is None or valor == '':
        return None
    return Decimal(str(valor))   # una instancia recien creada puede traer los valores como texto


def costo_efectivo(costo_unitario, precio_compra, peso_real):
    from .api_views import _costo_unitario_efectivo  # import tardio: api_views importa casi todo el proyecto
    return Decimal(str(_costo_unitario_efectivo(
        _decimal_o_none(costo_unitario), _decimal_o_none(precio_compra), _decimal_o_none(peso_real),
    )))


def variacion_pct(anterior, nuevo):
    """(nuevo - anterior) / anterior x 100, o None si no habia costo anterior."""
    anterior = Decimal(str(anterior))
    if anterior <= 0:
        return None
    return ((Decimal(str(nuevo)) - anterior) / anterior * Decimal('100')).quantize(CENT)


def umbral_alerta():
    from .models import VGConfiguracionCosteo
    return VGConfiguracionCosteo.obtener_config().alerta_variacion_costo_pct or Decimal('0')


def supera_umbral(variacion, umbral=None):
    umbral = umbral_alerta() if umbral is None else umbral
    return variacion is not None and umbral > 0 and abs(variacion) >= umbral


def _antes_de_guardar(sender, instance, update_fields=None, **kwargs):
    instance._costo_efectivo_previo = None
    if not instance.pk:
        return
    if update_fields is not None and not (set(update_fields) & CAMPOS_COSTO):
        return  # un guardado que no toca el costo (ej. solo el stock de una venta) no cuesta ninguna consulta extra
    fila = sender.objects.filter(pk=instance.pk).values('costo_unitario', 'precio_compra', 'peso_real').first()
    if fila is not None:
        instance._costo_efectivo_previo = costo_efectivo(fila['costo_unitario'], fila['precio_compra'], fila['peso_real'])


def _despues_de_guardar(sender, instance, created=False, **kwargs):
    from .models import VGHistorialCostoIngrediente

    previo = Decimal('0') if created else getattr(instance, '_costo_efectivo_previo', None)
    if previo is None:
        return
    nuevo = costo_efectivo(instance.costo_unitario, instance.precio_compra, instance.peso_real)
    if previo.quantize(SEIS) == nuevo.quantize(SEIS):
        return
    if created and nuevo <= 0:
        return
    variacion = variacion_pct(previo, nuevo)
    contexto = _contexto.get() or {}
    VGHistorialCostoIngrediente.objects.create(
        ingrediente=instance,
        costo_anterior=previo.quantize(SEIS),
        costo_nuevo=nuevo.quantize(SEIS),
        variacion_pct=variacion,
        origen=contexto.get('origen') or ('Alta del ingrediente' if created else 'Otro'),
        compra=contexto.get('compra'),
        es_alerta=supera_umbral(variacion),
        creado_por_id=instance.actualizado_por_id or instance.creado_por_id,
        actualizado_por_id=instance.actualizado_por_id or instance.creado_por_id,
    )
    instance._costo_efectivo_previo = None


def conectar_senales():
    from .models import VGIngrediente
    pre_save.connect(_antes_de_guardar, sender=VGIngrediente, dispatch_uid='costos_historial_pre')
    post_save.connect(_despues_de_guardar, sender=VGIngrediente, dispatch_uid='costos_historial_post')


def con_origen(resolver):
    """
    Decorador de vistas: todo cambio de costo que ocurra mientras la vista corre queda con ese origen.
    `resolver` es un texto fijo o una funcion (request) -> texto.
    """
    from functools import wraps

    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            origen = resolver(request) if callable(resolver) else resolver
            with origen_costo(origen):
                return vista(request, *args, **kwargs)
        return envoltura
    return decorador

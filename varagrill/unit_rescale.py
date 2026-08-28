"""
Reescalado de kg/l a g/ml para el catálogo de unidades de inventario (ver
migración 0025_solo_gramos_ml_unidad). Vive fuera de la migración para poder
reutilizar la misma lógica desde un test sin importar un módulo de
migraciones numerado — los tests pasan los modelos "vivos" de la app, la
migración pasa los modelos históricos de apps.get_model(...); a esta función
le da igual, solo necesita objetos con esos nombres de campo.

Regla de conversión: x1000 para una CANTIDAD FÍSICA (stock, cantidad
comprada/requerida, rendimiento de una subreceta), /1000 para un COSTO POR
UNIDAD (para que el dinero total, cantidad x costo_unitario, no cambie).
Nunca se toca un monto total ya pagado (ej. precio_total de un borrador de
compra) — eso es dinero, no depende de la unidad.
"""
from decimal import Decimal

FACTOR = Decimal('1000')

LEGACY_TO_NEW = {
    'kg': 'g',
    'l': 'ml',
}


def rescale_legacy_units(
    *,
    VGIngrediente,
    VGPreparacion,
    VGDetalleCompra,
    VGDetalleCompraBorrador,
    VGRecetaProducto,
    VGRecetaPreparacion,
):
    """Reescala en el sitio (guarda cada fila) y devuelve un dict con cuántas filas tocó cada modelo."""
    counts = {
        'ingredientes': 0,
        'preparaciones': 0,
        'detalle_compra': 0,
        'detalle_compra_borrador': 0,
        'receta_producto': 0,
        'receta_preparacion': 0,
    }

    ingredientes_convertidos = set()
    for ingrediente in VGIngrediente.objects.filter(unidad_medida__in=LEGACY_TO_NEW.keys()):
        ingrediente.stock_actual = (ingrediente.stock_actual or 0) * FACTOR
        ingrediente.stock_minimo = (ingrediente.stock_minimo or 0) * FACTOR
        ingrediente.costo_unitario = (ingrediente.costo_unitario or 0) / FACTOR
        ingrediente.unidad_medida = LEGACY_TO_NEW[ingrediente.unidad_medida]
        ingrediente.save(update_fields=['stock_actual', 'stock_minimo', 'costo_unitario', 'unidad_medida'])
        ingredientes_convertidos.add(ingrediente.id)
        counts['ingredientes'] += 1

    preparaciones_convertidas = set()
    for preparacion in VGPreparacion.objects.filter(rendimiento_unidad__in=LEGACY_TO_NEW.keys()):
        preparacion.rendimiento_cantidad = (preparacion.rendimiento_cantidad or 0) * FACTOR
        preparacion.rendimiento_unidad = LEGACY_TO_NEW[preparacion.rendimiento_unidad]
        preparacion.save(update_fields=['rendimiento_cantidad', 'rendimiento_unidad'])
        preparaciones_convertidas.add(preparacion.id)
        counts['preparaciones'] += 1

    if ingredientes_convertidos:
        for detalle in VGDetalleCompra.objects.filter(ingrediente_id__in=ingredientes_convertidos):
            detalle.cantidad = detalle.cantidad * FACTOR
            detalle.costo_unitario = detalle.costo_unitario / FACTOR
            detalle.save(update_fields=['cantidad', 'costo_unitario'])
            counts['detalle_compra'] += 1

        for detalle in VGDetalleCompraBorrador.objects.filter(ingrediente_id__in=ingredientes_convertidos):
            detalle.cantidad = detalle.cantidad * FACTOR
            detalle.save(update_fields=['cantidad'])
            counts['detalle_compra_borrador'] += 1

        for receta in VGRecetaProducto.objects.filter(ingrediente_id__in=ingredientes_convertidos):
            receta.cantidad_requerida = receta.cantidad_requerida * FACTOR
            receta.save(update_fields=['cantidad_requerida'])
            counts['receta_producto'] += 1

        for receta in VGRecetaPreparacion.objects.filter(ingrediente_id__in=ingredientes_convertidos):
            receta.cantidad_requerida = receta.cantidad_requerida * FACTOR
            receta.save(update_fields=['cantidad_requerida'])
            counts['receta_preparacion'] += 1

    if preparaciones_convertidas:
        for receta in VGRecetaProducto.objects.filter(preparacion_id__in=preparaciones_convertidas):
            receta.cantidad_requerida = receta.cantidad_requerida * FACTOR
            receta.save(update_fields=['cantidad_requerida'])
            counts['receta_producto'] += 1

        for receta in VGRecetaPreparacion.objects.filter(sub_preparacion_id__in=preparaciones_convertidas):
            receta.cantidad_requerida = receta.cantidad_requerida * FACTOR
            receta.save(update_fields=['cantidad_requerida'])
            counts['receta_preparacion'] += 1

    return counts

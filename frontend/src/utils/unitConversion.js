// Conversión de unidades para la receta de ingredientes de un producto (ver
// VGIngrediente.UNIDADES en el backend). Solo g/ml/unidad — el negocio ya no
// maneja kg/l (ver migración 0025_solo_gramos_ml_unidad), así que cada
// familia queda con un único miembro y convertirCantidad ahora siempre es un
// factor 1. El backend sigue siendo la conversión real al guardar
// (_convertir_cantidad_a_unidad_ingrediente en api_views.py) — esto es solo
// para mostrarle al analista una vista previa antes de enviar el formulario.

export const UNIT_FAMILY = {
  g: 'masa',
  ml: 'volumen',
  unidad: 'conteo',
};

const UNIT_TO_BASE = {
  g: 1,
  ml: 1,
  unidad: 1,
};

export const UNIT_OPTIONS = {
  g: ['g'],
  ml: ['ml'],
  unidad: ['unidad'],
};

export function convertirCantidad(cantidad, unidadOrigen, unidadDestino) {
  const value = Number(cantidad);
  if (!Number.isFinite(value)) {
    return null;
  }
  if (!unidadOrigen || unidadOrigen === unidadDestino) {
    return value;
  }
  if (UNIT_FAMILY[unidadOrigen] !== UNIT_FAMILY[unidadDestino] || !UNIT_TO_BASE[unidadOrigen] || !UNIT_TO_BASE[unidadDestino]) {
    return null;
  }
  return (value * UNIT_TO_BASE[unidadOrigen]) / UNIT_TO_BASE[unidadDestino];
}
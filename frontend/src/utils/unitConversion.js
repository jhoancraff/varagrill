// Conversión de unidades para la receta de ingredientes de un producto (ver
// VGIngrediente.UNIDADES en el backend). El analista puede teclear la cantidad en la
// unidad que le resulte más cómoda (ej. gramos) aunque el inventario del ingrediente
// viva en otra (ej. kilogramos); el backend hace la conversión real al guardar
// (_convertir_cantidad_a_unidad_ingrediente en api_views.py) — esto es solo para
// mostrarle al analista una vista previa antes de enviar el formulario.

export const UNIT_FAMILY = {
  kg: 'masa',
  g: 'masa',
  l: 'volumen',
  ml: 'volumen',
  unidad: 'conteo',
};

const UNIT_TO_BASE = {
  kg: 1000,
  g: 1,
  l: 1000,
  ml: 1,
  unidad: 1,
};

export const UNIT_OPTIONS = {
  kg: ['kg', 'g'],
  g: ['kg', 'g'],
  l: ['l', 'ml'],
  ml: ['l', 'ml'],
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
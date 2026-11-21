// Ingredientes por reponer que la pantalla de Stock mínimo le pasa a "Cargar por lote (factura de proveedor)":
// ahí se muestran como atajos (un clic llena el ingrediente y la cantidad que falta) y cada uno desaparece de la
// lista cuando se agrega a la compra. Vive en sessionStorage (solo esta pestaña) para sobrevivir al cambio de pantalla.
const CLAVE = 'vg.compras.sugeridos';

const esValido = (item) => item && Number.isInteger(item.id) && typeof item.nombre === 'string' && item.nombre.trim() !== '';

export function leerSugeridos() {
  try {
    const guardado = JSON.parse(window.sessionStorage.getItem(CLAVE) || '[]');
    return Array.isArray(guardado)
      ? guardado.filter(esValido).map((item) => ({
        id: item.id,
        nombre: item.nombre,
        unidad: typeof item.unidad === 'string' ? item.unidad : '',
        faltante: typeof item.faltante === 'string' ? item.faltante : '',
      }))
      : [];
  } catch (error) {
    return [];
  }
}

export function guardarSugeridos(items) {
  try {
    window.sessionStorage.setItem(CLAVE, JSON.stringify((items || []).filter(esValido)));
  } catch (error) {
    // Sin almacenamiento la compra se carga igual, solo sin los atajos.
  }
}

export function limpiarSugeridos() {
  try {
    window.sessionStorage.removeItem(CLAVE);
  } catch (error) {
    // Nada que limpiar.
  }
}

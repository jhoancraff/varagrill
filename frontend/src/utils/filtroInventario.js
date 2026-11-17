// Recuerda el filtro (categoría, búsqueda y página) del reporte de ingredientes mientras el usuario
// entra a "Modificar" y vuelve (con "Volver" o con el botón Atrás del navegador): sin esto la pantalla se
// vuelve a montar y el filtro se pierde. Vive en sessionStorage (solo esta pestaña) y se limpia al
// entrar al reporte desde el menú de Inventario, para que una consulta nueva empiece sin filtros.
const CLAVE = 'vg.inventario.filtros';
const VACIO = { categoria: '', busqueda: '', pagina: 0 };

export function leerFiltroInventario() {
  try {
    const guardado = JSON.parse(window.sessionStorage.getItem(CLAVE) || 'null');
    if (!guardado || typeof guardado !== 'object') {
      return { ...VACIO };
    }
    return {
      categoria: typeof guardado.categoria === 'string' ? guardado.categoria : '',
      busqueda: typeof guardado.busqueda === 'string' ? guardado.busqueda : '',
      pagina: Number.isInteger(guardado.pagina) && guardado.pagina > 0 ? guardado.pagina : 0,
    };
  } catch (error) {
    return { ...VACIO };
  }
}

export function guardarFiltroInventario(filtro) {
  try {
    window.sessionStorage.setItem(CLAVE, JSON.stringify(filtro));
  } catch (error) {
    // Sin almacenamiento la pantalla funciona igual, solo que no recuerda el filtro.
  }
}

export function limpiarFiltroInventario() {
  try {
    window.sessionStorage.removeItem(CLAVE);
  } catch (error) {
    // Nada que limpiar.
  }
}

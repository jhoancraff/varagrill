// Fecha compartida entre el cuadre de caja diario y sus 4 reportes de
// detalle (ventas del dia, cuentas por cobrar, cuentas cobradas, propinas):
// al entrar a un detalle desde el cuadre se debe usar la misma fecha que
// estaba elegida alli, y al volver el cuadre debe recordar esa fecha en vez
// de reiniciar a "hoy". sessionStorage (no un estado en memoria) porque cada
// pantalla es un componente separado que se monta/desmonta al navegar.
const KEY = 'contabilidad_fecha_seleccionada';

export function getFechaSeleccionada(fallback) {
  try {
    return sessionStorage.getItem(KEY) || fallback;
  } catch {
    return fallback;
  }
}

export function setFechaSeleccionada(fecha) {
  try {
    sessionStorage.setItem(KEY, fecha);
  } catch {
    // sessionStorage no disponible (modo privado, etc.) — la fecha
    // simplemente no persiste entre pantallas, sin romper nada.
  }
}

export function limpiarFechaSeleccionada() {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // ver comentario en setFechaSeleccionada.
  }
}

// Mismo mecanismo que la fecha de arriba, pero para el cuadre de caja POR
// RANGO y sus mismos 4 reportes de detalle: cuando el rango esta guardado,
// esas 4 pantallas de detalle deben consultar el rango completo (desde/hasta)
// en vez de un solo dia. Es un objeto {desde, hasta} en vez de un string
// porque hacen falta las dos fechas juntas o ninguna.
const RANGO_KEY = 'contabilidad_rango_seleccionado';

export function getRangoSeleccionado() {
  try {
    const raw = sessionStorage.getItem(RANGO_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && parsed.desde && parsed.hasta) {
      return parsed;
    }
    return null;
  } catch {
    return null;
  }
}

export function setRangoSeleccionado(desde, hasta) {
  try {
    sessionStorage.setItem(RANGO_KEY, JSON.stringify({ desde, hasta }));
  } catch {
    // ver comentario en setFechaSeleccionada.
  }
}

export function limpiarRangoSeleccionado() {
  try {
    sessionStorage.removeItem(RANGO_KEY);
  } catch {
    // ver comentario en setFechaSeleccionada.
  }
}

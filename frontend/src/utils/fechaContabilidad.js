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

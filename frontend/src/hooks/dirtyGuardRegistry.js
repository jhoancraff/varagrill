/**
 * Puente entre el formulario que está sucio (useUnsavedChangesGuard, dentro de
 * la página activa) y el router de más arriba (useViewHistory, en
 * WelcomeScreen) que no tiene forma de saber por sí solo si la pantalla que
 * está por abandonar tiene cambios sin guardar.
 *
 * Es un singleton fuera de React a propósito: en esta app solo hay UNA
 * pantalla activa a la vez (WelcomeScreen renderiza un único componente según
 * `activeView`), así que solo puede haber un formulario "sucio" a la vez —
 * no hace falta (ni conviene) modelar esto con Context, que forzaría a
 * envolver todo el árbol solo para un dato que en la práctica es siempre 0 o 1
 * guardián activo.
 */
let activeGuard = null;

/** Llamado por useUnsavedChangesGuard cuando su formulario pasa a estar sucio. */
export function setActiveGuard(guardFn) {
  activeGuard = guardFn;
}

/**
 * Llamado por useUnsavedChangesGuard cuando su formulario deja de estar sucio
 * (se guardó, se limpió, o el componente se desmonta). `guardFn` se pasa para
 * no borrar por error el guardián de OTRA pantalla si dos llamadas se cruzan
 * durante una transición de vista.
 */
export function clearActiveGuard(guardFn) {
  if (activeGuard === guardFn) {
    activeGuard = null;
  }
}

/** Borra el guardián sin importar cuál sea — usado al confirmar "salir sin guardar". */
export function forceClearActiveGuard() {
  activeGuard = null;
}

export function hasActiveGuard() {
  return activeGuard !== null;
}

/**
 * Ejecuta `action` directo si no hay ningún formulario sucio activo; si lo
 * hay, delega en su `guard()` (ver useUnsavedChangesGuard) — que la ejecuta
 * de una vez si al final no estaba sucio, o la deja pendiente y abre el modal
 * de confirmación si sí lo estaba.
 */
export function runWithActiveGuard(action) {
  if (activeGuard) {
    activeGuard(action);
  } else {
    action();
  }
}

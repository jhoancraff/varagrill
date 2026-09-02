/**
 * Puente diminuto entre useMobileBackHandler (que consume su propia entrada de
 * historial con un history.back() cuando una capa —modal/drawer— se cierra por
 * cualquier medio que no sea el Atrás físico) y useViewHistory (que escucha
 * TODOS los popstate para decidir a qué vista de la app volver).
 *
 * Sin esto, ese history.back() "interno" de una capa es indistinguible, para
 * useViewHistory, de un Atrás real del usuario: el evento resultante SÍ trae
 * `__appView` (porque volvió a la entrada de la vista actual, la que había
 * antes de que la capa empujara la suya) — así que el guardián de cambios sin
 * guardar de la vista activa se disparaba igual con solo cerrar un modal de
 * detalle, sin que el usuario intentara salir de la pantalla. Ver el mismo
 * patrón que useViewHistory ya usa para SUS propios history.back() internos
 * (suppressNextPopStateRef) — esto es esa misma idea, pero accesible entre
 * hooks que no se conocen entre sí.
 */
let suppressNext = false;

export function suppressNextPopState() {
  suppressNext = true;
}

export function consumeSuppressedPopState() {
  if (!suppressNext) {
    return false;
  }
  suppressNext = false;
  return true;
}

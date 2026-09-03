import { suppressNextPopState } from './popStateSuppression';

/**
 * Pila COMPARTIDA de "capas" (modal, drawer, panel lateral) que interceptan el
 * Atrás físico del celular — único consumidor: useMobileBackHandler.
 *
 * Por qué existe: antes, cada instancia de useMobileBackHandler registraba su
 * propio listener de `popstate` en `window` y decidía "¿este evento lo
 * disparé yo?" mirando solo un ref local propio. Eso funciona con una sola
 * capa abierta a la vez, pero se rompe apenas hay dos — por ejemplo el
 * Sidebar abierto (celular) y encima un modal (el picker de peso al agregar
 * un producto por kg, o el ConfirmModal de "Registrar nota de entrega" en
 * Cobro): cuando la capa de ARRIBA se cierra sola con su `history.back()`
 * interno, el `popstate` resultante es UN SOLO evento del navegador que
 * llega a TODOS los listeners activos por igual — incluido el del Sidebar,
 * que no disparó ese back pero tampoco tenía forma de saber que no era para
 * él, así que se cerraba solo. Con dos capas apiladas también podía pasar al
 * revés: el picker de peso se abría (empujaba su propia entrada) mientras la
 * entrada de la capa que se estaba cerrando debajo (el detalle del
 * producto) todavía no se había consumido — el `history.back()` diferido de
 * esa capa terminaba consumiendo la entrada NUEVA del picker en vez de la
 * suya propia, y el picker se cerraba solo apenas abría.
 *
 * La solución es un único listener de `popstate` para todas las capas y una
 * pila real: cada `pushLayer` se apila, y un Atrás físico solo cierra el
 * TOPE de la pila (revelando la capa de abajo, si la había) — nunca todas
 * las capas montadas a la vez.
 */
let stack = [];
let nextId = 1;
let pendingSelfPops = 0;

function handlePopState() {
  if (pendingSelfPops > 0) {
    // Eco de un history.back() que nosotros mismos disparamos al cerrar una
    // capa (ver popLayer) — no es un Atrás real del usuario.
    pendingSelfPops -= 1;
    return;
  }
  const top = stack.pop();
  if (top) {
    top.onClose();
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('popstate', handlePopState);
}

export function pushLayer(onClose) {
  const id = nextId;
  nextId += 1;
  stack.push({ id, onClose });
  window.history.pushState({ __mobileBackLayer: true }, '');
  return id;
}

// Consume la entrada de historial de una capa que se cerró por cualquier
// medio que no sea el Atrás físico (botón "X", click afuera, guardar y
// cerrar, confirmar...). Solo tocamos `history.back()` si esa capa sigue
// siendo el TOPE de la pila — si se cerró fuera de orden (no debería pasar
// en uso normal: las capas se cierran de arriba hacia abajo) preferimos
// dejar su entrada de historial huérfana antes que hacer back() sobre la
// entrada de OTRA capa que sigue abierta arriba de ella.
export function popLayer(id) {
  const idx = stack.findIndex((layer) => layer.id === id);
  if (idx === -1) {
    return;
  }
  const wasTop = idx === stack.length - 1;
  stack.splice(idx, 1);
  if (wasTop) {
    pendingSelfPops += 1;
    suppressNextPopState();
    window.history.back();
  }
}

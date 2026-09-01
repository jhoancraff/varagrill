import { useCallback, useEffect, useRef, useState } from 'react';
import { setActiveGuard, clearActiveGuard, forceClearActiveGuard } from './dirtyGuardRegistry';

/**
 * Detecta cambios sin guardar en un formulario y protege TODAS las salidas:
 * - Recarga/cierre real del navegador: dispara el diálogo nativo de
 *   "beforeunload" (el navegador no permite un modal propio ahí, es una
 *   restricción de seguridad del propio navegador, no una limitación
 *   nuestra) — igual avisa antes de perder los cambios.
 * - Cualquier salida DENTRO de la página (botón "Cancelar" del propio
 *   formulario, un link interno): usa `guard(accion)` en vez de llamar la
 *   acción directo. Si hay cambios sin guardar, abre el modal propio (ver
 *   UnsavedChangesModal) en vez de ejecutar la acción de una vez; si el
 *   usuario confirma que sí quiere salir, ahí se ejecuta.
 * - Cualquier salida FUERA de la página que el propio formulario no controla
 *   — click en el Sidebar, "Atrás" físico del celular/navegador, el botón
 *   "Volver" de la cabecera pasado como prop desde WelcomeScreen — se
 *   protege sola, sin que cada pantalla tenga que acordarse de envolver cada
 *   botón: mientras isDirty es true, este hook se registra a sí mismo (ver
 *   dirtyGuardRegistry) como "el formulario activo que hay que confirmar
 *   antes de dejar salir", y useViewHistory consulta ese registro antes de
 *   cualquier cambio de vista.
 *
 * `state` es cualquier valor serializable que represente "lo que el usuario
 * ha llenado" (el objeto form, o { form, listaExtra } combinados) — se
 * compara por JSON contra una copia base para saber si cambió. Esa copia
 * base se toma la primera vez que `state` deja de ser el valor inicial que
 * se le pasa a `baseline`, y se puede reiniciar a mano con `markClean()`
 * después de guardar con éxito (o de cargar datos existentes en un
 * formulario de edición), para que un guardado exitoso no quede marcado
 * como "cambios sin guardar".
 */
export default function useUnsavedChangesGuard(state, { enabled = true } = {}) {
  const baselineRef = useRef(JSON.stringify(state));
  const [isDirty, setIsDirty] = useState(false);
  const [pendingAction, setPendingAction] = useState(null);

  useEffect(() => {
    setIsDirty(enabled && JSON.stringify(state) !== baselineRef.current);
  }, [state, enabled]);

  useEffect(() => {
    if (!isDirty) {
      return undefined;
    }
    const handleBeforeUnload = (event) => {
      event.preventDefault();
      event.returnValue = '';
      return '';
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [isDirty]);

  const markClean = useCallback((nextState) => {
    baselineRef.current = JSON.stringify(nextState !== undefined ? nextState : state);
    setIsDirty(false);
    // Borrado síncrono del guardián, igual que en confirmLeave: si quien llama
    // markClean() navega en la MISMA función justo después (ej. handleSubmit
    // llamando a onSubmitSuccess tras un guardado exitoso), esa navegación
    // pasa por runWithActiveGuard() antes de que este setIsDirty(false) llegue
    // a confirmarse y su efecto alcance a des-registrar el guardián — sin este
    // borrado inmediato, runWithActiveGuard todavía ve el guardián viejo
    // (isDirty=true de la última vez que corrió su efecto) y abre el modal de
    // "cambios sin guardar" sobre una acción que en realidad ya se guardó.
    forceClearActiveGuard();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const guard = useCallback((action) => {
    if (isDirty) {
      setPendingAction(() => action);
    } else {
      action();
    }
  }, [isDirty]);

  // Registro/baja en el guardián global — SIEMPRE la versión más reciente de
  // `guard` (recreada cada vez que cambia `isDirty`), para que
  // useViewHistory/el Sidebar/el Atrás físico consulten el estado real de
  // esta pantalla en todo momento, no una copia vieja.
  useEffect(() => {
    if (!isDirty) {
      return undefined;
    }
    setActiveGuard(guard);
    return () => clearActiveGuard(guard);
  }, [isDirty, guard]);

  const confirmLeave = useCallback(() => {
    // El efecto secundario (current()) se ejecuta ACÁ, fuera del updater de
    // setPendingAction a propósito: React StrictMode invoca dos veces en
    // desarrollo cualquier función-actualizadora pasada a un setState (es su
    // manera de detectar updaters impuros) — si `current()` viviera dentro
    // del updater, una navegación con efectos no-idempotentes (como el
    // stack.pop()+history.back() de goBackView) se ejecutaría dos veces por
    // click, de-sincronizando la pila del historial real. Un callback de
    // evento normal (este) no se duplica así, solo los updaters/reducers.
    if (!pendingAction) {
      return;
    }
    // Borrado síncrono e incondicional: si `pendingAction` es a su vez una
    // navegación que también consulta el registro (ej. goBackView desde
    // useViewHistory), no debe encontrarse este mismo guardián todavía
    // activo y volver a preguntar — el usuario YA confirmó que quiere salir.
    // markClean() también lo haría, pero solo se refleja en el próximo
    // render; esto es inmediato.
    forceClearActiveGuard();
    markClean();
    const action = pendingAction;
    setPendingAction(null);
    action();
  }, [pendingAction, markClean]);

  const cancelLeave = useCallback(() => {
    setPendingAction(null);
  }, []);

  return {
    isDirty,
    markClean,
    guard,
    isConfirmOpen: pendingAction !== null,
    confirmLeave,
    cancelLeave,
  };
}

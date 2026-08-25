import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Detecta cambios sin guardar en un formulario y protege dos salidas:
 * - Recarga/cierre real del navegador: dispara el diálogo nativo de
 *   "beforeunload" (el navegador no permite un modal propio ahí, es una
 *   restricción de seguridad del propio navegador, no una limitación
 *   nuestra) — igual avisa antes de perder los cambios.
 * - Cualquier salida dentro de la app (botón "Volver", cambiar de pantalla):
 *   usa `guard(accion)` en vez de llamar la acción directo. Si hay cambios
 *   sin guardar, abre el modal propio (ver UnsavedChangesModal) en vez de
 *   ejecutar la acción de una vez; si el usuario confirma que sí quiere
 *   salir, ahí se ejecuta.
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const guard = useCallback((action) => {
    if (isDirty) {
      setPendingAction(() => action);
    } else {
      action();
    }
  }, [isDirty]);

  const confirmLeave = useCallback(() => {
    setPendingAction((current) => {
      if (current) {
        current();
      }
      return null;
    });
  }, []);

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

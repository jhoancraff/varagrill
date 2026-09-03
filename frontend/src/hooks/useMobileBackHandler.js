import { useEffect, useRef } from 'react';
import { pushLayer, popLayer } from './mobileBackLayerStack';

/**
 * Sincroniza una capa de UI (modal, drawer, panel lateral) con el historial del
 * navegador para que el botón/gesto físico de "Atrás" del celular la cierre en
 * vez de sacar al usuario de la app entera — el problema es que los cambios de
 * vista/modal se manejan solo con estado de React, sin tocar `window.history`,
 * así que el navegador no tiene ninguna entrada propia que "deshacer".
 *
 * Uso: dentro del componente que renderiza el modal/drawer,
 *
 *   useMobileBackHandler(isOpen, closeModal);
 *
 * Mientras `isOpen` es true, esta capa se apila en mobileBackLayerStack (que
 * empuja UNA entrada al historial). Si el usuario presiona Atrás, esa pila
 * cierra el TOPE — ver ese módulo para por qué hace falta una pila
 * compartida entre TODAS las capas en vez de que cada instancia escuche
 * `popstate` por su cuenta (con dos capas abiertas a la vez, ej. el Sidebar
 * + un modal encima, cada una decidiendo sola rompía a la otra). Si la capa
 * se cierra por cualquier otro medio (botón "X", click afuera, guardar y
 * cerrar...), consumimos su entrada al desmontar/cerrar para no dejar un
 * hueco fantasma que el siguiente Atrás tendría que saltar sin que se vea
 * ningún cambio en pantalla.
 *
 * Si no hay ninguna capa abierta (nadie llamó pushLayer), un Atrás en ese
 * momento simplemente no encuentra nada en la pila y el navegador hace su
 * comportamiento nativo — que en Home es exactamente lo que se pidió: salir.
 *
 * El efecto de arriba (montar/desmontar la capa) DIFIERE el `popLayer` de su
 * limpieza un tick: si el "monta" que sigue llega antes de que el timeout
 * dispare — que es exactamente lo que hace el doble-invoke de React
 * StrictMode (monta -> limpia -> monta, sincrónico, solo en desarrollo) —
 * se cancela y nunca se toca la pila ni el historial. Sin este diferido, ese
 * doble-invoke terminaba haciendo push + pop + push en el mismo tick y el
 * modal se cerraba solo apenas se abría (solo en desarrollo).
 */
export default function useMobileBackHandler(isOpen, onClose) {
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  const layerIdRef = useRef(null);
  const pendingPopTimeoutRef = useRef(null);

  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }

    if (pendingPopTimeoutRef.current) {
      // Doble-invoke de StrictMode: la limpieza de hace un instante ya
      // programó un popLayer diferido y este "monta" llegó antes de que
      // corriera — lo cancelamos, la capa que ya está apilada sigue siendo
      // válida, no hace falta apilar ni tocar el historial de nuevo.
      clearTimeout(pendingPopTimeoutRef.current);
      pendingPopTimeoutRef.current = null;
    } else {
      layerIdRef.current = pushLayer(() => onCloseRef.current());
    }

    return () => {
      pendingPopTimeoutRef.current = setTimeout(() => {
        pendingPopTimeoutRef.current = null;
        if (layerIdRef.current != null) {
          popLayer(layerIdRef.current);
          layerIdRef.current = null;
        }
      }, 0);
    };
  }, [isOpen]);
}

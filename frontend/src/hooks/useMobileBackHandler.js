import { useEffect, useRef } from 'react';
import { suppressNextPopState } from './popStateSuppression';

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
 * Mientras `isOpen` es true, esta capa empuja UNA entrada al historial. Si el
 * usuario presiona Atrás, el navegador dispara `popstate` y llamamos a
 * `onClose` en vez de dejar que salga de la app. Si la capa se cierra por
 * cualquier otro medio (botón "X", click afuera, guardar y cerrar...),
 * consumimos esa entrada con `history.back()` al desmontar/cerrar para no
 * dejar un hueco fantasma que el siguiente Atrás tendría que saltar sin que
 * se vea ningún cambio en pantalla.
 *
 * Si no hay ninguna capa abierta (nadie llamó pushState), un Atrás en ese
 * momento simplemente no encuentra listener nuestro y el navegador hace su
 * comportamiento nativo — que en Home es exactamente lo que se pidió: salir.
 */
export default function useMobileBackHandler(isOpen, onClose) {
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  const pushedRef = useRef(false);
  const closingFromPopStateRef = useRef(false);

  useEffect(() => {
    if (!isOpen) {
      return undefined;
    }

    window.history.pushState({ __mobileBackLayer: true }, '');
    pushedRef.current = true;
    closingFromPopStateRef.current = false;

    const handlePopState = () => {
      closingFromPopStateRef.current = true;
      onCloseRef.current();
    };

    window.addEventListener('popstate', handlePopState);

    return () => {
      window.removeEventListener('popstate', handlePopState);
      if (pushedRef.current && !closingFromPopStateRef.current) {
        // La capa se cerró por otro medio (no por Atrás) — consumimos la
        // entrada que empujamos para que el historial no quede desalineado.
        // suppressNextPopState() avisa a useViewHistory que el popstate que
        // esto está a punto de disparar es interno de esta capa, no un Atrás
        // real del usuario — sin esto, useViewHistory lo confunde con un
        // intento de salir de la pantalla activa y dispara su propio
        // guardián de cambios sin guardar por solo cerrar este modal.
        suppressNextPopState();
        window.history.back();
      }
      pushedRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);
}

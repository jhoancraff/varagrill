import { useCallback, useEffect, useRef, useState } from 'react';
import { runWithActiveGuard, hasActiveGuard } from './dirtyGuardRegistry';

/**
 * Reemplaza un simple `useState(vistaInicial)` para el router interno de
 * pantallas (WelcomeScreen) por uno que además sincroniza cada navegación con
 * `window.history`, para que el botón/gesto físico de "Atrás" del celular
 * navegue hacia la vista anterior en vez de salir de la app.
 *
 * Devuelve { activeView, goToView, goBackView }:
 *   - goToView(view)  — navegación "hacia adelante" (entrar a una subvista
 *     nueva: abrir un formulario, editar un registro, ir a un reporte...).
 *     Empuja `view` a la pila interna y a `window.history`.
 *   - goBackView()    — navegación "hacia atrás": saca la vista actual de la
 *     pila y vuelve a la anterior. A diferencia de codificar a mano "a qué
 *     vista específica regresa cada pantalla" (como estaba antes, un
 *     `onBack={() => setActiveView('padre-especifico')}` por cada una), acá
 *     el padre correcto sale solo de la ruta real que el usuario recorrió —
 *     así una misma pantalla (ej. el comprobante de pago) vuelve al lugar
 *     correcto sin importar desde cuál de sus varios padres posibles se
 *     entró.
 *
 * El gesto físico de Atrás dispara `popstate`, que hace exactamente lo mismo
 * que goBackView (sacar la vista actual de la pila) — así clickear "Volver"
 * en pantalla y presionar Atrás en el celular quedan sincronizados con la
 * MISMA pila, sin duplicar entradas ni romper el historial. Si el usuario ya
 * está en la vista raíz (sin nada apilado encima) y presiona Atrás, no hay
 * listener nuestro activo para esa capa y el navegador hace su
 * comportamiento nativo (salir de la app) — tal como se pidió.
 *
 * `event.state.__appView` (lo que de verdad guarda el navegador en cada
 * entrada) es la fuente de verdad para QUÉ vista mostrar tras un Atrás — la
 * pila interna (`stackRef`) es solo un cache local para saber "cuál es el
 * padre" y no depender de codificar cada `onBack` a mano. Si un Atrás llega
 * a una vista que no coincide con lo que la pila esperaba como padre
 * inmediato (no debería pasar en uso normal, pero por ejemplo una recarga a
 * mitad de sesión deja la pila en memoria en blanco mientras el navegador
 * sigue con la profundidad de antes), el handler se resincroniza tomando esa
 * vista como única entrada confiable en vez de arrastrar el desfase — un F5
 * ya pierde el estado de React de todos modos, así que no hay más que
 * conservar en ese momento.
 *
 * Guardián de cambios sin guardar (ver dirtyGuardRegistry/useUnsavedChangesGuard):
 * tanto goToView como goBackView consultan el registro antes de navegar — si
 * la pantalla activa tiene un formulario sucio, la navegación queda pendiente
 * y se abre el modal de confirmación en vez de perder los datos. Esto es lo
 * que protege el click en el Sidebar y cualquier otra navegación interna sin
 * que cada pantalla tenga que envolver cada botón a mano. El caso del Atrás
 * físico es más delicado porque el navegador YA movió el historial antes de
 * que nos enteremos (popstate no se puede cancelar): si hay un formulario
 * sucio, reponemos esa entrada de inmediato (deshaciendo visualmente el Atrás
 * sin que la pantalla cambie) y recién si el usuario confirma en el modal se
 * ejecuta el retroceso real.
 */
export default function useViewHistory(rootView) {
  const [activeView, setActiveView] = useState(rootView);
  const stackRef = useRef([rootView]);
  // true mientras estamos procesando un popstate que nosotros mismos
  // provocamos (con goBackView -> history.back()), para no reprocesarlo de
  // nuevo cuando el evento realmente llega.
  const suppressNextPopStateRef = useRef(false);
  // handlePopState necesita "cuál es la vista actual ANTES de este evento"
  // para poder reponerla si hay que cancelar un Atrás por datos sin guardar
  // — un ref en vez de leer `activeView` directo evita recrear el listener
  // en cada navegación.
  const activeViewAtEventRef = useRef(activeView);
  activeViewAtEventRef.current = activeView;

  useEffect(() => {
    // La primera entrada del historial (la que ya existía cuando esta pestaña
    // cargó, antes de que goToView empujara nada) nunca pasa por pushState —
    // así que llega sin `__appView`. Sin esto, el PRIMER Atrás después de UNA
    // sola navegación cae justo en esa entrada sin etiqueta: el handler de
    // popstate la trata como "fuera de la app" (ver el `if (!targetView)`
    // más abajo) y no hace nada, dejando la pantalla congelada — recién el
    // Atrás siguiente sale de Chrome de una, sin haber mostrado nunca Home en
    // el medio. replaceState (no pushState: no debe sumar profundidad) deja
    // esa entrada marcada como la raíz desde el arranque.
    window.history.replaceState({ __appView: rootView }, '');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const goToView = useCallback((view) => {
    runWithActiveGuard(() => {
      stackRef.current.push(view);
      window.history.pushState({ __appView: view }, '');
      setActiveView(view);
    });
  }, []);

  const goBackView = useCallback(() => {
    runWithActiveGuard(() => {
      const stack = stackRef.current;
      if (stack.length <= 1) {
        // Ya está en la raíz — no hay nada propio que retroceder. No tocamos
        // history acá: si esto se llamó desde un botón "Volver" en la raíz
        // simplemente no hace nada, correcto.
        return;
      }
      stack.pop();
      const target = stack[stack.length - 1];
      suppressNextPopStateRef.current = true;
      window.history.back();
      setActiveView(target);
    });
  }, []);

  // Para correcciones automáticas (ej. un guard de permisos que redirige lejos
  // de una vista prohibida apenas cambia el rol/la vista) que NO son una
  // navegación real del usuario: cambia la vista actual sin apilar una
  // entrada nueva de "adelante" ni tratarla como "atrás", y SIN pasar por el
  // guardián de cambios sin guardar (una corrección de permisos no es algo
  // que el usuario pueda cancelar quedándose con datos sin guardar).
  const replaceView = useCallback((view) => {
    const stack = stackRef.current;
    stack[stack.length - 1] = view;
    window.history.replaceState({ __appView: view }, '');
    setActiveView(view);
  }, []);

  useEffect(() => {
    const applyResync = (targetView) => {
      // Caso normal: el navegador retrocedió exactamente a lo que la pila
      // esperaba como padre — solo falta sacar el tope.
      const stack = stackRef.current;
      if (stack.length > 1 && stack[stack.length - 2] === targetView) {
        stack.pop();
        return;
      }
      // Desfase (típicamente por una recarga a mitad de sesión, ver el efecto
      // de arriba): confiamos en lo que el navegador dice y reconstruimos la
      // pila con eso como único dato confiable, en vez de arrastrar un pop
      // que ya no corresponde a la posición real.
      stackRef.current = [targetView];
    };

    const handlePopState = (event) => {
      if (suppressNextPopStateRef.current) {
        suppressNextPopStateRef.current = false;
        return;
      }

      const targetView = event.state?.__appView;
      if (!targetView) {
        // Salimos de todo lo que esta app empujó (o el estado no es
        // nuestro) — comportamiento nativo del navegador, tal como se pidió.
        return;
      }

      if (hasActiveGuard()) {
        // El navegador ya retrocedió una entrada real — la "cancelamos"
        // reponiéndola (la pantalla activa no cambia visualmente) y recién
        // ejecutamos el retroceso de verdad si el usuario confirma salir en
        // el modal.
        window.history.pushState({ __appView: activeViewAtEventRef.current }, '');
        runWithActiveGuard(() => {
          applyResync(targetView);
          suppressNextPopStateRef.current = true;
          window.history.back();
          setActiveView(targetView);
        });
        return;
      }

      applyResync(targetView);
      setActiveView(targetView);
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  return { activeView, goToView, goBackView, replaceView };
}

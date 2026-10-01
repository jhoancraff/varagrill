import { useLayoutEffect, useRef } from 'react';

// Campo de monto que se muestra con separador de miles mientras se escribe
// (1,100.88) pero cuyo valor — el que recibe onChange y el que se guarda en el
// estado/backend — es siempre el número limpio ("1100.88"), sin comas. Solo
// cambia lo que se VE: nada del formato viaja al servidor.
function formatearVisual(raw) {
  if (raw === '' || raw === null || raw === undefined) {
    return '';
  }
  const [entero, decimales] = String(raw).split('.');
  const enteroConComas = entero.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return decimales === undefined ? enteroConComas : `${enteroConComas}.${decimales}`;
}

function limpiar(texto, maxDecimales) {
  let limpio = texto.replace(/[^0-9.]/g, '');
  const primerPunto = limpio.indexOf('.');
  if (primerPunto !== -1) {
    limpio = limpio.slice(0, primerPunto + 1) + limpio.slice(primerPunto + 1).replace(/\./g, '');
  }
  let [entero, decimales] = limpio.split('.');
  entero = entero.replace(/^0+(?=\d)/, '');
  if (decimales !== undefined) {
    decimales = decimales.slice(0, maxDecimales);
    if (entero === '') {
      entero = '0';
    }
    return `${entero}.${decimales}`;
  }
  return entero;
}

function MoneyInput({ value, onChange, maxDecimales = 2, placeholder = '0.00', style, required, disabled, id }) {
  const inputRef = useRef(null);
  const caretPendiente = useRef(null);
  const visual = formatearVisual(value);

  // Tras reformatear (aparecen/desaparecen comas) el navegador manda el cursor
  // al final; se devuelve a la misma posición lógica: la que deja a su
  // izquierda la misma cantidad de dígitos/punto que antes de reformatear.
  useLayoutEffect(() => {
    const input = inputRef.current;
    const significativos = caretPendiente.current;
    if (!input || significativos === null || document.activeElement !== input) {
      return;
    }
    caretPendiente.current = null;
    let vistos = 0;
    let posicion = 0;
    while (posicion < visual.length && vistos < significativos) {
      if (visual[posicion] !== ',') {
        vistos += 1;
      }
      posicion += 1;
    }
    input.setSelectionRange(posicion, posicion);
  }, [visual]);

  const handleChange = (event) => {
    const texto = event.target.value;
    const caret = event.target.selectionStart ?? texto.length;
    caretPendiente.current = texto.slice(0, caret).replace(/[^0-9.]/g, '').length;
    onChange(limpiar(texto, maxDecimales));
  };

  return (
    <input
      id={id}
      ref={inputRef}
      type="text"
      inputMode="decimal"
      autoComplete="off"
      value={visual}
      onChange={handleChange}
      placeholder={placeholder}
      style={style}
      required={required}
      disabled={disabled}
    />
  );
}

export default MoneyInput;

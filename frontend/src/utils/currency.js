const bsFormatter = new Intl.NumberFormat('es-VE', {
  style: 'currency',
  currency: 'VES',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/**
 * Formatea un monto que YA está en bolívares (p. ej. la suma de varios
 * registros, cada uno convertido con su propia tasa histórica) — a
 * diferencia de formatBs, que convierte un monto en USD con una sola tasa.
 */
export function formatBsRaw(bsAmount) {
  const value = Number(bsAmount);
  if (!Number.isFinite(value)) {
    return '';
  }
  // Intl a veces pega el signo negativo justo al símbolo de moneda sin espacio
  // (ej. "Bs.S-547.491,63"); formateamos siempre el valor absoluto y anteponemos
  // el signo nosotros para que quede consistente ("-Bs.S 547.491,63").
  const sign = value < 0 ? '-' : '';
  return `${sign}${bsFormatter.format(Math.abs(value))}`;
}

export function formatBs(amountUsd, tasa) {
  const usdAmount = Number(amountUsd);
  const exchangeRate = Number(tasa);

  if (!Number.isFinite(usdAmount) || !Number.isFinite(exchangeRate) || exchangeRate <= 0) {
    return '';
  }

  return formatBsRaw(usdAmount * exchangeRate);
}

/**
 * Formatea un monto de una cuenta (nota de entrega/pre-factura/factura) en UNA sola
 * moneda, la que se eligió para esa cuenta (moneda: 'USD' o 'VES') — nunca muestra
 * las dos juntas. Si la cuenta es en bolívares pero no hay tasa disponible, cae a
 * dólares en vez de no mostrar nada.
 */
export function formatMontoDocumento(amountUsd, moneda, tasa) {
  if (moneda === 'VES') {
    const bs = formatBs(amountUsd, tasa);
    if (bs) {
      return bs;
    }
  }
  return `$${Number(amountUsd).toFixed(2)}`;
}
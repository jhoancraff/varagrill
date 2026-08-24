const bsFormatter = new Intl.NumberFormat('es-VE', {
  style: 'currency',
  currency: 'VES',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatBs(amountUsd, tasa) {
  const usdAmount = Number(amountUsd);
  const exchangeRate = Number(tasa);

  if (!Number.isFinite(usdAmount) || !Number.isFinite(exchangeRate) || exchangeRate <= 0) {
    return '';
  }

  return bsFormatter.format(usdAmount * exchangeRate);
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
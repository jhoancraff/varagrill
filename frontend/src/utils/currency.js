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
import { formatBs } from '../utils/currency';

/** Muestra el equivalente en bolívares junto a un precio en USD; no renderiza nada si falta la tasa. */
export default function BsAmount({ amountUsd, tasa, prefix = '· ', style }) {
  const formatted = formatBs(amountUsd, tasa);
  if (!formatted) {
    return null;
  }
  return (
    <span style={{ fontSize: '0.72em', opacity: 0.72, fontWeight: 500, marginLeft: 6, ...style }}>
      {prefix}{formatted}
    </span>
  );
}

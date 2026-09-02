import { formatBs, formatBsRaw } from '../utils/currency';

/**
 * Muestra el equivalente en bolívares junto a un precio en USD; no renderiza nada
 * si falta la tasa. Con `bs` se muestra ese valor ya convertido tal cual (p. ej. un
 * total que el backend ya sumó registro por registro con la tasa histórica de cada
 * uno) en vez de recalcularlo aquí con `amountUsd x tasa` — pasa `bs` cuando lo
 * tengas para no perder esa precisión histórica.
 */
export default function BsAmount({ amountUsd, tasa, bs, prefix = '· ', style }) {
  const formatted = bs !== undefined ? formatBsRaw(bs) : formatBs(amountUsd, tasa);
  if (!formatted) {
    return null;
  }
  return (
    <span style={{ color: '#fff', fontSize: '0.72em', opacity: 0.72, fontWeight: 500, marginLeft: 6, ...style }}>
      {prefix}{formatted}
    </span>
  );
}

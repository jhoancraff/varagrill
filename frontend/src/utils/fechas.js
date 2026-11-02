// Fecha real que se elige al registrar un gasto, una compra o un pago (ver fechas_registro.py en el backend):
// el sistema guarda siempre el momento exacto del registro, pero los reportes cuentan la fecha elegida.

export function hoyIso() {
  const ahora = new Date();
  const local = new Date(ahora.getTime() - ahora.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

function parseIso(iso) {
  const [anio, mes, dia] = String(iso || '').split('-').map(Number);
  if (!anio || !mes || !dia) return null;
  return new Date(anio, mes - 1, dia);
}

// '2026-10-31' -> '31/10/2026'
export function formatearFecha(iso) {
  const fecha = parseIso(iso);
  if (!fecha) return '';
  return `${String(fecha.getDate()).padStart(2, '0')}/${String(fecha.getMonth() + 1).padStart(2, '0')}/${fecha.getFullYear()}`;
}

// Cuantos dias antes de hoy es esa fecha (0 si es hoy o posterior).
export function diasAtras(iso) {
  const fecha = parseIso(iso);
  const hoy = parseIso(hoyIso());
  if (!fecha || !hoy) return 0;
  return Math.max(0, Math.round((hoy - fecha) / 86400000));
}

export function esHoy(iso) {
  return !iso || iso === hoyIso();
}

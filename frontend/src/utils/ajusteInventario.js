// Helpers compartidos por la lista de hojas de ajuste de inventario
// (AnalystAjusteInventarioPage) y el detalle de cada hoja (AnalystAjusteInventarioHojaPage).

const MESES = [
  'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
];

export function nombreMes(mes) {
  return MESES[(mes || 1) - 1] || '';
}

export function formatFechaHora(isoString) {
  if (!isoString) return '';
  return new Date(isoString).toLocaleString('es-VE', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

// "Ajuste #12" o, si la hoja tiene titulo, "Ajuste #12 — Conteo cocina".
export function nombreHoja(hoja) {
  return hoja.titulo ? `Ajuste #${hoja.id} — ${hoja.titulo}` : `Ajuste #${hoja.id}`;
}

// El estado que ve el analista: "Confirmada" solo si todo lo que tiene la hoja ya esta aplicado al stock.
export function estadoHoja(hoja) {
  if (hoja.mes_cerrado) return { clave: 'cerrada', label: 'Mes cerrado' };
  if (!hoja.total_lineas) return { clave: 'vacia', label: 'Vacía' };
  if (hoja.estado !== 'confirmado') return { clave: 'borrador', label: 'Borrador' };
  if (hoja.lineas_pendientes > 0) return { clave: 'pendiente', label: 'Cambios sin guardar' };
  return { clave: 'confirmada', label: 'Confirmada' };
}

const BADGES = {
  confirmada: { background: 'rgba(52, 211, 153, 0.18)', color: 'var(--vg-f-34d399)', border: '1px solid var(--vg-f-34d399-a400)' },
  borrador: { background: 'rgba(255, 205, 86, 0.18)', color: 'var(--vg-f-ffcd56)', border: '1px solid var(--vg-f-ffcd56-a400)' },
  pendiente: { background: 'rgba(255, 205, 86, 0.18)', color: 'var(--vg-f-ffcd56)', border: '1px solid var(--vg-f-ffcd56-a400)' },
  vacia: { background: 'rgba(var(--vg-ink), 0.06)', color: 'var(--vg-f-c8bbbb)', border: '1px solid rgba(var(--vg-ink), 0.14)' },
  cerrada: { background: 'rgba(var(--vg-ink), 0.06)', color: 'var(--vg-f-c8bbbb)', border: '1px solid rgba(var(--vg-ink), 0.14)' },
};

export function badgeEstadoStyle(clave) {
  return {
    display: 'inline-block',
    padding: '3px 10px',
    borderRadius: 999,
    fontSize: 11.5,
    fontWeight: 800,
    whiteSpace: 'nowrap',
    ...(BADGES[clave] || BADGES.vacia),
  };
}

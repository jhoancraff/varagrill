// Utilidades compartidas por las pantallas de lotes de punto de venta (POS):
// Cierre de caja, Lotes POS, Disponibilidad. Todos los montos de dinero que
// llegan del backend son strings decimales — se formatean aqui solo para
// mostrarlos, nunca se reenvian formateados.

export function formatMonto(value) {
  const number = Number(value || 0);
  return number.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function formatFecha(iso) {
  if (!iso) return '—';
  const [anio, mes, dia] = String(iso).slice(0, 10).split('-');
  return `${dia}/${mes}/${anio}`;
}

const DIAS_SEMANA = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'];

// "mié 07/10/2026" — el dia de la semana ayuda a ver de un vistazo que la fecha
// estimada de abono salto el fin de semana.
export function formatFechaConDia(iso) {
  if (!iso) return '—';
  const [anio, mes, dia] = String(iso).slice(0, 10).split('-').map(Number);
  const fecha = new Date(anio, mes - 1, dia);
  return `${DIAS_SEMANA[fecha.getDay()]} ${formatFecha(iso)}`;
}

export function formatFechaHora(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('es-VE', { dateStyle: 'short', timeStyle: 'short' });
}

export const ESTADO_LOTE_ESTILO = {
  abierto: { color: '#bde0ff', background: 'rgba(59,130,246,0.18)' },
  cerrado: { color: '#ffe3a3', background: 'rgba(255,193,7,0.16)' },
  acreditado: { color: '#bdf0cf', background: 'rgba(70,200,120,0.16)' },
  conciliado: { color: '#d6c8ff', background: 'rgba(139,92,246,0.18)' },
  anulado: { color: '#c8bbbb', background: 'rgba(255,255,255,0.08)' },
};

// POST a /api/admin/lotes-pos/ con el patron `action`. Lanza Error con el
// mensaje del servidor si algo falla.
export async function postLotePos(payload) {
  const response = await fetch('/api/admin/lotes-pos/', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const json = await response.json().catch(() => ({}));
  if (!response.ok || !json.ok) {
    throw new Error(json.message || 'No se pudo completar la accion sobre el lote.');
  }
  return json;
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

// Abre una ventana con el detalle del lote (un renglon por cobro, con su nota de
// entrega) lista para imprimir desde la PC — para comparar contra el cierre de lote
// que imprime el punto fisico cuando la impresora termica no esta disponible.
// `lote` debe traer `pagos` (detalle del lote).
export function imprimirLoteEnNavegador(lote) {
  const vigentes = (lote.pagos || []).filter((pago) => pago.estado !== 'anulado');
  const totalBs = vigentes.reduce((acc, pago) => acc + Number(pago.monto_bs || 0), 0);
  const totalUsd = vigentes.reduce((acc, pago) => acc + Number(pago.monto_usd || 0), 0);
  const filas = vigentes.map((pago, index) => `
    <tr>
      <td>${index + 1}</td>
      <td>${escapeHtml(new Date(pago.fecha_pago).toLocaleTimeString('es-VE', { hour: '2-digit', minute: '2-digit' }))}</td>
      <td>${escapeHtml(pago.origen)}</td>
      <td>${escapeHtml(pago.cliente || '')}</td>
      <td>${escapeHtml(pago.referencia && !String(pago.referencia).startsWith('ABONO-') ? pago.referencia : '')}</td>
      <td class="num">${pago.monto_bs ? `Bs ${escapeHtml(formatMonto(pago.monto_bs))}` : '—'}</td>
      <td class="num">$${escapeHtml(formatMonto(pago.monto_usd))}</td>
    </tr>`).join('');
  const html = `<!doctype html><html lang="es"><head><meta charset="utf-8"><title>${escapeHtml(lote.codigo)} — cierre de lote</title>
    <style>
      body { font-family: Arial, sans-serif; color: #111; margin: 24px; }
      h1 { font-size: 20px; margin: 0 0 4px; }
      .meta { font-size: 13px; color: #333; margin-bottom: 14px; line-height: 1.5; }
      table { border-collapse: collapse; width: 100%; font-size: 13px; }
      th, td { border: 1px solid #999; padding: 5px 8px; text-align: left; }
      th { background: #eee; }
      .num { text-align: right; white-space: nowrap; }
      tfoot td { font-weight: bold; background: #f5f5f5; }
      .nota { margin-top: 14px; font-size: 12px; color: #555; }
    </style></head><body>
    <h1>Cierre de lote de punto de venta — ${escapeHtml(lote.codigo)}</h1>
    <div class="meta">
      Método: ${escapeHtml(lote.metodo_pago_nombre)}${lote.cuenta_bancaria ? ` (${escapeHtml(lote.cuenta_bancaria)})` : ''}<br>
      Operación: ${escapeHtml(formatFecha(lote.fecha_operacion))}${lote.fecha_cierre ? ` · Cerrado: ${escapeHtml(formatFechaHora(lote.fecha_cierre))}${lote.cerrado_por ? ` por ${escapeHtml(lote.cerrado_por)}` : ''}` : ' · Lote abierto (parcial)'}<br>
      Compara este detalle con el cierre de lote impreso por el punto.
    </div>
    <table>
      <thead><tr><th>#</th><th>Hora</th><th>Nota de entrega</th><th>Cliente</th><th>Referencia</th><th class="num">Monto Bs</th><th class="num">Monto $</th></tr></thead>
      <tbody>${filas}</tbody>
      <tfoot><tr><td colspan="5">Total (${vigentes.length} cobro(s))</td><td class="num">Bs ${escapeHtml(formatMonto(totalBs))}</td><td class="num">$${escapeHtml(formatMonto(totalUsd))}</td></tr></tfoot>
    </table>
    <div class="nota">Documento sin efecto fiscal.</div>
    <script>window.onload = function () { window.print(); };<\/script>
    </body></html>`;
  const ventana = window.open('', '_blank', 'width=900,height=700');
  if (!ventana) {
    throw new Error('El navegador bloqueó la ventana de impresión. Permite las ventanas emergentes e intenta de nuevo.');
  }
  ventana.document.open();
  ventana.document.write(html);
  ventana.document.close();
}

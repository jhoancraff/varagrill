const TICKET_STYLES = `
  @page { size: 80mm auto; margin: 0; }
  * { box-sizing: border-box; }
  html, body {
    margin: 0;
    padding: 0;
    width: 80mm;
    font-family: 'Courier New', Courier, monospace;
    color: #000;
    background: #fff;
  }
  .ticket { padding: 4mm 3mm; }
  .center { text-align: center; }
  .title { font-size: 15px; font-weight: 700; text-transform: uppercase; margin: 0 0 2mm; }
  .subtitle { font-size: 11px; margin: 0 0 3mm; }
  .meta { font-size: 12px; margin: 0 0 1mm; }
  .divider { border-top: 1px dashed #000; margin: 3mm 0; }
  .item { margin: 0 0 2.5mm; }
  .item-line { font-size: 15px; font-weight: 700; }
  .item-note { font-size: 12px; padding-left: 3mm; }
  .notes { font-size: 12px; margin-top: 3mm; padding-top: 2mm; border-top: 1px dashed #000; }
  .footer { font-size: 10px; text-align: center; margin-top: 4mm; }
`;

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function tipoPedidoLabel(tipoPedido) {
  if (tipoPedido === 'llevar') {
    return 'Para llevar';
  }
  if (tipoPedido === 'delivery') {
    return 'Delivery';
  }
  return 'Local';
}

function formatTicketTime(dateInput) {
  const date = dateInput ? new Date(dateInput) : new Date();
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  return date.toLocaleString('es-ES', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function normalizeTicket(ticket = {}) {
  const itemsSource = Array.isArray(ticket.items) ? ticket.items : [];

  return {
    pedidoId: ticket.pedidoId ?? ticket.pedido_id ?? ticket.id ?? '',
    mesa: ticket.mesa ?? ticket.mesaNumero ?? ticket.mesa_numero ?? null,
    tipoPedido: ticket.tipoPedido ?? ticket.tipo_pedido ?? 'local',
    mesero: ticket.mesero ?? ticket.usuario ?? '',
    creadoEn: ticket.creadoEn ?? ticket.creado_en ?? ticket.createdAt ?? ticket.fecha_creacion ?? null,
    notasGenerales: ticket.notasGenerales ?? ticket.notas ?? '',
    items: itemsSource.map((item) => ({
      cantidad: item.cantidad ?? item.qty ?? 1,
      producto: item.producto ?? item.producto_nombre ?? item.nombre ?? '',
      notas: item.notas ?? item.notes ?? '',
      adicionales: Array.isArray(item.adicionales) ? item.adicionales.map((addon) => ({
        cantidad: addon.cantidad ?? 1,
        nombre: addon.nombre ?? '',
      })) : [],
      composicion: Array.isArray(item.composicion) ? item.composicion : [],
    })),
  };
}

export function buildKitchenTicketHtml(ticket) {
  const normalizedTicket = normalizeTicket(ticket);
  const items = normalizedTicket.items;

  const itemsHtml = items.map((item) => `
    <div class="item">
      <div class="item-line">${escapeHtml(item.cantidad)}x ${escapeHtml(item.producto)}</div>
      ${item.notas ? `<div class="item-note">- ${escapeHtml(item.notas)}</div>` : ''}
      ${item.adicionales.map((addon) => `<div class="item-note">+ ${escapeHtml(addon.cantidad)}x ${escapeHtml(addon.nombre)}</div>`).join('')}
      ${item.composicion.length > 0 ? `<div class="item-note">Lleva: ${escapeHtml(item.composicion.join(', '))}</div>` : ''}
    </div>
  `).join('');

  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Comanda #${escapeHtml(normalizedTicket.pedidoId)}</title>
    <style>${TICKET_STYLES}</style>
  </head>
  <body>
    <div class="ticket">
      <div class="title center">Varagrill</div>
      <div class="subtitle center">Comanda de cocina</div>
      <div class="meta">Pedido #${escapeHtml(normalizedTicket.pedidoId)}</div>
      <div class="meta">${escapeHtml(normalizedTicket.mesa ? `Mesa ${normalizedTicket.mesa}` : 'Sin mesa')} &middot; ${escapeHtml(tipoPedidoLabel(normalizedTicket.tipoPedido))}</div>
      ${normalizedTicket.mesero ? `<div class="meta">Mesero: ${escapeHtml(normalizedTicket.mesero)}</div>` : ''}
      <div class="meta">${escapeHtml(formatTicketTime(normalizedTicket.creadoEn))}</div>
      <div class="divider"></div>
      ${itemsHtml || '<div class="item-line">Sin items</div>'}
      ${normalizedTicket.notasGenerales ? `<div class="notes">Nota general: ${escapeHtml(normalizedTicket.notasGenerales)}</div>` : ''}
      <div class="footer">Impreso ${formatTicketTime(new Date())}</div>
    </div>
  </body>
</html>`;
}

export function printKitchenTicket(ticket) {
  const iframe = document.createElement('iframe');
  iframe.style.position = 'fixed';
  iframe.style.left = '-9999px';
  iframe.style.top = '0';
  iframe.style.width = '80mm';
  iframe.style.height = '120mm';
  iframe.style.border = '0';
  iframe.style.visibility = 'hidden';
  iframe.setAttribute('aria-hidden', 'true');

  const cleanup = () => {
    if (iframe.parentNode) {
      iframe.parentNode.removeChild(iframe);
    }
  };

  iframe.onload = () => {
    const win = iframe.contentWindow;
    if (!win) {
      cleanup();
      return;
    }

    const runPrint = () => {
      win.focus();
      win.print();
      win.addEventListener('afterprint', cleanup);
      window.setTimeout(cleanup, 5000);
    };

    win.requestAnimationFrame(() => {
      win.requestAnimationFrame(runPrint);
    });
  };

  document.body.appendChild(iframe);
  const doc = iframe.contentDocument || iframe.contentWindow.document;
  doc.open();
  doc.write(buildKitchenTicketHtml(ticket));
  doc.close();
}
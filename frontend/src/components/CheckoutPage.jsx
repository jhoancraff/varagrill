import { useCallback, useEffect, useMemo, useState } from 'react';

const METODOS_PAGO = [
  { key: 'efectivo', label: 'Efectivo' },
  { key: 'tarjeta', label: 'Tarjeta' },
  { key: 'transferencia', label: 'Transferencia' },
  { key: 'pago_movil', label: 'Pago móvil' },
];

function CheckoutPage({ isMobile, onBack, lastKitchenEvent }) {
  const [pedidos, setPedidos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedByGroup, setSelectedByGroup] = useState({});
  const [metodoByGroup, setMetodoByGroup] = useState({});
  const [checkingOutGroup, setCheckingOutGroup] = useState('');
  const [feedback, setFeedback] = useState('');
  const [feedbackType, setFeedbackType] = useState('success');
  const [expandedOrderIds, setExpandedOrderIds] = useState(() => new Set());

  const toggleExpanded = (pedidoId) => {
    setExpandedOrderIds((current) => {
      const next = new Set(current);
      if (next.has(pedidoId)) {
        next.delete(pedidoId);
      } else {
        next.add(pedidoId);
      }
      return next;
    });
  };

  const fetchPedidos = useCallback(async () => {
    try {
      const response = await fetch('/api/pedidos/cobro/', {
        credentials: 'include',
        cache: 'no-store',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setError(data.message || 'No se pudieron cargar los pedidos listos para cobrar.');
        return;
      }
      setPedidos(Array.isArray(data.pedidos) ? data.pedidos : []);
      setError('');
    } catch (requestError) {
      setError('Error de red al cargar los pedidos para cobrar.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    fetchPedidos();

    const intervalId = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        fetchPedidos();
      }
    }, 15000);

    return () => window.clearInterval(intervalId);
  }, [fetchPedidos]);

  useEffect(() => {
    if (lastKitchenEvent) {
      fetchPedidos();
    }
  }, [lastKitchenEvent, fetchPedidos]);

  const groups = useMemo(() => {
    const map = new Map();
    pedidos.forEach((pedido) => {
      const key = pedido.mesa ? `mesa-${pedido.mesa}` : `pedido-${pedido.id}`;
      const label = pedido.mesa
        ? `Mesa ${pedido.mesa}`
        : `${pedido.tipo_pedido === 'delivery' ? 'Delivery' : 'Para llevar'} · Pedido #${pedido.id}`;
      if (!map.has(key)) {
        map.set(key, { key, label, pedidos: [] });
      }
      map.get(key).pedidos.push(pedido);
    });
    return Array.from(map.values());
  }, [pedidos]);

  const toggleSelection = (groupKey, pedidoId) => {
    setSelectedByGroup((current) => {
      const groupSet = new Set(current[groupKey] || []);
      if (groupSet.has(pedidoId)) {
        groupSet.delete(pedidoId);
      } else {
        groupSet.add(pedidoId);
      }
      return { ...current, [groupKey]: groupSet };
    });
  };

  const handleCheckout = async (group) => {
    const selectedIds = Array.from(selectedByGroup[group.key] || []);
    if (selectedIds.length === 0) {
      return;
    }
    const metodoPago = metodoByGroup[group.key] || 'efectivo';

    setCheckingOutGroup(group.key);
    setFeedback('');
    try {
      const response = await fetch('/api/pedidos/cobro/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken') || '',
        },
        credentials: 'include',
        body: JSON.stringify({ pedido_ids: selectedIds, metodo_pago: metodoPago }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setFeedbackType('error');
        setFeedback(data.message || 'No se pudo procesar el cobro.');
        await fetchPedidos();
        return;
      }

      setFeedbackType('success');
      setFeedback(
        `Cobro registrado: $${data.factura.total} (${data.factura.pedidos.length} pedido(s)). Referencia ${data.factura.referencia}.`,
      );
      setSelectedByGroup((current) => {
        const copy = { ...current };
        delete copy[group.key];
        return copy;
      });
      await fetchPedidos();
    } catch (requestError) {
      setFeedbackType('error');
      setFeedback('Error de red al procesar el cobro.');
    } finally {
      setCheckingOutGroup('');
    }
  };

  return (
    <section style={containerStyle(isMobile)}>
      <div style={headerWrapStyle(isMobile)}>
        <div>
          <div style={eyebrowStyle}>Cobro</div>
          <h2 style={titleStyle(isMobile)}>Pedidos listos para cobrar</h2>
          <p style={subtitleStyle}>
            Agrupados por mesa. Marca uno o varios pedidos de la misma mesa para unificarlos en un solo cobro.
          </p>
        </div>
        <button type="button" onClick={onBack} style={backButtonStyle(isMobile)}>
          Volver
        </button>
      </div>

      {feedback ? <div style={feedbackStyle(feedbackType)}>{feedback}</div> : null}

      {loading ? <div style={emptyStateStyle}>Cargando pedidos...</div> : null}
      {!loading && error ? <div style={errorStyle}>{error}</div> : null}

      {!loading && !error && groups.length === 0 ? (
        <div style={emptyStateStyle}>No hay pedidos listos para cobrar en este momento.</div>
      ) : null}

      {!loading && !error && groups.length > 0 ? (
        <div style={groupsGridStyle(isMobile)}>
          {groups.map((group) => {
            const selectedSet = selectedByGroup[group.key] || new Set();
            const selectedTotal = group.pedidos
              .filter((pedido) => selectedSet.has(pedido.id))
              .reduce((sum, pedido) => sum + Number(pedido.total), 0);

            return (
              <article key={group.key} style={groupCardStyle}>
                <div style={groupHeaderStyle}>
                  <div style={{ color: '#fff', fontWeight: 700, fontSize: 17 }}>{group.label}</div>
                  <span style={groupCountStyle}>{group.pedidos.length} pedido(s)</span>
                </div>

                <div style={{ display: 'grid', gap: 8 }}>
                  {group.pedidos.map((pedido) => {
                    const isExpanded = expandedOrderIds.has(pedido.id);
                    const items = Array.isArray(pedido.items) ? pedido.items : [];
                    const itemsWithNotes = items.filter((item) => item.notas);

                    return (
                      <div key={pedido.id} style={orderCardStyle}>
                        <div style={orderRowStyle}>
                          <input
                            type="checkbox"
                            checked={selectedSet.has(pedido.id)}
                            onChange={() => toggleSelection(group.key, pedido.id)}
                          />
                          <span style={{ flex: 1, minWidth: 0 }}>
                            <span style={{ color: '#fff', fontWeight: 600 }}>Pedido #{pedido.id}</span>
                            <span style={{ color: '#d2c4c4', fontSize: 12, marginLeft: 8 }}>
                              {pedido.cliente || 'Sin cliente'} · {pedido.mesero} · {formatOrderTime(pedido.creado_en)}
                            </span>
                          </span>
                          <span style={{ color: '#ffcf7d', fontWeight: 700 }}>${pedido.total}</span>
                          <button type="button" onClick={() => toggleExpanded(pedido.id)} style={detailToggleStyle}>
                            {isExpanded ? 'Ocultar' : 'Detalle'}
                          </button>
                        </div>

                        {isExpanded ? (
                          <div style={orderDetailStyle}>
                            <div style={detailMetaRowStyle}>
                              <span>{tipoPedidoLabel(pedido.tipo_pedido)}</span>
                              {pedido.mesa ? <span>Mesa {pedido.mesa}</span> : null}
                              <span>Pedido tomado a las {formatOrderTime(pedido.creado_en)}</span>
                            </div>

                            {pedido.notas ? (
                              <div style={detailNoteStyle}>Nota general: {pedido.notas}</div>
                            ) : null}

                            <div style={{ display: 'grid', gap: 4 }}>
                              {items.map((item) => (
                                <div key={item.id} style={detailItemRowStyle}>
                                  <span style={{ color: '#fff' }}>{item.cantidad}x {item.producto}</span>
                                  <span style={{ color: '#d2c4c4' }}>${item.precio_unitario} c/u</span>
                                  <span style={{ color: '#ffcf7d', fontWeight: 700 }}>
                                    ${(Number(item.precio_unitario) * item.cantidad).toFixed(2)}
                                  </span>
                                </div>
                              ))}
                            </div>

                            {itemsWithNotes.length > 0 ? (
                              <div style={{ display: 'grid', gap: 2 }}>
                                {itemsWithNotes.map((item) => (
                                  <div key={`note-${item.id}`} style={itemNoteDetailStyle}>
                                    {item.producto}: {item.notas}
                                  </div>
                                ))}
                              </div>
                            ) : null}

                            <div style={detailTotalsStyle}>
                              <span>Subtotal: ${pedido.subtotal}</span>
                              {Number(pedido.impuesto) > 0 ? <span>Impuesto: ${pedido.impuesto}</span> : null}
                              {Number(pedido.descuento) > 0 ? <span>Descuento: -${pedido.descuento}</span> : null}
                              {Number(pedido.propina) > 0 ? <span>Propina: ${pedido.propina}</span> : null}
                              <span style={{ fontWeight: 800, color: '#fff' }}>Total: ${pedido.total}</span>
                            </div>
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                </div>

                <div style={groupFooterStyle(isMobile)}>
                  <div style={{ color: '#fff', fontWeight: 700 }}>
                    Total seleccionado: ${selectedTotal.toFixed(2)}
                  </div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                    <select
                      value={metodoByGroup[group.key] || 'efectivo'}
                      onChange={(event) => setMetodoByGroup((current) => ({ ...current, [group.key]: event.target.value }))}
                      style={selectStyle}
                    >
                      {METODOS_PAGO.map((metodo) => (
                        <option key={metodo.key} value={metodo.key}>{metodo.label}</option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={() => handleCheckout(group)}
                      style={checkoutButtonStyle}
                      disabled={selectedSet.size === 0 || checkingOutGroup === group.key}
                    >
                      {checkingOutGroup === group.key ? 'Procesando...' : 'Cobrar seleccionados'}
                    </button>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}

function getCookie(name) {
  const all = `; ${document.cookie}`;
  const parts = all.split(`; ${name}=`);
  if (parts.length === 2) {
    return parts.pop().split(';').shift();
  }
  return '';
}

function formatOrderTime(createdAt) {
  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  return date.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
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

const containerStyle = (isMobile) => ({
  display: 'grid',
  gap: 16,
  padding: isMobile ? 4 : 8,
});

const headerWrapStyle = (isMobile) => ({
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: isMobile ? 'flex-start' : 'center',
  flexDirection: isMobile ? 'column' : 'row',
  gap: 12,
});

const eyebrowStyle = {
  fontSize: 12,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
  color: '#f7a5a5',
  marginBottom: 8,
};

const titleStyle = (isMobile) => ({
  margin: 0,
  color: '#fff',
  fontSize: isMobile ? 26 : 32,
  fontWeight: 700,
});

const subtitleStyle = {
  margin: '8px 0 0',
  color: '#d2c3c3',
  lineHeight: 1.6,
  maxWidth: 640,
};

const backButtonStyle = (isMobile) => ({
  border: '1px solid rgba(255, 115, 115, 0.34)',
  borderRadius: 999,
  padding: isMobile ? '11px 16px' : '10px 16px',
  background: 'rgba(255,255,255,0.03)',
  color: '#fff',
  fontWeight: 600,
  cursor: 'pointer',
  width: isMobile ? '100%' : 'auto',
});

const emptyStateStyle = {
  minHeight: 100,
  display: 'grid',
  placeItems: 'center',
  borderRadius: 24,
  border: '1px dashed rgba(255, 255, 255, 0.14)',
  background: 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)',
  color: '#c8bbbb',
  textAlign: 'center',
  padding: 20,
};

const errorStyle = {
  padding: '12px 14px',
  borderRadius: 16,
  border: '1px solid rgba(255, 145, 145, 0.22)',
  background: 'rgba(255, 98, 98, 0.12)',
  color: '#ffd8d8',
};

const feedbackStyle = (feedbackType) => ({
  borderRadius: 12,
  border: feedbackType === 'error' ? '1px solid rgba(223, 102, 102, 0.5)' : '1px solid rgba(82, 206, 123, 0.35)',
  background: feedbackType === 'error' ? 'rgba(102, 29, 29, 0.55)' : 'rgba(31, 89, 48, 0.45)',
  color: feedbackType === 'error' ? '#ffe2e2' : '#dbffe4',
  padding: '10px 12px',
  fontSize: 13,
});

const groupsGridStyle = (isMobile) => ({
  display: 'grid',
  gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fill, minmax(320px, 1fr))',
  gap: 14,
});

const groupCardStyle = {
  display: 'grid',
  gap: 12,
  padding: '18px 18px',
  borderRadius: 20,
  background: 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)',
  border: '1px solid rgba(255, 255, 255, 0.1)',
  boxShadow: '0 12px 28px rgba(0,0,0,0.24)',
};

const groupHeaderStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 10,
};

const groupCountStyle = {
  padding: '4px 10px',
  borderRadius: 999,
  background: 'rgba(255, 255, 255, 0.08)',
  color: '#ffb0b0',
  fontSize: 12,
  fontWeight: 700,
};

const orderCardStyle = {
  borderRadius: 12,
  border: '1px solid rgba(255, 255, 255, 0.08)',
  background: 'rgba(255, 255, 255, 0.03)',
  overflow: 'hidden',
};

const orderRowStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  padding: '10px 12px',
};

const detailToggleStyle = {
  border: '1px solid rgba(255, 255, 255, 0.16)',
  borderRadius: 999,
  padding: '5px 12px',
  background: 'rgba(255, 255, 255, 0.05)',
  color: '#fff',
  fontSize: 12,
  fontWeight: 700,
  cursor: 'pointer',
  flexShrink: 0,
};

const orderDetailStyle = {
  display: 'grid',
  gap: 8,
  padding: '4px 12px 14px',
  borderTop: '1px solid rgba(255, 255, 255, 0.06)',
};

const detailMetaRowStyle = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 12,
  color: '#d2c4c4',
  fontSize: 12,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
};

const detailNoteStyle = {
  padding: '8px 10px',
  borderRadius: 10,
  background: 'rgba(255, 145, 145, 0.1)',
  border: '1px solid rgba(255, 145, 145, 0.2)',
  color: '#ffd8d8',
  fontSize: 13,
};

const detailItemRowStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  gap: 10,
  fontSize: 13,
  padding: '4px 0',
};

const itemNoteDetailStyle = {
  color: '#e8bcbc',
  fontSize: 12,
  fontStyle: 'italic',
};

const detailTotalsStyle = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 14,
  paddingTop: 8,
  borderTop: '1px solid rgba(255, 255, 255, 0.06)',
  color: '#d2c4c4',
  fontSize: 13,
};

const groupFooterStyle = (isMobile) => ({
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: isMobile ? 'flex-start' : 'center',
  flexDirection: isMobile ? 'column' : 'row',
  gap: 10,
  paddingTop: 10,
  borderTop: '1px solid rgba(255, 255, 255, 0.08)',
});

const selectStyle = {
  borderRadius: 12,
  border: '1px solid rgba(255, 255, 255, 0.14)',
  background: '#161010',
  padding: '9px 10px',
  color: '#fff4f4',
  fontSize: 13,
};

const checkoutButtonStyle = {
  border: 'none',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'linear-gradient(90deg, #1f7a3f 0%, #34d399 100%)',
  color: '#04140a',
  fontWeight: 800,
  cursor: 'pointer',
};

export default CheckoutPage;

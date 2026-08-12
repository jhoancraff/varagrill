import { useCallback, useEffect, useMemo, useState } from 'react';

const ACTIVE_FILTER = 'activos';
const ALL_FILTER = 'todos';

const statusColumns = [
  { key: 'pendiente', title: 'Pendientes', accent: '#f59e0b' },
  { key: 'en_preparacion', title: 'En preparación', accent: '#38bdf8' },
  { key: 'listo', title: 'Listos', accent: '#34d399' },
];

const nextActionsByState = {
  pendiente: [{ next: 'en_preparacion', label: 'Iniciar preparación' }],
  en_preparacion: [{ next: 'listo', label: 'Marcar listo' }],
  listo: [
    { next: 'en_preparacion', label: 'Volver a preparar' },
    { next: 'entregado', label: 'Entregado' },
  ],
};

function KitchenOrdersPage({
  isMobile,
  onBack,
  isSocketConnected,
  alertPermission,
  onRequestPermission,
  lastKitchenEvent,
  onEditOrder,
}) {
  const [orders, setOrders] = useState([]);
  const [counts, setCounts] = useState({ pendiente: 0, en_preparacion: 0, listo: 0 });
  const [loading, setLoading] = useState(true);
  const [updatingMap, setUpdatingMap] = useState({});
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState(ACTIVE_FILTER);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [mobileColumn, setMobileColumn] = useState('pendiente');

  const fetchOrders = useCallback(async (controller) => {
    try {
      const response = await fetch(`/api/pedidos/cocina/?estado=${statusFilter}&limit=120`, {
        method: 'GET',
        credentials: 'include',
        cache: 'no-store',
        signal: controller?.signal,
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setError(data.message || 'No se pudieron cargar los pedidos de cocina.');
        return;
      }

      setOrders(Array.isArray(data.orders) ? data.orders : []);
      setCounts(data.counts || { pendiente: 0, en_preparacion: 0, listo: 0 });
      setLastUpdate(new Date());
      setError('');
    } catch (requestError) {
      if (requestError?.name !== 'AbortError') {
        setError('Error de red al cargar pedidos de cocina.');
      }
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  // Alerts (sound/notification/vibration) and the socket connection now live
  // in the parent (WelcomeScreen) so they keep working from any view, not
  // just while this board is mounted. This effect just reacts to events the
  // parent already received and forwards to us via `lastKitchenEvent`.
  useEffect(() => {
    if (!lastKitchenEvent) {
      return;
    }
    fetchOrders();
  }, [lastKitchenEvent, fetchOrders]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    fetchOrders(controller);

    const intervalId = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        fetchOrders(controller);
      }
    }, 12000);

    return () => {
      controller.abort();
      window.clearInterval(intervalId);
    };
  }, [fetchOrders]);

  const groupedOrders = useMemo(() => {
    return statusColumns.reduce((accumulator, column) => {
      accumulator[column.key] = orders.filter((order) => order.estado === column.key);
      return accumulator;
    }, {});
  }, [orders]);

  const visibleColumns = useMemo(
    () => (isMobile ? statusColumns.filter((column) => column.key === mobileColumn) : statusColumns),
    [isMobile, mobileColumn],
  );

  const handleUpdateOrderState = async (orderId, nextState) => {
    if (updatingMap[orderId]) {
      return;
    }

    setUpdatingMap((current) => ({ ...current, [orderId]: true }));
    setError('');

    try {
      const response = await fetch(`/api/pedidos/${orderId}/estado/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken') || '',
        },
        credentials: 'include',
        body: JSON.stringify({ estado: nextState }),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setError(data.message || 'No se pudo actualizar el estado del pedido.');
        return;
      }

      setOrders((current) => {
        if (nextState === 'entregado' && statusFilter === ACTIVE_FILTER) {
          return current.filter((order) => order.id !== orderId);
        }

        return current.map((order) => {
          if (order.id !== orderId) {
            return order;
          }
          return { ...order, estado: nextState };
        });
      });

      setCounts((current) => {
        const draft = { ...current };
        const currentOrder = orders.find((order) => order.id === orderId);

        if (currentOrder && draft[currentOrder.estado] > 0) {
          draft[currentOrder.estado] -= 1;
        }

        if (nextState in draft) {
          draft[nextState] += 1;
        }

        return draft;
      });
    } catch (requestError) {
      setError('No se pudo contactar al servidor para actualizar el pedido.');
    } finally {
      setUpdatingMap((current) => {
        const copy = { ...current };
        delete copy[orderId];
        return copy;
      });
    }
  };

  return (
    <section style={containerStyle(isMobile)}>
      <div style={headerWrapStyle}>
        <div>
          <div style={eyebrowStyle}>Panel de cocina</div>
          <h2 style={titleStyle(isMobile)}>Pedidos en preparación</h2>
          <p style={subtitleStyle}>Vista optimizada para producción en tiempo real.</p>
        </div>

        <div style={headerActionsStyle(isMobile)}>
          <button
            type="button"
            onClick={() => setStatusFilter(ACTIVE_FILTER)}
            style={filterChipStyle(statusFilter === ACTIVE_FILTER, isMobile)}
          >
            Activos
          </button>
          <button
            type="button"
            onClick={() => setStatusFilter(ALL_FILTER)}
            style={filterChipStyle(statusFilter === ALL_FILTER, isMobile)}
          >
            Historial corto
          </button>
          <button type="button" onClick={onBack} style={backButtonStyle(isMobile)}>Volver</button>
        </div>
      </div>

      <div style={alertPanelStyle(isMobile)}>
        <div style={{ display: 'grid', gap: 4, minWidth: 0 }}>
          <div style={{ color: '#fff', fontWeight: 700 }}>Alertas de cocina</div>
          <div style={{ color: '#d6d6d6', fontSize: 12 }}>
            {alertPermission === 'granted'
              ? 'Recibirás una notificación cuando llegue un pedido nuevo.'
              : 'Activa las notificaciones para enterarte de pedidos nuevos aunque tengas otra pestaña abierta.'}
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {alertPermission !== 'granted' ? (
            <button type="button" onClick={onRequestPermission} style={primaryAlertButtonStyle(isMobile)}>
              Activar notificaciones
            </button>
          ) : null}
          <button type="button" onClick={() => fetchOrders()} style={secondaryAlertButtonStyle(isMobile)}>Actualizar</button>
        </div>
      </div>

      <div style={statusSummaryStyle(isMobile)}>
        <div>Pendientes: {counts.pendiente || 0}</div>
        <div>En preparación: {counts.en_preparacion || 0}</div>
        <div>Listos: {counts.listo || 0}</div>
        <div>WebSocket: {isSocketConnected ? 'Conectado' : 'Reconectando'}</div>
      </div>

      {lastUpdate && (
        <div style={{ color: '#d3cfcf', fontSize: 12 }}>
          Última actualización: {lastUpdate.toLocaleTimeString('es-ES')}
        </div>
      )}

      {loading && <div style={emptyStateStyle}>Cargando pedidos de cocina...</div>}
      {!loading && error && <div style={errorStyle}>{error}</div>}

      {!loading && !error && isMobile && (
        <div style={mobileColumnTabsWrapStyle}>
          {statusColumns.map((column) => (
            <button
              key={column.key}
              type="button"
              onClick={() => setMobileColumn(column.key)}
              style={mobileColumnTabStyle(mobileColumn === column.key, column.accent)}
            >
              {column.title} ({groupedOrders[column.key].length})
            </button>
          ))}
        </div>
      )}

      {!loading && !error && (
        <div style={columnsGridStyle(isMobile)}>
          {visibleColumns.map((column) => (
            <section key={column.key} style={columnStyle(column.accent)}>
              <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                <h3 style={{ margin: 0, color: '#fff', fontSize: 16 }}>{column.title}</h3>
                <span style={counterStyle}>{groupedOrders[column.key].length}</span>
              </header>

              {groupedOrders[column.key].length === 0 ? (
                <div style={columnEmptyStyle}>Sin pedidos en esta columna.</div>
              ) : (
                <div style={{ display: 'grid', gap: 10 }}>
                  {groupedOrders[column.key].map((order) => (
                    <article key={order.id} style={cardStyle}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                        <div>
                          <div style={{ color: '#fff', fontWeight: 700 }}>Pedido #{order.id}</div>
                          <div style={{ color: '#f3cfcf', fontSize: 12, marginTop: 4 }}>
                            {order.mesa ? `Mesa ${order.mesa}` : 'Sin mesa'} · {order.tipo_pedido}
                          </div>
                        </div>
                        <div style={timeBadgeStyle(order.creado_en)}>{formatElapsedTime(order.creado_en)}</div>
                      </div>

                      <div style={{ marginTop: 10, display: 'grid', gap: 6 }}>
                        {groupItemsByPlato(order.items).platos.map(({ grupoId, items }) => (
                          <div key={`plato-${grupoId}`} style={platoGroupStyle}>
                            <div style={platoGroupTitleStyle}>Plato {grupoId}</div>
                            {items.map((item) => renderKitchenItem(item))}
                          </div>
                        ))}
                        {groupItemsByPlato(order.items).sueltos.map((item) => renderKitchenItem(item))}
                      </div>

                      {!!order.notas && <p style={orderNoteStyle}>Nota general: {order.notas}</p>}

                      {(order.estado === 'pendiente' || (nextActionsByState[order.estado] || []).length > 0) && (
                        <div style={actionsWrapStyle(isMobile)}>
                          {order.estado === 'pendiente' && onEditOrder ? (
                            <button
                              type="button"
                              onClick={() => onEditOrder(order.id)}
                              style={editButtonStyle(isMobile)}
                            >
                              Editar pedido
                            </button>
                          ) : null}
                          {(nextActionsByState[order.estado] || []).map((action) => (
                            <button
                              key={action.next}
                              type="button"
                              onClick={() => handleUpdateOrderState(order.id, action.next)}
                              style={actionButtonStyle(action.next, isMobile)}
                              disabled={Boolean(updatingMap[order.id])}
                            >
                              {updatingMap[order.id] ? 'Actualizando...' : action.label}
                            </button>
                          ))}
                        </div>
                      )}
                    </article>
                  ))}
                </div>
              )}
            </section>
          ))}
        </div>
      )}
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

function groupItemsByPlato(items) {
  const grupos = new Map();
  const sueltos = [];
  (items || []).forEach((item) => {
    if (item.grupo_armado) {
      if (!grupos.has(item.grupo_armado)) {
        grupos.set(item.grupo_armado, []);
      }
      grupos.get(item.grupo_armado).push(item);
    } else {
      sueltos.push(item);
    }
  });
  const platos = Array.from(grupos.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([grupoId, groupedItems]) => ({ grupoId, items: groupedItems }));
  return { platos, sueltos };
}

function renderKitchenItem(item) {
  return (
    <div key={item.id} style={itemRowStyle}>
      <span style={{ color: '#fff' }}>{item.peso_gramos ? `${item.peso_gramos} g` : `${item.cantidad}x`} {item.producto}</span>
      {!!item.notas && <span style={itemNoteStyle}>{item.notas}</span>}
      {(item.adicionales || []).map((addon) => (
        <span key={addon.id} style={itemAddonStyle}>+ {addon.cantidad}x {addon.nombre}</span>
      ))}
      {(item.composicion || []).length > 0 && (
        <span style={itemNoteStyle}>Lleva: {item.composicion.join(', ')}</span>
      )}
    </div>
  );
}

function formatElapsedTime(createdAt) {
  const createdDate = new Date(createdAt);
  const elapsedMs = Date.now() - createdDate.getTime();
  const elapsedMinutes = Math.max(0, Math.floor(elapsedMs / 60000));

  if (elapsedMinutes < 1) {
    return 'Ahora';
  }
  if (elapsedMinutes < 60) {
    return `${elapsedMinutes} min`;
  }

  const hours = Math.floor(elapsedMinutes / 60);
  const minutes = elapsedMinutes % 60;
  return `${hours}h ${minutes}m`;
}

const containerStyle = (isMobile) => ({
  background: 'linear-gradient(180deg, rgba(18, 8, 8, 0.96) 0%, rgba(8, 8, 8, 0.98) 100%)',
  border: '1px solid rgba(255, 95, 95, 0.18)',
  borderRadius: 24,
  padding: isMobile ? 14 : 20,
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.05), 0 14px 30px rgba(0,0,0,0.32)',
  display: 'grid',
  gap: 14,
});

const headerWrapStyle = {
  display: 'flex',
  alignItems: 'flex-start',
  justifyContent: 'space-between',
  gap: 12,
  flexWrap: 'wrap',
};

const eyebrowStyle = {
  color: '#f7a5a5',
  fontSize: 12,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
};

const titleStyle = (isMobile) => ({
  margin: '8px 0 0',
  color: '#fff',
  fontSize: isMobile ? 24 : 30,
  lineHeight: 1.15,
});

const subtitleStyle = {
  margin: '8px 0 0',
  color: '#c6c6c6',
  fontSize: 14,
};

const headerActionsStyle = (isMobile) => ({
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  flexWrap: 'wrap',
  width: isMobile ? '100%' : 'auto',
});

const filterChipStyle = (active, isMobile) => ({
  border: active ? '1px solid rgba(255, 106, 106, 0.6)' : '1px solid rgba(255,255,255,0.16)',
  borderRadius: 999,
  padding: isMobile ? '10px 14px' : '8px 14px',
  background: active ? 'rgba(191, 31, 31, 0.28)' : 'rgba(255,255,255,0.03)',
  color: '#fff',
  fontWeight: 600,
  cursor: 'pointer',
  minHeight: isMobile ? 42 : 38,
  flex: isMobile ? '1 1 0' : '0 0 auto',
});

const backButtonStyle = (isMobile) => ({
  border: '1px solid rgba(255, 115, 115, 0.34)',
  borderRadius: 999,
  padding: isMobile ? '10px 14px' : '9px 14px',
  background: 'rgba(255,255,255,0.03)',
  color: '#fff',
  fontWeight: 600,
  cursor: 'pointer',
  minHeight: isMobile ? 42 : 38,
  width: isMobile ? '100%' : 'auto',
});

const alertPanelStyle = (isMobile) => ({
  border: '1px solid rgba(255, 107, 107, 0.35)',
  borderRadius: 16,
  background: 'linear-gradient(90deg, rgba(191, 31, 31, 0.24) 0%, rgba(255, 255, 255, 0.05) 100%)',
  color: '#fff',
  padding: isMobile ? '12px 12px 10px' : '12px 14px',
  display: 'flex',
  alignItems: 'flex-start',
  justifyContent: 'space-between',
  gap: 10,
  flexWrap: 'wrap',
  flexDirection: isMobile ? 'column' : 'row',
});

const primaryAlertButtonStyle = (isMobile) => ({
  border: 'none',
  borderRadius: 999,
  padding: isMobile ? '10px 14px' : '8px 12px',
  background: 'linear-gradient(90deg, #ff5d5d 0%, #ff8a00 100%)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
  minHeight: isMobile ? 44 : 36,
});

const secondaryAlertButtonStyle = (isMobile) => ({
  border: '1px solid rgba(255,255,255,0.2)',
  borderRadius: 999,
  padding: isMobile ? '10px 12px' : '8px 12px',
  background: 'rgba(255,255,255,0.06)',
  color: '#fff',
  cursor: 'pointer',
  minHeight: isMobile ? 44 : 36,
});

const statusSummaryStyle = (isMobile) => ({
  border: '1px solid rgba(255,255,255,0.14)',
  borderRadius: 14,
  background: 'rgba(255,255,255,0.03)',
  color: '#fff',
  padding: '10px 12px',
  display: 'flex',
  alignItems: 'center',
  gap: 14,
  flexWrap: 'wrap',
  fontSize: isMobile ? 13 : 14,
});

const refreshButtonStyle = (isMobile) => ({
  border: '1px solid rgba(255,255,255,0.2)',
  borderRadius: 999,
  padding: isMobile ? '9px 12px' : '7px 12px',
  background: 'rgba(255,255,255,0.06)',
  color: '#fff',
  marginLeft: isMobile ? 0 : 'auto',
  cursor: 'pointer',
  minHeight: isMobile ? 40 : 34,
  width: isMobile ? '100%' : 'auto',
});

const mobileColumnTabsWrapStyle = {
  display: 'grid',
  gridTemplateColumns: '1fr',
  gap: 8,
};

const mobileColumnTabStyle = (active, accent) => ({
  border: active ? `1px solid ${accent}` : '1px solid rgba(255,255,255,0.18)',
  borderRadius: 12,
  background: active ? 'rgba(255,255,255,0.09)' : 'rgba(255,255,255,0.03)',
  color: '#fff',
  textAlign: 'left',
  padding: '10px 12px',
  fontWeight: 700,
  cursor: 'pointer',
  minHeight: 42,
});

const columnsGridStyle = (isMobile) => ({
  display: 'grid',
  gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, minmax(0, 1fr))',
  gap: 14,
});

const emptyStateStyle = {
  borderRadius: 16,
  border: '1px dashed rgba(255,255,255,0.28)',
  padding: '18px 14px',
  color: '#d8cfcf',
};

const errorStyle = {
  borderRadius: 14,
  border: '1px solid rgba(223, 102, 102, 0.5)',
  background: 'rgba(102, 29, 29, 0.55)',
  color: '#ffe2e2',
  padding: '10px 12px',
  fontSize: 13,
};

const columnStyle = (accent) => ({
  borderRadius: 18,
  border: `1px solid ${accent}55`,
  background: 'rgba(8,8,8,0.5)',
  padding: 12,
});

const counterStyle = {
  borderRadius: 999,
  minWidth: 30,
  minHeight: 24,
  padding: '0 8px',
  display: 'inline-grid',
  placeItems: 'center',
  background: 'rgba(255,255,255,0.08)',
  color: '#fff',
  fontSize: 12,
  fontWeight: 700,
};

const columnEmptyStyle = {
  borderRadius: 14,
  border: '1px dashed rgba(255,255,255,0.2)',
  color: '#d5d5d5',
  fontSize: 13,
  padding: '14px 10px',
};

const cardStyle = {
  borderRadius: 14,
  border: '1px solid rgba(255,255,255,0.12)',
  background: 'rgba(255,255,255,0.03)',
  padding: 11,
};

const actionsWrapStyle = (isMobile) => ({
  display: 'flex',
  flexWrap: 'wrap',
  gap: 8,
  marginTop: 12,
  width: '100%',
  ...(isMobile ? { flexDirection: 'column' } : {}),
});

const itemRowStyle = {
  borderRadius: 10,
  background: 'rgba(255,255,255,0.04)',
  border: '1px solid rgba(255,255,255,0.1)',
  padding: '8px 9px',
  display: 'grid',
  gap: 4,
};

const itemNoteStyle = {
  color: '#e8bcbc',
  fontSize: 12,
};

const itemAddonStyle = {
  color: '#ffcf85',
  fontSize: 12,
  fontWeight: 700,
};

const platoGroupStyle = {
  display: 'grid',
  gap: 4,
  padding: '6px 8px',
  borderRadius: 10,
  border: '1px solid rgba(125, 200, 255, 0.28)',
  background: 'rgba(90, 170, 255, 0.05)',
};

const platoGroupTitleStyle = {
  color: '#bfe0ff',
  fontWeight: 800,
  fontSize: 11,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
};

const orderNoteStyle = {
  margin: '10px 0 0',
  padding: '8px 10px',
  borderRadius: 10,
  background: 'rgba(191, 31, 31, 0.14)',
  color: '#ffdede',
  fontSize: 12,
};

const actionButtonStyle = (nextState, isMobile) => ({
  border: 'none',
  borderRadius: 999,
  padding: isMobile ? '10px 14px' : '8px 12px',
  background: nextState === 'entregado'
    ? 'linear-gradient(90deg, #065f46 0%, #10b981 100%)'
    : 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
  minHeight: isMobile ? 42 : 36,
  width: isMobile ? '100%' : 'auto',
});

const editButtonStyle = (isMobile) => ({
  border: '1px solid rgba(255, 255, 255, 0.2)',
  borderRadius: 999,
  padding: isMobile ? '10px 14px' : '8px 12px',
  background: 'rgba(255, 255, 255, 0.04)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
  minHeight: isMobile ? 42 : 36,
  width: isMobile ? '100%' : 'auto',
});

const timeBadgeStyle = (createdAt) => {
  const elapsedMs = Date.now() - new Date(createdAt).getTime();
  const elapsedMinutes = Math.floor(elapsedMs / 60000);

  const tone = elapsedMinutes >= 30
    ? 'rgba(220, 38, 38, 0.35)'
    : elapsedMinutes >= 15
      ? 'rgba(245, 158, 11, 0.35)'
      : 'rgba(16, 185, 129, 0.35)';

  return {
    borderRadius: 999,
    padding: '5px 9px',
    fontSize: 12,
    color: '#fff',
    border: '1px solid rgba(255,255,255,0.14)',
    background: tone,
  };
};

export default KitchenOrdersPage;
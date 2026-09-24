import { useCallback, useEffect, useMemo, useState } from 'react';
import BsAmount from './BsAmount';
import AjustePedidoModal from './AjustePedidoModal';
import useExchangeRate from '../hooks/useExchangeRate';

const ESTADO_LABELS = {
  pendiente: 'Pendiente',
  en_preparacion: 'En preparación',
  listo: 'Listo',
  entregado: 'Entregado',
  pagado: 'Pagado',
  cancelado: 'Cancelado',
};

const TIPO_LABEL = {
  llevar: 'Para llevar',
  delivery: 'Delivery',
};

function estadoLabel(estado) {
  return ESTADO_LABELS[estado] || estado;
}

function getCookie(name) {
  const all = `; ${document.cookie}`;
  const parts = all.split(`; ${name}=`);
  if (parts.length === 2) {
    return parts.pop().split(';').shift();
  }
  return '';
}

// Espejo de MesasAtendidasPage pero para pedidos 'llevar'/'delivery' (sin mesa,
// ver pedidos_delivery_view en el backend) — mismo patrón de tarjeta → detalle,
// pero agrupado por cliente en vez de por mesa, y sin "cambiar de mesa" (no
// aplica) ni "mover item a otra mesa" (acá solo se puede quitar).
function DeliveryPage({ isMobile, onBack, onAddRoundToDelivery, onNuevoPedido, onEditOrder, sidebarOffset = '0px' }) {
  const tasaCambio = useExchangeRate();
  const [grupos, setGrupos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [lastUpdate, setLastUpdate] = useState(null);
  const [selectedGrupoId, setSelectedGrupoId] = useState(null);
  const [flashMessage, setFlashMessage] = useState('');
  const [prepBusyMap, setPrepBusyMap] = useState({});
  const [reprintBusyMap, setReprintBusyMap] = useState({});
  const [actionError, setActionError] = useState('');
  const [ajusteModal, setAjusteModal] = useState(null); // { pedidoId, item }
  const [ajusteBusy, setAjusteBusy] = useState(false);
  const [ajusteError, setAjusteError] = useState('');

  const fetchGrupos = useCallback(async (controller) => {
    try {
      const response = await fetch('/api/pedidos/delivery/', {
        method: 'GET',
        credentials: 'include',
        cache: 'no-store',
        signal: controller?.signal,
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setError(data.message || 'No se pudieron cargar los pedidos para llevar/delivery.');
        return;
      }

      setGrupos(Array.isArray(data.pedidos_delivery) ? data.pedidos_delivery : []);
      setLastUpdate(new Date());
      setError('');
    } catch (requestError) {
      if (requestError?.name !== 'AbortError') {
        setError('Error de red al cargar los pedidos para llevar/delivery.');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    fetchGrupos(controller);

    const intervalId = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        fetchGrupos(controller);
      }
    }, 15000);

    return () => {
      controller.abort();
      window.clearInterval(intervalId);
    };
  }, [fetchGrupos]);

  useEffect(() => {
    if (!flashMessage) return;
    const timeoutId = window.setTimeout(() => setFlashMessage(''), 6000);
    return () => window.clearTimeout(timeoutId);
  }, [flashMessage]);

  // Se selecciona por grupo_id (el ancla de "Agregar ronda", ver
  // pedidos_delivery_view), no por cliente_id: dos clientes distintos pueden
  // compartir nombre sin cédula y terminar con el mismo cliente_id, pero cada
  // uno con su propio pedido/grupo — usar cliente_id acá abriría el grupo
  // equivocado.
  const selectedGrupo = useMemo(
    () => grupos.find((grupo) => grupo.grupo_id === selectedGrupoId) || null,
    [grupos, selectedGrupoId],
  );

  const handleOpenGrupo = (grupoId) => {
    setSelectedGrupoId(grupoId);
  };

  const handleCloseGrupo = () => {
    setSelectedGrupoId(null);
  };

  const abrirAjuste = (pedidoId, item) => {
    setAjusteError('');
    setAjusteModal({
      pedidoId,
      item: { id: item.id, nombre: item.producto_nombre, cantidad: item.cantidad, esPorPeso: Boolean(item.peso_gramos) },
    });
  };

  // Mismo endpoint y transición que "Iniciar preparación" en MesasAtendidasPage
  // (ver su comentario): es lo que manda a imprimir la comanda y hace que el
  // pedido aparezca en Caja.
  const handleIniciarPreparacion = async (pedidoId) => {
    if (prepBusyMap[pedidoId]) return;
    setPrepBusyMap((current) => ({ ...current, [pedidoId]: true }));
    setActionError('');
    try {
      const response = await fetch(`/api/pedidos/${pedidoId}/estado/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') || '' },
        credentials: 'include',
        body: JSON.stringify({ estado: 'en_preparacion' }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setActionError(data.message || 'No se pudo iniciar la preparación.');
        return;
      }
      await fetchGrupos();
    } catch (requestError) {
      setActionError('Error de red al iniciar la preparación.');
    } finally {
      setPrepBusyMap((current) => ({ ...current, [pedidoId]: false }));
    }
  };

  const handleReimprimirItem = async (pedidoId, detalleId) => {
    const key = `${pedidoId}-${detalleId}`;
    if (reprintBusyMap[key]) return;
    setReprintBusyMap((current) => ({ ...current, [key]: true }));
    setActionError('');
    try {
      const response = await fetch(`/api/pedidos/${pedidoId}/items/${detalleId}/reimprimir/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrftoken') || '' },
        credentials: 'include',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setActionError(data.message || 'No se pudo reimprimir.');
      }
    } catch (requestError) {
      setActionError('Error de red al reimprimir.');
    } finally {
      setReprintBusyMap((current) => ({ ...current, [key]: false }));
    }
  };

  const handleConfirmarEliminar = async ({ motivo, cantidad }) => {
    if (!ajusteModal) return;
    setAjusteBusy(true);
    setAjusteError('');
    try {
      const response = await fetch(`/api/pedidos/${ajusteModal.pedidoId}/items/${ajusteModal.item.id}/eliminar/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') || '' },
        credentials: 'include',
        body: JSON.stringify({ motivo, cantidad }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setAjusteError(data.message || 'No se pudo quitar el item.');
        return;
      }
      setAjusteModal(null);
      await fetchGrupos();
    } catch (requestError) {
      setAjusteError('Error de red al quitar el item.');
    } finally {
      setAjusteBusy(false);
    }
  };

  const grupoTotal = selectedGrupo ? Number(selectedGrupo.total || 0) : 0;

  const handleAddRound = () => {
    if (!selectedGrupo || !onAddRoundToDelivery) {
      return;
    }
    // Prefill con el pedido activo mas reciente del grupo (el ultimo que sigue
    // sin pagar/cancelar) — mismo criterio que handleAddRound en MesasAtendidasPage.
    const activePedido = [...selectedGrupo.pedidos]
      .reverse()
      .find((pedido) => pedido.estado !== 'pagado' && pedido.estado !== 'cancelado');
    onAddRoundToDelivery({
      tipoPedido: (activePedido || selectedGrupo).tipo_pedido || selectedGrupo.tipo_pedido,
      cliente: selectedGrupo.cliente_nombre || '',
      clienteCedula: selectedGrupo.cliente_cedula || '',
      clienteTelefono: selectedGrupo.cliente_telefono || '',
      grupoPedidoId: selectedGrupo.grupo_id,
    });
  };

  if (selectedGrupo) {
    const pedidosPendientes = selectedGrupo.pedidos.filter((pedido) => pedido.estado === 'pendiente');
    const pedidoPendienteUnico = pedidosPendientes.length === 1 ? pedidosPendientes[0] : null;

    return (
      <section style={containerStyle(isMobile)}>
        <div style={scrollAreaWithFooterStyle}>
          <div style={headerWrapStyle}>
            <div>
              <div style={eyebrowStyle}>Delivery / Para llevar</div>
              <h2 style={titleStyle(isMobile)}>{selectedGrupo.cliente_nombre || 'Cliente sin nombre'}</h2>
              <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <span style={tipoBadgeStyle}>{TIPO_LABEL[selectedGrupo.tipo_pedido] || selectedGrupo.tipo_pedido}</span>
                {selectedGrupo.cliente_telefono ? (
                  <span style={telefonoBadgeStyle}>{selectedGrupo.cliente_telefono}</span>
                ) : null}
              </div>
            </div>
            <button type="button" onClick={handleCloseGrupo} style={backButtonStyle(isMobile)}>
              Volver
            </button>
          </div>

          {flashMessage ? <div style={flashBannerStyle}>{flashMessage}</div> : null}
          {error ? <div style={errorStyle}>{error}</div> : null}
          {actionError ? <div style={errorStyle}>{actionError}</div> : null}

          <div style={{ display: 'grid', gap: 10 }}>
            {selectedGrupo.pedidos.map((pedido) => {
              const impreso = pedido.estado !== 'pendiente';
              const items = pedido.detalles || [];
              const puedeAjustarItems = pedido.estado !== 'pagado' && pedido.estado !== 'cancelado' && items.length > 1;

              return (
                <div key={pedido.id} style={pedidoCardStyle}>
                  <div style={pedidoCardHeaderRowStyle}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
                        <div style={{ color: '#fff', fontWeight: 700 }}>Pedido #{pedido.id}</div>
                        <div style={{ color: '#fff', fontWeight: 700 }}>
                          ${Number(pedido.total || 0).toFixed(2)}
                          <BsAmount amountUsd={pedido.total} tasa={tasaCambio} />
                        </div>
                      </div>
                      <div style={{ color: '#d2c3c3', fontSize: 12, marginTop: 4 }}>
                        {estadoLabel(pedido.estado)} · {pedido.mesero}
                      </div>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gap: 6, marginTop: 10 }}>
                    {items.map((item) => (
                      <div key={item.id} style={itemRowStyle(impreso)}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                          <span style={{ color: '#fff', fontWeight: 600 }}>
                            {item.peso_gramos ? `${item.peso_gramos} g` : `${item.cantidad}x`} {item.producto_nombre}
                          </span>
                          <span style={{ color: '#fff', fontWeight: 600 }}>
                            ${Number(item.subtotal || 0).toFixed(2)}
                          </span>
                        </div>
                        {item.notas ? <div style={itemNoteStyle}>{item.notas}</div> : null}
                        {(item.adicionales || []).map((addon) => (
                          <div key={`addon-${addon.id}`} style={itemAddonStyle}>
                            + {addon.cantidad}x {addon.nombre} · ${Number(addon.subtotal || 0).toFixed(2)}
                          </div>
                        ))}
                        {(item.opciones || []).map((opcion) => (
                          <div key={`opcion-${opcion.id}`} style={itemNoteStyle}>
                            {opcion.grupo_nombre}: {opcion.nombre}
                          </div>
                        ))}
                        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginTop: 2 }}>
                          <span style={impresoTagStyle(impreso)}>
                            {impreso ? 'Enviado a cocina' : 'Sin enviar'}
                          </span>
                          {impreso ? (
                            <button
                              type="button"
                              onClick={() => handleReimprimirItem(pedido.id, item.id)}
                              style={reprintItemButtonStyle}
                              disabled={Boolean(reprintBusyMap[`${pedido.id}-${item.id}`])}
                            >
                              {reprintBusyMap[`${pedido.id}-${item.id}`] ? 'Reimprimiendo...' : 'Reimprimir'}
                            </button>
                          ) : null}
                          {puedeAjustarItems ? (
                            <button type="button" onClick={() => abrirAjuste(pedido.id, item)} style={removeItemButtonStyle}>
                              Quitar item
                            </button>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>

                  {pedido.notas ? <p style={orderNoteStyle}>Nota: {pedido.notas}</p> : null}

                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
                    {pedido.estado === 'pendiente' && !pedidoPendienteUnico ? (
                      <button
                        type="button"
                        onClick={() => handleIniciarPreparacion(pedido.id)}
                        style={{ ...iniciarPrepButtonStyle(false), width: 'auto' }}
                        disabled={Boolean(prepBusyMap[pedido.id])}
                      >
                        {prepBusyMap[pedido.id] ? 'Enviando...' : 'Iniciar preparación'}
                      </button>
                    ) : null}
                    {pedido.estado === 'pendiente' && !pedidoPendienteUnico && onEditOrder ? (
                      <button type="button" onClick={() => onEditOrder(pedido.id)} style={{ ...editOrderButtonStyle(false), width: 'auto' }}>
                        Editar
                      </button>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>

          <div style={totalsBoxStyle}>
            <span>Total del cliente</span>
            <strong>
              ${grupoTotal.toFixed(2)}
              <BsAmount amountUsd={grupoTotal} tasa={tasaCambio} />
            </strong>
          </div>
        </div>

        <div style={fixedFooterStyle(sidebarOffset)}>
          <div style={footerActionsRowStyle}>
            {pedidoPendienteUnico ? (
              <button
                type="button"
                onClick={() => handleIniciarPreparacion(pedidoPendienteUnico.id)}
                style={iniciarPrepButtonStyle(isMobile)}
                disabled={Boolean(prepBusyMap[pedidoPendienteUnico.id])}
              >
                {prepBusyMap[pedidoPendienteUnico.id] ? 'Enviando...' : 'Iniciar preparación'}
              </button>
            ) : null}
            {pedidoPendienteUnico && onEditOrder ? (
              <button type="button" onClick={() => onEditOrder(pedidoPendienteUnico.id)} style={editOrderButtonStyle(isMobile)}>
                Editar pedido
              </button>
            ) : null}
            {onAddRoundToDelivery ? (
              <button type="button" onClick={handleAddRound} style={addRoundButtonStyle(isMobile)}>
                Agregar ronda
              </button>
            ) : null}
          </div>
        </div>

        {ajusteModal ? (
          <AjustePedidoModal
            modo="eliminar"
            item={ajusteModal.item}
            busy={ajusteBusy}
            error={ajusteError}
            onClose={() => setAjusteModal(null)}
            onConfirmarEliminar={handleConfirmarEliminar}
          />
        ) : null}
      </section>
    );
  }

  return (
    <section style={containerStyle(isMobile)}>
      <div style={headerWrapStyle}>
        <div>
          <div style={eyebrowStyle}>Delivery / Para llevar</div>
          <h2 style={titleStyle(isMobile)}>Pedidos para llevar y delivery</h2>
        </div>
        <div style={headerActionsStyle(isMobile)}>
          {onNuevoPedido ? (
            <button type="button" onClick={onNuevoPedido} style={newOrderButtonStyle(isMobile)}>
              + Nuevo pedido
            </button>
          ) : null}
          <button type="button" onClick={() => fetchGrupos()} style={secondaryButtonStyle(isMobile)}>
            Actualizar
          </button>
          <button type="button" onClick={onBack} style={backButtonStyle(isMobile)}>
            Volver
          </button>
        </div>
      </div>

      {lastUpdate ? (
        <div style={{ color: '#d3cfcf', fontSize: 12 }}>
          Última actualización: {lastUpdate.toLocaleTimeString('es-ES')}
        </div>
      ) : null}

      {loading && <div style={emptyStateStyle}>Cargando pedidos...</div>}
      {!loading && error && <div style={errorStyle}>{error}</div>}
      {!loading && !error && grupos.length === 0 ? (
        <div style={emptyStateStyle}>No hay pedidos para llevar ni delivery abiertos hoy.</div>
      ) : null}

      {!loading && !error && grupos.length > 0 ? (
        <div style={mesasGridStyle(isMobile)}>
          {grupos.map((grupo) => (
            <button
              key={grupo.grupo_id}
              type="button"
              onClick={() => handleOpenGrupo(grupo.grupo_id)}
              style={grupoCardStyle}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
                <div style={{ color: '#fff', fontWeight: 800, fontSize: 17 }}>{grupo.cliente_nombre || 'Sin nombre'}</div>
                <span style={tipoBadgeStyle}>{TIPO_LABEL[grupo.tipo_pedido] || grupo.tipo_pedido}</span>
              </div>
              {grupo.cliente_telefono ? (
                <div style={{ color: '#c8bbbb', fontSize: 12.5, marginTop: 4 }}>{grupo.cliente_telefono}</div>
              ) : null}
              <div style={{ color: '#d2c3c3', fontSize: 13, marginTop: 6 }}>
                {grupo.pedidos.length} {grupo.pedidos.length === 1 ? 'pedido' : 'pedidos'}
              </div>
              <div style={{ color: '#fff', fontWeight: 700, fontSize: 16, marginTop: 8 }}>
                ${Number(grupo.total || 0).toFixed(2)}
                <BsAmount amountUsd={grupo.total} tasa={tasaCambio} />
              </div>
            </button>
          ))}
        </div>
      ) : null}
    </section>
  );
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

const newOrderButtonStyle = (isMobile) => ({
  border: 'none',
  borderRadius: 999,
  padding: isMobile ? '10px 14px' : '9px 14px',
  background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
  minHeight: isMobile ? 42 : 38,
  width: isMobile ? '100%' : 'auto',
});

const secondaryButtonStyle = (isMobile) => ({
  border: '1px solid rgba(255,255,255,0.2)',
  borderRadius: 999,
  padding: isMobile ? '10px 14px' : '9px 14px',
  background: 'rgba(255,255,255,0.06)',
  color: '#fff',
  fontWeight: 600,
  cursor: 'pointer',
  minHeight: isMobile ? 42 : 38,
  width: isMobile ? '100%' : 'auto',
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

const mesasGridStyle = (isMobile) => ({
  display: 'grid',
  gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fill, minmax(200px, 1fr))',
  gap: 12,
});

const grupoCardStyle = {
  textAlign: 'left',
  border: '1px solid rgba(52, 211, 153, 0.45)',
  background: 'rgba(52, 211, 153, 0.08)',
  borderRadius: 16,
  padding: 14,
  cursor: 'pointer',
  display: 'block',
};

const tipoBadgeStyle = {
  display: 'inline-block',
  borderRadius: 999,
  padding: '3px 10px',
  fontSize: 11,
  fontWeight: 800,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
  color: '#58a6ff',
  background: 'rgba(88, 166, 255, 0.14)',
  border: '1px solid rgba(88, 166, 255, 0.4)',
  whiteSpace: 'nowrap',
};

const telefonoBadgeStyle = {
  display: 'inline-block',
  borderRadius: 999,
  padding: '3px 10px',
  fontSize: 11,
  fontWeight: 700,
  color: '#c8bbbb',
  background: 'rgba(255,255,255,0.06)',
  border: '1px solid rgba(255,255,255,0.14)',
};

const pedidoCardStyle = {
  borderRadius: 14,
  border: '1px solid rgba(255,255,255,0.12)',
  background: 'rgba(255,255,255,0.03)',
  padding: 11,
};

const pedidoCardHeaderRowStyle = {
  display: 'flex',
  gap: 10,
  alignItems: 'flex-start',
};

const totalsBoxStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  borderRadius: 14,
  border: '1px solid rgba(255,255,255,0.16)',
  background: 'rgba(255,255,255,0.04)',
  color: '#fff',
  padding: '12px 14px',
  fontWeight: 800,
  fontSize: 16,
};

const addRoundButtonStyle = (isMobile) => ({
  border: '1px solid rgba(88, 166, 255, 0.5)',
  borderRadius: 999,
  padding: isMobile ? '12px 16px' : '10px 16px',
  background: 'rgba(88, 166, 255, 0.12)',
  color: '#58a6ff',
  fontWeight: 700,
  cursor: 'pointer',
  minHeight: isMobile ? 44 : 40,
  width: isMobile ? '100%' : 'auto',
});

const scrollAreaWithFooterStyle = {
  display: 'grid',
  gap: 14,
  paddingBottom: 200,
};

// `left` sigue a desktopContentOffset (WelcomeScreen.jsx), igual que en
// MesasAtendidasPage — ver su comentario sobre por qué no puede ser 0 fijo.
const fixedFooterStyle = (sidebarOffset) => ({
  position: 'fixed',
  left: sidebarOffset,
  right: 0,
  bottom: 0,
  zIndex: 20,
  padding: 12,
  display: 'grid',
  gap: 8,
  transition: 'left 260ms ease',
  background: 'linear-gradient(180deg, rgba(8,8,8,0) 0%, rgba(8,8,8,0.94) 35%, rgba(6,6,6,0.98) 100%)',
});

const footerActionsRowStyle = {
  display: 'flex',
  gap: 8,
  flexWrap: 'wrap',
};

const flashBannerStyle = {
  borderRadius: 14,
  border: '1px solid rgba(52, 211, 153, 0.4)',
  background: 'rgba(52, 211, 153, 0.12)',
  color: '#a7f3d3',
  padding: '10px 12px',
  fontSize: 13,
  fontWeight: 600,
};

const iniciarPrepButtonStyle = (isMobile) => ({
  border: 'none',
  borderRadius: 999,
  padding: isMobile ? '12px 16px' : '10px 16px',
  background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
  fontSize: 13,
  minHeight: isMobile ? 44 : 40,
  width: isMobile ? '100%' : 'auto',
});

const editOrderButtonStyle = (isMobile) => ({
  border: '1px solid rgba(255,255,255,0.2)',
  borderRadius: 999,
  padding: isMobile ? '12px 16px' : '10px 16px',
  background: 'rgba(255,255,255,0.06)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
  fontSize: 13,
  minHeight: isMobile ? 44 : 40,
  width: isMobile ? '100%' : 'auto',
});

const reprintItemButtonStyle = {
  justifySelf: 'start',
  border: '1px solid rgba(88, 166, 255, 0.45)',
  borderRadius: 999,
  padding: '4px 10px',
  background: 'rgba(88, 166, 255, 0.1)',
  color: '#bcdcff',
  fontSize: 11,
  fontWeight: 700,
  cursor: 'pointer',
};

const impresoTagStyle = (impreso) => ({
  display: 'inline-block',
  borderRadius: 999,
  padding: '2px 8px',
  fontSize: 10,
  fontWeight: 800,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
  color: impreso ? '#34d399' : '#f59e0b',
  background: impreso ? 'rgba(52, 211, 153, 0.14)' : 'rgba(245, 158, 11, 0.14)',
  border: `1px solid ${impreso ? 'rgba(52, 211, 153, 0.4)' : 'rgba(245, 158, 11, 0.45)'}`,
});

const itemRowStyle = (impreso) => ({
  borderRadius: 10,
  background: impreso ? 'rgba(52, 211, 153, 0.06)' : 'rgba(245, 158, 11, 0.08)',
  border: `1px solid ${impreso ? 'rgba(52, 211, 153, 0.3)' : 'rgba(245, 158, 11, 0.35)'}`,
  padding: '8px 9px',
  display: 'grid',
  gap: 4,
});

const itemNoteStyle = {
  color: '#e8bcbc',
  fontSize: 12,
};

const itemAddonStyle = {
  color: '#ffcf85',
  fontSize: 12,
  fontWeight: 700,
};

const removeItemButtonStyle = {
  justifySelf: 'start',
  marginTop: 2,
  border: '1px solid rgba(255, 102, 102, 0.45)',
  borderRadius: 999,
  padding: '4px 10px',
  background: 'rgba(255, 73, 73, 0.1)',
  color: '#ffb3b3',
  fontSize: 11,
  fontWeight: 700,
  cursor: 'pointer',
};

const orderNoteStyle = {
  margin: '10px 0 0',
  padding: '8px 10px',
  borderRadius: 10,
  background: 'rgba(191, 31, 31, 0.14)',
  color: '#ffdede',
  fontSize: 12,
};

export default DeliveryPage;

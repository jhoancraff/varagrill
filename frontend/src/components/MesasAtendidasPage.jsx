import { useCallback, useEffect, useMemo, useState } from 'react';
import BsAmount from './BsAmount';
import useExchangeRate from '../hooks/useExchangeRate';
import useMobileBackHandler from '../hooks/useMobileBackHandler';

const ESTADO_LABELS = {
  pendiente: 'Pendiente',
  en_preparacion: 'En preparación',
  listo: 'Listo',
  entregado: 'Entregado',
  pagado: 'Pagado',
  cancelado: 'Cancelado',
};

function estadoLabel(estado) {
  return ESTADO_LABELS[estado] || estado;
}

function MesasAtendidasPage({ isMobile, onBack, onAddRoundToTable, onNuevoPedido, mesasCatalogo = [], canGestionarItems = false }) {
  const tasaCambio = useExchangeRate();
  const [mesas, setMesas] = useState([]);
  const [todasLasMesas, setTodasLasMesas] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [lastUpdate, setLastUpdate] = useState(null);
  const [selectedMesaId, setSelectedMesaId] = useState(null);
  const [selectedPedidoIds, setSelectedPedidoIds] = useState(() => new Set());
  const [isMovingTable, setIsMovingTable] = useState(false);
  const [moveTargetMesaId, setMoveTargetMesaId] = useState('');
  const [moveError, setMoveError] = useState('');
  const [moveSubmitting, setMoveSubmitting] = useState(false);
  const [detailPedidoId, setDetailPedidoId] = useState(null);
  const [detailPedido, setDetailPedido] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [removingItemId, setRemovingItemId] = useState(null);
  const [removeItemError, setRemoveItemError] = useState('');

  const fetchMesas = useCallback(async (controller) => {
    try {
      const response = await fetch('/api/pedidos/mesas-atendidas/', {
        method: 'GET',
        credentials: 'include',
        cache: 'no-store',
        signal: controller?.signal,
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setError(data.message || 'No se pudieron cargar tus mesas atendidas.');
        return;
      }

      setMesas(Array.isArray(data.mesas) ? data.mesas : []);
      setTodasLasMesas(Boolean(data.todas_las_mesas));
      setLastUpdate(new Date());
      setError('');
    } catch (requestError) {
      if (requestError?.name !== 'AbortError') {
        setError('Error de red al cargar tus mesas atendidas.');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    fetchMesas(controller);

    const intervalId = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        fetchMesas(controller);
      }
    }, 15000);

    return () => {
      controller.abort();
      window.clearInterval(intervalId);
    };
  }, [fetchMesas]);

  const selectedMesa = useMemo(
    () => mesas.find((mesa) => mesa.mesa_id === selectedMesaId) || null,
    [mesas, selectedMesaId],
  );

  const handleOpenMesa = (mesaId) => {
    setSelectedMesaId(mesaId);
    setSelectedPedidoIds(new Set());
    setIsMovingTable(false);
    setMoveTargetMesaId('');
    setMoveError('');
  };

  const handleCloseMesa = () => {
    setSelectedMesaId(null);
    setSelectedPedidoIds(new Set());
    setIsMovingTable(false);
    setMoveTargetMesaId('');
    setMoveError('');
  };

  const handleMoveTable = async () => {
    if (!selectedMesa || !moveTargetMesaId || moveSubmitting) {
      return;
    }

    setMoveSubmitting(true);
    setMoveError('');

    try {
      const response = await fetch('/api/pedidos/mesas-atendidas/mover/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken') || '',
        },
        credentials: 'include',
        body: JSON.stringify({
          mesa_origen_id: selectedMesa.mesa_id,
          mesa_destino_id: Number(moveTargetMesaId),
        }),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setMoveError(data.message || 'No se pudo cambiar de mesa.');
        return;
      }

      await fetchMesas();
      handleCloseMesa();
    } catch (requestError) {
      setMoveError('Error de red al cambiar de mesa.');
    } finally {
      setMoveSubmitting(false);
    }
  };

  const openPedidoDetail = async (pedidoId) => {
    setDetailPedidoId(pedidoId);
    setDetailPedido(null);
    setDetailError('');
    setDetailLoading(true);

    try {
      const response = await fetch(`/api/pedidos/${pedidoId}/`, {
        credentials: 'include',
        cache: 'no-store',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setDetailError(data.message || 'No se pudo cargar el detalle del pedido.');
        return;
      }
      setDetailPedido(data.pedido);
    } catch (requestError) {
      setDetailError('Error de red al cargar el detalle del pedido.');
    } finally {
      setDetailLoading(false);
    }
  };

  const closePedidoDetail = () => {
    setDetailPedidoId(null);
    setDetailPedido(null);
    setDetailError('');
    setRemoveItemError('');
  };

  // Quitar un item mal elegido (ver canGestionarItems, reservado a cajera/admin/
  // contador) — recarga el detalle Y la lista de mesas, porque el total de la mesa
  // (y de la cuenta seleccionada, si el pedido estaba marcado) cambió. Usa su propio
  // error (removeItemError) en vez de detailError: ese último, si está seteado,
  // reemplaza TODO el contenido del modal por el mensaje (ver el render de abajo) —
  // perfecto para "no se pudo cargar el pedido", pero borraría los items a la vista
  // justo cuando el usuario más los necesita ver para saber qué falló.
  const handleEliminarItem = async (pedidoId, detalleId) => {
    setRemovingItemId(detalleId);
    setRemoveItemError('');
    try {
      const response = await fetch(`/api/pedidos/${pedidoId}/items/${detalleId}/eliminar/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrftoken') || '' },
        credentials: 'include',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setRemoveItemError(data.message || 'No se pudo quitar el item.');
        return;
      }
      setDetailPedido(data.pedido);
      await fetchMesas();
    } catch (requestError) {
      setRemoveItemError('Error de red al quitar el item.');
    } finally {
      setRemovingItemId(null);
    }
  };

  const togglePedidoSelection = (pedidoId) => {
    setSelectedPedidoIds((current) => {
      const next = new Set(current);
      if (next.has(pedidoId)) {
        next.delete(pedidoId);
      } else {
        next.add(pedidoId);
      }
      return next;
    });
  };

  const selectedSum = useMemo(() => {
    if (!selectedMesa) {
      return 0;
    }
    return selectedMesa.pedidos
      .filter((pedido) => selectedPedidoIds.has(pedido.id))
      .reduce((total, pedido) => total + Number(pedido.total || 0), 0);
  }, [selectedMesa, selectedPedidoIds]);

  const mesaTotal = selectedMesa ? Number(selectedMesa.total || 0) : 0;

  const handleAddRound = () => {
    if (!selectedMesa || !onAddRoundToTable) {
      return;
    }
    // Prefill con el cliente del pedido activo más reciente de la mesa (el
    // último que sigue sin pagar/cancelar), igual que en el panel de cocina.
    const activePedido = [...selectedMesa.pedidos]
      .reverse()
      .find((pedido) => pedido.estado !== 'pagado' && pedido.estado !== 'cancelado');
    onAddRoundToTable({
      mesaId: selectedMesa.mesa_id,
      cliente: activePedido?.cliente || '',
    });
  };

  if (selectedMesa) {
    return (
      <section style={containerStyle(isMobile)}>
        <div style={headerWrapStyle}>
          <div>
            <div style={eyebrowStyle}>Mesas atendidas</div>
            <h2 style={titleStyle(isMobile)}>Mesa {selectedMesa.mesa_numero}</h2>
            <div style={{ marginTop: 8 }}>
              <span style={stateBadgeStyle(selectedMesa.estado)}>
                {selectedMesa.estado === 'abierta' ? 'Abierta' : 'Cerrada'}
              </span>
            </div>
          </div>
          <button type="button" onClick={handleCloseMesa} style={backButtonStyle(isMobile)}>
            Volver
          </button>
        </div>

        {error ? <div style={errorStyle}>{error}</div> : null}

        <div style={{ display: 'grid', gap: 10 }}>
          {selectedMesa.pedidos.map((pedido) => (
            <div key={pedido.id} style={pedidoCardStyle(selectedPedidoIds.has(pedido.id))}>
              <input
                type="checkbox"
                checked={selectedPedidoIds.has(pedido.id)}
                onChange={() => togglePedidoSelection(pedido.id)}
                style={pedidoCheckboxStyle}
              />
              <button
                type="button"
                onClick={() => openPedidoDetail(pedido.id)}
                style={pedidoCardButtonStyle}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
                  <div style={{ color: '#fff', fontWeight: 700 }}>Pedido #{pedido.id}</div>
                  <div style={{ color: '#fff', fontWeight: 700 }}>
                    ${Number(pedido.total || 0).toFixed(2)}
                    <BsAmount amountUsd={pedido.total} tasa={tasaCambio} />
                  </div>
                </div>
                <div style={{ color: '#d2c3c3', fontSize: 12, marginTop: 4 }}>
                  {pedido.cliente || 'Sin cliente'} · {estadoLabel(pedido.estado)}
                  {todasLasMesas && pedido.mesero ? ` · ${pedido.mesero}` : ''}
                </div>
              </button>
            </div>
          ))}
        </div>

        {selectedPedidoIds.size > 0 ? (
          <div style={selectedSumBarStyle}>
            <span>Seleccionado ({selectedPedidoIds.size} {selectedPedidoIds.size === 1 ? 'cuenta' : 'cuentas'})</span>
            <strong>
              ${selectedSum.toFixed(2)}
              <BsAmount amountUsd={selectedSum} tasa={tasaCambio} />
            </strong>
          </div>
        ) : null}

        <div style={totalsBoxStyle}>
          <span>Total de la mesa</span>
          <strong>
            ${mesaTotal.toFixed(2)}
            <BsAmount amountUsd={mesaTotal} tasa={tasaCambio} />
          </strong>
        </div>

        {selectedMesa.estado === 'abierta' && onAddRoundToTable ? (
          <button type="button" onClick={handleAddRound} style={addRoundButtonStyle(isMobile)}>
            Agregar ronda a esta mesa
          </button>
        ) : null}

        {selectedMesa.estado === 'abierta' ? (
          isMovingTable ? (
            <div style={moveTableBoxStyle}>
              <span style={{ color: '#fff', fontWeight: 700, fontSize: 13 }}>
                Mover todos los pedidos abiertos de esta mesa a:
              </span>
              <select
                value={moveTargetMesaId}
                onChange={(event) => setMoveTargetMesaId(event.target.value)}
                style={moveSelectStyle}
              >
                <option value="">Seleccionar mesa destino</option>
                {mesasCatalogo
                  .filter((mesa) => mesa.id !== selectedMesa.mesa_id)
                  .map((mesa) => (
                    <option key={mesa.id} value={mesa.id}>
                      Mesa {mesa.numero}
                    </option>
                  ))}
              </select>
              {moveError ? <div style={errorStyle}>{moveError}</div> : null}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button
                  type="button"
                  onClick={handleMoveTable}
                  style={confirmMoveButtonStyle(isMobile)}
                  disabled={!moveTargetMesaId || moveSubmitting}
                >
                  {moveSubmitting ? 'Moviendo...' : 'Confirmar cambio'}
                </button>
                <button
                  type="button"
                  onClick={() => { setIsMovingTable(false); setMoveTargetMesaId(''); setMoveError(''); }}
                  style={cancelMoveButtonStyle(isMobile)}
                >
                  Cancelar
                </button>
              </div>
            </div>
          ) : (
            <button type="button" onClick={() => setIsMovingTable(true)} style={changeTableButtonStyle(isMobile)}>
              Cambiar de mesa
            </button>
          )
        ) : null}

        {detailPedidoId ? (
          <PedidoDetalleModal
            pedido={detailPedido}
            loading={detailLoading}
            error={detailError}
            tasaCambio={tasaCambio}
            onClose={closePedidoDetail}
            canGestionarItems={canGestionarItems}
            removingItemId={removingItemId}
            removeItemError={removeItemError}
            onEliminarItem={(detalleId) => handleEliminarItem(detailPedidoId, detalleId)}
          />
        ) : null}
      </section>
    );
  }

  return (
    <section style={containerStyle(isMobile)}>
      <div style={headerWrapStyle}>
        <div>
          <div style={eyebrowStyle}>{todasLasMesas ? 'Todas las mesas' : 'Mis mesas'}</div>
          <h2 style={titleStyle(isMobile)}>Mesas atendidas hoy</h2>
          <p style={subtitleStyle}>
            {todasLasMesas
              ? 'Mesas con pedidos todavía abiertos hoy, de todos los meseros — en cuanto caja cobra el último pedido de una mesa, desaparece de aquí.'
              : 'Tus mesas con pedidos todavía abiertos hoy — en cuanto caja cobra el último pedido de una mesa, desaparece de aquí.'}
          </p>
        </div>
        <div style={headerActionsStyle(isMobile)}>
          {onNuevoPedido ? (
            <button type="button" onClick={onNuevoPedido} style={newOrderButtonStyle(isMobile)}>
              + Nuevo pedido
            </button>
          ) : null}
          <button type="button" onClick={() => fetchMesas()} style={secondaryButtonStyle(isMobile)}>
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

      {loading && <div style={emptyStateStyle}>Cargando tus mesas...</div>}
      {!loading && error && <div style={errorStyle}>{error}</div>}
      {!loading && !error && mesas.length === 0 ? (
        <div style={emptyStateStyle}>Todavía no has atendido ninguna mesa hoy.</div>
      ) : null}

      {!loading && !error && mesas.length > 0 ? (
        <div style={mesasGridStyle(isMobile)}>
          {mesas.map((mesa) => {
            // Normalmente un solo mesero por mesa, pero puede haber más de uno si
            // cajera/admin le agregó una ronda a la mesa de un mesero (ver el
            // permiso de mesas_atendidas_view/pedido_create_view) — se listan todos.
            const meseros = [...new Set(mesa.pedidos.map((pedido) => pedido.mesero).filter(Boolean))];
            return (
              <button
                key={mesa.mesa_id}
                type="button"
                onClick={() => handleOpenMesa(mesa.mesa_id)}
                style={mesaCardStyle(mesa.estado)}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
                  <div style={{ color: '#fff', fontWeight: 800, fontSize: 18 }}>Mesa {mesa.mesa_numero}</div>
                  <span style={stateBadgeStyle(mesa.estado)}>
                    {mesa.estado === 'abierta' ? 'Abierta' : 'Cerrada'}
                  </span>
                </div>
                {todasLasMesas && meseros.length > 0 ? (
                  <div style={mesaMeseroTagStyle}>{meseros.join(' y ')}</div>
                ) : null}
                <div style={{ color: '#d2c3c3', fontSize: 13, marginTop: 6 }}>
                  {mesa.pedidos.length} {mesa.pedidos.length === 1 ? 'pedido' : 'pedidos'}
                </div>
                <div style={{ color: '#fff', fontWeight: 700, fontSize: 16, marginTop: 8 }}>
                  ${Number(mesa.total || 0).toFixed(2)}
                  <BsAmount amountUsd={mesa.total} tasa={tasaCambio} />
                </div>
              </button>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}

function PedidoDetalleModal({ pedido, loading, error, tasaCambio, onClose, canGestionarItems = false, removingItemId = null, removeItemError = '', onEliminarItem }) {
  // Solo se monta mientras hay un pedido seleccionado, así que montado == abierto.
  useMobileBackHandler(true, onClose);

  const items = pedido ? (pedido.items || []) : [];
  // Nunca dejar el pedido en cero items desde acá (para eso está cancelar el pedido
  // completo) ni tocar uno ya cobrado/cancelado — mismas reglas que valida el backend
  // (pedido_detalle_eliminar_view), repetidas acá solo para no mostrar un botón que
  // el servidor va a rechazar.
  const puedeEliminarItems = canGestionarItems
    && pedido
    && pedido.estado !== 'pagado'
    && pedido.estado !== 'cancelado'
    && items.length > 1;

  return (
    <div style={modalBackdropStyle} onClick={onClose}>
      <div style={modalCardStyle} onClick={(event) => event.stopPropagation()}>
        <button type="button" onClick={onClose} style={modalCloseButtonStyle} aria-label="Cerrar">
          ×
        </button>
        <div style={modalScrollAreaStyle}>
          <div style={modalBodyStyle}>
            {loading ? (
              <div style={{ color: '#d8cfcf' }}>Cargando detalle del pedido...</div>
            ) : error ? (
              <div style={errorStyle}>{error}</div>
            ) : pedido ? (
              <>
                <div style={modalTitleStyle}>Pedido #{pedido.id}</div>
                <div style={modalSubtitleStyle}>
                  {estadoLabel(pedido.estado)}{pedido.mesa ? ` · Mesa ${pedido.mesa}` : ''}
                </div>
                {pedido.cliente_nombre ? (
                  <div style={modalSubtitleStyle}>Cliente: {pedido.cliente_nombre}</div>
                ) : null}
                {pedido.cliente_cedula ? (
                  <div style={modalSubtitleStyle}>Cédula: {pedido.cliente_cedula}</div>
                ) : null}
                {pedido.cliente_telefono ? (
                  <div style={modalSubtitleStyle}>Teléfono: {pedido.cliente_telefono}</div>
                ) : null}

                {removeItemError ? <div style={errorStyle}>{removeItemError}</div> : null}

                <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
                  {items.map((item) => (
                    <div key={item.id} style={itemRowStyle}>
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
                      {puedeEliminarItems ? (
                        <button
                          type="button"
                          onClick={() => onEliminarItem(item.id)}
                          style={removeItemButtonStyle}
                          disabled={removingItemId === item.id}
                        >
                          {removingItemId === item.id ? 'Quitando...' : 'Quitar item'}
                        </button>
                      ) : null}
                    </div>
                  ))}
                </div>

                {pedido.notas ? <p style={orderNoteStyle}>Nota general: {pedido.notas}</p> : null}

                <div style={modalTotalStyle}>
                  Total: ${Number(pedido.total || 0).toFixed(2)}
                  <BsAmount amountUsd={pedido.total} tasa={tasaCambio} />
                </div>
              </>
            ) : null}
          </div>
        </div>
      </div>
    </div>
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

const MESA_TONES = {
  abierta: { border: 'rgba(52, 211, 153, 0.45)', background: 'rgba(52, 211, 153, 0.08)' },
  cerrada: { border: 'rgba(255,255,255,0.14)', background: 'rgba(255,255,255,0.03)' },
};

const mesaCardStyle = (estado) => {
  const tone = MESA_TONES[estado] || MESA_TONES.cerrada;
  return {
    textAlign: 'left',
    border: `1px solid ${tone.border}`,
    background: tone.background,
    borderRadius: 16,
    padding: 14,
    cursor: 'pointer',
    display: 'block',
  };
};

const mesaMeseroTagStyle = {
  color: '#ffcf85',
  fontSize: 12,
  fontWeight: 700,
  marginTop: 4,
};

const stateBadgeStyle = (estado) => ({
  display: 'inline-block',
  borderRadius: 999,
  padding: '3px 10px',
  fontSize: 11,
  fontWeight: 800,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
  color: estado === 'abierta' ? '#34d399' : '#c9c9c9',
  background: estado === 'abierta' ? 'rgba(52, 211, 153, 0.16)' : 'rgba(255,255,255,0.08)',
  border: `1px solid ${estado === 'abierta' ? 'rgba(52, 211, 153, 0.4)' : 'rgba(255,255,255,0.18)'}`,
});

const pedidoCardStyle = (selected) => ({
  display: 'flex',
  gap: 10,
  alignItems: 'flex-start',
  borderRadius: 14,
  border: selected ? '1px solid rgba(88, 166, 255, 0.6)' : '1px solid rgba(255,255,255,0.12)',
  background: selected ? 'rgba(88, 166, 255, 0.1)' : 'rgba(255,255,255,0.03)',
  padding: 11,
  cursor: 'pointer',
});

const pedidoCheckboxStyle = {
  marginTop: 3,
  width: 18,
  height: 18,
  flexShrink: 0,
  cursor: 'pointer',
};

const pedidoCardButtonStyle = {
  flex: 1,
  minWidth: 0,
  display: 'block',
  border: 'none',
  background: 'transparent',
  padding: 0,
  margin: 0,
  cursor: 'pointer',
  textAlign: 'left',
  font: 'inherit',
  color: 'inherit',
};

const selectedSumBarStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  borderRadius: 14,
  border: '1px solid rgba(88, 166, 255, 0.5)',
  background: 'rgba(88, 166, 255, 0.12)',
  color: '#bcdcff',
  padding: '10px 14px',
  fontWeight: 700,
  fontSize: 14,
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

const changeTableButtonStyle = (isMobile) => ({
  border: '1px solid rgba(245, 158, 11, 0.5)',
  borderRadius: 999,
  padding: isMobile ? '12px 16px' : '10px 16px',
  background: 'rgba(245, 158, 11, 0.12)',
  color: '#f59e0b',
  fontWeight: 700,
  cursor: 'pointer',
  minHeight: isMobile ? 44 : 40,
  width: isMobile ? '100%' : 'auto',
});

const moveTableBoxStyle = {
  display: 'grid',
  gap: 10,
  borderRadius: 14,
  border: '1px solid rgba(245, 158, 11, 0.4)',
  background: 'rgba(245, 158, 11, 0.08)',
  padding: 12,
};

const moveSelectStyle = {
  borderRadius: 10,
  border: '1px solid rgba(255,255,255,0.2)',
  background: 'rgba(0,0,0,0.3)',
  color: '#fff',
  padding: '10px 12px',
  fontSize: 14,
  minHeight: 42,
};

const confirmMoveButtonStyle = (isMobile) => ({
  border: 'none',
  borderRadius: 999,
  padding: isMobile ? '10px 14px' : '8px 14px',
  background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
  minHeight: isMobile ? 42 : 36,
  flex: isMobile ? '1 1 100%' : '0 0 auto',
});

const cancelMoveButtonStyle = (isMobile) => ({
  border: '1px solid rgba(255,255,255,0.2)',
  borderRadius: 999,
  padding: isMobile ? '10px 14px' : '8px 14px',
  background: 'rgba(255,255,255,0.04)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
  minHeight: isMobile ? 42 : 36,
  flex: isMobile ? '1 1 100%' : '0 0 auto',
});

const modalBackdropStyle = {
  position: 'fixed',
  inset: 0,
  zIndex: 40,
  background: 'rgba(0,0,0,0.7)',
  display: 'grid',
  placeItems: 'center',
  padding: 16,
};

const modalCardStyle = {
  position: 'relative',
  width: '100%',
  maxWidth: 420,
  maxHeight: '88vh',
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
  borderRadius: 20,
  border: '1px solid rgba(255,255,255,0.14)',
  background: 'linear-gradient(180deg, rgba(22, 10, 10, 0.98) 0%, rgba(10, 10, 10, 0.99) 100%)',
  boxShadow: '0 20px 50px rgba(0,0,0,0.5)',
};

const modalScrollAreaStyle = {
  overflowY: 'auto',
  flex: '1 1 auto',
  minHeight: 0,
};

const modalCloseButtonStyle = {
  position: 'absolute',
  top: 10,
  right: 10,
  zIndex: 2,
  width: 32,
  height: 32,
  borderRadius: '50%',
  border: 'none',
  background: 'rgba(0,0,0,0.55)',
  color: '#fff',
  fontSize: 20,
  lineHeight: 1,
  cursor: 'pointer',
  display: 'grid',
  placeItems: 'center',
};

const modalBodyStyle = {
  display: 'grid',
  gap: 10,
  padding: 20,
};

const modalTitleStyle = {
  color: '#fff',
  fontSize: 22,
  fontWeight: 800,
  paddingRight: 30,
};

const modalSubtitleStyle = {
  color: '#e8bcbc',
  fontSize: 13,
};

const modalTotalStyle = {
  marginTop: 6,
  paddingTop: 10,
  borderTop: '1px solid rgba(255,255,255,0.1)',
  color: '#fff',
  fontWeight: 800,
  fontSize: 16,
};

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

export default MesasAtendidasPage;

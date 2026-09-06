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

function estadoLabel(estado) {
  return ESTADO_LABELS[estado] || estado;
}

function MesasAtendidasPage({ isMobile, onBack, onAddRoundToTable, onNuevoPedido, onEditOrder, autoAbrir, onAutoAbrirConsumido, mesasCatalogo = [], canGestionarItems = false, sidebarOffset = '0px' }) {
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
  const [flashMessage, setFlashMessage] = useState('');
  const [prepBusyMap, setPrepBusyMap] = useState({});
  const [reprintBusyMap, setReprintBusyMap] = useState({});
  const [actionError, setActionError] = useState('');
  const [ajusteModal, setAjusteModal] = useState(null); // { modo, pedidoId, item }
  const [ajusteBusy, setAjusteBusy] = useState(false);
  const [ajusteError, setAjusteError] = useState('');
  const [requiereUsuarioMover, setRequiereUsuarioMover] = useState(false);
  const [meserosDisponibles, setMeserosDisponibles] = useState([]);

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

  // Precargada de una vez (no al abrir el modal de mover) para que el selector de
  // mesero nunca aparezca vacío por timing — ver AjustePedidoModal/cargarMeserosDisponibles.
  useEffect(() => {
    if (!canGestionarItems) return;
    cargarMeserosDisponibles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canGestionarItems]);

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

  // Al crear o editar un pedido (ver WelcomeScreen.jsx: handleOrderCreated,
  // handleOrderUpdated) el mesero aterriza acá con la mesa ya abierta, en vez
  // de en el extinto tablero de cocina — mismo patrón de "token" que ya usa
  // newOrderPreset en WelcomeScreen, para forzar la reapertura aunque sea la
  // misma mesaId de la vez anterior.
  useEffect(() => {
    if (!autoAbrir?.token) return;
    handleOpenMesa(autoAbrir.mesaId);
    if (autoAbrir.flashMessage) {
      setFlashMessage(autoAbrir.flashMessage);
    }
    // Se avisa al padre que ya se uso esta señal (ver WelcomeScreen.mesaAutoAbrir) —
    // sin esto, la proxima vez que se monte esta pagina (ej. tocando "Mesas
    // atendidas" en el menu, sin haber creado/editado ningun pedido) volveria a
    // abrir de un salto la misma mesa de la ultima vez, en vez de mostrar la lista.
    onAutoAbrirConsumido?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoAbrir?.token]);

  useEffect(() => {
    if (!flashMessage) return;
    const timeoutId = window.setTimeout(() => setFlashMessage(''), 6000);
    return () => window.clearTimeout(timeoutId);
  }, [flashMessage]);

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

  const abrirAjuste = (modo, pedidoId, item) => {
    setAjusteError('');
    setRequiereUsuarioMover(false);
    setAjusteModal({
      modo,
      pedidoId,
      item: { id: item.id, nombre: item.producto_nombre, cantidad: item.cantidad, esPorPeso: Boolean(item.peso_gramos) },
    });
  };

  // "Iniciar preparación" — mismo endpoint y transición que antes disparaba
  // KitchenOrdersPage.handleUpdateOrderState, ahora vive acá porque cocina ya
  // no mira ninguna pantalla: es el mesero quien manda el pedido a imprimir
  // desde su propia mesa (ver _notify_cocina_event en el backend).
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
      await fetchMesas();
    } catch (requestError) {
      setActionError('Error de red al iniciar la preparación.');
    } finally {
      setPrepBusyMap((current) => ({ ...current, [pedidoId]: false }));
    }
  };

  // Reimprime un solo renglón (no el pedido completo) — para cuando ese
  // ticket puntual se dañó o se perdió en cocina.
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

  const cargarMeserosDisponibles = async () => {
    if (meserosDisponibles.length > 0) return;
    try {
      const response = await fetch('/api/pedidos/meseros-disponibles/', { credentials: 'include', cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (response.ok && data.ok) {
        setMeserosDisponibles(Array.isArray(data.meseros) ? data.meseros : []);
      } else {
        console.error('No se pudo cargar la lista de meseros:', data.message || response.status);
      }
    } catch (requestError) {
      // Se reintenta la próxima vez que haga falta (ver el useEffect que precarga
      // esto al montar, y la llamada de respaldo en handleConfirmarMover).
      console.error('Error de red al cargar la lista de meseros:', requestError);
    }
  };

  // Quitar (completo o solo parte de la cantidad) o mover a otra mesa un item mal
  // comandado (ver canGestionarItems, reservado a cajera/admin/contador) — ambas
  // acciones piden motivo obligatorio (ver AjustePedidoModal/VGAjustePedido) y
  // recargan la lista de mesas completa (ya trae los items inline, ver
  // mesas_atendidas_view), porque el total de la mesa cambió.
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
      await fetchMesas();
    } catch (requestError) {
      setAjusteError('Error de red al quitar el item.');
    } finally {
      setAjusteBusy(false);
    }
  };

  // Si la mesa destino no tiene pedido abierto, el backend no lo trata como error:
  // responde requiere_usuario para que se le pida a la cajera/admin a qué mesero se
  // le abre esa mesa (ver pedido_detalle_mover_view) — acá eso NO se muestra como
  // ajusteError (rojo, de "algo salió mal"), sino que revela el selector de mesero
  // dentro del mismo modal para reintentar con usuario_id.
  const handleConfirmarMover = async ({ motivo, mesaDestinoId, usuarioId }) => {
    if (!ajusteModal) return;
    setAjusteBusy(true);
    setAjusteError('');
    try {
      const response = await fetch(`/api/pedidos/${ajusteModal.pedidoId}/items/${ajusteModal.item.id}/mover/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') || '' },
        credentials: 'include',
        body: JSON.stringify({ motivo, mesa_destino_id: mesaDestinoId, usuario_id: usuarioId }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        if (data.requiere_usuario) {
          setRequiereUsuarioMover(true);
          await cargarMeserosDisponibles();
          return;
        }
        setAjusteError(data.message || 'No se pudo mover el item.');
        return;
      }
      setAjusteModal(null);
      await fetchMesas();
    } catch (requestError) {
      setAjusteError('Error de red al mover el item.');
    } finally {
      setAjusteBusy(false);
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
    // Normalmente hay a lo sumo un pedido "pendiente" por mesa (se manda a
    // cocina antes de que el mesero piense en agregar otra ronda), así que el
    // footer puede mostrar "Iniciar preparación"/"Editar" para ese único
    // pedido sin ambigüedad. Si por algún motivo hay más de uno todavía
    // pendiente a la vez, no adivinamos cuál — esos dos botones vuelven a
    // aparecer en cada tarjeta para no perder la posibilidad de mandarlos a
    // cocina o editarlos.
    const pedidosPendientes = selectedMesa.pedidos.filter((pedido) => pedido.estado === 'pendiente');
    const pedidoPendienteUnico = pedidosPendientes.length === 1 ? pedidosPendientes[0] : null;

    return (
      <section style={containerStyle(isMobile)}>
        <div style={selectedMesa.estado === 'abierta' ? scrollAreaWithFooterStyle : undefined}>
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

          {flashMessage ? <div style={flashBannerStyle}>{flashMessage}</div> : null}
          {error ? <div style={errorStyle}>{error}</div> : null}
          {actionError ? <div style={errorStyle}>{actionError}</div> : null}

          <div style={{ display: 'grid', gap: 10 }}>
            {selectedMesa.pedidos.map((pedido) => {
              const impreso = pedido.estado !== 'pendiente';
              const items = pedido.detalles || [];
              const puedeAjustarItems = canGestionarItems
                && pedido.estado !== 'pagado'
                && pedido.estado !== 'cancelado'
                && items.length > 1;

              return (
                <div key={pedido.id} style={pedidoCardStyle(selectedPedidoIds.has(pedido.id))}>
                  <div style={pedidoCardHeaderRowStyle}>
                    <input
                      type="checkbox"
                      checked={selectedPedidoIds.has(pedido.id)}
                      onChange={() => togglePedidoSelection(pedido.id)}
                      style={pedidoCheckboxStyle}
                    />
                    <div style={{ flex: 1, minWidth: 0 }}>
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
                            <>
                              <button type="button" onClick={() => abrirAjuste('eliminar', pedido.id, item)} style={removeItemButtonStyle}>
                                Quitar item
                              </button>
                              <button type="button" onClick={() => abrirAjuste('mover', pedido.id, item)} style={moveItemButtonStyle}>
                                Mover a otra mesa
                              </button>
                            </>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>

                  {pedido.notas ? <p style={orderNoteStyle}>Nota: {pedido.notas}</p> : null}

                  {pedido.estado === 'pendiente' && !pedidoPendienteUnico ? (
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
                      <button
                        type="button"
                        onClick={() => handleIniciarPreparacion(pedido.id)}
                        style={{ ...iniciarPrepButtonStyle(false), width: 'auto' }}
                        disabled={Boolean(prepBusyMap[pedido.id])}
                      >
                        {prepBusyMap[pedido.id] ? 'Enviando...' : 'Iniciar preparación'}
                      </button>
                      {onEditOrder ? (
                        <button type="button" onClick={() => onEditOrder(pedido.id)} style={{ ...editOrderButtonStyle(false), width: 'auto' }}>
                          Editar
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              );
            })}
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
        </div>

        {selectedMesa.estado === 'abierta' ? (
          <div style={fixedFooterStyle(sidebarOffset)}>
            {isMovingTable ? (
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
                {onAddRoundToTable ? (
                  <button type="button" onClick={handleAddRound} style={addRoundButtonStyle(isMobile)}>
                    Agregar ronda
                  </button>
                ) : null}
                <button type="button" onClick={() => setIsMovingTable(true)} style={changeTableButtonStyle(isMobile)}>
                  Cambiar de mesa
                </button>
              </div>
            )}
          </div>
        ) : null}

        {ajusteModal ? (
          <AjustePedidoModal
            modo={ajusteModal.modo}
            item={ajusteModal.item}
            mesasCatalogo={mesasCatalogo}
            mesaActualId={selectedMesa.mesa_id}
            busy={ajusteBusy}
            error={ajusteError}
            requiereUsuario={requiereUsuarioMover}
            meserosDisponibles={meserosDisponibles}
            onClose={() => setAjusteModal(null)}
            onConfirmarEliminar={handleConfirmarEliminar}
            onConfirmarMover={handleConfirmarMover}
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
  borderRadius: 14,
  border: selected ? '1px solid rgba(88, 166, 255, 0.6)' : '1px solid rgba(255,255,255,0.12)',
  background: selected ? 'rgba(88, 166, 255, 0.1)' : 'rgba(255,255,255,0.03)',
  padding: 11,
});

const pedidoCardHeaderRowStyle = {
  display: 'flex',
  gap: 10,
  alignItems: 'flex-start',
};

const pedidoCheckboxStyle = {
  marginTop: 3,
  width: 18,
  height: 18,
  flexShrink: 0,
  cursor: 'pointer',
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

const scrollAreaWithFooterStyle = {
  display: 'grid',
  gap: 14,
  paddingBottom: 260,
};

// `left` sigue a desktopContentOffset (WelcomeScreen.jsx) para no quedar por
// debajo de la barra lateral fija en escritorio — sin esto, el footer se
// dibuja a todo el ancho del viewport e invade el espacio de la barra
// lateral. La transition queda igual a la que ya usa esa barra (260ms) para
// que el footer se deslice en sincronía al abrirla/cerrarla.
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

const moveItemButtonStyle = {
  justifySelf: 'start',
  marginTop: 2,
  border: '1px solid rgba(245, 158, 11, 0.45)',
  borderRadius: 999,
  padding: '4px 10px',
  background: 'rgba(245, 158, 11, 0.1)',
  color: '#f5c778',
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

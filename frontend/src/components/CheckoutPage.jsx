import { useCallback, useEffect, useMemo, useState } from 'react';
import BsAmount from './BsAmount';
import ConfirmModal from './ConfirmModal';
import CuentasPorCobrarPage from './CuentasPorCobrarPage';
import useExchangeRate from '../hooks/useExchangeRate';
import { formatMontoDocumento } from '../utils/currency';

const emptyCliente = { nombre: '', tipo_documento: '', numero_documento: '' };

function CheckoutPage({ isMobile, onBack, lastKitchenEvent }) {
  const tasaCambio = useExchangeRate();
  const [pedidos, setPedidos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedByGroup, setSelectedByGroup] = useState({});
  const [metodoByGroup, setMetodoByGroup] = useState({});
  const [clienteByGroup, setClienteByGroup] = useState({});
  const [prefacturaByGroup, setPrefacturaByGroup] = useState({});
  const [metodosPago, setMetodosPago] = useState([]);

  useEffect(() => {
    const loadMetodosPago = async () => {
      try {
        const response = await fetch('/api/metodos-pago/', { credentials: 'include', cache: 'no-store' });
        const data = await response.json().catch(() => ({}));
        if (response.ok && data.ok) {
          setMetodosPago(Array.isArray(data.metodos_pago) ? data.metodos_pago : []);
        }
      } catch (requestError) {
        // El selector simplemente queda vacio si falla; se reintenta en el siguiente montaje.
      }
    };

    loadMetodosPago();
  }, []);
  const [busyGroup, setBusyGroup] = useState('');
  const [feedback, setFeedback] = useState('');
  const [feedbackType, setFeedbackType] = useState('success');
  const [expandedOrderIds, setExpandedOrderIds] = useState(() => new Set());
  const [cuentasRefreshToken, setCuentasRefreshToken] = useState(0);
  const [pendingConfirm, setPendingConfirm] = useState(null);

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

  const updateCliente = (groupKey, field, value) => {
    setClienteByGroup((current) => ({
      ...current,
      [groupKey]: { ...(current[groupKey] || emptyCliente), [field]: value },
    }));
  };

  // La nota de entrega no lleva numeracion fiscal, asi que no necesita
  // documento del cliente — pero una pre-factura o factura si, para poder
  // identificar al cliente en el documento fiscal. Se valida en el frontend
  // antes de llamar al backend (que hoy acepta el documento vacio y cae a
  // "Consumidor Final") para forzar la politica del negocio de siempre
  // pedirlo en estos dos flujos.
  const validateClienteDocumento = (group) => {
    const cliente = clienteByGroup[group.key] || emptyCliente;
    if (!cliente.tipo_documento || !cliente.numero_documento.trim()) {
      setFeedbackType('error');
      setFeedback(`Indica el tipo y número de documento del cliente de ${group.label} antes de generar la pre-factura o factura.`);
      return false;
    }
    return true;
  };

  const clearGroupState = (groupKey) => {
    setSelectedByGroup((current) => {
      const copy = { ...current };
      delete copy[groupKey];
      return copy;
    });
    setPrefacturaByGroup((current) => {
      const copy = { ...current };
      delete copy[groupKey];
      return copy;
    });
  };

  // --- Documento 1: Nota de entrega (cobro directo e inmediato, sin IVA ni numeracion fiscal) ---
  const handleNotaEntrega = async (group) => {
    const selectedIds = Array.from(selectedByGroup[group.key] || []);
    if (selectedIds.length === 0) {
      return;
    }
    const metodoPagoId = metodoByGroup[group.key] || (metodosPago[0] && metodosPago[0].id);
    if (!metodoPagoId) {
      setFeedbackType('error');
      setFeedback('No hay metodos de pago activos configurados.');
      return;
    }

    setBusyGroup(group.key);
    setFeedback('');
    try {
      const response = await fetch('/api/pedidos/cobro/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken') || '',
        },
        credentials: 'include',
        body: JSON.stringify({ pedido_ids: selectedIds, metodo_pago_id: metodoPagoId }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setFeedbackType('error');
        setFeedback(data.message || 'No se pudo procesar la nota de entrega.');
        await fetchPedidos();
        return;
      }

      setFeedbackType('success');
      setFeedback(
        `Nota de entrega registrada: ${formatMontoDocumento(data.factura.total, data.factura.moneda, tasaCambio)} `
        + `(${data.factura.pedidos.length} pedido(s)). Referencia ${data.factura.referencia}.`,
      );
      clearGroupState(group.key);
      await fetchPedidos();
    } catch (requestError) {
      setFeedbackType('error');
      setFeedback('Error de red al procesar la nota de entrega.');
    } finally {
      setBusyGroup('');
    }
  };

  // --- Documento 2: Pre-factura (vista previa, sin cobrar todavia) ---
  const handleGenerarPrefactura = async (group) => {
    const selectedIds = Array.from(selectedByGroup[group.key] || []);
    if (selectedIds.length === 0) {
      return;
    }
    const cliente = clienteByGroup[group.key] || emptyCliente;
    const metodoPagoId = metodoByGroup[group.key] || (metodosPago[0] && metodosPago[0].id);

    setBusyGroup(group.key);
    setFeedback('');
    try {
      const response = await fetch('/api/prefacturas/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') || '' },
        credentials: 'include',
        body: JSON.stringify({
          pedido_ids: selectedIds,
          cliente_nombre: cliente.nombre,
          cliente_tipo_documento: cliente.tipo_documento,
          cliente_numero_documento: cliente.numero_documento,
          metodo_pago_id: metodoPagoId,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setFeedbackType('error');
        setFeedback(data.message || 'No se pudo generar la pre-factura.');
        return;
      }
      setFeedbackType('success');
      setFeedback(`Pre-factura ${data.prefactura.codigo} generada. Revisa la cuenta con el cliente antes de confirmar.`);
      setPrefacturaByGroup((current) => ({ ...current, [group.key]: data.prefactura }));
    } catch (requestError) {
      setFeedbackType('error');
      setFeedback('Error de red al generar la pre-factura.');
    } finally {
      setBusyGroup('');
    }
  };

  const handleDescartarPrefactura = (groupKey) => {
    setPrefacturaByGroup((current) => {
      const copy = { ...current };
      delete copy[groupKey];
      return copy;
    });
  };

  const handleConfirmarFacturaDesdePrefactura = async (group) => {
    const prefactura = prefacturaByGroup[group.key];
    if (!prefactura) {
      return;
    }
    setBusyGroup(group.key);
    setFeedback('');
    try {
      const response = await fetch(`/api/prefacturas/${prefactura.id}/convertir/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') || '' },
        credentials: 'include',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setFeedbackType('error');
        setFeedback(data.message || 'No se pudo emitir la factura.');
        return;
      }
      setFeedbackType('success');
      setFeedback(
        `Factura Nº ${data.factura.numero_factura} emitida (Control ${data.factura.numero_control}). `
        + `Total ${formatMontoDocumento(data.factura.total, data.factura.moneda, data.factura.tasa_cambio_referencia || tasaCambio)} `
        + `— saldo pendiente ${formatMontoDocumento(data.factura.saldo_pendiente, data.factura.moneda, data.factura.tasa_cambio_referencia || tasaCambio)}. `
        + 'Cóbrala desde Cuentas por cobrar, abajo.',
      );
      clearGroupState(group.key);
      setCuentasRefreshToken((current) => current + 1);
      await fetchPedidos();
    } catch (requestError) {
      setFeedbackType('error');
      setFeedback('Error de red al emitir la factura.');
    } finally {
      setBusyGroup('');
    }
  };

  // --- Documento 3: Factura directa (sin pasar por pre-factura) ---
  const handleFacturaDirecta = async (group) => {
    const selectedIds = Array.from(selectedByGroup[group.key] || []);
    if (selectedIds.length === 0) {
      return;
    }
    const cliente = clienteByGroup[group.key] || emptyCliente;
    const metodoPagoId = metodoByGroup[group.key] || (metodosPago[0] && metodosPago[0].id);

    setBusyGroup(group.key);
    setFeedback('');
    try {
      const response = await fetch('/api/facturas/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') || '' },
        credentials: 'include',
        body: JSON.stringify({
          pedido_ids: selectedIds,
          cliente_nombre: cliente.nombre,
          cliente_tipo_documento: cliente.tipo_documento,
          cliente_numero_documento: cliente.numero_documento,
          metodo_pago_id: metodoPagoId,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setFeedbackType('error');
        setFeedback(data.message || 'No se pudo emitir la factura.');
        return;
      }
      setFeedbackType('success');
      setFeedback(
        `Factura Nº ${data.factura.numero_factura} emitida (Control ${data.factura.numero_control}). `
        + `Total ${formatMontoDocumento(data.factura.total, data.factura.moneda, data.factura.tasa_cambio_referencia || tasaCambio)} `
        + `— saldo pendiente ${formatMontoDocumento(data.factura.saldo_pendiente, data.factura.moneda, data.factura.tasa_cambio_referencia || tasaCambio)}. `
        + 'Cóbrala desde Cuentas por cobrar, abajo.',
      );
      clearGroupState(group.key);
      setCuentasRefreshToken((current) => current + 1);
      await fetchPedidos();
    } catch (requestError) {
      setFeedbackType('error');
      setFeedback('Error de red al emitir la factura.');
    } finally {
      setBusyGroup('');
    }
  };

  // Arma el título/mensaje/etiqueta del modal de confirmación según qué botón
  // se apretó (nota de entrega, factura directa, o confirmar factura desde
  // una pre-factura ya generada) — se recalcula en cada render a partir de
  // los mismos mapas por-grupo que ya alimentan las tarjetas, así el monto y
  // la cantidad de pedidos que se muestran siempre coinciden con lo que el
  // usuario seleccionó.
  const buildConfirmContent = (pending) => {
    if (!pending) {
      return { title: '', message: '', confirmLabel: 'Confirmar' };
    }
    const { action, group } = pending;

    if (action === 'prefactura') {
      const prefactura = prefacturaByGroup[group.key];
      const totalLabel = prefactura
        ? formatMontoDocumento(prefactura.total, prefactura.moneda, prefactura.tasa_cambio_referencia || tasaCambio)
        : '';
      return {
        title: 'Emitir factura',
        message: `Vas a emitir la factura fiscal${prefactura ? ` de la pre-factura ${prefactura.codigo}` : ''} de ${group.label} por ${totalLabel}. Esta acción no se puede deshacer. ¿Confirmas?`,
        confirmLabel: 'Sí, emitir factura',
      };
    }

    const selectedSet = selectedByGroup[group.key] || new Set();
    const selectedTotal = group.pedidos
      .filter((pedido) => selectedSet.has(pedido.id))
      .reduce((sum, pedido) => sum + Number(pedido.total), 0);
    const totalLabel = `$${selectedTotal.toFixed(2)}`;

    if (action === 'nota') {
      return {
        title: 'Registrar nota de entrega',
        message: `Vas a cobrar ${selectedSet.size} pedido(s) de ${group.label} por ${totalLabel} con una nota de entrega (sin factura fiscal). ¿Confirmas?`,
        confirmLabel: 'Sí, registrar',
      };
    }

    if (action === 'factura') {
      return {
        title: 'Emitir factura directa',
        message: `Vas a emitir una factura fiscal para ${selectedSet.size} pedido(s) de ${group.label} por ${totalLabel}. Esta acción no se puede deshacer. ¿Confirmas?`,
        confirmLabel: 'Sí, emitir factura',
      };
    }

    return { title: '', message: '', confirmLabel: 'Confirmar' };
  };

  const confirmContent = buildConfirmContent(pendingConfirm);

  const handleConfirmPendingAction = async () => {
    if (!pendingConfirm) {
      return;
    }
    const { action, group } = pendingConfirm;
    if (action === 'nota') {
      await handleNotaEntrega(group);
    } else if (action === 'factura') {
      await handleFacturaDirecta(group);
    } else if (action === 'prefactura') {
      await handleConfirmarFacturaDesdePrefactura(group);
    }
    setPendingConfirm(null);
  };

  return (
    <section style={containerStyle(isMobile)}>
      <div style={headerWrapStyle(isMobile)}>
        <div>
          <div style={eyebrowStyle}>Cobro</div>
          <h2 style={titleStyle(isMobile)}>Pedidos listos para cobrar</h2>
          <p style={subtitleStyle}>
            Agrupados por mesa. Por cada grupo elige el documento que convenga: una nota de entrega rápida,
            una pre-factura para que el cliente revise la cuenta, o la factura fiscal directa.
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
            const cliente = clienteByGroup[group.key] || emptyCliente;
            const prefactura = prefacturaByGroup[group.key];
            const isBusy = busyGroup === group.key;

            return (
              <article key={group.key} style={groupCardStyle}>
                <div style={groupHeaderStyle}>
                  <div style={{ color: '#fff', fontWeight: 700, fontSize: 17 }}>{group.label}</div>
                  <span style={groupCountStyle}>{group.pedidos.length} pedido(s)</span>
                </div>

                <div style={ordersScrollStyle}>
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
                          <span style={{ color: '#ffcf7d', fontWeight: 700 }}>
                            ${pedido.total}
                            <BsAmount amountUsd={pedido.total} tasa={tasaCambio} />
                          </span>
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

                            <div style={{ display: 'grid', gap: 6 }}>
                              {groupItemsByPlato(items).platos.map(({ grupoId, items: grupoItems }) => (
                                <div key={`plato-${grupoId}`} style={platoGroupStyle}>
                                  <div style={platoGroupTitleStyle}>Plato {grupoId}</div>
                                  {grupoItems.map((item) => renderDetailItemRow(item, tasaCambio))}
                                </div>
                              ))}
                              {groupItemsByPlato(items).sueltos.map((item) => renderDetailItemRow(item, tasaCambio))}
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
                              <span>Subtotal: ${pedido.subtotal}<BsAmount amountUsd={pedido.subtotal} tasa={tasaCambio} /></span>
                              {Number(pedido.impuesto) > 0 ? <span>Impuesto: ${pedido.impuesto}<BsAmount amountUsd={pedido.impuesto} tasa={tasaCambio} /></span> : null}
                              {Number(pedido.descuento) > 0 ? <span>Descuento: -${pedido.descuento}<BsAmount amountUsd={pedido.descuento} tasa={tasaCambio} /></span> : null}
                              {Number(pedido.propina) > 0 ? <span>Propina: ${pedido.propina}<BsAmount amountUsd={pedido.propina} tasa={tasaCambio} /></span> : null}
                              <span style={{ fontWeight: 800, color: '#fff' }}>
                                Total: ${pedido.total}
                                <BsAmount amountUsd={pedido.total} tasa={tasaCambio} style={{ color: '#e0c9a3' }} />
                              </span>
                            </div>
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                </div>

                {!prefactura ? (
                  <div style={footerSectionStyle}>
                    <div style={clienteFormStyle(isMobile)}>
                      <input
                        placeholder="Cliente (opcional, solo para pre-factura/factura)"
                        value={cliente.nombre}
                        onChange={(event) => updateCliente(group.key, 'nombre', event.target.value)}
                        style={inputStyle}
                      />
                      <select
                        value={cliente.tipo_documento}
                        onChange={(event) => updateCliente(group.key, 'tipo_documento', event.target.value)}
                        style={selectStyle}
                        className="admin-dark-select"
                      >
                        <option value="">Sin documento</option>
                        <option value="V">V - Cédula</option>
                        <option value="E">E - Cédula extranjero</option>
                        <option value="J">J - RIF jurídico</option>
                        <option value="G">G - RIF gubernamental</option>
                        <option value="P">P - Pasaporte</option>
                      </select>
                      <input
                        placeholder="Número de documento"
                        value={cliente.numero_documento}
                        onChange={(event) => updateCliente(group.key, 'numero_documento', event.target.value)}
                        style={inputStyle}
                      />
                    </div>
                    <p style={clienteHintStyle}>
                      El tipo y número de documento son obligatorios para generar pre-factura o factura fiscal (no aplica a la nota de entrega).
                    </p>

                    <div style={groupFooterStyle(isMobile)}>
                      <div style={{ color: '#fff', fontWeight: 700 }}>
                        Total seleccionado: ${selectedTotal.toFixed(2)}
                        <BsAmount amountUsd={selectedTotal} tasa={tasaCambio} />
                      </div>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                        <select
                          value={metodoByGroup[group.key] || (metodosPago[0] && metodosPago[0].id) || ''}
                          onChange={(event) => setMetodoByGroup((current) => ({ ...current, [group.key]: Number(event.target.value) }))}
                          style={selectStyle}
                          className="admin-dark-select"
                        >
                          {metodosPago.map((metodo) => (
                            <option key={metodo.id} value={metodo.id}>{metodo.nombre}</option>
                          ))}
                        </select>
                        <button
                          type="button"
                          onClick={() => setPendingConfirm({ action: 'nota', group })}
                          style={checkoutButtonStyle}
                          disabled={selectedSet.size === 0 || isBusy}
                        >
                          {isBusy ? 'Procesando...' : 'Nota de entrega'}
                        </button>
                      </div>
                    </div>

                    <div style={docButtonsRowStyle(isMobile)}>
                      <button
                        type="button"
                        onClick={() => {
                          if (!validateClienteDocumento(group)) return;
                          handleGenerarPrefactura(group);
                        }}
                        style={secondaryButtonStyle}
                        disabled={selectedSet.size === 0 || isBusy}
                      >
                        {isBusy ? 'Generando...' : 'Pre-factura (vista previa)'}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          if (!validateClienteDocumento(group)) return;
                          setPendingConfirm({ action: 'factura', group });
                        }}
                        style={primaryButtonStyle}
                        disabled={selectedSet.size === 0 || isBusy}
                      >
                        {isBusy ? 'Emitiendo...' : 'Factura directa'}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div style={prefacturaPanelStyle}>
                    <div style={{ color: '#ffb0b0', fontWeight: 800, fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                      Pre-factura {prefactura.codigo}
                    </div>
                    <div style={{ color: '#d2c4c4', fontSize: 13 }}>
                      Cliente: {prefactura.cliente ? prefactura.cliente.nombre : 'Consumidor Final'}
                    </div>
                    <div style={{ display: 'grid', gap: 4 }}>
                      {prefactura.lineas.map((linea) => (
                        <div key={linea.id} style={lineaRowStyle}>
                          <span>{linea.cantidad}x {linea.descripcion}</span>
                          <span>{formatMontoDocumento(linea.subtotal, prefactura.moneda, prefactura.tasa_cambio_referencia || tasaCambio)}</span>
                        </div>
                      ))}
                    </div>
                    <div style={detailTotalsStyle}>
                      <span>Subtotal: {formatMontoDocumento(prefactura.subtotal, prefactura.moneda, prefactura.tasa_cambio_referencia || tasaCambio)}</span>
                      <span>IVA: {formatMontoDocumento(prefactura.total_iva, prefactura.moneda, prefactura.tasa_cambio_referencia || tasaCambio)}</span>
                      <span style={{ fontWeight: 800, color: '#fff' }}>Total: {formatMontoDocumento(prefactura.total, prefactura.moneda, prefactura.tasa_cambio_referencia || tasaCambio)}</span>
                    </div>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      <button
                        type="button"
                        onClick={() => handleDescartarPrefactura(group.key)}
                        style={secondaryButtonStyle}
                        disabled={isBusy}
                      >
                        Descartar (usar otra opción)
                      </button>
                      <button
                        type="button"
                        onClick={() => setPendingConfirm({ action: 'prefactura', group })}
                        style={primaryButtonStyle}
                        disabled={isBusy}
                      >
                        {isBusy ? 'Emitiendo...' : 'Confirmar y emitir factura'}
                      </button>
                    </div>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      ) : null}

      <div style={cuentasPorCobrarWrapStyle}>
        <CuentasPorCobrarPage isMobile={isMobile} embedded refreshToken={cuentasRefreshToken} />
      </div>

      <ConfirmModal
        open={Boolean(pendingConfirm)}
        title={confirmContent.title}
        message={confirmContent.message}
        confirmLabel={confirmContent.confirmLabel}
        busy={pendingConfirm ? busyGroup === pendingConfirm.group.key : false}
        onCancel={() => setPendingConfirm(null)}
        onConfirm={handleConfirmPendingAction}
      />
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

function renderDetailItemRow(item, tasaCambio) {
  const cantidadLabel = item.peso_gramos ? `${item.peso_gramos} g` : `${item.cantidad}x`;
  const lineTotal = item.subtotal !== undefined ? Number(item.subtotal) : Number(item.precio_unitario) * item.cantidad;
  return (
    <div key={item.id} style={detailItemRowStyle}>
      <span style={{ color: '#fff' }}>{cantidadLabel} {item.producto}</span>
      <span style={{ color: '#d2c4c4' }}>${item.precio_unitario}{item.venta_por_peso ? '/kg' : ' c/u'}</span>
      <span style={{ color: '#ffcf7d', fontWeight: 700 }}>
        ${lineTotal.toFixed(2)}
        <BsAmount amountUsd={lineTotal} tasa={tasaCambio} />
      </span>
    </div>
  );
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
  gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fill, minmax(360px, 1fr))',
  // Sin esto, CSS Grid estira cada tarjeta a la altura de la más alta de su
  // fila (comportamiento por defecto de `align-items: stretch`) — con mesas
  // de tamaños muy distintos (18 pedidos vs 2), la mesa chica queda con un
  // hueco enorme y sus pedidos/botones repartidos de forma rara. `start`
  // deja que cada tarjeta mida su propia altura según su contenido (ver
  // groupCardStyle), sin que la de al lado la afecte.
  alignItems: 'start',
  gap: 14,
});

const groupCardStyle = {
  display: 'flex',
  flexDirection: 'column',
  gap: 12,
  padding: '18px 18px',
  borderRadius: 20,
  background: 'linear-gradient(180deg, rgba(46, 25, 25, 0.95) 0%, rgba(24, 14, 14, 0.97) 100%)',
  border: '1px solid rgba(255, 255, 255, 0.14)',
  boxShadow: '0 12px 28px rgba(0,0,0,0.24)',
};

const groupHeaderStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 10,
  flexShrink: 0,
};

// Cada tarjeta mide lo que necesita su propio contenido — sin alto fijo ni
// scroll interno, así el botón de cobro queda siempre justo debajo del
// último pedido de esa mesa (nunca escondido detrás de un scroll interno).
// `align-items: start` en groupsGridStyle evita que una mesa con pocos
// pedidos se estire para igualar a la más alta de su fila.
const ordersScrollStyle = {
  display: 'flex',
  flexDirection: 'column',
  gap: 8,
};

const footerSectionStyle = {
  display: 'grid',
  gap: 12,
  flexShrink: 0,
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
  flexShrink: 0,
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

const platoGroupStyle = {
  display: 'grid',
  gap: 2,
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

const clienteFormStyle = (isMobile) => ({
  display: 'grid',
  gridTemplateColumns: isMobile ? '1fr' : '2fr 1.4fr 1fr',
  gap: 8,
});

const clienteHintStyle = {
  margin: 0,
  color: '#a89999',
  fontSize: 12,
};

const inputStyle = {
  width: '100%',
  boxSizing: 'border-box',
  borderRadius: 12,
  border: '1px solid rgba(255, 255, 255, 0.14)',
  background: '#161010',
  padding: '9px 10px',
  color: '#fff4f4',
  fontSize: 13,
};

const docButtonsRowStyle = (isMobile) => ({
  display: 'flex',
  gap: 8,
  flexWrap: 'wrap',
  flexDirection: isMobile ? 'column' : 'row',
});

const secondaryButtonStyle = {
  border: '1px solid rgba(255, 255, 255, 0.16)',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'rgba(255, 255, 255, 0.05)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
};

const primaryButtonStyle = {
  border: 'none',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)',
  color: '#fff',
  fontWeight: 800,
  cursor: 'pointer',
};

const prefacturaPanelStyle = {
  display: 'grid',
  gap: 8,
  padding: '12px 14px',
  borderRadius: 14,
  border: '1px solid rgba(255, 190, 120, 0.3)',
  background: 'rgba(255, 190, 120, 0.06)',
};

const lineaRowStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  fontSize: 13,
  color: '#e8dede',
};

const cuentasPorCobrarWrapStyle = {
  marginTop: 8,
  paddingTop: 20,
  borderTop: '1px solid rgba(255, 255, 255, 0.1)',
};

export default CheckoutPage;

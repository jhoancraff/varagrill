import { useCallback, useEffect, useMemo, useState } from 'react';
import BsAmount from './BsAmount';
import ConfirmModal from './ConfirmModal';
import CuentasPorCobrarPage from './CuentasPorCobrarPage';
import useMobileBackHandler from '../hooks/useMobileBackHandler';
import FacturasHistorialPage from './FacturasHistorialPage';
import NotasEntregaHistorialPage from './NotasEntregaHistorialPage';
import Toast from './Toast';
import useExchangeRate from '../hooks/useExchangeRate';
import useToast from '../hooks/useToast';
import { formatMontoDocumento } from '../utils/currency';

const emptyCliente = { nombre: '', tipo_documento: '', numero_documento: '' };

// El SENIAT aun esta homologando el sistema para facturacion fiscal (2026-09) —
// mientras tanto solo se puede cobrar con nota de entrega (sin efecto fiscal).
// Cuando el SENIAT apruebe, cambiar esto a `true` para reactivar pre-factura y
// factura directa; el resto del flujo de esos dos documentos sigue intacto,
// solo queda oculto detras de esta bandera.
const FACTURACION_HABILITADA = false;

function CheckoutPage({ isMobile, onBack, lastKitchenEvent, canCancelarPedidos = false }) {
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

  // Propinas y "pagos extra" (ver handleRegistrarIngresoExtra): dinero que la
  // cajera recibe junto con el cobro de la nota de entrega pero que no es parte
  // de la venta, así que se registra aparte en su propia cuenta.
  const [ingresoModalTipo, setIngresoModalTipo] = useState(null);
  const [ingresosExtra, setIngresosExtra] = useState([]);
  const [ingresosExtraLoading, setIngresosExtraLoading] = useState(true);
  const [ingresoSubmitting, setIngresoSubmitting] = useState(false);

  const fetchIngresosExtra = useCallback(async () => {
    try {
      const response = await fetch('/api/contabilidad/ingresos-extra/', { credentials: 'include', cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (response.ok && data.ok) {
        setIngresosExtra(Array.isArray(data.ingresos) ? data.ingresos : []);
      }
    } catch (requestError) {
      // La lista simplemente queda como estaba si falla; no bloquea el resto de Cobro.
    } finally {
      setIngresosExtraLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchIngresosExtra();
  }, [fetchIngresosExtra]);

  const handleRegistrarIngresoExtra = async ({ monto, descripcion, metodoPagoId }) => {
    const montoNumber = Number(monto);
    if (!montoNumber || montoNumber <= 0) {
      showError('Ingresa un monto válido.');
      return;
    }
    if (!metodoPagoId) {
      showError('Selecciona la cuenta donde se abonará el dinero.');
      return;
    }

    setIngresoSubmitting(true);
    try {
      const response = await fetch('/api/contabilidad/ingresos-extra/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') || '' },
        credentials: 'include',
        body: JSON.stringify({
          tipo: ingresoModalTipo,
          monto: montoNumber,
          descripcion,
          metodo_pago_id: Number(metodoPagoId),
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        showError(data.message || 'No se pudo registrar.');
        return;
      }
      showSuccess(data.message || 'Registrado correctamente.');
      setIngresoModalTipo(null);
      await fetchIngresosExtra();
    } catch (requestError) {
      showError('Error de red al registrar.');
    } finally {
      setIngresoSubmitting(false);
    }
  };

  const [busyGroup, setBusyGroup] = useState('');
  const { toast, showSuccess, showError, hideToast } = useToast();
  const [expandedOrderIds, setExpandedOrderIds] = useState(() => new Set());
  const [cuentasRefreshToken, setCuentasRefreshToken] = useState(0);
  const [notasRefreshToken, setNotasRefreshToken] = useState(0);
  const [pendingConfirm, setPendingConfirm] = useState(null);
  const [mesaQuery, setMesaQuery] = useState('');
  const [selectedGroupKey, setSelectedGroupKey] = useState('');

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

  // Mesas primero y ordenadas por numero, delivery/para-llevar al final — asi la
  // cajera encuentra las mesas donde suele mirar primero.
  const sortedGroups = [...groups].sort((a, b) => {
    const mesaA = a.pedidos[0] ? a.pedidos[0].mesa : null;
    const mesaB = b.pedidos[0] ? b.pedidos[0].mesa : null;
    if (mesaA != null && mesaB != null) return mesaA - mesaB;
    if (mesaA != null) return -1;
    if (mesaB != null) return 1;
    return a.label.localeCompare(b.label);
  });

  const mesaQueryTerm = mesaQuery.trim().toLowerCase();
  const filteredGroups = mesaQueryTerm
    ? sortedGroups.filter((group) => (
      group.label.toLowerCase().includes(mesaQueryTerm)
      || group.pedidos.some((pedido) => (pedido.cliente || '').toLowerCase().includes(mesaQueryTerm))
    ))
    : sortedGroups;

  const selectedGroup = groups.find((group) => group.key === selectedGroupKey) || null;
  const selectedSet = selectedGroup ? (selectedByGroup[selectedGroup.key] || new Set()) : new Set();
  const selectedTotal = selectedGroup
    ? selectedGroup.pedidos.filter((pedido) => selectedSet.has(pedido.id)).reduce((sum, pedido) => sum + Number(pedido.total), 0)
    : 0;
  const selectedGroupFullTotal = selectedGroup
    ? selectedGroup.pedidos.reduce((sum, pedido) => sum + Number(pedido.total), 0)
    : 0;
  const cliente = selectedGroup ? (clienteByGroup[selectedGroup.key] || emptyCliente) : emptyCliente;
  const prefactura = selectedGroup ? prefacturaByGroup[selectedGroup.key] : null;
  const isBusy = selectedGroup ? busyGroup === selectedGroup.key : false;

  // Si se cobraron (o cancelaron) todos los pedidos de la mesa seleccionada, el
  // grupo desaparece de `groups` en el proximo refresh — se limpia la seleccion
  // para que la cajera vuelva sola al buscador en vez de quedar viendo una
  // tarjeta vacia.
  useEffect(() => {
    if (selectedGroupKey && !groups.some((group) => group.key === selectedGroupKey)) {
      setSelectedGroupKey('');
    }
  }, [groups, selectedGroupKey]);

  const handleSelectGroup = (group) => {
    setSelectedGroupKey(group.key);
    setMesaQuery('');
  };

  const handleClearSelection = () => {
    setSelectedGroupKey('');
    setMesaQuery('');
  };

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
      showError(`Indica el tipo y número de documento del cliente de ${group.label} antes de generar la pre-factura o factura.`);
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

  // Cancelar un pedido individual desde caja (antes de cobrarlo) — solo visible para
  // quien puede hacerlo (ver canCancelarPedidos, resuelto en WelcomeScreen a partir
  // del rol). El backend vuelve a validar el permiso igual, esto es solo la UI.
  const handleCancelarPedido = async (pedido) => {
    setBusyGroup(`cancel-${pedido.id}`);
    try {
      const response = await fetch(`/api/pedidos/${pedido.id}/estado/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') || '' },
        credentials: 'include',
        body: JSON.stringify({ estado: 'cancelado' }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        showError(data.message || 'No se pudo cancelar el pedido.');
        return;
      }
      showSuccess(`Pedido #${pedido.id} cancelado.`);
      await fetchPedidos();
    } catch (requestError) {
      showError('Error de red al cancelar el pedido.');
    } finally {
      setBusyGroup('');
    }
  };

  // Valida antes de abrir el modal de confirmación (no dentro de handleNotaEntrega,
  // que ya corre DESPUÉS de que el usuario confirmó) — así "0 pedidos seleccionados"
  // o "sin método de pago" avisan de una con un toast arriba a la derecha, en vez de
  // abrir un "vas a cobrar 0 pedido(s) por $0.00" sin sentido o fallar en silencio.
  const handleClickNotaEntrega = (group) => {
    const selectedSet = selectedByGroup[group.key] || new Set();
    if (selectedSet.size === 0) {
      showError(`Selecciona al menos un pedido de ${group.label} para registrar la nota de entrega.`);
      return;
    }
    const metodoPagoId = metodoByGroup[group.key] || (metodosPago[0] && metodosPago[0].id);
    if (!metodoPagoId) {
      showError('No hay métodos de pago activos configurados.');
      return;
    }
    setPendingConfirm({ action: 'nota', group });
  };

  // --- Documento 1: Nota de entrega (cobro directo e inmediato, sin IVA ni numeracion fiscal) ---
  const handleNotaEntrega = async (group) => {
    const selectedIds = Array.from(selectedByGroup[group.key] || []);
    if (selectedIds.length === 0) {
      return;
    }
    const metodoPagoId = metodoByGroup[group.key] || (metodosPago[0] && metodosPago[0].id);
    if (!metodoPagoId) {
      showError('No hay metodos de pago activos configurados.');
      return;
    }

    setBusyGroup(group.key);
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
        showError(data.message || 'No se pudo procesar la nota de entrega.');
        await fetchPedidos();
        return;
      }

      showSuccess(
        `Nota de entrega ${data.nota_entrega.codigo} registrada: `
        + `${formatMontoDocumento(data.nota_entrega.total, data.nota_entrega.moneda, tasaCambio)} `
        + `(${data.nota_entrega.pedidos.length} pedido(s)). Pendiente de cobro — `
        + `abona desde el reporte de notas de entrega.`,
      );
      setNotasRefreshToken((current) => current + 1);
      clearGroupState(group.key);
      await fetchPedidos();
    } catch (requestError) {
      showError('Error de red al procesar la nota de entrega.');
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
        showError(data.message || 'No se pudo generar la pre-factura.');
        return;
      }
      showSuccess(`Pre-factura ${data.prefactura.codigo} generada. Revisa la cuenta con el cliente antes de confirmar.`);
      setPrefacturaByGroup((current) => ({ ...current, [group.key]: data.prefactura }));
    } catch (requestError) {
      showError('Error de red al generar la pre-factura.');
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
    try {
      const response = await fetch(`/api/prefacturas/${prefactura.id}/convertir/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') || '' },
        credentials: 'include',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        showError(data.message || 'No se pudo emitir la factura.');
        return;
      }
      showSuccess(
        `Factura Nº ${data.factura.numero_factura} emitida (Control ${data.factura.numero_control}). `
        + `Total ${formatMontoDocumento(data.factura.total, data.factura.moneda, data.factura.tasa_cambio_referencia || tasaCambio)} `
        + `— saldo pendiente ${formatMontoDocumento(data.factura.saldo_pendiente, data.factura.moneda, data.factura.tasa_cambio_referencia || tasaCambio)}. `
        + 'Cóbrala desde Cuentas por cobrar, abajo.',
      );
      clearGroupState(group.key);
      setCuentasRefreshToken((current) => current + 1);
      await fetchPedidos();
    } catch (requestError) {
      showError('Error de red al emitir la factura.');
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
        showError(data.message || 'No se pudo emitir la factura.');
        return;
      }
      showSuccess(
        `Factura Nº ${data.factura.numero_factura} emitida (Control ${data.factura.numero_control}). `
        + `Total ${formatMontoDocumento(data.factura.total, data.factura.moneda, data.factura.tasa_cambio_referencia || tasaCambio)} `
        + `— saldo pendiente ${formatMontoDocumento(data.factura.saldo_pendiente, data.factura.moneda, data.factura.tasa_cambio_referencia || tasaCambio)}. `
        + 'Cóbrala desde Cuentas por cobrar, abajo.',
      );
      clearGroupState(group.key);
      setCuentasRefreshToken((current) => current + 1);
      await fetchPedidos();
    } catch (requestError) {
      showError('Error de red al emitir la factura.');
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

    if (action === 'cancelar-pedido') {
      const { pedido } = pending;
      return {
        title: 'Cancelar pedido',
        message: `Vas a cancelar el pedido #${pedido.id} (${pedido.cliente || 'sin cliente'}, $${pedido.total}). Esta acción no se puede deshacer. ¿Confirmas?`,
        confirmLabel: 'Sí, cancelar pedido',
      };
    }

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
    const metodoSeleccionadoId = metodoByGroup[group.key] || (metodosPago[0] && metodosPago[0].id);
    const metodoSeleccionado = metodosPago.find((metodo) => metodo.id === metodoSeleccionadoId);
    const totalLabel = formatMontoDocumento(selectedTotal, metodoSeleccionado ? metodoSeleccionado.moneda : 'USD', tasaCambio);

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
  // Misma llave que usan busyGroup/setBusyGroup para marcar "ocupado" según la
  // acción pendiente: por grupo (group.key) para nota/pre-factura/factura, o por
  // pedido individual (cancel-<id>) para cancelar-pedido — ver handleCancelarPedido.
  const pendingConfirmBusyKey = pendingConfirm
    ? (pendingConfirm.group ? pendingConfirm.group.key : `cancel-${pendingConfirm.pedido.id}`)
    : null;

  const handleConfirmPendingAction = async () => {
    if (!pendingConfirm) {
      return;
    }
    const { action, group, pedido } = pendingConfirm;
    if (action === 'nota') {
      await handleNotaEntrega(group);
    } else if (action === 'factura') {
      await handleFacturaDirecta(group);
    } else if (action === 'prefactura') {
      await handleConfirmarFacturaDesdePrefactura(group);
    } else if (action === 'cancelar-pedido') {
      await handleCancelarPedido(pedido);
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
            Busca la mesa para ver su cuenta. Por cada mesa elige el documento que convenga: una nota de
            entrega rápida, una pre-factura para que el cliente revise la cuenta, o la factura fiscal directa.
          </p>
        </div>
        <button type="button" onClick={onBack} style={backButtonStyle(isMobile)}>
          Volver
        </button>
      </div>

      <Toast toast={toast} onClose={hideToast} />

      {loading ? <div style={emptyStateStyle}>Cargando pedidos...</div> : null}
      {!loading && error ? <div style={errorStyle}>{error}</div> : null}

      {!loading && !error && groups.length === 0 ? (
        <div style={emptyStateStyle}>No hay pedidos listos para cobrar en este momento.</div>
      ) : null}

      {!loading && !error && groups.length > 0 ? (
        <div style={cobroPickerWrapStyle}>
          <div style={mesaSearchBoxStyle}>
            <input
              type="text"
              value={mesaQuery}
              onChange={(event) => setMesaQuery(event.target.value)}
              placeholder="Buscar mesa por número o por cliente..."
              style={mesaSearchInputStyle}
            />

            {!selectedGroup || mesaQueryTerm ? (
              <div style={mesaOptionsListStyle}>
                {filteredGroups.length === 0 ? (
                  <div style={mesaOptionEmptyStyle}>No se encontraron mesas con ese criterio.</div>
                ) : (
                  filteredGroups.map((group) => {
                    const groupTotal = group.pedidos.reduce((sum, pedido) => sum + Number(pedido.total), 0);
                    const isCurrent = selectedGroup && selectedGroup.key === group.key;
                    return (
                      <button
                        key={group.key}
                        type="button"
                        onClick={() => handleSelectGroup(group)}
                        style={isCurrent ? mesaOptionRowActiveStyle : mesaOptionRowStyle}
                      >
                        <span style={{ fontWeight: 700, color: '#fff' }}>{group.label}</span>
                        <span style={mesaOptionMetaStyle}>{group.pedidos.length} pedido(s) · ${groupTotal.toFixed(2)}</span>
                      </button>
                    );
                  })
                )}
              </div>
            ) : (
              <button type="button" onClick={handleClearSelection} style={selectedMesaChipStyle}>
                <span style={{ fontWeight: 700, color: '#fff' }}>{selectedGroup.label}</span>
                <span style={mesaOptionMetaStyle}>
                  {selectedGroup.pedidos.length} pedido(s) · ${selectedGroupFullTotal.toFixed(2)}
                </span>
                <span style={selectedMesaChipClearStyle}>Cambiar ✕</span>
              </button>
            )}
          </div>

          {selectedGroup ? (
            <article style={groupCardStyle}>
                <div style={groupHeaderStyle}>
                  <div style={{ color: '#fff', fontWeight: 700, fontSize: 17 }}>{selectedGroup.label}</div>
                  <span style={groupCountStyle}>{selectedGroup.pedidos.length} pedido(s)</span>
                </div>

                <div style={ordersScrollStyle}>
                  {selectedGroup.pedidos.map((pedido) => {
                    const isExpanded = expandedOrderIds.has(pedido.id);
                    const items = Array.isArray(pedido.items) ? pedido.items : [];
                    const itemsWithNotes = items.filter((item) => item.notas);

                    return (
                      <div key={pedido.id} style={orderCardStyle}>
                        <div style={orderRowStyle}>
                          <div style={orderRowTopStyle}>
                            <label style={orderCheckboxLabelStyle}>
                              <input
                                type="checkbox"
                                checked={selectedSet.has(pedido.id)}
                                onChange={() => toggleSelection(selectedGroup.key, pedido.id)}
                              />
                              <span style={orderTitleStyle}>Pedido #{pedido.id}</span>
                            </label>
                            <span style={orderPriceStyle}>
                              ${pedido.total}
                              <BsAmount amountUsd={pedido.total} tasa={tasaCambio} />
                            </span>
                          </div>
                          <div style={orderRowBottomStyle}>
                            <span style={orderMetaStyle}>
                              {pedido.cliente || 'Sin cliente'} · {pedido.mesero} · {formatOrderTime(pedido.creado_en)}
                            </span>
                            <span style={orderActionsStyle}>
                              <button type="button" onClick={() => toggleExpanded(pedido.id)} style={detailToggleStyle}>
                                {isExpanded ? 'Ocultar' : 'Detalle'}
                              </button>
                              {canCancelarPedidos ? (
                                <button
                                  type="button"
                                  onClick={() => setPendingConfirm({ action: 'cancelar-pedido', pedido })}
                                  style={cancelOrderToggleStyle}
                                  disabled={busyGroup === `cancel-${pedido.id}`}
                                >
                                  Cancelar
                                </button>
                              ) : null}
                            </span>
                          </div>
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
                    <div style={clienteFormStyle}>
                      <input
                        placeholder="Cliente (opcional)"
                        value={cliente.nombre}
                        onChange={(event) => updateCliente(selectedGroup.key, 'nombre', event.target.value)}
                        style={inputStyle}
                      />
                      <select
                        value={cliente.tipo_documento}
                        onChange={(event) => updateCliente(selectedGroup.key, 'tipo_documento', event.target.value)}
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
                        onChange={(event) => updateCliente(selectedGroup.key, 'numero_documento', event.target.value)}
                        style={inputStyle}
                      />
                    </div>
                    <p style={clienteHintStyle}>
                      {FACTURACION_HABILITADA
                        ? 'El tipo y número de documento son obligatorios para generar factura fiscal (no aplica a la pre-factura ni a la nota de entrega).'
                        : 'Opcional: solo para que el nombre del cliente aparezca en la pre-factura que se le entrega.'}
                    </p>

                    <div style={groupFooterStyle(isMobile)}>
                      <div style={{ color: '#fff', fontWeight: 700 }}>
                        Total seleccionado: ${selectedTotal.toFixed(2)}
                        <BsAmount amountUsd={selectedTotal} tasa={tasaCambio} />
                      </div>
                      <select
                        value={metodoByGroup[selectedGroup.key] || (metodosPago[0] && metodosPago[0].id) || ''}
                        onChange={(event) => setMetodoByGroup((current) => ({ ...current, [selectedGroup.key]: Number(event.target.value) }))}
                        style={selectStyle}
                        className="admin-dark-select"
                      >
                        {metodosPago.map((metodo) => (
                          <option key={metodo.id} value={metodo.id}>{metodo.nombre}</option>
                        ))}
                      </select>
                    </div>

                    <div style={docButtonsRowStyle(isMobile)}>
                      <button
                        type="button"
                        onClick={() => handleClickNotaEntrega(selectedGroup)}
                        style={checkoutButtonStyle}
                        disabled={isBusy}
                      >
                        {isBusy ? 'Procesando...' : 'Nota de entrega'}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleGenerarPrefactura(selectedGroup)}
                        style={secondaryButtonStyle}
                        disabled={selectedSet.size === 0 || isBusy}
                      >
                        {isBusy ? 'Generando...' : 'Pre-factura (vista previa)'}
                      </button>
                      {FACTURACION_HABILITADA ? (
                        <button
                          type="button"
                          onClick={() => {
                            if (!validateClienteDocumento(selectedGroup)) return;
                            setPendingConfirm({ action: 'factura', group: selectedGroup });
                          }}
                          style={primaryButtonStyle}
                          disabled={selectedSet.size === 0 || isBusy}
                        >
                          {isBusy ? 'Emitiendo...' : 'Factura directa'}
                        </button>
                      ) : null}
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
                      <span style={{ fontWeight: 800, color: '#fff' }}>Total: {formatMontoDocumento(prefactura.total, prefactura.moneda, prefactura.tasa_cambio_referencia || tasaCambio)}</span>
                    </div>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      <button
                        type="button"
                        onClick={() => handleDescartarPrefactura(selectedGroup.key)}
                        style={secondaryButtonStyle}
                        disabled={isBusy}
                      >
                        Descartar (usar otra opción)
                      </button>
                      <button
                        type="button"
                        onClick={() => handleClickNotaEntrega(selectedGroup)}
                        style={checkoutButtonStyle}
                        disabled={isBusy}
                      >
                        {isBusy ? 'Procesando...' : 'Nota de entrega'}
                      </button>
                      {FACTURACION_HABILITADA ? (
                        <button
                          type="button"
                          onClick={() => setPendingConfirm({ action: 'prefactura', group: selectedGroup })}
                          style={primaryButtonStyle}
                          disabled={isBusy}
                        >
                          {isBusy ? 'Emitiendo...' : 'Confirmar y emitir factura'}
                        </button>
                      ) : null}
                    </div>
                  </div>
                )}
            </article>
          ) : null}
        </div>
      ) : null}

      <div style={cuentasPorCobrarWrapStyle}>
        <NotasEntregaHistorialPage isMobile={isMobile} embedded refreshToken={notasRefreshToken} />
      </div>

      <div style={cuentasPorCobrarWrapStyle}>
        <div style={ingresoExtraButtonsRowStyle(isMobile)}>
          <button type="button" onClick={() => setIngresoModalTipo('propina')} style={propinaButtonStyle}>
            + Registrar propina
          </button>
          <button type="button" onClick={() => setIngresoModalTipo('pago_extra')} style={pagoExtraButtonStyle}>
            + Pago extra
          </button>
        </div>
        <p style={ingresoExtraHintStyle}>
          Para cuando el cliente paga todo junto (la nota de entrega más la propina, o de más porque redondeó):
          cobra la nota solo por el total de los platos y registra la propina o el excedente acá, en la cuenta
          donde de verdad quedó ese dinero.
        </p>

        <div style={ingresoExtraHistoryTitleStyle}>Propinas y pagos extra registrados</div>
        {ingresosExtraLoading ? (
          <div style={emptyStateStyle}>Cargando...</div>
        ) : ingresosExtra.length === 0 ? (
          <div style={emptyStateStyle}>Todavía no se ha registrado ninguna propina ni pago extra.</div>
        ) : (
          <div style={{ display: 'grid', gap: 8 }}>
            {ingresosExtra.map((ingreso) => (
              <div key={ingreso.id} style={ingresoHistoryRowStyle}>
                <span style={ingreso.tipo === 'propina' ? propinaTagStyle : pagoExtraTagStyle}>
                  {ingreso.tipo_label}
                </span>
                <span style={{ color: '#fff', fontWeight: 700 }}>${Number(ingreso.monto).toFixed(2)}</span>
                <span style={{ color: '#d2c4c4', fontSize: 12 }}>{ingreso.metodo_pago_nombre}</span>
                {ingreso.descripcion ? (
                  <span style={{ color: '#d2c4c4', fontSize: 12 }}>{ingreso.descripcion}</span>
                ) : null}
                <span style={{ color: '#a89999', fontSize: 11, marginLeft: 'auto' }}>
                  {ingreso.registrado_por} · {formatFechaHora(ingreso.fecha_creacion)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={cuentasPorCobrarWrapStyle}>
        <CuentasPorCobrarPage isMobile={isMobile} embedded refreshToken={cuentasRefreshToken} />
      </div>

      <div style={cuentasPorCobrarWrapStyle}>
        <FacturasHistorialPage isMobile={isMobile} embedded />
      </div>

      <ConfirmModal
        open={Boolean(pendingConfirm)}
        title={confirmContent.title}
        message={confirmContent.message}
        confirmLabel={confirmContent.confirmLabel}
        busy={pendingConfirm ? busyGroup === pendingConfirmBusyKey : false}
        onCancel={() => setPendingConfirm(null)}
        onConfirm={handleConfirmPendingAction}
      />

      {ingresoModalTipo ? (
        <IngresoExtraModal
          tipo={ingresoModalTipo}
          metodosPago={metodosPago}
          submitting={ingresoSubmitting}
          onClose={() => setIngresoModalTipo(null)}
          onSubmit={handleRegistrarIngresoExtra}
        />
      ) : null}
    </section>
  );
}

function IngresoExtraModal({ tipo, metodosPago, submitting, onClose, onSubmit }) {
  // Solo se monta mientras hay un tipo elegido, así que montado == abierto.
  useMobileBackHandler(true, onClose);
  const [monto, setMonto] = useState('');
  const [descripcion, setDescripcion] = useState('');
  const [metodoPagoId, setMetodoPagoId] = useState('');

  const esPropina = tipo === 'propina';

  return (
    <div style={ingresoModalBackdropStyle} onClick={submitting ? undefined : onClose}>
      <div style={ingresoModalCardStyle} onClick={(event) => event.stopPropagation()}>
        <button type="button" onClick={onClose} style={modalCloseButtonStyle} aria-label="Cerrar" disabled={submitting}>
          ×
        </button>
        <div style={ingresoModalTitleStyle}>
          {esPropina ? 'Registrar propina' : 'Registrar pago extra'}
        </div>
        <p style={ingresoModalDescStyle}>
          {esPropina
            ? 'La propina que el cliente pagó junto con la nota de entrega, para los meseros.'
            : 'El excedente que el cliente pagó de más (redondeó el total) y no pidió de vuelta.'}
        </p>

        <label style={ingresoFieldLabelStyle}>
          Monto ($)
          <input
            type="number"
            min="0.01"
            step="0.01"
            value={monto}
            onChange={(event) => setMonto(event.target.value)}
            style={ingresoInputStyle}
            placeholder="0.00"
            autoFocus
          />
        </label>

        <label style={ingresoFieldLabelStyle}>
          Descripción (opcional)
          <input
            type="text"
            value={descripcion}
            onChange={(event) => setDescripcion(event.target.value)}
            style={ingresoInputStyle}
            placeholder={esPropina ? 'Ej: Propina Mesa 4' : 'Ej: Redondeo Mesa 4'}
          />
        </label>

        <label style={ingresoFieldLabelStyle}>
          Cuenta donde se abonará
          <select
            value={metodoPagoId}
            onChange={(event) => setMetodoPagoId(event.target.value)}
            style={ingresoInputStyle}
            className="admin-dark-select"
          >
            <option value="">Selecciona una cuenta...</option>
            {metodosPago.map((metodo) => (
              <option key={metodo.id} value={metodo.id}>{metodo.nombre}</option>
            ))}
          </select>
        </label>

        <div style={ingresoModalFooterStyle}>
          <button type="button" onClick={onClose} style={secondaryButtonStyle} disabled={submitting}>
            Cancelar
          </button>
          <button
            type="button"
            onClick={() => onSubmit({ monto, descripcion, metodoPagoId })}
            style={esPropina ? propinaButtonStyle : pagoExtraButtonStyle}
            disabled={submitting}
          >
            {submitting ? 'Registrando...' : 'Registrar'}
          </button>
        </div>
      </div>
    </div>
  );
}

function formatFechaHora(fechaIso) {
  const date = new Date(fechaIso);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  return date.toLocaleString('es-ES', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
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

const cobroPickerWrapStyle = {
  display: 'grid',
  gap: 14,
  maxWidth: 640,
};

const mesaSearchBoxStyle = {
  display: 'grid',
  gap: 8,
};

const mesaSearchInputStyle = {
  width: '100%',
  boxSizing: 'border-box',
  borderRadius: 14,
  border: '1px solid rgba(255, 255, 255, 0.16)',
  background: '#161010',
  padding: '12px 14px',
  color: '#fff4f4',
  fontSize: 15,
};

const mesaOptionsListStyle = {
  display: 'grid',
  gap: 6,
  maxHeight: 360,
  overflowY: 'auto',
};

const mesaOptionRowStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 10,
  width: '100%',
  textAlign: 'left',
  border: '1px solid rgba(255, 255, 255, 0.1)',
  borderRadius: 14,
  padding: '12px 14px',
  background: 'rgba(255, 255, 255, 0.03)',
  color: '#fff',
  cursor: 'pointer',
};

const mesaOptionRowActiveStyle = {
  ...mesaOptionRowStyle,
  border: '1px solid rgba(52, 211, 153, 0.5)',
  background: 'rgba(52, 211, 153, 0.08)',
};

const mesaOptionMetaStyle = {
  color: '#ffcf7d',
  fontSize: 13,
  fontWeight: 700,
  flexShrink: 0,
};

const mesaOptionEmptyStyle = {
  padding: 14,
  borderRadius: 14,
  border: '1px dashed rgba(255, 255, 255, 0.14)',
  color: '#c8bbbb',
  textAlign: 'center',
  fontSize: 13,
};

const selectedMesaChipStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 10,
  width: '100%',
  textAlign: 'left',
  border: '1px solid rgba(255, 255, 255, 0.16)',
  borderRadius: 14,
  padding: '12px 14px',
  background: 'rgba(255, 255, 255, 0.05)',
  cursor: 'pointer',
};

const selectedMesaChipClearStyle = {
  color: '#ffb0b0',
  fontSize: 12,
  fontWeight: 700,
  flexShrink: 0,
};

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

// La tarjeta mide lo que necesita su propio contenido — sin alto fijo ni
// scroll interno, así el botón de cobro queda siempre justo debajo del
// último pedido de esa mesa (nunca escondido detrás de un scroll interno).
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
  flexDirection: 'column',
  gap: 6,
  padding: '10px 12px',
};

// Fila superior (checkbox + numero de pedido + precio) y fila inferior (meta +
// acciones) van cada una en su propio flex — así el precio y los botones nunca
// quedan flotando en el medio de un bloque de texto envuelto en varias líneas
// (pasaba cuando cliente/mesero/hora no cabían junto al resto en una sola fila
// sin wrap: el checkbox y el precio se centraban verticalmente contra ese texto
// envuelto en vez de quedar alineados con su primera línea).
const orderRowTopStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 10,
};

const orderCheckboxLabelStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  minWidth: 0,
  cursor: 'pointer',
};

const orderTitleStyle = {
  color: '#fff',
  fontWeight: 600,
};

const orderPriceStyle = {
  color: '#ffcf7d',
  fontWeight: 700,
  flexShrink: 0,
  whiteSpace: 'nowrap',
};

const orderRowBottomStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  flexWrap: 'wrap',
  gap: 8,
};

const orderMetaStyle = {
  color: '#d2c4c4',
  fontSize: 12,
  minWidth: 0,
};

const orderActionsStyle = {
  display: 'flex',
  gap: 6,
  flexShrink: 0,
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

const cancelOrderToggleStyle = {
  border: '1px solid rgba(255, 102, 102, 0.45)',
  borderRadius: 999,
  padding: '5px 12px',
  background: 'rgba(255, 73, 73, 0.1)',
  color: '#ffb3b3',
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

const clienteFormStyle = {
  display: 'grid',
  gridTemplateColumns: '1fr',
  gap: 8,
};

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

const ingresoExtraButtonsRowStyle = (isMobile) => ({
  display: 'flex',
  gap: 10,
  flexWrap: 'wrap',
  flexDirection: isMobile ? 'column' : 'row',
});

// Violeta para propina y verde azulado para pago extra — colores que no usa
// ningún otro botón de Cobro (verde = nota de entrega, rojo = factura, ámbar =
// cambiar mesa en Mesas atendidas) para que se distingan a simple vista.
const propinaButtonStyle = {
  border: 'none',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'linear-gradient(90deg, #6d28d9 0%, #a78bfa 100%)',
  color: '#fff',
  fontWeight: 800,
  cursor: 'pointer',
};

const pagoExtraButtonStyle = {
  border: 'none',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'linear-gradient(90deg, #0d9488 0%, #2dd4bf 100%)',
  color: '#04201c',
  fontWeight: 800,
  cursor: 'pointer',
};

const ingresoExtraHintStyle = {
  margin: '10px 0 0',
  color: '#a89999',
  fontSize: 12,
  lineHeight: 1.5,
  maxWidth: 640,
};

const ingresoExtraHistoryTitleStyle = {
  marginTop: 18,
  color: '#ffb0b0',
  fontSize: 12,
  fontWeight: 800,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
};

const ingresoHistoryRowStyle = {
  display: 'flex',
  flexWrap: 'wrap',
  alignItems: 'center',
  gap: 10,
  borderRadius: 12,
  border: '1px solid rgba(255, 255, 255, 0.1)',
  background: 'rgba(255, 255, 255, 0.03)',
  padding: '10px 12px',
};

const propinaTagStyle = {
  borderRadius: 999,
  padding: '3px 10px',
  fontSize: 11,
  fontWeight: 800,
  textTransform: 'uppercase',
  color: '#d9c8ff',
  background: 'rgba(139, 92, 246, 0.18)',
  border: '1px solid rgba(167, 139, 250, 0.4)',
};

const pagoExtraTagStyle = {
  borderRadius: 999,
  padding: '3px 10px',
  fontSize: 11,
  fontWeight: 800,
  textTransform: 'uppercase',
  color: '#b6fff0',
  background: 'rgba(13, 148, 136, 0.18)',
  border: '1px solid rgba(45, 212, 191, 0.4)',
};

const ingresoModalBackdropStyle = {
  position: 'fixed',
  inset: 0,
  zIndex: 1000,
  background: 'rgba(0, 0, 0, 0.6)',
  display: 'grid',
  placeItems: 'center',
  padding: 16,
};

const ingresoModalCardStyle = {
  position: 'relative',
  width: '100%',
  maxWidth: 420,
  borderRadius: 20,
  border: '1px solid rgba(255, 145, 145, 0.3)',
  background: 'linear-gradient(180deg, rgba(28, 12, 12, 0.98) 0%, rgba(10, 8, 8, 0.99) 100%)',
  padding: '22px 22px 18px',
  boxShadow: '0 20px 50px rgba(0, 0, 0, 0.45)',
  display: 'grid',
  gap: 12,
};

const modalCloseButtonStyle = {
  position: 'absolute',
  top: 10,
  right: 10,
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

const ingresoModalTitleStyle = {
  color: '#fff',
  fontSize: 19,
  fontWeight: 800,
  paddingRight: 30,
};

const ingresoModalDescStyle = {
  margin: 0,
  color: '#d2c3c3',
  lineHeight: 1.5,
  fontSize: 13,
};

const ingresoFieldLabelStyle = {
  display: 'grid',
  gap: 6,
  color: '#e8dede',
  fontSize: 13,
  fontWeight: 700,
};

const ingresoInputStyle = {
  width: '100%',
  boxSizing: 'border-box',
  borderRadius: 12,
  border: '1px solid rgba(255, 255, 255, 0.14)',
  background: '#161010',
  padding: '10px 12px',
  color: '#fff4f4',
  fontSize: 14,
  fontWeight: 400,
};

const ingresoModalFooterStyle = {
  display: 'flex',
  justifyContent: 'flex-end',
  gap: 10,
  marginTop: 6,
  flexWrap: 'wrap',
};

export default CheckoutPage;

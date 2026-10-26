import { useCallback, useEffect, useMemo, useState } from 'react';
import BsAmount from './BsAmount';
import AjustePedidoModal from './AjustePedidoModal';
import ConfirmModal from './ConfirmModal';
import CuentasPorCobrarPage from './CuentasPorCobrarPage';
import useMobileBackHandler from '../hooks/useMobileBackHandler';
import FacturasHistorialPage from './FacturasHistorialPage';
import MoneyInput from './MoneyInput';
import NotasEntregaHistorialPage from './NotasEntregaHistorialPage';
import Toast from './Toast';
import './CheckoutPage.css';
import useExchangeRate from '../hooks/useExchangeRate';
import useToast from '../hooks/useToast';
import { formatBs, formatMontoDocumento } from '../utils/currency';

const emptyCliente = { nombre: '', tipo_documento: '', numero_documento: '' };
const emptyNotaCliente = { cedula: '', apellido: '', nombre: '' };

// El SENIAT aun esta homologando el sistema para facturacion fiscal (2026-09) —
// mientras tanto solo se puede cobrar con nota de entrega (sin efecto fiscal).
// Cuando el SENIAT apruebe, cambiar esto a `true` para reactivar pre-factura y
// factura directa; el resto del flujo de esos dos documentos sigue intacto,
// solo queda oculto detras de esta bandera.
const FACTURACION_HABILITADA = false;

function formatTasa(valor) {
  const numero = Number(valor);
  return Number.isFinite(numero) ? numero.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 4 }) : '';
}

function CheckoutPage({ isMobile, onBack, lastKitchenEvent, canCancelarPedidos = false, canGestionarItems = false, mesasCatalogo = [], onArmarCanje }) {
  const tasaCambio = useExchangeRate();
  const [pedidos, setPedidos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedByGroup, setSelectedByGroup] = useState({});
  const [metodoByGroup, setMetodoByGroup] = useState({});
  const [clienteByGroup, setClienteByGroup] = useState({});
  // Cliente de la NOTA DE ENTREGA — aparte de `clienteByGroup` (que sigue
  // siendo el de pre-factura/factura, con su selector de tipo de documento
  // para poder registrar RIF de empresa): acá siempre es cédula (V), la
  // cajera anota primero el número y el nombre se autocompleta solo si ya
  // existe ese cliente (ver buscarClientePorCedula/pedidos_cobro_view).
  const [notaClienteByGroup, setNotaClienteByGroup] = useState({});
  const [prefacturaByGroup, setPrefacturaByGroup] = useState({});
  // Pre-facturas (cuentas del cliente) cuya tasa sigue vigente — ver tasa_cuenta.py: mientras la cuenta que se le
  // dio al cliente este dentro de la ventana, la nota de entrega nace con ESA tasa, aunque la BCV cambie.
  const [prefacturasTasa, setPrefacturasTasa] = useState([]);
  const [usarTasaActualByGroup, setUsarTasaActualByGroup] = useState({});
  // Descuento manual opcional al cobrar (ver pedidos_cobro_view/VGNotaEntrega):
  // se activa con un check que primero pide confirmación (por eso el estado
  // guarda si ya está desbloqueado, no solo si el checkbox está marcado — ver
  // handleActivarDescuento/handleDesactivarDescuento). Vacío = sin descuento,
  // se cobra el total completo; el motivo es obligatorio si hay monto.
  const [descuentoActivoByGroup, setDescuentoActivoByGroup] = useState({});
  const [descuentoMontoByGroup, setDescuentoMontoByGroup] = useState({});
  const [descuentoMotivoByGroup, setDescuentoMotivoByGroup] = useState({});
  const [metodosPago, setMetodosPago] = useState([]);
  const [ajusteModal, setAjusteModal] = useState(null); // { modo, item, pedidoId, mesaActualId }
  const [ajusteBusy, setAjusteBusy] = useState(false);
  const [ajusteError, setAjusteError] = useState('');
  const [requiereUsuarioMover, setRequiereUsuarioMover] = useState(false);
  const [meserosDisponibles, setMeserosDisponibles] = useState([]);

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

  const handleRegistrarIngresoExtra = async ({ monto, descripcion, metodoPagoId, notaEntregaId }) => {
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
          nota_entrega_id: notaEntregaId ? Number(notaEntregaId) : null,
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
  // Pestaña activa de la pantalla: 'cobro' | 'notas' | 'propinas' | 'cuentas' | 'facturas'.
  const [activeTab, setActiveTab] = useState('cobro');

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
      setPrefacturasTasa(Array.isArray(data.prefacturas_tasa_vigente) ? data.prefacturas_tasa_vigente : []);
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

  // Precargada de una vez (no al abrir el modal de mover) para que el selector de
  // mesero nunca aparezca vacío por timing — ver AjustePedidoModal/cargarMeserosDisponibles.
  useEffect(() => {
    if (!canGestionarItems) return;
    cargarMeserosDisponibles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canGestionarItems]);

  // Quitar (completo o solo parte de la cantidad) o mover a otra mesa un item mal
  // comandado — mismo patrón que MesasAtendidasPage (ver AjustePedidoModal), pero acá
  // no hay un "detailPedido" propio que parchear: el detalle es solo una expansión
  // local de lo que ya trae /api/pedidos/cobro/, así que tras el ajuste se refresca
  // toda la lista (fetchPedidos) para no arrastrar un shape de respuesta distinto
  // (pedido_detalle_eliminar_view usa producto_nombre; esta pantalla usa producto).
  const abrirAjuste = (modo, item, pedido) => {
    setAjusteError('');
    setRequiereUsuarioMover(false);
    setAjusteModal({
      modo,
      pedidoId: pedido.id,
      mesaActualId: pedido.mesa_id,
      item: { id: item.id, nombre: item.producto, cantidad: item.cantidad, esPorPeso: Boolean(item.peso_gramos) },
    });
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
      await fetchPedidos();
    } catch (requestError) {
      setAjusteError('Error de red al quitar el item.');
    } finally {
      setAjusteBusy(false);
    }
  };

  // Si la mesa destino no tiene pedido abierto, el backend no lo trata como error:
  // responde requiere_usuario para que se elija a qué mesero se le abre esa mesa
  // (ver pedido_detalle_mover_view) — acá eso NO se muestra como ajusteError (rojo),
  // sino que revela el selector de mesero dentro del mismo modal para reintentar.
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
      await fetchPedidos();
    } catch (requestError) {
      setAjusteError('Error de red al mover el item.');
    } finally {
      setAjusteBusy(false);
    }
  };

  // Las mesas agrupan por número de mesa (varias rondas de la misma mesa ya
  // caían solas en el mismo grupo). Delivery/para-llevar no tenían ese ancla:
  // cada ronda nueva creaba un pedido con su propio id, y cada una aparecía
  // como una cuenta aparte — la cajera terminaba cobrando dos veces y sumando
  // a mano. Se agrupa por `grupo_id` (grupo_pedido_id o, si el pedido es su
  // propia ancla, su propio id — ver pedido_create_view/pedidos_cobro_view),
  // el mismo ancla explícita que arma "Agregar ronda" en DeliveryPage. A
  // propósito NO se agrupa por cliente: dos clientes distintos pueden
  // compartir nombre (y no siempre traen cédula), lo que mezclaría sus
  // pedidos en una sola cuenta.
  const groups = useMemo(() => {
    const map = new Map();
    pedidos.forEach((pedido) => {
      const key = pedido.mesa ? `mesa-${pedido.mesa}` : `grupo-${pedido.grupo_id}`;
      if (!map.has(key)) {
        const label = pedido.mesa
          ? `Mesa ${pedido.mesa}`
          : `${pedido.tipo_pedido === 'delivery' ? 'Delivery' : 'Para llevar'} · ${pedido.cliente || `Pedido #${pedido.id}`}`;
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

  // Cuenta (pre-factura) vigente que cubre TODOS los pedidos seleccionados de un grupo, o null.
  const tasaCuentaDelGrupo = (group) => {
    const ids = Array.from(selectedByGroup[group.key] || []);
    if (ids.length === 0) return null;
    return prefacturasTasa.find((cuenta) => ids.every((id) => cuenta.pedido_ids.includes(id))) || null;
  };
  // Tasa con la que se muestran y se cobran los Bs de ese grupo: la de la cuenta mientras valga, o la actual.
  const tasaDelGrupo = (group) => {
    const cuenta = tasaCuentaDelGrupo(group);
    return cuenta && !usarTasaActualByGroup[group.key] ? Number(cuenta.tasa) : tasaCambio;
  };

  const selectedGroup = groups.find((group) => group.key === selectedGroupKey) || null;
  const selectedSet = selectedGroup ? (selectedByGroup[selectedGroup.key] || new Set()) : new Set();
  const selectedTotal = selectedGroup
    ? selectedGroup.pedidos.filter((pedido) => selectedSet.has(pedido.id)).reduce((sum, pedido) => sum + Number(pedido.total), 0)
    : 0;
  const selectedGroupFullTotal = selectedGroup
    ? selectedGroup.pedidos.reduce((sum, pedido) => sum + Number(pedido.total), 0)
    : 0;
  const tasaCuenta = selectedGroup ? tasaCuentaDelGrupo(selectedGroup) : null;
  const usarTasaActual = selectedGroup ? Boolean(usarTasaActualByGroup[selectedGroup.key]) : false;
  const tasaGrupo = selectedGroup ? tasaDelGrupo(selectedGroup) : tasaCambio;
  const cliente = selectedGroup ? (clienteByGroup[selectedGroup.key] || emptyCliente) : emptyCliente;
  // Lo que escribió el mesero al tomar el pedido (cédula y nombre del cliente) llega
  // precargado a la caja; la cajera solo lo edita si hace falta. Una vez que ella
  // toca algún campo, manda lo que haya en notaClienteByGroup.
  const clienteDelMesero = (group) => {
    const pedidoConCedula = group.pedidos.find((pedido) => pedido.cliente_cedula);
    const origen = pedidoConCedula || group.pedidos.find((pedido) => pedido.cliente) || null;
    if (!origen) {
      return emptyNotaCliente;
    }
    return {
      cedula: origen.cliente_cedula || '',
      apellido: origen.cliente_apellido || '',
      nombre: origen.cliente || '',
    };
  };
  const notaClienteDe = (group) => notaClienteByGroup[group.key] || clienteDelMesero(group);
  const notaCliente = selectedGroup ? notaClienteDe(selectedGroup) : emptyNotaCliente;
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

  const selectAllInGroup = (group) => {
    setSelectedByGroup((current) => ({
      ...current,
      [group.key]: new Set(group.pedidos.map((pedido) => pedido.id)),
    }));
  };

  // Si al momento de cobrar (nota de entrega, pre-factura o factura directa)
  // quedan pedidos de la mesa sin marcar, es fácil que sea un olvido (un
  // pedido llegó después y no se seleccionó) y no una decisión a propósito —
  // se pide confirmar antes de seguir, para evitar dejar pedidos sin cobrar
  // por error humano. Con selección vacía o completa no interrumpe: el caso
  // vacío ya lo bloquean los propios handlers de cada acción con su mensaje
  // específico.
  const continuarConSeleccionParcial = (group, siguienteAccion) => {
    const selectedSet = selectedByGroup[group.key] || new Set();
    if (selectedSet.size > 0 && selectedSet.size < group.pedidos.length) {
      setPendingConfirm({ action: 'advertencia-parcial', group, siguienteAccion });
      return;
    }
    siguienteAccion();
  };

  const updateCliente = (groupKey, field, value) => {
    setClienteByGroup((current) => ({
      ...current,
      [groupKey]: { ...(current[groupKey] || emptyCliente), [field]: value },
    }));
  };

  const updateNotaCliente = (groupKey, field, value) => {
    setNotaClienteByGroup((current) => ({
      ...current,
      [groupKey]: { ...(current[groupKey] || clienteDelMesero(groups.find((group) => group.key === groupKey) || { pedidos: [] })), [field]: value },
    }));
  };

  // Al salir del campo de cédula, busca si ya existe un cliente con ese
  // número (VGCliente.numero_documento) — reusa el mismo endpoint liviano de
  // búsqueda que ya usaba facturación (clientes_buscar_view, filtra por
  // nombre o número). Si hay una coincidencia EXACTA de número, autocompleta
  // nombre/apellido; si no, la cajera los escribe a mano y
  // pedidos_cobro_view crea el cliente nuevo al cobrar.
  const buscarClientePorCedula = async (groupKey, cedulaInput) => {
    const cedula = cedulaInput.trim();
    if (!cedula) {
      return;
    }
    try {
      const response = await fetch(`/api/clientes/buscar/?q=${encodeURIComponent(cedula)}`, {
        credentials: 'include',
        cache: 'no-store',
      });
      const data = await response.json().catch(() => ({}));
      if (!data.ok) {
        return;
      }
      const encontrado = (data.clientes || []).find((item) => item.numero_documento === cedula);
      if (encontrado) {
        setNotaClienteByGroup((current) => ({
          ...current,
          [groupKey]: { cedula, nombre: encontrado.nombre, apellido: encontrado.apellido || '' },
        }));
      }
    } catch (requestError) {
      // Si falla la busqueda, la cajera simplemente escribe el nombre a mano
      // — no bloquea el flujo, pedidos_cobro_view igual crea el cliente si
      // la cedula no existe.
    }
  };

  // La pre-factura y la factura SI necesitan poder registrar tipo+numero de
  // documento por separado (puede ser RIF de empresa, no solo cedula) — se
  // valida en el frontend antes de llamar al backend (que hoy acepta el
  // documento vacio y cae a "Consumidor Final") para forzar la politica del
  // negocio de siempre pedirlo en estos dos flujos. La nota de entrega usa su
  // propia validacion, mas simple — ver handleClickNotaEntrega.
  const validateClienteDocumento = (group) => {
    const cliente = clienteByGroup[group.key] || emptyCliente;
    if (!cliente.tipo_documento || !cliente.numero_documento.trim()) {
      showError(`Indica el tipo y número de documento del cliente de ${group.label} antes de generar la cuenta del cliente o factura.`);
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
    setUsarTasaActualByGroup((current) => {
      const copy = { ...current };
      delete copy[groupKey];
      return copy;
    });
    setDescuentoActivoByGroup((current) => {
      const copy = { ...current };
      delete copy[groupKey];
      return copy;
    });
    setDescuentoMontoByGroup((current) => {
      const copy = { ...current };
      delete copy[groupKey];
      return copy;
    });
    setDescuentoMotivoByGroup((current) => {
      const copy = { ...current };
      delete copy[groupKey];
      return copy;
    });
  };

  // Cambiar el cargo de delivery de un pedido antes de cobrarlo (ver delivery_views.pedido_cargo_delivery_view):
  // lo usa caja cuando el cliente reclama el precio. Si ya se le había dado la cuenta del cliente, esa cuenta
  // queda con el monto viejo: se descarta para que se genere de nuevo con el total correcto.
  const handleCambiarDelivery = async (pedido, cuerpo, groupKey) => {
    try {
      const response = await fetch(`/api/pedidos/${pedido.id}/delivery/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') || '' },
        credentials: 'include',
        body: JSON.stringify(cuerpo),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        showError(data.message || 'No se pudo cambiar el delivery.');
        return false;
      }
      showSuccess(`Delivery del pedido #${pedido.id} actualizado: $${Number(data.pedido.cargo_delivery).toFixed(2)}.`);
      if (groupKey) {
        setPrefacturaByGroup((current) => {
          const copy = { ...current };
          delete copy[groupKey];
          return copy;
        });
      }
      await fetchPedidos();
      return true;
    } catch (requestError) {
      showError('Error de red al cambiar el delivery.');
      return false;
    }
  };

  // Cambiar los servicios adicionales de un pedido antes de cobrarlo (ver servicios_adicionales_views.pedido_servicios_view):
  // cualquier rol puede. Si ya se le había dado la cuenta del cliente, esa cuenta queda con el total viejo: se descarta
  // para que se genere de nuevo.
  const handleCambiarServicios = async (pedido, servicios, groupKey) => {
    try {
      const response = await fetch(`/api/pedidos/${pedido.id}/servicios/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') || '' },
        credentials: 'include',
        body: JSON.stringify({ servicios }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        showError(data.message || 'No se pudieron cambiar los servicios.');
        return false;
      }
      showSuccess(`Servicios del pedido #${pedido.id} actualizados: $${Number(data.pedido.cargo_servicios).toFixed(2)}.`);
      if (groupKey) {
        setPrefacturaByGroup((current) => {
          const copy = { ...current };
          delete copy[groupKey];
          return copy;
        });
      }
      await fetchPedidos();
      return true;
    } catch (requestError) {
      showError('Error de red al cambiar los servicios.');
      return false;
    }
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

  // Suma del total de los pedidos SELECCIONADOS de un grupo — usado tanto para
  // validar el descuento (¿el monto puesto es menor al total real?) como para
  // mostrarlo en el modal de confirmación.
  const computeSelectedTotal = (group) => {
    const selectedSet = selectedByGroup[group.key] || new Set();
    return group.pedidos
      .filter((pedido) => selectedSet.has(pedido.id))
      .reduce((sum, pedido) => sum + Number(pedido.total), 0);
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
    const notaCliente = notaClienteDe(group);
    if (!notaCliente.cedula.trim()) {
      showError(`Indica la cédula del cliente de ${group.label} antes de registrar la nota de entrega.`);
      return;
    }
    if (!notaCliente.nombre.trim()) {
      showError(`Indica el nombre del cliente de ${group.label} antes de registrar la nota de entrega.`);
      return;
    }
    if (descuentoActivoByGroup[group.key]) {
      const montoRaw = descuentoMontoByGroup[group.key];
      if (montoRaw !== '' && montoRaw !== undefined && montoRaw !== null) {
        const montoCobrar = Number(montoRaw);
        const selectedTotal = computeSelectedTotal(group);
        if (montoCobrar > selectedTotal) {
          showError(`El monto a cobrar ($${montoCobrar.toFixed(2)}) no puede ser mayor al total de la cuenta ($${selectedTotal.toFixed(2)}).`);
          return;
        }
        if (montoCobrar < selectedTotal && !(descuentoMotivoByGroup[group.key] || '').trim()) {
          showError('Indica el motivo del descuento antes de continuar.');
          return;
        }
      }
    }
    setPendingConfirm({ action: 'nota', group });
  };

  // El check de descuento no se activa directo: primero pide confirmación
  // (advertencia de que se va a cobrar menos del total) — ver
  // buildConfirmContent/handleConfirmPendingAction, acción 'activar-descuento'.
  // Recién al confirmar se desbloquean los campos de monto y motivo.
  const handleClickActivarDescuento = (group) => {
    setPendingConfirm({ action: 'activar-descuento', group });
  };

  const handleDesactivarDescuento = (groupKey) => {
    setDescuentoActivoByGroup((current) => ({ ...current, [groupKey]: false }));
    setDescuentoMontoByGroup((current) => ({ ...current, [groupKey]: '' }));
    setDescuentoMotivoByGroup((current) => ({ ...current, [groupKey]: '' }));
  };

  // --- Documento 1: Nota de entrega (cobro directo e inmediato, sin IVA ni numeracion fiscal) ---
  const handleNotaEntrega = async (group) => {
    const selectedIds = Array.from(selectedByGroup[group.key] || []);
    if (selectedIds.length === 0) {
      return;
    }
    const notaCliente = notaClienteDe(group);

    // montoCobrar es el monto FINAL a cobrar (no lo que se resta) — vacío/no
    // activo significa "sin descuento", se cobra el total completo (el
    // backend lo interpreta igual: ver pedidos_cobro_view).
    const descuentoActivo = descuentoActivoByGroup[group.key];
    const montoRaw = descuentoActivo ? descuentoMontoByGroup[group.key] : '';
    const montoCobrar = montoRaw !== '' && montoRaw !== undefined && montoRaw !== null ? montoRaw : null;
    const descuentoMotivo = descuentoActivo ? (descuentoMotivoByGroup[group.key] || '').trim() : '';

    setBusyGroup(group.key);
    try {
      const response = await fetch('/api/pedidos/cobro/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken') || '',
        },
        credentials: 'include',
        body: JSON.stringify({
          pedido_ids: selectedIds,
          monto_cobrar: montoCobrar,
          descuento_motivo: descuentoMotivo,
          cliente_numero_documento: notaCliente.cedula.trim(),
          cliente_nombre: notaCliente.nombre.trim(),
          cliente_apellido: notaCliente.apellido.trim(),
          usar_tasa_actual: Boolean(usarTasaActualByGroup[group.key]),
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        showError(data.message || 'No se pudo procesar la nota de entrega.');
        await fetchPedidos();
        return;
      }

      const descuentoAplicado = Number(data.nota_entrega.descuento_monto || 0);
      showSuccess(
        `Nota de entrega ${data.nota_entrega.codigo} registrada: `
        + `${formatMontoDocumento(data.nota_entrega.total, data.nota_entrega.moneda, tasaCambio)} `
        + `(${data.nota_entrega.pedidos.length} pedido(s))`
        + `${descuentoAplicado > 0 ? ` con descuento de $${descuentoAplicado.toFixed(2)}` : ''}. Pendiente de cobro — `
        + `abona desde el reporte de notas de entrega.`
        + `${data.nota_entrega.tasa_origen === 'prefactura' ? ` Se respetó la tasa de la cuenta ${data.nota_entrega.tasa_prefactura} (Bs ${formatTasa(data.nota_entrega.tasa_cambio_referencia)}).` : ''}`
        + `${data.nota_entrega.tasa_prefactura_vencida ? ` Atención: la tasa de la cuenta ya venció, se usó la tasa de hoy (Bs ${formatTasa(data.nota_entrega.tasa_cambio_referencia)}).` : ''}`,
      );
      setNotasRefreshToken((current) => current + 1);
      clearGroupState(group.key);
      // No fetchPedidos() acá a propósito: el backend ya marcó el pedido como
      // 'pagado' (pedidos_cobro_view lo excluye de BILLABLE_ORDER_STATES), así
      // que un refresh inmediato lo haría desaparecer de un salto justo cuando
      // la cajera recién ve el toast de éxito. Se va solo con el próximo poll
      // de 15s (o si recarga la página) — no hace falta forzarlo.
    } catch (requestError) {
      showError('Error de red al procesar la nota de entrega.');
    } finally {
      setBusyGroup('');
    }
  };

  // --- Documento 2: Cuenta del cliente / pre-factura (vista previa, sin cobrar todavia) ---
  // No se manda metodo_pago_id acá: a esta altura el cliente puede seguir
  // comiendo o decidir cómo pagar después, así que pedirlo aquí era
  // redundante con lo que ya se vuelve a preguntar al cobrar (nota de
  // entrega/factura) y no aporta nada — sin método de pago el backend
  // simplemente muestra la cuenta en USD (ver _resolve_moneda), y como esto
  // no genera ningún pago real tampoco afecta el cuadre de caja.
  const handleGenerarPrefactura = async (group, { renovar = false } = {}) => {
    const selectedIds = Array.from(selectedByGroup[group.key] || []);
    if (selectedIds.length === 0) {
      return;
    }

    setBusyGroup(group.key);
    try {
      const response = await fetch('/api/prefacturas/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') || '' },
        credentials: 'include',
        body: JSON.stringify({ pedido_ids: selectedIds, renovar_tasa: renovar }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        showError(data.message || 'No se pudo generar la cuenta del cliente.');
        return;
      }
      showSuccess(
        data.tasa_reutilizada
          ? `Cuenta del cliente ${data.prefactura.codigo} generada con la misma tasa de la cuenta anterior (Bs ${formatTasa(data.prefactura.tasa_cambio_referencia)}, vigente ${data.prefactura.tasa_minutos_restantes} min más).`
          : `Cuenta del cliente ${data.prefactura.codigo} generada con la tasa de hoy (Bs ${formatTasa(data.prefactura.tasa_cambio_referencia)}).`,
      );
      setPrefacturaByGroup((current) => ({ ...current, [group.key]: data.prefactura }));
      // Para que la pantalla de cobro tome de una vez la tasa de esta cuenta (si no, esperaria al refresco de 15 s).
      fetchPedidos();
    } catch (requestError) {
      showError('Error de red al generar la cuenta del cliente.');
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
      // Sin fetchPedidos() acá tampoco, mismo motivo que en handleNotaEntrega:
      // el pedido ya quedó facturado (pedidos_cobro_view lo marca 'pagado'), un
      // refresh inmediato lo sacaría de la lista de un salto.
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
      // Sin fetchPedidos() acá tampoco, mismo motivo que en handleNotaEntrega:
      // el pedido ya quedó facturado (pedidos_cobro_view lo marca 'pagado'), un
      // refresh inmediato lo sacaría de la lista de un salto.
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

    if (action === 'advertencia-parcial') {
      const selectedSet = selectedByGroup[group.key] || new Set();
      return {
        title: 'Pedidos sin seleccionar',
        message: `Seleccionaste ${selectedSet.size} de ${group.pedidos.length} pedido(s) de ${group.label}. `
          + 'Si continúas, los pedidos sin marcar quedarán pendientes por cobrar. ¿Estás seguro de continuar sin seleccionar todos los pedidos de la mesa?',
        confirmLabel: 'Sí, continuar así',
      };
    }

    if (action === 'activar-descuento') {
      return {
        title: 'Aplicar descuento',
        message: `Vas a habilitar un descuento manual para la cuenta de ${group.label}. Por defecto se cobrará el total completo; `
          + 'si pones un monto, ese será el TOTAL que se le cobre al cliente (no lo que se resta), y vas a tener que indicar el motivo '
          + 'si queda por debajo del total real (queda guardado para auditoría). ¿Estás de acuerdo?',
        confirmLabel: 'Sí, habilitar descuento',
      };
    }

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
        message: `Vas a emitir la factura fiscal${prefactura ? ` de la cuenta del cliente ${prefactura.codigo}` : ''} de ${group.label} por ${totalLabel}. Esta acción no se puede deshacer. ¿Confirmas?`,
        confirmLabel: 'Sí, emitir factura',
      };
    }

    const selectedSet = selectedByGroup[group.key] || new Set();
    const selectedTotal = group.pedidos
      .filter((pedido) => selectedSet.has(pedido.id))
      .reduce((sum, pedido) => sum + Number(pedido.total), 0);
    // La nota de entrega ya no declara método de pago al emitirse (se elige al
    // abonarla), así que el monto se muestra en dólares y en bolívares.
    const labelUsdBs = (monto) => {
      const bs = formatBs(monto, tasaDelGrupo(group));
      return bs ? `$${Number(monto).toFixed(2)} (${bs})` : `$${Number(monto).toFixed(2)}`;
    };
    const totalLabel = labelUsdBs(selectedTotal);

    if (action === 'nota') {
      const montoRaw = descuentoActivoByGroup[group.key] ? descuentoMontoByGroup[group.key] : '';
      const tieneMontoCobrar = montoRaw !== '' && montoRaw !== undefined && montoRaw !== null;
      const montoCobrar = tieneMontoCobrar ? Number(montoRaw) : selectedTotal;
      const hayDescuento = tieneMontoCobrar && montoCobrar < selectedTotal;
      const montoCobrarLabel = tieneMontoCobrar ? labelUsdBs(montoCobrar) : null;
      return {
        title: 'Registrar nota de entrega',
        message: `Vas a cobrar ${selectedSet.size} pedido(s) de ${group.label} por ${totalLabel}`
          + (hayDescuento
            ? `, pero con el monto puesto se va a cobrar ${montoCobrarLabel} (descuento de $${(selectedTotal - montoCobrar).toFixed(2)})`
            : tieneMontoCobrar ? ` (sin descuento real: el monto puesto es igual al total)` : '')
          + ' con una nota de entrega (sin factura fiscal). '
          + 'El número de referencia del pago se registra luego, al abonarla desde el reporte de notas de entrega. ¿Confirmas?',
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
    const { action, group, pedido, siguienteAccion } = pendingConfirm;
    if (action === 'advertencia-parcial') {
      setPendingConfirm(null);
      siguienteAccion();
      return;
    }
    if (action === 'activar-descuento') {
      setDescuentoActivoByGroup((current) => ({ ...current, [group.key]: true }));
      setPendingConfirm(null);
      return;
    }
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

  const tabs = [
    { id: 'cobro', icon: '💳', label: 'Cobro de Mesas', count: groups.length },
    { id: 'notas', icon: '📋', label: 'Notas de Entrega' },
    { id: 'propinas', icon: '🪙', label: 'Propinas & Pagos Extra' },
    { id: 'cuentas', icon: '📑', label: 'Cuentas por Cobrar' },
    ...(FACTURACION_HABILITADA ? [{ id: 'facturas', icon: '📜', label: 'Facturas' }] : []),
  ];
  const panelStyle = (id) => ({ display: activeTab === id ? 'grid' : 'none', gap: 12 });

  return (
    <section className="vg-cobro" style={containerStyle(isMobile)}>
      <div style={headerWrapStyle(isMobile)}>
        <div>
          <div style={eyebrowStyle}>Cobro</div>
          <h2 style={titleStyle(isMobile)}>Pedidos listos para cobrar</h2>
        </div>
        <button type="button" onClick={onBack} style={backButtonStyle(isMobile)}>
          Volver
        </button>
      </div>

      <Toast toast={toast} onClose={hideToast} />

      <div className="vg-cobro-tabs no-print" role="tablist" aria-label="Secciones de cobro">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            className={`vg-cobro-tab${activeTab === tab.id ? ' is-active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <span aria-hidden="true">{tab.icon}</span>
            {tab.label}
            {tab.count > 0 ? <span className="vg-cobro-tab__count">{tab.count}</span> : null}
          </button>
        ))}
      </div>

      <div role="tabpanel" style={panelStyle('cobro')}>
        {loading ? <div style={emptyStateStyle}>Cargando pedidos...</div> : null}
        {!loading && error ? <div style={errorStyle}>{error}</div> : null}

        {!loading && !error && groups.length === 0 ? (
          <div style={emptyStateStyle}>No hay pedidos listos para cobrar en este momento.</div>
        ) : null}

        {!loading && !error && groups.length > 0 ? (
          <div className={`vg-cobro-split${selectedGroup ? ' vg-cobro-split--abierta' : ''}`}>
            <aside className="vg-cobro-lista" aria-label="Mesas pendientes de cobro">
              <input
                type="text"
                value={mesaQuery}
                onChange={(event) => setMesaQuery(event.target.value)}
                placeholder="Buscar mesa por número o por cliente..."
                style={mesaSearchInputStyle}
              />

              <div className="vg-cobro-lista__items">
                {filteredGroups.length === 0 ? (
                  <div style={mesaOptionEmptyStyle}>No se encontraron mesas con ese criterio.</div>
                ) : (
                  filteredGroups.map((group) => {
                    const groupTotal = group.pedidos.reduce((sum, pedido) => sum + Number(pedido.total), 0);
                    const isCurrent = Boolean(selectedGroup && selectedGroup.key === group.key);
                    return (
                      <button
                        key={group.key}
                        type="button"
                        className={`vg-cobro-mesa${isCurrent ? ' is-active' : ''}`}
                        aria-pressed={isCurrent}
                        onClick={() => handleSelectGroup(group)}
                      >
                        <span className="vg-cobro-mesa__nombre">{group.label}</span>
                        <span className="vg-cobro-mesa__total">
                          ${groupTotal.toFixed(2)}
                          <BsAmount amountUsd={groupTotal} tasa={tasaCambio} />
                        </span>
                        <span className="vg-cobro-mesa__meta">{group.pedidos.length} pedido(s)</span>
                      </button>
                    );
                  })
                )}
              </div>
            </aside>

            <div className="vg-cobro-ticket">
              {selectedGroup ? (
                <article style={groupCardStyle}>
                  <button type="button" className="vg-cobro-volver" onClick={handleClearSelection}>
                    ← Mesas
                  </button>
                  <div style={groupHeaderStyle}>
                    <div style={{ color: 'var(--vg-text-strong)', fontWeight: 700, fontSize: 18 }}>{selectedGroup.label}</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                      <span style={groupCountStyle}>{selectedGroup.pedidos.length} pedido(s)</span>
                      {selectedGroup.pedidos.length > 1 && selectedSet.size < selectedGroup.pedidos.length ? (
                        <button
                          type="button"
                          onClick={() => selectAllInGroup(selectedGroup)}
                          style={selectAllButtonStyle}
                        >
                          Seleccionar todos los pedidos
                        </button>
                      ) : null}
                    </div>
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
                              <BsAmount amountUsd={pedido.total} tasa={tasaGrupo} />
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
                                  {grupoItems.map((item) => renderDetailItemRow(item, tasaGrupo, {
                                    canGestionarItems, onAjustarItem: (modo, it) => abrirAjuste(modo, it, pedido), soloItem: items.length <= 1,
                                  }))}
                                </div>
                              ))}
                              {groupItemsByPlato(items).sueltos.map((item) => renderDetailItemRow(item, tasaGrupo, {
                                canGestionarItems, onAjustarItem: (modo, it) => abrirAjuste(modo, it, pedido), soloItem: items.length <= 1,
                              }))}
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

                            {(pedido.servicios || []).length > 0 ? (
                              <div style={{ display: 'grid', gap: 2 }}>
                                {pedido.servicios.map((servicio) => (
                                  <div key={`srv-${servicio.id}`} style={itemNoteDetailStyle}>
                                    Servicio: {servicio.cantidad}x {servicio.nombre} — ${servicio.subtotal}
                                  </div>
                                ))}
                              </div>
                            ) : null}

                            <div style={detailTotalsStyle}>
                              <span>Subtotal: ${pedido.subtotal}<BsAmount amountUsd={pedido.subtotal} tasa={tasaGrupo} /></span>
                              {Number(pedido.cargo_servicios) > 0 ? <span>Servicios: ${pedido.cargo_servicios}<BsAmount amountUsd={pedido.cargo_servicios} tasa={tasaGrupo} /></span> : null}
                              {Number(pedido.impuesto) > 0 ? <span>Impuesto: ${pedido.impuesto}<BsAmount amountUsd={pedido.impuesto} tasa={tasaGrupo} /></span> : null}
                              {Number(pedido.descuento) > 0 ? <span>Descuento: -${pedido.descuento}<BsAmount amountUsd={pedido.descuento} tasa={tasaGrupo} /></span> : null}
                              {Number(pedido.propina) > 0 ? <span>Propina: ${pedido.propina}<BsAmount amountUsd={pedido.propina} tasa={tasaGrupo} /></span> : null}
                              {Number(pedido.cargo_delivery) > 0 ? (
                                <span>
                                  Delivery{pedido.zona_delivery_nombre ? ` (${pedido.zona_delivery_nombre})` : ''}: ${pedido.cargo_delivery}
                                  <BsAmount amountUsd={pedido.cargo_delivery} tasa={tasaGrupo} />
                                </span>
                              ) : null}
                              <span style={{ fontWeight: 800, color: 'var(--vg-text-strong)' }}>
                                Total: ${pedido.total}
                                <BsAmount amountUsd={pedido.total} tasa={tasaGrupo} style={{ color: 'var(--vg-f-e0c9a3)' }} />
                              </span>
                            </div>

                            <ServiciosEditor
                              pedido={pedido}
                              onGuardar={(servicios) => handleCambiarServicios(pedido, servicios, selectedGroup.key)}
                            />

                            {pedido.tipo_pedido === 'delivery' && (pedido.grupo_id === pedido.id) ? (
                              <DeliveryCargoEditor
                                pedido={pedido}
                                onGuardar={(cuerpo) => handleCambiarDelivery(pedido, cuerpo, selectedGroup.key)}
                              />
                            ) : null}
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                </div>

                {!prefactura ? (
                  <div style={footerSectionStyle}>
                    <div style={clienteSeccionTituloStyle}>Cliente</div>
                    <div className="vg-cobro-cliente">
                      <input
                        placeholder="Cédula *"
                        value={notaCliente.cedula}
                        onChange={(event) => updateNotaCliente(selectedGroup.key, 'cedula', event.target.value)}
                        onBlur={(event) => buscarClientePorCedula(selectedGroup.key, event.target.value)}
                        style={inputStyle}
                      />
                      <input
                        placeholder="Nombre *"
                        value={notaCliente.nombre}
                        onChange={(event) => updateNotaCliente(selectedGroup.key, 'nombre', event.target.value)}
                        style={inputStyle}
                      />
                      <input
                        placeholder="Apellido"
                        value={notaCliente.apellido}
                        onChange={(event) => updateNotaCliente(selectedGroup.key, 'apellido', event.target.value)}
                        style={inputStyle}
                      />
                    </div>
                    <p style={clienteHintStyle}>
                      Cédula y nombre son obligatorios — si la cédula ya está registrada, el nombre y apellido se completan solos.
                    </p>

                    {/* Datos fiscales para factura: solo existen mientras la facturación esté
                        habilitada. "Generar cuenta del cliente" ya no pide ningún dato — es solo
                        el resumen de lo que pidió el cliente (ver prefacturaPanel abajo). */}
                    {FACTURACION_HABILITADA ? (
                      <>
                        <div style={clienteSeccionTituloStyle}>Cliente — factura</div>
                        <div className="vg-cobro-cliente">
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
                          El tipo y número de documento son obligatorios para generar factura fiscal.
                        </p>
                      </>
                    ) : null}

                    {tasaCuenta ? (
                      <div style={tasaCuentaAvisoStyle}>
                        <div>
                          Cuenta {tasaCuenta.codigo} · tasa <strong>Bs {formatTasa(tasaCuenta.tasa)}</strong> · vigente {tasaCuenta.minutos_restantes} min más.
                          {' '}Los Bs de abajo usan esa tasa, la misma que se le dijo al cliente.
                        </div>
                        <label style={tasaCuentaOpcionStyle}>
                          <input
                            type="checkbox"
                            checked={usarTasaActual}
                            onChange={(event) => setUsarTasaActualByGroup((current) => ({ ...current, [selectedGroup.key]: event.target.checked }))}
                          />
                          Cobrar con la tasa actual{tasaCambio ? ` (Bs ${formatTasa(tasaCambio)})` : ''}
                        </label>
                      </div>
                    ) : null}

                    <div style={groupFooterStyle(isMobile)}>
                      <div className="vg-cobro-total">
                        <span className="vg-cobro-total__label">Total seleccionado</span>
                        <span className="vg-cobro-total__monto">
                          ${selectedTotal.toFixed(2)}
                          <BsAmount amountUsd={selectedTotal} tasa={tasaGrupo} />
                        </span>
                      </div>
                      {FACTURACION_HABILITADA ? (
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
                      ) : null}
                    </div>

                    <DescuentoManualBlock
                      group={selectedGroup}
                      activo={Boolean(descuentoActivoByGroup[selectedGroup.key])}
                      monto={descuentoMontoByGroup[selectedGroup.key] || ''}
                      motivo={descuentoMotivoByGroup[selectedGroup.key] || ''}
                      onActivar={() => handleClickActivarDescuento(selectedGroup)}
                      onDesactivar={() => handleDesactivarDescuento(selectedGroup.key)}
                      onMontoChange={(value) => setDescuentoMontoByGroup((current) => ({ ...current, [selectedGroup.key]: value }))}
                      onMotivoChange={(value) => setDescuentoMotivoByGroup((current) => ({ ...current, [selectedGroup.key]: value }))}
                    />

                    <div style={docButtonsRowStyle(isMobile)}>
                      <button
                        type="button"
                        onClick={() => continuarConSeleccionParcial(selectedGroup, () => handleClickNotaEntrega(selectedGroup))}
                        style={checkoutButtonStyle}
                        disabled={isBusy}
                      >
                        {isBusy ? 'Procesando...' : 'Nota de entrega'}
                      </button>
                      <button
                        type="button"
                        onClick={() => continuarConSeleccionParcial(selectedGroup, () => handleGenerarPrefactura(selectedGroup))}
                        style={secondaryButtonStyle}
                        disabled={selectedSet.size === 0 || isBusy}
                      >
                        {isBusy ? 'Generando...' : 'Generar cuenta del cliente'}
                      </button>
                      {FACTURACION_HABILITADA ? (
                        <button
                          type="button"
                          onClick={() => continuarConSeleccionParcial(selectedGroup, () => {
                            if (!validateClienteDocumento(selectedGroup)) return;
                            setPendingConfirm({ action: 'factura', group: selectedGroup });
                          })}
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
                    <div style={{ color: 'var(--vg-f-ffb0b0)', fontWeight: 800, fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                      Cuenta del cliente {prefactura.codigo}
                    </div>
                    <div style={{ display: 'grid', gap: 4 }}>
                      {prefactura.lineas.map((linea) => (
                        <div key={linea.id} style={lineaRowStyle}>
                          <span>{linea.cantidad}x {linea.descripcion}</span>
                          <span>
                            ${Number(linea.subtotal).toFixed(2)}
                            <BsAmount amountUsd={linea.subtotal} tasa={prefactura.tasa_cambio_referencia || tasaCambio} />
                          </span>
                        </div>
                      ))}
                    </div>
                    <div style={detailTotalsStyle}>
                      <span style={{ fontWeight: 800, color: 'var(--vg-text-strong)' }}>
                        Total: ${Number(prefactura.total).toFixed(2)}
                        <BsAmount amountUsd={prefactura.total} tasa={prefactura.tasa_cambio_referencia || tasaCambio} style={{ color: 'var(--vg-f-e0c9a3)' }} />
                      </span>
                    </div>

                    {prefactura.tasa_cambio_referencia ? (
                      <div style={tasaCuentaAvisoStyle}>
                        <div>
                          Tasa de esta cuenta: <strong>Bs {formatTasa(prefactura.tasa_cambio_referencia)}</strong>
                          {prefactura.tasa_minutos_restantes > 0
                            ? ` · vigente ${prefactura.tasa_minutos_restantes} min más`
                            : ' · ya venció: al cobrar se usará la tasa de hoy'}
                        </div>
                      </div>
                    ) : null}

                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      <button
                        type="button"
                        onClick={() => handleDescartarPrefactura(selectedGroup.key)}
                        style={secondaryButtonStyle}
                        disabled={isBusy}
                      >
                        ← Volver
                      </button>
                      <button
                        type="button"
                        onClick={() => handleGenerarPrefactura(selectedGroup, { renovar: true })}
                        style={secondaryButtonStyle}
                        disabled={isBusy}
                        title="Congela la tasa de hoy para esta cuenta y reinicia los minutos de vigencia"
                      >
                        Renovar tasa
                      </button>
                      {FACTURACION_HABILITADA ? (
                        <button
                          type="button"
                          onClick={() => continuarConSeleccionParcial(selectedGroup, () => setPendingConfirm({ action: 'prefactura', group: selectedGroup }))}
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
              ) : (
                <div className="vg-cobro-vacio">Selecciona una mesa de la lista para ver su cuenta y cobrarla.</div>
              )}
            </div>
          </div>
        ) : null}
      </div>

      <div style={panelStyle('notas')}>
        <NotasEntregaHistorialPage isMobile={isMobile} embedded refreshToken={notasRefreshToken} onArmarCanje={onArmarCanje} />
      </div>

      <div style={panelStyle('propinas')}>
        <div style={ingresoExtraButtonsRowStyle(isMobile)}>
          <button type="button" onClick={() => setIngresoModalTipo('propina')} style={propinaButtonStyle}>
            + Registrar propina
          </button>
          <button type="button" onClick={() => setIngresoModalTipo('pago_extra')} style={pagoExtraButtonStyle}>
            + Excedente / pago extra
          </button>
        </div>

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
                <span style={{ color: 'var(--vg-text-strong)', fontWeight: 700 }}>
                  {formatMontoDocumento(ingreso.monto, ingreso.moneda, ingreso.tasa_cambio_referencia || tasaCambio)}
                </span>
                <span style={{ color: 'var(--vg-f-d2c4c4)', fontSize: 12 }}>{ingreso.metodo_pago_nombre}</span>
                {ingreso.descripcion ? (
                  <span style={{ color: 'var(--vg-f-d2c4c4)', fontSize: 12 }}>{ingreso.descripcion}</span>
                ) : null}
                {ingreso.nota_entrega_codigo ? (
                  <span style={{ color: 'var(--vg-f-d2c4c4)', fontSize: 12 }}>Nota {ingreso.nota_entrega_codigo}</span>
                ) : null}
                {ingreso.lote_pos_numero ? (
                  <span style={{ color: 'var(--vg-f-a89999)', fontSize: 11 }}>Lote POS #{ingreso.lote_pos_numero}</span>
                ) : null}
                <span style={{ color: 'var(--vg-f-a89999)', fontSize: 11, marginLeft: 'auto' }}>
                  {ingreso.registrado_por} · {formatFechaHora(ingreso.fecha_creacion)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={panelStyle('cuentas')}>
        <CuentasPorCobrarPage isMobile={isMobile} embedded refreshToken={cuentasRefreshToken} />
      </div>

      {FACTURACION_HABILITADA ? (
        <div style={panelStyle('facturas')}>
          <FacturasHistorialPage isMobile={isMobile} embedded />
        </div>
      ) : null}

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

      {ajusteModal ? (
        <AjustePedidoModal
          modo={ajusteModal.modo}
          item={ajusteModal.item}
          mesasCatalogo={mesasCatalogo}
          mesaActualId={ajusteModal.mesaActualId}
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

// Checklist para aplicar un descuento manual al cobrar (ver
// pedidos_cobro_view/VGNotaEntrega.descuento_monto): marcar el check pide
// confirmación primero (ver acción 'activar-descuento' en
// buildConfirmContent/handleConfirmPendingAction); recién al confirmar se
// desbloquean el monto y el motivo. El monto es el TOTAL FINAL a cobrar (no
// lo que se resta) — ej. si la cuenta da $13.90 y se pone $10, se cobran $10.
// Vacío = sin descuento, se cobra el total completo; el motivo es
// obligatorio solo si el monto puesto queda por debajo del total real.
function DescuentoManualBlock({ group, activo, monto, motivo, onActivar, onDesactivar, onMontoChange, onMotivoChange }) {
  return (
    <div style={descuentoBlockStyle}>
      <label style={descuentoCheckboxRowStyle}>
        <input
          type="checkbox"
          checked={activo}
          onChange={(event) => (event.target.checked ? onActivar() : onDesactivar())}
        />
        <span>Aplicar descuento a la cuenta de {group.label}</span>
      </label>
      {activo ? (
        <div style={descuentoFieldsRowStyle}>
          <MoneyInput
            placeholder="Monto final a cobrar ($, vacío = cobrar el total)"
            value={monto}
            onChange={onMontoChange}
            style={inputStyle}
          />
          <input
            type="text"
            placeholder="Motivo del descuento (obligatorio si hay monto)"
            value={motivo}
            onChange={(event) => onMotivoChange(event.target.value)}
            style={{ ...inputStyle, flex: 1 }}
          />
        </div>
      ) : null}
    </div>
  );
}

function IngresoExtraModal({ tipo, metodosPago, submitting, onClose, onSubmit }) {
  // Solo se monta mientras hay un tipo elegido, así que montado == abierto.
  useMobileBackHandler(true, onClose);
  const [monto, setMonto] = useState('');
  const [descripcion, setDescripcion] = useState('');
  const [metodoPagoId, setMetodoPagoId] = useState('');
  const [notaEntregaId, setNotaEntregaId] = useState('');
  const [notasEntrega, setNotasEntrega] = useState([]);
  const [cargandoNotas, setCargandoNotas] = useState(true);
  const [errorNotas, setErrorNotas] = useState('');

  const esPropina = tipo === 'propina';
  useEffect(() => {
    let cancelado = false;
    const hoy = new Date();
    const isoLocal = (fecha) => {
      const local = new Date(fecha.getTime() - fecha.getTimezoneOffset() * 60000);
      return local.toISOString().slice(0, 10);
    };
    const desde = new Date(hoy);
    desde.setDate(desde.getDate() - 90);
    const params = new URLSearchParams({ desde: isoLocal(desde), hasta: isoLocal(hoy) });
    setCargandoNotas(true);
    setErrorNotas('');
    fetch(`/api/notas-entrega/?${params.toString()}`, { credentials: 'include', cache: 'no-store' })
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.message || 'No se pudieron cargar las notas de entrega.');
        if (!cancelado) setNotasEntrega(Array.isArray(data.notas_entrega) ? data.notas_entrega : []);
      })
      .catch((error) => {
        if (!cancelado) setErrorNotas(error.message || 'No se pudieron cargar las notas de entrega.');
      })
      .finally(() => {
        if (!cancelado) setCargandoNotas(false);
      });
    return () => {
      cancelado = true;
    };
  }, []);
  const metodoSeleccionado = metodosPago.find((metodo) => String(metodo.id) === String(metodoPagoId));
  // El monto se escribe siempre en la moneda de la cuenta elegida (igual que un
  // abono de nota de entrega/factura) — si es una cuenta en bolívares, acá se
  // cuentan bolívares, no dólares; el backend convierte a USD con la tasa del
  // momento (ver ingresos_extra_view). Antes de elegir cuenta no se puede saber
  // cuál es, así que por defecto se asume $ hasta que se seleccione una.
  const esBs = metodoSeleccionado?.moneda === 'VES';

  return (
    <div style={ingresoModalBackdropStyle} onClick={submitting ? undefined : onClose}>
      <div style={ingresoModalCardStyle} onClick={(event) => event.stopPropagation()}>
        <button type="button" onClick={onClose} style={modalCloseButtonStyle} aria-label="Cerrar" disabled={submitting}>
          ×
        </button>
        <div style={ingresoModalTitleStyle}>
          {esPropina ? 'Registrar propina' : 'Registrar excedente / pago extra'}
        </div>
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
              <option key={metodo.id} value={metodo.id}>
                {metodo.nombre} ({metodo.moneda === 'VES' ? 'Bs' : '$'})
              </option>
            ))}
          </select>
        </label>

        <label style={ingresoFieldLabelStyle}>
          Nota de entrega{esPropina ? ' (opcional)' : ' (obligatoria)'}
          <select
            value={notaEntregaId}
            onChange={(event) => setNotaEntregaId(event.target.value)}
            style={ingresoInputStyle}
            className="admin-dark-select"
            disabled={cargandoNotas || Boolean(errorNotas)}
            required={!esPropina}
          >
            <option value="">{cargandoNotas ? 'Cargando notas...' : 'Selecciona una nota de entrega...'}</option>
            {notasEntrega.map((nota) => (
              <option key={nota.id} value={nota.id}>
                {nota.codigo} · {new Date(nota.fecha_emision).toLocaleDateString('es-VE')}
              </option>
            ))}
          </select>
          {errorNotas ? <span style={{ color: 'var(--vg-f-ff9191)', fontSize: 12 }}>{errorNotas}</span> : null}
          {!cargandoNotas && !errorNotas && notasEntrega.length === 0 ? (
            <span style={{ color: 'var(--vg-f-a89999)', fontSize: 12 }}>No hay notas de entrega en los últimos 90 días.</span>
          ) : null}
        </label>

        <label style={ingresoFieldLabelStyle}>
          Monto ({esBs ? 'Bs' : '$'})
          <MoneyInput
            value={monto}
            onChange={setMonto}
            style={ingresoInputStyle}
            placeholder="0.00"
          />
        </label>

        <label style={ingresoFieldLabelStyle}>
          Descripción (opcional)
          <input
            type="text"
            value={descripcion}
            onChange={(event) => setDescripcion(event.target.value)}
            style={ingresoInputStyle}
            placeholder={esPropina ? 'Ej: Propina Mesa 4' : 'Ej: Excedente Mesa 4'}
          />
        </label>

        <div style={ingresoModalFooterStyle}>
          <button type="button" onClick={onClose} style={secondaryButtonStyle} disabled={submitting}>
            Cancelar
          </button>
          <button
            type="button"
            onClick={() => onSubmit({ monto, descripcion, metodoPagoId, notaEntregaId })}
            style={esPropina ? propinaButtonStyle : pagoExtraButtonStyle}
            disabled={submitting || (esPropina === false && (cargandoNotas || Boolean(errorNotas) || !notaEntregaId))}
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

// Servicios adicionales de un pedido (descorche, decoración...): agregar uno o varios, el mismo más de una vez, o quitarlos
// antes de cobrar. El precio siempre es el del catálogo; no llevan IVA.
function ServiciosEditor({ pedido, onGuardar }) {
  const [abierto, setAbierto] = useState(false);
  const [catalogo, setCatalogo] = useState([]);
  const [lineas, setLineas] = useState([]);
  const [guardando, setGuardando] = useState(false);

  const abrir = async () => {
    setLineas((pedido.servicios || []).map((s) => ({
      servicioId: s.servicio_id, nombre: s.nombre, precio: Number(s.precio_unitario), cantidad: s.cantidad,
    })));
    setAbierto(true);
    try {
      const response = await fetch('/api/servicios-adicionales/', { credentials: 'include', cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (response.ok && data.ok) setCatalogo(Array.isArray(data.servicios) ? data.servicios : []);
    } catch (requestError) {
      // Sin catálogo solo se pueden quitar o cambiar cantidades de los que ya tiene.
    }
  };

  const agregar = (servicioId) => {
    const servicio = catalogo.find((item) => item.id === servicioId);
    if (!servicio) return;
    setLineas((actual) => (
      actual.some((l) => l.servicioId === servicioId)
        ? actual.map((l) => (l.servicioId === servicioId ? { ...l, cantidad: Math.min(99, l.cantidad + 1) } : l))
        : [...actual, { servicioId, nombre: servicio.nombre, precio: Number(servicio.precio), cantidad: 1 }]
    ));
  };
  const cambiar = (servicioId, delta) => setLineas((actual) => actual
    .map((l) => (l.servicioId === servicioId ? { ...l, cantidad: Math.min(99, l.cantidad + delta) } : l))
    .filter((l) => l.cantidad > 0));

  const guardar = async () => {
    setGuardando(true);
    const ok = await onGuardar(lineas.map((l) => ({ servicio_id: l.servicioId, cantidad: l.cantidad })));
    setGuardando(false);
    if (ok) setAbierto(false);
  };

  if (!abierto) {
    return (
      <div>
        <button type="button" onClick={abrir} style={deliveryEditorButtonStyle}>
          {Number(pedido.cargo_servicios) > 0 ? 'Cambiar servicios adicionales' : 'Agregar servicio adicional'}
        </button>
      </div>
    );
  }

  const total = lineas.reduce((suma, l) => suma + l.precio * l.cantidad, 0);
  return (
    <div style={deliveryEditorStyle}>
      <select
        value=""
        onChange={(event) => { if (event.target.value) agregar(Number(event.target.value)); }}
        style={deliveryEditorInputStyle}
        className="admin-dark-select"
      >
        <option value="">Agregar un servicio...</option>
        {catalogo.map((servicio) => (
          <option key={servicio.id} value={servicio.id}>{servicio.nombre} — ${Number(servicio.precio).toFixed(2)}</option>
        ))}
      </select>
      {lineas.map((l) => (
        <div key={l.servicioId} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
          <span style={{ flex: 1 }}>{l.nombre}</span>
          <button type="button" onClick={() => cambiar(l.servicioId, -1)} style={deliveryEditorButtonStyle} aria-label="Quitar uno">−</button>
          <span style={{ minWidth: 18, textAlign: 'center' }}>{l.cantidad}</span>
          <button type="button" onClick={() => cambiar(l.servicioId, 1)} style={deliveryEditorButtonStyle} aria-label="Agregar uno">+</button>
          <span style={{ minWidth: 64, textAlign: 'right', fontWeight: 700 }}>${(l.precio * l.cantidad).toFixed(2)}</span>
        </div>
      ))}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap' }}>
        <strong>Servicios: ${total.toFixed(2)}</strong>
        <span style={{ display: 'flex', gap: 8 }}>
          <button type="button" onClick={guardar} disabled={guardando} style={deliveryEditorSaveStyle}>
            {guardando ? 'Guardando...' : 'Guardar'}
          </button>
          <button type="button" onClick={() => setAbierto(false)} disabled={guardando} style={deliveryEditorButtonStyle}>Cancelar</button>
        </span>
      </div>
    </div>
  );
}

// Cambio del cargo de delivery de un pedido: elegir otra zona o escribir el monto que se va a cobrar. Caja
// puede dejar el monto que quiera (por ejemplo cuando el cliente reclama que le cobraron mucho); la zona y su
// tarifa original quedan registradas en el pedido, para saber que se cambio.
function DeliveryCargoEditor({ pedido, onGuardar }) {
  const [abierto, setAbierto] = useState(false);
  const [zonas, setZonas] = useState([]);
  const [zonaId, setZonaId] = useState('');
  const [monto, setMonto] = useState('');
  const [guardando, setGuardando] = useState(false);

  const abrir = async () => {
    setZonaId(pedido.zona_delivery_id ? String(pedido.zona_delivery_id) : '');
    setMonto(String(Number(pedido.cargo_delivery || 0)));
    setAbierto(true);
    try {
      const response = await fetch('/api/delivery/zonas/', { credentials: 'include', cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (response.ok && data.ok) {
        setZonas(Array.isArray(data.zonas) ? data.zonas : []);
      }
    } catch (requestError) {
      // Sin la lista de zonas se puede igual escribir el monto.
    }
  };

  const elegirZona = (valor) => {
    setZonaId(valor);
    const zona = zonas.find((item) => String(item.id) === String(valor));
    if (zona) {
      setMonto(String(Number(zona.tarifa)));
    }
  };

  const guardar = async () => {
    if (monto === '' || Number.isNaN(Number(monto)) || Number(monto) < 0) {
      return;
    }
    setGuardando(true);
    const cuerpo = { cargo_delivery: monto };
    if (zonaId) {
      cuerpo.zona_delivery_id = Number(zonaId);
    }
    const ok = await onGuardar(cuerpo);
    setGuardando(false);
    if (ok) {
      setAbierto(false);
    }
  };

  if (!abierto) {
    return (
      <div>
        <button type="button" onClick={abrir} style={deliveryEditorButtonStyle}>
          {Number(pedido.cargo_delivery) > 0 ? 'Cambiar delivery' : 'Agregar cargo de delivery'}
        </button>
      </div>
    );
  }

  const zonaActual = zonas.find((item) => String(item.id) === String(zonaId));
  const montoDistinto = zonaActual && Number(monto) !== Number(zonaActual.tarifa);

  return (
    <div style={deliveryEditorStyle}>
      <div style={{ color: 'var(--vg-text-strong)', fontWeight: 700, fontSize: 13 }}>Delivery del pedido #{pedido.id}</div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <select value={zonaId} onChange={(event) => elegirZona(event.target.value)} style={deliveryEditorInputStyle} className="admin-dark-select">
          <option value="">Sin zona (monto libre)</option>
          {zonas.map((zona) => (
            <option key={zona.id} value={zona.id}>{zona.nombre} — ${Number(zona.tarifa).toFixed(2)}</option>
          ))}
        </select>
        <input
          type="number"
          min="0"
          step="0.01"
          value={monto}
          onChange={(event) => setMonto(event.target.value)}
          placeholder="Monto $"
          style={{ ...deliveryEditorInputStyle, width: 120 }}
        />
      </div>
      {montoDistinto ? (
        <div style={{ color: 'var(--vg-f-ffcf7d)', fontSize: 12 }}>
          Es distinto a la tarifa de la zona (${Number(zonaActual.tarifa).toFixed(2)}); queda registrado en el pedido.
        </div>
      ) : null}
      <div style={{ display: 'flex', gap: 8 }}>
        <button type="button" onClick={guardar} disabled={guardando} style={deliveryEditorSaveStyle}>
          {guardando ? 'Guardando...' : 'Guardar'}
        </button>
        <button type="button" onClick={() => setAbierto(false)} disabled={guardando} style={deliveryEditorButtonStyle}>
          Cancelar
        </button>
      </div>
    </div>
  );
}

const deliveryEditorStyle = { display: 'grid', gap: 8, padding: '10px 12px', borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.12)', background: 'rgba(var(--vg-ink), 0.03)' };
const deliveryEditorInputStyle = { borderRadius: 10, border: '1px solid rgba(var(--vg-ink), 0.16)', background: 'var(--vg-s-161010)', padding: '8px 10px', color: 'var(--vg-text-strong)', fontSize: 13 };
const deliveryEditorButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.16)', borderRadius: 999, padding: '7px 14px', background: 'rgba(var(--vg-ink), 0.05)', color: 'var(--vg-f-ff9d9d)', fontWeight: 700, cursor: 'pointer', fontSize: 12.5 };
const deliveryEditorSaveStyle = { border: 'none', borderRadius: 999, padding: '8px 16px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: 12.5 };

function renderDetailItemRow(item, tasaCambio, { canGestionarItems = false, onAjustarItem, soloItem = false } = {}) {
  const cantidadLabel = item.peso_gramos ? `${item.peso_gramos} g` : `${item.cantidad}x`;
  const lineTotal = item.subtotal !== undefined ? Number(item.subtotal) : Number(item.precio_unitario) * item.cantidad;
  return (
    <div key={item.id} style={{ display: 'grid', gap: 3 }}>
      <div style={detailItemRowStyle}>
        <span style={{ color: 'var(--vg-text-strong)' }}>{cantidadLabel} {item.producto}</span>
        <span style={{ color: 'var(--vg-f-d2c4c4)' }}>${item.precio_unitario}{item.venta_por_peso ? '/kg' : ' c/u'}</span>
        <span style={{ color: 'var(--vg-f-ffcf7d)', fontWeight: 700 }}>
          ${lineTotal.toFixed(2)}
          <BsAmount amountUsd={lineTotal} tasa={tasaCambio} />
        </span>
      </div>
      {canGestionarItems && !soloItem ? (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button type="button" onClick={() => onAjustarItem('eliminar', item)} style={ajusteItemButtonStyle('eliminar')}>
            Quitar item
          </button>
          <button type="button" onClick={() => onAjustarItem('mover', item)} style={ajusteItemButtonStyle('mover')}>
            Mover a otra mesa
          </button>
        </div>
      ) : null}
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
  gap: 12,
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
  color: 'var(--vg-f-f7a5a5)',
  marginBottom: 4,
};

const titleStyle = (isMobile) => ({
  margin: 0,
  color: 'var(--vg-text-strong)',
  fontSize: isMobile ? 22 : 26,
  fontWeight: 700,
});

const subtitleStyle = {
  margin: '8px 0 0',
  color: 'var(--vg-f-d2c3c3)',
  lineHeight: 1.6,
  maxWidth: 640,
};

const backButtonStyle = (isMobile) => ({
  border: '1px solid var(--vg-f-ff7373-a340)',
  borderRadius: 999,
  padding: isMobile ? '11px 16px' : '10px 16px',
  background: 'rgba(var(--vg-ink), 0.03)',
  color: 'var(--vg-text-strong)',
  fontWeight: 600,
  cursor: 'pointer',
  width: isMobile ? '100%' : 'auto',
});

const emptyStateStyle = {
  minHeight: 100,
  display: 'grid',
  placeItems: 'center',
  borderRadius: 24,
  border: '1px dashed rgba(var(--vg-ink), 0.14)',
  background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)',
  color: 'var(--vg-f-c8bbbb)',
  textAlign: 'center',
  padding: 20,
};

const errorStyle = {
  padding: '12px 14px',
  borderRadius: 16,
  border: '1px solid var(--vg-f-ff9191-a220)',
  background: 'rgba(255, 98, 98, 0.12)',
  color: 'var(--vg-f-ffd8d8)',
};

const mesaSearchInputStyle = {
  width: '100%',
  boxSizing: 'border-box',
  borderRadius: 10,
  border: '1px solid var(--cb-input-border)',
  background: 'var(--cb-input-bg)',
  padding: '9px 12px',
  color: 'var(--cb-title)',
  fontSize: 14,
};

const mesaOptionEmptyStyle = {
  padding: 14,
  borderRadius: 14,
  border: '1px dashed rgba(var(--vg-ink), 0.14)',
  color: 'var(--vg-f-c8bbbb)',
  textAlign: 'center',
  fontSize: 13,
};

const groupCardStyle = {
  display: 'flex',
  flexDirection: 'column',
  gap: 12,
  padding: '16px',
  borderRadius: 16,
  background: 'var(--cb-card-bg)',
  border: '1px solid var(--cb-card-border)',
  boxShadow: 'var(--cb-card-shadow)',
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
  background: 'rgba(var(--vg-ink), 0.08)',
  color: 'var(--vg-f-ffb0b0)',
  fontSize: 12,
  fontWeight: 700,
};

const orderCardStyle = {
  borderRadius: 12,
  border: '1px solid var(--cb-row-border)',
  background: 'var(--cb-row-bg)',
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
  color: 'var(--vg-text-strong)',
  fontWeight: 600,
};

const orderPriceStyle = {
  color: 'var(--vg-f-ffcf7d)',
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
  color: 'var(--vg-f-d2c4c4)',
  fontSize: 12,
  minWidth: 0,
};

const orderActionsStyle = {
  display: 'flex',
  gap: 6,
  flexShrink: 0,
};

const selectAllButtonStyle = {
  border: '1px solid rgba(var(--vg-ink), 0.16)',
  borderRadius: 999,
  padding: '4px 10px',
  background: 'rgba(var(--vg-ink), 0.05)',
  color: 'var(--vg-f-e0c9a3)',
  fontSize: 11.5,
  fontWeight: 700,
  cursor: 'pointer',
  flexShrink: 0,
  whiteSpace: 'nowrap',
};

const detailToggleStyle = {
  border: '1px solid rgba(var(--vg-ink), 0.16)',
  borderRadius: 999,
  padding: '5px 12px',
  background: 'rgba(var(--vg-ink), 0.05)',
  color: 'var(--vg-text-strong)',
  fontSize: 12,
  fontWeight: 700,
  cursor: 'pointer',
  flexShrink: 0,
};

const cancelOrderToggleStyle = {
  border: '1px solid var(--vg-f-ff6666-a450)',
  borderRadius: 999,
  padding: '5px 12px',
  background: 'rgba(255, 73, 73, 0.1)',
  color: 'var(--vg-f-ffb3b3)',
  fontSize: 12,
  fontWeight: 700,
  cursor: 'pointer',
  flexShrink: 0,
};

const orderDetailStyle = {
  display: 'grid',
  gap: 8,
  padding: '4px 12px 14px',
  borderTop: '1px solid rgba(var(--vg-ink), 0.06)',
};

const detailMetaRowStyle = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 12,
  color: 'var(--vg-f-d2c4c4)',
  fontSize: 12,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
};

const detailNoteStyle = {
  padding: '8px 10px',
  borderRadius: 10,
  background: 'rgba(255, 145, 145, 0.1)',
  border: '1px solid var(--vg-f-ff9191-a200)',
  color: 'var(--vg-f-ffd8d8)',
  fontSize: 13,
};

const ajusteItemButtonStyle = (modo) => ({
  justifySelf: 'start',
  border: modo === 'eliminar' ? '1px solid var(--vg-f-ff6666-a450)' : '1px solid var(--vg-f-f59e0b-a450)',
  borderRadius: 999,
  padding: '4px 10px',
  background: modo === 'eliminar' ? 'rgba(255, 73, 73, 0.1)' : 'rgba(245, 158, 11, 0.1)',
  color: modo === 'eliminar' ? 'var(--vg-f-ffb3b3)' : 'var(--vg-f-f5c778)',
  fontSize: 11,
  fontWeight: 700,
  cursor: 'pointer',
});

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
  border: '1px solid var(--vg-f-7dc8ff-a280)',
  background: 'rgba(90, 170, 255, 0.05)',
};

const platoGroupTitleStyle = {
  color: 'var(--vg-f-bfe0ff)',
  fontWeight: 800,
  fontSize: 11,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
};

const itemNoteDetailStyle = {
  color: 'var(--vg-f-e8bcbc)',
  fontSize: 12,
  fontStyle: 'italic',
};

const detailTotalsStyle = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 14,
  paddingTop: 8,
  borderTop: '1px solid rgba(var(--vg-ink), 0.06)',
  color: 'var(--vg-f-d2c4c4)',
  fontSize: 13,
};

const groupFooterStyle = (isMobile) => ({
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: isMobile ? 'flex-start' : 'center',
  flexDirection: isMobile ? 'column' : 'row',
  gap: 10,
  paddingTop: 10,
  borderTop: '1px solid rgba(var(--vg-ink), 0.08)',
});

const selectStyle = {
  borderRadius: 12,
  border: '1px solid var(--cb-input-border)',
  background: 'var(--cb-input-bg)',
  padding: '9px 10px',
  color: 'var(--cb-title)',
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

const tasaCuentaAvisoStyle = {
  display: 'grid', gap: 8, padding: '10px 14px', borderRadius: 12,
  border: '1px solid var(--vg-f-ffcf7d-a450)', background: 'rgba(255, 207, 125, 0.08)',
  color: 'var(--vg-f-ffe3a3)', fontSize: 14, lineHeight: 1.5,
};
const tasaCuentaOpcionStyle = { display: 'flex', alignItems: 'center', gap: 8, color: 'var(--vg-f-f2e6e6)', fontWeight: 600, cursor: 'pointer' };
const clienteHintStyle = {
  margin: 0,
  color: 'var(--vg-f-a89999)',
  fontSize: 12,
};

const clienteSeccionTituloStyle = {
  color: 'var(--vg-f-d2c3c3)',
  fontSize: 11.5,
  fontWeight: 800,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  marginTop: 4,
};

const descuentoBlockStyle = {
  display: 'grid',
  gap: 8,
  padding: '10px 12px',
  borderRadius: 14,
  border: '1px solid var(--vg-f-9fd8ff-a250)',
  background: 'rgba(159, 216, 255, 0.06)',
};
const descuentoCheckboxRowStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  color: 'var(--vg-f-d2e9ff)',
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
};
const descuentoFieldsRowStyle = {
  display: 'flex',
  gap: 8,
  flexWrap: 'wrap',
};

const inputStyle = {
  width: '100%',
  boxSizing: 'border-box',
  borderRadius: 12,
  border: '1px solid var(--cb-input-border)',
  background: 'var(--cb-input-bg)',
  padding: '9px 10px',
  color: 'var(--cb-title)',
  fontSize: 13,
};

const docButtonsRowStyle = (isMobile) => ({
  display: 'flex',
  gap: 8,
  flexWrap: 'wrap',
  flexDirection: isMobile ? 'column' : 'row',
});

const secondaryButtonStyle = {
  border: '1px solid rgba(var(--vg-ink), 0.16)',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'rgba(var(--vg-ink), 0.05)',
  color: 'var(--vg-text-strong)',
  fontWeight: 700,
  cursor: 'pointer',
};

const primaryButtonStyle = {
  border: 'none',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'linear-gradient(90deg, #bf1f1f 0%, var(--vg-accent-primary) 100%)',
  color: '#fff',
  fontWeight: 800,
  cursor: 'pointer',
};

const prefacturaPanelStyle = {
  display: 'grid',
  gap: 8,
  padding: '12px 14px',
  borderRadius: 14,
  border: '1px solid var(--vg-f-ffbe78-a300)',
  background: 'rgba(255, 190, 120, 0.06)',
};

const lineaRowStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  fontSize: 13,
  color: 'var(--vg-f-e8dede)',
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
  color: 'var(--vg-f-a89999)',
  fontSize: 12,
  lineHeight: 1.5,
  maxWidth: 640,
};

const ingresoExtraHistoryTitleStyle = {
  marginTop: 18,
  color: 'var(--vg-f-ffb0b0)',
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
  border: '1px solid rgba(var(--vg-ink), 0.1)',
  background: 'rgba(var(--vg-ink), 0.03)',
  padding: '10px 12px',
};

const propinaTagStyle = {
  borderRadius: 999,
  padding: '3px 10px',
  fontSize: 11,
  fontWeight: 800,
  textTransform: 'uppercase',
  color: 'var(--vg-f-d9c8ff)',
  background: 'rgba(139, 92, 246, 0.18)',
  border: '1px solid var(--vg-f-a78bfa-a400)',
};

const pagoExtraTagStyle = {
  borderRadius: 999,
  padding: '3px 10px',
  fontSize: 11,
  fontWeight: 800,
  textTransform: 'uppercase',
  color: 'var(--vg-f-b6fff0)',
  background: 'rgba(13, 148, 136, 0.18)',
  border: '1px solid var(--vg-f-2dd4bf-a400)',
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
  border: '1px solid var(--vg-f-ff9191-a300)',
  background: 'linear-gradient(180deg, var(--vg-s-1c0c0c-a980) 0%, var(--vg-s-0a0808-a990) 100%)',
  padding: '22px 22px 18px',
  boxShadow: '0 20px 50px rgba(0, 0, 0, calc(0.45 * var(--vg-shadow-k)))',
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
  color: 'var(--vg-text-strong)',
  fontSize: 20,
  lineHeight: 1,
  cursor: 'pointer',
  display: 'grid',
  placeItems: 'center',
};

const ingresoModalTitleStyle = {
  color: 'var(--vg-text-strong)',
  fontSize: 19,
  fontWeight: 800,
  paddingRight: 30,
};

const ingresoModalDescStyle = {
  margin: 0,
  color: 'var(--vg-f-d2c3c3)',
  lineHeight: 1.5,
  fontSize: 13,
};

const ingresoFieldLabelStyle = {
  display: 'grid',
  gap: 6,
  color: 'var(--vg-f-e8dede)',
  fontSize: 13,
  fontWeight: 700,
};

const ingresoInputStyle = {
  width: '100%',
  boxSizing: 'border-box',
  borderRadius: 12,
  border: '1px solid var(--cb-input-border)',
  background: 'var(--cb-input-bg)',
  padding: '10px 12px',
  color: 'var(--cb-title)',
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

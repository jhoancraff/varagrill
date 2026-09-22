import { useCallback, useEffect, useRef, useState } from 'react';
import ConfirmModal from './ConfirmModal';
import useExchangeRate from '../hooks/useExchangeRate';
import { formatBsRaw, formatMontoDocumento } from '../utils/currency';

function getCookie(name) {
  const all = `; ${document.cookie}`;
  const parts = all.split(`; ${name}=`);
  if (parts.length === 2) {
    return parts.pop().split(';').shift();
  }
  return '';
}

function hoyISO() {
  const now = new Date();
  const offsetMs = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - offsetMs).toISOString().slice(0, 10);
}

function estadoLabel(estado) {
  if (estado === 'pendiente_pago') return 'Pendiente';
  if (estado === 'abonada_parcial') return 'Abonada';
  if (estado === 'pagada') return 'Pagada';
  if (estado === 'anulada') return 'Anulada';
  return estado;
}

// Cuando la cajera no escribe una referencia (pago en efectivo, o el metodo no
// la exige), el backend igual guarda una autogenerada (COBRO-.../ABONO-...)
// para que el pago nunca quede sin referencia — esa no es información útil
// para mostrarle a nadie, así que se filtra acá.
function esReferenciaAutogenerada(referencia) {
  return /^(COBRO|ABONO)-\d{14}-\d+$/.test(referencia || '');
}

const NOTAS_POR_PAGINA = 30;

const MOTIVOS_DEVOLUCION = [
  { valor: 'calidad_plato', etiqueta: 'Calidad del plato' },
  { valor: 'error_mesero', etiqueta: 'Error de mesero / toma de pedido' },
  { valor: 'cliente_cambio', etiqueta: 'Cliente cambió de opinión' },
  { valor: 'error_cobro', etiqueta: 'Error en el cobro' },
  { valor: 'otro', etiqueta: 'Otro' },
];

// "Por qué se anuló" (motivo) y "qué pasa con el dinero" (tipo de resolución)
// son preguntas independientes — ver revertir_y_reabrir_pedido en
// devoluciones_views.py. Solo 'reembolso' descuenta del banco/caja.
const TIPOS_RESOLUCION_DEVOLUCION = [
  { valor: 'reembolso', etiqueta: 'Reembolso — se le devuelve el dinero al cliente', ayuda: 'Sale plata del banco/caja. No se reabre ningún pedido.' },
  { valor: 'canje_item', etiqueta: 'Canje de un ítem — solo se cambia un plato', ayuda: 'El resto de la nota sigue igual (no se anula ni se cancela nada más). Solo se marca merma de ese plato y armas su reemplazo.' },
  { valor: 'canje', etiqueta: 'Canje de toda la cuenta — se lleva otros platos por el mismo valor', ayuda: 'Anula la nota completa (todos los platos quedan como merma). Úsalo solo si el cliente devuelve TODO el pedido, no un ítem suelto.' },
  { valor: 'credito_futuro', etiqueta: 'Crédito — queda a favor para una próxima compra', ayuda: 'El dinero se queda, no se reabre nada hoy. Requiere que el pedido tenga un cliente identificado.' },
  { valor: 'ajuste_parcial', etiqueta: 'Ajuste parcial — se baja el monto sin anular nada', ayuda: 'La nota NO se anula: solo se le reduce el total y el saldo pendiente por el monto del ajuste (ej. medio plato dañado, cliente pagó de menos y ya se fue).' },
];

function NotasEntregaHistorialPage({ isMobile, onBack, embedded = false, refreshToken, onArmarCanje }) {
  const tasaCambio = useExchangeRate();
  const [desde, setDesde] = useState(hoyISO);
  const [hasta, setHasta] = useState(hoyISO);
  const [notas, setNotas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reprintingId, setReprintingId] = useState(null);
  const [feedback, setFeedback] = useState('');
  const [feedbackType, setFeedbackType] = useState('success');

  const [selectedNotaId, setSelectedNotaId] = useState(null);
  const [notaDetalle, setNotaDetalle] = useState(null);
  const [loadingDetalle, setLoadingDetalle] = useState(false);
  const [metodosPago, setMetodosPago] = useState([]);
  const [montoAbono, setMontoAbono] = useState('');
  const [metodoAbono, setMetodoAbono] = useState('');
  const [referenciaAbono, setReferenciaAbono] = useState('');
  const [filtroEstado, setFiltroEstado] = useState('todas');
  const [busquedaCodigo, setBusquedaCodigo] = useState('');
  const [paginaActual, setPaginaActual] = useState(1);
  const [savingAbono, setSavingAbono] = useState(false);
  const [confirmCambioMetodo, setConfirmCambioMetodo] = useState(null); // { metodo_anterior, metodo_nuevo, message }

  const [devolucionOpen, setDevolucionOpen] = useState(false);
  const [devolucionMotivo, setDevolucionMotivo] = useState(MOTIVOS_DEVOLUCION[0].valor);
  const [devolucionTipoResolucion, setDevolucionTipoResolucion] = useState(TIPOS_RESOLUCION_DEVOLUCION[0].valor);
  const [devolucionMontoAjuste, setDevolucionMontoAjuste] = useState('');
  // Saldar el saldo pendiente completo usa documento.saldo_pendiente tal cual
  // (ya en dólares) en vez de convertir un monto en Bs escrito a mano — es la
  // única forma de dejar la nota en exactamente $0.00 sin arrastrar el
  // redondeo de la conversión (reportado 2026-09: un ajuste en Bs dejaba el
  // total un par de bolívares desfasado del monto que el cliente pagó).
  const [devolucionSaldarCompleto, setDevolucionSaldarCompleto] = useState(false);
  const [devolucionItemId, setDevolucionItemId] = useState('');
  const [devolucionDetalle, setDevolucionDetalle] = useState('');
  const [devolucionUser, setDevolucionUser] = useState('');
  const [devolucionPass, setDevolucionPass] = useState('');
  const [devolucionSaving, setDevolucionSaving] = useState(false);
  const [devolucionError, setDevolucionError] = useState('');
  // Cuando la devolución es un canje, queda pendiente armar el plato de
  // reemplazo (ver onArmarCanje) — se recuerda acá para mostrar el botón
  // justo después de confirmar, sin tener que ir a buscar la NC al reporte.
  const [canjePendiente, setCanjePendiente] = useState(null); // { notaCreditoId, codigo }

  // Ver DETAIL_STICKY_TOP más abajo: mide el placeholder y decide si el panel
  // de detalle/abono pasa a `position: fixed` para seguir el scroll.
  const detailPlaceholderRef = useRef(null);
  const detailPanelRef = useRef(null);
  const lastPanelHeightRef = useRef(200);
  const [detailFixed, setDetailFixed] = useState(false);
  const [detailFixedRect, setDetailFixedRect] = useState({ left: 0, width: 0 });

  const fetchNotas = useCallback(async (desdeBuscado, hastaBuscado) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (desdeBuscado) {
        params.set('desde', desdeBuscado);
      }
      if (hastaBuscado) {
        params.set('hasta', hastaBuscado);
      }
      const response = await fetch(`/api/notas-entrega/?${params.toString()}`, { credentials: 'include', cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setError(data.message || 'No se pudieron cargar las notas de entrega.');
        return;
      }
      setNotas(Array.isArray(data.notas_entrega) ? data.notas_entrega : []);
      setError('');
    } catch (requestError) {
      setError('Error de red al cargar las notas de entrega.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchNotas(desde, hasta);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshToken]);

  useEffect(() => {
    const loadMetodosPago = async () => {
      try {
        const response = await fetch('/api/metodos-pago/', { credentials: 'include', cache: 'no-store' });
        const data = await response.json().catch(() => ({}));
        if (response.ok && data.ok) {
          setMetodosPago(Array.isArray(data.metodos_pago) ? data.metodos_pago : []);
        }
      } catch (requestError) {
        // El selector queda vacio si falla.
      }
    };
    loadMetodosPago();
  }, []);

  const handleBuscar = (event) => {
    event.preventDefault();
    if (desde && hasta && desde > hasta) {
      setError('"Desde" no puede ser posterior a "Hasta".');
      return;
    }
    fetchNotas(desde, hasta);
  };

  const fetchNotaDetalle = useCallback(async (notaId) => {
    setLoadingDetalle(true);
    try {
      const response = await fetch(`/api/notas-entrega/${notaId}/`, { credentials: 'include', cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setFeedbackType('error');
        setFeedback(data.message || 'No se pudo cargar el detalle de la nota de entrega.');
        return;
      }
      setNotaDetalle(data.nota_entrega);
    } catch (requestError) {
      setFeedbackType('error');
      setFeedback('Error de red al cargar el detalle de la nota de entrega.');
    } finally {
      setLoadingDetalle(false);
    }
  }, []);

  const handleSelectNota = (nota) => {
    setFeedback('');
    setMontoAbono('');
    setReferenciaAbono('');
    setSelectedNotaId(nota.id);
    fetchNotaDetalle(nota.id);
  };

  const handleReimprimir = async (nota) => {
    setReprintingId(nota.id);
    setFeedback('');
    try {
      const response = await fetch(`/api/notas-entrega/${nota.id}/reimprimir/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrftoken') || '' },
        credentials: 'include',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setFeedbackType('error');
        setFeedback(data.message || 'No se pudo reimprimir la nota de entrega.');
        return;
      }
      setFeedbackType('success');
      setFeedback(data.message || `Nota de entrega ${nota.codigo} reenviada a la impresora.`);
    } catch (requestError) {
      setFeedbackType('error');
      setFeedback('Error de red al reimprimir la nota de entrega.');
    } finally {
      setReprintingId(null);
    }
  };

  const enviarAbono = async (metodoPagoId, confirmarCambioMetodo = false) => {
    const response = await fetch(`/api/notas-entrega/${selectedNotaId}/abonos/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') || '' },
      credentials: 'include',
      body: JSON.stringify({
        monto: montoAbono,
        metodo_pago_id: metodoPagoId,
        referencia: referenciaAbono.trim(),
        confirmar_cambio_metodo: confirmarCambioMetodo,
      }),
    });
    return { response, data: await response.json().catch(() => ({})) };
  };

  const handleRegistrarAbono = async (event) => {
    event.preventDefault();
    if (!selectedNotaId) {
      return;
    }
    const metodoPagoId = metodoAbono || (metodosPago[0] && metodosPago[0].id);
    if (!metodoPagoId) {
      setFeedbackType('error');
      setFeedback('No hay metodos de pago activos configurados.');
      return;
    }
    const metodo = metodosPago.find((item) => item.id === metodoPagoId);
    if (metodo && !metodo.es_efectivo && !referenciaAbono.trim()) {
      setFeedbackType('error');
      setFeedback(`Indica el número de referencia del pago por ${metodo.nombre}.`);
      return;
    }

    setSavingAbono(true);
    setFeedback('');
    try {
      const { response, data } = await enviarAbono(metodoPagoId, false);
      if (!response.ok || !data.ok) {
        // La nota se generó con otra cuenta y esta se le está cobrando con una
        // distinta — el backend pide confirmación explícita antes de mover la
        // plata (ver requiere_confirmacion en nota_entrega_abono_view).
        if (data.requiere_confirmacion) {
          setConfirmCambioMetodo({ metodoPagoId, message: data.message });
          return;
        }
        setFeedbackType('error');
        setFeedback(data.message || 'No se pudo registrar el abono.');
        return;
      }
      setFeedbackType('success');
      setFeedback(`Abono de $${Number(data.pago.monto).toFixed(2)} registrado. Saldo pendiente: $${Number(data.nota_entrega.saldo_pendiente).toFixed(2)}.`);
      setNotaDetalle(data.nota_entrega);
      setMontoAbono('');
      setReferenciaAbono('');
      await fetchNotas(desde, hasta);
    } catch (requestError) {
      setFeedbackType('error');
      setFeedback('Error de red al registrar el abono.');
    } finally {
      setSavingAbono(false);
    }
  };

  const handleConfirmarCambioMetodo = async () => {
    if (!confirmCambioMetodo) {
      return;
    }
    setSavingAbono(true);
    try {
      const { response, data } = await enviarAbono(confirmCambioMetodo.metodoPagoId, true);
      if (!response.ok || !data.ok) {
        setFeedbackType('error');
        setFeedback(data.message || 'No se pudo registrar el abono.');
        return;
      }
      setFeedbackType('success');
      setFeedback(`Abono de $${Number(data.pago.monto).toFixed(2)} registrado (cuenta cambiada). Saldo pendiente: $${Number(data.nota_entrega.saldo_pendiente).toFixed(2)}.`);
      setNotaDetalle(data.nota_entrega);
      setMontoAbono('');
      setReferenciaAbono('');
      await fetchNotas(desde, hasta);
    } catch (requestError) {
      setFeedbackType('error');
      setFeedback('Error de red al registrar el abono.');
    } finally {
      setSavingAbono(false);
      setConfirmCambioMetodo(null);
    }
  };

  const handleAbrirDevolucion = () => {
    setDevolucionMotivo(MOTIVOS_DEVOLUCION[0].valor);
    setDevolucionTipoResolucion(TIPOS_RESOLUCION_DEVOLUCION[0].valor);
    setDevolucionMontoAjuste('');
    setDevolucionSaldarCompleto(false);
    setDevolucionItemId('');
    setDevolucionDetalle('');
    setDevolucionUser('');
    setDevolucionPass('');
    setDevolucionError('');
    setCanjePendiente(null);
    setDevolucionOpen(true);
  };

  const handleConfirmarDevolucion = async (event) => {
    event.preventDefault();
    if (!selectedNotaId) {
      return;
    }
    if (!devolucionUser.trim() || !devolucionPass) {
      setDevolucionError('El Gerente/Supervisor debe indicar su usuario y contraseña.');
      return;
    }
    if (devolucionTipoResolucion === 'ajuste_parcial' && !devolucionSaldarCompleto && !(Number(devolucionMontoAjuste) > 0)) {
      setDevolucionError('Indica el monto del ajuste (debe ser mayor a cero) o marca "Saldar completo".');
      return;
    }
    if (devolucionTipoResolucion === 'canje_item' && !devolucionItemId) {
      setDevolucionError('Selecciona el ítem a cambiar.');
      return;
    }
    setDevolucionSaving(true);
    setDevolucionError('');
    try {
      const response = await fetch('/api/devoluciones/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') || '' },
        credentials: 'include',
        body: JSON.stringify({
          documento_tipo: 'nota_entrega',
          documento_id: selectedNotaId,
          motivo: devolucionMotivo,
          motivo_detalle: devolucionDetalle.trim(),
          tipo_resolucion: devolucionTipoResolucion,
          saldar_completo: ['ajuste_parcial', 'canje_item'].includes(devolucionTipoResolucion) ? devolucionSaldarCompleto : undefined,
          monto_ajuste: ['ajuste_parcial', 'canje_item'].includes(devolucionTipoResolucion) && !devolucionSaldarCompleto
            ? devolucionMontoAjuste
            : undefined,
          detalle_pedido_id: devolucionTipoResolucion === 'canje_item' ? devolucionItemId : undefined,
          autorizador_username: devolucionUser.trim(),
          autorizador_password: devolucionPass,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setDevolucionError(data.message || 'No se pudo registrar la devolución.');
        return;
      }
      setDevolucionOpen(false);
      setFeedbackType('success');
      const detalleResultado = devolucionTipoResolucion === 'ajuste_parcial'
        ? `nuevo total $${Number(data.documento_nuevo_total).toFixed(2)}, saldo pendiente $${Number(data.documento_nuevo_saldo_pendiente).toFixed(2)}.`
        : devolucionTipoResolucion === 'canje_item'
          ? `nuevo total $${Number(data.documento_nuevo_total).toFixed(2)} — falta armar el plato de cambio.`
          : data.credito_generado
            ? `crédito de $${Number(data.credito_generado.saldo_disponible).toFixed(2)} a favor del cliente.`
            : devolucionTipoResolucion === 'canje'
              ? 'falta armar el plato de cambio.'
              : 'el cliente ya se fue con su reembolso.';
      setFeedback(`${data.message} — ${detalleResultado}`);
      setCanjePendiente(
        ['canje', 'canje_item'].includes(devolucionTipoResolucion)
          ? { notaCreditoId: data.nota_credito.id, codigo: data.nota_credito.codigo }
          : null,
      );
      await fetchNotas(desde, hasta);
      await fetchNotaDetalle(selectedNotaId);
    } catch (requestError) {
      setDevolucionError('Error de red al registrar la devolución.');
    } finally {
      setDevolucionSaving(false);
    }
  };

  const busquedaCodigoTerm = busquedaCodigo.trim().toLowerCase();
  const notasFiltradas = notas.filter((nota) => {
    if (filtroEstado === 'pendientes' && ['pagada', 'anulada'].includes(nota.estado)) return false;
    if (filtroEstado === 'pagadas' && nota.estado !== 'pagada') return false;
    if (busquedaCodigoTerm && !(nota.codigo || '').toLowerCase().includes(busquedaCodigoTerm)) return false;
    return true;
  });

  // 30 tarjetas por página (en vez de todo el historial de una vez) para no
  // obligar a la cajera a hacer scroll infinito buscando una nota — ver
  // totalPaginas/flechas de navegación más abajo.
  const totalPaginas = Math.max(1, Math.ceil(notasFiltradas.length / NOTAS_POR_PAGINA));
  const paginaSegura = Math.min(paginaActual, totalPaginas);
  const notasPagina = notasFiltradas.slice(
    (paginaSegura - 1) * NOTAS_POR_PAGINA,
    paginaSegura * NOTAS_POR_PAGINA,
  );

  useEffect(() => {
    setPaginaActual(1);
  }, [filtroEstado, busquedaCodigo, notas]);

  useEffect(() => {
    const medir = () => {
      if (!detailPlaceholderRef.current) return;
      if (!detailFixed && detailPanelRef.current) {
        lastPanelHeightRef.current = detailPanelRef.current.getBoundingClientRect().height;
      }
      const rect = detailPlaceholderRef.current.getBoundingClientRect();
      setDetailFixed(rect.top < DETAIL_STICKY_TOP);
      setDetailFixedRect({ left: rect.left, width: rect.width });
    };
    medir();
    window.addEventListener('scroll', medir, { passive: true });
    window.addEventListener('resize', medir);
    return () => {
      window.removeEventListener('scroll', medir);
      window.removeEventListener('resize', medir);
    };
    // Se vuelve a medir cuando cambia el contenido del panel (selección de
    // nota, detalle cargado, o la página de la lista) porque eso cambia su
    // alto y, por lo tanto, en qué punto del scroll debería engancharse.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNotaId, notaDetalle, notasPagina.length, isMobile]);

  return (
    <section style={containerStyle(isMobile, embedded)}>
      {!embedded ? (
        <div style={headerWrapStyle(isMobile)}>
          <div>
            <div style={eyebrowStyle}>Contabilidad</div>
            <h2 style={titleStyle(isMobile)}>Historial de notas de entrega</h2>
            <p style={subtitleStyle}>
              Busca las notas de entrega emitidas por rango de fecha, registra sus abonos y reimprímelas si el cliente necesita otra copia.
            </p>
          </div>
          <button type="button" onClick={onBack} style={backButtonStyle(isMobile)}>
            Volver
          </button>
        </div>
      ) : (
        <div style={embeddedHeaderStyle}>Historial de notas de entrega · Abonos y reimpresión</div>
      )}

      <form onSubmit={handleBuscar} style={buscadorFormStyle(isMobile)}>
        <label style={dateFieldStyle}>
          <span style={dateLabelStyle}>Desde</span>
          <input
            type="date"
            value={desde}
            onChange={(event) => setDesde(event.target.value)}
            style={inputStyle}
            className="admin-dark-select"
          />
        </label>
        <label style={dateFieldStyle}>
          <span style={dateLabelStyle}>Hasta</span>
          <input
            type="date"
            value={hasta}
            onChange={(event) => setHasta(event.target.value)}
            style={inputStyle}
            className="admin-dark-select"
          />
        </label>
        <button type="submit" style={secondaryButtonStyle} disabled={loading}>
          {loading ? 'Buscando...' : 'Buscar'}
        </button>
        <label style={dateFieldStyle}>
          <span style={dateLabelStyle}>Estado</span>
          <select
            value={filtroEstado}
            onChange={(event) => setFiltroEstado(event.target.value)}
            style={inputStyle}
            className="admin-dark-select"
          >
            <option value="todas">Todas</option>
            <option value="pendientes">Pendientes</option>
            <option value="pagadas">Pagadas</option>
          </select>
        </label>
        <label style={dateFieldStyle}>
          <span style={dateLabelStyle}>Nº de nota</span>
          <input
            type="text"
            value={busquedaCodigo}
            onChange={(event) => setBusquedaCodigo(event.target.value)}
            placeholder="Ej: 00000064"
            style={inputStyle}
          />
        </label>
      </form>

      {feedback ? <div style={feedbackStyle(feedbackType)}>{feedback}</div> : null}

      {canjePendiente && onArmarCanje ? (
        <div style={feedbackStyle('success')}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <span>{canjePendiente.codigo}: falta armar el plato de cambio para poder entregárselo al cliente.</span>
            <button
              type="button"
              onClick={() => {
                onArmarCanje({ notaCreditoId: canjePendiente.notaCreditoId, cliente: '' });
                setCanjePendiente(null);
              }}
              style={devolucionButtonStyle}
            >
              Armar plato de cambio
            </button>
          </div>
        </div>
      ) : null}

      {loading ? <div style={emptyStateStyle}>Cargando notas de entrega...</div> : null}
      {!loading && error ? <div style={errorStyle}>{error}</div> : null}
      {!loading && !error && notas.length === 0 ? (
        <div style={emptyStateStyle}>No hay notas de entrega registradas en ese rango de fechas.</div>
      ) : null}
      {!loading && !error && notas.length > 0 && notasFiltradas.length === 0 ? (
        <div style={emptyStateStyle}>
          {busquedaCodigoTerm
            ? `No hay ninguna nota de entrega que coincida con "${busquedaCodigo}".`
            : `No hay notas de entrega ${filtroEstado === 'pendientes' ? 'pendientes' : 'pagadas'} en ese rango de fechas.`}
        </div>
      ) : null}

      {!loading && !error && notasFiltradas.length > 0 ? (
        <div style={layoutStyle(isMobile)}>
          <div style={listColumnStyle}>
            <div style={listStyle}>
            {notasPagina.map((nota) => (
              <div key={nota.id} style={notaRowStyle(selectedNotaId === nota.id)}>
                <div style={{ display: 'grid', gap: 2 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                    <span style={{ color: '#fff', fontWeight: 700 }}>Nota de entrega {nota.codigo}</span>
                    <span style={estadoBadgeStyle(nota.estado)}>{estadoLabel(nota.estado)}</span>
                  </div>
                  <div style={{ color: '#d2c4c4', fontSize: 13 }}>
                    {nota.metodo_pago}
                    {' · '}
                    {new Date(nota.fecha_emision).toLocaleString('es-VE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
                    {' · '}
                    {nota.pedidos.length} pedido(s)
                    {nota.referencia && !esReferenciaAutogenerada(nota.referencia) ? ` · Ref: ${nota.referencia}` : ''}
                  </div>
                  <div style={{ color: '#ffcf7d', fontWeight: 700 }}>
                    Total: {formatMontoDocumento(nota.total, nota.moneda, nota.tasa_cambio_referencia || tasaCambio)}
                  </div>
                  {Number(nota.descuento_monto) > 0 ? (
                    <div style={{ color: '#9fd8ff', fontSize: 12.5 }} title={nota.descuento_motivo}>
                      Descuento aplicado: -${Number(nota.descuento_monto).toFixed(2)} — {nota.descuento_motivo}
                      {nota.creado_por ? ` (${nota.creado_por})` : ''}
                    </div>
                  ) : null}
                  {!['pagada', 'anulada'].includes(nota.estado) ? (
                    <div style={{ color: '#ff9b9b', fontWeight: 700 }}>
                      Saldo: {formatMontoDocumento(nota.saldo_pendiente, nota.moneda, nota.tasa_cambio_referencia || tasaCambio)}
                    </div>
                  ) : null}
                </div>
                <div style={rowActionsStyle}>
                  <button type="button" onClick={() => handleSelectNota(nota)} style={secondaryButtonStyle}>
                    Ver / Abonar
                  </button>
                  <button
                    type="button"
                    onClick={() => handleReimprimir(nota)}
                    style={secondaryButtonStyle}
                    disabled={reprintingId === nota.id}
                  >
                    {reprintingId === nota.id ? 'Enviando...' : 'Reimprimir'}
                  </button>
                </div>
              </div>
            ))}
            </div>
            {totalPaginas > 1 ? (
              <div style={paginacionBarStyle}>
                <button
                  type="button"
                  onClick={() => setPaginaActual((current) => Math.max(1, current - 1))}
                  disabled={paginaSegura <= 1}
                  style={paginacionBotonStyle(paginaSegura <= 1)}
                >
                  ← Anterior
                </button>
                <span style={paginacionInfoStyle}>
                  Página {paginaSegura} de {totalPaginas} · {notasFiltradas.length} nota(s)
                </span>
                <button
                  type="button"
                  onClick={() => setPaginaActual((current) => Math.min(totalPaginas, current + 1))}
                  disabled={paginaSegura >= totalPaginas}
                  style={paginacionBotonStyle(paginaSegura >= totalPaginas)}
                >
                  Siguiente →
                </button>
              </div>
            ) : null}
          </div>

          <div
            ref={detailPlaceholderRef}
            style={detailFixed ? { minHeight: lastPanelHeightRef.current } : undefined}
          >
          <div
            ref={detailPanelRef}
            style={
              detailFixed
                ? { ...detailPanelStyle, position: 'fixed', top: DETAIL_STICKY_TOP, left: detailFixedRect.left, width: detailFixedRect.width, zIndex: 5 }
                : detailPanelStyle
            }
          >
            {!selectedNotaId ? (
              <div style={emptyStateStyle}>Selecciona una nota de entrega para ver su detalle y registrar un abono.</div>
            ) : loadingDetalle || !notaDetalle ? (
              <div style={emptyStateStyle}>Cargando nota de entrega...</div>
            ) : (
              <>
                <div style={{ color: '#ffb0b0', fontWeight: 800, fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                  Nota de entrega {notaDetalle.codigo}
                </div>
                <div style={{ color: '#d2c4c4', fontSize: 13 }}>
                  {notaDetalle.metodo_pago}
                  {' · '}
                  {new Date(notaDetalle.fecha_emision).toLocaleString('es-VE')}
                  {' · '}
                  {notaDetalle.pedidos.length} pedido(s)
                </div>

                <div style={detailTotalsStyle}>
                  <span style={{ fontWeight: 800, color: '#fff' }}>
                    Total: {formatMontoDocumento(notaDetalle.total, notaDetalle.moneda, notaDetalle.tasa_cambio_referencia || tasaCambio)}
                  </span>
                  <span style={{ fontWeight: 800, color: '#ffcf7d' }}>
                    Saldo pendiente: {notaDetalle.moneda === 'VES' && notaDetalle.saldo_pendiente_bs_vigente
                      ? formatBsRaw(notaDetalle.saldo_pendiente_bs_vigente)
                      : formatMontoDocumento(notaDetalle.saldo_pendiente, notaDetalle.moneda, notaDetalle.tasa_cambio_referencia || tasaCambio)}
                  </span>
                </div>

                {!notaDetalle.es_de_hoy && notaDetalle.moneda === 'VES' && notaDetalle.estado !== 'pagada' ? (
                  <div style={fiadoRecalculadoStyle}>
                    Esta nota es de días anteriores — el saldo se recalculó a la tasa BCV de HOY
                    (Bs. {Number(notaDetalle.tasa_cobro_vigente || 0).toFixed(2)}/$), no a la tasa con la que se
                    cotizó originalmente (Bs. {Number(notaDetalle.tasa_cambio_referencia || 0).toFixed(2)}/$).
                    Cóbrale a este monto recalculado, no al que aparece impreso en la nota vieja.
                  </div>
                ) : null}

                {notaDetalle.estado !== 'anulada' ? (
                  <button type="button" onClick={handleAbrirDevolucion} style={devolucionButtonStyle}>
                    Devolución / ajuste
                  </button>
                ) : (
                  <div style={{ color: '#ffb0b0', fontWeight: 700, fontSize: 13 }} title={notaDetalle.motivo_anulacion}>
                    Anulada — {notaDetalle.motivo_anulacion || 'sin motivo registrado'}
                  </div>
                )}

                {notaDetalle.pagos.length > 0 ? (
                  <div style={{ display: 'grid', gap: 4 }}>
                    <div style={{ color: '#9fe3b0', fontWeight: 700, fontSize: 12, textTransform: 'uppercase' }}>Abonos registrados</div>
                    {notaDetalle.pagos.map((pago) => (
                      <div key={pago.id} style={lineaRowStyle}>
                        <span>
                          {pago.metodo_pago} — {new Date(pago.fecha_pago).toLocaleString('es-VE')}
                          {pago.referencia && !esReferenciaAutogenerada(pago.referencia) ? ` · Ref: ${pago.referencia}` : ''}
                        </span>
                        <span>{formatMontoDocumento(pago.monto, pago.moneda, pago.tasa_cambio_referencia || tasaCambio)}</span>
                      </div>
                    ))}
                  </div>
                ) : null}

                {!['pagada', 'anulada'].includes(notaDetalle.estado) ? (
                  <form onSubmit={handleRegistrarAbono} style={abonoFormStyle(isMobile)}>
                    <input
                      type="number"
                      min="0.01"
                      step="0.01"
                      placeholder={
                        metodosPago.find((item) => item.id === (metodoAbono || (metodosPago[0] && metodosPago[0].id)))?.moneda === 'VES'
                          ? 'Monto del abono (Bs)'
                          : 'Monto del abono ($)'
                      }
                      value={montoAbono}
                      onChange={(event) => setMontoAbono(event.target.value)}
                      style={inputStyle}
                      required
                    />
                    {/* El placeholder usa la moneda de la cuenta SELECCIONADA en el
                        select de abajo, no la de la nota — pueden ser distintas (ver
                        cambia_metodo en nota_entrega_abono_view): lo que importa para
                        saber si escribir dólares o bolívares es con qué cuenta se está
                        cobrando ESTE abono, no con la que se declaró al emitir la nota. */}
                    {/* Sin `required`: handleRegistrarAbono ya valida esto con un mensaje propio
                        (ver el bug de `required` nativo bloqueando el aviso, mismo criterio que
                        Mesa/Cliente en NewOrderPage/EditOrderPage). */}
                    {!(metodosPago.find((item) => item.id === (metodoAbono || (metodosPago[0] && metodosPago[0].id)))?.es_efectivo) ? (
                      <input
                        type="text"
                        placeholder="Número de referencia del pago"
                        value={referenciaAbono}
                        onChange={(event) => setReferenciaAbono(event.target.value)}
                        style={inputStyle}
                      />
                    ) : null}
                    <select
                      value={metodoAbono || (metodosPago[0] && metodosPago[0].id) || ''}
                      onChange={(event) => setMetodoAbono(Number(event.target.value))}
                      style={selectStyle}
                      className="admin-dark-select"
                    >
                      {metodosPago.map((metodo) => (
                        <option key={metodo.id} value={metodo.id}>{metodo.nombre}</option>
                      ))}
                    </select>
                    <button type="submit" style={primaryButtonStyle} disabled={savingAbono}>
                      {savingAbono ? 'Registrando...' : 'Registrar abono'}
                    </button>
                  </form>
                ) : (
                  <div style={{ color: '#9fe3b0', fontWeight: 700 }}>
                    {notaDetalle.estado === 'anulada' ? 'Esta nota de entrega esta anulada.' : 'Esta nota de entrega ya esta saldada.'}
                  </div>
                )}
              </>
            )}
          </div>
          </div>
        </div>
      ) : null}

      {devolucionOpen ? (
        <div style={backdropStyle} onClick={devolucionSaving ? undefined : () => setDevolucionOpen(false)}>
          <form
            onSubmit={handleConfirmarDevolucion}
            style={devolucionCardStyle}
            onClick={(event) => event.stopPropagation()}
          >
            <div style={{ color: '#fff', fontSize: 18, fontWeight: 800 }}>
              {devolucionTipoResolucion === 'ajuste_parcial'
                ? 'Ajustar nota cobrada'
                : devolucionTipoResolucion === 'canje_item'
                  ? 'Cambiar un ítem'
                  : 'Anular pedido cobrado'}
            </div>
            <p style={{ margin: 0, color: '#d2c3c3', fontSize: 13, lineHeight: 1.5 }}>
              {devolucionTipoResolucion === 'ajuste_parcial'
                ? `Esto emite una nota de crédito y le baja el total/saldo pendiente a ${notaDetalle?.codigo} sin anularla. Requiere autorización de un Gerente/Supervisor.`
                : devolucionTipoResolucion === 'canje_item'
                  ? `Esto NO anula ${notaDetalle?.codigo} — solo marca merma del ítem elegido y emite una nota de crédito. El resto de la cuenta sigue igual. Requiere autorización de un Gerente/Supervisor.`
                  : `Esto anula ${notaDetalle?.codigo} al 100% y emite una nota de crédito. Requiere autorización de un Gerente/Supervisor.`}
            </p>

            <label style={dateFieldStyle}>
              <span style={dateLabelStyle}>¿Qué pasa con el dinero?</span>
              <select
                value={devolucionTipoResolucion}
                onChange={(event) => setDevolucionTipoResolucion(event.target.value)}
                style={selectStyle}
                className="admin-dark-select"
              >
                {TIPOS_RESOLUCION_DEVOLUCION.map((tipo) => (
                  <option key={tipo.valor} value={tipo.valor}>{tipo.etiqueta}</option>
                ))}
              </select>
              <span style={{ color: '#a89999', fontSize: 11.5, lineHeight: 1.4 }}>
                {TIPOS_RESOLUCION_DEVOLUCION.find((tipo) => tipo.valor === devolucionTipoResolucion)?.ayuda}
              </span>
            </label>

            {devolucionTipoResolucion === 'ajuste_parcial' ? (
              <>
                <label style={{ ...dateFieldStyle, display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <input
                    type="checkbox"
                    checked={devolucionSaldarCompleto}
                    onChange={(event) => setDevolucionSaldarCompleto(event.target.checked)}
                  />
                  <span style={{ color: '#f2e6e6', fontSize: 13 }}>
                    Saldar el saldo pendiente completo
                    {notaDetalle ? (
                      <> — {notaDetalle.moneda === 'VES' && notaDetalle.saldo_pendiente_bs_vigente
                        ? formatBsRaw(notaDetalle.saldo_pendiente_bs_vigente)
                        : `$${Number(notaDetalle.saldo_pendiente).toFixed(2)}`}</>
                    ) : null}
                  </span>
                </label>
                {devolucionSaldarCompleto ? (
                  <span style={{ color: '#a89999', fontSize: 11.5, marginTop: -4 }}>
                    Deja el saldo en exactamente $0.00 — no hay que calcular ni escribir ningún monto en Bs.
                  </span>
                ) : (
                  <label style={dateFieldStyle}>
                    <span style={dateLabelStyle}>
                      Monto del ajuste ({notaDetalle?.moneda === 'VES' ? 'Bs' : '$'})
                    </span>
                    <input
                      type="number"
                      min="0.01"
                      step="0.01"
                      placeholder={notaDetalle?.moneda === 'VES' ? 'Ej: 8500.00' : 'Ej: 10.00'}
                      value={devolucionMontoAjuste}
                      onChange={(event) => setDevolucionMontoAjuste(event.target.value)}
                      style={inputStyle}
                    />
                    {notaDetalle?.moneda === 'VES' ? (
                      <span style={{ color: '#a89999', fontSize: 11.5 }}>
                        Se convierte a dólares a Bs. {Number(notaDetalle.tasa_cobro_vigente || notaDetalle.tasa_cambio_referencia || 0).toFixed(2)}/$ (la misma tasa que usarías para cobrar el saldo hoy).
                      </span>
                    ) : null}
                  </label>
                )}
              </>
            ) : null}

            {devolucionTipoResolucion === 'canje_item' ? (
              <>
                <label style={dateFieldStyle}>
                  <span style={dateLabelStyle}>¿Qué ítem se cambia?</span>
                  <select
                    value={devolucionItemId}
                    onChange={(event) => setDevolucionItemId(event.target.value)}
                    style={selectStyle}
                    className="admin-dark-select"
                  >
                    <option value="">Selecciona un ítem...</option>
                    {(notaDetalle?.items || []).map((item) => (
                      <option key={item.detalle_id} value={item.detalle_id}>
                        {item.cantidad}x {item.producto} — ${Number(item.subtotal).toFixed(2)} (pedido #{item.pedido_id})
                      </option>
                    ))}
                  </select>
                </label>
                <label style={{ ...dateFieldStyle, display: 'flex', flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <input
                    type="checkbox"
                    checked={devolucionSaldarCompleto}
                    onChange={(event) => setDevolucionSaldarCompleto(event.target.checked)}
                  />
                  <span style={{ color: '#f2e6e6', fontSize: 13 }}>
                    Saldar el saldo pendiente completo
                    {notaDetalle ? (
                      <> — {notaDetalle.moneda === 'VES' && notaDetalle.saldo_pendiente_bs_vigente
                        ? formatBsRaw(notaDetalle.saldo_pendiente_bs_vigente)
                        : `$${Number(notaDetalle.saldo_pendiente).toFixed(2)}`}</>
                    ) : null}
                  </span>
                </label>
                {devolucionSaldarCompleto ? (
                  <span style={{ color: '#a89999', fontSize: 11.5, marginTop: -4 }}>
                    Deja el saldo en exactamente $0.00 — no hay que calcular ni escribir ningún monto en Bs.
                  </span>
                ) : (
                  <label style={dateFieldStyle}>
                    <span style={dateLabelStyle}>
                      Monto a descontar si el reemplazo vale menos (opcional, en {notaDetalle?.moneda === 'VES' ? 'Bs' : '$'})
                    </span>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      placeholder="Vacío = mismo valor, no cambia el total"
                      value={devolucionMontoAjuste}
                      onChange={(event) => setDevolucionMontoAjuste(event.target.value)}
                      style={inputStyle}
                    />
                    {notaDetalle?.moneda === 'VES' && devolucionMontoAjuste ? (
                      <span style={{ color: '#a89999', fontSize: 11.5 }}>
                        Se convierte a dólares a Bs. {Number(notaDetalle.tasa_cobro_vigente || notaDetalle.tasa_cambio_referencia || 0).toFixed(2)}/$.
                      </span>
                    ) : null}
                  </label>
                )}
              </>
            ) : null}

            <label style={dateFieldStyle}>
              <span style={dateLabelStyle}>Motivo de la devolución</span>
              <select
                value={devolucionMotivo}
                onChange={(event) => setDevolucionMotivo(event.target.value)}
                style={selectStyle}
                className="admin-dark-select"
              >
                {MOTIVOS_DEVOLUCION.map((motivo) => (
                  <option key={motivo.valor} value={motivo.valor}>{motivo.etiqueta}</option>
                ))}
              </select>
            </label>

            <label style={dateFieldStyle}>
              <span style={dateLabelStyle}>Detalle (opcional)</span>
              <textarea
                value={devolucionDetalle}
                onChange={(event) => setDevolucionDetalle(event.target.value)}
                style={{ ...inputStyle, minHeight: 60, resize: 'vertical', fontFamily: 'inherit' }}
                placeholder="Explica brevemente qué pasó..."
              />
            </label>

            <div style={{ borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: 10, display: 'grid', gap: 8 }}>
              <span style={{ ...dateLabelStyle, color: '#ffcf7d' }}>Autorización de Gerente/Supervisor</span>
              <input
                type="text"
                placeholder="Usuario del Gerente/Supervisor"
                value={devolucionUser}
                onChange={(event) => setDevolucionUser(event.target.value)}
                style={inputStyle}
                autoComplete="off"
              />
              <input
                type="password"
                placeholder="Contraseña"
                value={devolucionPass}
                onChange={(event) => setDevolucionPass(event.target.value)}
                style={inputStyle}
                autoComplete="off"
              />
            </div>

            {devolucionError ? <div style={feedbackStyle('error')}>{devolucionError}</div> : null}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 4 }}>
              <button
                type="button"
                onClick={() => setDevolucionOpen(false)}
                style={secondaryButtonStyle}
                disabled={devolucionSaving}
              >
                Cancelar
              </button>
              <button type="submit" style={devolucionButtonStyle} disabled={devolucionSaving}>
                {devolucionSaving ? 'Procesando...' : 'Confirmar devolución'}
              </button>
            </div>
          </form>
        </div>
      ) : null}

      <ConfirmModal
        open={Boolean(confirmCambioMetodo)}
        title="¿Cambiar la cuenta de esta nota?"
        message={confirmCambioMetodo?.message || ''}
        confirmLabel="Sí, cambiar cuenta"
        cancelLabel="Cancelar"
        busy={savingAbono}
        onConfirm={handleConfirmarCambioMetodo}
        onCancel={() => setConfirmCambioMetodo(null)}
      />
    </section>
  );
}

const containerStyle = (isMobile, embedded) => ({
  display: 'grid',
  gap: 16,
  padding: embedded ? 0 : (isMobile ? 4 : 8),
});

const embeddedHeaderStyle = {
  color: '#ffb0b0',
  fontWeight: 800,
  fontSize: 13,
  textTransform: 'uppercase',
  letterSpacing: '0.1em',
};

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

const buscadorFormStyle = (isMobile) => ({
  display: 'flex',
  flexDirection: isMobile ? 'column' : 'row',
  alignItems: isMobile ? 'stretch' : 'flex-end',
  flexWrap: 'wrap',
  gap: 8,
});

const dateFieldStyle = {
  display: 'grid',
  gap: 4,
  minWidth: 0,
};

const dateLabelStyle = {
  fontSize: 11,
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  color: '#d2c4c4',
};

const inputStyle = {
  boxSizing: 'border-box',
  width: '100%',
  minWidth: 0,
  maxWidth: '100%',
  borderRadius: 12,
  border: '1px solid rgba(255, 255, 255, 0.14)',
  background: '#161010',
  padding: '9px 10px',
  color: '#fff4f4',
  fontSize: 13,
};

const secondaryButtonStyle = {
  border: '1px solid rgba(255, 173, 173, 0.35)',
  borderRadius: 12,
  padding: '9px 14px',
  background: 'rgba(255, 255, 255, 0.02)',
  color: '#ffe0e0',
  fontWeight: 600,
  cursor: 'pointer',
};

const emptyStateStyle = {
  minHeight: 80,
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

const layoutStyle = (isMobile) => ({
  display: 'grid',
  gridTemplateColumns: isMobile ? '1fr' : 'minmax(280px, 380px) 1fr',
  gap: 16,
  alignItems: 'start',
});

const listColumnStyle = {
  display: 'grid',
  gap: 10,
  alignContent: 'start',
};

const listStyle = {
  display: 'grid',
  gap: 10,
};

const paginacionBarStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 8,
  flexWrap: 'wrap',
  padding: '8px 2px',
};

const paginacionBotonStyle = (disabled) => ({
  border: '1px solid rgba(255, 173, 173, 0.35)',
  borderRadius: 12,
  padding: '7px 12px',
  background: disabled ? 'rgba(255, 255, 255, 0.02)' : 'rgba(255, 255, 255, 0.05)',
  color: disabled ? '#8a7a7a' : '#ffe0e0',
  fontWeight: 600,
  fontSize: 13,
  cursor: disabled ? 'not-allowed' : 'pointer',
  opacity: disabled ? 0.6 : 1,
});

const paginacionInfoStyle = {
  color: '#c8bbbb',
  fontSize: 12.5,
  fontWeight: 600,
};

const notaRowStyle = (selected) => ({
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 12,
  flexWrap: 'wrap',
  padding: '14px 16px',
  borderRadius: 16,
  border: selected ? '1px solid rgba(255, 130, 130, 0.6)' : '1px solid rgba(255, 255, 255, 0.1)',
  background: selected ? 'rgba(255, 90, 90, 0.12)' : 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)',
});

const rowActionsStyle = {
  display: 'flex',
  flexDirection: 'column',
  gap: 6,
};

const estadoBadgeStyle = (estado) => ({
  padding: '3px 10px',
  borderRadius: 999,
  fontSize: 11,
  fontWeight: 800,
  textTransform: 'uppercase',
  height: 'fit-content',
  background: estado === 'pagada' ? 'rgba(82, 206, 123, 0.16)' : 'rgba(255, 200, 120, 0.16)',
  color: estado === 'pagada' ? '#9fe3b0' : '#ffcf7d',
});

const detailPanelStyle = {
  display: 'grid',
  gap: 12,
  padding: '18px 18px',
  borderRadius: 20,
  background: 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)',
  border: '1px solid rgba(255, 255, 255, 0.1)',
  boxShadow: '0 12px 28px rgba(0,0,0,0.24)',
  minHeight: 200,
  maxHeight: 'calc(100vh - 24px)',
  overflowY: 'auto',
  boxSizing: 'border-box',
};

// El shell general de la app (WelcomeScreen) tiene overflow:hidden en su
// contenedor raíz, lo que rompe `position: sticky` nativo (el navegador lo
// calcula contra ese ancestro, que nunca hace scroll, en vez de contra la
// ventana). Se reimplementa "seguir el scroll" a mano: se mide la posición
// del placeholder y, cuando su borde superior cruza DETAIL_STICKY_TOP, el
// panel pasa a `position: fixed` clavado en ese punto — así no hay que subir
// hasta arriba para abonar una nota seleccionada más abajo en la lista.
const DETAIL_STICKY_TOP = 12;

const lineaRowStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  fontSize: 13,
  color: '#e8dede',
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

const fiadoRecalculadoStyle = {
  padding: '10px 12px',
  borderRadius: 12,
  border: '1px solid rgba(255, 200, 120, 0.3)',
  background: 'rgba(255, 200, 120, 0.08)',
  color: '#ffd8a3',
  fontSize: 12.5,
  lineHeight: 1.5,
};

const abonoFormStyle = (isMobile) => ({
  display: 'grid',
  gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr auto',
  gap: 8,
  paddingTop: 10,
  borderTop: '1px solid rgba(255, 255, 255, 0.08)',
});

const selectStyle = {
  ...inputStyle,
  appearance: 'auto',
  colorScheme: 'dark',
  cursor: 'pointer',
};

const primaryButtonStyle = {
  border: 'none',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'linear-gradient(90deg, #1f7a3f 0%, #34d399 100%)',
  color: '#04140a',
  fontWeight: 800,
  cursor: 'pointer',
};

const backdropStyle = {
  position: 'fixed',
  inset: 0,
  background: 'rgba(0, 0, 0, 0.6)',
  display: 'grid',
  placeItems: 'center',
  zIndex: 1000,
  padding: 16,
};

const devolucionCardStyle = {
  width: '100%',
  maxWidth: 420,
  display: 'grid',
  gap: 10,
  borderRadius: 20,
  border: '1px solid rgba(255, 145, 145, 0.3)',
  background: 'linear-gradient(180deg, rgba(28, 12, 12, 0.98) 0%, rgba(10, 8, 8, 0.99) 100%)',
  padding: '22px 22px 18px',
  boxShadow: '0 20px 50px rgba(0, 0, 0, 0.45)',
  maxHeight: 'calc(100vh - 32px)',
  overflowY: 'auto',
  overflowX: 'hidden',
  boxSizing: 'border-box',
};

const devolucionButtonStyle = {
  border: '1px solid rgba(255, 126, 126, 0.4)',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'rgba(145, 33, 33, 0.35)',
  color: '#ffd3d3',
  fontWeight: 800,
  cursor: 'pointer',
};

export default NotasEntregaHistorialPage;

import { useCallback, useEffect, useRef, useState } from 'react';
import useConfirmacionesFecha, { postConAdvertencias } from '../hooks/useConfirmacionesFecha';
import useExchangeRate from '../hooks/useExchangeRate';
import { formatBs, formatBsRaw } from '../utils/currency';
import { consumirAperturaCuentasPorPagarPagadas } from '../utils/fechaContabilidad';
import { formatearFecha, hoyIso } from '../utils/fechas';
import AnularCompraModal from './AnularCompraModal';
import BotonDescargarPdf from './BotonDescargarPdf';
import ReporteNotasCreditoCompra from './ReporteNotasCreditoCompra';
import { RangoFechas } from './FiltroFechas';
import MoneyInput from './MoneyInput';

// `bsPreciso`, cuando viene, es el total_bs que ya calculó el backend (para
// una compra con total_bs_factura, es el monto EXACTO que el analista
// escribió — ver _serialize_compra) en vez de recalcular amount*tasa aquí,
// que perdía bolívares por el redondeo de `amount` a 2 decimales.
function formatUsdBs(amount, tasa, bsPreciso) {
  const usd = `$${Number(amount).toFixed(2)}`;
  const bs = bsPreciso != null ? formatBsRaw(bsPreciso) : formatBs(amount, tasa);
  return bs ? `${usd} (${bs})` : usd;
}

// Para el saldo pendiente de un gasto: saldo_pendiente_bs viene precalculado
// desde el backend con la precision completa de monto (ver _serialize_gasto),
// asi que coincide con el total en bs que muestra el reporte de gastos — a
// diferencia de convertir aqui saldo_pendiente (redondeado a 2 decimales),
// que perdia centimos y mostraba un bs distinto para la misma deuda.
function formatSaldoUsdBs(amount, tasa, saldoBsPreciso) {
  const usd = `$${Number(amount).toFixed(2)}`;
  const bs = saldoBsPreciso != null ? formatBsRaw(saldoBsPreciso) : formatBs(amount, tasa);
  return bs ? `${usd} (${bs})` : usd;
}

function todayIso() {
  const now = new Date();
  const offset = now.getTimezoneOffset();
  const local = new Date(now.getTime() - offset * 60000);
  return local.toISOString().slice(0, 10);
}

function startOfMonthIso() {
  const today = todayIso();
  return `${today.slice(0, 7)}-01`;
}

const FILAS_POR_PAGINA = 20;

function coincideBusqueda(compra, busqueda) {
  if (!busqueda) return true;
  const texto = busqueda.trim().toLowerCase();
  if (!texto) return true;
  const campos = [
    String(compra.id),
    compra.proveedor_nombre,
    compra.categoria_nombre,
    compra.descripcion,
    compra.numero_factura_proveedor,
    compra.numero_comprobante,
  ];
  return campos.some((campo) => (campo || '').toLowerCase().includes(texto));
}

function coincideTipo(compra, filtroTipo) {
  if (filtroTipo === 'todos') return true;
  return compra.tipo === filtroTipo;
}

function CuentasPorPagarPage({ isMobile, onBack, onVerComprobante }) {
  const tasaCambio = useExchangeRate();
  // 'pendientes' es el comportamiento de siempre (lotes/gastos sin saldar);
  // 'pagadas' es el historial nuevo de facturas ya saldadas, filtrable por
  // fecha — "las facturas que pagué". Si se llega desde el chip "Compras a
  // proveedores" del estado de resultados (ver setAbrirCuentasPorPagarEnPagadas),
  // arranca directo en esa pestaña con el mismo rango que se estaba viendo, para
  // poder rastrear de dónde sale ese monto.
  const [aperturaInicial] = useState(() => consumirAperturaCuentasPorPagarPagadas());
  const [vista, setVista] = useState(aperturaInicial ? 'pagadas' : 'pendientes');
  const [historialDesde, setHistorialDesde] = useState(aperturaInicial ? aperturaInicial.desde : startOfMonthIso());
  const [historialHasta, setHistorialHasta] = useState(aperturaInicial ? aperturaInicial.hasta : todayIso());
  const [compras, setCompras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [metodosPago, setMetodosPago] = useState([]);
  const [selectedCompraId, setSelectedCompraId] = useState(null);
  const [selectedTipo, setSelectedTipo] = useState(null);
  const [compraDetalle, setCompraDetalle] = useState(null);
  const [loadingDetalle, setLoadingDetalle] = useState(false);
  const [montoAbono, setMontoAbono] = useState('');
  const [monedaAbono, setMonedaAbono] = useState('USD');
  // Tasa propia del abono (vacia = la de la factura/BCV). Ver tasaPorDefecto.
  const [tasaAbono, setTasaAbono] = useState('');
  const [metodoAbono, setMetodoAbono] = useState('');
  // Nº de la transferencia / pago móvil con el que se pagó: se guarda en VGAbonoCompra.referencia
  // (y VGAbonoGasto.referencia), que es lo que la conciliación bancaria cruza con el extracto.
  const [referenciaAbono, setReferenciaAbono] = useState('');
  // Dia en que de verdad se pago (hoy por defecto); el sistema guarda aparte el momento exacto del registro.
  const [fechaAbono, setFechaAbono] = useState(hoyIso());
  // La fecha del pago es hoy salvo que se pida cambiarla: asi el formulario no muestra un campo que casi nunca se toca.
  const [fechaEditable, setFechaEditable] = useState(false);
  // Pestana abierta del detalle de una cuenta: abonos, productos o notas de credito.
  const [detalleTab, setDetalleTab] = useState('abonos');
  const [savingAbono, setSavingAbono] = useState(false);
  const { confirmarFecha, confirmarAdvertencias, modales } = useConfirmacionesFecha();
  const [feedback, setFeedback] = useState('');
  const [feedbackType, setFeedbackType] = useState('success');
  const [ultimoAbonoId, setUltimoAbonoId] = useState(null);
  // Nota de credito del proveedor (rebaja la deuda de una factura de compra cargada con monto equivocado).
  const [ncAbierta, setNcAbierta] = useState(false);
  const [ncMonto, setNcMonto] = useState('');
  const [ncMoneda, setNcMoneda] = useState('USD');
  const [ncMotivo, setNcMotivo] = useState('');
  const [ncNumero, setNcNumero] = useState('');
  const [savingNc, setSavingNc] = useState(false);
  // Factura de compra que se esta anulando (el stock vuelve a como estaba): abre el modal con las advertencias.
  const [anulandoCompra, setAnulandoCompra] = useState(null);
  const [busqueda, setBusqueda] = useState('');
  const [filtroTipo, setFiltroTipo] = useState('todos');
  const [pagina, setPagina] = useState(1);
  const detailPanelRef = useRef(null);
  // El diseno de dos columnas depende del ancho que de verdad tiene el contenido (con la barra lateral abierta
  // una pantalla ancha puede quedar estrecha), no solo de si es un celular.
  const raizRef = useRef(null);
  const [anchoContenido, setAnchoContenido] = useState(1200);
  useEffect(() => {
    const elemento = raizRef.current;
    if (!elemento || typeof ResizeObserver === 'undefined') return undefined;
    setAnchoContenido(elemento.getBoundingClientRect().width);
    const observador = new ResizeObserver(([entrada]) => setAnchoContenido(entrada.contentRect.width));
    observador.observe(elemento);
    return () => observador.disconnect();
  }, []);
  // Reporte PDF: tiene sus propios filtros (no depende de la pestana ni de la busqueda de la pantalla).
  const [reporteAbierto, setReporteAbierto] = useState(false);
  const [reporteTipo, setReporteTipo] = useState('todos');
  const [reporteEstado, setReporteEstado] = useState('pendientes');
  const [reporteConFechas, setReporteConFechas] = useState(false);
  const [reporteDesde, setReporteDesde] = useState(startOfMonthIso());
  const [reporteHasta, setReporteHasta] = useState(todayIso());
  const [reporteError, setReporteError] = useState('');

  const fetchCompras = useCallback(async () => {
    if (vista === 'notas_credito') {
      setLoading(false);
      return;
    }
    try {
      const query = vista === 'pagadas'
        ? `?estado=pagadas&desde=${historialDesde}&hasta=${historialHasta}`
        : '';
      const response = await fetch(`/api/cuentas-por-pagar/${query}`, { credentials: 'include', cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setError(data.message || 'No se pudieron cargar las cuentas por pagar.');
        return;
      }
      setCompras(Array.isArray(data.compras) ? data.compras : []);
      setError('');
    } catch (requestError) {
      setError('Error de red al cargar las cuentas por pagar.');
    } finally {
      setLoading(false);
    }
  }, [vista, historialDesde, historialHasta]);

  useEffect(() => {
    setLoading(true);
    setSelectedCompraId(null);
    setCompraDetalle(null);
    fetchCompras();
  }, [fetchCompras]);

  const alternarReporte = () => {
    if (!reporteAbierto) {
      // Al abrirlo arranca con lo que se esta viendo (la pestana, el tipo y el rango de "Facturas pagadas").
      setReporteEstado(vista === 'pagadas' ? 'pagadas' : 'pendientes');
      setReporteTipo(filtroTipo);
      if (vista === 'pagadas') {
        setReporteConFechas(true);
        setReporteDesde(historialDesde);
        setReporteHasta(historialHasta);
      }
      setReporteError('');
    }
    setReporteAbierto((abierto) => !abierto);
  };

  const cambiarVista = (nuevaVista) => {
    setVista(nuevaVista);
    setBusqueda('');
    setFiltroTipo('todos');
    setPagina(1);
    setFeedback('');
  };

  useEffect(() => {
    setPagina(1);
  }, [busqueda, filtroTipo, vista, historialDesde, historialHasta]);

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

  const fetchCompraDetalle = useCallback(async (compraId, tipo) => {
    setLoadingDetalle(true);
    const url = tipo === 'gasto' ? `/api/admin/gastos/${compraId}/` : `/api/admin/compras/${compraId}/`;
    try {
      const response = await fetch(url, { credentials: 'include', cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setFeedbackType('error');
        setFeedback(data.message || 'No se pudo cargar el detalle.');
        return;
      }
      setCompraDetalle({ ...(tipo === 'gasto' ? data.gasto : data.compra), tipo });
    } catch (requestError) {
      setFeedbackType('error');
      setFeedback('Error de red al cargar el detalle.');
    } finally {
      setLoadingDetalle(false);
    }
  }, []);

  const handleSelectCompra = (compra) => {
    setNcAbierta(false);
    setNcMonto('');
    setNcMotivo('');
    setNcNumero('');
    setFeedback('');
    setMontoAbono('');
    setMonedaAbono('USD');
    setTasaAbono('');
    setReferenciaAbono('');
    setFechaAbono(hoyIso());
    setFechaEditable(false);
    setDetalleTab('abonos');
    setSelectedCompraId(compra.id);
    setSelectedTipo(compra.tipo);
    fetchCompraDetalle(compra.id, compra.tipo);
    // Al elegir una fila mas abajo en una lista larga, el detalle se ve sin
    // tener que volver a subir con la mano hasta el principio de la pagina.
    if (detailPanelRef.current) {
      detailPanelRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  // La tasa con la que se paga por defecto (la misma que usa el servidor si no se escribe
  // ninguna): en dolares o con la deuda en dolares, la del BCV de hoy; en bolivares, la de la
  // factura (congelada al cargarla). Los proveedores cobran a tasas distintas; quien paga puede
  // escribir la suya para que los Bs registrados sean los que salieron del banco.
  const tasaPorDefecto = (monedaAbono === 'USD' || compraDetalle?.moneda_origen === 'USD')
    ? Number(tasaCambio)
    : Number(compraDetalle?.tasa_cambio_referencia ?? tasaCambio);
  const origenTasaPorDefecto = tasaPorDefecto === Number(tasaCambio) ? 'BCV de hoy' : 'de la factura';
  const tasaAbonoNum = Number(tasaAbono);
  const tasaAbonoManual = tasaAbono !== '' && Number.isFinite(tasaAbonoNum) && tasaAbonoNum > 0
    && Math.abs(tasaAbonoNum - tasaPorDefecto) > 0.00005;
  const tasaEfectiva = tasaAbonoManual ? tasaAbonoNum : tasaPorDefecto;
  const montoAbonoNum = Number(montoAbono);
  const vistaPreviaAbono = (() => {
    if (!Number.isFinite(montoAbonoNum) || montoAbonoNum <= 0 || !Number.isFinite(tasaEfectiva) || tasaEfectiva <= 0) {
      return '';
    }
    return monedaAbono === 'VES'
      ? `Se descontarán $${(montoAbonoNum / tasaEfectiva).toFixed(2)} de la deuda (${formatBsRaw(montoAbonoNum)} ÷ ${tasaEfectiva})`
      : `Se registrarán ${formatBsRaw(montoAbonoNum * tasaEfectiva)} (${'$'}${montoAbonoNum.toFixed(2)} × ${tasaEfectiva})`;
  })();

  const handleRegistrarAbono = async (event) => {
    event.preventDefault();
    if (!selectedCompraId) {
      return;
    }
    const metodoPagoId = metodoAbono || (metodosPago[0] && metodosPago[0].id);
    if (!metodoPagoId) {
      setFeedbackType('error');
      setFeedback('No hay metodos de pago activos configurados.');
      return;
    }

    // Si la fecha del pago no es hoy (ej. se les olvido cargarlo ayer) se pide confirmar que fue ese dia.
    if (!(await confirmarFecha(fechaAbono, 'pago'))) {
      return;
    }

    setSavingAbono(true);
    setFeedback('');
    setUltimoAbonoId(null);
    const url = selectedTipo === 'gasto'
      ? `/api/admin/gastos/${selectedCompraId}/abonos/`
      : `/api/admin/compras/${selectedCompraId}/abonos/`;
    try {
      const resultado = await postConAdvertencias(url, {
        ...(monedaAbono === 'VES' ? { monto_bs: montoAbono } : { monto: montoAbono }),
        // Solo si la tasa se cambio a mano: asi un abono normal sigue usando la tasa habitual.
        ...(tasaAbonoManual ? { tasa_cambio: tasaAbono } : {}),
        metodo_pago_id: metodoPagoId,
        referencia: referenciaAbono.trim(),
        fecha_abono: fechaAbono,
      }, confirmarAdvertencias);
      if (resultado.cancelado) {
        return;
      }
      const { response, data } = resultado;
      if (!response.ok || !data.ok) {
        setFeedbackType('error');
        setFeedback(data.message || 'No se pudo registrar el abono.');
        return;
      }
      const cuentaActualizada = selectedTipo === 'gasto' ? data.gasto : data.compra;
      setFeedbackType('success');
      setFeedback(`Abono de ${formatUsdBs(data.abono.monto, data.abono.tasa_cambio_referencia ?? tasaCambio)} registrado. Saldo pendiente: ${formatSaldoUsdBs(cuentaActualizada.saldo_pendiente, cuentaActualizada.tasa_cambio_referencia ?? tasaCambio, cuentaActualizada.saldo_pendiente_bs)}.`);
      setCompraDetalle({ ...cuentaActualizada, tipo: selectedTipo });
      setUltimoAbonoId(data.abono.id);
      setMontoAbono('');
      setTasaAbono('');
      setReferenciaAbono('');
      setFechaAbono(hoyIso());
      setFechaEditable(false);
      await fetchCompras();
    } catch (requestError) {
      setFeedbackType('error');
      setFeedback('Error de red al registrar el abono.');
    } finally {
      setSavingAbono(false);
    }
  };

  const abrirNotaCredito = () => {
    setNcMoneda(compraDetalle?.moneda_origen === 'VES' ? 'VES' : 'USD');
    setNcMonto('');
    setNcMotivo('');
    setNcNumero('');
    setNcAbierta(true);
  };

  const handleRegistrarNotaCredito = async (event) => {
    event.preventDefault();
    if (!selectedCompraId || selectedTipo !== 'compra') {
      return;
    }
    if (!ncMotivo.trim()) {
      setFeedbackType('error');
      setFeedback('Escribe el motivo de la nota de crédito.');
      return;
    }
    setSavingNc(true);
    setFeedback('');
    try {
      const response = await fetch(`/api/admin/compras/${selectedCompraId}/notas-credito/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          ...(ncMoneda === 'VES' ? { monto_bs: ncMonto } : { monto: ncMonto }),
          motivo: ncMotivo,
          numero_documento_proveedor: ncNumero,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setFeedbackType('error');
        setFeedback(data.message || 'No se pudo registrar la nota de crédito.');
        return;
      }
      setFeedbackType('success');
      setFeedback(data.message);
      setCompraDetalle({ ...data.compra, tipo: 'compra' });
      setNcAbierta(false);
      await fetchCompras();
    } catch (requestError) {
      setFeedbackType('error');
      setFeedback('Error de red al registrar la nota de crédito.');
    } finally {
      setSavingNc(false);
    }
  };

  const handleAnularNotaCredito = async (nota) => {
    const motivo = window.prompt(`Motivo para anular la nota de crédito ${nota.codigo} (la deuda vuelve a subir $${Number(nota.monto).toFixed(2)}):`);
    if (!motivo || !motivo.trim()) {
      return;
    }
    setSavingNc(true);
    setFeedback('');
    try {
      const response = await fetch(`/api/admin/compras/notas-credito/${nota.id}/anular/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ motivo }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setFeedbackType('error');
        setFeedback(data.message || 'No se pudo anular la nota de crédito.');
        return;
      }
      setFeedbackType('success');
      setFeedback(data.message);
      setCompraDetalle({ ...data.compra, tipo: 'compra' });
      await fetchCompras();
    } catch (requestError) {
      setFeedbackType('error');
      setFeedback('Error de red al anular la nota de crédito.');
    } finally {
      setSavingNc(false);
    }
  };

  const comprasFiltradas = compras.filter(
    (compra) => coincideTipo(compra, filtroTipo) && coincideBusqueda(compra, busqueda),
  );
  const totalPaginas = Math.max(1, Math.ceil(comprasFiltradas.length / FILAS_POR_PAGINA));
  const paginaActual = Math.min(pagina, totalPaginas);
  const comprasPagina = comprasFiltradas.slice(
    (paginaActual - 1) * FILAS_POR_PAGINA,
    paginaActual * FILAS_POR_PAGINA,
  );

  // Lo que se debe (o lo que se pagó, en el historial) en la lista que se está viendo: es la cifra que abre la página.
  const enPagadas = vista === 'pagadas';
  const montoDeCuenta = (cuenta) => Number(enPagadas ? montoTotalDe(cuenta) : cuenta.saldo_pendiente) || 0;
  const bsDeCuenta = (cuenta) => {
    if (enPagadas) {
      return cuenta.total_bs != null ? Number(cuenta.total_bs) : montoTotalDe(cuenta) * Number(cuenta.tasa_cambio_referencia ?? tasaCambio);
    }
    return cuenta.saldo_pendiente_bs != null
      ? Number(cuenta.saldo_pendiente_bs)
      : Number(cuenta.saldo_pendiente) * Number(cuenta.tasa_cambio_referencia ?? tasaCambio);
  };
  const resumenUsd = comprasFiltradas.reduce((suma, cuenta) => suma + montoDeCuenta(cuenta), 0);
  const resumenBs = comprasFiltradas.reduce((suma, cuenta) => suma + (bsDeCuenta(cuenta) || 0), 0);
  const resumenLotes = comprasFiltradas.filter((cuenta) => cuenta.tipo !== 'gasto').length;
  const resumenGastos = comprasFiltradas.length - resumenLotes;

  const metodoElegido = metodosPago.find((metodo) => metodo.id === (metodoAbono || (metodosPago[0] && metodosPago[0].id)));
  const pideReferencia = Boolean(metodoElegido) && !metodoElegido.es_efectivo;
  const fechaEsHoy = fechaAbono === hoyIso();

  const compacto = isMobile || anchoContenido < 860;
  const cuentaAbierta = Boolean(selectedCompraId);
  const mostrarLista = !(compacto && cuentaAbierta);

  const cerrarDetalle = () => {
    setSelectedCompraId(null);
    setSelectedTipo(null);
    setCompraDetalle(null);
    setFeedback('');
  };

  const detalle = compraDetalle;
  const detalleSaldada = detalle ? esEstadoSaldado(detalle.estado_pago) : false;
  const detalleTotal = detalle ? montoTotalDe(detalle) : 0;
  const detalleSaldo = detalle ? Number(detalle.saldo_pendiente) || 0 : 0;
  const detallePagado = Math.max(0, detalleTotal - detalleSaldo);
  const detalleTasa = detalle ? (detalle.tasa_cambio_referencia ?? tasaCambio) : tasaCambio;
  const detalleEsLote = detalle ? detalle.tipo !== 'gasto' : false;
  const notasCredito = detalleEsLote ? (detalle?.notas_credito || []) : [];
  const pestanasDetalle = detalle ? [
    { id: 'abonos', label: `Abonos${detalle.abonos.length ? ` (${detalle.abonos.length})` : ''}` },
    ...(detalleEsLote ? [
      { id: 'productos', label: 'Productos' },
      { id: 'notas', label: `Notas de crédito${notasCredito.length ? ` (${notasCredito.length})` : ''}` },
    ] : []),
  ] : [];

  // En vivo, con la tasa que este activa (la propia si se escribio una): cuanto debe la cuenta en Bs y cuanto quedaria
  // despues del abono que se esta escribiendo.
  const tasaValida = Number.isFinite(tasaEfectiva) && tasaEfectiva > 0;
  const saldoEnBsConTasa = tasaValida ? detalleSaldo * tasaEfectiva : null;
  const usdDelAbono = montoAbonoNum > 0 && tasaValida ? (monedaAbono === 'VES' ? montoAbonoNum / tasaEfectiva : montoAbonoNum) : 0;
  const quedaUsd = Math.max(0, detalleSaldo - usdDelAbono);
  const abonoPasaDelSaldo = usdDelAbono > detalleSaldo + 0.01;

  // "Pagar todo" llena el monto en la moneda que esta elegida: en dolares, el saldo; en bolivares, el saldo en Bs
  // (con la tasa propia si se escribio una, o con la tasa normal de la cuenta). Asi el monto saldado coincide
  // con lo que muestra "Debes".
  const pagarTodo = () => {
    if (!detalle) return;
    if (monedaAbono === 'VES') {
      const bs = tasaAbonoManual
        ? detalleSaldo * tasaAbonoNum
        : (detalle.saldo_pendiente_bs != null ? Number(detalle.saldo_pendiente_bs) : detalleSaldo * tasaEfectiva);
      if (!Number.isFinite(bs)) return;
      setMontoAbono(String(Number(bs.toFixed(2))));
      return;
    }
    setMontoAbono(String(Number(detalleSaldo.toFixed(6))));
  };

  return (
    <section ref={raizRef} style={containerStyle(isMobile)}>
      <div style={headerWrapStyle}>
        <h2 style={titleStyle(isMobile)}>Cuentas por pagar</h2>
        <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
          <button type="button" onClick={alternarReporte} style={ghostButtonStyle(reporteAbierto)} aria-expanded={reporteAbierto}>
            Descargar PDF
          </button>
          <button type="button" onClick={onBack} style={ghostButtonStyle(false)}>Volver</button>
        </div>
      </div>

      <div style={segmentedStyle} role="tablist" aria-label="Vista">
        {[['pendientes', 'Pendientes'], ['pagadas', 'Pagadas'], ['notas_credito', 'Notas de crédito']].map(([id, etiqueta]) => (
          <button key={id} type="button" role="tab" aria-selected={vista === id} onClick={() => cambiarVista(id)} style={segmentStyle(vista === id)}>
            {etiqueta}
          </button>
        ))}
      </div>

      {reporteAbierto ? (
        <section style={reportePanelStyle}>
          <div style={reporteFiltrosStyle(isMobile)}>
            <label style={reporteLabelStyle}>
              Incluir
              <select value={reporteTipo} onChange={(event) => setReporteTipo(event.target.value)} style={selectStyle} className="admin-dark-select">
                <option value="todos">Lotes y gastos</option>
                <option value="compra">Solo lotes</option>
                <option value="gasto">Solo gastos</option>
              </select>
            </label>
            <label style={reporteLabelStyle}>
              Estado
              <select value={reporteEstado} onChange={(event) => setReporteEstado(event.target.value)} style={selectStyle} className="admin-dark-select">
                <option value="pendientes">Pendientes y abonadas</option>
                <option value="pagadas">Pagadas</option>
                <option value="todos">Todas</option>
              </select>
            </label>
          </div>
          <label style={reporteCheckStyle}>
            <input type="checkbox" checked={reporteConFechas} onChange={(event) => setReporteConFechas(event.target.checked)} />
            Limitar por fechas
          </label>
          {reporteConFechas ? (
            <>
              <RangoFechas
                desde={reporteDesde}
                hasta={reporteHasta}
                onChange={(rango) => { setReporteDesde(rango.desde); setReporteHasta(rango.hasta); }}
              />
              <div style={mutedStyle}>Las pendientes usan la fecha de la factura o del gasto; las pagadas, la fecha de pago.</div>
            </>
          ) : null}
          {reporteError ? <div style={errorStyle}>{reporteError}</div> : null}
          <div>
            <BotonDescargarPdf
              url="/api/admin/reportes/cuentas-por-pagar-pdf/"
              params={{
                tipo: reporteTipo,
                estado: reporteEstado,
                desde: reporteConFechas ? reporteDesde : '',
                hasta: reporteConFechas ? reporteHasta : '',
              }}
              onError={setReporteError}
            >
              Descargar PDF
            </BotonDescargarPdf>
          </div>
        </section>
      ) : null}

      {vista === 'notas_credito' ? <ReporteNotasCreditoCompra isMobile={isMobile} /> : null}

      {vista !== 'notas_credito' ? (
        <>
          {!loading && !error && compras.length > 0 && mostrarLista ? (
            <div style={resumenStyle(isMobile)}>
              <div>
                <div style={resumenEtiquetaStyle}>{enPagadas ? 'Pagaste en este período' : 'Debes'}</div>
                <div style={resumenMontoStyle(isMobile, enPagadas)}>{fmtUsd(resumenUsd)}</div>
                {resumenBs > 0 ? <div style={resumenBsStyle}>{formatBsRaw(resumenBs)}</div> : null}
              </div>
              <div style={resumenConteoStyle}>
                {comprasFiltradas.length} {comprasFiltradas.length === 1 ? 'cuenta' : 'cuentas'}
                {resumenLotes > 0 && resumenGastos > 0 ? (
                  <div style={mutedStyle}>{resumenLotes} {resumenLotes === 1 ? 'lote' : 'lotes'}, {resumenGastos} {resumenGastos === 1 ? 'gasto' : 'gastos'}</div>
                ) : null}
              </div>
            </div>
          ) : null}

          {enPagadas && mostrarLista ? (
            <RangoFechas
              desde={historialDesde}
              hasta={historialHasta}
              onChange={(rango) => { setHistorialDesde(rango.desde); setHistorialHasta(rango.hasta); }}
            />
          ) : null}

          {mostrarLista ? (
            <div style={filtrosBusquedaRowStyle(isMobile)}>
              <input
                type="search"
                value={busqueda}
                onChange={(event) => setBusqueda(event.target.value)}
                placeholder="Buscar proveedor, factura o categoría"
                aria-label="Buscar cuenta"
                style={busquedaInputStyle}
              />
              <div style={chipsStyle} role="group" aria-label="Tipo de cuenta">
                {[['todos', 'Todos'], ['compra', 'Lotes'], ['gasto', 'Gastos']].map(([id, etiqueta]) => (
                  <button key={id} type="button" aria-pressed={filtroTipo === id} onClick={() => setFiltroTipo(id)} style={chipStyle(filtroTipo === id)}>
                    {etiqueta}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {feedback ? (
            <div style={feedbackStyle(feedbackType)} role="status">
              <span>{feedback}</span>
              {ultimoAbonoId && onVerComprobante ? (
                <button type="button" onClick={() => onVerComprobante(selectedTipo, selectedCompraId, ultimoAbonoId)} style={comprobanteLinkStyle}>
                  Ver comprobante
                </button>
              ) : null}
            </div>
          ) : null}

          {loading ? <div style={emptyStateStyle}>Cargando…</div> : null}
          {!loading && error ? <div style={errorStyle}>{error}</div> : null}
          {!loading && !error && compras.length === 0 ? (
            <div style={emptyStateStyle}>
              {enPagadas ? 'No se pagó ninguna cuenta en este período.' : 'No debes nada por ahora.'}
            </div>
          ) : null}
          {!loading && !error && compras.length > 0 && comprasFiltradas.length === 0 ? (
            <div style={emptyStateStyle}>
              {busqueda ? `Nada coincide con "${busqueda}".` : `No hay ${filtroTipo === 'compra' ? 'lotes' : 'gastos'} en esta vista.`}
            </div>
          ) : null}

          {!loading && !error && comprasFiltradas.length > 0 ? (
            <div style={layoutStyle(compacto)}>
              {mostrarLista ? (
                <div style={listColumnStyle}>
                  <div style={listPanelStyle}>
                    {comprasPagina.map((compra) => {
                      const seleccionada = selectedCompraId === compra.id && selectedTipo === compra.tipo;
                      const total = montoTotalDe(compra);
                      const saldo = Number(compra.saldo_pendiente) || 0;
                      const avance = total > 0 ? Math.min(1, Math.max(0, 1 - saldo / total)) : 0;
                      const abonada = !enPagadas && compra.estado_pago === 'abonada_parcial';
                      const tasaCuenta = compra.tasa_cambio_referencia ?? tasaCambio;
                      return (
                        <button
                          key={`${compra.tipo}-${compra.id}`}
                          type="button"
                          onClick={() => handleSelectCompra(compra)}
                          aria-pressed={seleccionada}
                          style={filaStyle(seleccionada, enPagadas ? 'pagada' : compra.estado_pago)}
                        >
                          <span style={{ display: 'grid', gap: 3, minWidth: 0, textAlign: 'left' }}>
                            <span style={filaTituloStyle}>
                              {compra.tipo === 'gasto' ? (compra.categoria_nombre || compra.descripcion) : compra.proveedor_nombre}
                            </span>
                            <span style={mutedStyle}>
                              {compra.tipo === 'gasto' ? 'Gasto' : 'Lote'} #{compra.id}
                              {compra.numero_factura_proveedor ? `, factura ${compra.numero_factura_proveedor}` : ''}
                            </span>
                            {abonada ? (
                              <span style={barraPistaStyle} aria-hidden="true">
                                <span style={{ ...barraRellenoStyle, width: `${Math.round(avance * 100)}%` }} />
                              </span>
                            ) : null}
                          </span>
                          <span style={{ display: 'grid', gap: 2, justifyItems: 'end', flexShrink: 0 }}>
                            <span style={filaMontoStyle(enPagadas)}>{fmtUsd(enPagadas ? total : saldo)}</span>
                            <span style={mutedStyle}>
                              {formatBsRaw(enPagadas
                                ? (compra.total_bs != null ? compra.total_bs : total * Number(tasaCuenta))
                                : (compra.saldo_pendiente_bs != null ? compra.saldo_pendiente_bs : saldo * Number(tasaCuenta)))}
                            </span>
                            {abonada ? <span style={etiquetaAbonadaStyle}>Abonada</span> : null}
                          </span>
                        </button>
                      );
                    })}
                  </div>

                  {totalPaginas > 1 ? (
                    <div style={paginacionStyle}>
                      <button type="button" onClick={() => setPagina((p) => Math.max(1, p - 1))} disabled={paginaActual <= 1} style={paginacionBotonStyle(paginaActual <= 1)}>
                        Anterior
                      </button>
                      <span style={paginacionTextoStyle}>{paginaActual} de {totalPaginas}</span>
                      <button type="button" onClick={() => setPagina((p) => Math.min(totalPaginas, p + 1))} disabled={paginaActual >= totalPaginas} style={paginacionBotonStyle(paginaActual >= totalPaginas)}>
                        Siguiente
                      </button>
                    </div>
                  ) : null}
                </div>
              ) : null}

              {!compacto || cuentaAbierta ? (
              <div ref={detailPanelRef} style={detailPanelStyle(isMobile)}>
                {compacto && cuentaAbierta ? (
                  <button type="button" onClick={cerrarDetalle} style={backLinkStyle}>← Cuentas</button>
                ) : null}

                {!cuentaAbierta ? (
                  <div style={detalleVacioStyle}>Elige una cuenta para ver sus abonos y registrar un pago.</div>
                ) : loadingDetalle || !detalle ? (
                  <div style={detalleVacioStyle}>Cargando…</div>
                ) : (
                  <>
                    <div style={detalleCabeceraStyle}>
                      <div style={{ minWidth: 0 }}>
                        <h3 style={detalleTituloStyle}>{detalleEsLote ? detalle.proveedor_nombre : (detalle.categoria_nombre || detalle.descripcion)}</h3>
                        <div style={metaFilaStyle}>
                          <span>{detalleEsLote ? 'Lote' : 'Gasto'} #{detalle.id}</span>
                          {detalle.numero_factura_proveedor ? <span>Factura {detalle.numero_factura_proveedor}</span> : null}
                          {detalle.numero_comprobante ? <span>Comprobante {detalle.numero_comprobante}</span> : null}
                          {!detalleEsLote && detalle.categoria_nombre && detalle.descripcion ? <span>{detalle.descripcion}</span> : null}
                          <span>Cargado el {new Date(detalle.fecha_creacion).toLocaleDateString('es-VE')}</span>
                        </div>
                      </div>
                      <span style={estadoChipStyle(detalle.estado_pago)}>{estadoLabel(detalle.estado_pago)}</span>
                    </div>

                    <div style={cifrasStyle}>
                      <div style={cifraStyle}>
                        <span style={mutedStyle}>Total</span>
                        <span style={cifraValorStyle}>{fmtUsd(detalleTotal)}</span>
                      </div>
                      <div style={cifraStyle}>
                        <span style={mutedStyle}>Pagado</span>
                        <span style={{ ...cifraValorStyle, color: 'var(--vg-f-9fe3b0)' }}>{fmtUsd(detallePagado)}</span>
                      </div>
                      <div style={cifraStyle}>
                        <span style={mutedStyle}>{detalleSaldada ? 'Saldada' : 'Debes'}</span>
                        <span style={cifraDebesStyle(detalleSaldada)}>{fmtUsd(detalleSaldo)}</span>
                        {tasaAbonoManual && saldoEnBsConTasa != null ? (
                          <span style={{ ...mutedStyle, color: 'var(--vg-f-ffcf7d)', fontWeight: 700 }}>
                            {formatBsRaw(saldoEnBsConTasa)} a tu tasa
                          </span>
                        ) : (
                          <span style={mutedStyle}>
                            {formatBsRaw(detalle.saldo_pendiente_bs != null ? detalle.saldo_pendiente_bs : detalleSaldo * Number(detalleTasa))}
                          </span>
                        )}
                      </div>
                    </div>
                    {detalleTotal > 0 ? (
                      <div style={barraPistaStyle} aria-hidden="true">
                        <span style={{ ...barraRellenoStyle, width: `${Math.round(Math.min(1, detallePagado / detalleTotal) * 100)}%` }} />
                      </div>
                    ) : null}

                    {!detalleSaldada ? (
                      <form onSubmit={handleRegistrarAbono} style={abonoFormStyle}>
                        <div style={formTituloStyle}>Registrar abono</div>

                        <div style={montoFilaStyle}>
                          <div style={monedaSegmentadoStyle} role="group" aria-label="Moneda del abono">
                            <button type="button" aria-pressed={monedaAbono === 'USD'} onClick={() => setMonedaAbono('USD')} style={monedaOpcionStyle(monedaAbono === 'USD')}>$</button>
                            <button type="button" aria-pressed={monedaAbono === 'VES'} onClick={() => setMonedaAbono('VES')} style={monedaOpcionStyle(monedaAbono === 'VES')}>Bs</button>
                          </div>
                          {/* Con separador de miles mientras se escribe (1,100.88), igual que los cobros;
                              el valor que se guarda y se envía es el número limpio. En $ admite hasta
                              6 decimales para que "Pagar todo" no pierda centavos. */}
                          <MoneyInput
                            maxDecimales={monedaAbono === 'VES' ? 2 : 6}
                            placeholder="Monto"
                            value={montoAbono}
                            onChange={setMontoAbono}
                            style={{ ...inputStyle, flex: 1, minWidth: 0, fontSize: 16, fontWeight: 700 }}
                            required
                          />
                          <button
                            type="button"
                            onClick={pagarTodo}
                            style={textButtonStyle}
                          >
                            Pagar todo
                          </button>
                        </div>
                        {vistaPreviaAbono ? (
                          <div style={{ display: 'grid', gap: 2 }}>
                            <div style={{ ...mutedStyle, color: tasaAbonoManual ? 'var(--vg-f-ffcf7d)' : 'var(--vg-f-9fe3b0)' }}>
                              {monedaAbono === 'VES'
                                ? `Descuenta $${(montoAbonoNum / tasaEfectiva).toFixed(2)} de la deuda`
                                : `Equivale a ${formatBsRaw(montoAbonoNum * tasaEfectiva)}`}
                              {tasaAbonoManual ? `, a tu tasa ${tasaAbonoNum}` : ''}
                            </div>
                            {abonoPasaDelSaldo ? (
                              <div style={avisoFechaStyle}>Es más de lo que debes.</div>
                            ) : (
                              <div style={mutedStyle}>
                                Después quedan {fmtUsd(quedaUsd)} ({formatBsRaw(quedaUsd * tasaEfectiva)})
                              </div>
                            )}
                          </div>
                        ) : null}

                        <div style={dosColumnasStyle(compacto)}>
                          <label style={campoStyle}>
                            <span style={campoEtiquetaStyle}>Método</span>
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
                          </label>
                          <div style={campoStyle}>
                            <span style={campoEtiquetaStyle}>Fecha del pago</span>
                            {fechaEsHoy && !fechaEditable ? (
                              <div style={fechaHoyStyle}>
                                <span>Hoy</span>
                                <button type="button" onClick={() => setFechaEditable(true)} style={textButtonStyle}>Cambiar</button>
                              </div>
                            ) : (
                              <div style={fechaHoyStyle}>
                                <input
                                  type="date"
                                  value={fechaAbono}
                                  max={hoyIso()}
                                  onChange={(event) => setFechaAbono(event.target.value || hoyIso())}
                                  style={{ ...inputStyle, flex: 1, minWidth: 0 }}
                                  aria-label="Fecha del pago"
                                  required
                                />
                                <button type="button" onClick={() => { setFechaAbono(hoyIso()); setFechaEditable(false); }} style={textButtonStyle}>Hoy</button>
                              </div>
                            )}
                          </div>
                        </div>
                        {!fechaEsHoy ? (
                          <div style={avisoFechaStyle}>Se guardará como pago del {formatearFecha(fechaAbono)}.</div>
                        ) : null}

                        {pideReferencia ? (
                          <label style={campoStyle}>
                            <span style={campoEtiquetaStyle}>Referencia</span>
                            <input
                              type="text"
                              maxLength={100}
                              placeholder="Nº de transferencia o pago móvil"
                              value={referenciaAbono}
                              onChange={(event) => setReferenciaAbono(event.target.value)}
                              style={inputStyle}
                            />
                          </label>
                        ) : null}

                        <details style={opcionesStyle}>
                          <summary style={opcionesResumenStyle}>Pagué a otra tasa</summary>
                          <div style={{ display: 'grid', gap: 6, paddingTop: 8 }}>
                            <MoneyInput
                              maxDecimales={4}
                              placeholder={Number.isFinite(tasaPorDefecto) && tasaPorDefecto > 0 ? `Por defecto ${tasaPorDefecto} (${origenTasaPorDefecto})` : 'Bs por $'}
                              value={tasaAbono}
                              onChange={setTasaAbono}
                              style={inputStyle}
                            />
                            {tasaAbonoManual && saldoEnBsConTasa != null ? (
                              <div style={tasaEnVivoStyle}>
                                Debes {fmtUsd(detalleSaldo)} × {tasaAbonoNum} = <strong>{formatBsRaw(saldoEnBsConTasa)}</strong>
                              </div>
                            ) : (
                              <div style={mutedStyle}>
                                Déjala vacía para usar la tasa normal. Si la cambias, los Bs del abono se calculan con la tuya.
                              </div>
                            )}
                          </div>
                        </details>

                        <button type="submit" style={primaryButtonStyle} disabled={savingAbono}>
                          {savingAbono ? 'Registrando…' : 'Registrar abono'}
                        </button>
                      </form>
                    ) : null}

                    <div style={pestanasStyle} role="tablist" aria-label="Detalle de la cuenta">
                      {pestanasDetalle.map((pestana) => (
                        <button
                          key={pestana.id}
                          type="button"
                          role="tab"
                          aria-selected={detalleTab === pestana.id}
                          onClick={() => setDetalleTab(pestana.id)}
                          style={pestanaStyle(detalleTab === pestana.id)}
                        >
                          {pestana.label}
                        </button>
                      ))}
                    </div>

                    {detalleTab === 'abonos' ? (
                      detalle.abonos.length === 0 ? (
                        <div style={mutedStyle}>Todavía no hay abonos.</div>
                      ) : (
                        <div style={listaDetalleStyle}>
                          {detalle.abonos.map((abono) => (
                            <div key={abono.id} style={lineaStyle}>
                              <div style={{ display: 'grid', gap: 2, minWidth: 0 }}>
                                <span style={lineaTituloStyle}>{abono.metodo_pago}</span>
                                <span style={mutedStyle} title={`Registrado el ${new Date(abono.fecha_pago).toLocaleString('es-VE')}`}>
                                  {abono.fecha_abono ? formatearFecha(abono.fecha_abono) : new Date(abono.fecha_pago).toLocaleDateString('es-VE')}
                                  {abono.referencia ? `, ref. ${abono.referencia}` : ''}
                                  {abono.tasa_manual ? `, tasa ${abono.tasa_cambio_referencia}` : ''}
                                </span>
                              </div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
                                <span style={{ display: 'grid', justifyItems: 'end', gap: 2 }}>
                                  <span style={lineaMontoStyle}>{fmtUsd(abono.monto)}</span>
                                  <span style={mutedStyle}>
                                    {formatBsRaw(abono.monto_bs != null ? abono.monto_bs : Number(abono.monto) * Number(abono.tasa_cambio_referencia ?? tasaCambio))}
                                  </span>
                                </span>
                                {onVerComprobante ? (
                                  <button
                                    type="button"
                                    onClick={() => onVerComprobante(detalle.tipo, detalle.id, abono.id)}
                                    style={iconButtonStyle}
                                    title="Ver comprobante"
                                    aria-label={`Ver comprobante del abono de ${fmtUsd(abono.monto)}`}
                                  >
                                    🖨
                                  </button>
                                ) : null}
                              </div>
                            </div>
                          ))}
                        </div>
                      )
                    ) : null}

                    {detalleTab === 'productos' && detalleEsLote ? (
                      <div style={listaDetalleStyle}>
                        {detalle.detalles.map((linea) => (
                          <div key={linea.id} style={lineaStyle}>
                            <span style={lineaTituloStyle}>{linea.ingrediente_nombre}</span>
                            <span style={{ ...mutedStyle, flexShrink: 0 }}>{linea.cantidad} {linea.unidad_medida}</span>
                            <span style={{ ...lineaMontoStyle, flexShrink: 0 }}>{fmtUsd(linea.subtotal)}</span>
                          </div>
                        ))}
                      </div>
                    ) : null}

                    {detalleTab === 'notas' && detalleEsLote ? (
                      <div style={{ display: 'grid', gap: 10 }}>
                        {notasCredito.length > 0 ? (
                          <div style={listaDetalleStyle}>
                            <div style={mutedStyle}>Total original {fmtUsd(detalle.total_original)}</div>
                            {notasCredito.map((nota) => (
                              <div key={nota.id} style={{ ...lineaStyle, opacity: nota.estado === 'anulada' ? 0.55 : 1 }}>
                                <div style={{ display: 'grid', gap: 2, minWidth: 0 }}>
                                  <span style={lineaTituloStyle}>
                                    {nota.codigo}{nota.estado === 'anulada' ? ' (anulada)' : ''}
                                  </span>
                                  <span style={mutedStyle}>
                                    {new Date(`${nota.fecha}T00:00:00`).toLocaleDateString('es-VE')}, {nota.estado === 'anulada' ? nota.motivo_anulacion : nota.motivo}
                                    {nota.numero_documento_proveedor ? `, nº ${nota.numero_documento_proveedor}` : ''}
                                  </span>
                                </div>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
                                  <span style={{ ...lineaMontoStyle, textDecoration: nota.estado === 'anulada' ? 'line-through' : 'none' }}>
                                    −{fmtUsd(nota.monto)}
                                  </span>
                                  {nota.estado === 'vigente' ? (
                                    <button type="button" disabled={savingNc} onClick={() => handleAnularNotaCredito(nota)} style={textButtonStyle}>
                                      Anular
                                    </button>
                                  ) : null}
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div style={mutedStyle}>Esta factura no tiene notas de crédito.</div>
                        )}

                        {!detalleSaldada ? (
                          ncAbierta ? (
                            <form onSubmit={handleRegistrarNotaCredito} style={ncFormStyle}>
                              <div style={formTituloStyle}>Nueva nota de crédito</div>
                              <div style={mutedStyle}>Baja lo que debes por esta factura. No cambia el inventario ni los abonos hechos.</div>
                              <div style={montoFilaStyle}>
                                <div style={monedaSegmentadoStyle} role="group" aria-label="Moneda de la nota">
                                  <button type="button" aria-pressed={ncMoneda === 'USD'} onClick={() => setNcMoneda('USD')} style={monedaOpcionStyle(ncMoneda === 'USD')}>$</button>
                                  <button type="button" aria-pressed={ncMoneda === 'VES'} onClick={() => setNcMoneda('VES')} style={monedaOpcionStyle(ncMoneda === 'VES')}>Bs</button>
                                </div>
                                <input
                                  type="number"
                                  min="0.01"
                                  step="0.01"
                                  placeholder="Monto"
                                  value={ncMonto}
                                  onChange={(event) => setNcMonto(event.target.value)}
                                  style={{ ...inputStyle, flex: 1, minWidth: 0 }}
                                  required
                                />
                              </div>
                              <input
                                type="text"
                                placeholder="Motivo, por ejemplo: monto mal cargado"
                                value={ncMotivo}
                                onChange={(event) => setNcMotivo(event.target.value)}
                                style={inputStyle}
                                required
                              />
                              <input
                                type="text"
                                placeholder="Nº de la nota del proveedor (opcional)"
                                value={ncNumero}
                                onChange={(event) => setNcNumero(event.target.value)}
                                style={inputStyle}
                              />
                              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                                <button type="submit" style={primaryButtonStyle} disabled={savingNc}>
                                  {savingNc ? 'Registrando…' : 'Registrar nota'}
                                </button>
                                <button type="button" onClick={() => setNcAbierta(false)} style={textButtonStyle} disabled={savingNc}>Cancelar</button>
                              </div>
                            </form>
                          ) : (
                            <button type="button" onClick={abrirNotaCredito} style={ghostButtonStyle(false)}>Nueva nota de crédito</button>
                          )
                        ) : null}
                      </div>
                    ) : null}

                    {detalleEsLote ? (
                      <div style={zonaPeligroStyle}>
                        <button type="button" onClick={() => setAnulandoCompra(detalle)} style={anularFacturaButtonStyle} title="El stock vuelve a como estaba">
                          Anular factura
                        </button>
                      </div>
                    ) : null}
                  </>
                )}
              </div>
              ) : null}
            </div>
          ) : null}
        </>
      ) : null}

      {modales}

      {anulandoCompra ? (
        <AnularCompraModal
          compra={anulandoCompra}
          onClose={() => setAnulandoCompra(null)}
          onDone={async (mensaje) => {
            setAnulandoCompra(null);
            setSelectedCompraId(null);
            setSelectedTipo(null);
            setCompraDetalle(null);
            setFeedbackType('success');
            setFeedback(mensaje);
            await fetchCompras();
          }}
        />
      ) : null}
    </section>
  );
}

function estadoLabel(estado) {
  if (estado === 'pendiente') return 'Pendiente';
  if (estado === 'abonada_parcial') return 'Abonada';
  if (estado === 'pagada' || estado === 'pagado') return 'Pagada';
  return estado;
}

function esEstadoSaldado(estado) {
  return estado === 'pagada' || estado === 'pagado';
}

// Monto total de una cuenta: un gasto trae `monto`, un lote trae `total`.
function montoTotalDe(cuenta) {
  return Number(cuenta.tipo === 'gasto' ? cuenta.monto : cuenta.total) || 0;
}

// $1,240.50 — con separador de miles, igual que el campo de monto.
function fmtUsd(valor) {
  const numero = Number(valor);
  if (!Number.isFinite(numero)) return '$0.00';
  return `$${numero.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// ---- Estilos. Mismos colores de la app; la jerarquía sale del tamaño, el peso y el espacio, no de más cajas. ----
const numeros = { fontVariantNumeric: 'tabular-nums' };
const mutedStyle = { color: 'var(--vg-f-a89999)', fontSize: 12, lineHeight: 1.4, ...numeros };

const containerStyle = (isMobile) => ({ display: 'grid', gap: isMobile ? 14 : 18, padding: isMobile ? 4 : 8 });
const headerWrapStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap', paddingTop: 36 };
const titleStyle = (isMobile) => ({ margin: 0, color: 'var(--vg-text-strong)', fontSize: isMobile ? 26 : 32, fontWeight: 700, letterSpacing: '-0.01em' });
const backLinkStyle = { width: 'fit-content', border: 'none', background: 'transparent', color: 'var(--vg-f-d2c4c4)', fontWeight: 600, fontSize: 13, cursor: 'pointer', padding: 0 };
const ghostButtonStyle = (activo) => ({
  border: '1px solid rgba(var(--vg-ink), 0.16)', borderRadius: 999, padding: '9px 16px', fontSize: 13, fontWeight: 700, cursor: 'pointer',
  background: activo ? 'rgba(var(--vg-ink), 0.1)' : 'transparent', color: 'var(--vg-text-strong)', width: 'fit-content',
});

const segmentedStyle = { display: 'inline-flex', width: 'fit-content', maxWidth: '100%', padding: 3, gap: 2, borderRadius: 999, background: 'rgba(var(--vg-ink), 0.06)', overflowX: 'auto', scrollbarWidth: 'none' };
const segmentStyle = (activo) => ({
  border: 'none', borderRadius: 999, padding: '8px 16px', fontSize: 13, fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap',
  background: activo ? 'var(--vg-text-strong)' : 'transparent', color: activo ? 'var(--vg-s-080808-a980)' : 'var(--vg-f-d2c4c4)',
});

const reportePanelStyle = { display: 'grid', gap: 12, padding: 16, borderRadius: 16, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'rgba(var(--vg-ink), 0.03)' };
const reporteFiltrosStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 260px))', gap: 12 });
const reporteLabelStyle = { display: 'grid', gap: 6, color: 'var(--vg-f-f2e6e6)', fontSize: 13, fontWeight: 600 };
const reporteCheckStyle = { display: 'flex', alignItems: 'center', gap: 8, color: 'var(--vg-f-f2e6e6)', fontSize: 13, fontWeight: 600, cursor: 'pointer' };

const resumenStyle = (isMobile) => ({ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 16, flexWrap: 'wrap', padding: isMobile ? '2px 2px 6px' : '4px 4px 8px' });
const resumenEtiquetaStyle = { color: 'var(--vg-f-d2c4c4)', fontSize: 14, fontWeight: 600 };
const resumenMontoStyle = (isMobile, pagadas) => ({ color: pagadas ? 'var(--vg-f-9fe3b0)' : 'var(--vg-f-ffcf7d)', fontSize: isMobile ? 32 : 40, fontWeight: 700, lineHeight: 1.1, letterSpacing: '-0.02em', ...numeros });
const resumenBsStyle = { color: 'var(--vg-f-a89999)', fontSize: 14, marginTop: 2, ...numeros };
const resumenConteoStyle = { textAlign: 'right', color: 'var(--vg-f-d2c4c4)', fontSize: 14, fontWeight: 600 };

const filtrosBusquedaRowStyle = (isMobile) => ({ display: 'flex', gap: 10, flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'stretch' : 'center' });
const busquedaInputStyle = { flex: 1, minWidth: 0, width: '100%', boxSizing: 'border-box', borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-161010)', padding: '11px 14px', color: 'var(--vg-f-fff4f4)', fontSize: 14 };
const chipsStyle = { display: 'flex', gap: 6, flexShrink: 0 };
const chipStyle = (activo) => ({
  border: activo ? '1px solid var(--vg-f-ff8282-a600)' : '1px solid rgba(var(--vg-ink), 0.14)', borderRadius: 999, padding: '8px 14px', fontSize: 13, fontWeight: 600, cursor: 'pointer',
  background: activo ? 'rgba(255, 90, 90, 0.14)' : 'transparent', color: activo ? 'var(--vg-f-ffb0b0)' : 'var(--vg-f-d2c4c4)',
});

const emptyStateStyle = { minHeight: 90, display: 'grid', placeItems: 'center', borderRadius: 16, border: '1px dashed rgba(var(--vg-ink), 0.14)', color: 'var(--vg-f-c8bbbb)', textAlign: 'center', padding: 20, fontSize: 14 };
const errorStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid var(--vg-f-ff9191-a220)', background: 'rgba(255, 98, 98, 0.12)', color: 'var(--vg-f-ffd8d8)', fontSize: 14 };
const feedbackStyle = (feedbackType) => ({
  display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', borderRadius: 12, padding: '10px 14px', fontSize: 14,
  border: feedbackType === 'error' ? '1px solid var(--vg-f-df6666-a500)' : '1px solid var(--vg-f-52ce7b-a350)',
  background: feedbackType === 'error' ? 'var(--vg-s-661d1d-a550)' : 'var(--vg-s-1f5930-a450)',
  color: feedbackType === 'error' ? 'var(--vg-f-ffe2e2)' : 'var(--vg-f-dbffe4)',
});
const comprobanteLinkStyle = { border: 'none', background: 'transparent', color: 'inherit', textDecoration: 'underline', fontWeight: 700, cursor: 'pointer', padding: 0, fontSize: 13 };

const layoutStyle = (compacto) => ({ display: 'grid', gridTemplateColumns: compacto ? '1fr' : 'minmax(300px, 380px) minmax(0, 1fr)', gap: compacto ? 14 : 24, alignItems: 'start' });
const listColumnStyle = { display: 'grid', gap: 10 };
const listPanelStyle = { display: 'grid', borderRadius: 16, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)', overflow: 'hidden' };
const colorEstado = (estado) => (estado === 'pendiente' ? 'var(--vg-f-ff9b9b)' : estado === 'abonada_parcial' ? 'var(--vg-f-ffcf7d)' : 'var(--vg-f-9fe3b0)');
const filaStyle = (seleccionada, estado) => ({
  display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, textAlign: 'left', width: '100%', boxSizing: 'border-box',
  padding: '14px 16px', border: 'none', borderBottom: '1px solid rgba(var(--vg-ink), 0.07)', borderLeft: `3px solid ${seleccionada ? colorEstado(estado) : 'transparent'}`,
  background: seleccionada ? 'rgba(var(--vg-ink), 0.07)' : 'transparent', color: 'var(--vg-text-strong)', cursor: 'pointer',
});
const filaTituloStyle = { color: 'var(--vg-text-strong)', fontWeight: 700, fontSize: 15, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' };
const filaMontoStyle = (pagadas) => ({ color: pagadas ? 'var(--vg-f-9fe3b0)' : 'var(--vg-f-ffcf7d)', fontWeight: 700, fontSize: 16, ...numeros });
const etiquetaAbonadaStyle = { color: 'var(--vg-f-ffcf7d)', fontSize: 11.5, fontWeight: 700 };
const barraPistaStyle = { display: 'block', height: 4, borderRadius: 999, background: 'rgba(var(--vg-ink), 0.1)', overflow: 'hidden', marginTop: 3 };
const barraRellenoStyle = { display: 'block', height: '100%', borderRadius: 999, background: 'var(--vg-f-9fe3b0)' };

const paginacionStyle = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 };
const paginacionTextoStyle = { color: 'var(--vg-f-c8bbbb)', fontSize: 12, fontWeight: 700 };
const paginacionBotonStyle = (deshabilitado) => ({
  border: '1px solid rgba(var(--vg-ink), 0.14)', borderRadius: 999, padding: '7px 14px', fontSize: 12, fontWeight: 700, background: 'transparent',
  color: deshabilitado ? '#6b6060' : 'var(--vg-text-strong)', cursor: deshabilitado ? 'not-allowed' : 'pointer', opacity: deshabilitado ? 0.6 : 1,
});

const detailPanelStyle = (isMobile) => ({
  display: 'grid', gap: 18, padding: isMobile ? 16 : 22, borderRadius: 20, minHeight: 220,
  background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)', border: '1px solid rgba(var(--vg-ink), 0.1)',
  boxShadow: '0 12px 28px rgba(0, 0, 0, calc(0.24 * var(--vg-shadow-k)))',
});
const detalleVacioStyle = { minHeight: 160, display: 'grid', placeItems: 'center', textAlign: 'center', color: 'var(--vg-f-c8bbbb)', fontSize: 14, padding: 12 };
const detalleCabeceraStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 };
const detalleTituloStyle = { margin: 0, color: 'var(--vg-text-strong)', fontSize: 22, fontWeight: 700, lineHeight: 1.2 };
const metaFilaStyle = { display: 'flex', flexWrap: 'wrap', columnGap: 14, rowGap: 2, marginTop: 6, color: 'var(--vg-f-a89999)', fontSize: 12.5 };
const estadoChipStyle = (estado) => ({
  flexShrink: 0, padding: '4px 12px', borderRadius: 999, fontSize: 12, fontWeight: 700,
  background: estado === 'pendiente' ? 'rgba(255, 145, 145, 0.16)' : esEstadoSaldado(estado) ? 'rgba(52, 211, 153, 0.16)' : 'rgba(255, 200, 120, 0.16)',
  color: colorEstado(estado === 'pagado' ? 'pagada' : estado),
});

const cifrasStyle = { display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12 };
const cifraStyle = { display: 'grid', gap: 2, alignContent: 'start' };
const cifraValorStyle = { color: 'var(--vg-text-strong)', fontSize: 17, fontWeight: 700, ...numeros };
const cifraDebesStyle = (saldada) => ({ color: saldada ? 'var(--vg-f-9fe3b0)' : 'var(--vg-f-ffcf7d)', fontSize: 26, fontWeight: 700, lineHeight: 1.1, letterSpacing: '-0.01em', ...numeros });

const abonoFormStyle = { display: 'grid', gap: 12, padding: 16, borderRadius: 16, background: 'rgba(var(--vg-ink), 0.04)', border: '1px solid rgba(var(--vg-ink), 0.08)' };
const formTituloStyle = { color: 'var(--vg-text-strong)', fontSize: 15, fontWeight: 700 };
const montoFilaStyle = { display: 'flex', alignItems: 'center', gap: 10 };
const monedaSegmentadoStyle = { display: 'inline-flex', flexShrink: 0, padding: 3, gap: 2, borderRadius: 12, background: 'rgba(var(--vg-ink), 0.08)' };
const monedaOpcionStyle = (activo) => ({
  border: 'none', borderRadius: 9, minWidth: 40, padding: '8px 10px', fontSize: 13, fontWeight: 800, cursor: 'pointer',
  background: activo ? 'linear-gradient(90deg, #1f7a3f 0%, #34d399 100%)' : 'transparent', color: activo ? '#04140a' : 'var(--vg-f-d2c4c4)',
});
const textButtonStyle = { border: 'none', background: 'transparent', color: 'var(--vg-f-9fe3b0)', fontWeight: 700, fontSize: 13, cursor: 'pointer', padding: '4px 2px', whiteSpace: 'nowrap' };
const dosColumnasStyle = (compacto) => ({ display: 'grid', gridTemplateColumns: compacto ? '1fr' : '1fr 1fr', gap: 12 });
const campoStyle = { display: 'grid', gap: 6 };
const campoEtiquetaStyle = { color: 'var(--vg-f-d2c4c4)', fontSize: 12.5, fontWeight: 600 };
const fechaHoyStyle = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, minHeight: 38, color: 'var(--vg-text-strong)', fontSize: 14, fontWeight: 600 };
const tasaEnVivoStyle = { color: 'var(--vg-f-ffcf7d)', fontSize: 14, fontWeight: 600, fontVariantNumeric: 'tabular-nums' };
const avisoFechaStyle = { color: 'var(--vg-f-ffcf7d)', fontSize: 12.5, fontWeight: 600 };
const opcionesStyle = { color: 'var(--vg-f-d2c4c4)' };
const opcionesResumenStyle = { cursor: 'pointer', fontSize: 13, fontWeight: 600, color: 'var(--vg-f-a89999)' };
const inputStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-161010)', padding: '10px 12px', color: 'var(--vg-f-fff4f4)', fontSize: 14 };
const selectStyle = { ...inputStyle, appearance: 'auto', colorScheme: 'dark', cursor: 'pointer' };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '12px 18px', background: 'linear-gradient(90deg, #1f7a3f 0%, #34d399 100%)', color: '#04140a', fontWeight: 800, fontSize: 14, cursor: 'pointer' };

const pestanasStyle = { display: 'flex', gap: 18, borderBottom: '1px solid rgba(var(--vg-ink), 0.1)', overflowX: 'auto', scrollbarWidth: 'none' };
const pestanaStyle = (activa) => ({
  border: 'none', background: 'transparent', padding: '8px 0', fontSize: 13.5, fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap',
  color: activa ? 'var(--vg-text-strong)' : 'var(--vg-f-a89999)', borderBottom: activa ? '2px solid var(--vg-f-ff8282-a600)' : '2px solid transparent', marginBottom: -1,
});
const listaDetalleStyle = { display: 'grid', gap: 2 };
const lineaStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, padding: '10px 0', borderBottom: '1px solid rgba(var(--vg-ink), 0.06)' };
const lineaTituloStyle = { color: 'var(--vg-text-strong)', fontSize: 14, fontWeight: 600, minWidth: 0 };
const lineaMontoStyle = { color: 'var(--vg-text-strong)', fontSize: 14, fontWeight: 700, ...numeros };
const iconButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.14)', borderRadius: 10, padding: '6px 8px', background: 'transparent', cursor: 'pointer', fontSize: 14, lineHeight: 1 };
const ncFormStyle = { display: 'grid', gap: 10, padding: 14, borderRadius: 14, border: '1px solid var(--vg-f-78b4ff-a350)', background: 'rgba(59, 130, 246, 0.07)' };
const zonaPeligroStyle = { display: 'flex', justifyContent: 'flex-end', paddingTop: 4 };
const anularFacturaButtonStyle = { border: 'none', background: 'transparent', color: 'var(--vg-f-ff9b9b)', fontWeight: 600, fontSize: 13, cursor: 'pointer', padding: '4px 2px', textDecoration: 'underline' };

export default CuentasPorPagarPage;

import { useCallback, useEffect, useMemo, useState } from 'react';
import BsAmount from './BsAmount';
import useExchangeRate from '../hooks/useExchangeRate';

function toIso(date) {
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60000);
  return local.toISOString().slice(0, 10);
}

function todayIso() {
  return toIso(new Date());
}

function startOfWeekIso() {
  const now = new Date();
  const day = now.getDay();
  const diff = day === 0 ? 6 : day - 1;
  const monday = new Date(now);
  monday.setDate(now.getDate() - diff);
  return toIso(monday);
}

function startOfMonthIso() {
  const now = new Date();
  return toIso(new Date(now.getFullYear(), now.getMonth(), 1));
}

function startOfYearIso() {
  const now = new Date();
  return toIso(new Date(now.getFullYear(), 0, 1));
}

function yesterdayIso() {
  const now = new Date();
  now.setDate(now.getDate() - 1);
  return toIso(now);
}

function formatMonto(value) {
  const number = Number(value || 0);
  return number.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatHora(isoString) {
  if (!isoString) return '';
  const fecha = new Date(isoString);
  return fecha.toLocaleString('es-VE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function formatCantidadFila(fila) {
  if (fila.unidad === 'kg' && fila.peso_gramos != null) {
    return `${formatMonto(fila.peso_gramos)} g`;
  }
  return `${fila.cantidad} u.`;
}

const PRESETS = [
  { label: 'Hoy', get: () => ({ desde: todayIso(), hasta: todayIso() }) },
  { label: 'Ayer', get: () => ({ desde: yesterdayIso(), hasta: yesterdayIso() }) },
  { label: 'Esta semana', get: () => ({ desde: startOfWeekIso(), hasta: todayIso() }) },
  { label: 'Este mes', get: () => ({ desde: startOfMonthIso(), hasta: todayIso() }) },
  { label: 'Este año', get: () => ({ desde: startOfYearIso(), hasta: todayIso() }) },
];

function AnalystMargenGananciaPage({ isMobile, onBack }) {
  const tasaCambio = useExchangeRate();
  // Por defecto se ve solo el día de hoy — el analista elige el rango si
  // quiere ver más.
  const [desde, setDesde] = useState(todayIso());
  const [hasta, setHasta] = useState(todayIso());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busqueda, setBusqueda] = useState('');
  const [isBusquedaFocused, setIsBusquedaFocused] = useState(false);
  const [productoSeleccionado, setProductoSeleccionado] = useState(null);

  const loadReport = useCallback(async (desdeConsultado, hastaConsultado) => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch(
        `/api/admin/reportes/margen-ganancia/?desde=${desdeConsultado}&hasta=${hastaConsultado}`,
        { credentials: 'include', cache: 'no-store' },
      );
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cargar el reporte de margen de ganancia.');
      }
      setData(json);
    } catch (requestError) {
      setError(requestError.message || 'No se pudo cargar el reporte de margen de ganancia.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadReport(desde, hasta);
  }, [desde, hasta, loadReport]);

  useEffect(() => {
    setBusqueda('');
    setProductoSeleccionado(null);
  }, [desde, hasta]);

  const applyPreset = (preset) => {
    const range = preset.get();
    setDesde(range.desde);
    setHasta(range.hasta);
  };

  const secciones = data?.secciones || [];
  const totales = data?.totales;

  const query = busqueda.trim().toLowerCase();

  // Hasta 5 coincidencias para el desplegable, mientras se escribe y todavía
  // no se ha seleccionado un plato puntual.
  const coincidencias = useMemo(() => {
    if (!query) return [];
    return secciones.filter((seccion) => seccion.nombre.toLowerCase().includes(query)).slice(0, 5);
  }, [secciones, query]);

  const handleBusquedaChange = (value) => {
    // Escribir invalida la selección anterior — el filtro solo aplica cuando
    // se elige un plato puntual del desplegable, no con el texto libre.
    setBusqueda(value);
    setProductoSeleccionado(null);
  };

  const handleSelectProducto = (seccion) => {
    setProductoSeleccionado({ producto_id: seccion.producto_id, nombre: seccion.nombre });
    setBusqueda(seccion.nombre);
    setIsBusquedaFocused(false);
  };

  const handleQuitarFiltro = () => {
    setProductoSeleccionado(null);
    setBusqueda('');
  };

  // Una sección = un producto (con todas sus ventas individuales) — si hay un
  // plato seleccionado del desplegable, solo se muestra esa sección; si no,
  // se muestran todas.
  const seccionesFiltradas = useMemo(() => {
    if (!productoSeleccionado) return secciones;
    return secciones.filter((seccion) => seccion.producto_id === productoSeleccionado.producto_id);
  }, [secciones, productoSeleccionado]);

  return (
    <section style={containerStyle(isMobile)}>
      <div className="no-print" style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          ← Volver a Contabilidad
        </button>
        <button type="button" onClick={() => window.print()} style={printButtonStyle}>
          Imprimir / Guardar PDF
        </button>
      </div>

      <div>
        <h2 style={titleStyle(isMobile)}>Margen de ganancia por plato</h2>
      </div>

      <div className="no-print" style={filtersRowStyle(isMobile)}>
        <label style={dateLabelStyle}>
          Desde
          <input type="date" value={desde} max={hasta} onChange={(event) => setDesde(event.target.value)} style={dateInputStyle} />
        </label>
        <label style={dateLabelStyle}>
          Hasta
          <input type="date" value={hasta} max={todayIso()} onChange={(event) => setHasta(event.target.value)} style={dateInputStyle} />
        </label>
        <div style={presetsWrapStyle}>
          {PRESETS.map((preset) => (
            <button key={preset.label} type="button" onClick={() => applyPreset(preset)} style={presetButtonStyle}>
              {preset.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? <div style={emptyStyle}>Cargando reporte...</div> : null}
      {!loading && error ? <div style={noticeStyle}>{error}</div> : null}

      {!loading && !error && data ? (
        <section style={panelStyle}>
          <div style={sectionTitleStyle}>
            {desde === hasta ? `Ventas del ${desde}` : `Ventas del ${desde} al ${hasta}`}
          </div>

          <div className="no-print" style={{ ...searchWrapStyle, position: 'relative' }}>
            <input
              type="text"
              value={busqueda}
              onChange={(event) => handleBusquedaChange(event.target.value)}
              onFocus={() => setIsBusquedaFocused(true)}
              onBlur={() => setTimeout(() => setIsBusquedaFocused(false), 150)}
              placeholder="Buscar plato por nombre..."
              style={searchInputStyle}
              autoComplete="off"
            />
            {isBusquedaFocused && query && coincidencias.length > 0 ? (
              <div style={suggestionsPanelStyle}>
                {coincidencias.map((seccion) => (
                  <button
                    key={seccion.producto_id}
                    type="button"
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => handleSelectProducto(seccion)}
                    style={suggestionRowStyle}
                  >
                    <span style={{ color: '#fff', fontWeight: 600 }}>{seccion.nombre}</span>
                    <span style={{ color: '#e8bcbc', fontSize: 12 }}>{seccion.categoria}</span>
                  </button>
                ))}
              </div>
            ) : null}
            {productoSeleccionado ? (
              <button type="button" onClick={handleQuitarFiltro} style={quitarFiltroButtonStyle} className="no-print">
                Quitar filtro ×
              </button>
            ) : null}
          </div>

          {seccionesFiltradas.length === 0 ? (
            <div style={emptyStyle}>No hay ventas para este filtro.</div>
          ) : (
            <div style={{ display: 'grid', gap: 22 }}>
              {seccionesFiltradas.map((seccion) => (
                <div key={seccion.producto_id} style={seccionBlockStyle}>
                  <div style={seccionTituloStyle}>
                    {seccion.nombre}
                    <span style={seccionCategoriaStyle}>{seccion.categoria}</span>
                    {seccion.tiene_costo_estimado ? (
                      <span
                        style={estimadoBadgeStyle}
                        title="Alguna venta de este plato es de antes de que se empezara a guardar el costo histórico; se usó el costo actual de la receta para esa fila puntual."
                      >
                        costo estimado en alguna fila
                      </span>
                    ) : null}
                  </div>
                  <div style={tableWrapStyle}>
                    <div style={tableStyle}>
                      <div style={headStyle}>Cantidad</div>
                      <div style={headStyle}>Fecha / hora</div>
                      <div style={headStyle}>Pedido</div>
                      <div style={headStyle}>Nota de entrega</div>
                      <div style={headStyle}>Ingreso</div>
                      <div style={headStyle}>Costo</div>
                      <div style={headStyle}>Ganancia</div>
                      {seccion.filas.map((fila) => (
                        <div key={fila.detalle_id} style={rowFragmentStyle}>
                          <div style={{ ...cellStyle, fontWeight: 700, color: '#8fffb0' }}>{formatCantidadFila(fila)}</div>
                          <div style={cellStyle}>{formatHora(fila.fecha_hora)}</div>
                          <div style={cellStyle}>#{fila.pedido_id}</div>
                          <div style={cellStyle}>{fila.nota_entrega_codigo || '—'}</div>
                          <div style={cellStyle}>
                            ${formatMonto(fila.ingreso)}
                            <BsAmount amountUsd={fila.ingreso} tasa={tasaCambio} />
                          </div>
                          <div style={cellStyle}>
                            ${formatMonto(fila.costo)}
                            <BsAmount amountUsd={fila.costo} tasa={tasaCambio} />
                            {fila.costo_estimado ? <span style={estimadoBadgeInlineStyle}>estimado</span> : null}
                          </div>
                          <div style={{ ...cellStyle, color: Number(fila.ganancia_monto) >= 0 ? '#8fffb0' : '#ff9d9d', fontWeight: 700 }}>
                            ${formatMonto(fila.ganancia_monto)} ({formatMonto(fila.ganancia_pct)}%)
                          </div>
                        </div>
                      ))}
                      <div style={{ ...cellStyle, ...totalCellStyle, fontWeight: 800, color: '#8fffb0' }}>
                        {Number(seccion.total_unidades) > 0 ? `${formatMonto(seccion.total_unidades)} u.` : ''}
                        {Number(seccion.total_unidades) > 0 && Number(seccion.total_kg) > 0 ? ' + ' : ''}
                        {Number(seccion.total_kg) > 0 ? `${formatMonto(seccion.total_kg)} kg` : ''}
                      </div>
                      <div style={{ ...cellStyle, ...totalCellStyle, fontWeight: 800 }}>Total: {seccion.total_lineas} línea(s)</div>
                      <div style={{ ...cellStyle, ...totalCellStyle }} />
                      <div style={{ ...cellStyle, ...totalCellStyle }} />
                      <div style={{ ...cellStyle, ...totalCellStyle, fontWeight: 800 }}>${formatMonto(seccion.total_ingreso)}</div>
                      <div style={{ ...cellStyle, ...totalCellStyle, fontWeight: 800 }}>${formatMonto(seccion.total_costo)}</div>
                      <div style={{ ...cellStyle, ...totalCellStyle, fontWeight: 800, color: '#8fffb0' }}>
                        ${formatMonto(seccion.total_ganancia_monto)} ({formatMonto(seccion.total_ganancia_pct)}%)
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {totales ? (
            <div style={summaryStyle}>
              {data.total_lineas} venta(s) en el período · Ingreso ${formatMonto(totales.ingreso_total)} · Costo $
              {formatMonto(totales.costo_total)} · Ganancia ${formatMonto(totales.ganancia_monto)} ({formatMonto(totales.ganancia_pct)}%)
            </div>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: '#d2c3c3', maxWidth: 640, lineHeight: 1.6 };
const filtersRowStyle = (isMobile) => ({
  display: 'flex',
  gap: 14,
  flexWrap: 'wrap',
  alignItems: isMobile ? 'stretch' : 'flex-end',
  flexDirection: isMobile ? 'column' : 'row',
});
const dateLabelStyle = { display: 'flex', flexDirection: 'column', gap: 6, color: '#f2e6e6', fontSize: 13, fontWeight: 700 };
const dateInputStyle = { borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff' };
const presetsWrapStyle = { display: 'flex', gap: 8, flexWrap: 'wrap' };
const presetButtonStyle = { border: '1px solid rgba(255,255,255,0.16)', borderRadius: 999, padding: '9px 14px', background: 'rgba(255,255,255,0.05)', color: '#fff', fontSize: 13, fontWeight: 700, cursor: 'pointer' };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const sectionTitleStyle = { color: '#fff', fontSize: 19, fontWeight: 700 };
const seccionBlockStyle = { display: 'grid', gap: 8 };
const seccionTituloStyle = { display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap', color: '#ff9d9d', fontSize: 15, fontWeight: 800 };
const seccionCategoriaStyle = { color: '#c8bbbb', fontSize: 11.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(90px,0.6fr) minmax(140px,0.9fr) minmax(80px,0.5fr) minmax(130px,0.8fr) minmax(120px,0.8fr) minmax(120px,0.9fr) minmax(140px,1fr)', minWidth: 980, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(255,255,255,0.06)', color: '#ffb0b0', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '14px', borderTop: '1px solid rgba(255,255,255,0.08)', color: '#f2e6e6', display: 'grid', alignContent: 'center' };
const totalCellStyle = { background: 'rgba(255,255,255,0.04)' };
const estimadoBadgeStyle = {
  padding: '2px 8px',
  borderRadius: 999,
  background: 'rgba(255, 200, 120, 0.16)',
  color: '#ffcf7d',
  fontSize: 10.5,
  fontWeight: 800,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
};
const estimadoBadgeInlineStyle = { ...estimadoBadgeStyle, marginLeft: 6, display: 'inline-block' };
const rowFragmentStyle = { display: 'contents' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };
const printButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const searchInputStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff', fontSize: 14 };
const searchWrapStyle = { maxWidth: 420 };
const summaryStyle = { color: '#c8bbbb', fontSize: 13 };
const suggestionsPanelStyle = { position: 'absolute', top: '100%', left: 0, right: 0, marginTop: 6, zIndex: 5, borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: 'rgba(10, 8, 8, 0.98)', boxShadow: '0 12px 30px rgba(0,0,0,0.4)', padding: 8, display: 'grid', gap: 4, maxHeight: 260, overflowY: 'auto' };
const suggestionRowStyle = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 10, padding: '8px 10px', background: 'rgba(255,255,255,0.04)', cursor: 'pointer', textAlign: 'left' };
const quitarFiltroButtonStyle = { marginTop: 8, border: '1px solid rgba(255,157,157,0.35)', borderRadius: 999, padding: '6px 12px', background: 'rgba(145,33,33,0.2)', color: '#ff9d9d', fontWeight: 700, fontSize: 12, cursor: 'pointer' };

export default AnalystMargenGananciaPage;

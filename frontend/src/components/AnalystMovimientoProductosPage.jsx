import { useCallback, useEffect, useMemo, useState } from 'react';

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

const PRESETS = [
  { label: 'Hoy', get: () => ({ desde: todayIso(), hasta: todayIso() }) },
  { label: 'Ayer', get: () => ({ desde: yesterdayIso(), hasta: yesterdayIso() }) },
  { label: 'Esta semana', get: () => ({ desde: startOfWeekIso(), hasta: todayIso() }) },
  { label: 'Este mes', get: () => ({ desde: startOfMonthIso(), hasta: todayIso() }) },
  { label: 'Este año', get: () => ({ desde: startOfYearIso(), hasta: todayIso() }) },
];

const CATEGORIA_TODAS = '__todas__';
const CATEGORIA_SIN = '__sin__';

function AnalystMovimientoProductosPage({ isMobile, onBack }) {
  const [desde, setDesde] = useState(startOfMonthIso());
  const [hasta, setHasta] = useState(todayIso());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [categoriaFiltro, setCategoriaFiltro] = useState(CATEGORIA_TODAS);
  const [busqueda, setBusqueda] = useState('');

  const loadReport = useCallback(async (desdeConsultado, hastaConsultado) => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch(
        `/api/admin/reportes/movimiento-productos/?desde=${desdeConsultado}&hasta=${hastaConsultado}`,
        { credentials: 'include', cache: 'no-store' },
      );
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cargar el reporte de movimiento de productos.');
      }
      setData(json);
    } catch (requestError) {
      setError(requestError.message || 'No se pudo cargar el reporte de movimiento de productos.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadReport(desde, hasta);
  }, [desde, hasta, loadReport]);

  useEffect(() => {
    setCategoriaFiltro(CATEGORIA_TODAS);
    setBusqueda('');
  }, [desde, hasta]);

  const applyPreset = (preset) => {
    const range = preset.get();
    setDesde(range.desde);
    setHasta(range.hasta);
  };

  const productos = data?.productos || [];
  const categorias = data?.categorias || [];

  const productosFiltrados = useMemo(() => {
    const query = busqueda.trim().toLowerCase();
    return productos.filter((producto) => {
      if (categoriaFiltro === CATEGORIA_SIN) {
        if (producto.categoria_id) return false;
      } else if (categoriaFiltro !== CATEGORIA_TODAS) {
        if (String(producto.categoria_id) !== categoriaFiltro) return false;
      }
      if (query && !producto.nombre.toLowerCase().includes(query)) return false;
      return true;
    });
  }, [productos, categoriaFiltro, busqueda]);

  const totalesFiltrados = useMemo(() => {
    let unidades = 0;
    let kg = 0;
    let ventas = 0;
    productosFiltrados.forEach((producto) => {
      if (producto.unidad === 'kg') kg += Number(producto.cantidad_vendida || 0);
      else unidades += Number(producto.cantidad_vendida || 0);
      ventas += Number(producto.num_ventas || 0);
    });
    return { unidades, kg, ventas };
  }, [productosFiltrados]);

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
        <h2 style={titleStyle(isMobile)}>Movimiento de productos</h2>
        <p style={subtitleStyle}>
          Cuántas unidades (o kilos) de cada plato se vendieron en el rango de fechas que elijas — filtra por
          categoría o busca un producto puntual para ver solo su movimiento.
        </p>
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
            {desde === hasta ? `Movimiento del ${desde}` : `Movimiento del ${desde} al ${hasta}`}
          </div>

          {categorias.length > 0 ? (
            <div className="no-print" style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              <button
                type="button"
                onClick={() => setCategoriaFiltro(CATEGORIA_TODAS)}
                style={chipButtonStyle(categoriaFiltro === CATEGORIA_TODAS)}
              >
                Todas las categorías
              </button>
              {categorias.map((categoria) => (
                <button
                  key={categoria.categoria_id ?? 'sin-categoria'}
                  type="button"
                  onClick={() => setCategoriaFiltro(categoria.categoria_id ? String(categoria.categoria_id) : CATEGORIA_SIN)}
                  style={chipButtonStyle(categoriaFiltro === (categoria.categoria_id ? String(categoria.categoria_id) : CATEGORIA_SIN))}
                >
                  {categoria.categoria}
                  {Number(categoria.cantidad_unidades) > 0 ? ` · ${formatMonto(categoria.cantidad_unidades)} u.` : ''}
                  {Number(categoria.cantidad_kg) > 0 ? ` · ${formatMonto(categoria.cantidad_kg)} kg` : ''}
                </button>
              ))}
            </div>
          ) : null}

          <input
            type="text"
            value={busqueda}
            onChange={(event) => setBusqueda(event.target.value)}
            placeholder="Buscar producto por nombre..."
            style={searchInputStyle}
          />

          {productosFiltrados.length === 0 ? (
            <div style={emptyStyle}>No hay productos con movimiento para este filtro.</div>
          ) : (
            <div style={tableWrapStyle}>
              <div style={tableStyle}>
                <div style={headStyle}>Producto</div>
                <div style={headStyle}>Categoría</div>
                <div style={headStyle}>Cant. vendida</div>
                <div style={headStyle}>Pedidos</div>
                {productosFiltrados.map((producto) => (
                  <div key={producto.producto_id} style={rowFragmentStyle}>
                    <div style={cellStyle}>{producto.nombre}</div>
                    <div style={cellStyle}>{producto.categoria}</div>
                    <div style={{ ...cellStyle, fontWeight: 700, color: '#8fffb0' }}>
                      {formatMonto(producto.cantidad_vendida)} {producto.unidad === 'kg' ? 'kg' : 'u.'}
                    </div>
                    <div style={cellStyle}>{producto.num_ventas}</div>
                  </div>
                ))}
                <div style={{ ...cellStyle, fontWeight: 800 }}>Total</div>
                <div style={cellStyle} />
                <div style={{ ...cellStyle, fontWeight: 800, color: '#8fffb0' }}>
                  {totalesFiltrados.unidades > 0 ? `${formatMonto(totalesFiltrados.unidades)} u.` : ''}
                  {totalesFiltrados.unidades > 0 && totalesFiltrados.kg > 0 ? ' + ' : ''}
                  {totalesFiltrados.kg > 0 ? `${formatMonto(totalesFiltrados.kg)} kg` : ''}
                </div>
                <div style={{ ...cellStyle, fontWeight: 800 }}>{formatMonto(totalesFiltrados.ventas)}</div>
              </div>
            </div>
          )}

          <div style={summaryStyle}>
            {data.total_productos_distintos} producto(s) con movimiento en el período completo
            {Number(data.total_unidades_vendidas) > 0 ? ` · ${formatMonto(data.total_unidades_vendidas)} unidades vendidas` : ''}
            {Number(data.total_kg_vendidos) > 0 ? ` · ${formatMonto(data.total_kg_vendidos)} kg vendidos` : ''}
          </div>
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
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(220px,1.8fr) minmax(140px,1fr) minmax(140px,0.9fr) minmax(100px,0.6fr)', minWidth: 720, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(255,255,255,0.06)', color: '#ffb0b0', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '14px', borderTop: '1px solid rgba(255,255,255,0.08)', color: '#f2e6e6', display: 'grid', alignContent: 'center' };
const rowFragmentStyle = { display: 'contents' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };
const printButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const searchInputStyle = { borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff', fontSize: 14 };
const summaryStyle = { color: '#c8bbbb', fontSize: 13 };
const chipButtonStyle = (active) => ({
  border: active ? '1px solid rgba(143,255,176,0.5)' : '1px solid rgba(255,255,255,0.16)',
  borderRadius: 999,
  padding: '8px 14px',
  background: active ? 'rgba(70, 200, 120, 0.16)' : 'rgba(255,255,255,0.05)',
  color: active ? '#8fffb0' : '#fff',
  fontSize: 12.5,
  fontWeight: 700,
  cursor: 'pointer',
});

export default AnalystMovimientoProductosPage;

import { useCallback, useEffect, useMemo, useState } from 'react';

// Reporte de margen de ganancia POR PRODUCTO, en vivo: se recalcula con los costos de hoy
// (ingredientes, subrecetas y recetas), no con ventas pasadas. El reporte anterior, venta por
// venta, quedo guardado sin acceso en AnalystMargenGananciaDetalladoPage.

function formatMonto(value) {
  const number = Number(value || 0);
  return number.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatPct(value) {
  if (value == null || value === '') return '—';
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  return `${number.toLocaleString('es-VE', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}%`;
}

function CeldaMonto({ value, sinDato }) {
  if (sinDato) return <span style={{ color: '#7a6f6f' }}>—</span>;
  return <>${formatMonto(value)}</>;
}

function AnalystMargenGananciaPage({ isMobile, onBack, onVerDetalle }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busqueda, setBusqueda] = useState('');
  const [categoriaId, setCategoriaId] = useState('');
  const [ocultarSinReceta, setOcultarSinReceta] = useState(false);

  const loadReport = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch('/api/admin/reportes/margen-productos/', { credentials: 'include', cache: 'no-store' });
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
    loadReport();
  }, [loadReport]);

  const productos = data?.productos || [];

  const categorias = useMemo(() => {
    const vistas = new Map();
    productos.forEach((producto) => vistas.set(String(producto.categoria_id), producto.categoria));
    return [...vistas.entries()].map(([id, nombre]) => ({ id, nombre })).sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'));
  }, [productos]);

  const query = busqueda.trim().toLowerCase();
  const filas = useMemo(() => productos.filter((producto) => {
    if (query && !producto.nombre.toLowerCase().includes(query)) return false;
    if (categoriaId && String(producto.categoria_id) !== categoriaId) return false;
    if (ocultarSinReceta && !producto.tiene_receta) return false;
    return true;
  }), [productos, query, categoriaId, ocultarSinReceta]);

  const sinReceta = productos.filter((producto) => !producto.tiene_receta).length;
  const bajoElSugerido = productos.filter((producto) => (
    producto.tiene_receta && Number(producto.precio_real) < Number(producto.precio_sugerido)
  )).length;

  return (
    <section style={containerStyle(isMobile)}>
      <div className="no-print" style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          ← Volver a Contabilidad
        </button>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {onVerDetalle ? (
            <button type="button" onClick={onVerDetalle} style={detalleButtonStyle}>
              Ver detalles de margen de ganancia por plato
            </button>
          ) : null}
          <button type="button" onClick={loadReport} style={printButtonStyle} disabled={loading}>
            {loading ? 'Actualizando...' : 'Actualizar'}
          </button>
          <button type="button" onClick={() => window.print()} style={printButtonStyle}>
            Imprimir / Guardar PDF
          </button>
        </div>
      </div>

      <div>
        <h2 style={titleStyle(isMobile)}>Margen de ganancia por producto</h2>
        <p style={subtitleStyle}>
          Se calcula con los costos de hoy: si cambia el costo de un ingrediente, de una subreceta o de la receta, la fila cambia sola.
        </p>
      </div>

      {data ? (
        <div style={chipsRowStyle}>
          <span style={chipStyle}>Margen de producción: {formatPct(data.config.rendimiento_receta_pct)}</span>
          <span style={chipStyle}>Margen de ganancia por defecto: {formatPct(data.config.margen_ganancia_defecto_pct)}</span>
        </div>
      ) : null}

      <div className="no-print" style={filtersRowStyle(isMobile)}>
        <input
          type="text"
          value={busqueda}
          onChange={(event) => setBusqueda(event.target.value)}
          placeholder="Buscar producto por nombre..."
          style={searchInputStyle}
          autoComplete="off"
        />
        <select value={categoriaId} onChange={(event) => setCategoriaId(event.target.value)} style={selectStyle} className="admin-dark-select">
          <option value="">Todas las categorías</option>
          {categorias.map((categoria) => (
            <option key={categoria.id} value={categoria.id}>{categoria.nombre}</option>
          ))}
        </select>
        <label style={checkLabelStyle}>
          <input type="checkbox" checked={ocultarSinReceta} onChange={(event) => setOcultarSinReceta(event.target.checked)} />
          Ocultar productos sin receta
        </label>
      </div>

      {loading && !data ? <div style={emptyStyle}>Cargando reporte...</div> : null}
      {error ? <div style={noticeStyle}>{error}</div> : null}

      {data ? (
        <section style={panelStyle}>
          {filas.length === 0 ? (
            <div style={emptyStyle}>No hay productos para este filtro.</div>
          ) : (
            <div style={tableWrapStyle}>
              <div style={tableStyle}>
                <div style={{ ...headStyle, ...headProductoStyle }}>Producto</div>
                <div style={headBaseStyle} title="Costo de la receta, subreceta o ingrediente anclado al producto, sin margen de producción">Costo receta</div>
                <div style={headBaseStyle} title="Porcentaje de producción (mermas) que se suma al costo de la receta">Margen de producción</div>
                <div style={headBaseStyle} title="Costo de receta + margen de producción: es el costo sobre el que se calcula la ganancia">Costo a tomar</div>
                <div style={headBaseStyle} title="Margen propio del producto o, si no tiene, el de por defecto">Margen de ganancia</div>
                <div style={headBaseStyle} title="Costo a tomar + margen de ganancia">Precio de venta sugerido</div>
                <div style={headBaseStyle} title="Precio de venta actual del producto en el menú">Precio de venta real</div>
                <div style={headResultStyle}>$ Ganancia</div>
                <div style={headResultStyle}>% Ganancia</div>

                {filas.map((fila) => {
                  const sinDato = !fila.tiene_receta;
                  const bajo = !sinDato && Number(fila.precio_real) < Number(fila.precio_sugerido);
                  const negativa = !sinDato && Number(fila.ganancia) < 0;
                  const colorGanancia = sinDato ? '#7a6f6f' : negativa ? '#ff9d9d' : '#8fffb0';
                  return (
                    <div key={fila.producto_id} style={rowFragmentStyle}>
                      <div style={{ ...cellStyle, ...cellProductoStyle }}>
                        <div style={{ fontWeight: 800 }}>
                          {fila.nombre}
                          {fila.venta_por_peso ? <span style={tagStyle}>por kg</span> : null}
                          {!fila.disponible ? <span style={tagMutedStyle}>no disponible</span> : null}
                          {sinDato ? <span style={tagWarnStyle}>sin receta</span> : null}
                        </div>
                        <div style={{ fontSize: 11.5, color: '#a89999' }}>{fila.categoria}</div>
                        {fila.ingredientes_sin_costo && fila.ingredientes_sin_costo.length > 0 ? (
                          <div
                            style={{ fontSize: 11.5, color: '#ffcf7d', fontWeight: 700 }}
                            title="Ese ingrediente no tiene precio de compra registrado: aporta $0 y el costo del producto queda incompleto."
                          >
                            Falta el costo de: {fila.ingredientes_sin_costo.join(', ')}
                          </div>
                        ) : null}
                      </div>
                      <div style={cellStyle}><CeldaMonto value={fila.costo_receta} sinDato={sinDato} /></div>
                      <div style={cellStyle}>{sinDato ? <span style={{ color: '#7a6f6f' }}>—</span> : formatPct(fila.margen_produccion_pct)}</div>
                      <div style={cellStyle}><CeldaMonto value={fila.costo_a_tomar} sinDato={sinDato} /></div>
                      <div style={cellStyle}>
                        {formatPct(fila.margen_ganancia_pct)}
                        <span style={{ fontSize: 10.5, color: '#a89999' }}>{fila.margen_ganancia_propio ? 'propio' : 'por defecto'}</span>
                      </div>
                      <div style={cellStyle}><CeldaMonto value={fila.precio_sugerido} sinDato={sinDato} /></div>
                      <div
                        style={{ ...cellStyle, fontWeight: 800, color: bajo ? '#ffcf7d' : '#f2e6e6' }}
                        title={bajo ? 'El precio real está por debajo del sugerido' : undefined}
                      >
                        ${formatMonto(fila.precio_real)}
                        {bajo ? <span style={{ fontSize: 10.5, color: '#ffcf7d' }}>bajo el sugerido</span> : null}
                      </div>
                      <div style={{ ...cellStyle, fontWeight: 800, color: colorGanancia }}>
                        <CeldaMonto value={fila.ganancia} sinDato={sinDato} />
                      </div>
                      <div style={{ ...cellStyle, fontWeight: 800, color: colorGanancia }}>
                        {sinDato || fila.ganancia_pct == null ? <span style={{ color: '#7a6f6f' }}>—</span> : formatPct(fila.ganancia_pct)}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <div style={summaryStyle}>
            {productos.length} producto(s)
            {sinReceta > 0 ? ` · ${sinReceta} sin receta (sin costo)` : ''}
            {bajoElSugerido > 0 ? ` · ${bajoElSugerido} con precio real por debajo del sugerido` : ''}
          </div>
        </section>
      ) : null}
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: '#d2c3c3', maxWidth: 720, lineHeight: 1.6 };
const chipsRowStyle = { display: 'flex', gap: 8, flexWrap: 'wrap' };
const chipStyle = { display: 'inline-flex', padding: '5px 12px', borderRadius: 999, fontSize: 12, fontWeight: 700, color: '#c8bbbb', background: 'rgba(255,255,255,0.06)' };
const filtersRowStyle = (isMobile) => ({
  display: 'flex',
  gap: 12,
  flexWrap: 'wrap',
  alignItems: isMobile ? 'stretch' : 'center',
  flexDirection: isMobile ? 'column' : 'row',
});
const searchInputStyle = { flex: 1, minWidth: 220, maxWidth: 420, boxSizing: 'border-box', borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff', fontSize: 14 };
const selectStyle = { borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff', fontSize: 14 };
const checkLabelStyle = { display: 'inline-flex', alignItems: 'center', gap: 8, color: '#f2e6e6', fontSize: 13, fontWeight: 700 };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = {
  display: 'grid',
  gridTemplateColumns: 'minmax(190px,1.6fr) repeat(6, minmax(110px,1fr)) repeat(2, minmax(100px,0.9fr))',
  minWidth: 1150,
  border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: 14,
  overflow: 'hidden',
};
const headStyle = { padding: '12px 12px', color: '#ffd0d0', fontSize: 11.5, letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 800, textAlign: 'center', display: 'grid', alignContent: 'center' };
const headProductoStyle = { background: 'rgba(255, 120, 120, 0.22)', textAlign: 'left' };
const headBaseStyle = { ...headStyle, background: 'rgba(255, 120, 120, 0.22)' };
const headResultStyle = { ...headStyle, background: 'rgba(255,255,255,0.07)', color: '#f2e6e6' };
const cellStyle = { padding: '14px 12px', borderTop: '1px solid rgba(255,255,255,0.08)', color: '#f2e6e6', display: 'grid', alignContent: 'center', justifyItems: 'center', textAlign: 'center', gap: 2 };
const cellProductoStyle = { justifyItems: 'start', textAlign: 'left' };
const rowFragmentStyle = { display: 'contents' };
const tagStyle = { marginLeft: 8, padding: '2px 8px', borderRadius: 999, background: 'rgba(120, 180, 255, 0.16)', color: '#9ecbff', fontSize: 10.5, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.04em' };
const tagMutedStyle = { ...tagStyle, background: 'rgba(255,255,255,0.08)', color: '#c8bbbb' };
const tagWarnStyle = { ...tagStyle, background: 'rgba(255, 200, 120, 0.16)', color: '#ffcf7d' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };
const summaryStyle = { color: '#c8bbbb', fontSize: 13 };
const printButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const detalleButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default AnalystMargenGananciaPage;

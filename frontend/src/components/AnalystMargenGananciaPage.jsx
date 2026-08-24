import { useCallback, useEffect, useState } from 'react';
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

const PRESETS = [
  { label: 'Hoy', get: () => ({ desde: todayIso(), hasta: todayIso() }) },
  { label: 'Ayer', get: () => ({ desde: yesterdayIso(), hasta: yesterdayIso() }) },
  { label: 'Esta semana', get: () => ({ desde: startOfWeekIso(), hasta: todayIso() }) },
  { label: 'Este mes', get: () => ({ desde: startOfMonthIso(), hasta: todayIso() }) },
  { label: 'Este año', get: () => ({ desde: startOfYearIso(), hasta: todayIso() }) },
];

function AnalystMargenGananciaPage({ isMobile, onBack }) {
  const tasaCambio = useExchangeRate();
  const [desde, setDesde] = useState(todayIso());
  const [hasta, setHasta] = useState(todayIso());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

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

  const applyPreset = (preset) => {
    const range = preset.get();
    setDesde(range.desde);
    setHasta(range.hasta);
  };

  const platos = data?.platos || [];
  const totales = data?.totales;

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
        <p style={subtitleStyle}>
          Ingreso, costo y ganancia de cada plato vendido en el rango de fechas elegido. El costo es el que
          quedó registrado al momento de cada venta; las marcadas como <em>costo estimado</em> son de antes de
          que existiera ese registro y usan el costo actual de la receta como aproximación.
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
            {desde === hasta ? `Ventas del ${desde}` : `Ventas del ${desde} al ${hasta}`}
          </div>

          {platos.length === 0 ? (
            <div style={emptyStyle}>No hay platos vendidos en este rango de fechas.</div>
          ) : (
            <div style={tableWrapStyle}>
              <div style={tableStyle}>
                <div style={headStyle}>Plato</div>
                <div style={headStyle}>Cant.</div>
                <div style={headStyle}>Ingreso</div>
                <div style={headStyle}>Costo</div>
                <div style={headStyle}>Ganancia</div>
                <div style={headStyle}>%</div>
                {platos.map((plato) => (
                  <div key={plato.producto_id} style={rowFragmentStyle}>
                    <div style={cellStyle}>
                      {plato.nombre}
                      {plato.categoria ? <span style={categoriaStyle}> · {plato.categoria}</span> : null}
                      {plato.costo_estimado ? (
                        <span style={estimadoBadgeStyle} title="Alguna venta de este plato es de antes de que se empezara a guardar el costo histórico; se usó el costo actual de la receta para esa parte.">
                          costo estimado
                        </span>
                      ) : null}
                    </div>
                    <div style={cellStyle}>{formatMonto(plato.cantidad_vendida)} {plato.unidad === 'kg' ? 'kg' : ''}</div>
                    <div style={cellStyle}>
                      ${formatMonto(plato.ingreso_total)}
                      <BsAmount amountUsd={plato.ingreso_total} tasa={tasaCambio} />
                    </div>
                    <div style={cellStyle}>
                      ${formatMonto(plato.costo_total)}
                      <BsAmount amountUsd={plato.costo_total} tasa={tasaCambio} />
                    </div>
                    <div style={{ ...cellStyle, color: Number(plato.ganancia_monto) >= 0 ? '#8fffb0' : '#ff9d9d', fontWeight: 700 }}>
                      ${formatMonto(plato.ganancia_monto)}
                    </div>
                    <div style={{ ...cellStyle, color: Number(plato.ganancia_pct) >= 0 ? '#8fffb0' : '#ff9d9d', fontWeight: 700 }}>
                      {formatMonto(plato.ganancia_pct)}%
                    </div>
                  </div>
                ))}
                <div style={{ ...cellStyle, fontWeight: 800 }}>Total</div>
                <div style={cellStyle} />
                <div style={{ ...cellStyle, fontWeight: 800 }}>${formatMonto(totales?.ingreso_total)}</div>
                <div style={{ ...cellStyle, fontWeight: 800 }}>${formatMonto(totales?.costo_total)}</div>
                <div style={{ ...cellStyle, fontWeight: 800, color: '#8fffb0' }}>${formatMonto(totales?.ganancia_monto)}</div>
                <div style={{ ...cellStyle, fontWeight: 800, color: '#8fffb0' }}>{formatMonto(totales?.ganancia_pct)}%</div>
              </div>
            </div>
          )}
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
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(200px,1.6fr) minmax(80px,0.7fr) minmax(120px,0.9fr) minmax(120px,0.9fr) minmax(110px,0.9fr) minmax(80px,0.6fr)', minWidth: 820, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(255,255,255,0.06)', color: '#ffb0b0', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '14px', borderTop: '1px solid rgba(255,255,255,0.08)', color: '#f2e6e6', display: 'grid', alignContent: 'center' };
const categoriaStyle = { color: '#c8bbbb', fontSize: 12 };
const estimadoBadgeStyle = {
  marginLeft: 8,
  padding: '2px 8px',
  borderRadius: 999,
  background: 'rgba(255, 200, 120, 0.16)',
  color: '#ffcf7d',
  fontSize: 10.5,
  fontWeight: 800,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
};
const rowFragmentStyle = { display: 'contents' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };
const printButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default AnalystMargenGananciaPage;

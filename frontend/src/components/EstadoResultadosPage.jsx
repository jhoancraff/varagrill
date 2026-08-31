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

function startOfMonthIso() {
  const now = new Date();
  return toIso(new Date(now.getFullYear(), now.getMonth(), 1));
}

function startOfYearIso() {
  const now = new Date();
  return toIso(new Date(now.getFullYear(), 0, 1));
}

function startOfWeekIso() {
  const now = new Date();
  const day = now.getDay();
  const diff = day === 0 ? 6 : day - 1;
  const monday = new Date(now);
  monday.setDate(now.getDate() - diff);
  return toIso(monday);
}

function formatMonto(value) {
  const number = Number(value || 0);
  return number.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const PRESETS = [
  { label: 'Esta semana', get: () => ({ desde: startOfWeekIso(), hasta: todayIso() }) },
  { label: 'Este mes', get: () => ({ desde: startOfMonthIso(), hasta: todayIso() }) },
  { label: 'Este año', get: () => ({ desde: startOfYearIso(), hasta: todayIso() }) },
];

function EstadoResultadosPage({ isMobile, onBack }) {
  const tasaCambio = useExchangeRate();
  const [desde, setDesde] = useState(startOfMonthIso());
  const [hasta, setHasta] = useState(todayIso());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadReport = useCallback(async (desdeConsultado, hastaConsultado) => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch(
        `/api/admin/reportes/estado-resultados/?desde=${desdeConsultado}&hasta=${hastaConsultado}`,
        { credentials: 'include', cache: 'no-store' },
      );
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cargar el estado de resultados.');
      }
      setData(json);
    } catch (requestError) {
      setError(requestError.message || 'No se pudo cargar el estado de resultados.');
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

  const utilidadNetaPositiva = data ? Number(data.utilidad_neta) >= 0 : true;

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
        <h2 style={titleStyle(isMobile)}>Estado de resultados</h2>
        <p style={subtitleStyle}>
          Ventas menos costo de ingredientes menos gastos operativos, para el rango de fechas que elijas —
          el número final te dice si el negocio ganó o perdió plata en ese período.
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
            {desde === hasta ? `Resultado del ${desde}` : `Resultado del ${desde} al ${hasta}`}
          </div>

          <div style={waterfallStyle}>
            <div style={lineRowStyle}>
              <span style={lineLabelStyle}>Ventas totales</span>
              <span style={lineValueStyle}>
                ${formatMonto(data.ventas_total)}
                <BsAmount amountUsd={data.ventas_total} bs={data.ventas_total_bs} tasa={tasaCambio} />
              </span>
            </div>
            <div style={lineRowStyle}>
              <span style={lineLabelStyle}>(−) Costo de ingredientes</span>
              <span style={{ ...lineValueStyle, color: '#ff9d9d' }}>
                −${formatMonto(data.costo_ingredientes_total)}
                <BsAmount amountUsd={data.costo_ingredientes_total} bs={data.costo_ingredientes_total_bs ?? undefined} tasa={tasaCambio} />
              </span>
            </div>
            <div style={subtotalRowStyle}>
              <span style={lineLabelStyle}>= Utilidad bruta</span>
              <span style={{ ...lineValueStyle, fontWeight: 800 }}>
                ${formatMonto(data.utilidad_bruta)}
                <BsAmount amountUsd={data.utilidad_bruta} bs={data.utilidad_bruta_bs ?? undefined} tasa={tasaCambio} />
              </span>
            </div>

            <div style={lineRowStyle}>
              <span style={lineLabelStyle}>(−) Gastos operativos</span>
              <span style={{ ...lineValueStyle, color: '#ff9d9d' }}>
                −${formatMonto(data.gastos_total)}
                <BsAmount amountUsd={data.gastos_total} bs={data.gastos_total_bs} tasa={tasaCambio} />
              </span>
            </div>

            {data.gastos_por_categoria.length > 0 ? (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, paddingLeft: 12 }}>
                {data.gastos_por_categoria.map((entry) => (
                  <span key={entry.categoria_nombre} style={categoriaChipStyle}>
                    {entry.categoria_nombre}: ${formatMonto(entry.total)}
                  </span>
                ))}
              </div>
            ) : null}

            <div style={finalRowStyle(utilidadNetaPositiva)}>
              <span style={{ ...lineLabelStyle, fontSize: 16, fontWeight: 800 }}>= Utilidad neta</span>
              <span style={{ fontSize: 22, fontWeight: 800, color: utilidadNetaPositiva ? '#8fffb0' : '#ff9d9d' }}>
                ${formatMonto(data.utilidad_neta)} ({formatMonto(data.utilidad_neta_pct)}%)
                <BsAmount amountUsd={data.utilidad_neta} bs={data.utilidad_neta_bs ?? undefined} tasa={tasaCambio} style={{ opacity: 0.85 }} />
              </span>
            </div>
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
  display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: isMobile ? 'stretch' : 'flex-end', flexDirection: isMobile ? 'column' : 'row',
});
const dateLabelStyle = { display: 'flex', flexDirection: 'column', gap: 6, color: '#f2e6e6', fontSize: 13, fontWeight: 700 };
const dateInputStyle = { borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff' };
const presetsWrapStyle = { display: 'flex', gap: 8, flexWrap: 'wrap' };
const presetButtonStyle = { border: '1px solid rgba(255,255,255,0.16)', borderRadius: 999, padding: '9px 14px', background: 'rgba(255,255,255,0.05)', color: '#fff', fontSize: 13, fontWeight: 700, cursor: 'pointer' };
const panelStyle = { display: 'grid', gap: 16, padding: 22, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const sectionTitleStyle = { color: '#fff', fontSize: 19, fontWeight: 700 };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };

const waterfallStyle = { display: 'grid', gap: 10, maxWidth: 560 };
const lineRowStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12 };
const subtotalRowStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12, padding: '8px 0', borderTop: '1px dashed rgba(255,255,255,0.15)', borderBottom: '1px dashed rgba(255,255,255,0.15)' };
const lineLabelStyle = { color: '#d2c3c3', fontSize: 14.5 };
const lineValueStyle = { color: '#fff', fontSize: 14.5, fontWeight: 600, whiteSpace: 'nowrap' };
const categoriaChipStyle = { display: 'inline-flex', padding: '4px 10px', borderRadius: 999, fontSize: 11.5, fontWeight: 700, color: '#c8bbbb', background: 'rgba(255,255,255,0.06)' };
const finalRowStyle = (positive) => ({
  display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12, marginTop: 4, padding: '14px 16px', borderRadius: 14,
  background: positive ? 'rgba(70, 200, 120, 0.12)' : 'rgba(255, 98, 98, 0.12)',
  border: positive ? '1px solid rgba(80, 200, 130, 0.3)' : '1px solid rgba(255, 145, 145, 0.3)',
});

const printButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default EstadoResultadosPage;

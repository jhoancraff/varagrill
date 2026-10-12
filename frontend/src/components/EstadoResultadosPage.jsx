import { useCallback, useEffect, useState } from 'react';
import BsAmount from './BsAmount';
import { RangoFechas } from './FiltroFechas';
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

function formatMonto(value) {
  const number = Number(value || 0);
  return number.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function EstadoResultadosPage({ isMobile, onBack, onNavigate }) {
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

  const utilidadNetaPositiva = data ? Number(data.utilidad_neta) >= 0 : true;
  const utilidadBrutaPositiva = data ? Number(data.utilidad_bruta) >= 0 : true;

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
      </div>

      <RangoFechas
        desde={desde}
        hasta={hasta}
        onChange={(rango) => {
          setDesde(rango.desde);
          setHasta(rango.hasta);
        }}
      />

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
              <span style={lineLabelStyle}>
                (−) Costo de ventas
                {onNavigate ? (
                  <button
                    type="button"
                    onClick={() => onNavigate('margen-ganancia')}
                    style={verDetalleGastosButtonStyle}
                    className="no-print"
                  >
                    Ver detalle →
                  </button>
                ) : null}
              </span>
              <span style={{ ...lineValueStyle, color: '#ff9d9d' }}>
                −${formatMonto(data.costo_ventas)}
                <BsAmount amountUsd={data.costo_ventas} bs={data.costo_ventas_bs} tasa={tasaCambio} />
              </span>
            </div>
            {Number(data.costo_lineas_estimadas) > 0 ? (
              <div style={avisoStyle}>
                {data.costo_lineas_estimadas} línea(s) vendida(s) no tienen el costo guardado al cobrar (ventas antiguas):
                para esas se usa el costo actual de la receta.
              </div>
            ) : null}

            <div style={subtotalRowStyle(utilidadBrutaPositiva)}>
              <span style={{ ...lineLabelStyle, fontWeight: 800 }}>= Utilidad bruta</span>
              <span style={{ fontSize: 17, fontWeight: 800, color: utilidadBrutaPositiva ? '#8fffb0' : '#ff9d9d', whiteSpace: 'nowrap' }}>
                ${formatMonto(data.utilidad_bruta)} ({formatMonto(data.utilidad_bruta_pct)}%)
                <BsAmount amountUsd={data.utilidad_bruta} bs={data.utilidad_bruta_bs ?? undefined} tasa={tasaCambio} style={{ opacity: 0.85 }} />
              </span>
            </div>

            <div style={lineRowStyle}>
              <span style={lineLabelStyle}>
                (−) Gastos operativos
                {onNavigate ? (
                  <button
                    type="button"
                    onClick={() => onNavigate('gastos-reporte')}
                    style={verDetalleGastosButtonStyle}
                    className="no-print"
                  >
                    Ver detalle →
                  </button>
                ) : null}
              </span>
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

            <div style={avisoStyle}>
              Las compras a proveedores (lotes) no se suman aquí: su costo ya está dentro del costo de ventas, que sale del costo
              de cada producto vendido. Lo que se les pagó se ve en Cuentas por pagar.
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
const panelStyle = { display: 'grid', gap: 16, padding: 22, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const sectionTitleStyle = { color: '#fff', fontSize: 19, fontWeight: 700 };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };

const waterfallStyle = { display: 'grid', gap: 10, maxWidth: 560 };
const lineRowStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12 };
const lineLabelStyle = { color: '#d2c3c3', fontSize: 14.5 };
const lineValueStyle = { color: '#fff', fontSize: 14.5, fontWeight: 600, whiteSpace: 'nowrap' };
const categoriaChipStyle = { display: 'inline-flex', padding: '4px 10px', borderRadius: 999, fontSize: 11.5, fontWeight: 700, color: '#c8bbbb', background: 'rgba(255,255,255,0.06)' };
const avisoStyle = { color: '#a89999', fontSize: 12.5, lineHeight: 1.5 };
const subtotalRowStyle = (positive) => ({
  display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12, padding: '10px 14px', borderRadius: 12,
  background: 'rgba(255,255,255,0.04)',
  border: positive ? '1px solid rgba(80, 200, 130, 0.22)' : '1px solid rgba(255, 145, 145, 0.25)',
});
const finalRowStyle = (positive) => ({
  display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12, marginTop: 4, padding: '14px 16px', borderRadius: 14,
  background: positive ? 'rgba(70, 200, 120, 0.12)' : 'rgba(255, 98, 98, 0.12)',
  border: positive ? '1px solid rgba(80, 200, 130, 0.3)' : '1px solid rgba(255, 145, 145, 0.3)',
});

const printButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const verDetalleGastosButtonStyle = { marginLeft: 10, border: 'none', background: 'transparent', color: '#ff9d9d', fontWeight: 700, fontSize: 12.5, cursor: 'pointer', padding: 0, textDecoration: 'underline' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default EstadoResultadosPage;

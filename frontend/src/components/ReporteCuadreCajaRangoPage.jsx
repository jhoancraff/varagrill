import { Fragment, useCallback, useEffect, useRef, useState } from 'react';
import { setRangoSeleccionado } from '../utils/fechaContabilidad';
import { RangoFechas } from './FiltroFechas';

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

function formatMonto(value) {
  const number = Number(value || 0);
  return number.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function ReporteCuadreCajaRangoPage({ isMobile, onBack, onNavigate }) {
  const [desde, setDesde] = useState(startOfWeekIso());
  const [hasta, setHasta] = useState(todayIso());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const requestIdRef = useRef(0);

  const loadReport = useCallback(async (desdeConsultado, hastaConsultado) => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setLoading(true);
    setError('');
    try {
      const response = await fetch(
        `/api/admin/reportes/cuadre-caja-rango/?desde=${desdeConsultado}&hasta=${hastaConsultado}`,
        { credentials: 'include', cache: 'no-store' },
      );
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cargar el cuadre de caja del rango.');
      }
      if (requestId !== requestIdRef.current) return;
      setData(json);
    } catch (requestError) {
      if (requestId !== requestIdRef.current) return;
      setError(requestError.message || 'No se pudo cargar el cuadre de caja del rango.');
      setData(null);
    } finally {
      if (requestId === requestIdRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (desde > hasta) return;
    loadReport(desde, hasta);
    // Igual que la fecha del cuadre diario (ver fechaContabilidad.js): al
    // entrar a uno de los 4 reportes de detalle desde aca, deben consultar
    // este mismo rango, y al volver aca (boton Volver) el rango elegido
    // debe seguir siendo el mismo en vez de reiniciar a la semana actual.
    setRangoSeleccionado(desde, hasta);
  }, [desde, hasta, loadReport]);

  const dias = data?.dias || [];
  const totalesPorMetodo = data?.totales_por_metodo || [];
  const diasCerrados = dias.filter((dia) => dia.cierre).length;
  const diasAbiertos = dias.length - diasCerrados;

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
        <h2 style={titleStyle(isMobile)}>Cuadre de caja por rango</h2>
      </div>

      <RangoFechas
        desde={desde}
        hasta={hasta}
        onChange={(rango) => {
          setDesde(rango.desde);
          setHasta(rango.hasta);
        }}
      />

      {loading ? <div style={emptyStyle}>Cargando cuadre de caja...</div> : null}
      {!loading && error ? <div style={noticeStyle}>{error}</div> : null}

      {!loading && !error && data ? (
        <>
          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Ventas del rango — {desde} al {hasta}</div>
            <div style={ventasGridStyle(isMobile)}>
              <div style={desgloseTileStyle}>
                <div style={desgloseLabelStyle}>Facturado</div>
                <div style={desgloseValueStyle}>${formatMonto(data.resumen_ventas?.total_vendido)}</div>
                <button
                  type="button"
                  onClick={() => onNavigate && onNavigate('contabilidad-ventas-dia')}
                  style={verDetalleLinkStyle}
                  className="no-print"
                >
                  Ver detalle →
                </button>
              </div>
              <div style={desgloseTileStyle}>
                <div style={desgloseLabelStyle}>Pendiente por cobrar</div>
                <div style={desgloseValueStyle}>${formatMonto(data.resumen_ventas?.total_pendiente)}</div>
                <button
                  type="button"
                  onClick={() => onNavigate && onNavigate('contabilidad-cuentas-por-cobrar-detalle')}
                  style={verDetalleLinkStyle}
                  className="no-print"
                >
                  Ver detalle →
                </button>
              </div>
              <div style={desgloseTileStyle}>
                <div style={desgloseLabelStyle}>Cuentas cobradas</div>
                <div style={desgloseValueStyle}>${formatMonto(data.resumen_ventas?.cuentas_cobradas_hoy)}</div>
                <div style={desgloseSecondaryStyle}>De fechas anteriores al rango</div>
                <button
                  type="button"
                  onClick={() => onNavigate && onNavigate('contabilidad-cuentas-cobradas-dia')}
                  style={verDetalleLinkStyle}
                  className="no-print"
                >
                  Ver detalle →
                </button>
              </div>
              <div style={desgloseTileStyle}>
                <div style={desgloseLabelStyle}>Propinas / excedentes</div>
                <div style={desgloseValueStyle}>${formatMonto(data.resumen_ventas?.total_propinas_excedentes)}</div>
                <div style={desgloseSecondaryStyle}>No cuenta como venta</div>
                <button
                  type="button"
                  onClick={() => onNavigate && onNavigate('contabilidad-propinas-dia')}
                  style={verDetalleLinkStyle}
                  className="no-print"
                >
                  Ver detalle →
                </button>
              </div>
              <div style={desgloseTileStyle}>
                <div style={desgloseLabelStyle}>Devoluciones</div>
                <div style={desgloseValueStyle}>${formatMonto(data.resumen_ventas?.total_devuelto)}</div>
                <div style={desgloseSecondaryStyle}>Notas de crédito emitidas</div>
                <button
                  type="button"
                  onClick={() => onNavigate && onNavigate('contabilidad-devoluciones')}
                  style={verDetalleLinkStyle}
                  className="no-print"
                >
                  Ver detalle →
                </button>
              </div>
            </div>
          </section>

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Desglose por moneda — rango completo</div>
            <div style={desgloseGridStyle(isMobile)}>
              <div style={desgloseTileStyle}>
                <div style={desgloseLabelStyle}>Bolívares · Físico</div>
                <div style={desgloseValueStyle}>
                  {data.desglose_caja?.bs_fisico?.total_bs !== null && data.desglose_caja?.bs_fisico?.total_bs !== undefined
                    ? `Bs. ${formatMonto(data.desglose_caja.bs_fisico.total_bs)}`
                    : '—'}
                </div>
                <div style={desgloseSecondaryStyle}>${formatMonto(data.desglose_caja?.bs_fisico?.total_usd)}</div>
              </div>
              <div style={desgloseTileStyle}>
                <div style={desgloseLabelStyle}>Bolívares · Bancos</div>
                <div style={desgloseValueStyle}>
                  {data.desglose_caja?.bs_digital?.total_bs !== null && data.desglose_caja?.bs_digital?.total_bs !== undefined
                    ? `Bs. ${formatMonto(data.desglose_caja.bs_digital.total_bs)}`
                    : '—'}
                </div>
                <div style={desgloseSecondaryStyle}>${formatMonto(data.desglose_caja?.bs_digital?.total_usd)}</div>
              </div>
              <div style={desgloseTileStyle}>
                <div style={desgloseLabelStyle}>Dólares · Físico</div>
                <div style={desgloseValueStyle}>${formatMonto(data.desglose_caja?.usd_fisico?.total_usd)}</div>
              </div>
              <div style={desgloseTileStyle}>
                <div style={desgloseLabelStyle}>Dólares · Digital</div>
                <div style={desgloseValueStyle}>${formatMonto(data.desglose_caja?.usd_digital?.total_usd)}</div>
              </div>
            </div>
          </section>

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>
              {desde === hasta ? `Resumen del ${desde}` : `Resumen del ${desde} al ${hasta}`} ({dias.length} día{dias.length === 1 ? '' : 's'})
            </div>
            <div style={statusRowStyle}>
              <span style={statusChipStyle(true)}>{diasCerrados} día(s) cerrado(s)</span>
              {diasAbiertos > 0 ? <span style={statusChipStyle(false)}>{diasAbiertos} día(s) sin cerrar</span> : null}
            </div>

            <div style={tableWrapStyle}>
              <div style={tableStyle}>
                <div style={headStyle}>Método</div>
                <div style={headStyle}>Total</div>
                {totalesPorMetodo.map((metodo) => (
                  <Fragment key={metodo.id}>
                    <div style={cellStyle}>
                      {metodo.nombre}{metodo.es_efectivo ? ' (efectivo)' : ''}
                    </div>
                    <div style={cellStyle}>
                      {metodo.moneda === 'VES' ? (
                        <>
                          Bs. {metodo.total_bs !== null ? formatMonto(metodo.total_bs) : '—'}
                          <span style={secondaryAmountStyle}> (${formatMonto(metodo.total)})</span>
                        </>
                      ) : (
                        <>${formatMonto(metodo.total)}</>
                      )}
                    </div>
                  </Fragment>
                ))}
                <div style={{ ...cellStyle, fontWeight: 800 }}>Total general</div>
                <div style={{ ...cellStyle, fontWeight: 800 }}>${formatMonto(data.total_general)}</div>
              </div>
            </div>
          </section>

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Efectivo del rango</div>
            <div style={{ display: 'grid', gap: 8, color: '#f2e6e6' }}>
              <div>Efectivo esperado (ventas − gastos en efectivo, sumado día por día): <strong>${formatMonto(data.efectivo_esperado)}</strong></div>
              <div>Total consignado en el rango: <strong>${formatMonto(data.total_consignado)}</strong></div>
              {Number(data.gastos_efectivo) > 0 ? (
                <div style={{ color: '#ff9d9d' }}>Gastos pagados en efectivo en el rango: −${formatMonto(data.gastos_efectivo)}</div>
              ) : null}
            </div>
          </section>

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Desglose día por día</div>
            <div style={tableWrapStyle}>
              <div style={diasTableStyle}>
                <div style={headStyle}>Fecha</div>
                <div style={headStyle}>Total del día</div>
                <div style={headStyle}>Consignado</div>
                <div style={headStyle}>Estado</div>
                {dias.map((dia) => (
                  <Fragment key={dia.fecha}>
                    <div style={cellStyle}>{dia.fecha}</div>
                    <div style={cellStyle}>${formatMonto(dia.total_general)}</div>
                    <div style={cellStyle}>${formatMonto(dia.total_consignado)}</div>
                    <div style={cellStyle}>
                      {dia.cierre ? (
                        <span style={statusChipStyle(true)}>
                          Cerrado{Number(dia.cierre.diferencia) !== 0 ? ` (dif. $${formatMonto(dia.cierre.diferencia)})` : ''}
                        </span>
                      ) : (
                        <span style={statusChipStyle(false)}>Sin cerrar</span>
                      )}
                    </div>
                  </Fragment>
                ))}
              </div>
            </div>
          </section>
        </>
      ) : null}
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: '#d2c3c3', maxWidth: 680, lineHeight: 1.6 };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const sectionTitleStyle = { color: '#fff', fontSize: 19, fontWeight: 700 };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };
const statusRowStyle = { display: 'flex', gap: 8, flexWrap: 'wrap' };
const statusChipStyle = (closed) => ({
  display: 'inline-flex', alignItems: 'center', padding: '4px 10px', borderRadius: 999,
  fontSize: 12, fontWeight: 700,
  color: closed ? '#8fffb0' : '#ffcf7d',
  background: closed ? 'rgba(70,200,120,0.14)' : 'rgba(255,190,120,0.14)',
  border: closed ? '1px solid rgba(80,200,130,0.3)' : '1px solid rgba(255,190,120,0.3)',
});
const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(180px,1fr) minmax(140px,1fr)', minWidth: 320, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const diasTableStyle = { display: 'grid', gridTemplateColumns: 'minmax(110px,0.8fr) minmax(120px,0.8fr) minmax(120px,0.8fr) minmax(160px,1fr)', minWidth: 620, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(255,255,255,0.06)', color: '#ffb0b0', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '14px', borderTop: '1px solid rgba(255,255,255,0.08)', color: '#f2e6e6', display: 'grid', alignContent: 'center' };
const secondaryAmountStyle = { color: '#c8bbbb', fontSize: 12, marginLeft: 6 };
const desgloseGridStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)', gap: 10 });
const ventasGridStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)', gap: 10 });
const verDetalleLinkStyle = { border: 'none', background: 'none', color: '#ff9d9d', fontSize: 12, fontWeight: 700, cursor: 'pointer', padding: 0, textAlign: 'left', width: 'fit-content' };
const desgloseTileStyle = { display: 'grid', gap: 4, padding: '14px 16px', borderRadius: 14, border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.03)' };
const desgloseLabelStyle = { color: '#ffb0b0', fontSize: 11.5, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' };
const desgloseValueStyle = { color: '#fff', fontSize: 20, fontWeight: 800 };
const desgloseSecondaryStyle = { color: '#c8bbbb', fontSize: 12.5 };
const printButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default ReporteCuadreCajaRangoPage;

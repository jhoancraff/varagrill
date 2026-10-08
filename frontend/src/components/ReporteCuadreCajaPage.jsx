import { Fragment, useCallback, useEffect, useState } from 'react';
import { getFechaSeleccionada, setFechaSeleccionada } from '../utils/fechaContabilidad';
import { ESTADO_LOTE_ESTILO } from '../utils/lotesPos';

function todayIso() {
  const now = new Date();
  const offset = now.getTimezoneOffset();
  const local = new Date(now.getTime() - offset * 60000);
  return local.toISOString().slice(0, 10);
}

function formatMonto(value) {
  const number = Number(value || 0);
  return number.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function ReporteCuadreCajaPage({ isMobile, onBack, onNavigate, backLabel = '← Volver a Contabilidad' }) {
  const [fecha, setFecha] = useState(() => getFechaSeleccionada(todayIso()));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');

  const loadReport = useCallback(async (fechaConsultada) => {
    setLoading(true);
    setMessage('');
    try {
      const response = await fetch(`/api/admin/reportes/cuadre-caja/?fecha=${fechaConsultada}`, {
        credentials: 'include',
        cache: 'no-store',
      });
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cargar el cuadre de caja.');
      }
      setData(json);
    } catch (error) {
      setMessage(error.message || 'No se pudo cargar el cuadre de caja.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadReport(fecha);
    setFechaSeleccionada(fecha);
  }, [fecha, loadReport]);

  const cierre = data?.cierre || null;
  const totalesPorMetodo = data?.totales_por_metodo || [];
  const pos = data?.pos || null;

  return (
    <section style={containerStyle(isMobile)}>
      <div className="no-print" style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          {backLabel}
        </button>
        <button type="button" onClick={() => window.print()} style={printButtonStyle}>
          Imprimir / Guardar PDF
        </button>
      </div>

      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Cuadre de caja diario</h2>
        </div>
        <label className="no-print" style={dateLabelStyle}>
          Fecha
          <input
            type="date"
            value={fecha}
            max={todayIso()}
            onChange={(event) => setFecha(event.target.value)}
            style={dateInputStyle}
          />
        </label>
      </div>

      {message ? <div style={noticeStyle} className="no-print">{message}</div> : null}

      {loading ? <div style={emptyStyle}>Cargando cuadre de caja...</div> : null}

      {!loading && data ? (
        <>
          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Ventas del día — {fecha}</div>
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
                <div style={desgloseLabelStyle}>Cuentas cobradas hoy</div>
                <div style={desgloseValueStyle}>${formatMonto(data.resumen_ventas?.cuentas_cobradas_hoy)}</div>
                <div style={desgloseSecondaryStyle}>Pendiente de días anteriores</div>
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
            <div style={sectionTitleStyle}>Desglose por moneda — {fecha}</div>
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
            {!data.tasa_bcv ? (
              <div style={{ fontSize: 12, color: '#ffcf85' }}>
                No hay tasa BCV registrada para esta fecha; los montos en bolívares no se pueden convertir.
              </div>
            ) : null}
          </section>

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Totales por metodo de pago — {fecha}</div>
            {data.tasa_bcv ? (
              <div style={{ fontSize: 12, color: '#c8bbbb' }}>Tasa BCV usada: Bs. {formatMonto(data.tasa_bcv)} / $</div>
            ) : (
              <div style={{ fontSize: 12, color: '#ffcf85' }}>No hay tasa BCV registrada para esta fecha; los metodos en bolivares no muestran conversion.</div>
            )}
            <div style={tableWrapStyle}>
              <div style={tableStyle}>
                <div style={headStyle}>Metodo</div>
                <div style={headStyle}>Total</div>
                {totalesPorMetodo.map((metodo) => (
                  <Fragment key={metodo.id}>
                    <div style={cellStyle}>
                      {metodo.nombre}{metodo.es_efectivo ? ' (efectivo)' : ''}
                      {metodo.cuenta_bancaria ? (
                        <div style={secondaryAmountStyle}>Banco: {metodo.cuenta_bancaria}</div>
                      ) : null}
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
                      {Number(metodo.ingresos_extra) > 0 ? (
                        <div style={secondaryAmountStyle}>
                          incluye ${formatMonto(metodo.ingresos_extra)} en propinas/extra
                        </div>
                      ) : null}
                    </div>
                  </Fragment>
                ))}
                <div style={{ ...cellStyle, fontWeight: 800 }}>Total general</div>
                <div style={{ ...cellStyle, fontWeight: 800 }}>${formatMonto(data.total_general)}</div>
              </div>
            </div>
          </section>

          {pos ? (
            <section style={panelStyle}>
              <div style={sectionTitleStyle}>Puntos de venta — {fecha}</div>
              {pos.lotes_dia.length === 0 ? (
                <div style={emptyStyle}>Sin lotes de punto de venta este día.</div>
              ) : (
                <div style={tableWrapStyle}>
                  <div style={posTableStyle}>
                    <div style={headStyle}>Lote</div>
                    <div style={headStyle}>Método</div>
                    <div style={headStyle}>Monto</div>
                    <div style={headStyle}>Estado</div>
                    {pos.lotes_dia.map((lote) => (
                      <Fragment key={lote.id}>
                        <div style={cellStyle}>{lote.codigo}</div>
                        <div style={cellStyle}>{lote.metodo_pago_nombre}</div>
                        <div style={cellStyle}>${formatMonto(lote.monto_usd)}</div>
                        <div style={cellStyle}>
                          <span style={{ ...posBadgeStyle, ...(ESTADO_LOTE_ESTILO[lote.estado] || {}) }}>{lote.estado_label}</span>
                        </div>
                      </Fragment>
                    ))}
                  </div>
                </div>
              )}
              {onNavigate ? (
                <button type="button" className="no-print" onClick={() => onNavigate('contabilidad-lotes-pos')} style={verDetalleLinkStyle}>
                  Ver todos los lotes →
                </button>
              ) : null}
            </section>
          ) : null}

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Cierre del dia</div>
            {Number(data.gastos_efectivo_dia) > 0 ? (
              <div style={{ color: '#ff9d9d', fontSize: 13 }}>
                Gastos pagados en efectivo hoy: −${formatMonto(data.gastos_efectivo_dia)}
              </div>
            ) : null}
            <div style={{ color: '#c8bbbb', fontSize: 13 }}>
              Efectivo esperado (ventas + propinas/extra − gastos, todo en efectivo): <strong style={{ color: '#fff' }}>${formatMonto(cierre ? cierre.efectivo_esperado : data.efectivo_esperado_preview)}</strong>
            </div>
            {cierre ? (
              <div style={{ display: 'grid', gap: 8, color: '#f2e6e6' }}>
                <div style={{ color: '#8fffb0', fontWeight: 800 }}>La caja de este día ya está cerrada.</div>
                {cierre.conteo_efectivo_realizado ? (
                  <>
                    <div>Efectivo contado al cerrar: <strong>${formatMonto(cierre.efectivo_contado_final)}</strong></div>
                    <div style={{ color: Number(cierre.diferencia) === 0 ? '#8fffb0' : '#ff9d9d', fontWeight: 800 }}>
                      Diferencia: ${formatMonto(cierre.diferencia)}
                    </div>
                  </>
                ) : null}
                {pos ? <div>POS por acreditar al cerrar: <strong>${formatMonto(cierre.pos_por_acreditar_usd)}</strong></div> : null}
                {cierre.notas ? <div>Notas: {cierre.notas}</div> : null}
                <div style={{ fontSize: 13, color: '#c8bbbb' }}>
                  Cerrado por {cierre.cerrado_por || '—'} el {new Date(cierre.fecha_creacion).toLocaleString('es-VE')}
                </div>
              </div>
            ) : (
              <div className="no-print">
                <button
                  type="button"
                  onClick={() => onNavigate && onNavigate('contabilidad-cierre-caja')}
                  style={dangerButtonStyle}
                >
                  Cerrar caja →
                </button>
              </div>
            )}
          </section>
        </>
      ) : null}
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const headerRowStyle = (isMobile) => ({ display: 'flex', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center', flexDirection: isMobile ? 'column' : 'row', gap: 12 });
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: '#d2c3c3' };
const dateLabelStyle = { display: 'flex', flexDirection: 'column', gap: 6, color: '#f2e6e6', fontSize: 13, fontWeight: 700 };
const dateInputStyle = { borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff' };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const sectionTitleStyle = { color: '#fff', fontSize: 19, fontWeight: 700 };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(180px,1fr) minmax(140px,1fr)', minWidth: 320, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(255,255,255,0.06)', color: '#ffb0b0', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '14px', borderTop: '1px solid rgba(255,255,255,0.08)', color: '#f2e6e6', display: 'grid', alignContent: 'center' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };
const secondaryAmountStyle = { color: '#c8bbbb', fontSize: 12, marginLeft: 6 };
const desgloseGridStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)', gap: 10 });
const ventasGridStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)', gap: 10 });
const desgloseTileStyle = { display: 'grid', gap: 4, padding: '14px 16px', borderRadius: 14, border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.03)' };
const desgloseLabelStyle = { color: '#ffb0b0', fontSize: 11.5, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' };
const desgloseValueStyle = { color: '#fff', fontSize: 20, fontWeight: 800 };
const desgloseSecondaryStyle = { color: '#c8bbbb', fontSize: 12.5 };
const verDetalleLinkStyle = { border: 'none', background: 'none', color: '#ff9d9d', fontSize: 12, fontWeight: 700, cursor: 'pointer', padding: 0, textAlign: 'left', width: 'fit-content' };
const posTableStyle = { display: 'grid', gridTemplateColumns: 'minmax(110px,0.8fr) minmax(150px,1fr) minmax(120px,0.8fr) minmax(130px,0.8fr)', minWidth: 520, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const posBadgeStyle = { fontSize: 11, fontWeight: 800, padding: '3px 10px', borderRadius: 999, textTransform: 'uppercase', letterSpacing: '0.04em', width: 'fit-content' };
const dangerButtonStyle = { border: '1px solid rgba(255,126,126,0.4)', borderRadius: 999, padding: '12px 16px', background: 'rgba(145,33,33,0.35)', color: '#ffd3d3', fontWeight: 700, cursor: 'pointer' };
const printButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default ReporteCuadreCajaPage;

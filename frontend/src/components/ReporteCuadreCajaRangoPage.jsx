import { Fragment, useCallback, useEffect, useState } from 'react';

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

function startOfWeekIso() {
  const now = new Date();
  const day = now.getDay();
  const diff = day === 0 ? 6 : day - 1;
  const monday = new Date(now);
  monday.setDate(now.getDate() - diff);
  return toIso(monday);
}

function sevenDaysAgoIso() {
  const now = new Date();
  now.setDate(now.getDate() - 6);
  return toIso(now);
}

function formatMonto(value) {
  const number = Number(value || 0);
  return number.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const PRESETS = [
  { label: 'Últimos 7 días', get: () => ({ desde: sevenDaysAgoIso(), hasta: todayIso() }) },
  { label: 'Esta semana', get: () => ({ desde: startOfWeekIso(), hasta: todayIso() }) },
  { label: 'Este mes', get: () => ({ desde: startOfMonthIso(), hasta: todayIso() }) },
];

function ReporteCuadreCajaRangoPage({ isMobile, onBack }) {
  const [desde, setDesde] = useState(startOfWeekIso());
  const [hasta, setHasta] = useState(todayIso());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadReport = useCallback(async (desdeConsultado, hastaConsultado) => {
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
      setData(json);
    } catch (requestError) {
      setError(requestError.message || 'No se pudo cargar el cuadre de caja del rango.');
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
        <p style={subtitleStyle}>
          Suma el mismo cuadre diario a lo largo de varios días — útil para revisar una semana o un mes de
          una vez. El cierre físico de efectivo sigue siendo por día individual, así que abajo se indica
          cuáles días del rango ya están cerrados y cuáles todavía no.
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

      {loading ? <div style={emptyStyle}>Cargando cuadre de caja...</div> : null}
      {!loading && error ? <div style={noticeStyle}>{error}</div> : null}

      {!loading && !error && data ? (
        <>
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
                <div style={desgloseLabelStyle}>Bolívares · Digital</div>
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
            <div style={sectionTitleStyle}>Propinas y pagos extra del rango</div>
            {(data.ingresos_extra_rango || []).length === 0 ? (
              <div style={emptyStyle}>No se registró ninguna propina ni pago extra en este rango.</div>
            ) : (
              <div style={tableWrapStyle}>
                <div style={ingresoExtraTableStyle}>
                  <div style={headStyle}>Fecha</div>
                  <div style={headStyle}>Tipo</div>
                  <div style={headStyle}>Monto</div>
                  <div style={headStyle}>Cuenta</div>
                  <div style={headStyle}>Registrado por</div>
                  <div style={headStyle}>Descripción</div>
                  {data.ingresos_extra_rango.map((item) => (
                    <Fragment key={item.id}>
                      <div style={cellStyle}>{new Date(item.fecha_creacion).toLocaleDateString('es-VE')}</div>
                      <div style={cellStyle}>{item.tipo_label}</div>
                      <div style={cellStyle}>
                        {item.moneda === 'VES' ? (
                          <>
                            Bs. {formatMonto(Number(item.monto) * Number(item.tasa_cambio_referencia || 0))}
                            <span style={secondaryAmountStyle}> (${formatMonto(item.monto)})</span>
                          </>
                        ) : (
                          <>${formatMonto(item.monto)}</>
                        )}
                      </div>
                      <div style={cellStyle}>{item.metodo_pago_nombre}</div>
                      <div style={cellStyle}>{item.registrado_por || '—'}</div>
                      <div style={cellStyle}>{item.descripcion || '—'}</div>
                    </Fragment>
                  ))}
                </div>
              </div>
            )}
            <div style={{ fontWeight: 700, color: '#fff' }}>
              Total propinas/extra: ${formatMonto(data.total_ingresos_extra_rango)}
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
const filtersRowStyle = (isMobile) => ({
  display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: isMobile ? 'stretch' : 'flex-end', flexDirection: isMobile ? 'column' : 'row',
});
const dateLabelStyle = { display: 'flex', flexDirection: 'column', gap: 6, color: '#f2e6e6', fontSize: 13, fontWeight: 700 };
const dateInputStyle = { borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff' };
const presetsWrapStyle = { display: 'flex', gap: 8, flexWrap: 'wrap' };
const presetButtonStyle = { border: '1px solid rgba(255,255,255,0.16)', borderRadius: 999, padding: '9px 14px', background: 'rgba(255,255,255,0.05)', color: '#fff', fontSize: 13, fontWeight: 700, cursor: 'pointer' };
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
const ingresoExtraTableStyle = { display: 'grid', gridTemplateColumns: 'minmax(100px,0.6fr) minmax(100px,0.7fr) minmax(90px,0.6fr) minmax(170px,1fr) minmax(140px,0.9fr) minmax(160px,1.2fr)', minWidth: 900, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(255,255,255,0.06)', color: '#ffb0b0', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '14px', borderTop: '1px solid rgba(255,255,255,0.08)', color: '#f2e6e6', display: 'grid', alignContent: 'center' };
const secondaryAmountStyle = { color: '#c8bbbb', fontSize: 12, marginLeft: 6 };
const desgloseGridStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)', gap: 10 });
const desgloseTileStyle = { display: 'grid', gap: 4, padding: '14px 16px', borderRadius: 14, border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.03)' };
const desgloseLabelStyle = { color: '#ffb0b0', fontSize: 11.5, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' };
const desgloseValueStyle = { color: '#fff', fontSize: 20, fontWeight: 800 };
const desgloseSecondaryStyle = { color: '#c8bbbb', fontSize: 12.5 };
const printButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default ReporteCuadreCajaRangoPage;

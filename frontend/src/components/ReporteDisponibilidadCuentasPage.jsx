import { Fragment, useCallback, useEffect, useState } from 'react';

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

function ReporteDisponibilidadCuentasPage({ isMobile, onBack }) {
  const [fecha, setFecha] = useState(todayIso());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadReport = useCallback(async (fechaConsultada) => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch(`/api/admin/reportes/disponibilidad-cuentas/?fecha=${fechaConsultada}`, {
        credentials: 'include',
        cache: 'no-store',
      });
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cargar la disponibilidad de las cuentas.');
      }
      setData(json);
    } catch (requestError) {
      setError(requestError.message || 'No se pudo cargar la disponibilidad de las cuentas.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadReport(fecha);
  }, [fecha, loadReport]);

  const cuentas = data?.cuentas || [];

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

      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Disponibilidad por cuenta</h2>
          <p style={subtitleStyle}>
            Saldo acumulado de cada método de pago hasta la fecha elegida: todo lo cobrado con esa cuenta
            menos lo pagado con ella a gastos y proveedores — como un estado de cuenta que puedes consultar
            en cualquier día.
          </p>
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

      {loading ? <div style={emptyStyle}>Cargando disponibilidad...</div> : null}
      {!loading && error ? <div style={noticeStyle}>{error}</div> : null}

      {!loading && !error && data ? (
        <>
          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Saldo por cuenta — al {fecha}</div>
            {data.tasa_bcv ? (
              <div style={{ fontSize: 12, color: '#c8bbbb' }}>Tasa BCV usada: Bs. {formatMonto(data.tasa_bcv)} / $</div>
            ) : (
              <div style={{ fontSize: 12, color: '#ffcf85' }}>No hay tasa BCV registrada para esta fecha; las cuentas en bolívares no muestran conversión.</div>
            )}

            <div style={cuentasGridStyle(isMobile)}>
              {cuentas.map((cuenta) => (
                <article key={cuenta.id} style={cuentaCardStyle(Number(cuenta.saldo_disponible) < 0)}>
                  <div style={cuentaHeaderStyle}>
                    <div style={cuentaNombreStyle}>
                      {cuenta.nombre}
                      {!cuenta.activo ? <span style={inactivaBadgeStyle}>Inactiva</span> : null}
                    </div>
                    {cuenta.es_efectivo ? <span style={efectivoBadgeStyle}>Efectivo</span> : null}
                  </div>
                  <div style={cuentaSaldoStyle(Number(cuenta.saldo_disponible) < 0)}>
                    {cuenta.moneda === 'VES' ? (
                      <>
                        Bs. {cuenta.saldo_disponible_bs !== null ? formatMonto(cuenta.saldo_disponible_bs) : '—'}
                        <span style={secondaryAmountStyle}> (${formatMonto(cuenta.saldo_disponible)})</span>
                      </>
                    ) : (
                      <>${formatMonto(cuenta.saldo_disponible)}</>
                    )}
                  </div>
                  <div style={cuentaDetalleStyle}>
                    <span>+${formatMonto(cuenta.ingresos_acumulados)} cobrado</span>
                    {Number(cuenta.ingresos_extra_acumulados) > 0 ? (
                      <span>+${formatMonto(cuenta.ingresos_extra_acumulados)} propinas/extra</span>
                    ) : null}
                    <span>−${formatMonto(cuenta.gastos_acumulados)} gastos</span>
                    <span>−${formatMonto(cuenta.compras_acumuladas)} proveedores</span>
                    {Number(cuenta.consignado_acumulado) > 0 ? (
                      <span>−${formatMonto(cuenta.consignado_acumulado)} consignado</span>
                    ) : null}
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Detalle por cuenta</div>
            <div style={tableWrapStyle}>
              <div style={tableStyle}>
                <div style={headStyle}>Cuenta</div>
                <div style={headStyle}>Cobrado</div>
                <div style={headStyle}>Propinas/extra</div>
                <div style={headStyle}>Gastos</div>
                <div style={headStyle}>Proveedores</div>
                <div style={headStyle}>Consignado</div>
                <div style={headStyle}>Saldo disponible</div>
                {cuentas.map((cuenta) => (
                  <Fragment key={cuenta.id}>
                    <div style={cellStyle}>{cuenta.nombre}{cuenta.es_efectivo ? ' (efectivo)' : ''}</div>
                    <div style={cellStyle}>${formatMonto(cuenta.ingresos_acumulados)}</div>
                    <div style={cellStyle}>${formatMonto(cuenta.ingresos_extra_acumulados)}</div>
                    <div style={cellStyle}>${formatMonto(cuenta.gastos_acumulados)}</div>
                    <div style={cellStyle}>${formatMonto(cuenta.compras_acumuladas)}</div>
                    <div style={cellStyle}>${formatMonto(cuenta.consignado_acumulado)}</div>
                    <div style={{ ...cellStyle, fontWeight: 800, color: Number(cuenta.saldo_disponible) < 0 ? '#ff9d9d' : '#8fffb0' }}>
                      ${formatMonto(cuenta.saldo_disponible)}
                    </div>
                  </Fragment>
                ))}
                <div style={{ ...cellStyle, fontWeight: 800 }}>Total disponible</div>
                <div style={cellStyle} />
                <div style={cellStyle} />
                <div style={cellStyle} />
                <div style={cellStyle} />
                <div style={cellStyle} />
                <div style={{ ...cellStyle, fontWeight: 800 }}>${formatMonto(data.total_disponible)}</div>
              </div>
            </div>
          </section>
        </>
      ) : null}
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const headerRowStyle = (isMobile) => ({ display: 'flex', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center', flexDirection: isMobile ? 'column' : 'row', gap: 12 });
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: '#d2c3c3', maxWidth: 680, lineHeight: 1.6 };
const dateLabelStyle = { display: 'flex', flexDirection: 'column', gap: 6, color: '#f2e6e6', fontSize: 13, fontWeight: 700 };
const dateInputStyle = { borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff' };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const sectionTitleStyle = { color: '#fff', fontSize: 19, fontWeight: 700 };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };

const cuentasGridStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fill, minmax(240px, 1fr))', gap: 12 });
const cuentaCardStyle = (negativo) => ({
  display: 'grid', gap: 8, padding: '16px 18px', borderRadius: 16,
  border: negativo ? '1px solid rgba(255, 145, 145, 0.3)' : '1px solid rgba(255,255,255,0.1)',
  background: negativo ? 'rgba(255, 98, 98, 0.08)' : 'rgba(255,255,255,0.03)',
});
const cuentaHeaderStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 };
const cuentaNombreStyle = { color: '#fff', fontWeight: 700, fontSize: 15, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' };
const inactivaBadgeStyle = { fontSize: 10.5, fontWeight: 800, color: '#c8bbbb', background: 'rgba(255,255,255,0.08)', padding: '2px 8px', borderRadius: 999, textTransform: 'uppercase', letterSpacing: '0.04em' };
const efectivoBadgeStyle = { fontSize: 10.5, fontWeight: 800, color: '#bdf0cf', background: 'rgba(70,200,120,0.14)', padding: '2px 8px', borderRadius: 999, textTransform: 'uppercase', letterSpacing: '0.04em', whiteSpace: 'nowrap' };
const cuentaSaldoStyle = (negativo) => ({ fontSize: 22, fontWeight: 800, color: negativo ? '#ff9d9d' : '#fff' });
const cuentaDetalleStyle = { display: 'flex', flexDirection: 'column', gap: 2, color: '#c8bbbb', fontSize: 12.5 };
const secondaryAmountStyle = { color: '#c8bbbb', fontSize: 13, marginLeft: 6, fontWeight: 600 };

const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(160px,1.1fr) minmax(110px,0.8fr) minmax(120px,0.8fr) minmax(100px,0.7fr) minmax(120px,0.8fr) minmax(110px,0.7fr) minmax(140px,0.9fr)', minWidth: 940, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(255,255,255,0.06)', color: '#ffb0b0', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '14px', borderTop: '1px solid rgba(255,255,255,0.08)', color: '#f2e6e6', display: 'grid', alignContent: 'center' };

const printButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default ReporteDisponibilidadCuentasPage;

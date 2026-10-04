import { Fragment, useCallback, useEffect, useState } from 'react';
import TransferenciaCuentasModal from './TransferenciaCuentasModal';
import IngresoParcialModal from './IngresoParcialModal';
import Toast from './Toast';
import useToast from '../hooks/useToast';

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

function ReporteDisponibilidadCuentasPage({ isMobile, onBack, onNavigate }) {
  const [fecha, setFecha] = useState(todayIso());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [modalTransferenciaAbierto, setModalTransferenciaAbierto] = useState(false);
  const [modalIngresoAbierto, setModalIngresoAbierto] = useState(false);
  const [ingresoSubmitting, setIngresoSubmitting] = useState(false);
  const { toast, showSuccess, showError, hideToast } = useToast();

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

  const handleRegistrarIngresoParcial = async ({ monto, descripcion, metodoPagoId }) => {
    setIngresoSubmitting(true);
    try {
      const response = await fetch('/api/contabilidad/ingresos-extra/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          tipo: 'ingreso_no_facturado',
          monto,
          descripcion,
          metodo_pago_id: Number(metodoPagoId),
        }),
      });
      const json = await response.json().catch(() => ({}));
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo registrar el ingreso.');
      }
      setModalIngresoAbierto(false);
      showSuccess(json.message || 'Ingreso registrado correctamente.');
      loadReport(fecha);
    } catch (requestError) {
      showError(requestError.message || 'No se pudo registrar el ingreso.');
    } finally {
      setIngresoSubmitting(false);
    }
  };

  const cuentas = data?.cuentas || [];
  const bancos = data?.bancos || [];
  const hayPuntoVenta = bancos.some((banco) => banco.tiene_punto_venta);
  const transitorio = data?.pos_por_cobrar || null;

  return (
    <section style={containerStyle(isMobile)}>
      <Toast toast={toast} onClose={hideToast} />

      <div className="no-print" style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          ← Volver a Contabilidad
        </button>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <select
            value=""
            onChange={(event) => {
              const accion = event.target.value;
              if (accion === 'nueva') setModalTransferenciaAbierto(true);
              else if (accion === 'historial' && onNavigate) onNavigate('contabilidad-historial-transferencias');
            }}
            style={accionSelectStyle('transferencia')}
          >
            <option value="" disabled>⇄ Transferencias</option>
            <option value="nueva">+ Nueva transferencia</option>
            {onNavigate ? <option value="historial">Ver historial</option> : null}
          </select>

          <select
            value=""
            onChange={(event) => {
              const accion = event.target.value;
              if (accion === 'nuevo') setModalIngresoAbierto(true);
              else if (accion === 'historial' && onNavigate) onNavigate('contabilidad-historial-ingresos-no-facturados');
            }}
            style={accionSelectStyle('ingreso')}
          >
            <option value="" disabled>+ Ingresos parciales</option>
            <option value="nuevo">+ Registrar ingreso</option>
            {onNavigate ? <option value="historial">Ver historial</option> : null}
          </select>

          <button type="button" onClick={() => window.print()} style={printButtonStyle}>
            Imprimir / Guardar PDF
          </button>
        </div>
      </div>

      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Disponibilidad diaria</h2>
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

            {hayPuntoVenta ? (
              <div style={{ fontSize: 12, color: '#c8bbbb' }}>
                En los puntos de venta, el saldo disponible solo cuenta los lotes ya acreditados; lo demás está por acreditar.
              </div>
            ) : null}

            <div style={cuentasGridStyle(isMobile)}>
              {bancos.map((banco) => (
                <article key={banco.nombre} style={cuentaCardStyle(Number(banco.saldo_disponible) < 0)}>
                  <div style={cuentaHeaderStyle}>
                    <div style={cuentaNombreStyle}>
                      {banco.nombre}
                      {!banco.agrupado && !banco.metodos[0].activo ? <span style={inactivaBadgeStyle}>Inactiva</span> : null}
                      {banco.agrupado ? <span style={efectivoBadgeStyle}>{banco.metodos.length} métodos</span> : null}
                      {banco.moneda_mixta ? <span style={inactivaBadgeStyle}>Monedas mixtas</span> : null}
                    </div>
                  </div>
                  <div style={cuentaSaldoStyle(Number(banco.saldo_disponible) < 0)}>
                    {banco.moneda === 'VES' ? (
                      <>
                        Bs. {banco.saldo_disponible_bs !== null ? formatMonto(banco.saldo_disponible_bs) : '—'}
                        <span style={secondaryAmountStyle}> (${formatMonto(banco.saldo_disponible)})</span>
                      </>
                    ) : (
                      <>${formatMonto(banco.saldo_disponible)}</>
                    )}
                  </div>
                  {banco.tiene_punto_venta ? (
                    <div style={porAcreditarBoxStyle}>
                      <div style={{ fontWeight: 800, color: '#ffe3a3' }}>
                        Por acreditar: {banco.moneda === 'VES' ? `Bs. ${formatMonto(banco.por_acreditar_bs)} ` : ''}
                        <span style={secondaryAmountStyle}>(${formatMonto(banco.por_acreditar_usd)})</span>
                      </div>
                      <div>{banco.lotes_por_acreditar.length} lote(s) sin acreditar</div>
                    </div>
                  ) : null}
                  {banco.agrupado ? (
                    <div style={metodosAnidadosStyle}>
                      {banco.metodos.map((metodo) => (
                        <div key={metodo.id} style={metodoAnidadoRowStyle}>
                          <span>
                            {metodo.nombre}
                            {!metodo.activo ? <span style={inactivaBadgeStyle}> Inactiva</span> : null}
                          </span>
                          <span>
                            {metodo.moneda === 'VES'
                              ? `Bs. ${metodo.saldo_disponible_bs !== null ? formatMonto(metodo.saldo_disponible_bs) : '—'}`
                              : `$${formatMonto(metodo.saldo_disponible)}`}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={cuentaDetalleStyle}>
                      <span>+${formatMonto(banco.metodos[0].ingresos_acumulados)} cobrado</span>
                      {Number(banco.metodos[0].ingresos_extra_acumulados) > 0 ? (
                        <span>+${formatMonto(banco.metodos[0].ingresos_extra_acumulados)} propinas/extra</span>
                      ) : null}
                      {Number(banco.metodos[0].transferencias_entrantes_acumuladas) > 0 ? (
                        <span>+${formatMonto(banco.metodos[0].transferencias_entrantes_acumuladas)} transferencias recibidas</span>
                      ) : null}
                      <span>−${formatMonto(banco.metodos[0].gastos_acumulados)} gastos</span>
                      <span>−${formatMonto(banco.metodos[0].compras_acumuladas)} proveedores</span>
                      {Number(banco.metodos[0].transferencias_salientes_acumuladas) > 0 ? (
                        <span>−${formatMonto(banco.metodos[0].transferencias_salientes_acumuladas)} transferencias enviadas</span>
                      ) : null}
                      {Number(banco.metodos[0].consignado_acumulado) > 0 ? (
                        <span>−${formatMonto(banco.metodos[0].consignado_acumulado)} consignado</span>
                      ) : null}
                      {banco.metodos[0].es_efectivo ? <span style={efectivoBadgeStyle}>Efectivo</span> : null}
                    </div>
                  )}
                </article>
              ))}
            </div>
          </section>

          {transitorio && Number(transitorio.total_usd) > 0 ? (
            <section style={panelStyle}>
              <div style={sectionTitleStyle}>Puntos de venta por cobrar (transitorio) — al {fecha}</div>
              <div style={{ fontSize: 12.5, color: '#c8bbbb' }}>
                Lotes de punto de venta abiertos o cerrados que todavía no se acreditan: ${formatMonto(transitorio.total_usd)} en total.
              </div>
              <div style={tableWrapStyle}>
                <div style={transitorioTableStyle}>
                  <div style={headStyle}>Banco</div>
                  <div style={headStyle}>Lotes abiertos</div>
                  <div style={headStyle}>Lotes cerrados</div>
                  <div style={headStyle}>Por acreditar</div>
                  {transitorio.por_banco.map((item) => (
                    <Fragment key={item.banco}>
                      <div style={cellStyle}>{item.banco}</div>
                      <div style={cellStyle}>{item.lotes_abiertos}</div>
                      <div style={cellStyle}>{item.lotes_cerrados}</div>
                      <div style={cellStyle}>${formatMonto(item.monto_usd)}</div>
                    </Fragment>
                  ))}
                </div>
              </div>
              {onNavigate ? (
                <button type="button" className="no-print" onClick={() => onNavigate('contabilidad-lotes-pos')} style={verLotesLinkStyle}>
                  Ver lotes de punto de venta →
                </button>
              ) : null}
            </section>
          ) : null}

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Detalle por cuenta</div>
            <div style={tableWrapStyle}>
              <div style={tableStyle}>
                <div style={headStyle}>Cuenta</div>
                <div style={headStyle}>Cobrado</div>
                <div style={headStyle}>Propinas/extra</div>
                <div style={headStyle}>Transf. entrada</div>
                <div style={headStyle}>Gastos</div>
                <div style={headStyle}>Proveedores</div>
                <div style={headStyle}>Transf. salida</div>
                <div style={headStyle}>Consignado</div>
                <div style={headStyle}>Saldo disponible</div>
                <div style={headStyle}>Por acreditar</div>
                {cuentas.map((cuenta) => (
                  <Fragment key={cuenta.id}>
                    <div style={cellStyle}>{cuenta.nombre}{cuenta.es_efectivo ? ' (efectivo)' : ''}</div>
                    <div style={cellStyle}>${formatMonto(cuenta.ingresos_acumulados)}</div>
                    <div style={cellStyle}>${formatMonto(cuenta.ingresos_extra_acumulados)}</div>
                    <div style={cellStyle}>${formatMonto(cuenta.transferencias_entrantes_acumuladas)}</div>
                    <div style={cellStyle}>${formatMonto(cuenta.gastos_acumulados)}</div>
                    <div style={cellStyle}>${formatMonto(cuenta.compras_acumuladas)}</div>
                    <div style={cellStyle}>${formatMonto(cuenta.transferencias_salientes_acumuladas)}</div>
                    <div style={cellStyle}>${formatMonto(cuenta.consignado_acumulado)}</div>
                    <div style={{ ...cellStyle, fontWeight: 800, color: Number(cuenta.saldo_disponible) < 0 ? '#ff9d9d' : '#8fffb0' }}>
                      ${formatMonto(cuenta.saldo_disponible)}
                    </div>
                    <div style={cellStyle}>{cuenta.es_punto_venta ? `$${formatMonto(cuenta.por_acreditar_usd)}` : '—'}</div>
                  </Fragment>
                ))}
                <div style={{ ...cellStyle, fontWeight: 800 }}>Total disponible</div>
                <div style={cellStyle} />
                <div style={cellStyle} />
                <div style={cellStyle} />
                <div style={cellStyle} />
                <div style={cellStyle} />
                <div style={cellStyle} />
                <div style={cellStyle} />
                <div style={{ ...cellStyle, fontWeight: 800 }}>${formatMonto(data.total_disponible)}</div>
                <div style={{ ...cellStyle, fontWeight: 800 }}>${formatMonto(data.total_por_acreditar)}</div>
              </div>
            </div>
          </section>
        </>
      ) : null}

      <TransferenciaCuentasModal
        open={modalTransferenciaAbierto}
        fechaInicial={fecha}
        onClose={() => setModalTransferenciaAbierto(false)}
        onSuccess={(transferencia) => {
          setModalTransferenciaAbierto(false);
          showSuccess(`Transferencia #${transferencia.id} registrada correctamente.`);
          loadReport(fecha);
        }}
      />

      <IngresoParcialModal
        open={modalIngresoAbierto}
        submitting={ingresoSubmitting}
        onClose={() => setModalIngresoAbierto(false)}
        onSubmit={handleRegistrarIngresoParcial}
      />
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
const metodosAnidadosStyle = { display: 'grid', gap: 4, paddingTop: 6, borderTop: '1px dashed rgba(255,255,255,0.12)' };
const metodoAnidadoRowStyle = { display: 'flex', justifyContent: 'space-between', gap: 8, color: '#d2c3c3', fontSize: 12.5 };

const porAcreditarBoxStyle = { display: 'grid', gap: 2, padding: '8px 10px', borderRadius: 10, border: '1px dashed rgba(255,207,133,0.4)', background: 'rgba(255,207,133,0.06)', color: '#e8d9b6', fontSize: 12.5 };
const transitorioTableStyle = { display: 'grid', gridTemplateColumns: 'minmax(140px,1.2fr) repeat(3, minmax(110px,0.8fr))', minWidth: 520, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const verLotesLinkStyle = { border: 'none', background: 'none', color: '#ff9d9d', fontSize: 13, fontWeight: 700, cursor: 'pointer', padding: 0, textAlign: 'left', width: 'fit-content' };
const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(160px,1.1fr) minmax(100px,0.7fr) minmax(110px,0.7fr) minmax(110px,0.7fr) minmax(100px,0.7fr) minmax(110px,0.7fr) minmax(100px,0.7fr) minmax(100px,0.7fr) minmax(140px,0.9fr) minmax(120px,0.8fr)', minWidth: 1300, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(255,255,255,0.06)', color: '#ffb0b0', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '14px', borderTop: '1px solid rgba(255,255,255,0.08)', color: '#f2e6e6', display: 'grid', alignContent: 'center' };

const printButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
// Cada categoria (transferencia/ingreso) era antes DOS botones sueltos (uno
// para la accion, otro para el historial) — con 4 botones pegados se veia
// desordenado. Un solo <select> por categoria agrupa "accion nueva" y "ver
// historial" en un solo control compacto; el valor siempre vuelve a "" tras
// elegir una opcion (ver onChange), asi que es un menu de acciones, no un
// campo que "recuerda" una seleccion.
const accionSelectStyle = (variante) => {
  const colores = {
    transferencia: { border: 'rgba(150,130,255,0.4)', background: 'linear-gradient(90deg, #6d28d9 0%, #4f46e5 100%)', shadow: 'rgba(109, 40, 217, 0.35)' },
    ingreso: { border: 'rgba(120,220,150,0.4)', background: 'linear-gradient(90deg, #15803d 0%, #22c55e 100%)', shadow: 'rgba(21, 128, 61, 0.35)' },
  }[variante];
  return {
    border: `1px solid ${colores.border}`,
    borderRadius: 999,
    padding: '10px 34px 10px 18px',
    background: colores.background,
    color: '#fff',
    fontWeight: 700,
    fontSize: 13.5,
    cursor: 'pointer',
    boxShadow: `0 8px 20px ${colores.shadow}`,
    appearance: 'none',
    WebkitAppearance: 'none',
    backgroundImage: 'url("data:image/svg+xml;utf8,<svg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 20 20\' fill=\'white\'><path d=\'M5.5 7.5l4.5 5 4.5-5z\'/></svg>")',
    backgroundRepeat: 'no-repeat',
    backgroundPosition: 'right 12px center',
    backgroundSize: '14px',
  };
};

export default ReporteDisponibilidadCuentasPage;

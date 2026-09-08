import { Fragment, useCallback, useEffect, useState } from 'react';
import useMobileBackHandler from '../hooks/useMobileBackHandler';
import { getFechaSeleccionada, setFechaSeleccionada } from '../utils/fechaContabilidad';

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

function getCookie(name) {
  const all = `; ${document.cookie}`;
  const parts = all.split(`; ${name}=`);
  if (parts.length === 2) {
    return parts.pop().split(';').shift();
  }
  return '';
}

function ReporteCuentasCobradasPage({ isMobile, onBack }) {
  const [fecha, setFecha] = useState(() => getFechaSeleccionada(todayIso()));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [notaSeleccionadaId, setNotaSeleccionadaId] = useState(null);
  const [notaDetalle, setNotaDetalle] = useState(null);
  const [notaDetalleLoading, setNotaDetalleLoading] = useState(false);
  const [notaDetalleError, setNotaDetalleError] = useState('');

  const loadReport = useCallback(async (fechaConsultada) => {
    setLoading(true);
    setMessage('');
    try {
      const response = await fetch(`/api/admin/reportes/cuentas-cobradas-dia/?fecha=${fechaConsultada}`, {
        credentials: 'include',
        cache: 'no-store',
      });
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cargar las cuentas cobradas hoy.');
      }
      setData(json);
    } catch (error) {
      setMessage(error.message || 'No se pudo cargar las cuentas cobradas hoy.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadReport(fecha);
    setFechaSeleccionada(fecha);
  }, [fecha, loadReport]);

  const abrirDetalleNota = async (notaId) => {
    setNotaSeleccionadaId(notaId);
    setNotaDetalle(null);
    setNotaDetalleError('');
    setNotaDetalleLoading(true);
    try {
      const response = await fetch(`/api/admin/reportes/ventas-dia/${notaId}/`, {
        credentials: 'include',
        cache: 'no-store',
      });
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cargar el detalle de la nota.');
      }
      setNotaDetalle(json);
    } catch (error) {
      setNotaDetalleError(error.message || 'No se pudo cargar el detalle de la nota.');
    } finally {
      setNotaDetalleLoading(false);
    }
  };

  const pagos = data?.pagos || [];

  return (
    <section style={containerStyle(isMobile)}>
      <div className="no-print" style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          ← Volver a Cuadre de caja
        </button>
        <button type="button" onClick={() => window.print()} style={printButtonStyle}>
          Imprimir / Guardar PDF
        </button>
      </div>

      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Cuentas cobradas hoy</h2>
          <p style={subtitleStyle}>
            Fiados de días anteriores que se cobraron hoy. El monto en dólares es siempre el mismo (la deuda no
            cambia), pero el bolívar se devalúa mientras está pendiente — acá se ve cuánto más había que cobrar
            en bolívares hoy frente a lo que hubiera sido el día que se emitió la nota.
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

      {message ? <div style={noticeStyle} className="no-print">{message}</div> : null}

      {loading ? <div style={emptyStyle}>Cargando cuentas cobradas...</div> : null}

      {!loading && data ? (
        <section style={panelStyle}>
          <div style={sectionTitleStyle}>Cobrado hoy de días anteriores — {fecha}</div>

          {pagos.length === 0 ? (
            <div style={emptyStyle}>Hoy no se cobró ninguna cuenta pendiente de un día anterior.</div>
          ) : (
            <div style={tableWrapStyle}>
              <div style={cobradasTableStyle}>
                <div style={headStyle}>Nota</div>
                <div style={headStyle}>Cliente</div>
                <div style={headStyle}>Monto ($)</div>
                <div style={headStyle}>Emitida</div>
                <div style={headStyle}>Cobrada hoy</div>
                <div style={headStyle}>Diferencia (Bs)</div>
                <div style={headStyle}>Método</div>
                <div style={headStyle}>Banco</div>
                <div style={headStyle}>Referencia</div>
                {pagos.map((pago) => (
                  <Fragment key={pago.pago_id}>
                    <div style={cellStyle}>
                      <button type="button" onClick={() => abrirDetalleNota(pago.nota_id)} style={notaLinkStyle}>
                        {pago.nota_codigo} →
                      </button>
                    </div>
                    <div style={cellStyle}>{pago.cliente || '—'}</div>
                    <div style={cellStyle}>${formatMonto(pago.monto)}</div>
                    <div style={cellStyle}>
                      {new Date(pago.fecha_emision_nota).toLocaleDateString('es-VE')}
                      {pago.tasa_emision ? (
                        <div style={secondaryAmountStyle}>
                          Bs. {formatMonto(pago.bs_a_tasa_emision)} (a Bs {formatMonto(pago.tasa_emision)}/$)
                        </div>
                      ) : (
                        <div style={secondaryAmountStyle}>Pagado en USD, sin tasa</div>
                      )}
                    </div>
                    <div style={cellStyle}>
                      {new Date(pago.fecha_pago).toLocaleTimeString('es-VE')}
                      {pago.tasa_cobro ? (
                        <div style={secondaryAmountStyle}>
                          Bs. {formatMonto(pago.bs_a_tasa_cobro)} (a Bs {formatMonto(pago.tasa_cobro)}/$)
                        </div>
                      ) : (
                        <div style={secondaryAmountStyle}>Pagado en USD, sin tasa</div>
                      )}
                    </div>
                    <div style={cellStyle}>
                      {pago.diferencia_bs !== null ? (
                        <span style={diferenciaStyle(Number(pago.diferencia_bs))}>
                          {Number(pago.diferencia_bs) > 0 ? '+' : ''}Bs. {formatMonto(pago.diferencia_bs)}
                        </span>
                      ) : '—'}
                    </div>
                    <div style={cellStyle}>{pago.metodo_pago_nombre}</div>
                    <div style={cellStyle}>{pago.cuenta_bancaria || '—'}</div>
                    <div style={cellStyle}>{pago.referencia || '—'}</div>
                  </Fragment>
                ))}
              </div>
            </div>
          )}

          <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
            <div style={{ fontWeight: 700, color: '#fff' }}>
              Total cobrado: ${formatMonto(data.total_cobrado)}
            </div>
            <div style={{ fontWeight: 700, color: '#c8bbbb' }}>
              Diferencia total por devaluación: Bs. {formatMonto(data.total_diferencia_bs)}
            </div>
          </div>
        </section>
      ) : null}

      {notaSeleccionadaId ? (
        <NotaDetalleModal
          loading={notaDetalleLoading}
          error={notaDetalleError}
          detalle={notaDetalle}
          onClose={() => setNotaSeleccionadaId(null)}
        />
      ) : null}
    </section>
  );
}

const ESTADO_LABEL = {
  pendiente_pago: 'Pendiente',
  abonada_parcial: 'Abonada parcial',
  pagada: 'Pagada',
};

function NotaDetalleModal({ loading, error, detalle, onClose }) {
  // Solo se monta mientras hay una nota seleccionada, asi que montado == abierto.
  useMobileBackHandler(true, onClose);
  const [reimprimiendo, setReimprimiendo] = useState(false);
  const [reimprimirMsg, setReimprimirMsg] = useState('');

  const handleReimprimir = async () => {
    if (!detalle) return;
    setReimprimiendo(true);
    setReimprimirMsg('');
    try {
      const response = await fetch(`/api/notas-entrega/${detalle.nota.id}/reimprimir/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrftoken') || '' },
        credentials: 'include',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo reimprimir la nota de entrega.');
      }
      setReimprimirMsg(data.message || `Nota ${detalle.nota.codigo} reenviada a la impresora.`);
    } catch (requestError) {
      setReimprimirMsg(requestError.message || 'No se pudo reimprimir la nota de entrega.');
    } finally {
      setReimprimiendo(false);
    }
  };

  return (
    <div style={modalBackdropStyle} onClick={onClose}>
      <div style={modalCardStyle} onClick={(event) => event.stopPropagation()}>
        <div style={modalHeaderStyle}>
          <div style={modalTitleStyle}>{detalle ? `Nota ${detalle.nota.codigo}` : 'Detalle de la nota'}</div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {detalle ? (
              <button type="button" onClick={handleReimprimir} disabled={reimprimiendo} style={reimprimirButtonStyle}>
                {reimprimiendo ? 'Enviando...' : 'Reimprimir'}
              </button>
            ) : null}
            <button type="button" onClick={onClose} style={modalCloseButtonStyle}>✕</button>
          </div>
        </div>

        {reimprimirMsg ? <div style={secondaryAmountStyle}>{reimprimirMsg}</div> : null}
        {loading ? <div style={emptyStyle}>Cargando detalle...</div> : null}
        {error ? <div style={noticeStyle}>{error}</div> : null}

        {!loading && detalle ? (
          <>
            <div style={modalMetaGridStyle}>
              <div><span style={modalMetaLabelStyle}>Cliente</span><br />{detalle.nota.cliente || '—'}</div>
              <div><span style={modalMetaLabelStyle}>Mesa</span><br />{detalle.mesas.length ? detalle.mesas.join(', ') : '—'}</div>
              <div><span style={modalMetaLabelStyle}>Mesero</span><br />{detalle.meseros.length ? detalle.meseros.join(', ') : '—'}</div>
              <div><span style={modalMetaLabelStyle}>Estado</span><br />{ESTADO_LABEL[detalle.nota.estado] || detalle.nota.estado}</div>
              <div><span style={modalMetaLabelStyle}>Total</span><br />${formatMonto(detalle.nota.total)}</div>
            </div>

            <div style={modalItemsTitleStyle}>Lo que pidieron</div>
            {detalle.items.length === 0 ? (
              <div style={emptyStyle}>Esta nota no tiene pedidos asociados.</div>
            ) : (
              <div style={modalItemsListStyle}>
                {detalle.items.map((item, index) => (
                  <div key={index} style={modalItemRowStyle}>
                    <div style={modalItemNombreStyle}>
                      {item.venta_por_peso ? `${item.peso_gramos} g` : `${item.cantidad}x`} {item.producto}
                    </div>
                    {(item.adicionales.length > 0 || item.opciones.length > 0) ? (
                      <div style={modalItemExtraStyle}>
                        {[...item.adicionales, ...item.opciones].join(' · ')}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </>
        ) : null}
      </div>
    </div>
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
const tableWrapStyle = { overflowX: 'auto' };
const cobradasTableStyle = { display: 'grid', gridTemplateColumns: 'minmax(100px,0.7fr) minmax(120px,0.9fr) minmax(90px,0.6fr) minmax(160px,1.1fr) minmax(160px,1.1fr) minmax(130px,0.8fr) minmax(120px,0.8fr) minmax(130px,0.8fr) minmax(120px,0.8fr)', minWidth: 1150, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(255,255,255,0.06)', color: '#ffb0b0', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '14px', borderTop: '1px solid rgba(255,255,255,0.08)', color: '#f2e6e6', display: 'grid', alignContent: 'center' };
const secondaryAmountStyle = { color: '#c8bbbb', fontSize: 12, marginTop: 2 };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };
const printButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const notaLinkStyle = { border: 'none', background: 'none', color: '#ff9d9d', fontWeight: 700, cursor: 'pointer', padding: 0, fontSize: 'inherit', fontFamily: 'inherit' };
const diferenciaStyle = (valor) => ({
  fontWeight: 800,
  color: valor > 0 ? '#ffcf85' : valor < 0 ? '#9fd8ff' : '#c8bbbb',
});

const modalBackdropStyle = { position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,0.6)', display: 'grid', placeItems: 'center', padding: 16 };
const modalCardStyle = { width: '100%', maxWidth: 560, maxHeight: '85vh', overflowY: 'auto', borderRadius: 20, border: '1px solid rgba(255,145,145,0.3)', background: 'linear-gradient(180deg, rgba(28,12,12,0.98) 0%, rgba(10,8,8,0.99) 100%)', padding: '22px 22px 18px', boxShadow: '0 20px 50px rgba(0,0,0,0.45)', display: 'grid', gap: 14 };
const modalHeaderStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center' };
const modalTitleStyle = { color: '#fff', fontSize: 19, fontWeight: 800 };
const modalCloseButtonStyle = { border: 'none', background: 'rgba(255,255,255,0.08)', color: '#fff', width: 30, height: 30, borderRadius: 999, cursor: 'pointer', fontSize: 14 };
const reimprimirButtonStyle = { border: '1px solid rgba(255,255,255,0.16)', borderRadius: 999, padding: '6px 14px', background: 'rgba(255,255,255,0.06)', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: 12.5 };
const modalMetaGridStyle = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 12, color: '#f2e6e6', fontSize: 14 };
const modalMetaLabelStyle = { color: '#ffb0b0', fontSize: 11, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' };
const modalItemsTitleStyle = { color: '#fff', fontSize: 15, fontWeight: 700, borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: 12 };
const modalItemsListStyle = { display: 'grid', gap: 10 };
const modalItemRowStyle = { padding: '10px 12px', borderRadius: 12, border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(255,255,255,0.03)' };
const modalItemNombreStyle = { color: '#fff', fontWeight: 700, fontSize: 14 };
const modalItemExtraStyle = { color: '#c8bbbb', fontSize: 12.5, marginTop: 4 };

export default ReporteCuentasCobradasPage;

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

function ReportePropinasPage({ isMobile, onBack }) {
  const [fecha, setFecha] = useState(() => getFechaSeleccionada(todayIso()));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [cambioMetodoModal, setCambioMetodoModal] = useState(null);
  const [cambiandoMetodo, setCambiandoMetodo] = useState(false);

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
        throw new Error(json.message || 'No se pudo cargar las propinas y excedentes.');
      }
      setData(json);
    } catch (error) {
      setMessage(error.message || 'No se pudo cargar las propinas y excedentes.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadReport(fecha);
    setFechaSeleccionada(fecha);
  }, [fecha, loadReport]);

  // Igual que en ReporteVentasDiaPage: no se aplica directo desde el <select>,
  // abre un modal que pide el motivo (obligatorio, queda en la auditoria —
  // ver VGCorreccionMetodoPago) y hay que confirmar ahi.
  const abrirCambioMetodo = (id, metodoActualId, metodoActualNombre, metodoNuevoId, metodoNuevoNombre) => {
    setCambioMetodoModal({ id, metodoActualId, metodoActualNombre, metodoNuevoId, metodoNuevoNombre });
  };

  const confirmarCambioMetodo = async (motivo) => {
    if (!cambioMetodoModal) {
      return;
    }
    const { id, metodoNuevoId } = cambioMetodoModal;
    setCambiandoMetodo(true);
    setMessage('');
    try {
      const response = await fetch('/api/admin/reportes/cuadre-caja/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'cambiar_metodo_pago', fecha, tipo: 'ingreso_extra', id, metodo_pago_id: metodoNuevoId, motivo }),
      });
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cambiar la cuenta.');
      }
      setMessage(json.message || 'Cuenta actualizada.');
      setCambioMetodoModal(null);
      loadReport(fecha);
    } catch (error) {
      setMessage(error.message || 'No se pudo cambiar la cuenta.');
    } finally {
      setCambiandoMetodo(false);
    }
  };

  const metodosPago = data?.metodos_pago || [];
  const ingresosExtra = data?.ingresos_extra_dia || [];

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
          <h2 style={titleStyle(isMobile)}>Propinas y excedentes</h2>
          <p style={subtitleStyle}>
            Dinero que entró junto con un cobro pero que no es venta: propinas para meseros y el vuelto que el
            cliente no pidió de vuelta. Si la cajera lo registró en la cuenta equivocada, la cambias acá.
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

      {loading ? <div style={emptyStyle}>Cargando propinas y excedentes...</div> : null}

      {!loading && data ? (
        <section style={panelStyle}>
          <div style={sectionTitleStyle}>Propinas y pagos extra — {fecha}</div>

          {ingresosExtra.length === 0 ? (
            <div style={emptyStyle}>Aún no se registró ninguna propina ni pago extra este día.</div>
          ) : (
            <div style={tableWrapStyle}>
              <div style={ingresoExtraTableStyle}>
                <div style={headStyle}>Tipo</div>
                <div style={headStyle}>Monto</div>
                <div style={headStyle}>Cuenta</div>
                <div style={headStyle}>Registrado por</div>
                <div style={headStyle}>Hora</div>
                <div style={headStyle}>Descripción</div>
                {ingresosExtra.map((item) => (
                  <Fragment key={item.id}>
                    <div style={cellStyle}>{item.tipo_label}</div>
                    <div style={cellStyle}>
                      {item.moneda === 'VES' && item.tasa_cambio_referencia ? (
                        <>
                          {/* Siempre con la tasa que se congeló al registrar este ingreso —
                              nunca la de hoy: esto es un registro histórico, no debe cambiar
                              de valor cada vez que se refresca el cache del BCV. */}
                          Bs. {formatMonto(Number(item.monto) * Number(item.tasa_cambio_referencia))}
                          <span style={secondaryAmountStyle}> (${formatMonto(item.monto)})</span>
                        </>
                      ) : (
                        <>${formatMonto(item.monto)}</>
                      )}
                    </div>
                    <div style={cellStyle}>
                      <select
                        value={item.metodo_pago_id}
                        onChange={(event) => {
                          const nuevoId = Number(event.target.value);
                          const nuevo = metodosPago.find((m) => m.id === nuevoId);
                          if (!nuevo || nuevoId === item.metodo_pago_id) return;
                          abrirCambioMetodo(item.id, item.metodo_pago_id, item.metodo_pago_nombre, nuevoId, nuevo.nombre);
                        }}
                        style={cuentaSelectStyle}
                        className="admin-dark-select"
                      >
                        {metodosPago.map((metodo) => (
                          <option key={metodo.id} value={metodo.id}>{metodo.nombre}</option>
                        ))}
                      </select>
                    </div>
                    <div style={cellStyle}>{item.registrado_por || '—'}</div>
                    <div style={cellStyle}>{new Date(item.fecha_creacion).toLocaleTimeString('es-VE')}</div>
                    <div style={cellStyle}>{item.descripcion || '—'}</div>
                    {item.ultima_correccion ? (
                      <div style={correccionNotaStyle}>
                        ✎ Corregido de {item.ultima_correccion.metodo_anterior} a {item.ultima_correccion.metodo_nuevo} por{' '}
                        {item.ultima_correccion.corregido_por || '—'}: “{item.ultima_correccion.motivo}”
                      </div>
                    ) : null}
                  </Fragment>
                ))}
              </div>
            </div>
          )}

          <div style={{ fontWeight: 700, color: '#fff' }}>
            Total propinas/extra: ${formatMonto(data.total_ingresos_extra_dia)}
          </div>
        </section>
      ) : null}

      {cambioMetodoModal ? (
        <CambiarMetodoModal
          info={cambioMetodoModal}
          busy={cambiandoMetodo}
          onClose={() => setCambioMetodoModal(null)}
          onConfirm={confirmarCambioMetodo}
        />
      ) : null}
    </section>
  );
}

function CambiarMetodoModal({ info, busy, onClose, onConfirm }) {
  // Solo se monta mientras hay un cambio en curso, así que montado == abierto.
  useMobileBackHandler(true, onClose);
  const [motivo, setMotivo] = useState('');

  return (
    <div style={modalBackdropStyle} onClick={busy ? undefined : onClose}>
      <div style={modalCardStyle} onClick={(event) => event.stopPropagation()}>
        <div style={modalTitleStyle}>Cambiar cuenta</div>
        <p style={modalDescStyle}>
          Vas a mover este registro de <strong>{info.metodoActualNombre}</strong> a{' '}
          <strong>{info.metodoNuevoNombre}</strong>. Escribe el motivo del cambio — queda guardado para auditoría.
        </p>
        <label style={modalFieldLabelStyle}>
          Motivo del cambio *
          <textarea
            value={motivo}
            onChange={(event) => setMotivo(event.target.value)}
            style={modalTextareaStyle}
            placeholder="Ej: La cajera registró la propina en Efectivo pero llegó por Pago Móvil."
            rows={3}
            autoFocus
          />
        </label>
        <div style={modalFooterStyle}>
          <button type="button" onClick={onClose} style={secondaryModalButtonStyle} disabled={busy}>
            Cancelar
          </button>
          <button
            type="button"
            onClick={() => onConfirm(motivo.trim())}
            style={primaryButtonStyle}
            disabled={busy || !motivo.trim()}
          >
            {busy ? 'Guardando...' : 'Confirmar cambio'}
          </button>
        </div>
      </div>
    </div>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const headerRowStyle = (isMobile) => ({ display: 'flex', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center', flexDirection: isMobile ? 'column' : 'row', gap: 12 });
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: '#d2c3c3', maxWidth: 640 };
const dateLabelStyle = { display: 'flex', flexDirection: 'column', gap: 6, color: '#f2e6e6', fontSize: 13, fontWeight: 700 };
const dateInputStyle = { borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff' };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const sectionTitleStyle = { color: '#fff', fontSize: 19, fontWeight: 700 };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const tableWrapStyle = { overflowX: 'auto' };
const ingresoExtraTableStyle = { display: 'grid', gridTemplateColumns: 'minmax(100px,0.7fr) minmax(90px,0.6fr) minmax(170px,1fr) minmax(140px,0.9fr) minmax(90px,0.6fr) minmax(160px,1.2fr)', minWidth: 880, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const cuentaSelectStyle = { borderRadius: 10, border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(0,0,0,0.3)', color: '#fff', padding: '6px 8px', fontSize: 13, width: '100%' };
const correccionNotaStyle = { gridColumn: '1 / -1', padding: '2px 14px 10px', fontSize: 11.5, color: '#ffcf85', fontStyle: 'italic' };
const headStyle = { padding: '12px 14px', background: 'rgba(255,255,255,0.06)', color: '#ffb0b0', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '14px', borderTop: '1px solid rgba(255,255,255,0.08)', color: '#f2e6e6', display: 'grid', alignContent: 'center' };
const secondaryAmountStyle = { color: '#c8bbbb', fontSize: 12, marginLeft: 6 };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };
const printButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };

const modalBackdropStyle = { position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,0.6)', display: 'grid', placeItems: 'center', padding: 16 };
const modalCardStyle = { width: '100%', maxWidth: 440, borderRadius: 20, border: '1px solid rgba(255,145,145,0.3)', background: 'linear-gradient(180deg, rgba(28,12,12,0.98) 0%, rgba(10,8,8,0.99) 100%)', padding: '22px 22px 18px', boxShadow: '0 20px 50px rgba(0,0,0,0.45)', display: 'grid', gap: 12 };
const modalTitleStyle = { color: '#fff', fontSize: 19, fontWeight: 800 };
const modalDescStyle = { margin: 0, color: '#d2c3c3', lineHeight: 1.55, fontSize: 13.5 };
const modalFieldLabelStyle = { display: 'grid', gap: 6, color: '#e8dede', fontSize: 13, fontWeight: 700 };
const modalTextareaStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff4f4', fontSize: 14, fontFamily: 'inherit', resize: 'vertical' };
const modalFooterStyle = { display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 6, flexWrap: 'wrap' };
const secondaryModalButtonStyle = { border: '1px solid rgba(255,255,255,0.16)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.05)', color: '#fff', fontWeight: 700, cursor: 'pointer' };

export default ReportePropinasPage;

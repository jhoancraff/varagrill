import { Fragment, useCallback, useEffect, useState } from 'react';
import useMobileBackHandler from '../hooks/useMobileBackHandler';

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

// Sin referencia propia (efectivo, o el metodo no la exigia cuando se cobro),
// el backend igual guarda una autogenerada (COBRO-.../ABONO-...) para que el
// pago nunca quede sin referencia — no es informacion util para mostrar.
function esReferenciaAutogenerada(referencia) {
  return /^(COBRO|ABONO)-\d{14}-\d+$/.test(referencia || '');
}

function ReporteCuadreCajaPage({ isMobile, onBack, backLabel = '← Volver a Contabilidad' }) {
  const [fecha, setFecha] = useState(todayIso());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);
  const [consignacionMonto, setConsignacionMonto] = useState('');
  const [consignacionNotas, setConsignacionNotas] = useState('');
  const [efectivoContado, setEfectivoContado] = useState('');
  const [cierreNotas, setCierreNotas] = useState('');
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
  }, [fecha, loadReport]);

  const handleAddConsignacion = async (event) => {
    event.preventDefault();
    const monto = Number(consignacionMonto);
    if (!monto || monto <= 0) {
      setMessage('Indica un monto valido para la consignacion.');
      return;
    }

    setSaving(true);
    setMessage('');
    try {
      const response = await fetch('/api/admin/reportes/cuadre-caja/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'agregar_consignacion',
          fecha,
          monto,
          notas: consignacionNotas,
        }),
      });
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo registrar la consignacion.');
      }
      setConsignacionMonto('');
      setConsignacionNotas('');
      setMessage(json.message || 'Consignacion registrada.');
      loadReport(fecha);
    } catch (error) {
      setMessage(error.message || 'No se pudo registrar la consignacion.');
    } finally {
      setSaving(false);
    }
  };

  // Corrige la cuenta (metodo_pago) de un pago o una propina/pago extra de este
  // dia — para cuando la cajera cobro con la cuenta equivocada y esa plata
  // necesita "moverse" a la correcta para que el cuadre coincida con lo que de
  // verdad hay en el banco. No se aplica directo desde el <select>: abre un
  // modal que pide el motivo (obligatorio, es lo que queda en la auditoria —
  // ver VGCorreccionMetodoPago) y hay que confirmar ahi.
  const abrirCambioMetodo = (tipo, id, metodoActualId, metodoActualNombre, metodoNuevoId, metodoNuevoNombre) => {
    setCambioMetodoModal({ tipo, id, metodoActualId, metodoActualNombre, metodoNuevoId, metodoNuevoNombre });
  };

  const confirmarCambioMetodo = async (motivo) => {
    if (!cambioMetodoModal) {
      return;
    }
    const { tipo, id, metodoNuevoId } = cambioMetodoModal;
    setCambiandoMetodo(true);
    setMessage('');
    try {
      const response = await fetch('/api/admin/reportes/cuadre-caja/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'cambiar_metodo_pago', fecha, tipo, id, metodo_pago_id: metodoNuevoId, motivo }),
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

  const handleCerrarCaja = async (event) => {
    event.preventDefault();
    if (efectivoContado === '' || Number(efectivoContado) < 0) {
      setMessage('Indica cuanto efectivo contaste fisicamente.');
      return;
    }
    if (!window.confirm('¿Cerrar la caja de este dia? Esta accion queda registrada de forma permanente.')) {
      return;
    }

    setSaving(true);
    setMessage('');
    try {
      const response = await fetch('/api/admin/reportes/cuadre-caja/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'cerrar_caja',
          fecha,
          efectivo_contado_final: Number(efectivoContado),
          notas: cierreNotas,
        }),
      });
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cerrar la caja.');
      }
      setMessage(json.message || 'Caja cerrada.');
      loadReport(fecha);
    } catch (error) {
      setMessage(error.message || 'No se pudo cerrar la caja.');
    } finally {
      setSaving(false);
    }
  };

  const cierre = data?.cierre || null;
  const totalesPorMetodo = data?.totales_por_metodo || [];
  const metodosPago = data?.metodos_pago || [];
  const pagosDia = data?.pagos_dia || [];

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
          <p style={subtitleStyle}>Efectivo esperado vs. contado en fisico, mas el resto de metodos como referencia.</p>
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

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Pagos del día</div>
            <p style={{ margin: 0, color: '#c8bbbb', fontSize: 12 }}>
              Si la cajera cobró con la cuenta equivocada, cámbiala acá — el pago se mueve a la cuenta
              correcta y el cuadre de este día se recalcula solo.
            </p>
            {pagosDia.length === 0 ? (
              <div style={emptyStyle}>No hay pagos registrados este día.</div>
            ) : (
              <div style={tableWrapStyle}>
                <div style={pagosTableStyle}>
                  <div style={headStyle}>Origen</div>
                  <div style={headStyle}>Monto</div>
                  <div style={headStyle}>Registrado por</div>
                  <div style={headStyle}>Hora</div>
                  <div style={headStyle}>Cuenta</div>
                  {pagosDia.map((pago) => (
                    <Fragment key={pago.id}>
                      <div style={cellStyle}>
                        <div>{pago.origen}</div>
                        {pago.referencia && !esReferenciaAutogenerada(pago.referencia) ? (
                          <div style={secondaryAmountStyle}>Ref: {pago.referencia}</div>
                        ) : null}
                      </div>
                      <div style={cellStyle}>${formatMonto(pago.monto)}</div>
                      <div style={cellStyle}>{pago.registrado_por || '—'}</div>
                      <div style={cellStyle}>{new Date(pago.fecha_pago).toLocaleTimeString('es-VE')}</div>
                      <div style={cellStyle}>
                        <select
                          value={pago.metodo_pago_id}
                          onChange={(event) => {
                            const nuevoId = Number(event.target.value);
                            const nuevo = metodosPago.find((m) => m.id === nuevoId);
                            if (!nuevo || nuevoId === pago.metodo_pago_id) return;
                            abrirCambioMetodo('pago', pago.id, pago.metodo_pago_id, pago.metodo_pago_nombre, nuevoId, nuevo.nombre);
                          }}
                          style={cuentaSelectStyle}
                          className="admin-dark-select"
                        >
                          {metodosPago.map((metodo) => (
                            <option key={metodo.id} value={metodo.id}>{metodo.nombre}</option>
                          ))}
                        </select>
                      </div>
                      {pago.ultima_correccion ? (
                        <div style={correccionNotaStyle}>
                          ✎ Corregido de {pago.ultima_correccion.metodo_anterior} a {pago.ultima_correccion.metodo_nuevo} por{' '}
                          {pago.ultima_correccion.corregido_por || '—'}: “{pago.ultima_correccion.motivo}”
                        </div>
                      ) : null}
                    </Fragment>
                  ))}
                </div>
              </div>
            )}
          </section>

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Consignaciones del turno</div>
            {data.consignaciones.length === 0 ? (
              <div style={emptyStyle}>Aun no hay consignaciones registradas para este dia.</div>
            ) : (
              <div style={tableWrapStyle}>
                <div style={consignacionTableStyle}>
                  <div style={headStyle}>Monto</div>
                  <div style={headStyle}>Registrada por</div>
                  <div style={headStyle}>Hora</div>
                  <div style={headStyle}>Notas</div>
                  {data.consignaciones.map((item) => (
                    <Fragment key={item.id}>
                      <div style={cellStyle}>${formatMonto(item.monto)}</div>
                      <div style={cellStyle}>{item.creado_por || '—'}</div>
                      <div style={cellStyle}>{new Date(item.fecha_creacion).toLocaleTimeString('es-VE')}</div>
                      <div style={cellStyle}>{item.notas || '—'}</div>
                    </Fragment>
                  ))}
                </div>
              </div>
            )}
            <div style={{ fontWeight: 700, color: '#fff' }}>
              Total consignado: ${formatMonto(data.total_consignado)}
            </div>

            {!cierre ? (
              <form onSubmit={handleAddConsignacion} className="no-print" style={formRowStyle(isMobile)}>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="Monto"
                  value={consignacionMonto}
                  onChange={(event) => setConsignacionMonto(event.target.value)}
                  style={inputStyle}
                />
                <input
                  type="text"
                  placeholder="Notas (opcional)"
                  value={consignacionNotas}
                  onChange={(event) => setConsignacionNotas(event.target.value)}
                  style={{ ...inputStyle, flex: 1 }}
                />
                <button type="submit" disabled={saving} style={primaryButtonStyle}>
                  Registrar consignacion
                </button>
              </form>
            ) : null}
          </section>

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Propinas y pagos extra del dia</div>
            {(data.ingresos_extra_dia || []).length === 0 ? (
              <div style={emptyStyle}>Aun no se registro ninguna propina ni pago extra este dia.</div>
            ) : (
              <div style={tableWrapStyle}>
                <div style={ingresoExtraTableStyle}>
                  <div style={headStyle}>Tipo</div>
                  <div style={headStyle}>Monto</div>
                  <div style={headStyle}>Cuenta</div>
                  <div style={headStyle}>Registrado por</div>
                  <div style={headStyle}>Hora</div>
                  <div style={headStyle}>Descripcion</div>
                  {data.ingresos_extra_dia.map((item) => (
                    <Fragment key={item.id}>
                      <div style={cellStyle}>{item.tipo_label}</div>
                      <div style={cellStyle}>
                        {item.moneda === 'VES' ? (
                          <>
                            Bs. {formatMonto(Number(item.monto) * Number(item.tasa_cambio_referencia || data.tasa_bcv || 0))}
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
                            abrirCambioMetodo('ingreso_extra', item.id, item.metodo_pago_id, item.metodo_pago_nombre, nuevoId, nuevo.nombre);
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

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Cierre del dia</div>
            {Number(data.gastos_efectivo_dia) > 0 ? (
              <div style={{ color: '#ff9d9d', fontSize: 13 }}>
                Gastos pagados en efectivo hoy: −${formatMonto(data.gastos_efectivo_dia)}
              </div>
            ) : null}
            {cierre ? (
              <div style={{ display: 'grid', gap: 8, color: '#f2e6e6' }}>
                <div>Efectivo esperado (ventas + propinas/extra − gastos, todo en efectivo): <strong>${formatMonto(cierre.efectivo_esperado)}</strong></div>
                <div>Total consignado: <strong>${formatMonto(cierre.total_consignado)}</strong></div>
                <div>Efectivo contado al cerrar: <strong>${formatMonto(cierre.efectivo_contado_final)}</strong></div>
                <div style={{ color: Number(cierre.diferencia) === 0 ? '#8fffb0' : '#ff9d9d', fontWeight: 800 }}>
                  Diferencia: ${formatMonto(cierre.diferencia)}
                </div>
                {cierre.notas ? <div>Notas: {cierre.notas}</div> : null}
                <div style={{ fontSize: 13, color: '#c8bbbb' }}>
                  Cerrado por {cierre.cerrado_por || '—'} el {new Date(cierre.fecha_creacion).toLocaleString('es-VE')}
                </div>
              </div>
            ) : (
              <form onSubmit={handleCerrarCaja} className="no-print" style={{ display: 'grid', gap: 12, maxWidth: 420 }}>
                <div style={{ color: '#c8bbbb', fontSize: 13 }}>
                  Efectivo esperado (ventas + propinas/extra − gastos, todo en efectivo): <strong style={{ color: '#fff' }}>${formatMonto(data.efectivo_esperado_preview)}</strong>
                </div>
                <label style={{ display: 'grid', gap: 6, color: '#f2e6e6' }}>
                  Efectivo contado fisicamente
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={efectivoContado}
                    onChange={(event) => setEfectivoContado(event.target.value)}
                    style={inputStyle}
                  />
                </label>
                <label style={{ display: 'grid', gap: 6, color: '#f2e6e6' }}>
                  Notas (opcional)
                  <input
                    type="text"
                    value={cierreNotas}
                    onChange={(event) => setCierreNotas(event.target.value)}
                    style={inputStyle}
                  />
                </label>
                <button type="submit" disabled={saving} style={dangerButtonStyle}>
                  Cerrar caja del dia
                </button>
              </form>
            )}
          </section>
        </>
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
          Vas a mover este {info.tipo === 'pago' ? 'pago' : 'registro'} de <strong>{info.metodoActualNombre}</strong> a{' '}
          <strong>{info.metodoNuevoNombre}</strong>. Escribe el motivo del cambio — queda guardado para auditoría.
        </p>
        <label style={modalFieldLabelStyle}>
          Motivo del cambio *
          <textarea
            value={motivo}
            onChange={(event) => setMotivo(event.target.value)}
            style={modalTextareaStyle}
            placeholder="Ej: La cajera cobró por Efectivo pero el cliente pagó por Transferencia."
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
const subtitleStyle = { margin: '8px 0 0', color: '#d2c3c3' };
const dateLabelStyle = { display: 'flex', flexDirection: 'column', gap: 6, color: '#f2e6e6', fontSize: 13, fontWeight: 700 };
const dateInputStyle = { borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff' };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const sectionTitleStyle = { color: '#fff', fontSize: 19, fontWeight: 700 };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(180px,1fr) minmax(140px,1fr)', minWidth: 320, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const consignacionTableStyle = { display: 'grid', gridTemplateColumns: 'minmax(120px,0.8fr) minmax(160px,1fr) minmax(100px,0.6fr) minmax(180px,1.2fr)', minWidth: 700, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const ingresoExtraTableStyle = { display: 'grid', gridTemplateColumns: 'minmax(100px,0.7fr) minmax(90px,0.6fr) minmax(170px,1fr) minmax(140px,0.9fr) minmax(90px,0.6fr) minmax(160px,1.2fr)', minWidth: 880, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const pagosTableStyle = { display: 'grid', gridTemplateColumns: 'minmax(140px,1fr) minmax(100px,0.7fr) minmax(140px,0.9fr) minmax(90px,0.6fr) minmax(170px,1fr)', minWidth: 780, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const cuentaSelectStyle = { borderRadius: 10, border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(0,0,0,0.3)', color: '#fff', padding: '6px 8px', fontSize: 13, width: '100%' };
const correccionNotaStyle = { gridColumn: '1 / -1', padding: '2px 14px 10px', fontSize: 11.5, color: '#ffcf85', fontStyle: 'italic' };

const modalBackdropStyle = { position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,0.6)', display: 'grid', placeItems: 'center', padding: 16 };
const modalCardStyle = { width: '100%', maxWidth: 440, borderRadius: 20, border: '1px solid rgba(255,145,145,0.3)', background: 'linear-gradient(180deg, rgba(28,12,12,0.98) 0%, rgba(10,8,8,0.99) 100%)', padding: '22px 22px 18px', boxShadow: '0 20px 50px rgba(0,0,0,0.45)', display: 'grid', gap: 12 };
const modalTitleStyle = { color: '#fff', fontSize: 19, fontWeight: 800 };
const modalDescStyle = { margin: 0, color: '#d2c3c3', lineHeight: 1.55, fontSize: 13.5 };
const modalFieldLabelStyle = { display: 'grid', gap: 6, color: '#e8dede', fontSize: 13, fontWeight: 700 };
const modalTextareaStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff4f4', fontSize: 14, fontFamily: 'inherit', resize: 'vertical' };
const modalFooterStyle = { display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 6, flexWrap: 'wrap' };
const secondaryModalButtonStyle = { border: '1px solid rgba(255,255,255,0.16)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.05)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const headStyle = { padding: '12px 14px', background: 'rgba(255,255,255,0.06)', color: '#ffb0b0', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '14px', borderTop: '1px solid rgba(255,255,255,0.08)', color: '#f2e6e6', display: 'grid', alignContent: 'center' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };
const secondaryAmountStyle = { color: '#c8bbbb', fontSize: 12, marginLeft: 6 };
const desgloseGridStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, 1fr)', gap: 10 });
const desgloseTileStyle = { display: 'grid', gap: 4, padding: '14px 16px', borderRadius: 14, border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.03)' };
const desgloseLabelStyle = { color: '#ffb0b0', fontSize: 11.5, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' };
const desgloseValueStyle = { color: '#fff', fontSize: 20, fontWeight: 800 };
const desgloseSecondaryStyle = { color: '#c8bbbb', fontSize: 12.5 };
const formRowStyle = (isMobile) => ({ display: 'flex', gap: 10, flexWrap: 'wrap', flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'stretch' : 'center' });
const inputStyle = { borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff' };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const dangerButtonStyle = { border: '1px solid rgba(255,126,126,0.4)', borderRadius: 999, padding: '12px 16px', background: 'rgba(145,33,33,0.35)', color: '#ffd3d3', fontWeight: 700, cursor: 'pointer' };
const printButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default ReporteCuadreCajaPage;

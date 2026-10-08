import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import Toast from './Toast';
import useToast from '../hooks/useToast';
import {
  ESTADO_LOTE_ESTILO,
  formatFecha,
  formatFechaHora,
  formatMonto,
  imprimirLoteEnNavegador,
  postLotePos,
} from '../utils/lotesPos';
import { RangoFechas } from './FiltroFechas';

function todayIso() {
  const now = new Date();
  const offset = now.getTimezoneOffset();
  const local = new Date(now.getTime() - offset * 60000);
  return local.toISOString().slice(0, 10);
}

function daysAgoIso(days) {
  const now = new Date();
  now.setDate(now.getDate() - days);
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

const ESTADOS = [
  ['', 'Todos'],
  ['abierto', 'Abiertos'],
  ['cerrado', 'Cerrados (por acreditar)'],
  ['acreditado', 'Acreditados'],
  ['anulado', 'Anulados'],
];

const MOTIVO_TITULOS = {
  reabrir: 'Reabrir lote',
  anular: 'Anular lote',
  revertir: 'Revertir acreditación',
};

const MOTIVO_AYUDA = {
  reabrir: 'El lote vuelve a estar abierto y recibirá cobros de nuevo. Solo se puede si el método no tiene otro lote abierto.',
  anular: 'El lote queda anulado; sus cobros pasan al lote abierto actual del método.',
  revertir: 'El monto se quita del saldo de la cuenta y el lote vuelve a quedar cerrado (por acreditar).',
};

// Lotes de punto de venta (POS): el dinero cobrado por punto de venta no suma al
// saldo de la cuenta hasta que se acredita. Flujo: el lote se cierra (a mano o al
// cerrar la caja); cuando el personal revisa el punto/banco y el lote cayo, toca
// "Acreditar" y el monto suma de una vez a la cuenta.
function LotesPOSPage({ isMobile, onBack }) {
  const [desde, setDesde] = useState(() => daysAgoIso(30));
  const [hasta, setHasta] = useState(todayIso());
  const [estado, setEstado] = useState('');
  const [metodoId, setMetodoId] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [working, setWorking] = useState(false);
  const [modal, setModal] = useState(null); // { modo: 'detalle' | 'reabrir' | 'anular' | 'revertir', lote }
  const { toast, showSuccess, showError, hideToast } = useToast();

  const loadLotes = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({ desde, hasta });
      if (estado) params.set('estado', estado);
      if (metodoId) params.set('metodo_pago_id', metodoId);
      const response = await fetch(`/api/admin/lotes-pos/?${params.toString()}`, { credentials: 'include', cache: 'no-store' });
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudieron cargar los lotes.');
      }
      setData(json);
    } catch (requestError) {
      setError(requestError.message || 'No se pudieron cargar los lotes.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [desde, hasta, estado, metodoId]);

  useEffect(() => {
    loadLotes();
  }, [loadLotes]);

  const lotes = data?.lotes || [];
  const esAdmin = Boolean(data?.es_admin);

  const porAcreditar = useMemo(() => {
    const pendientes = lotes.filter((lote) => lote.estado === 'abierto' || lote.estado === 'cerrado');
    return {
      cantidad: pendientes.length,
      total: pendientes.reduce((acc, lote) => acc + Number(lote.monto_usd || 0), 0),
    };
  }, [lotes]);

  const ejecutar = async (payload, confirmacion) => {
    if (confirmacion && !window.confirm(confirmacion)) {
      return;
    }
    setWorking(true);
    try {
      const json = await postLotePos(payload);
      showSuccess(json.message || 'Listo.');
      await loadLotes();
    } catch (requestError) {
      showError(requestError.message);
    } finally {
      setWorking(false);
    }
  };

  const cerrarLote = (lote) => ejecutar(
    { action: 'cerrar_lote', lote_id: lote.id },
    `¿Cerrar ${lote.codigo} por $${formatMonto(lote.monto_usd)}? Se imprimirá el detalle de cada cobro para compararlo con el cierre del punto, y los próximos cobros de ${lote.metodo_pago_nombre} abrirán un lote nuevo.`,
  );

  // Reimprime en la impresora de caja el detalle del lote (un renglon por cobro, con su nota de entrega).
  const imprimirLote = (lote) => ejecutar({ action: 'imprimir_lote', lote_id: lote.id });

  // Misma informacion en una hoja para imprimir desde la PC (si la impresora termica no esta disponible).
  const imprimirEnPc = async (lote) => {
    setWorking(true);
    try {
      const response = await fetch(`/api/admin/lotes-pos/?lote_id=${lote.id}`, { credentials: 'include', cache: 'no-store' });
      const json = await response.json();
      if (!response.ok || !json.ok) throw new Error(json.message || 'No se pudo cargar el lote.');
      imprimirLoteEnNavegador(json.lote);
    } catch (requestError) {
      showError(requestError.message);
    } finally {
      setWorking(false);
    }
  };

  const acreditarLote = (lote) => ejecutar(
    { action: 'acreditar_lote', lote_id: lote.id },
    `¿El ${lote.codigo} ya cayó en el banco? Se sumarán $${formatMonto(lote.monto_usd)} (Bs ${formatMonto(lote.monto_bs)}) al saldo de ${lote.metodo_pago_nombre}.`,
  );

  return (
    <section style={containerStyle(isMobile)}>
      <Toast toast={toast} onClose={hideToast} />

      <div className="no-print">
        <button type="button" onClick={onBack} style={backButtonStyle}>← Volver a Contabilidad</button>
      </div>

      <div>
        <h2 style={titleStyle(isMobile)}>Lotes de punto de venta</h2>
        <p style={subtitleStyle}>
          El dinero cobrado por punto de venta no suma a la cuenta hasta que el lote se acredita. Cierra el lote y, cuando revises el punto
          o el banco y el lote haya caído, toca <strong>Acreditar</strong>: el monto se suma de una vez al saldo.
        </p>
      </div>

      <section style={panelStyle}>
        <div className="no-print" style={filtrosStyle(isMobile)}>
          <RangoFechas
            desde={desde}
            hasta={hasta}
            onChange={(rango) => { setDesde(rango.desde); setHasta(rango.hasta); }}
          />
          <label style={fieldStyle}>Estado
            <select value={estado} onChange={(event) => setEstado(event.target.value)} style={inputStyle} className="admin-dark-select">
              {ESTADOS.map(([valor, etiqueta]) => <option key={valor} value={valor}>{etiqueta}</option>)}
            </select>
          </label>
          <label style={fieldStyle}>Método
            <select value={metodoId} onChange={(event) => setMetodoId(event.target.value)} style={inputStyle} className="admin-dark-select">
              <option value="">Todos</option>
              {(data?.metodos_pos || []).map((metodo) => <option key={metodo.id} value={metodo.id}>{metodo.nombre}</option>)}
            </select>
          </label>
        </div>
        <div style={{ color: '#c8bbbb', fontSize: 13 }}>
          {porAcreditar.cantidad} lote(s) sin acreditar · <strong style={{ color: '#ffe3a3' }}>${formatMonto(porAcreditar.total)}</strong> por acreditar
          <span style={{ color: '#a89999' }}> (los lotes abiertos o cerrados siempre se muestran, sin importar el rango)</span>
        </div>

        {loading ? <div style={emptyStyle}>Cargando lotes...</div> : null}
        {!loading && error ? <div style={noticeStyle}>{error}</div> : null}
        {!loading && !error && lotes.length === 0 ? <div style={emptyStyle}>No hay lotes en este rango.</div> : null}

        {!loading && !error && lotes.length > 0 ? (
          <div style={tableWrapStyle}>
            <div style={tableStyle}>
              <div style={headStyle}>Lote</div>
              <div style={headStyle}>Método</div>
              <div style={headStyle}>Operación</div>
              <div style={headStyle}>Cobros</div>
              <div style={headStyle}>Monto</div>
              <div style={headStyle}>Estado</div>
              <div style={headStyle}>Acciones</div>
              {lotes.map((lote) => (
                <Fragment key={lote.id}>
                  <div style={cellStyle}><strong>{lote.codigo}</strong></div>
                  <div style={cellStyle}>
                    {lote.metodo_pago_nombre}
                    {lote.cuenta_bancaria ? <span style={mutedStyle}>{lote.cuenta_bancaria}</span> : null}
                  </div>
                  <div style={cellStyle}>{formatFecha(lote.fecha_operacion)}</div>
                  <div style={cellStyle}>{lote.num_pagos}</div>
                  <div style={cellStyle}>
                    ${formatMonto(lote.monto_usd)}
                    <span style={mutedStyle}>Bs {formatMonto(lote.monto_bs)}</span>
                  </div>
                  <div style={cellStyle}>
                    <span style={{ ...badgeStyle, ...(ESTADO_LOTE_ESTILO[lote.estado] || {}) }}>{lote.estado_label}</span>
                    {lote.estado === 'acreditado' ? <span style={mutedStyle}>{formatFecha(lote.fecha_abono)}</span> : null}
                  </div>
                  <div style={cellActionsStyle}>
                    <button type="button" style={miniButtonStyle} onClick={() => setModal({ modo: 'detalle', lote })}>Ver</button>
                    {lote.estado === 'abierto' && lote.num_pagos > 0 ? (
                      <button type="button" style={miniButtonStyle} disabled={working} onClick={() => cerrarLote(lote)}>Cerrar lote</button>
                    ) : null}
                    {lote.estado !== 'anulado' && lote.num_pagos > 0 ? (
                      <button type="button" style={miniButtonStyle} disabled={working} onClick={() => imprimirLote(lote)}>Imprimir</button>
                    ) : null}
                    {lote.estado === 'cerrado' ? (
                      <button type="button" style={miniPrimaryStyle} disabled={working} onClick={() => acreditarLote(lote)}>Acreditar</button>
                    ) : null}
                    {esAdmin && lote.estado === 'cerrado' ? (
                      <>
                        <button type="button" style={miniButtonStyle} onClick={() => setModal({ modo: 'reabrir', lote })}>Reabrir</button>
                        <button type="button" style={miniDangerStyle} onClick={() => setModal({ modo: 'anular', lote })}>Anular</button>
                      </>
                    ) : null}
                    {esAdmin && lote.estado === 'acreditado' ? (
                      <button type="button" style={miniDangerStyle} onClick={() => setModal({ modo: 'revertir', lote })}>Revertir</button>
                    ) : null}
                    {esAdmin && lote.estado === 'abierto' && lote.num_pagos === 0 ? (
                      <button type="button" style={miniDangerStyle} onClick={() => setModal({ modo: 'anular', lote })}>Anular</button>
                    ) : null}
                  </div>
                </Fragment>
              ))}
            </div>
          </div>
        ) : null}
      </section>

      {modal ? (
        <LoteModal
          modo={modal.modo}
          lote={modal.lote}
          onClose={() => setModal(null)}
          esAdmin={esAdmin}
          onPrintLote={imprimirLote}
          onPrintPc={imprimirEnPc}
          onDone={(mensaje) => {
            setModal(null);
            showSuccess(mensaje);
            loadLotes();
          }}
        />
      ) : null}
    </section>
  );
}

// Detalle de un lote (con sus cobros) y las acciones que piden motivo
// (reabrir, anular, revertir una acreditacion).
function LoteModal({ modo, lote: loteInicial, onClose, onDone, onPrintLote, onPrintPc, esAdmin }) {
  const [lote, setLote] = useState(loteInicial);
  const [motivo, setMotivo] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  // Mover un cobro de un lote cerrado (se dieron cuenta de que no va en ese lote).
  const [moviendo, setMoviendo] = useState(null); // pago elegido
  const [metodos, setMetodos] = useState([]);
  const [destinoMetodoId, setDestinoMetodoId] = useState('');

  useEffect(() => {
    if (modo !== 'detalle' || !esAdmin || loteInicial.estado !== 'cerrado') return undefined;
    let cancelado = false;
    fetch('/api/metodos-pago/', { credentials: 'include', cache: 'no-store' })
      .then((response) => response.json())
      .then((json) => {
        if (!cancelado && json.ok) setMetodos(json.metodos_pago || []);
      })
      .catch(() => {});
    return () => {
      cancelado = true;
    };
  }, [modo, esAdmin, loteInicial.estado]);

  const moverCobro = async (event) => {
    event.preventDefault();
    setError('');
    if (!motivo.trim()) {
      setError('El motivo es obligatorio.');
      return;
    }
    setSaving(true);
    try {
      const json = await postLotePos({
        action: 'mover_pago',
        lote_id: lote.id,
        pago_id: moviendo.id,
        metodo_pago_id: destinoMetodoId || null,
        motivo,
      });
      onDone(json.message || 'Cobro movido.');
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    if (modo !== 'detalle') return undefined;
    let cancelado = false;
    fetch(`/api/admin/lotes-pos/?lote_id=${loteInicial.id}`, { credentials: 'include', cache: 'no-store' })
      .then((response) => response.json())
      .then((json) => {
        if (!cancelado && json.ok) setLote(json.lote);
      })
      .catch(() => {});
    return () => {
      cancelado = true;
    };
  }, [modo, loteInicial.id]);

  const submit = async (event) => {
    event.preventDefault();
    setError('');
    if (!motivo.trim()) {
      setError('El motivo es obligatorio.');
      return;
    }
    const action = { reabrir: 'reabrir_lote', anular: 'anular_lote', revertir: 'revertir_acreditacion' }[modo];
    setSaving(true);
    try {
      const json = await postLotePos({ action, lote_id: lote.id, motivo });
      onDone(json.message || 'Listo.');
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={backdropStyle} onClick={saving ? undefined : onClose}>
      <div style={modalCardStyle} onClick={(event) => event.stopPropagation()}>
        <div style={modalTitleStyle}>{modo === 'detalle' ? `${lote.codigo} — detalle` : `${MOTIVO_TITULOS[modo]} ${lote.codigo}`}</div>
        <div style={{ color: '#c8bbbb', fontSize: 13 }}>
          {lote.metodo_pago_nombre}{lote.cuenta_bancaria ? ` · ${lote.cuenta_bancaria}` : ''} · operado el {formatFecha(lote.fecha_operacion)} · {lote.num_pagos} cobro(s)
        </div>
        <div style={{ color: '#fff', fontWeight: 800, fontSize: 20 }}>
          ${formatMonto(lote.monto_usd)} <span style={{ color: '#c8bbbb', fontSize: 14, fontWeight: 600 }}>· Bs {formatMonto(lote.monto_bs)}</span>
        </div>

        {modo === 'detalle' ? (
          <div style={{ display: 'grid', gap: 10 }}>
            <div style={{ color: '#c8bbbb', fontSize: 12.5 }}>
              {lote.fecha_cierre ? `Cerrado ${formatFechaHora(lote.fecha_cierre)}${lote.cerrado_por ? ` por ${lote.cerrado_por}` : ''}` : 'Abierto'}
              {lote.estado === 'acreditado' ? ` · Acreditado ${formatFechaHora(lote.fecha_acreditacion)}${lote.acreditado_por ? ` por ${lote.acreditado_por}` : ''}` : ''}
            </div>
            {lote.notas ? <div style={{ color: '#d2c3c3', fontSize: 12.5, whiteSpace: 'pre-wrap' }}>{lote.notas}</div> : null}
            {lote.pagos ? (
              <div style={{ display: 'grid', gap: 4 }}>
                <div style={sectionLabelStyle}>Cobros del lote</div>
                {lote.pagos.map((pago) => (
                  <div
                    key={pago.id}
                    style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 13, color: pago.estado === 'anulado' ? '#8c7f7f' : '#f2e6e6', textDecoration: pago.estado === 'anulado' ? 'line-through' : 'none' }}
                  >
                    <span>{pago.origen} · {formatFechaHora(pago.fecha_pago)}{pago.referencia ? ` · ${pago.referencia}` : ''}</span>
                    <span>
                      {pago.monto_bs ? `Bs ${formatMonto(pago.monto_bs)} · ` : ''}${formatMonto(pago.monto_usd)}
                      {esAdmin && lote.estado === 'cerrado' && pago.estado !== 'anulado' ? (
                        <button
                          type="button"
                          style={moverButtonStyle}
                          onClick={() => {
                            setMoviendo(pago);
                            setDestinoMetodoId('');
                            setMotivo('');
                            setError('');
                          }}
                        >
                          Mover
                        </button>
                      ) : null}
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
            {moviendo ? (
              <form onSubmit={moverCobro} style={moverFormStyle}>
                <div style={{ color: '#fff', fontWeight: 700 }}>
                  Mover el cobro de {moviendo.origen} (${formatMonto(moviendo.monto_usd)}) fuera de {lote.codigo}
                </div>
                <label style={fieldStyle}>¿A dónde va?
                  <select value={destinoMetodoId} onChange={(event) => setDestinoMetodoId(event.target.value)} style={inputStyle} className="admin-dark-select">
                    <option value="">Al lote abierto actual de {lote.metodo_pago_nombre} (mismo método)</option>
                    {metodos.filter((metodo) => metodo.id !== lote.metodo_pago_id).map((metodo) => (
                      <option key={metodo.id} value={metodo.id}>Cambiar la cuenta a {metodo.nombre}</option>
                    ))}
                  </select>
                </label>
                <label style={fieldStyle}>Motivo (obligatorio, queda anotado)
                  <input type="text" value={motivo} onChange={(event) => setMotivo(event.target.value)} style={inputStyle} />
                </label>
                <div style={mutedStyle}>
                  El lote cerrado se recalcula sin este cobro para que vuelva a cuadrar con el cierre del punto. No hace falta reabrirlo.
                </div>
                {error ? <div style={noticeStyle}>{error}</div> : null}
                <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
                  <button type="button" onClick={() => setMoviendo(null)} disabled={saving} style={secondaryButtonStyle}>Cancelar</button>
                  <button type="submit" disabled={saving} style={primaryButtonStyle}>{saving ? 'Moviendo...' : 'Mover cobro'}</button>
                </div>
              </form>
            ) : null}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, flexWrap: 'wrap' }}>
              {lote.estado !== 'anulado' && lote.num_pagos > 0 ? (
                <>
                  <button type="button" onClick={() => onPrintLote(lote)} style={secondaryButtonStyle}>Imprimir en caja</button>
                  <button type="button" onClick={() => onPrintPc(lote)} style={secondaryButtonStyle}>Imprimir en la PC</button>
                </>
              ) : null}
              <button type="button" onClick={onClose} style={secondaryButtonStyle}>Cerrar</button>
            </div>
          </div>
        ) : (
          <form onSubmit={submit} style={{ display: 'grid', gap: 12 }}>
            <div style={{ color: '#d2c3c3', fontSize: 13.5 }}>{MOTIVO_AYUDA[modo]}</div>
            <label style={fieldStyle}>Motivo (obligatorio, queda anotado en el lote)
              <input type="text" value={motivo} onChange={(event) => setMotivo(event.target.value)} style={inputStyle} autoFocus />
            </label>
            {error ? <div style={noticeStyle}>{error}</div> : null}
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button type="button" onClick={onClose} disabled={saving} style={secondaryButtonStyle}>Cancelar</button>
              <button type="submit" disabled={saving} style={modo === 'reabrir' ? primaryButtonStyle : dangerButtonStyle}>
                {saving ? 'Guardando...' : MOTIVO_TITULOS[modo]}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: '#d2c3c3', maxWidth: 720, lineHeight: 1.6 };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };
const filtrosStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, minmax(150px, 220px))', gap: 12 });
const fieldStyle = { display: 'grid', gap: 6, color: '#f2e6e6', fontSize: 13, fontWeight: 700 };
const inputStyle = { borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff', width: '100%', boxSizing: 'border-box' };
const mutedStyle = { color: '#a89999', fontSize: 12, display: 'block' };
const sectionLabelStyle = { color: '#ffb0b0', fontSize: 11.5, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.06em' };
const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(110px,0.7fr) minmax(150px,1fr) minmax(100px,0.6fr) minmax(70px,0.4fr) minmax(140px,0.9fr) minmax(120px,0.7fr) minmax(260px,1.5fr)', minWidth: 950, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(255,255,255,0.06)', color: '#ffb0b0', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '12px 14px', borderTop: '1px solid rgba(255,255,255,0.08)', color: '#f2e6e6', display: 'grid', alignContent: 'center', gap: 2 };
const cellActionsStyle = { ...cellStyle, display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' };
const badgeStyle = { fontSize: 11, fontWeight: 800, padding: '3px 10px', borderRadius: 999, textTransform: 'uppercase', letterSpacing: '0.04em', width: 'fit-content' };
const miniButtonStyle = { border: '1px solid rgba(255,255,255,0.18)', borderRadius: 999, padding: '6px 12px', background: 'rgba(255,255,255,0.05)', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: 12.5 };
const miniPrimaryStyle = { ...miniButtonStyle, border: 'none', background: 'linear-gradient(90deg, #15803d 0%, #22c55e 100%)', padding: '7px 16px', fontSize: 13 };
const miniDangerStyle = { ...miniButtonStyle, border: '1px solid rgba(255,126,126,0.4)', background: 'rgba(145,33,33,0.25)', color: '#ffd3d3' };
const secondaryButtonStyle = { border: '1px solid rgba(255,255,255,0.18)', borderRadius: 999, padding: '10px 18px', background: 'rgba(255,255,255,0.05)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 18px', background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const dangerButtonStyle = { border: '1px solid rgba(255,126,126,0.4)', borderRadius: 999, padding: '10px 18px', background: 'rgba(145,33,33,0.45)', color: '#ffd3d3', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const backdropStyle = { position: 'fixed', inset: 0, background: 'rgba(0, 0, 0, 0.65)', display: 'grid', placeItems: 'center', zIndex: 1000, padding: 16, overflowY: 'auto' };
const modalCardStyle = { width: 'min(640px, 100%)', maxHeight: '92vh', overflowY: 'auto', display: 'grid', gap: 14, padding: 22, borderRadius: 20, border: '1px solid rgba(255,255,255,0.14)', background: '#140b0b', boxShadow: '0 30px 80px rgba(0,0,0,0.6)' };
const moverButtonStyle = { marginLeft: 10, border: '1px solid rgba(255,255,255,0.18)', borderRadius: 999, padding: '2px 10px', background: 'rgba(255,255,255,0.05)', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: 12 };
const moverFormStyle = { display: 'grid', gap: 10, padding: 14, borderRadius: 14, border: '1px solid rgba(255,207,133,0.35)', background: 'rgba(255,207,133,0.05)' };
const modalTitleStyle = { color: '#fff', fontSize: 21, fontWeight: 800 };

export default LotesPOSPage;

import { useCallback, useEffect, useState } from 'react';
import useExchangeRate from '../hooks/useExchangeRate';
import { formatMontoDocumento } from '../utils/currency';

function getCookie(name) {
  const all = `; ${document.cookie}`;
  const parts = all.split(`; ${name}=`);
  if (parts.length === 2) {
    return parts.pop().split(';').shift();
  }
  return '';
}

function hoyISO() {
  const now = new Date();
  const offsetMs = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - offsetMs).toISOString().slice(0, 10);
}

function estadoLabel(estado) {
  if (estado === 'pendiente_pago') return 'Pendiente';
  if (estado === 'abonada_parcial') return 'Abonada';
  if (estado === 'pagada') return 'Pagada';
  return estado;
}

function NotasEntregaHistorialPage({ isMobile, onBack, embedded = false, refreshToken }) {
  const tasaCambio = useExchangeRate();
  const [desde, setDesde] = useState(hoyISO);
  const [hasta, setHasta] = useState(hoyISO);
  const [notas, setNotas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reprintingId, setReprintingId] = useState(null);
  const [feedback, setFeedback] = useState('');
  const [feedbackType, setFeedbackType] = useState('success');

  const [selectedNotaId, setSelectedNotaId] = useState(null);
  const [notaDetalle, setNotaDetalle] = useState(null);
  const [loadingDetalle, setLoadingDetalle] = useState(false);
  const [metodosPago, setMetodosPago] = useState([]);
  const [montoAbono, setMontoAbono] = useState('');
  const [metodoAbono, setMetodoAbono] = useState('');
  const [savingAbono, setSavingAbono] = useState(false);

  const fetchNotas = useCallback(async (desdeBuscado, hastaBuscado) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (desdeBuscado) {
        params.set('desde', desdeBuscado);
      }
      if (hastaBuscado) {
        params.set('hasta', hastaBuscado);
      }
      const response = await fetch(`/api/notas-entrega/?${params.toString()}`, { credentials: 'include', cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setError(data.message || 'No se pudieron cargar las notas de entrega.');
        return;
      }
      setNotas(Array.isArray(data.notas_entrega) ? data.notas_entrega : []);
      setError('');
    } catch (requestError) {
      setError('Error de red al cargar las notas de entrega.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchNotas(desde, hasta);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshToken]);

  useEffect(() => {
    const loadMetodosPago = async () => {
      try {
        const response = await fetch('/api/metodos-pago/', { credentials: 'include', cache: 'no-store' });
        const data = await response.json().catch(() => ({}));
        if (response.ok && data.ok) {
          setMetodosPago(Array.isArray(data.metodos_pago) ? data.metodos_pago : []);
        }
      } catch (requestError) {
        // El selector queda vacio si falla.
      }
    };
    loadMetodosPago();
  }, []);

  const handleBuscar = (event) => {
    event.preventDefault();
    if (desde && hasta && desde > hasta) {
      setError('"Desde" no puede ser posterior a "Hasta".');
      return;
    }
    fetchNotas(desde, hasta);
  };

  const fetchNotaDetalle = useCallback(async (notaId) => {
    setLoadingDetalle(true);
    try {
      const response = await fetch(`/api/notas-entrega/${notaId}/`, { credentials: 'include', cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setFeedbackType('error');
        setFeedback(data.message || 'No se pudo cargar el detalle de la nota de entrega.');
        return;
      }
      setNotaDetalle(data.nota_entrega);
    } catch (requestError) {
      setFeedbackType('error');
      setFeedback('Error de red al cargar el detalle de la nota de entrega.');
    } finally {
      setLoadingDetalle(false);
    }
  }, []);

  const handleSelectNota = (nota) => {
    setFeedback('');
    setMontoAbono('');
    setSelectedNotaId(nota.id);
    fetchNotaDetalle(nota.id);
  };

  const handleReimprimir = async (nota) => {
    setReprintingId(nota.id);
    setFeedback('');
    try {
      const response = await fetch(`/api/notas-entrega/${nota.id}/reimprimir/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrftoken') || '' },
        credentials: 'include',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setFeedbackType('error');
        setFeedback(data.message || 'No se pudo reimprimir la nota de entrega.');
        return;
      }
      setFeedbackType('success');
      setFeedback(data.message || `Nota de entrega ${nota.codigo} reenviada a la impresora.`);
    } catch (requestError) {
      setFeedbackType('error');
      setFeedback('Error de red al reimprimir la nota de entrega.');
    } finally {
      setReprintingId(null);
    }
  };

  const handleRegistrarAbono = async (event) => {
    event.preventDefault();
    if (!selectedNotaId) {
      return;
    }
    const metodoPagoId = metodoAbono || (metodosPago[0] && metodosPago[0].id);
    if (!metodoPagoId) {
      setFeedbackType('error');
      setFeedback('No hay metodos de pago activos configurados.');
      return;
    }

    setSavingAbono(true);
    setFeedback('');
    try {
      const response = await fetch(`/api/notas-entrega/${selectedNotaId}/abonos/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') || '' },
        credentials: 'include',
        body: JSON.stringify({ monto: montoAbono, metodo_pago_id: metodoPagoId }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setFeedbackType('error');
        setFeedback(data.message || 'No se pudo registrar el abono.');
        return;
      }
      setFeedbackType('success');
      setFeedback(`Abono de $${data.pago.monto} registrado. Saldo pendiente: $${data.nota_entrega.saldo_pendiente}.`);
      setNotaDetalle(data.nota_entrega);
      setMontoAbono('');
      await fetchNotas(desde, hasta);
    } catch (requestError) {
      setFeedbackType('error');
      setFeedback('Error de red al registrar el abono.');
    } finally {
      setSavingAbono(false);
    }
  };

  return (
    <section style={containerStyle(isMobile, embedded)}>
      {!embedded ? (
        <div style={headerWrapStyle(isMobile)}>
          <div>
            <div style={eyebrowStyle}>Contabilidad</div>
            <h2 style={titleStyle(isMobile)}>Historial de notas de entrega</h2>
            <p style={subtitleStyle}>
              Busca las notas de entrega emitidas por rango de fecha, registra sus abonos y reimprímelas si el cliente necesita otra copia.
            </p>
          </div>
          <button type="button" onClick={onBack} style={backButtonStyle(isMobile)}>
            Volver
          </button>
        </div>
      ) : (
        <div style={embeddedHeaderStyle}>Historial de notas de entrega · Abonos y reimpresión</div>
      )}

      <form onSubmit={handleBuscar} style={buscadorFormStyle(isMobile)}>
        <label style={dateFieldStyle}>
          <span style={dateLabelStyle}>Desde</span>
          <input
            type="date"
            value={desde}
            onChange={(event) => setDesde(event.target.value)}
            style={inputStyle}
            className="admin-dark-select"
          />
        </label>
        <label style={dateFieldStyle}>
          <span style={dateLabelStyle}>Hasta</span>
          <input
            type="date"
            value={hasta}
            onChange={(event) => setHasta(event.target.value)}
            style={inputStyle}
            className="admin-dark-select"
          />
        </label>
        <button type="submit" style={secondaryButtonStyle} disabled={loading}>
          {loading ? 'Buscando...' : 'Buscar'}
        </button>
      </form>

      {feedback ? <div style={feedbackStyle(feedbackType)}>{feedback}</div> : null}

      {loading ? <div style={emptyStateStyle}>Cargando notas de entrega...</div> : null}
      {!loading && error ? <div style={errorStyle}>{error}</div> : null}
      {!loading && !error && notas.length === 0 ? (
        <div style={emptyStateStyle}>No hay notas de entrega registradas en ese rango de fechas.</div>
      ) : null}

      {!loading && !error && notas.length > 0 ? (
        <div style={layoutStyle(isMobile)}>
          <div style={listStyle}>
            {notas.map((nota) => (
              <div key={nota.id} style={notaRowStyle(selectedNotaId === nota.id)}>
                <div style={{ display: 'grid', gap: 2 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                    <span style={{ color: '#fff', fontWeight: 700 }}>Nota de entrega {nota.codigo}</span>
                    <span style={estadoBadgeStyle(nota.estado)}>{estadoLabel(nota.estado)}</span>
                  </div>
                  <div style={{ color: '#d2c4c4', fontSize: 13 }}>
                    {nota.metodo_pago}
                    {' · '}
                    {new Date(nota.fecha_emision).toLocaleString('es-VE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
                    {' · '}
                    {nota.pedidos.length} pedido(s)
                  </div>
                  <div style={{ color: '#ffcf7d', fontWeight: 700 }}>
                    Total: {formatMontoDocumento(nota.total, nota.moneda, nota.tasa_cambio_referencia || tasaCambio)}
                  </div>
                  {nota.estado !== 'pagada' ? (
                    <div style={{ color: '#ff9b9b', fontWeight: 700 }}>
                      Saldo: {formatMontoDocumento(nota.saldo_pendiente, nota.moneda, nota.tasa_cambio_referencia || tasaCambio)}
                    </div>
                  ) : null}
                </div>
                <div style={rowActionsStyle}>
                  <button type="button" onClick={() => handleSelectNota(nota)} style={secondaryButtonStyle}>
                    Ver / Abonar
                  </button>
                  <button
                    type="button"
                    onClick={() => handleReimprimir(nota)}
                    style={secondaryButtonStyle}
                    disabled={reprintingId === nota.id}
                  >
                    {reprintingId === nota.id ? 'Enviando...' : 'Reimprimir'}
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div style={detailPanelStyle}>
            {!selectedNotaId ? (
              <div style={emptyStateStyle}>Selecciona una nota de entrega para ver su detalle y registrar un abono.</div>
            ) : loadingDetalle || !notaDetalle ? (
              <div style={emptyStateStyle}>Cargando nota de entrega...</div>
            ) : (
              <>
                <div style={{ color: '#ffb0b0', fontWeight: 800, fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                  Nota de entrega {notaDetalle.codigo}
                </div>
                <div style={{ color: '#d2c4c4', fontSize: 13 }}>
                  {notaDetalle.metodo_pago}
                  {' · '}
                  {new Date(notaDetalle.fecha_emision).toLocaleString('es-VE')}
                  {' · '}
                  {notaDetalle.pedidos.length} pedido(s)
                </div>

                <div style={detailTotalsStyle}>
                  <span style={{ fontWeight: 800, color: '#fff' }}>
                    Total: {formatMontoDocumento(notaDetalle.total, notaDetalle.moneda, notaDetalle.tasa_cambio_referencia || tasaCambio)}
                  </span>
                  <span style={{ fontWeight: 800, color: '#ffcf7d' }}>
                    Saldo pendiente: {formatMontoDocumento(notaDetalle.saldo_pendiente, notaDetalle.moneda, notaDetalle.tasa_cambio_referencia || tasaCambio)}
                  </span>
                </div>

                {notaDetalle.pagos.length > 0 ? (
                  <div style={{ display: 'grid', gap: 4 }}>
                    <div style={{ color: '#9fe3b0', fontWeight: 700, fontSize: 12, textTransform: 'uppercase' }}>Abonos registrados</div>
                    {notaDetalle.pagos.map((pago) => (
                      <div key={pago.id} style={lineaRowStyle}>
                        <span>{pago.metodo_pago} — {new Date(pago.fecha_pago).toLocaleString('es-VE')}</span>
                        <span>{formatMontoDocumento(pago.monto, notaDetalle.moneda, notaDetalle.tasa_cambio_referencia || tasaCambio)}</span>
                      </div>
                    ))}
                  </div>
                ) : null}

                {notaDetalle.estado !== 'pagada' ? (
                  <form onSubmit={handleRegistrarAbono} style={abonoFormStyle(isMobile)}>
                    <input
                      type="number"
                      min="0.01"
                      step="0.01"
                      placeholder={notaDetalle.moneda === 'VES' ? 'Monto del abono (Bs)' : 'Monto del abono ($)'}
                      value={montoAbono}
                      onChange={(event) => setMontoAbono(event.target.value)}
                      style={inputStyle}
                      required
                    />
                    <select
                      value={metodoAbono || (metodosPago[0] && metodosPago[0].id) || ''}
                      onChange={(event) => setMetodoAbono(Number(event.target.value))}
                      style={selectStyle}
                      className="admin-dark-select"
                    >
                      {metodosPago.map((metodo) => (
                        <option key={metodo.id} value={metodo.id}>{metodo.nombre}</option>
                      ))}
                    </select>
                    <button type="submit" style={primaryButtonStyle} disabled={savingAbono}>
                      {savingAbono ? 'Registrando...' : 'Registrar abono'}
                    </button>
                  </form>
                ) : (
                  <div style={{ color: '#9fe3b0', fontWeight: 700 }}>Esta nota de entrega ya esta saldada.</div>
                )}
              </>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}

const containerStyle = (isMobile, embedded) => ({
  display: 'grid',
  gap: 16,
  padding: embedded ? 0 : (isMobile ? 4 : 8),
});

const embeddedHeaderStyle = {
  color: '#ffb0b0',
  fontWeight: 800,
  fontSize: 13,
  textTransform: 'uppercase',
  letterSpacing: '0.1em',
};

const headerWrapStyle = (isMobile) => ({
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: isMobile ? 'flex-start' : 'center',
  flexDirection: isMobile ? 'column' : 'row',
  gap: 12,
});

const eyebrowStyle = {
  fontSize: 12,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
  color: '#f7a5a5',
  marginBottom: 8,
};

const titleStyle = (isMobile) => ({
  margin: 0,
  color: '#fff',
  fontSize: isMobile ? 26 : 32,
  fontWeight: 700,
});

const subtitleStyle = {
  margin: '8px 0 0',
  color: '#d2c3c3',
  lineHeight: 1.6,
  maxWidth: 640,
};

const backButtonStyle = (isMobile) => ({
  border: '1px solid rgba(255, 115, 115, 0.34)',
  borderRadius: 999,
  padding: isMobile ? '11px 16px' : '10px 16px',
  background: 'rgba(255,255,255,0.03)',
  color: '#fff',
  fontWeight: 600,
  cursor: 'pointer',
  width: isMobile ? '100%' : 'auto',
});

const buscadorFormStyle = (isMobile) => ({
  display: 'flex',
  flexDirection: isMobile ? 'column' : 'row',
  alignItems: isMobile ? 'stretch' : 'flex-end',
  gap: 8,
});

const dateFieldStyle = {
  display: 'grid',
  gap: 4,
};

const dateLabelStyle = {
  fontSize: 11,
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  color: '#d2c4c4',
};

const inputStyle = {
  boxSizing: 'border-box',
  borderRadius: 12,
  border: '1px solid rgba(255, 255, 255, 0.14)',
  background: '#161010',
  padding: '9px 10px',
  color: '#fff4f4',
  fontSize: 13,
};

const secondaryButtonStyle = {
  border: '1px solid rgba(255, 173, 173, 0.35)',
  borderRadius: 12,
  padding: '9px 14px',
  background: 'rgba(255, 255, 255, 0.02)',
  color: '#ffe0e0',
  fontWeight: 600,
  cursor: 'pointer',
};

const emptyStateStyle = {
  minHeight: 80,
  display: 'grid',
  placeItems: 'center',
  borderRadius: 24,
  border: '1px dashed rgba(255, 255, 255, 0.14)',
  background: 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)',
  color: '#c8bbbb',
  textAlign: 'center',
  padding: 20,
};

const errorStyle = {
  padding: '12px 14px',
  borderRadius: 16,
  border: '1px solid rgba(255, 145, 145, 0.22)',
  background: 'rgba(255, 98, 98, 0.12)',
  color: '#ffd8d8',
};

const feedbackStyle = (feedbackType) => ({
  borderRadius: 12,
  border: feedbackType === 'error' ? '1px solid rgba(223, 102, 102, 0.5)' : '1px solid rgba(82, 206, 123, 0.35)',
  background: feedbackType === 'error' ? 'rgba(102, 29, 29, 0.55)' : 'rgba(31, 89, 48, 0.45)',
  color: feedbackType === 'error' ? '#ffe2e2' : '#dbffe4',
  padding: '10px 12px',
  fontSize: 13,
});

const layoutStyle = (isMobile) => ({
  display: 'grid',
  gridTemplateColumns: isMobile ? '1fr' : 'minmax(280px, 380px) 1fr',
  gap: 16,
  alignItems: 'start',
});

const listStyle = {
  display: 'grid',
  gap: 10,
};

const notaRowStyle = (selected) => ({
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 12,
  flexWrap: 'wrap',
  padding: '14px 16px',
  borderRadius: 16,
  border: selected ? '1px solid rgba(255, 130, 130, 0.6)' : '1px solid rgba(255, 255, 255, 0.1)',
  background: selected ? 'rgba(255, 90, 90, 0.12)' : 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)',
});

const rowActionsStyle = {
  display: 'flex',
  flexDirection: 'column',
  gap: 6,
};

const estadoBadgeStyle = (estado) => ({
  padding: '3px 10px',
  borderRadius: 999,
  fontSize: 11,
  fontWeight: 800,
  textTransform: 'uppercase',
  height: 'fit-content',
  background: estado === 'pagada' ? 'rgba(82, 206, 123, 0.16)' : 'rgba(255, 200, 120, 0.16)',
  color: estado === 'pagada' ? '#9fe3b0' : '#ffcf7d',
});

const detailPanelStyle = {
  display: 'grid',
  gap: 12,
  padding: '18px 18px',
  borderRadius: 20,
  background: 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)',
  border: '1px solid rgba(255, 255, 255, 0.1)',
  boxShadow: '0 12px 28px rgba(0,0,0,0.24)',
  minHeight: 200,
};

const lineaRowStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  fontSize: 13,
  color: '#e8dede',
};

const detailTotalsStyle = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 14,
  paddingTop: 8,
  borderTop: '1px solid rgba(255, 255, 255, 0.06)',
  color: '#d2c4c4',
  fontSize: 13,
};

const abonoFormStyle = (isMobile) => ({
  display: 'grid',
  gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr auto',
  gap: 8,
  paddingTop: 10,
  borderTop: '1px solid rgba(255, 255, 255, 0.08)',
});

const selectStyle = {
  ...inputStyle,
  appearance: 'auto',
  colorScheme: 'dark',
  cursor: 'pointer',
};

const primaryButtonStyle = {
  border: 'none',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'linear-gradient(90deg, #1f7a3f 0%, #34d399 100%)',
  color: '#04140a',
  fontWeight: 800,
  cursor: 'pointer',
};

export default NotasEntregaHistorialPage;

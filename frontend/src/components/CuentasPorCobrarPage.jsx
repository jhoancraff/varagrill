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

function CuentasPorCobrarPage({ isMobile, onBack, embedded = false, refreshToken }) {
  const tasaCambio = useExchangeRate();
  const [ordenes, setOrdenes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [metodosPago, setMetodosPago] = useState([]);
  const [selectedFacturaId, setSelectedFacturaId] = useState(null);
  const [facturaDetalle, setFacturaDetalle] = useState(null);
  const [loadingDetalle, setLoadingDetalle] = useState(false);
  const [montoAbono, setMontoAbono] = useState('');
  const [metodoAbono, setMetodoAbono] = useState('');
  const [savingAbono, setSavingAbono] = useState(false);
  const [feedback, setFeedback] = useState('');
  const [feedbackType, setFeedbackType] = useState('success');

  const fetchOrdenes = useCallback(async () => {
    try {
      const response = await fetch('/api/cuentas-por-cobrar/', { credentials: 'include', cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setError(data.message || 'No se pudieron cargar las cuentas por cobrar.');
        return;
      }
      setOrdenes(Array.isArray(data.ordenes_cobro) ? data.ordenes_cobro : []);
      setError('');
    } catch (requestError) {
      setError('Error de red al cargar las cuentas por cobrar.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    fetchOrdenes();
    // refreshToken: cuando el padre (Cobro) emite una factura nueva, incrementa este
    // valor para forzar un refetch aca sin tener que desmontar/remontar el componente
    // embebido (que perderia la factura seleccionada y su detalle en pantalla).
  }, [fetchOrdenes, refreshToken]);

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

  const fetchFacturaDetalle = useCallback(async (facturaId) => {
    setLoadingDetalle(true);
    try {
      const response = await fetch(`/api/facturas/${facturaId}/`, { credentials: 'include', cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setFeedbackType('error');
        setFeedback(data.message || 'No se pudo cargar el detalle de la factura.');
        return;
      }
      setFacturaDetalle(data.factura);
    } catch (requestError) {
      setFeedbackType('error');
      setFeedback('Error de red al cargar el detalle de la factura.');
    } finally {
      setLoadingDetalle(false);
    }
  }, []);

  const handleSelectOrden = (orden) => {
    setFeedback('');
    setMontoAbono('');
    setSelectedFacturaId(orden.factura.id);
    fetchFacturaDetalle(orden.factura.id);
  };

  const handleRegistrarAbono = async (event) => {
    event.preventDefault();
    if (!selectedFacturaId) {
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
      const response = await fetch(`/api/facturas/${selectedFacturaId}/abonos/`, {
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
      setFeedback(`Abono de $${data.pago.monto} registrado. Saldo pendiente: $${data.factura.saldo_pendiente}.`);
      setFacturaDetalle(data.factura);
      setMontoAbono('');
      await fetchOrdenes();
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
            <h2 style={titleStyle(isMobile)}>Cuentas por cobrar</h2>
            <p style={subtitleStyle}>
              Facturas emitidas con saldo pendiente. Selecciona una para registrar los abonos hasta saldarla.
            </p>
          </div>
          <button type="button" onClick={onBack} style={backButtonStyle(isMobile)}>
            Volver
          </button>
        </div>
      ) : (
        <div style={embeddedHeaderStyle}>Cuentas por cobrar</div>
      )}

      {feedback ? <div style={feedbackStyle(feedbackType)}>{feedback}</div> : null}

      {loading ? <div style={emptyStateStyle}>Cargando cuentas por cobrar...</div> : null}
      {!loading && error ? <div style={errorStyle}>{error}</div> : null}
      {!loading && !error && ordenes.length === 0 ? (
        <div style={emptyStateStyle}>No hay deudas pendientes por cobrar en este momento.</div>
      ) : null}

      {!loading && !error && ordenes.length > 0 ? (
        <div style={layoutStyle(isMobile)}>
          <div style={listStyle}>
            {ordenes.map((orden) => (
              <button
                key={orden.id}
                type="button"
                onClick={() => handleSelectOrden(orden)}
                style={ordenCardStyle(selectedFacturaId === orden.factura.id)}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                  <span style={{ color: '#fff', fontWeight: 700 }}>Factura {orden.factura.codigo}</span>
                  <span style={estadoBadgeStyle(orden.estado)}>{estadoLabel(orden.estado)}</span>
                </div>
                <div style={{ color: '#d2c4c4', fontSize: 13 }}>
                  {orden.factura.cliente ? orden.factura.cliente.nombre : 'Consumidor Final'}
                </div>
                <div style={{ color: '#ffcf7d', fontWeight: 700 }}>
                  Saldo: {formatMontoDocumento(orden.saldo_pendiente, orden.factura.moneda, orden.factura.tasa_cambio_referencia || tasaCambio)}
                </div>
              </button>
            ))}
          </div>

          <div style={detailPanelStyle}>
            {!selectedFacturaId ? (
              <div style={emptyStateStyle}>Selecciona una factura para ver su detalle y registrar un abono.</div>
            ) : loadingDetalle || !facturaDetalle ? (
              <div style={emptyStateStyle}>Cargando factura...</div>
            ) : (
              <>
                <div style={{ color: '#ffb0b0', fontWeight: 800, fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                  Factura {facturaDetalle.codigo} · Control {facturaDetalle.numero_control}
                </div>
                <div style={{ color: '#d2c4c4', fontSize: 13 }}>
                  Cliente: {facturaDetalle.cliente ? facturaDetalle.cliente.nombre : 'Consumidor Final'}
                  {facturaDetalle.cliente && facturaDetalle.cliente.numero_documento
                    ? ` (${facturaDetalle.cliente.tipo_documento}-${facturaDetalle.cliente.numero_documento})`
                    : ''}
                </div>

                <div style={{ display: 'grid', gap: 4 }}>
                  {facturaDetalle.lineas.map((linea) => (
                    <div key={linea.id} style={lineaRowStyle}>
                      <span>{linea.cantidad}x {linea.descripcion}</span>
                      <span>{formatMontoDocumento(linea.subtotal, facturaDetalle.moneda, facturaDetalle.tasa_cambio_referencia || tasaCambio)}</span>
                    </div>
                  ))}
                </div>

                <div style={detailTotalsStyle}>
                  <span>Subtotal: {formatMontoDocumento(facturaDetalle.subtotal, facturaDetalle.moneda, facturaDetalle.tasa_cambio_referencia || tasaCambio)}</span>
                  <span>IVA: {formatMontoDocumento(facturaDetalle.total_iva, facturaDetalle.moneda, facturaDetalle.tasa_cambio_referencia || tasaCambio)}</span>
                  <span style={{ fontWeight: 800, color: '#fff' }}>Total: {formatMontoDocumento(facturaDetalle.total, facturaDetalle.moneda, facturaDetalle.tasa_cambio_referencia || tasaCambio)}</span>
                  <span style={{ fontWeight: 800, color: '#ffcf7d' }}>Saldo pendiente: {formatMontoDocumento(facturaDetalle.saldo_pendiente, facturaDetalle.moneda, facturaDetalle.tasa_cambio_referencia || tasaCambio)}</span>
                </div>

                {facturaDetalle.pagos.length > 0 ? (
                  <div style={{ display: 'grid', gap: 4 }}>
                    <div style={{ color: '#9fe3b0', fontWeight: 700, fontSize: 12, textTransform: 'uppercase' }}>Abonos registrados</div>
                    {facturaDetalle.pagos.map((pago) => (
                      <div key={pago.id} style={lineaRowStyle}>
                        <span>{pago.metodo_pago} — {new Date(pago.fecha_pago).toLocaleString('es-VE')}</span>
                        <span>{formatMontoDocumento(pago.monto, facturaDetalle.moneda, facturaDetalle.tasa_cambio_referencia || tasaCambio)}</span>
                      </div>
                    ))}
                  </div>
                ) : null}

                {facturaDetalle.estado !== 'pagada' && facturaDetalle.estado !== 'anulada' ? (
                  <form onSubmit={handleRegistrarAbono} style={abonoFormStyle(isMobile)}>
                    <input
                      type="number"
                      min="0.01"
                      step="0.01"
                      placeholder="Monto del abono"
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
                  <div style={{ color: '#9fe3b0', fontWeight: 700 }}>Esta factura ya esta saldada.</div>
                )}
              </>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function estadoLabel(estado) {
  if (estado === 'pendiente') return 'Pendiente';
  if (estado === 'parcial') return 'Abonada';
  if (estado === 'saldada') return 'Saldada';
  return estado;
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

const emptyStateStyle = {
  minHeight: 100,
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
  gridTemplateColumns: isMobile ? '1fr' : 'minmax(260px, 340px) 1fr',
  gap: 16,
  alignItems: 'start',
});

const listStyle = {
  display: 'grid',
  gap: 10,
};

const ordenCardStyle = (selected) => ({
  display: 'grid',
  gap: 6,
  textAlign: 'left',
  padding: '14px 16px',
  borderRadius: 16,
  border: selected ? '1px solid rgba(255, 130, 130, 0.6)' : '1px solid rgba(255, 255, 255, 0.1)',
  background: selected ? 'rgba(255, 90, 90, 0.12)' : 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)',
  color: '#fff',
  cursor: 'pointer',
});

const estadoBadgeStyle = (estado) => ({
  padding: '3px 10px',
  borderRadius: 999,
  fontSize: 11,
  fontWeight: 800,
  textTransform: 'uppercase',
  height: 'fit-content',
  background: estado === 'pendiente' ? 'rgba(255, 145, 145, 0.16)' : 'rgba(255, 200, 120, 0.16)',
  color: estado === 'pendiente' ? '#ff9b9b' : '#ffcf7d',
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

const inputStyle = {
  width: '100%',
  boxSizing: 'border-box',
  borderRadius: 12,
  border: '1px solid rgba(255, 255, 255, 0.14)',
  background: '#161010',
  padding: '9px 10px',
  color: '#fff4f4',
  fontSize: 13,
};

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

export default CuentasPorCobrarPage;

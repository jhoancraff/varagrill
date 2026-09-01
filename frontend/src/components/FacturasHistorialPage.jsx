import { useCallback, useEffect, useState } from 'react';
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
  if (estado === 'pendiente_pago') return 'Pendiente de pago';
  if (estado === 'abonada_parcial') return 'Abonada parcial';
  if (estado === 'pagada') return 'Pagada';
  if (estado === 'anulada') return 'Anulada';
  return estado;
}

function FacturasHistorialPage({ isMobile, onBack, embedded = false }) {
  const [fecha, setFecha] = useState(hoyISO);
  const [facturas, setFacturas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reprintingId, setReprintingId] = useState(null);
  const [feedback, setFeedback] = useState('');
  const [feedbackType, setFeedbackType] = useState('success');

  const fetchFacturas = useCallback(async (fechaBuscada) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (fechaBuscada) {
        params.set('desde', fechaBuscada);
        params.set('hasta', fechaBuscada);
      }
      const response = await fetch(`/api/facturas/?${params.toString()}`, { credentials: 'include', cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setError(data.message || 'No se pudieron cargar las facturas.');
        return;
      }
      setFacturas(Array.isArray(data.facturas) ? data.facturas : []);
      setError('');
    } catch (requestError) {
      setError('Error de red al cargar las facturas.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFacturas(fecha);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleBuscar = (event) => {
    event.preventDefault();
    fetchFacturas(fecha);
  };

  const handleReimprimir = async (factura) => {
    setReprintingId(factura.id);
    setFeedback('');
    try {
      const response = await fetch(`/api/facturas/${factura.id}/reimprimir/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrftoken') || '' },
        credentials: 'include',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setFeedbackType('error');
        setFeedback(data.message || 'No se pudo reimprimir la factura.');
        return;
      }
      setFeedbackType('success');
      setFeedback(data.message || `Factura ${factura.codigo} reenviada a la impresora.`);
    } catch (requestError) {
      setFeedbackType('error');
      setFeedback('Error de red al reimprimir la factura.');
    } finally {
      setReprintingId(null);
    }
  };

  return (
    <section style={containerStyle(isMobile, embedded)}>
      {!embedded ? (
        <div style={headerWrapStyle(isMobile)}>
          <div>
            <div style={eyebrowStyle}>Contabilidad</div>
            <h2 style={titleStyle(isMobile)}>Historial de facturas</h2>
            <p style={subtitleStyle}>
              Busca una factura ya emitida por fecha y reimprímela si el cliente necesita otra copia.
            </p>
          </div>
          <button type="button" onClick={onBack} style={backButtonStyle(isMobile)}>
            Volver
          </button>
        </div>
      ) : (
        <div style={embeddedHeaderStyle}>Historial de facturas · Reimprimir</div>
      )}

      <form onSubmit={handleBuscar} style={buscadorFormStyle(isMobile)}>
        <input
          type="date"
          value={fecha}
          onChange={(event) => setFecha(event.target.value)}
          style={inputStyle}
          className="admin-dark-select"
        />
        <button type="submit" style={secondaryButtonStyle} disabled={loading}>
          {loading ? 'Buscando...' : 'Buscar'}
        </button>
      </form>

      {feedback ? <div style={feedbackStyle(feedbackType)}>{feedback}</div> : null}

      {loading ? <div style={emptyStateStyle}>Cargando facturas...</div> : null}
      {!loading && error ? <div style={errorStyle}>{error}</div> : null}
      {!loading && !error && facturas.length === 0 ? (
        <div style={emptyStateStyle}>No hay facturas emitidas en esa fecha.</div>
      ) : null}

      {!loading && !error && facturas.length > 0 ? (
        <div style={listStyle}>
          {facturas.map((factura) => (
            <div key={factura.id} style={facturaRowStyle}>
              <div style={{ display: 'grid', gap: 2 }}>
                <div style={{ color: '#fff', fontWeight: 700 }}>
                  Factura {factura.codigo}
                  <span style={estadoBadgeStyle(factura.estado)}>{estadoLabel(factura.estado)}</span>
                </div>
                <div style={{ color: '#d2c4c4', fontSize: 13 }}>
                  {factura.cliente ? factura.cliente.nombre : 'Consumidor Final'}
                  {' · '}
                  {new Date(factura.fecha_emision).toLocaleTimeString('es-VE', { hour: '2-digit', minute: '2-digit' })}
                </div>
                <div style={{ color: '#ffcf7d', fontWeight: 700 }}>
                  {formatMontoDocumento(factura.total, factura.moneda, factura.tasa_cambio_referencia)}
                </div>
              </div>
              <button
                type="button"
                onClick={() => handleReimprimir(factura)}
                style={secondaryButtonStyle}
                disabled={reprintingId === factura.id}
              >
                {reprintingId === factura.id ? 'Enviando...' : 'Reimprimir'}
              </button>
            </div>
          ))}
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
  gap: 8,
});

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

const listStyle = {
  display: 'grid',
  gap: 10,
};

const facturaRowStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 12,
  flexWrap: 'wrap',
  padding: '14px 16px',
  borderRadius: 16,
  border: '1px solid rgba(255, 255, 255, 0.1)',
  background: 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)',
};

const estadoBadgeStyle = (estado) => ({
  marginLeft: 8,
  padding: '3px 10px',
  borderRadius: 999,
  fontSize: 11,
  fontWeight: 800,
  textTransform: 'uppercase',
  background: estado === 'anulada' ? 'rgba(255, 145, 145, 0.16)' : 'rgba(255, 200, 120, 0.16)',
  color: estado === 'anulada' ? '#ff9b9b' : '#ffcf7d',
});

export default FacturasHistorialPage;

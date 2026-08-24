import { useCallback, useEffect, useState } from 'react';
import BsAmount from './BsAmount';
import useExchangeRate from '../hooks/useExchangeRate';

const FILTROS = [
  { value: '', label: 'Todas' },
  { value: 'pendiente_pago', label: 'Pendientes' },
  { value: 'abonada_parcial', label: 'Abonadas' },
  { value: 'pagada', label: 'Pagadas' },
  { value: 'anulada', label: 'Anuladas' },
];

function HistorialFacturasPage({ isMobile, onBack }) {
  const tasaCambio = useExchangeRate();
  const [facturas, setFacturas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [estadoFiltro, setEstadoFiltro] = useState('');
  const [expandedId, setExpandedId] = useState(null);
  const [detalleById, setDetalleById] = useState({});
  const [loadingDetalleId, setLoadingDetalleId] = useState(null);

  const fetchFacturas = useCallback(async (estado) => {
    setLoading(true);
    try {
      const query = estado ? `?estado=${encodeURIComponent(estado)}` : '';
      const response = await fetch(`/api/facturas/${query}`, { credentials: 'include', cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setError(data.message || 'No se pudo cargar el historial de facturas.');
        return;
      }
      setFacturas(Array.isArray(data.facturas) ? data.facturas : []);
      setError('');
    } catch (requestError) {
      setError('Error de red al cargar el historial de facturas.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFacturas(estadoFiltro);
  }, [estadoFiltro, fetchFacturas]);

  const toggleExpand = async (factura) => {
    if (expandedId === factura.id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(factura.id);
    if (detalleById[factura.id]) {
      return;
    }
    setLoadingDetalleId(factura.id);
    try {
      const response = await fetch(`/api/facturas/${factura.id}/`, { credentials: 'include', cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (response.ok && data.ok) {
        setDetalleById((current) => ({ ...current, [factura.id]: data.factura }));
      }
    } catch (requestError) {
      // El detalle simplemente no se muestra si falla; se puede reintentar cerrando y abriendo.
    } finally {
      setLoadingDetalleId(null);
    }
  };

  return (
    <section style={containerStyle(isMobile)}>
      <div style={headerWrapStyle(isMobile)}>
        <div>
          <div style={eyebrowStyle}>Contabilidad</div>
          <h2 style={titleStyle(isMobile)}>Historial de facturas</h2>
          <p style={subtitleStyle}>
            Todas las facturas emitidas, con su estado y el detalle de los abonos que se le registraron —
            incluidas las ya saldadas.
          </p>
        </div>
        <button type="button" onClick={onBack} style={backButtonStyle(isMobile)}>
          Volver
        </button>
      </div>

      <div style={filtrosRowStyle}>
        {FILTROS.map((filtro) => (
          <button
            key={filtro.value || 'todas'}
            type="button"
            onClick={() => setEstadoFiltro(filtro.value)}
            style={filtroButtonStyle(estadoFiltro === filtro.value)}
          >
            {filtro.label}
          </button>
        ))}
      </div>

      {loading ? <div style={emptyStateStyle}>Cargando facturas...</div> : null}
      {!loading && error ? <div style={errorStyle}>{error}</div> : null}
      {!loading && !error && facturas.length === 0 ? (
        <div style={emptyStateStyle}>No hay facturas para este filtro.</div>
      ) : null}

      {!loading && !error && facturas.length > 0 ? (
        <div style={listStyle}>
          {facturas.map((factura) => {
            const isExpanded = expandedId === factura.id;
            const detalle = detalleById[factura.id];

            return (
              <article key={factura.id} style={cardStyle}>
                <button type="button" onClick={() => toggleExpand(factura)} style={cardHeaderButtonStyle}>
                  <div style={{ display: 'grid', gap: 2, textAlign: 'left' }}>
                    <span style={{ color: '#fff', fontWeight: 700 }}>Factura {factura.codigo} · Control {factura.numero_control}</span>
                    <span style={{ color: '#d2c4c4', fontSize: 12 }}>
                      {factura.cliente ? factura.cliente.nombre : 'Consumidor Final'} · {new Date(factura.fecha_emision).toLocaleString('es-VE')}
                    </span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span style={estadoBadgeStyle(factura.estado)}>{estadoLabel(factura.estado)}</span>
                    <span style={{ color: '#ffcf7d', fontWeight: 700 }}>
                      ${factura.total}
                      <BsAmount amountUsd={factura.total} tasa={tasaCambio} />
                    </span>
                  </div>
                </button>

                {isExpanded ? (
                  <div style={detailWrapStyle}>
                    {loadingDetalleId === factura.id || !detalle ? (
                      <div style={emptyStateStyle}>Cargando detalle...</div>
                    ) : (
                      <>
                        <div style={{ display: 'grid', gap: 4 }}>
                          {detalle.lineas.map((linea) => (
                            <div key={linea.id} style={lineaRowStyle}>
                              <span>{linea.cantidad}x {linea.descripcion}</span>
                              <span>${linea.subtotal}</span>
                            </div>
                          ))}
                        </div>

                        <div style={detailTotalsStyle}>
                          <span>Subtotal: ${detalle.subtotal}</span>
                          <span>IVA: ${detalle.total_iva}</span>
                          <span style={{ fontWeight: 800, color: '#fff' }}>Total: ${detalle.total}</span>
                          <span>Saldo pendiente: ${detalle.saldo_pendiente}</span>
                        </div>

                        {detalle.motivo_anulacion ? (
                          <div style={detailNoteStyle}>Motivo de anulación: {detalle.motivo_anulacion}</div>
                        ) : null}

                        {detalle.pagos.length > 0 ? (
                          <div style={{ display: 'grid', gap: 4 }}>
                            <div style={{ color: '#9fe3b0', fontWeight: 700, fontSize: 12, textTransform: 'uppercase' }}>
                              Abonos registrados
                            </div>
                            {detalle.pagos.map((pago) => (
                              <div key={pago.id} style={lineaRowStyle}>
                                <span>{pago.metodo_pago} — {new Date(pago.fecha_pago).toLocaleString('es-VE')} — {pago.creado_por}</span>
                                <span>${pago.monto}</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div style={{ color: '#d2c4c4', fontSize: 13 }}>Aún no se ha registrado ningún abono.</div>
                        )}
                      </>
                    )}
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}

function estadoLabel(estado) {
  if (estado === 'pendiente_pago') return 'Pendiente';
  if (estado === 'abonada_parcial') return 'Abonada';
  if (estado === 'pagada') return 'Pagada';
  if (estado === 'anulada') return 'Anulada';
  return estado;
}

const containerStyle = (isMobile) => ({
  display: 'grid',
  gap: 16,
  padding: isMobile ? 4 : 8,
});

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

const filtrosRowStyle = {
  display: 'flex',
  gap: 8,
  flexWrap: 'wrap',
};

const filtroButtonStyle = (active) => ({
  border: active ? '1px solid rgba(255, 130, 130, 0.6)' : '1px solid rgba(255, 255, 255, 0.14)',
  borderRadius: 999,
  padding: '8px 14px',
  background: active ? 'rgba(255, 90, 90, 0.16)' : 'rgba(255, 255, 255, 0.03)',
  color: '#fff',
  fontSize: 13,
  fontWeight: 700,
  cursor: 'pointer',
});

const emptyStateStyle = {
  minHeight: 80,
  display: 'grid',
  placeItems: 'center',
  borderRadius: 20,
  border: '1px dashed rgba(255, 255, 255, 0.14)',
  background: 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)',
  color: '#c8bbbb',
  textAlign: 'center',
  padding: 16,
};

const errorStyle = {
  padding: '12px 14px',
  borderRadius: 16,
  border: '1px solid rgba(255, 145, 145, 0.22)',
  background: 'rgba(255, 98, 98, 0.12)',
  color: '#ffd8d8',
};

const listStyle = {
  display: 'grid',
  gap: 10,
};

const cardStyle = {
  borderRadius: 18,
  border: '1px solid rgba(255, 255, 255, 0.1)',
  background: 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)',
  overflow: 'hidden',
};

const cardHeaderButtonStyle = {
  width: '100%',
  boxSizing: 'border-box',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 10,
  padding: '14px 16px',
  border: 'none',
  background: 'transparent',
  cursor: 'pointer',
};

const estadoBadgeStyle = (estado) => ({
  padding: '3px 10px',
  borderRadius: 999,
  fontSize: 11,
  fontWeight: 800,
  textTransform: 'uppercase',
  background:
    estado === 'pagada' ? 'rgba(82, 206, 123, 0.16)'
      : estado === 'anulada' ? 'rgba(160, 160, 160, 0.16)'
        : 'rgba(255, 200, 120, 0.16)',
  color:
    estado === 'pagada' ? '#7be69b'
      : estado === 'anulada' ? '#c9c9c9'
        : '#ffcf7d',
});

const detailWrapStyle = {
  display: 'grid',
  gap: 8,
  padding: '4px 16px 16px',
  borderTop: '1px solid rgba(255, 255, 255, 0.06)',
};

const lineaRowStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  fontSize: 13,
  color: '#e8dede',
};

const detailNoteStyle = {
  padding: '8px 10px',
  borderRadius: 10,
  background: 'rgba(255, 145, 145, 0.1)',
  border: '1px solid rgba(255, 145, 145, 0.2)',
  color: '#ffd8d8',
  fontSize: 13,
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

export default HistorialFacturasPage;

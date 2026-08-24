import { useEffect, useState } from 'react';

function AnalystComprasPage({ isMobile, onBack }) {
  const [compras, setCompras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expandedId, setExpandedId] = useState(null);

  useEffect(() => {
    const loadCompras = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/admin/compras/', { credentials: 'include', cache: 'no-store' });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.ok) {
          setError(data.message || 'No se pudo cargar el historial de compras.');
          return;
        }
        setCompras(Array.isArray(data.compras) ? data.compras : []);
        setError('');
      } catch (requestError) {
        setError('Error de red al cargar el historial de compras.');
      } finally {
        setLoading(false);
      }
    };
    loadCompras();
  }, []);

  const toggleExpand = (compraId) => {
    setExpandedId((current) => (current === compraId ? null : compraId));
  };

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>
        ← Volver
      </button>

      <div>
        <h2 style={titleStyle(isMobile)}>Historial de compras</h2>
        <p style={subtitleStyle}>
          Cada lote de ingredientes cargado al inventario — de qué proveedor y factura vino, cuándo se cargó y
          qué ingredientes trajo, con su costo.
        </p>
      </div>

      {loading ? <div style={emptyStateStyle}>Cargando compras...</div> : null}
      {!loading && error ? <div style={errorStyle}>{error}</div> : null}
      {!loading && !error && compras.length === 0 ? (
        <div style={emptyStateStyle}>Todavía no hay lotes de compra registrados.</div>
      ) : null}

      {!loading && !error && compras.length > 0 ? (
        <div style={listStyle}>
          {compras.map((compra) => {
            const isExpanded = expandedId === compra.id;
            return (
              <article key={compra.id} style={cardStyle}>
                <button type="button" onClick={() => toggleExpand(compra.id)} style={cardHeaderButtonStyle}>
                  <div style={{ display: 'grid', gap: 2, textAlign: 'left' }}>
                    <span style={{ color: '#fff', fontWeight: 700 }}>
                      Lote #{compra.id} — {compra.proveedor_nombre}
                    </span>
                    <span style={{ color: '#d2c4c4', fontSize: 12 }}>
                      {compra.numero_factura_proveedor ? `Factura ${compra.numero_factura_proveedor} · ` : ''}
                      {compra.fecha_factura ? `Fecha factura ${compra.fecha_factura} · ` : ''}
                      Cargado el {new Date(compra.fecha_creacion).toLocaleString('es-VE')} por {compra.creado_por || '—'}
                    </span>
                  </div>
                  <span style={{ color: '#ffcf7d', fontWeight: 700 }}>${compra.total}</span>
                </button>

                {isExpanded ? (
                  <div style={detailWrapStyle}>
                    {(compra.detalles || []).length === 0 ? (
                      <div style={{ color: '#c8bbbb', fontSize: 13 }}>Este lote no tiene ingredientes registrados.</div>
                    ) : (
                      compra.detalles.map((detalle) => (
                        <div key={detalle.id} style={lineaRowStyle}>
                          <span>{detalle.cantidad} {detalle.unidad_medida} — {detalle.ingrediente_nombre}</span>
                          <span>${detalle.costo_unitario}/u · ${detalle.subtotal}</span>
                        </div>
                      ))
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

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const backButtonStyle = {
  display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999,
  padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff',
  fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)',
};
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: '#d2c3c3', lineHeight: 1.6, maxWidth: 720 };

const emptyStateStyle = {
  minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 20,
  border: '1px dashed rgba(255, 255, 255, 0.14)',
  background: 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)',
  color: '#c8bbbb', textAlign: 'center', padding: 16,
};
const errorStyle = {
  padding: '12px 14px', borderRadius: 16, border: '1px solid rgba(255, 145, 145, 0.22)',
  background: 'rgba(255, 98, 98, 0.12)', color: '#ffd8d8',
};

const listStyle = { display: 'grid', gap: 10 };
const cardStyle = {
  borderRadius: 18, border: '1px solid rgba(255, 255, 255, 0.1)',
  background: 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)', overflow: 'hidden',
};
const cardHeaderButtonStyle = {
  width: '100%', boxSizing: 'border-box', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  gap: 10, padding: '14px 16px', border: 'none', background: 'transparent', cursor: 'pointer',
};
const detailWrapStyle = { display: 'grid', gap: 6, padding: '4px 16px 16px', borderTop: '1px solid rgba(255, 255, 255, 0.06)' };
const lineaRowStyle = { display: 'flex', justifyContent: 'space-between', fontSize: 13, color: '#e8dede' };

export default AnalystComprasPage;

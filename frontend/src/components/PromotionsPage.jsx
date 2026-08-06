import { useEffect, useMemo, useState } from 'react';

function PromotionsPage({ isMobile, onBack }) {
  const [promotions, setPromotions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [message, setMessage] = useState('');

  useEffect(() => {
    let cancelled = false;

    const loadPromotions = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/promociones/', {
          credentials: 'include',
          cache: 'no-store',
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || 'No se pudieron cargar las promociones.');
        }
        if (!cancelled) {
          setPromotions(Array.isArray(data.promotions) ? data.promotions : []);
        }
      } catch (error) {
        if (!cancelled) {
          setMessage(error.message || 'No se pudieron cargar las promociones.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadPromotions();
    return () => {
      cancelled = true;
    };
  }, []);

  const filteredPromotions = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) {
      return promotions;
    }
    return promotions.filter((promotion) => {
      const source = `${promotion.producto_nombre || ''} ${promotion.categoria || ''} ${promotion.titulo || ''}`.toLowerCase();
      return source.includes(query);
    });
  }, [promotions, search]);

  return (
    <section style={containerStyle(isMobile)}>
      <div style={badgeStyle}>Promociones</div>
      <h2 style={titleStyle(isMobile)}>Catálogo de promociones</h2>
      <p style={subtitleStyle}>Busca un producto para saber si tiene descuento vigente.</p>

      <input
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder="Buscar producto o categoría en promoción"
        style={searchInputStyle}
      />

      {message ? <div style={noticeStyle}>{message}</div> : null}

      {loading ? <div style={emptyStateStyle}>Cargando promociones...</div> : null}

      {!loading && promotions.length === 0 ? (
        <div style={emptyStateStyle}>Todavía no hay promociones activas.</div>
      ) : null}

      {!loading && promotions.length > 0 && filteredPromotions.length === 0 ? (
        <div style={emptyStateStyle}>No se encontraron promociones para esa búsqueda.</div>
      ) : null}

      {!loading && filteredPromotions.length > 0 ? (
        <div style={gridStyle(isMobile)}>
          {filteredPromotions.map((promotion) => (
            <article key={promotion.id} style={cardStyle}>
              <div style={cardImageWrapStyle}>
                {promotion.imagen_url ? (
                  <img src={promotion.imagen_url} alt={promotion.producto_nombre} style={cardImageStyle} loading="lazy" />
                ) : (
                  <div style={cardImagePlaceholderStyle}>{(promotion.producto_nombre || '?').charAt(0).toUpperCase()}</div>
                )}
                <span style={discountBadgeStyle}>-{promotion.porcentaje_descuento}%</span>
              </div>
              <div style={cardBodyStyle}>
                <div style={productNameStyle}>{promotion.producto_nombre}</div>
                <div style={categoryStyle}>{promotion.categoria || 'Sin categoría'}</div>
                <div style={priceRowStyle}>
                  <span style={originalPriceStyle}>${promotion.precio_original}</span>
                  <span style={finalPriceStyle}>${promotion.precio_descuento}</span>
                </div>
                {promotion.descripcion ? <div style={descriptionStyle}>{promotion.descripcion}</div> : null}
              </div>
            </article>
          ))}
        </div>
      ) : null}

      <button type="button" onClick={onBack} style={backButtonStyle}>
        Volver al inicio
      </button>
    </section>
  );
}

const containerStyle = (isMobile) => ({
  display: 'grid',
  gap: 16,
  padding: isMobile ? 6 : 10,
});

const badgeStyle = {
  display: 'inline-flex',
  width: 'fit-content',
  padding: '7px 12px',
  borderRadius: 999,
  background: 'rgba(255, 163, 163, 0.12)',
  color: '#ffb5b5',
  fontSize: 12,
  fontWeight: 800,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
};

const titleStyle = (isMobile) => ({
  margin: 0,
  color: '#fff',
  fontSize: isMobile ? 28 : 34,
});

const subtitleStyle = {
  margin: 0,
  color: '#d2c3c3',
  lineHeight: 1.6,
  maxWidth: 760,
};

const searchInputStyle = {
  width: '100%',
  maxWidth: 420,
  boxSizing: 'border-box',
  borderRadius: 999,
  border: '1px solid rgba(255, 255, 255, 0.14)',
  background: '#161010',
  padding: '12px 16px',
  color: '#fff4f4',
  fontSize: 14,
};

const gridStyle = (isMobile) => ({
  display: 'grid',
  gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fill, minmax(220px, 1fr))',
  gap: 14,
});

const cardStyle = {
  display: 'grid',
  gap: 0,
  overflow: 'hidden',
  borderRadius: 20,
  background: 'linear-gradient(180deg, rgba(20, 10, 10, 0.94) 0%, rgba(10, 10, 10, 0.96) 100%)',
  border: '1px solid rgba(255, 255, 255, 0.08)',
  boxShadow: '0 12px 28px rgba(0,0,0,0.24)',
};

const cardImageWrapStyle = {
  position: 'relative',
  width: '100%',
  aspectRatio: '4 / 3',
  background: 'rgba(255,255,255,0.04)',
};

const cardImageStyle = {
  width: '100%',
  height: '100%',
  objectFit: 'cover',
  display: 'block',
};

const cardImagePlaceholderStyle = {
  width: '100%',
  height: '100%',
  display: 'grid',
  placeItems: 'center',
  fontSize: 30,
  fontWeight: 800,
  color: '#7a5f5f',
  background: 'linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%)',
};

const cardBodyStyle = {
  display: 'grid',
  gap: 8,
  padding: '14px 18px 18px',
};

const productNameStyle = {
  color: '#fff',
  fontWeight: 700,
  fontSize: 16,
  lineHeight: 1.3,
};

const discountBadgeStyle = {
  position: 'absolute',
  bottom: 8,
  left: 8,
  padding: '4px 10px',
  borderRadius: 999,
  background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)',
  color: '#fff',
  fontSize: 12,
  fontWeight: 800,
};

const categoryStyle = {
  color: '#b89999',
  fontSize: 12,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
};

const priceRowStyle = {
  display: 'flex',
  alignItems: 'baseline',
  gap: 10,
  marginTop: 4,
};

const originalPriceStyle = {
  color: '#8f7676',
  fontSize: 14,
  textDecoration: 'line-through',
};

const finalPriceStyle = {
  color: '#7dffa0',
  fontSize: 20,
  fontWeight: 800,
};

const descriptionStyle = {
  color: '#c7c7c7',
  fontSize: 13,
  lineHeight: 1.5,
};

const emptyStateStyle = {
  minHeight: 120,
  display: 'grid',
  placeItems: 'center',
  borderRadius: 24,
  border: '1px dashed rgba(255, 255, 255, 0.14)',
  background: 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)',
  color: '#c8bbbb',
  textAlign: 'center',
  padding: 20,
};

const noticeStyle = {
  padding: '12px 14px',
  borderRadius: 16,
  border: '1px solid rgba(255, 145, 145, 0.22)',
  background: 'rgba(255, 98, 98, 0.12)',
  color: '#ffd8d8',
};

const backButtonStyle = {
  justifySelf: 'flex-start',
  border: '1px solid rgba(255, 255, 255, 0.14)',
  borderRadius: 999,
  padding: '11px 18px',
  background: 'rgba(255, 255, 255, 0.04)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
};

export default PromotionsPage;
import { useEffect, useMemo, useState } from 'react';
import BsAmount from './BsAmount';
import useExchangeRate from '../hooks/useExchangeRate';

function ChefRecommendationsPage({ isMobile, onBack }) {
  const tasaCambio = useExchangeRate();
  const [recommendations, setRecommendations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [message, setMessage] = useState('');

  useEffect(() => {
    let cancelled = false;

    const loadRecommendations = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/recomendaciones-chef/', {
          credentials: 'include',
          cache: 'no-store',
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || 'No se pudieron cargar las recomendaciones.');
        }
        if (!cancelled) {
          setRecommendations(Array.isArray(data.recommendations) ? data.recommendations : []);
        }
      } catch (error) {
        if (!cancelled) {
          setMessage(error.message || 'No se pudieron cargar las recomendaciones.');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadRecommendations();
    return () => {
      cancelled = true;
    };
  }, []);

  const filteredRecommendations = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) {
      return recommendations;
    }
    return recommendations.filter((recommendation) => {
      const source = `${recommendation.producto_nombre || ''} ${recommendation.categoria || ''}`.toLowerCase();
      return source.includes(query);
    });
  }, [recommendations, search]);

  return (
    <section style={containerStyle(isMobile)}>
      <div style={badgeStyle}>Recomendación del chef</div>
      <h2 style={titleStyle(isMobile)}>Platos recomendados de hoy</h2>

      <input
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder="Buscar producto o categoría recomendada"
        style={searchInputStyle}
      />

      {message ? <div style={noticeStyle}>{message}</div> : null}

      {loading ? <div style={emptyStateStyle}>Cargando recomendaciones...</div> : null}

      {!loading && recommendations.length === 0 ? (
        <div style={emptyStateStyle}>Todavía no hay recomendaciones para hoy.</div>
      ) : null}

      {!loading && recommendations.length > 0 && filteredRecommendations.length === 0 ? (
        <div style={emptyStateStyle}>No se encontraron recomendaciones para esa búsqueda.</div>
      ) : null}

      {!loading && filteredRecommendations.length > 0 ? (
        <div style={gridStyle(isMobile)}>
          {filteredRecommendations.map((recommendation) => (
            <article key={recommendation.id} style={cardStyle}>
              <div style={cardImageWrapStyle}>
                {recommendation.imagen_url ? (
                  <img src={recommendation.imagen_url} alt={recommendation.producto_nombre} style={cardImageStyle} loading="lazy" />
                ) : (
                  <div style={cardImagePlaceholderStyle}>{(recommendation.producto_nombre || '?').charAt(0).toUpperCase()}</div>
                )}
              </div>
              <div style={cardBodyStyle}>
                <div style={productNameStyle}>{recommendation.producto_nombre}</div>
                <div style={categoryStyle}>{recommendation.categoria || 'Sin categoría'}</div>
                <div style={priceStyle}>
                  ${recommendation.precio_venta}
                  <BsAmount amountUsd={recommendation.precio_venta} tasa={tasaCambio} />
                </div>
                {recommendation.comentario_chef ? (
                  <div style={commentStyle}>&ldquo;{recommendation.comentario_chef}&rdquo;</div>
                ) : null}
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
  color: 'var(--vg-f-ffb5b5)',
  fontSize: 12,
  fontWeight: 800,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
};

const titleStyle = (isMobile) => ({
  margin: 0,
  color: 'var(--vg-text-strong)',
  fontSize: isMobile ? 28 : 34,
});

const subtitleStyle = {
  margin: 0,
  color: 'var(--vg-f-d2c3c3)',
  lineHeight: 1.6,
  maxWidth: 760,
};

const searchInputStyle = {
  width: '100%',
  maxWidth: 420,
  boxSizing: 'border-box',
  borderRadius: 999,
  border: '1px solid rgba(var(--vg-ink), 0.14)',
  background: 'var(--vg-s-161010)',
  padding: '12px 16px',
  color: 'var(--vg-f-fff4f4)',
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
  background: 'linear-gradient(180deg, var(--vg-s-140a0a-a940) 0%, var(--vg-s-0a0a0a-a960) 100%)',
  border: '1px solid rgba(var(--vg-ink), 0.08)',
  boxShadow: '0 12px 28px rgba(0, 0, 0, calc(0.24 * var(--vg-shadow-k)))',
};

const cardImageWrapStyle = {
  position: 'relative',
  width: '100%',
  aspectRatio: '4 / 3',
  background: 'rgba(var(--vg-ink), 0.04)',
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
  background: 'linear-gradient(135deg, rgba(var(--vg-ink), 0.05) 0%, rgba(var(--vg-ink), 0.02) 100%)',
};

const cardBodyStyle = {
  display: 'grid',
  gap: 8,
  padding: '14px 18px 18px',
};

const productNameStyle = {
  color: 'var(--vg-text-strong)',
  fontWeight: 700,
  fontSize: 16,
  lineHeight: 1.3,
};

const categoryStyle = {
  color: 'var(--vg-f-b89999)',
  fontSize: 12,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
};

const priceStyle = {
  color: 'var(--vg-f-ffcf7d)',
  fontSize: 18,
  fontWeight: 800,
};

const commentStyle = {
  color: 'var(--vg-f-c7c7c7)',
  fontSize: 13,
  lineHeight: 1.5,
  fontStyle: 'italic',
};

const emptyStateStyle = {
  minHeight: 120,
  display: 'grid',
  placeItems: 'center',
  borderRadius: 24,
  border: '1px dashed rgba(var(--vg-ink), 0.14)',
  background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)',
  color: 'var(--vg-f-c8bbbb)',
  textAlign: 'center',
  padding: 20,
};

const noticeStyle = {
  padding: '12px 14px',
  borderRadius: 16,
  border: '1px solid var(--vg-f-ff9191-a220)',
  background: 'rgba(255, 98, 98, 0.12)',
  color: 'var(--vg-f-ffd8d8)',
};

const backButtonStyle = {
  justifySelf: 'flex-start',
  border: '1px solid rgba(var(--vg-ink), 0.14)',
  borderRadius: 999,
  padding: '11px 18px',
  background: 'rgba(var(--vg-ink), 0.04)',
  color: 'var(--vg-text-strong)',
  fontWeight: 700,
  cursor: 'pointer',
};

export default ChefRecommendationsPage;
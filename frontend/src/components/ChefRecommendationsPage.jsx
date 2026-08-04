import { useEffect, useMemo, useState } from 'react';

function ChefRecommendationsPage({ isMobile, onBack }) {
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
      <p style={subtitleStyle}>Busca un producto para saber si el chef lo recomienda hoy.</p>

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
              <div style={productNameStyle}>{recommendation.producto_nombre}</div>
              <div style={categoryStyle}>{recommendation.categoria || 'Sin categoría'}</div>
              <div style={priceStyle}>${recommendation.precio_venta}</div>
              {recommendation.comentario_chef ? (
                <div style={commentStyle}>&ldquo;{recommendation.comentario_chef}&rdquo;</div>
              ) : null}
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
  gap: 8,
  padding: '16px 18px',
  borderRadius: 20,
  background: 'linear-gradient(180deg, rgba(20, 10, 10, 0.94) 0%, rgba(10, 10, 10, 0.96) 100%)',
  border: '1px solid rgba(255, 255, 255, 0.08)',
  boxShadow: '0 12px 28px rgba(0,0,0,0.24)',
};

const productNameStyle = {
  color: '#fff',
  fontWeight: 700,
  fontSize: 16,
  lineHeight: 1.3,
};

const categoryStyle = {
  color: '#b89999',
  fontSize: 12,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
};

const priceStyle = {
  color: '#ffcf7d',
  fontSize: 18,
  fontWeight: 800,
};

const commentStyle = {
  color: '#c7c7c7',
  fontSize: 13,
  lineHeight: 1.5,
  fontStyle: 'italic',
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

export default ChefRecommendationsPage;

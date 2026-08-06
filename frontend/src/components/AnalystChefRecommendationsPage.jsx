import { useEffect, useMemo, useState } from 'react';
import Pagination from './Pagination';

const PAGE_SIZE = 50;

function AnalystChefRecommendationsPage({ isMobile, isAdmin, onBack, onCreateNew }) {
  const [recommendations, setRecommendations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState('');
  const [message, setMessage] = useState('');
  const [page, setPage] = useState(0);

  useEffect(() => {
    if (!isAdmin) {
      setLoading(false);
      return;
    }

    const loadRecommendations = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/admin/recomendaciones-chef/', {
          credentials: 'include',
          cache: 'no-store',
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || 'No se pudo cargar el reporte de recomendaciones.');
        }
        setRecommendations(Array.isArray(data.recommendations) ? data.recommendations : []);
      } catch (error) {
        setMessage(error.message || 'No se pudo cargar el reporte de recomendaciones.');
      } finally {
        setLoading(false);
      }
    };

    loadRecommendations();
  }, [isAdmin]);

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

  const pageCount = Math.max(1, Math.ceil(filteredRecommendations.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const pagedRecommendations = filteredRecommendations.slice(currentPage * PAGE_SIZE, currentPage * PAGE_SIZE + PAGE_SIZE);

  const handleDelete = async (recommendation) => {
    if (!window.confirm(`¿Deseas eliminar la recomendación de ${recommendation.producto_nombre}?`)) {
      return;
    }

    setSaving(true);
    try {
      const response = await fetch('/api/admin/recomendaciones-chef/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'delete', id: recommendation.id }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo eliminar la recomendación.');
      }
      setRecommendations((current) => current.filter((entry) => entry.id !== recommendation.id));
      setMessage(data.message || 'Recomendación eliminada correctamente.');
    } catch (error) {
      setMessage(error.message || 'No se pudo eliminar la recomendación.');
    } finally {
      setSaving(false);
    }
  };

  if (!isAdmin) {
    return (
      <section style={containerStyle(isMobile)}>
        <div style={badgeStyle}>Recomendaciones del chef</div>
        <h2 style={titleStyle(isMobile)}>Acceso restringido</h2>
        <div style={noticeStyle}>Solo el rol Administrador puede entrar a esta sección.</div>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          ← Volver al panel del analista
        </button>
      </section>
    );
  }

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>
        ← Volver al panel del analista
      </button>

      <div style={badgeStyle}>Recomendaciones del chef</div>
      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Reporte de platos recomendados</h2>
          <p style={subtitleStyle}>Consulta, busca y elimina las recomendaciones del chef registradas por fecha.</p>
        </div>
        <button type="button" onClick={onCreateNew} style={primaryButtonStyle}>
          Agregar recomendación
        </button>
      </div>

      {message ? <div style={noticeStyle}>{message}</div> : null}

      <section style={panelStyle}>
        <div style={reportHeaderStyle(isMobile)}>
          <div style={sectionTitleStyle}>Listado de recomendaciones</div>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Buscar producto o categoría"
            style={searchInputStyle(isMobile)}
          />
        </div>

        {loading ? <div style={emptyStateStyle}>Cargando recomendaciones...</div> : null}

        {!loading && recommendations.length === 0 ? (
          <div style={emptyStateStyle}>No hay platos recomendados registrados todavía.</div>
        ) : null}

        {!loading && recommendations.length > 0 && filteredRecommendations.length === 0 ? (
          <div style={emptyStateStyle}>No se encontraron recomendaciones para esa búsqueda.</div>
        ) : null}

        {!loading && filteredRecommendations.length > 0 ? (
          <div style={tableWrapStyle}>
            <div style={tableStyle}>
              <div style={tableHeadStyle}>Producto</div>
              <div style={tableHeadStyle}>Categoría</div>
              <div style={tableHeadStyle}>Fecha</div>
              <div style={tableHeadStyle}>Comentario</div>
              <div style={tableHeadStyle}>Acciones</div>

              {pagedRecommendations.map((recommendation) => (
                <>
                  <div key={`name-${recommendation.id}`} style={tableCellPrimaryStyle}>
                    <div style={productRowStyle}>
                      <div style={productThumbWrapStyle}>
                        {recommendation.imagen_url ? (
                          <img src={recommendation.imagen_url} alt={recommendation.producto_nombre} style={productThumbImgStyle} loading="lazy" />
                        ) : (
                          <div style={productThumbPlaceholderStyle}>{(recommendation.producto_nombre || '?').charAt(0).toUpperCase()}</div>
                        )}
                      </div>
                      <div>
                        <div style={productNameStyle}>{recommendation.producto_nombre}</div>
                        <div style={productMetaStyle}>ID #{recommendation.id}</div>
                      </div>
                    </div>
                  </div>
                  <div key={`category-${recommendation.id}`} style={tableCellStyle}>
                    {recommendation.categoria || 'Sin categoría'}
                  </div>
                  <div key={`date-${recommendation.id}`} style={tableCellStyle}>
                    {recommendation.fecha}
                  </div>
                  <div key={`comment-${recommendation.id}`} style={tableCellStyle}>
                    {recommendation.comentario_chef || 'Sin comentario'}
                  </div>
                  <div key={`actions-${recommendation.id}`} style={tableCellActionStyle}>
                    <button type="button" onClick={() => handleDelete(recommendation)} style={dangerButtonStyle} disabled={saving}>
                      Eliminar
                    </button>
                  </div>
                </>
              ))}
            </div>
          </div>
        ) : null}

        <Pagination
          page={currentPage}
          pageCount={pageCount}
          totalCount={filteredRecommendations.length}
          pageSize={PAGE_SIZE}
          isMobile={isMobile}
          onPrev={() => setPage((current) => Math.max(0, current - 1))}
          onNext={() => setPage((current) => Math.min(pageCount - 1, current + 1))}
        />
      </section>
    </section>
  );
}

const containerStyle = (isMobile) => ({
  display: 'grid',
  gap: 18,
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
  margin: '8px 0 0',
  color: '#d2c3c3',
  lineHeight: 1.6,
  maxWidth: 760,
};

const headerRowStyle = (isMobile) => ({
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: isMobile ? 'flex-start' : 'center',
  gap: 14,
  flexDirection: isMobile ? 'column' : 'row',
});

const panelStyle = {
  display: 'grid',
  gap: 16,
  padding: '20px 18px',
  borderRadius: 24,
  border: '1px solid rgba(255, 255, 255, 0.1)',
  background: 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)',
};

const reportHeaderStyle = (isMobile) => ({
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: isMobile ? 'flex-start' : 'center',
  flexDirection: isMobile ? 'column' : 'row',
  gap: 10,
});

const sectionTitleStyle = {
  color: '#fff',
  fontSize: 20,
  fontWeight: 700,
};

const searchInputStyle = (isMobile) => ({
  width: isMobile ? '100%' : 360,
  boxSizing: 'border-box',
  borderRadius: 14,
  border: '1px solid rgba(255, 255, 255, 0.14)',
  background: '#161010',
  padding: '11px 12px',
  color: '#fff4f4',
  fontSize: 14,
});

const emptyStateStyle = {
  minHeight: 80,
  display: 'grid',
  placeItems: 'center',
  borderRadius: 18,
  border: '1px dashed rgba(255, 255, 255, 0.12)',
  color: '#c8bbbb',
};

const tableWrapStyle = {
  overflowX: 'auto',
};

const tableStyle = {
  display: 'grid',
  gridTemplateColumns: 'minmax(180px, 1fr) minmax(140px, 0.7fr) minmax(120px, 0.6fr) minmax(220px, 1.2fr) minmax(140px, 0.7fr)',
  alignItems: 'stretch',
  border: '1px solid rgba(255, 255, 255, 0.08)',
  borderRadius: 18,
  overflow: 'hidden',
  minWidth: 920,
};

const tableHeadStyle = {
  padding: '14px 16px',
  background: 'rgba(255, 255, 255, 0.06)',
  color: '#ffb0b0',
  fontSize: 12,
  fontWeight: 800,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
  borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
};

const tableCellStyle = {
  padding: '16px',
  borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
  color: '#f2e6e6',
  display: 'grid',
  alignContent: 'center',
  gap: 4,
};

const tableCellPrimaryStyle = {
  ...tableCellStyle,
  background: 'rgba(255, 255, 255, 0.02)',
};

const tableCellActionStyle = {
  ...tableCellStyle,
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  flexWrap: 'wrap',
};

const productRowStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
};

const productThumbWrapStyle = {
  width: 44,
  height: 44,
  borderRadius: 10,
  overflow: 'hidden',
  flexShrink: 0,
  background: 'rgba(255,255,255,0.04)',
};

const productThumbImgStyle = {
  width: '100%',
  height: '100%',
  objectFit: 'cover',
  display: 'block',
};

const productThumbPlaceholderStyle = {
  width: '100%',
  height: '100%',
  display: 'grid',
  placeItems: 'center',
  fontSize: 16,
  fontWeight: 800,
  color: '#7a5f5f',
  background: 'linear-gradient(135deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.02) 100%)',
};

const productNameStyle = {
  color: '#fff',
  fontWeight: 700,
  fontSize: 17,
};

const productMetaStyle = {
  color: '#d2c4c4',
  fontSize: 13,
};

const noticeStyle = {
  padding: '12px 14px',
  borderRadius: 16,
  border: '1px solid rgba(255, 145, 145, 0.22)',
  background: 'rgba(255, 98, 98, 0.12)',
  color: '#ffd8d8',
};

const primaryButtonStyle = {
  border: 'none',
  borderRadius: 999,
  padding: '11px 18px',
  background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
};

const dangerButtonStyle = {
  border: '1px solid rgba(255, 126, 126, 0.4)',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'rgba(145, 33, 33, 0.25)',
  color: '#ffd3d3',
  fontWeight: 700,
  cursor: 'pointer',
};

const backButtonStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  justifySelf: 'flex-start',
  width: 'fit-content',
  border: 'none',
  borderRadius: 999,
  padding: '11px 18px',
  background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
  boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)',
};

export default AnalystChefRecommendationsPage;
import { useEffect, useMemo, useState } from 'react';
import Pagination from './Pagination';
import Toast from './Toast';
import useToast from '../hooks/useToast';

const PAGE_SIZE = 50;

function AnalystRecipesPage({ isMobile, isAdmin, onBack, onCreateNewRecipe, onEditRecipe }) {
  const [recipes, setRecipes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState('');
  const { toast, showSuccess, showError, hideToast } = useToast();
  const [page, setPage] = useState(0);

  useEffect(() => {
    if (!isAdmin) {
      setLoading(false);
      return;
    }

    const loadRecipes = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/admin/recetas/', {
          credentials: 'include',
          cache: 'no-store',
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || 'No se pudo cargar el reporte de recetas.');
        }
        setRecipes(Array.isArray(data.recipes) ? data.recipes : []);
      } catch (error) {
        showError(error.message || 'No se pudo cargar el reporte de recetas.');
      } finally {
        setLoading(false);
      }
    };

    loadRecipes();
  }, [isAdmin]);

  const filteredRecipes = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) {
      return recipes;
    }
    return recipes.filter((recipe) => {
      const componentNames = (recipe.componentes || []).map((component) => component.nombre || '').join(' ');
      const source = `${recipe.nombre || ''} ${recipe.descripcion || ''} ${componentNames}`.toLowerCase();
      return source.includes(query);
    });
  }, [recipes, search]);

  const pageCount = Math.max(1, Math.ceil(filteredRecipes.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const pagedRecipes = filteredRecipes.slice(currentPage * PAGE_SIZE, currentPage * PAGE_SIZE + PAGE_SIZE);

  const handleDelete = async (recipe) => {
    if (!window.confirm(`¿Deseas eliminar la receta ${recipe.nombre}?`)) {
      return;
    }

    setSaving(true);
    try {
      const response = await fetch('/api/admin/recetas/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'delete', id: recipe.id }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo eliminar la receta.');
      }
      setRecipes((current) => current.filter((entry) => entry.id !== recipe.id));
      showSuccess(data.message || 'Receta eliminada correctamente.');
    } catch (error) {
      showError(error.message || 'No se pudo eliminar la receta.');
    } finally {
      setSaving(false);
    }
  };

  if (!isAdmin) {
    return (
      <section style={containerStyle(isMobile)}>
        <div style={badgeStyle}>Recetas</div>
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

      <div style={badgeStyle}>Recetas</div>
      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Reporte de recetas registradas</h2>
          <p style={subtitleStyle}>Busca por nombre, descripción o componentes. Desde aquí puedes modificar o eliminar una receta.</p>
        </div>
        <button type="button" onClick={onCreateNewRecipe} style={primaryButtonStyle}>
          Agregar nueva receta
        </button>
      </div>

      <Toast toast={toast} onClose={hideToast} />

      <section style={panelStyle}>
        <div style={reportHeaderStyle(isMobile)}>
          <div style={sectionTitleStyle}>Listado administrativo</div>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Buscar receta por nombre, descripción o componente"
            style={searchInputStyle(isMobile)}
          />
        </div>

        {loading ? <div style={emptyStateStyle}>Cargando recetas...</div> : null}
        {!loading && filteredRecipes.length === 0 ? <div style={emptyStateStyle}>No se encontraron recetas para esa búsqueda.</div> : null}

        {!loading && filteredRecipes.length > 0 ? (
          <div style={tableWrapStyle}>
            <div style={tableStyle}>
              <div style={tableHeadStyle}>Receta</div>
              <div style={tableHeadStyle}>Descripción</div>
              <div style={tableHeadStyle}>Componentes</div>
              <div style={tableHeadStyle}>Costo</div>
              <div style={tableHeadStyle}>Acciones</div>

              {pagedRecipes.map((recipe) => (
                <>
                  <div key={`name-${recipe.id}`} style={tableCellPrimaryStyle}>
                    <div style={recipeNameStyle}>{recipe.nombre}</div>
                    <div style={recipeMetaStyle}>ID #{recipe.id}</div>
                  </div>
                  <div key={`description-${recipe.id}`} style={tableCellStyle}>
                    {recipe.descripcion || 'Sin descripción'}
                  </div>
                  <div key={`components-${recipe.id}`} style={tableCellStyle}>
                    <div style={componentCountStyle}>{recipe.componentes_total || 0} componentes</div>
                    <div style={componentPreviewStyle}>
                      {(recipe.componentes || []).slice(0, 3).map((component) => component.nombre).join(', ') || 'Sin componentes'}
                    </div>
                  </div>
                  <div key={`cost-${recipe.id}`} style={tableCellStyle}>
                    <div style={{ color: '#7dffa0', fontWeight: 700 }}>${recipe.costo_calculado || '0.00'}</div>
                  </div>
                  <div key={`actions-${recipe.id}`} style={tableCellActionStyle}>
                    <button type="button" onClick={() => onEditRecipe(recipe.id)} style={secondaryButtonStyle}>
                      Modificar
                    </button>
                    <button type="button" onClick={() => handleDelete(recipe)} style={dangerButtonStyle} disabled={saving}>
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
          totalCount={filteredRecipes.length}
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
  gridTemplateColumns: 'minmax(180px, 1fr) minmax(240px, 1.1fr) minmax(200px, 1fr) minmax(120px, 0.7fr) minmax(220px, 0.9fr)',
  alignItems: 'stretch',
  border: '1px solid rgba(255, 255, 255, 0.08)',
  borderRadius: 18,
  overflow: 'hidden',
  minWidth: 1040,
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

const recipeNameStyle = {
  color: '#fff',
  fontWeight: 700,
  fontSize: 17,
};

const recipeMetaStyle = {
  color: '#d2c4c4',
  fontSize: 13,
};

const componentCountStyle = {
  color: '#ffcaca',
  fontSize: 13,
  fontWeight: 700,
};

const componentPreviewStyle = {
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

const secondaryButtonStyle = {
  border: '1px solid rgba(255, 255, 255, 0.14)',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'rgba(255, 255, 255, 0.04)',
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

export default AnalystRecipesPage;
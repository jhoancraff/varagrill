import { useEffect, useMemo, useState } from 'react';
import Pagination from './Pagination';
import BsAmount from './BsAmount';
import Toast from './Toast';
import useExchangeRate from '../hooks/useExchangeRate';
import useToast from '../hooks/useToast';

const PAGE_SIZE = 50;

function AnalystPromotionsPage({ isMobile, isAdmin, onBack, onSelectProduct, onSelectBulk }) {
  const tasaCambio = useExchangeRate();
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState('');
  const { toast, showSuccess, showError, hideToast } = useToast();
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [page, setPage] = useState(0);

  const loadProducts = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/admin/promociones/', {
        credentials: 'include',
        cache: 'no-store',
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo cargar el reporte de productos.');
      }
      setProducts(Array.isArray(data.products) ? data.products : []);
    } catch (error) {
      showError(error.message || 'No se pudo cargar el reporte de productos.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!isAdmin) {
      setLoading(false);
      return;
    }

    loadProducts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin]);

  const handleDeletePromotion = async (product) => {
    if (!product.promocion) {
      return;
    }
    if (!window.confirm(`¿Deseas eliminar la promoción de ${product.nombre}?`)) {
      return;
    }

    setSaving(true);
    try {
      const response = await fetch('/api/admin/promociones/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'delete', id: product.promocion.id }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo eliminar la promoción.');
      }
      showSuccess(data.message || 'Promoción eliminada correctamente.');
      await loadProducts();
    } catch (error) {
      showError(error.message || 'No se pudo eliminar la promoción.');
    } finally {
      setSaving(false);
    }
  };

  const filteredProducts = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) {
      return products;
    }
    return products.filter((product) => {
      const source = `${product.nombre || ''} ${product.categoria || ''}`.toLowerCase();
      return source.includes(query);
    });
  }, [products, search]);

  const pageCount = Math.max(1, Math.ceil(filteredProducts.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const pagedProducts = filteredProducts.slice(currentPage * PAGE_SIZE, currentPage * PAGE_SIZE + PAGE_SIZE);

  const selectableProducts = useMemo(
    () => pagedProducts.filter((product) => !product.promocion_activa),
    [pagedProducts],
  );
  const allVisibleSelected = selectableProducts.length > 0
    && selectableProducts.every((product) => selectedIds.has(product.id));

  const toggleProduct = (productId) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(productId)) {
        next.delete(productId);
      } else {
        next.add(productId);
      }
      return next;
    });
  };

  const toggleSelectAllVisible = () => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (allVisibleSelected) {
        selectableProducts.forEach((product) => next.delete(product.id));
      } else {
        selectableProducts.forEach((product) => next.add(product.id));
      }
      return next;
    });
  };

  if (!isAdmin) {
    return (
      <section style={containerStyle(isMobile)}>
        <div style={badgeStyle}>Promociones</div>
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

      <div style={badgeStyle}>Promociones</div>
      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Reporte de productos disponibles</h2>
          <p style={subtitleStyle}>Selecciona un producto para crear una promoción con descuento.</p>
        </div>
      </div>

      <Toast toast={toast} onClose={hideToast} />

      {selectedIds.size > 0 ? (
        <div style={bulkBarStyle(isMobile)}>
          <div style={bulkTextStyle}>{selectedIds.size} producto(s) seleccionado(s)</div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <button
              type="button"
              onClick={() => onSelectBulk(Array.from(selectedIds))}
              style={primaryButtonStyle}
            >
              Aplicar descuento a los seleccionados
            </button>
            <button type="button" onClick={() => setSelectedIds(new Set())} style={secondaryButtonStyle}>
              Limpiar selección
            </button>
          </div>
        </div>
      ) : null}

      <section style={panelStyle}>
        <div style={reportHeaderStyle(isMobile)}>
          <div style={sectionTitleStyle}>Listado de productos</div>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Buscar producto por nombre o categoría"
            style={searchInputStyle(isMobile)}
          />
        </div>

        {loading ? <div style={emptyStateStyle}>Cargando productos...</div> : null}
        {!loading && filteredProducts.length === 0 ? <div style={emptyStateStyle}>No se encontraron productos para esa búsqueda.</div> : null}

        {!loading && filteredProducts.length > 0 ? (
          <div style={tableWrapStyle}>
            <div style={tableStyle}>
              <div style={tableHeadStyle}>
                <input
                  type="checkbox"
                  checked={allVisibleSelected}
                  onChange={toggleSelectAllVisible}
                  disabled={selectableProducts.length === 0}
                  aria-label="Seleccionar todos los productos visibles"
                />
              </div>
              <div style={tableHeadStyle}>Producto</div>
              <div style={tableHeadStyle}>Categoría</div>
              <div style={tableHeadStyle}>Precio</div>
              <div style={tableHeadStyle}>Estado</div>
              <div style={tableHeadStyle}>Acciones</div>

              {pagedProducts.map((product) => (
                <>
                  <div key={`select-${product.id}`} style={tableCellStyle}>
                    <input
                      type="checkbox"
                      checked={selectedIds.has(product.id)}
                      onChange={() => toggleProduct(product.id)}
                      disabled={product.promocion_activa}
                      aria-label={`Seleccionar ${product.nombre}`}
                    />
                  </div>
                  <div key={`name-${product.id}`} style={tableCellPrimaryStyle}>
                    <div style={productRowStyle}>
                      <div style={productThumbWrapStyle}>
                        {product.imagen_url ? (
                          <img src={product.imagen_url} alt={product.nombre} style={productThumbImgStyle} loading="lazy" />
                        ) : (
                          <div style={productThumbPlaceholderStyle}>{(product.nombre || '?').charAt(0).toUpperCase()}</div>
                        )}
                      </div>
                      <div>
                        <div style={productNameStyle}>{product.nombre}</div>
                        <div style={productMetaStyle}>ID #{product.id}</div>
                      </div>
                    </div>
                  </div>
                  <div key={`category-${product.id}`} style={tableCellStyle}>
                    {product.categoria || 'Sin categoría'}
                  </div>
                  <div key={`price-${product.id}`} style={tableCellStyle}>
                    ${product.precio_venta}
                    <BsAmount amountUsd={product.precio_venta} tasa={tasaCambio} />
                  </div>
                  <div key={`status-${product.id}`} style={tableCellStyle}>
                    <span style={statusBadgeStyle(product.promocion_activa)}>
                      {product.promocion_activa ? 'Con promoción activa' : 'Sin promoción'}
                    </span>
                  </div>
                  <div key={`actions-${product.id}`} style={tableCellActionStyle}>
                    {product.promocion_activa ? (
                      <>
                        <button type="button" onClick={() => onSelectProduct(product.id)} style={primaryButtonStyle}>
                          Editar promoción
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDeletePromotion(product)}
                          style={dangerButtonStyle}
                          disabled={saving}
                        >
                          Eliminar
                        </button>
                      </>
                    ) : (
                      <button type="button" onClick={() => onSelectProduct(product.id)} style={primaryButtonStyle}>
                        Aplicar descuento
                      </button>
                    )}
                  </div>
                </>
              ))}
            </div>
          </div>
        ) : null}

        <Pagination
          page={currentPage}
          pageCount={pageCount}
          totalCount={filteredProducts.length}
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
  gridTemplateColumns: 'minmax(44px, 44px) minmax(180px, 1fr) minmax(140px, 0.8fr) minmax(100px, 0.6fr) minmax(180px, 0.9fr) minmax(180px, 0.9fr)',
  alignItems: 'stretch',
  border: '1px solid rgba(255, 255, 255, 0.08)',
  borderRadius: 18,
  overflow: 'hidden',
  minWidth: 960,
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

const statusBadgeStyle = (isActive) => ({
  display: 'inline-flex',
  width: 'fit-content',
  padding: '5px 10px',
  borderRadius: 999,
  fontSize: 12,
  fontWeight: 700,
  color: isActive ? '#c8ffd8' : '#d2c4c4',
  background: isActive ? 'rgba(70, 200, 120, 0.18)' : 'rgba(255, 255, 255, 0.06)',
  border: isActive ? '1px solid rgba(120, 220, 160, 0.4)' : '1px solid rgba(255, 255, 255, 0.1)',
});

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
  padding: '10px 16px',
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

const secondaryButtonStyle = {
  border: '1px solid rgba(255, 255, 255, 0.14)',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'rgba(255, 255, 255, 0.04)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
};

const bulkBarStyle = (isMobile) => ({
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: isMobile ? 'flex-start' : 'center',
  flexDirection: isMobile ? 'column' : 'row',
  gap: 12,
  padding: '14px 18px',
  borderRadius: 18,
  background: 'rgba(255, 88, 88, 0.14)',
  border: '1px solid rgba(255, 132, 132, 0.35)',
});

const bulkTextStyle = {
  color: '#fff',
  fontWeight: 700,
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

export default AnalystPromotionsPage;
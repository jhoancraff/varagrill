import { useEffect, useState } from 'react';

function AnalystProductsPage({ isMobile, isAdmin, onBack, onCreateNewProduct, onEditProduct, onProductsChanged }) {
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  const loadProducts = async () => {
    setLoading(true);
    setMessage('');
    try {
      const response = await fetch('/api/admin/productos/', {
        credentials: 'include',
        cache: 'no-store',
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo cargar la gestión de productos.');
      }
      setProducts(Array.isArray(data.products) ? data.products : []);
      setCategories(Array.isArray(data.categories) ? data.categories : []);
    } catch (error) {
      setMessage(error.message || 'No se pudo cargar la gestión de productos.');
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
  }, [isAdmin]);

  const handleDelete = async (product) => {
    if (!window.confirm(`¿Deseas eliminar el producto "${product.nombre}"?`)) {
      return;
    }

    setSaving(true);
    try {
      const response = await fetch('/api/admin/productos/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'delete', id: product.id }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo eliminar el producto.');
      }

      setProducts((current) => current.filter((entry) => entry.id !== product.id));
      setMessage(data.message || 'Producto eliminado correctamente.');
      if (onProductsChanged) {
        onProductsChanged();
      }
    } catch (error) {
      setMessage(error.message || 'No se pudo eliminar el producto.');
    } finally {
      setSaving(false);
    }
  };

  if (!isAdmin) {
    return (
      <section style={containerStyle(isMobile)}>
        <div style={badgeStyle}>Productos</div>
        <h2 style={titleStyle(isMobile)}>Acceso restringido</h2>
        <div style={noticeStyle}>Solo el rol Administrador puede entrar a esta sección.</div>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          Volver al panel del analista
        </button>
      </section>
    );
  }

  const availableCount = products.filter((product) => Boolean(product.disponible)).length;

  return (
    <section style={containerStyle(isMobile)}>
      <div style={badgeStyle}>Productos</div>
      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Gestión de productos</h2>
          <p style={subtitleStyle}>Administra los productos del menú, su precio, categoría y disponibilidad.</p>
        </div>
        <button type="button" onClick={onCreateNewProduct} style={primaryButtonStyle}>
          Agregar producto nuevo
        </button>
      </div>

      {message ? <div style={noticeStyle}>{message}</div> : null}

      <div style={summaryGridStyle(isMobile)}>
        <article style={summaryCardStyle}>
          <div style={summaryLabelStyle}>Productos totales</div>
          <div style={summaryValueStyle}>{products.length}</div>
        </article>
        <article style={summaryCardStyle}>
          <div style={summaryLabelStyle}>Disponibles</div>
          <div style={summaryValueStyle}>{availableCount}</div>
        </article>
        <article style={summaryCardStyle}>
          <div style={summaryLabelStyle}>No disponibles</div>
          <div style={summaryValueStyle}>{products.length - availableCount}</div>
        </article>
        <article style={summaryCardStyle}>
          <div style={summaryLabelStyle}>Categorías</div>
          <div style={summaryValueStyle}>{categories.length}</div>
        </article>
      </div>

      <section style={panelStyle}>
        <div style={reportHeaderStyle(isMobile)}>
          <div style={sectionTitleStyle}>Reporte administrativo de productos</div>
          <div style={reportHintStyle}>Consulta precio, categoría, disponibilidad e imagen principal.</div>
        </div>

        {loading ? <div style={emptyStateStyle}>Cargando productos...</div> : null}
        {!loading && products.length === 0 ? <div style={emptyStateStyle}>No hay productos registrados.</div> : null}

        {!loading && products.length > 0 ? (
          <div style={tableWrapStyle}>
            <div style={tableStyle}>
              <div style={tableHeadStyle}>Producto</div>
              <div style={tableHeadStyle}>Categoría</div>
              <div style={tableHeadStyle}>Precio</div>
              <div style={tableHeadStyle}>Estado</div>
              <div style={tableHeadStyle}>Acciones</div>

              {products.map((product) => (
                <>
                  <div key={`product-${product.id}`} style={tableCellPrimaryStyle}>
                    <div style={nameStyle}>{product.nombre || 'Sin nombre'}</div>
                    <div style={metaStyle}>{product.descripcion || 'Sin descripción'}</div>
                  </div>
                  <div key={`category-${product.id}`} style={tableCellStyle}>
                    <span style={pillStyle}>{product.categoria_nombre || 'Sin categoría'}</span>
                  </div>
                  <div key={`price-${product.id}`} style={tableCellStyle}>
                    {formatCurrency(product.precio_venta)}
                  </div>
                  <div key={`status-${product.id}`} style={tableCellStyle}>
                    <span style={statusPillStyle(product.disponible)}>{product.disponible ? 'Disponible' : 'No disponible'}</span>
                  </div>
                  <div key={`actions-${product.id}`} style={tableCellActionStyle}>
                    <button type="button" onClick={() => onEditProduct(product.id)} style={secondaryButtonStyle}>
                      Modificar
                    </button>
                    <button type="button" onClick={() => handleDelete(product)} style={dangerButtonStyle} disabled={saving}>
                      Eliminar
                    </button>
                  </div>
                </>
              ))}
            </div>
          </div>
        ) : null}
      </section>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <button type="button" onClick={loadProducts} style={secondaryButtonStyle} disabled={loading || saving}>
          Recargar productos
        </button>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          Volver al panel del analista
        </button>
      </div>
    </section>
  );
}

function formatCurrency(value) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) {
    return '$0.00';
  }
  return new Intl.NumberFormat('es-VE', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
  }).format(amount);
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
  maxWidth: 720,
};

const headerRowStyle = (isMobile) => ({
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: isMobile ? 'flex-start' : 'center',
  gap: 14,
  flexDirection: isMobile ? 'column' : 'row',
});

const summaryGridStyle = (isMobile) => ({
  display: 'grid',
  gridTemplateColumns: isMobile ? 'repeat(2, minmax(0, 1fr))' : 'repeat(4, minmax(0, 1fr))',
  gap: 18,
});

const summaryCardStyle = {
  display: 'grid',
  gap: 10,
  padding: '18px 16px',
  borderRadius: 20,
  border: '1px solid rgba(255, 255, 255, 0.1)',
  background: 'linear-gradient(180deg, rgba(27, 10, 10, 0.96) 0%, rgba(10, 10, 10, 0.98) 100%)',
};

const summaryLabelStyle = {
  color: '#f0b1b1',
  fontSize: 12,
  fontWeight: 800,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
};

const summaryValueStyle = {
  color: '#fff',
  fontSize: 28,
  fontWeight: 800,
};

const panelStyle = {
  display: 'grid',
  gap: 16,
  padding: '20px 18px',
  borderRadius: 24,
  border: '1px solid rgba(255, 255, 255, 0.1)',
  background: 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)',
};

const sectionTitleStyle = {
  color: '#fff',
  fontSize: 20,
  fontWeight: 700,
};

const reportHeaderStyle = (isMobile) => ({
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: isMobile ? 'flex-start' : 'center',
  flexDirection: isMobile ? 'column' : 'row',
  gap: 10,
});

const reportHintStyle = {
  color: '#d2c4c4',
  fontSize: 13,
};

const tableWrapStyle = {
  overflowX: 'auto',
  borderRadius: 18,
  border: '1px solid rgba(255, 255, 255, 0.08)',
};

const tableStyle = {
  minWidth: 880,
  display: 'grid',
  gridTemplateColumns: 'minmax(220px, 1.2fr) minmax(160px, .9fr) minmax(140px, .7fr) minmax(130px, .7fr) minmax(220px, 1fr)',
  background: 'rgba(8, 8, 8, 0.55)',
};

const tableHeadStyle = {
  padding: '13px 14px',
  fontSize: 12,
  fontWeight: 800,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  color: '#f4b0b0',
  borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
};

const tableCellStyle = {
  padding: '14px',
  color: '#eadede',
  borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
  display: 'grid',
  alignContent: 'center',
  gap: 4,
};

const tableCellPrimaryStyle = {
  ...tableCellStyle,
  color: '#fff',
};

const tableCellActionStyle = {
  ...tableCellStyle,
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  flexWrap: 'wrap',
};

const nameStyle = {
  fontWeight: 700,
  fontSize: 15,
};

const metaStyle = {
  color: '#c7b8b8',
  fontSize: 13,
};

const pillStyle = {
  display: 'inline-flex',
  width: 'fit-content',
  padding: '5px 10px',
  borderRadius: 999,
  fontSize: 12,
  background: 'rgba(255, 143, 143, 0.16)',
  color: '#ffc4c4',
};

const statusPillStyle = (isAvailable) => ({
  display: 'inline-flex',
  width: 'fit-content',
  padding: '5px 10px',
  borderRadius: 999,
  fontSize: 12,
  fontWeight: 700,
  background: isAvailable ? 'rgba(95, 224, 140, 0.16)' : 'rgba(255, 125, 125, 0.16)',
  color: isAvailable ? '#9ef4bd' : '#ffb5b5',
});

const noticeStyle = {
  padding: '12px 14px',
  borderRadius: 14,
  background: 'rgba(255, 140, 140, 0.14)',
  border: '1px solid rgba(255, 175, 175, 0.24)',
  color: '#ffd4d4',
};

const emptyStateStyle = {
  padding: '14px',
  borderRadius: 14,
  background: 'rgba(255, 255, 255, 0.04)',
  border: '1px dashed rgba(255, 255, 255, 0.14)',
  color: '#d8c8c8',
};

const primaryButtonStyle = {
  border: 'none',
  borderRadius: 12,
  padding: '10px 14px',
  background: 'linear-gradient(135deg, #ff6464 0%, #b21f1f 100%)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
};

const secondaryButtonStyle = {
  border: '1px solid rgba(255, 173, 173, 0.35)',
  borderRadius: 12,
  padding: '10px 14px',
  background: 'rgba(255, 255, 255, 0.02)',
  color: '#ffe0e0',
  fontWeight: 600,
  cursor: 'pointer',
};

const dangerButtonStyle = {
  border: '1px solid rgba(255, 102, 102, 0.45)',
  borderRadius: 12,
  padding: '10px 14px',
  background: 'rgba(255, 73, 73, 0.1)',
  color: '#ffb3b3',
  fontWeight: 600,
  cursor: 'pointer',
};

const backButtonStyle = {
  ...secondaryButtonStyle,
  width: 'fit-content',
};

export default AnalystProductsPage;

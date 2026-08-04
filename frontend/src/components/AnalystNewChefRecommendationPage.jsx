import { useEffect, useMemo, useRef, useState } from 'react';

const todayIsoDate = () => new Date().toISOString().slice(0, 10);

function AnalystNewChefRecommendationPage({ isMobile, isAdmin, onBack }) {
  const productPickerRef = useRef(null);
  const [products, setProducts] = useState([]);
  const [productSearch, setProductSearch] = useState('');
  const [productId, setProductId] = useState('');
  const [showProductResults, setShowProductResults] = useState(false);
  const [fecha, setFecha] = useState(todayIsoDate());
  const [comentario, setComentario] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    const handlePointerDown = (event) => {
      if (productPickerRef.current && !productPickerRef.current.contains(event.target)) {
        setShowProductResults(false);
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('touchstart', handlePointerDown);

    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('touchstart', handlePointerDown);
    };
  }, []);

  useEffect(() => {
    if (!isAdmin) {
      setLoading(false);
      return;
    }

    const loadProducts = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/admin/recomendaciones-chef/', {
          credentials: 'include',
          cache: 'no-store',
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || 'No se pudieron cargar los productos.');
        }
        setProducts(Array.isArray(data.products) ? data.products : []);
      } catch (error) {
        setMessage(error.message || 'No se pudieron cargar los productos.');
      } finally {
        setLoading(false);
      }
    };

    loadProducts();
  }, [isAdmin]);

  const filteredProducts = useMemo(() => {
    const query = productSearch.trim().toLowerCase();
    if (!query) {
      return products;
    }
    return products.filter((item) => String(item.nombre || '').toLowerCase().includes(query));
  }, [products, productSearch]);

  const handleSelectProduct = (item) => {
    setProductId(String(item.id));
    setProductSearch(item.nombre);
    setShowProductResults(false);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (!productId) {
      setMessage('Debes seleccionar un producto para la recomendación.');
      return;
    }
    if (!fecha) {
      setMessage('Debes indicar la fecha en la que aplica la recomendación.');
      return;
    }

    setSaving(true);
    try {
      const response = await fetch('/api/admin/recomendaciones-chef/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'create',
          producto_id: productId,
          fecha,
          comentario_chef: comentario,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo guardar la recomendación.');
      }

      setMessage(data.message || 'Recomendación creada correctamente.');
      setProductId('');
      setProductSearch('');
      setComentario('');
      setFecha(todayIsoDate());
    } catch (error) {
      setMessage(error.message || 'No se pudo guardar la recomendación.');
    } finally {
      setSaving(false);
    }
  };

  if (!isAdmin) {
    return (
      <section style={containerStyle(isMobile)}>
        <div style={badgeStyle}>Nueva recomendación</div>
        <h2 style={titleStyle(isMobile)}>Acceso restringido</h2>
        <div style={noticeStyle}>Solo el rol Administrador puede crear recomendaciones.</div>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          Volver al reporte
        </button>
      </section>
    );
  }

  return (
    <section style={containerStyle(isMobile)}>
      <style>
        {`.recommendation-picker-option:hover { background: rgba(255, 90, 90, 0.16); }
          .recommendation-picker-option:focus-visible { outline: 1px solid rgba(255, 132, 132, 0.8); }
          .recommendation-dark-textarea::placeholder { color: #cfb8b8; }
        `}
      </style>

      <div style={badgeStyle}>Nueva recomendación</div>
      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Registrar recomendación del chef</h2>
          <p style={subtitleStyle}>Busca el producto, define la fecha en la que aplica y agrega un comentario del chef si quieres.</p>
        </div>
      </div>

      {message ? <div style={noticeStyle}>{message}</div> : null}

      <form onSubmit={handleSubmit} style={panelStyle}>
        {loading ? <div style={emptyStateStyle}>Cargando productos...</div> : null}

        {!loading ? (
          <>
            <div style={formGridStyle(isMobile)}>
              <label style={fieldStyle}>
                <span style={labelStyle}>Producto</span>
                <div ref={productPickerRef} style={pickerWrapStyle}>
                  <input
                    value={productSearch}
                    onChange={(event) => {
                      setProductSearch(event.target.value);
                      setProductId('');
                      setShowProductResults(true);
                    }}
                    onFocus={() => setShowProductResults(true)}
                    placeholder="Buscar producto por nombre"
                    style={inputStyle}
                  />

                  {showProductResults ? (
                    <div style={pickerListStyle}>
                      {filteredProducts.length > 0 ? filteredProducts.map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          className="recommendation-picker-option"
                          onMouseDown={(event) => event.preventDefault()}
                          onClick={() => handleSelectProduct(item)}
                          style={pickerItemStyle}
                        >
                          <span style={pickerItemTitleStyle}>{item.nombre}</span>
                          <span style={pickerItemMetaStyle}>${item.precio_venta}</span>
                        </button>
                      )) : (
                        <div style={pickerEmptyStyle}>No hay productos que coincidan.</div>
                      )}
                    </div>
                  ) : null}
                </div>
              </label>

              <label style={fieldStyle}>
                <span style={labelStyle}>Fecha en la que aplica</span>
                <input
                  type="date"
                  value={fecha}
                  onChange={(event) => setFecha(event.target.value)}
                  style={inputStyle}
                />
              </label>

              <label style={{ ...fieldStyle, gridColumn: isMobile ? 'auto' : '1 / -1' }}>
                <span style={labelStyle}>Comentario del chef (opcional)</span>
                <textarea
                  value={comentario}
                  onChange={(event) => setComentario(event.target.value)}
                  style={textareaStyle}
                  className="recommendation-dark-textarea"
                  rows={3}
                  placeholder="Ej. Preparado con salsa de la casa, ideal para compartir"
                />
              </label>
            </div>

            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <button type="submit" style={primaryButtonStyle} disabled={saving}>
                {saving ? 'Guardando...' : 'Guardar recomendación'}
              </button>
              <button type="button" onClick={onBack} style={secondaryButtonStyle}>
                Volver al reporte
              </button>
            </div>
          </>
        ) : null}
      </form>
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

const formGridStyle = (isMobile) => ({
  display: 'grid',
  gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 1fr))',
  gap: 12,
});

const fieldStyle = {
  display: 'grid',
  gap: 6,
};

const labelStyle = {
  color: '#f0b4b4',
  fontSize: 13,
  fontWeight: 700,
};

const inputStyle = {
  width: '100%',
  boxSizing: 'border-box',
  borderRadius: 14,
  border: '1px solid rgba(255, 255, 255, 0.14)',
  background: '#161010',
  padding: '11px 12px',
  color: '#fff4f4',
  fontSize: 14,
};

const textareaStyle = {
  ...inputStyle,
  resize: 'vertical',
};

const pickerWrapStyle = {
  position: 'relative',
};

const pickerListStyle = {
  position: 'absolute',
  zIndex: 8,
  top: 'calc(100% + 6px)',
  left: 0,
  right: 0,
  maxHeight: 230,
  overflowY: 'auto',
  borderRadius: 14,
  border: '1px solid rgba(255, 132, 132, 0.4)',
  background: '#140d0d',
  boxShadow: '0 12px 24px rgba(0, 0, 0, 0.3)',
};

const pickerItemStyle = {
  width: '100%',
  textAlign: 'left',
  border: 'none',
  background: 'transparent',
  color: '#ffeaea',
  padding: '10px 12px',
  display: 'grid',
  gap: 3,
  cursor: 'pointer',
};

const pickerItemTitleStyle = {
  fontWeight: 700,
};

const pickerItemMetaStyle = {
  fontSize: 12,
  color: '#d8bcbc',
};

const pickerEmptyStyle = {
  padding: '10px 12px',
  color: '#d8bcbc',
  fontSize: 13,
};

const emptyStateStyle = {
  minHeight: 80,
  display: 'grid',
  placeItems: 'center',
  borderRadius: 18,
  border: '1px dashed rgba(255, 255, 255, 0.12)',
  color: '#c8bbbb',
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

export default AnalystNewChefRecommendationPage;

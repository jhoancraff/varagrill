import { useEffect, useRef, useState } from 'react';

const emptyForm = {
  id: null,
  nombre: '',
  descripcion: '',
  categoria_id: '',
  precio_venta: '',
  costo_estimado: '',
  tiempo_preparacion_min: '0',
  disponible: true,
  vinculo_tipo: '',
  vinculo_id: '',
};

function AnalystEditProductPage({ isMobile, isAdmin, productId, onBack, onProductsChanged }) {
  const [categories, setCategories] = useState([]);
  const [recetas, setRecetas] = useState([]);
  const [subrecetas, setSubrecetas] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [currentImageUrl, setCurrentImageUrl] = useState('');
  const [imageFile, setImageFile] = useState(null);
  const [imagePreview, setImagePreview] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const fileInputRef = useRef(null);

  useEffect(() => {
    if (!isAdmin) {
      setLoading(false);
      return;
    }

    const loadProduct = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/admin/productos/', {
          credentials: 'include',
          cache: 'no-store',
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || 'No se pudo cargar el producto.');
        }

        const selectedProduct = (data.products || []).find((entry) => String(entry.id) === String(productId));
        if (!selectedProduct) {
          throw new Error('El producto seleccionado no existe.');
        }

        setCategories(Array.isArray(data.categories) ? data.categories : []);
        setRecetas(Array.isArray(data.recetas) ? data.recetas : []);
        setSubrecetas(Array.isArray(data.subrecetas) ? data.subrecetas : []);
        const vinculoTipo = selectedProduct.receta_vinculada_id ? 'receta' : selectedProduct.subreceta_vinculada_id ? 'subreceta' : '';
        setForm({
          id: selectedProduct.id,
          nombre: selectedProduct.nombre || '',
          descripcion: selectedProduct.descripcion || '',
          categoria_id: selectedProduct.categoria_id ? String(selectedProduct.categoria_id) : '',
          precio_venta: selectedProduct.precio_venta || '',
          costo_estimado: selectedProduct.costo_estimado || '',
          tiempo_preparacion_min: String(selectedProduct.tiempo_preparacion_min ?? '0'),
          disponible: Boolean(selectedProduct.disponible),
          vinculo_tipo: vinculoTipo,
          vinculo_id: vinculoTipo === 'receta'
            ? String(selectedProduct.receta_vinculada_id)
            : vinculoTipo === 'subreceta'
              ? String(selectedProduct.subreceta_vinculada_id)
              : '',
        });
        setCurrentImageUrl(selectedProduct.imagen_url || '');
      } catch (error) {
        setMessage(error.message || 'No se pudo cargar el producto.');
      } finally {
        setLoading(false);
      }
    };

    loadProduct();
  }, [isAdmin, productId]);

  const handleChange = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const selectedVinculo = form.vinculo_id
    ? (form.vinculo_tipo === 'receta' ? recetas : subrecetas).find((item) => String(item.id) === String(form.vinculo_id))
    : null;

  const handleImageChange = (event) => {
    const file = event.target.files && event.target.files[0] ? event.target.files[0] : null;
    setImageFile(file);
    setImagePreview(file ? URL.createObjectURL(file) : '');
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (!form.categoria_id) {
      setMessage('Debes seleccionar una categoría para el producto.');
      return;
    }

    setSaving(true);
    try {
      const formData = new FormData();
      formData.append('action', 'update');
      formData.append('id', form.id);
      formData.append('nombre', form.nombre);
      formData.append('descripcion', form.descripcion);
      formData.append('categoria_id', form.categoria_id);
      formData.append('precio_venta', form.precio_venta || '0');
      formData.append('costo_estimado', form.costo_estimado);
      formData.append('tiempo_preparacion_min', form.tiempo_preparacion_min || '0');
      formData.append('disponible', form.disponible ? 'true' : 'false');
      formData.append('vinculo_tipo', form.vinculo_tipo);
      formData.append('vinculo_id', form.vinculo_id);
      if (imageFile) {
        formData.append('imagen', imageFile);
      }

      const response = await fetch('/api/admin/productos/', {
        method: 'POST',
        credentials: 'include',
        body: formData,
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo actualizar el producto.');
      }

      setMessage(data.message || 'Producto actualizado correctamente.');
      setCurrentImageUrl(data.product?.imagen_url || currentImageUrl);
      setImageFile(null);
      setImagePreview('');
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
      if (onProductsChanged) {
        onProductsChanged();
      }
    } catch (error) {
      setMessage(error.message || 'No se pudo actualizar el producto.');
    } finally {
      setSaving(false);
    }
  };

  if (!isAdmin) {
    return (
      <section style={containerStyle(isMobile)}>
        <div style={badgeStyle}>Editar producto</div>
        <h2 style={titleStyle(isMobile)}>Acceso restringido</h2>
        <div style={noticeStyle}>Solo el rol Administrador puede modificar productos.</div>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          Volver al reporte
        </button>
      </section>
    );
  }

  return (
    <section style={containerStyle(isMobile)}>
      <div style={badgeStyle}>Editar producto</div>
      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Actualización de producto</h2>
          <p style={subtitleStyle}>Modifica los datos del producto. Si no subes una imagen nueva, se conserva la actual.</p>
        </div>
      </div>

      {message ? <div style={noticeStyle}>{message}</div> : null}

      <form onSubmit={handleSubmit} style={panelStyle}>
        {loading ? <div style={emptyStateStyle}>Cargando producto...</div> : null}
        {!loading ? (
          <>
            <div style={formGridStyle(isMobile)}>
              <label style={fieldStyle}>
                <span style={labelStyle}>Nombre del producto</span>
                <input value={form.nombre} onChange={(event) => handleChange('nombre', event.target.value)} style={inputStyle} required />
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Categoría *</span>
                <select value={form.categoria_id} onChange={(event) => handleChange('categoria_id', event.target.value)} style={inputStyle} required>
                  <option value="">Selecciona una categoría</option>
                  {categories.map((category) => (
                    <option key={category.id} value={category.id}>{category.nombre}</option>
                  ))}
                </select>
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Precio de venta</span>
                <input type="number" min="0" step="0.01" value={form.precio_venta} onChange={(event) => handleChange('precio_venta', event.target.value)} style={inputStyle} />
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Costo estimado</span>
                <input type="number" min="0" step="0.01" value={form.costo_estimado} onChange={(event) => handleChange('costo_estimado', event.target.value)} style={inputStyle} />
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Tiempo de preparación (min)</span>
                <input type="number" min="0" step="1" value={form.tiempo_preparacion_min} onChange={(event) => handleChange('tiempo_preparacion_min', event.target.value)} style={inputStyle} />
              </label>
              <label style={toggleRowStyle}>
                <input type="checkbox" checked={form.disponible} onChange={(event) => handleChange('disponible', event.target.checked)} />
                <span>Producto disponible</span>
              </label>
            </div>

            <div style={linkCardStyle}>
              <div style={labelStyle}>Vincular con Receta o Subreceta (opcional)</div>
              <p style={linkHintStyle}>Así, cuando el mesero pida este producto, cocina verá también de qué está compuesto.</p>
              <div style={formGridStyle(isMobile)}>
                <label style={fieldStyle}>
                  <span style={labelStyle}>Tipo de vínculo</span>
                  <select
                    value={form.vinculo_tipo}
                    onChange={(event) => setForm((current) => ({ ...current, vinculo_tipo: event.target.value, vinculo_id: '' }))}
                    style={inputStyle}
                  >
                    <option value="">Ninguno</option>
                    <option value="receta">Receta</option>
                    <option value="subreceta">Subreceta</option>
                  </select>
                </label>
                {form.vinculo_tipo ? (
                  <label style={fieldStyle}>
                    <span style={labelStyle}>{form.vinculo_tipo === 'receta' ? 'Receta' : 'Subreceta'}</span>
                    <select value={form.vinculo_id} onChange={(event) => handleChange('vinculo_id', event.target.value)} style={inputStyle}>
                      <option value="">Selecciona...</option>
                      {(form.vinculo_tipo === 'receta' ? recetas : subrecetas).map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.nombre} — costo unitario: ${Number(item.costo_unitario_calculado || 0).toFixed(2)}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
              </div>

              {selectedVinculo ? (
                <div style={costReferenceBoxStyle}>
                  <div>
                    <div style={costReferenceLabelStyle}>Costo unitario calculado de "{selectedVinculo.nombre}"</div>
                    <div style={costReferenceValueStyle}>${Number(selectedVinculo.costo_unitario_calculado || 0).toFixed(2)}</div>
                    <p style={costReferenceHintStyle}>
                      Es la suma del costo de los ingredientes/subrecetas de esta receta. Úsalo como referencia para definir el costo real del producto (empaque, mano de obra, etc.).
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleChange('costo_estimado', selectedVinculo.costo_unitario_calculado)}
                    style={useCostButtonStyle}
                  >
                    Usar este valor
                  </button>
                </div>
              ) : null}
            </div>

            <label style={fieldStyle}>
              <span style={labelStyle}>Descripción</span>
              <textarea rows={3} value={form.descripcion} onChange={(event) => handleChange('descripcion', event.target.value)} style={{ ...inputStyle, resize: 'vertical' }} />
            </label>

            <label style={fieldStyle}>
              <span style={labelStyle}>Reemplazar imagen (JPG, PNG, WEBP o GIF, máx. 5MB)</span>
              <input ref={fileInputRef} type="file" accept="image/jpeg,image/png,image/webp,image/gif" onChange={handleImageChange} style={inputStyle} />
            </label>

            <div style={previewRowStyle}>
              {currentImageUrl ? (
                <div>
                  <div style={previewLabelStyle}>Imagen actual</div>
                  <img src={currentImageUrl} alt={form.nombre} style={previewImageStyle} />
                </div>
              ) : (
                <div style={previewLabelStyle}>Este producto aún no tiene imagen.</div>
              )}
              {imagePreview ? (
                <div>
                  <div style={previewLabelStyle}>Imagen nueva</div>
                  <img src={imagePreview} alt="Vista previa" style={previewImageStyle} />
                </div>
              ) : null}
            </div>

            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <button type="submit" style={primaryButtonStyle} disabled={saving}>
                {saving ? 'Guardando...' : 'Guardar cambios'}
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
  maxWidth: 720,
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

const emptyStateStyle = {
  minHeight: 80,
  display: 'grid',
  placeItems: 'center',
  borderRadius: 18,
  border: '1px dashed rgba(255, 255, 255, 0.12)',
  color: '#c8bbbb',
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
  background: 'rgba(255, 255, 255, 0.04)',
  padding: '11px 12px',
  color: '#fff',
  fontSize: 14,
};

const toggleRowStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 10,
  color: '#fff',
  fontWeight: 600,
  minHeight: 42,
};

const linkCardStyle = {
  display: 'grid',
  gap: 8,
  padding: 14,
  borderRadius: 14,
  border: '1px solid rgba(255,255,255,0.08)',
  background: 'rgba(255,255,255,0.02)',
};

const linkHintStyle = {
  margin: 0,
  color: '#c2adad',
  fontSize: 12.5,
};

const costReferenceBoxStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 14,
  flexWrap: 'wrap',
  padding: '12px 14px',
  borderRadius: 14,
  border: '1px solid rgba(120, 220, 160, 0.35)',
  background: 'rgba(70, 200, 120, 0.08)',
};

const costReferenceLabelStyle = {
  color: '#bdf0cf',
  fontSize: 12,
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
};

const costReferenceValueStyle = {
  color: '#7dffa0',
  fontSize: 22,
  fontWeight: 800,
  marginTop: 2,
};

const costReferenceHintStyle = {
  margin: '4px 0 0',
  color: '#c2adad',
  fontSize: 12,
  maxWidth: 480,
};

const useCostButtonStyle = {
  border: '1px solid rgba(125, 255, 160, 0.4)',
  borderRadius: 999,
  padding: '9px 14px',
  background: 'rgba(125, 255, 160, 0.12)',
  color: '#bdf0cf',
  fontWeight: 700,
  cursor: 'pointer',
  whiteSpace: 'nowrap',
};

const previewRowStyle = {
  display: 'flex',
  gap: 20,
  flexWrap: 'wrap',
};

const previewLabelStyle = {
  color: '#f0b4b4',
  fontSize: 12,
  fontWeight: 700,
  marginBottom: 6,
};

const previewImageStyle = {
  width: 140,
  height: 140,
  objectFit: 'cover',
  borderRadius: 16,
  border: '1px solid rgba(255, 255, 255, 0.14)',
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

export default AnalystEditProductPage;
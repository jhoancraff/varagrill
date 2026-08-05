import { useEffect, useRef, useState } from 'react';

const emptyForm = {
  nombre: '',
  descripcion: '',
  categoria_id: '',
  precio_venta: '',
  costo_estimado: '',
  tiempo_preparacion_min: '0',
  disponible: true,
};

function AnalystNewProductPage({ isMobile, isAdmin, onBack, onProductsChanged }) {
  const [categories, setCategories] = useState([]);
  const [form, setForm] = useState(emptyForm);
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

    const loadCategories = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/admin/productos/', {
          credentials: 'include',
          cache: 'no-store',
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || 'No se pudieron cargar las categorías.');
        }
        setCategories(Array.isArray(data.categories) ? data.categories : []);
      } catch (error) {
        setMessage(error.message || 'No se pudieron cargar las categorías.');
      } finally {
        setLoading(false);
      }
    };

    loadCategories();
  }, [isAdmin]);

  const handleChange = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

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
      formData.append('action', 'create');
      formData.append('nombre', form.nombre);
      formData.append('descripcion', form.descripcion);
      formData.append('categoria_id', form.categoria_id);
      formData.append('precio_venta', form.precio_venta || '0');
      formData.append('costo_estimado', form.costo_estimado);
      formData.append('tiempo_preparacion_min', form.tiempo_preparacion_min || '0');
      formData.append('disponible', form.disponible ? 'true' : 'false');
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
        throw new Error(data.message || 'No se pudo crear el producto.');
      }

      setMessage(data.message || 'Producto creado correctamente.');
      setForm(emptyForm);
      setImageFile(null);
      setImagePreview('');
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
      if (onProductsChanged) {
        onProductsChanged();
      }
    } catch (error) {
      setMessage(error.message || 'No se pudo crear el producto.');
    } finally {
      setSaving(false);
    }
  };

  if (!isAdmin) {
    return (
      <section style={containerStyle(isMobile)}>
        <div style={badgeStyle}>Nuevo producto</div>
        <h2 style={titleStyle(isMobile)}>Acceso restringido</h2>
        <div style={noticeStyle}>Solo el rol Administrador puede crear productos.</div>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          Volver a productos
        </button>
      </section>
    );
  }

  return (
    <section style={containerStyle(isMobile)}>
      <div style={badgeStyle}>Nuevo producto</div>
      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Registrar producto nuevo</h2>
          <p style={subtitleStyle}>Sube la foto del plato o bebida desde el dispositivo y asígnale una categoría del menú.</p>
        </div>
      </div>

      {message ? <div style={noticeStyle}>{message}</div> : null}

      <form onSubmit={handleSubmit} style={panelStyle}>
        {loading ? <div style={emptyStateStyle}>Cargando categorías...</div> : null}
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

            <label style={fieldStyle}>
              <span style={labelStyle}>Descripción</span>
              <textarea rows={3} value={form.descripcion} onChange={(event) => handleChange('descripcion', event.target.value)} style={{ ...inputStyle, resize: 'vertical' }} />
            </label>

            <label style={fieldStyle}>
              <span style={labelStyle}>Imagen del producto (JPG, PNG, WEBP o GIF, máx. 5MB)</span>
              <input ref={fileInputRef} type="file" accept="image/jpeg,image/png,image/webp,image/gif" onChange={handleImageChange} style={inputStyle} />
            </label>

            {imagePreview ? (
              <div style={previewWrapStyle}>
                <img src={imagePreview} alt="Vista previa" style={previewImageStyle} />
              </div>
            ) : null}

            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <button type="submit" style={primaryButtonStyle} disabled={saving}>
                {saving ? 'Guardando...' : 'Crear producto'}
              </button>
              <button type="button" onClick={onBack} style={secondaryButtonStyle}>
                Volver a productos
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

const previewWrapStyle = {
  display: 'flex',
  justifyContent: 'flex-start',
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

export default AnalystNewProductPage;

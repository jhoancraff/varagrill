import { useEffect, useState } from 'react';

const emptyForm = {
  id: '',
  nombre: '',
  unidad: 'kg',
  stock_actual: '',
  stock_minimo: '',
  costo_unitario: '',
  proveedor: '',
};

function AnalystEditIngredientPage({ isMobile, ingredientId, onBack }) {
  const [form, setForm] = useState(emptyForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/admin/catalogo/', {
          credentials: 'include',
          cache: 'no-store',
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || 'No se pudo cargar el ingrediente.');
        }

        const item = (data.inventory || []).find((entry) => String(entry.id) === String(ingredientId));
        if (!item) {
          throw new Error('El ingrediente seleccionado no existe.');
        }

        setForm({
          id: item.id,
          nombre: item.nombre || '',
          unidad: item.unidad_medida || 'kg',
          stock_actual: item.stock_actual || '0',
          stock_minimo: item.stock_minimo || '0',
          costo_unitario: item.costo_unitario || '0',
          proveedor: item.ultimo_proveedor || '',
        });
      } catch (error) {
        setMessage(error.message || 'No se pudo cargar el ingrediente.');
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [ingredientId]);

  const handleChange = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);

    try {
      const response = await fetch('/api/admin/catalogo/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tipo: 'actualizar_ingrediente',
          id: form.id,
          nombre: form.nombre,
          unidad: form.unidad,
          stock_actual: form.stock_actual,
          stock_minimo: form.stock_minimo,
          costo_unitario: form.costo_unitario,
          proveedor: form.proveedor,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo actualizar el ingrediente.');
      }

      setMessage(data.message || 'Ingrediente actualizado correctamente.');
    } catch (error) {
      setMessage(error.message || 'No se pudo actualizar el ingrediente.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <section style={containerStyle(isMobile)}>
      <h2 style={titleStyle(isMobile)}>Editar ingrediente</h2>
      {message ? <div style={noticeStyle}>{message}</div> : null}

      <form onSubmit={handleSubmit} style={panelStyle}>
        {loading ? <div style={emptyStyle}>Cargando ingrediente...</div> : null}
        {!loading ? (
          <>
            <div style={gridStyle(isMobile)}>
              <label style={fieldStyle}><span style={labelStyle}>Nombre</span><input value={form.nombre} onChange={(e) => handleChange('nombre', e.target.value)} style={inputStyle} /></label>
              <label style={fieldStyle}><span style={labelStyle}>Unidad</span><input value={form.unidad} onChange={(e) => handleChange('unidad', e.target.value)} style={inputStyle} /></label>
              <label style={fieldStyle}><span style={labelStyle}>Stock actual</span><input type="number" step="0.001" value={form.stock_actual} onChange={(e) => handleChange('stock_actual', e.target.value)} style={inputStyle} /></label>
              <label style={fieldStyle}><span style={labelStyle}>Stock minimo</span><input type="number" step="0.001" value={form.stock_minimo} onChange={(e) => handleChange('stock_minimo', e.target.value)} style={inputStyle} /></label>
              <label style={fieldStyle}><span style={labelStyle}>Costo unitario</span><input type="number" step="0.01" value={form.costo_unitario} onChange={(e) => handleChange('costo_unitario', e.target.value)} style={inputStyle} /></label>
              <label style={fieldStyle}><span style={labelStyle}>Proveedor</span><input value={form.proveedor} onChange={(e) => handleChange('proveedor', e.target.value)} style={inputStyle} /></label>
            </div>

            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <button type="submit" style={primaryButtonStyle} disabled={saving}>{saving ? 'Guardando...' : 'Guardar cambios'}</button>
              <button type="button" onClick={onBack} style={secondaryButtonStyle}>Volver al reporte</button>
            </div>
          </>
        ) : null}
      </form>
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 28 : 34 });
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const gridStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 1fr))', gap: 12 });
const fieldStyle = { display: 'grid', gap: 6 };
const labelStyle = { color: '#f0b4b4', fontSize: 13, fontWeight: 700 };
const inputStyle = { borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const secondaryButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };

export default AnalystEditIngredientPage;

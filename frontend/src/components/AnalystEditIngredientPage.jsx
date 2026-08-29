import { useEffect, useMemo, useState } from 'react';
import UnsavedChangesModal from './UnsavedChangesModal';
import Toast from './Toast';
import useUnsavedChangesGuard from '../hooks/useUnsavedChangesGuard';
import useToast from '../hooks/useToast';

const emptyForm = {
  id: '',
  nombre: '',
  unidad: 'g',
  stock_actual: '',
  stock_minimo: '',
  costo_unitario: '',
  contenido_envase: '',
  peso_real: '',
  precio_compra: '',
  ingrediente_crudo_equivalente_id: '',
  rendimiento_ingrediente_crudo: '',
  proveedor: '',
};

const unidadOptions = [
  { value: 'g', label: 'Gramos (g)' },
  { value: 'ml', label: 'Mililitros (ml)' },
  { value: 'unidad', label: 'Unidad' },
];

function AnalystEditIngredientPage({ isMobile, ingredientId, onBack }) {
  const [form, setForm] = useState(emptyForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [inventory, setInventory] = useState([]);
  const { toast, showSuccess, showError, hideToast } = useToast();
  const { guard, isConfirmOpen, confirmLeave, cancelLeave, markClean } = useUnsavedChangesGuard(form);

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

        const items = data.inventory || [];
        const item = items.find((entry) => String(entry.id) === String(ingredientId));
        if (!item) {
          throw new Error('El ingrediente seleccionado no existe.');
        }
        setInventory(items);

        const loadedForm = {
          id: item.id,
          nombre: item.nombre || '',
          unidad: item.unidad_medida || 'kg',
          stock_actual: item.stock_actual || '0',
          stock_minimo: item.stock_minimo || '0',
          costo_unitario: item.costo_unitario || '0',
          contenido_envase: item.contenido_envase ?? '',
          peso_real: item.peso_real ?? '',
          precio_compra: item.precio_compra ?? '',
          ingrediente_crudo_equivalente_id: item.ingrediente_crudo_equivalente ?? '',
          rendimiento_ingrediente_crudo: item.rendimiento_ingrediente_crudo ?? '',
          proveedor: item.ultimo_proveedor || '',
        };
        setForm(loadedForm);
        markClean(loadedForm);
      } catch (error) {
        showError(error.message || 'No se pudo cargar el ingrediente.');
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [ingredientId]);

  const handleChange = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const costoUnitarioCalculado = useMemo(() => {
    const precio = Number(form.precio_compra);
    const peso = Number(form.peso_real);
    if (!form.precio_compra || !form.peso_real || !Number.isFinite(precio) || !Number.isFinite(peso) || peso <= 0) {
      return null;
    }
    return precio / peso;
  }, [form.precio_compra, form.peso_real]);

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
          contenido_envase: form.contenido_envase || null,
          peso_real: form.peso_real || null,
          precio_compra: form.precio_compra || null,
          ingrediente_crudo_equivalente_id: form.ingrediente_crudo_equivalente_id || null,
          rendimiento_ingrediente_crudo: form.rendimiento_ingrediente_crudo || null,
          proveedor: form.proveedor,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo actualizar el ingrediente.');
      }

      showSuccess(data.message || 'Ingrediente actualizado correctamente.');
      markClean(form);
    } catch (error) {
      showError(error.message || 'No se pudo actualizar el ingrediente.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <section style={containerStyle(isMobile)}>
      <h2 style={titleStyle(isMobile)}>Editar ingrediente</h2>
      <Toast toast={toast} onClose={hideToast} />

      <form onSubmit={handleSubmit} style={panelStyle}>
        {loading ? <div style={emptyStyle}>Cargando ingrediente...</div> : null}
        {!loading ? (
          <>
            <div style={gridStyle(isMobile)}>
              <label style={fieldStyle}><span style={labelStyle}>Nombre</span><input value={form.nombre} onChange={(e) => handleChange('nombre', e.target.value)} style={inputStyle} /></label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Unidad</span>
                <select value={form.unidad} onChange={(e) => handleChange('unidad', e.target.value)} style={inputStyle}>
                  {unidadOptions.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>
              <label style={fieldStyle}><span style={labelStyle}>Stock actual</span><input type="number" step="0.001" value={form.stock_actual} onChange={(e) => handleChange('stock_actual', e.target.value)} style={inputStyle} /></label>
              <label style={fieldStyle}><span style={labelStyle}>Stock minimo</span><input type="number" step="0.001" value={form.stock_minimo} onChange={(e) => handleChange('stock_minimo', e.target.value)} style={inputStyle} /></label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Costo unitario{costoUnitarioCalculado !== null ? ' (calculado)' : ''}</span>
                <input
                  type="text"
                  disabled={costoUnitarioCalculado !== null}
                  value={costoUnitarioCalculado !== null ? costoUnitarioCalculado.toFixed(6) : form.costo_unitario}
                  onChange={(e) => handleChange('costo_unitario', e.target.value)}
                  style={costoUnitarioCalculado !== null ? { ...inputStyle, color: '#c8bbbb', cursor: 'not-allowed' } : inputStyle}
                />
              </label>
              <label style={fieldStyle}><span style={labelStyle}>Proveedor</span><input value={form.proveedor} onChange={(e) => handleChange('proveedor', e.target.value)} style={inputStyle} /></label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Contenido del envase</span>
                <input type="number" step="0.01" value={form.contenido_envase} onChange={(e) => handleChange('contenido_envase', e.target.value)} style={inputStyle} placeholder="Ej: 1000 (una bolsa de 1kg)" />
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Peso real (utilizable)</span>
                <input type="number" step="0.01" value={form.peso_real} onChange={(e) => handleChange('peso_real', e.target.value)} style={inputStyle} placeholder="Igual al de arriba si no hay pérdida" />
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Precio de compra</span>
                <input type="number" step="0.01" value={form.precio_compra} onChange={(e) => handleChange('precio_compra', e.target.value)} style={inputStyle} placeholder="Lo pagado por ese envase" />
              </label>
              <p style={helpTextStyle}>
                Contenido del envase y peso real se usan juntos para calcular el costo por gramo/ml/unidad al
                confirmar una compra — completá los dos o dejá los dos vacíos. Si además cargás el precio de
                compra de ese envase, el costo unitario de arriba se calcula solo (precio de compra ÷ peso real)
                y deja de editarse a mano.
              </p>

              <label style={fieldStyle}>
                <span style={labelStyle}>Ingrediente crudo equivalente</span>
                <select
                  value={form.ingrediente_crudo_equivalente_id}
                  onChange={(e) => handleChange('ingrediente_crudo_equivalente_id', e.target.value)}
                  style={inputStyle}
                >
                  <option value="">No es un empacado / no aplica</option>
                  {inventory
                    .filter((entry) => String(entry.id) !== String(form.id))
                    .map((entry) => (
                      <option key={entry.id} value={entry.id}>{entry.nombre}</option>
                    ))}
                </select>
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Rinde (cantidad de crudo por paquete)</span>
                <input
                  type="number"
                  step="0.01"
                  value={form.rendimiento_ingrediente_crudo}
                  onChange={(e) => handleChange('rendimiento_ingrediente_crudo', e.target.value)}
                  style={inputStyle}
                  placeholder="Ej: 500 (500g de carne cruda por paquete)"
                />
              </label>
              <p style={helpTextStyle}>
                Completá esto solo si este ingrediente es un producto empacado para reventa (ej. carne al
                vacío, patacones empacados): permite usar la acción "Reponer cocina" para abrir paquetes y
                sumar su contenido al ingrediente crudo cuando la cocina se quede sin materia prima.
              </p>
            </div>

            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <button type="submit" style={primaryButtonStyle} disabled={saving}>{saving ? 'Guardando...' : 'Guardar cambios'}</button>
              <button type="button" onClick={() => guard(onBack)} style={secondaryButtonStyle}>Volver al reporte</button>
            </div>
          </>
        ) : null}
      </form>

      <UnsavedChangesModal open={isConfirmOpen} onConfirm={confirmLeave} onCancel={cancelLeave} />
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
const helpTextStyle = { gridColumn: '1 / -1', margin: 0, color: '#c8bbbb', fontSize: 12, lineHeight: 1.5 };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const secondaryButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };

export default AnalystEditIngredientPage;

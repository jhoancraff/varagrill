import { useEffect, useMemo, useState } from 'react';
import UnsavedChangesModal from './UnsavedChangesModal';
import Toast from './Toast';
import useUnsavedChangesGuard from '../hooks/useUnsavedChangesGuard';
import useToast from '../hooks/useToast';

const emptyForm = {
  nombre: '',
  unidad: 'g',
  stock_actual: '',
  stock_minimo: '',
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

function AnalystNewIngredientPage({ isMobile, onBack, onEditExisting }) {
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const { toast, showSuccess, showError, hideToast } = useToast();
  const [inventory, setInventory] = useState([]);
  const [loadingInventory, setLoadingInventory] = useState(true);
  const [isNameFocused, setIsNameFocused] = useState(false);
  const { guard, isConfirmOpen, confirmLeave, cancelLeave, markClean } = useUnsavedChangesGuard(form);

  useEffect(() => {
    const loadInventory = async () => {
      setLoadingInventory(true);
      try {
        const response = await fetch('/api/admin/catalogo/', {
          credentials: 'include',
          cache: 'no-store',
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || 'No se pudo cargar el inventario actual.');
        }
        setInventory(Array.isArray(data.inventory) ? data.inventory : []);
      } catch (error) {
        // Si falla la carga del inventario, igual se puede crear el ingrediente sin el buscador.
      } finally {
        setLoadingInventory(false);
      }
    };

    loadInventory();
  }, []);

  const nameQuery = form.nombre.trim().toLowerCase();

  const nameMatches = useMemo(() => {
    if (!nameQuery) {
      return [];
    }
    return inventory
      .filter((item) => (item.nombre || '').toLowerCase().includes(nameQuery))
      .slice(0, 6);
  }, [inventory, nameQuery]);

  const exactMatch = useMemo(
    () => inventory.find((item) => (item.nombre || '').toLowerCase() === nameQuery) || null,
    [inventory, nameQuery],
  );

  const costoUnitarioCalculado = useMemo(() => {
    const precio = Number(form.precio_compra);
    const peso = Number(form.peso_real);
    if (!form.precio_compra || !form.peso_real || !Number.isFinite(precio) || !Number.isFinite(peso) || peso <= 0) {
      return null;
    }
    return precio / peso;
  }, [form.precio_compra, form.peso_real]);

  const handleChange = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const handleSelectExisting = (item) => {
    setForm((current) => ({ ...current, nombre: item.nombre }));
    setIsNameFocused(false);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (exactMatch) {
      showError(`Ya existe un ingrediente llamado "${exactMatch.nombre}". Edítalo en vez de crear uno duplicado.`);
      return;
    }

    if (!form.contenido_envase || !form.peso_real || !form.precio_compra) {
      showError('El contenido del envase, el peso real y el precio de compra son obligatorios para calcular bien el costo por gramo.');
      return;
    }

    setSaving(true);

    try {
      const response = await fetch('/api/admin/catalogo/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tipo: 'crear_ingrediente',
          nombre: form.nombre,
          unidad: form.unidad,
          stock_actual: form.stock_actual || '0',
          stock_minimo: form.stock_minimo || '0',
          contenido_envase: form.contenido_envase,
          peso_real: form.peso_real,
          precio_compra: form.precio_compra,
          ingrediente_crudo_equivalente_id: form.ingrediente_crudo_equivalente_id || '',
          rendimiento_ingrediente_crudo: form.rendimiento_ingrediente_crudo || '',
          proveedor: form.proveedor,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo crear el ingrediente.');
      }

      showSuccess(data.message || 'Ingrediente creado correctamente.');
      setForm(emptyForm);
      markClean(emptyForm);
      setInventory((current) => [...current, { id: data.item?.id, nombre: data.item?.nombre || form.nombre }]);
    } catch (error) {
      showError(error.message || 'No se pudo crear el ingrediente.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <section style={containerStyle(isMobile)}>
      <h2 style={titleStyle(isMobile)}>Nuevo ingrediente</h2>
      <p style={subtitleStyle}>Para el ingreso de mercancía: busca primero si el ingrediente ya existe antes de crear uno nuevo.</p>
      <Toast toast={toast} onClose={hideToast} />

      <form onSubmit={handleSubmit} style={panelStyle}>
        <div style={gridStyle(isMobile)}>
          <div style={{ ...fieldStyle, position: 'relative' }}>
            <span style={labelStyle}>Nombre</span>
            <input
              value={form.nombre}
              onChange={(e) => handleChange('nombre', e.target.value)}
              onFocus={() => setIsNameFocused(true)}
              onBlur={() => setTimeout(() => setIsNameFocused(false), 150)}
              placeholder={loadingInventory ? 'Cargando ingredientes actuales...' : 'Ejemplo: Tomate, Queso blanco...'}
              style={inputStyle}
              autoComplete="off"
            />

            {isNameFocused && nameQuery && nameMatches.length > 0 ? (
              <div style={suggestionsPanelStyle}>
                <div style={suggestionsHintStyle}>Ingredientes existentes con ese nombre:</div>
                {nameMatches.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => handleSelectExisting(item)}
                    style={suggestionRowStyle}
                  >
                    <span style={{ color: '#fff', fontWeight: 600 }}>{item.nombre}</span>
                    <span style={{ color: '#e8bcbc', fontSize: 12 }}>
                      Stock: {item.stock_actual || '0'} {item.unidad_medida || ''}
                    </span>
                  </button>
                ))}
              </div>
            ) : null}

            {exactMatch ? (
              <div style={duplicateWarningStyle}>
                Ya existe un ingrediente llamado "{exactMatch.nombre}".
                {onEditExisting ? (
                  <button type="button" onClick={() => onEditExisting(exactMatch.id)} style={duplicateLinkStyle}>
                    Ir a editarlo
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>

          <label style={fieldStyle}>
            <span style={labelStyle}>Unidad</span>
            <select value={form.unidad} onChange={(e) => handleChange('unidad', e.target.value)} style={inputStyle}>
              {unidadOptions.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>

          <label style={fieldStyle}><span style={labelStyle}>Stock inicial</span><input type="number" step="0.001" value={form.stock_actual} onChange={(e) => handleChange('stock_actual', e.target.value)} style={inputStyle} /></label>
          <label style={fieldStyle}><span style={labelStyle}>Stock minimo</span><input type="number" step="0.001" value={form.stock_minimo} onChange={(e) => handleChange('stock_minimo', e.target.value)} style={inputStyle} /></label>
          <label style={fieldStyle}><span style={labelStyle}>Proveedor</span><input value={form.proveedor} onChange={(e) => handleChange('proveedor', e.target.value)} style={inputStyle} /></label>
          <label style={fieldStyle}>
            <span style={labelStyle}>Contenido del envase *</span>
            <input type="number" step="0.01" required value={form.contenido_envase} onChange={(e) => handleChange('contenido_envase', e.target.value)} style={inputStyle} placeholder="Ej: 1000 (una bolsa de 1kg)" />
          </label>
          <label style={fieldStyle}>
            <span style={labelStyle}>Peso real (utilizable) *</span>
            <input type="number" step="0.01" required value={form.peso_real} onChange={(e) => handleChange('peso_real', e.target.value)} style={inputStyle} placeholder="Igual al de arriba si no hay pérdida" />
          </label>
          <label style={fieldStyle}>
            <span style={labelStyle}>Precio de compra *</span>
            <input type="number" step="0.01" required value={form.precio_compra} onChange={(e) => handleChange('precio_compra', e.target.value)} style={inputStyle} placeholder="Lo pagado por ese envase" />
          </label>
          <label style={fieldStyle}>
            <span style={labelStyle}>Costo unitario (calculado)</span>
            <input type="text" disabled value={costoUnitarioCalculado !== null ? costoUnitarioCalculado.toFixed(6) : '—'} style={{ ...inputStyle, color: '#c8bbbb', cursor: 'not-allowed' }} />
          </label>
          <p style={helpTextStyle}>
            Cuánto trae el envase según la etiqueta, cuánto queda realmente utilizable después de pelar, deshuesar o
            limpiar, y cuánto costó ese envase. Con esto el costo unitario se calcula solo (precio de compra ÷ peso
            real) — igualá contenido del envase y peso real si el ingrediente no tiene ninguna merma.
          </p>

          <label style={fieldStyle}>
            <span style={labelStyle}>Ingrediente crudo equivalente</span>
            <select
              value={form.ingrediente_crudo_equivalente_id}
              onChange={(e) => handleChange('ingrediente_crudo_equivalente_id', e.target.value)}
              style={inputStyle}
            >
              <option value="">No es un empacado / no aplica</option>
              {inventory.map((item) => (
                <option key={item.id} value={item.id}>{item.nombre}</option>
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
            Completá esto solo si este ingrediente es un producto empacado para reventa (ej. carne al vacío,
            patacones empacados): permite usar la acción "Reponer cocina" para abrir paquetes y sumar su
            contenido al ingrediente crudo cuando la cocina se quede sin materia prima.
          </p>
        </div>

        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <button type="submit" style={primaryButtonStyle} disabled={saving || Boolean(exactMatch)}>{saving ? 'Guardando...' : 'Crear ingrediente'}</button>
          <button type="button" onClick={() => guard(onBack)} style={secondaryButtonStyle}>Volver al reporte</button>
        </div>
      </form>

      <UnsavedChangesModal open={isConfirmOpen} onConfirm={confirmLeave} onCancel={cancelLeave} />
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: 0, color: '#d2c3c3', fontSize: 13 };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const gridStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 1fr))', gap: 12 });
const fieldStyle = { display: 'grid', gap: 6 };
const labelStyle = { color: '#f0b4b4', fontSize: 13, fontWeight: 700 };
const inputStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };
const helpTextStyle = { gridColumn: '1 / -1', margin: 0, color: '#c8bbbb', fontSize: 12, lineHeight: 1.5 };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const secondaryButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };

const suggestionsPanelStyle = {
  position: 'absolute',
  top: '100%',
  left: 0,
  right: 0,
  marginTop: 6,
  zIndex: 5,
  borderRadius: 12,
  border: '1px solid rgba(255,255,255,0.14)',
  background: 'rgba(10, 8, 8, 0.98)',
  boxShadow: '0 12px 30px rgba(0,0,0,0.4)',
  padding: 8,
  display: 'grid',
  gap: 4,
  maxHeight: 240,
  overflowY: 'auto',
};

const suggestionsHintStyle = {
  color: '#e8bcbc',
  fontSize: 11,
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  padding: '4px 6px',
};

const suggestionRowStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 8,
  border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: 10,
  padding: '9px 10px',
  background: 'rgba(255,255,255,0.04)',
  cursor: 'pointer',
  textAlign: 'left',
};

const duplicateWarningStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  flexWrap: 'wrap',
  marginTop: 4,
  padding: '9px 12px',
  borderRadius: 10,
  border: '1px solid rgba(255,187,102,0.35)',
  background: 'rgba(255,153,51,0.12)',
  color: '#ffdcae',
  fontSize: 12.5,
};

const duplicateLinkStyle = {
  border: 'none',
  background: 'transparent',
  color: '#ffb74d',
  fontWeight: 700,
  textDecoration: 'underline',
  cursor: 'pointer',
  fontSize: 12.5,
  padding: 0,
};

export default AnalystNewIngredientPage;

import { useEffect, useRef, useState } from 'react';

const NEW_INGREDIENT_VALUE = '__new__';

const emptyForm = {
  ingrediente_id: '',
  nombre: '',
  unidad: 'kg',
  cantidad: '',
  stock_minimo: '',
  precio_total: '',
  proveedor: '',
  numero_factura_proveedor: '',
  fecha_factura: '',
};

const UNIDAD_LABELS = {
  kg: 'kg',
  g: 'g',
  l: 'L',
  ml: 'ml',
  unidad: 'unidad',
};

function AnalystIngredientsPage({ isMobile, onBack }) {
  const ingredientPickerRef = useRef(null);
  const [inventory, setInventory] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [ingredientSearch, setIngredientSearch] = useState('');
  const [showIngredientResults, setShowIngredientResults] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    const handlePointerDown = (event) => {
      if (ingredientPickerRef.current && !ingredientPickerRef.current.contains(event.target)) {
        setShowIngredientResults(false);
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
    const loadInventory = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/admin/catalogo/', {
          credentials: 'include',
          cache: 'no-store',
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || 'No se pudo cargar el inventario.');
        }
        setInventory(Array.isArray(data.inventory) ? data.inventory : []);
      } catch (error) {
        setMessage(error.message || 'No se pudo cargar el inventario.');
      } finally {
        setLoading(false);
      }
    };

    loadInventory();
  }, []);

  const isCreatingNew = form.ingrediente_id === NEW_INGREDIENT_VALUE;
  const cantidadNumber = Number(form.cantidad);
  const precioTotalNumber = Number(form.precio_total);
  const computedUnitCost = cantidadNumber > 0 && precioTotalNumber > 0
    ? (precioTotalNumber / cantidadNumber).toFixed(4)
    : null;
  const filteredInventory = inventory.filter((item) => {
    const query = ingredientSearch.trim().toLowerCase();
    if (!query) {
      return true;
    }
    return String(item.nombre || '').toLowerCase().includes(query);
  });

  const handleSelectIngredient = (value) => {
    if (value === NEW_INGREDIENT_VALUE) {
      setForm((current) => ({
        ...current,
        ingrediente_id: NEW_INGREDIENT_VALUE,
        nombre: '',
        unidad: 'kg',
        stock_minimo: '',
        precio_total: '',
        proveedor: '',
      }));
      setIngredientSearch('');
      setShowIngredientResults(false);
      return;
    }

    const selectedIngredient = inventory.find((item) => String(item.id) === String(value));
    setForm((current) => ({
      ...current,
      ingrediente_id: value,
      nombre: selectedIngredient?.nombre || '',
      unidad: selectedIngredient?.unidad_medida || 'kg',
      stock_minimo: selectedIngredient?.stock_minimo || '',
      precio_total: '',
      proveedor: selectedIngredient?.ultimo_proveedor || '',
    }));
    setIngredientSearch(selectedIngredient?.nombre || '');
    setShowIngredientResults(false);
  };

  const handleChange = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      const payload = {
        tipo: 'inventario',
        ingrediente_id: isCreatingNew ? null : form.ingrediente_id || null,
        nombre: form.nombre,
        unidad: form.unidad,
        cantidad: form.cantidad,
        stock_minimo: form.stock_minimo || '0',
        precio_total: form.precio_total || '0',
        proveedor: form.proveedor,
        numero_factura_proveedor: form.numero_factura_proveedor,
        fecha_factura: form.fecha_factura,
      };

      const response = await fetch('/api/admin/catalogo/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo registrar el ingreso.');
      }

      setMessage(data.message || 'Ingreso registrado correctamente.');
      setForm(emptyForm);
      setIngredientSearch('');
      setShowIngredientResults(false);

      const refreshResponse = await fetch('/api/admin/catalogo/', {
        credentials: 'include',
        cache: 'no-store',
      });
      const refreshData = await refreshResponse.json();
      if (refreshResponse.ok && refreshData.ok) {
        setInventory(Array.isArray(refreshData.inventory) ? refreshData.inventory : []);
      }
    } catch (error) {
      setMessage(error.message || 'No se pudo registrar el ingreso.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <section style={containerStyle(isMobile)}>
      <style>
        {`.ingredient-picker-option:hover { background: rgba(255, 90, 90, 0.16); }
          .ingredient-picker-option:focus-visible { outline: 1px solid rgba(255, 132, 132, 0.8); }
          .admin-dark-select option { background: #120b0b; color: #fff4f4; }
        `}
      </style>
      <div style={badgeStyle}>Ingredientes</div>
      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Ingreso administrativo de ingredientes</h2>
          <p style={subtitleStyle}>Registra entradas de inventario alimentando ingredientes, compras y movimientos para conservar la auditoría del sistema.</p>
        </div>
      </div>

      {message ? <div style={noticeStyle}>{message}</div> : null}

      <form onSubmit={handleSubmit} style={panelStyle}>
        {loading ? <div style={emptyStateStyle}>Cargando ingredientes...</div> : null}
        {!loading ? (
          <>
            <div style={formGridStyle(isMobile)}>
              <label style={fieldStyle}>
                <span style={labelStyle}>Ingrediente</span>
                <div ref={ingredientPickerRef} style={pickerWrapStyle}>
                  <input
                    value={ingredientSearch}
                    onChange={(event) => {
                      setIngredientSearch(event.target.value);
                      setShowIngredientResults(true);
                      if (form.ingrediente_id !== NEW_INGREDIENT_VALUE) {
                        setForm((current) => ({ ...current, ingrediente_id: '', nombre: event.target.value }));
                      }
                    }}
                    onFocus={() => setShowIngredientResults(true)}
                    placeholder="Escribe para buscar un ingrediente"
                    style={inputStyle}
                  />
                  {showIngredientResults ? (
                    <div style={pickerListStyle}>
                      {filteredInventory.length > 0 ? filteredInventory.map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          className="ingredient-picker-option"
                          onMouseDown={(event) => event.preventDefault()}
                          onClick={() => handleSelectIngredient(item.id)}
                          style={pickerItemStyle}
                        >
                          <span style={pickerItemTitleStyle}>{item.nombre}</span>
                          <span style={pickerItemMetaStyle}>{item.unidad_medida || 'unidad'} · stock {item.stock_actual || '0'}</span>
                        </button>
                      )) : (
                        <div style={pickerEmptyStyle}>No hay coincidencias con esa búsqueda.</div>
                      )}
                      <button
                        type="button"
                        className="ingredient-picker-option"
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => handleSelectIngredient(NEW_INGREDIENT_VALUE)}
                        style={{ ...pickerItemStyle, borderTop: '1px solid rgba(255, 255, 255, 0.08)' }}
                      >
                        <span style={pickerItemTitleStyle}>Crear ingrediente nuevo</span>
                        <span style={pickerItemMetaStyle}>Usa este nombre si el ingrediente todavía no existe.</span>
                      </button>
                    </div>
                  ) : null}
                </div>
              </label>

              <label style={fieldStyle}>
                <span style={labelStyle}>Nombre del ingrediente</span>
                <input
                  value={form.nombre}
                  onChange={(event) => handleChange('nombre', event.target.value)}
                  style={inputStyle}
                  disabled={!isCreatingNew && Boolean(form.ingrediente_id)}
                  placeholder="Ej. Tomate"
                />
              </label>

              <label style={fieldStyle}>
                <span style={labelStyle}>Unidad de medida</span>
                <select value={form.unidad} onChange={(event) => handleChange('unidad', event.target.value)} style={selectStyle} className="admin-dark-select">
                  <option value="kg">Kilogramos</option>
                  <option value="g">Gramos</option>
                  <option value="l">Litros</option>
                  <option value="ml">Mililitros</option>
                  <option value="unidad">Unidad</option>
                </select>
              </label>

              <label style={fieldStyle}>
                <span style={labelStyle}>Cantidad ingresada</span>
                <input type="number" min="0.001" step="0.001" value={form.cantidad} onChange={(event) => handleChange('cantidad', event.target.value)} style={inputStyle} />
              </label>

              <label style={fieldStyle}>
                <span style={labelStyle}>Stock mínimo</span>
                <input type="number" min="0" step="0.01" value={form.stock_minimo} onChange={(event) => handleChange('stock_minimo', event.target.value)} style={inputStyle} />
              </label>

              <label style={fieldStyle}>
                <span style={labelStyle}>Precio total pagado</span>
                <input type="number" min="0" step="0.01" value={form.precio_total} onChange={(event) => handleChange('precio_total', event.target.value)} style={inputStyle} placeholder="Lo que pagaste por toda la compra" />
                {computedUnitCost ? (
                  <span style={unitCostHintStyle}>≈ ${computedUnitCost} por {UNIDAD_LABELS[form.unidad] || form.unidad}</span>
                ) : null}
              </label>

              <label style={fieldStyle}>
                <span style={labelStyle}>Proveedor</span>
                <input value={form.proveedor} onChange={(event) => handleChange('proveedor', event.target.value)} style={inputStyle} placeholder="Nombre del proveedor" />
              </label>

              <label style={fieldStyle}>
                <span style={labelStyle}>Número de factura del proveedor</span>
                <input value={form.numero_factura_proveedor} onChange={(event) => handleChange('numero_factura_proveedor', event.target.value)} style={inputStyle} placeholder="Opcional" />
              </label>

              <label style={fieldStyle}>
                <span style={labelStyle}>Fecha de la factura</span>
                <input type="date" value={form.fecha_factura} onChange={(event) => handleChange('fecha_factura', event.target.value)} style={inputStyle} />
              </label>
            </div>

            <div style={helperCardStyle}>
              <div style={helperTitleStyle}>Auditoría automática</div>
              <div style={helperTextStyle}>Cada ingreso crea o actualiza el ingrediente y además registra una compra con su detalle y un movimiento de inventario de tipo entrada. El costo por {UNIDAD_LABELS[form.unidad] || form.unidad} se calcula solo dividiendo el precio total pagado entre la cantidad recibida — no hace falta calcularlo a mano, incluso si el paquete trae una cantidad no redonda (ej. 910 g).</div>
            </div>

            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <button type="submit" style={primaryButtonStyle} disabled={saving}>
                {saving ? 'Registrando...' : 'Registrar ingreso'}
              </button>
            </div>
          </>
        ) : null}
      </form>

      <button type="button" onClick={onBack} style={backButtonStyle}>
        Volver al panel del analista
      </button>
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

const selectStyle = {
  ...inputStyle,
  appearance: 'auto',
  colorScheme: 'dark',
  cursor: 'pointer',
};

const pickerWrapStyle = {
  position: 'relative',
};

const pickerListStyle = {
  position: 'absolute',
  top: 'calc(100% + 6px)',
  left: 0,
  right: 0,
  zIndex: 20,
  display: 'grid',
  maxHeight: 260,
  overflowY: 'auto',
  borderRadius: 16,
  border: '1px solid rgba(255, 255, 255, 0.12)',
  background: '#120b0b',
  boxShadow: '0 16px 36px rgba(0, 0, 0, 0.35)',
};

const pickerItemStyle = {
  display: 'grid',
  gap: 4,
  textAlign: 'left',
  padding: '12px 14px',
  background: 'transparent',
  border: 'none',
  color: '#fff4f4',
  cursor: 'pointer',
};

const pickerItemTitleStyle = {
  fontWeight: 700,
};

const pickerItemMetaStyle = {
  color: '#cfb8b8',
  fontSize: 12,
};

const unitCostHintStyle = {
  color: '#9fe3b0',
  fontSize: 12,
  fontWeight: 700,
};

const pickerEmptyStyle = {
  padding: '14px',
  color: '#cfb8b8',
  fontSize: 13,
};

const helperCardStyle = {
  display: 'grid',
  gap: 8,
  padding: '16px',
  borderRadius: 18,
  border: '1px solid rgba(255, 255, 255, 0.08)',
  background: 'rgba(255, 255, 255, 0.03)',
};

const helperTitleStyle = {
  color: '#fff',
  fontWeight: 700,
};

const helperTextStyle = {
  color: '#d2c4c4',
  lineHeight: 1.6,
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

export default AnalystIngredientsPage;
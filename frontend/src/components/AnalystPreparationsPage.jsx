import { useEffect, useRef, useState } from 'react';

const emptyForm = {
  nombre: '',
  rendimiento_cantidad: '1',
  rendimiento_unidad: 'unidad',
};

const emptyDraft = {
  ingredientSearch: '',
  ingredientId: '',
  ingredientName: '',
  cantidad: '',
};

function AnalystPreparationsPage({ isMobile, onBack }) {
  const ingredientPickerRef = useRef(null);
  const [inventory, setInventory] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [componentDraft, setComponentDraft] = useState(emptyDraft);
  const [components, setComponents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [showIngredientResults, setShowIngredientResults] = useState(false);

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
          throw new Error(data.message || 'No se pudieron cargar los ingredientes.');
        }
        setInventory(Array.isArray(data.inventory) ? data.inventory : []);
      } catch (error) {
        setMessage(error.message || 'No se pudieron cargar los ingredientes.');
      } finally {
        setLoading(false);
      }
    };

    loadInventory();
  }, []);

  const filteredInventory = inventory.filter((item) => {
    const query = componentDraft.ingredientSearch.trim().toLowerCase();
    if (!query) {
      return true;
    }
    return String(item.nombre || '').toLowerCase().includes(query);
  });

  const handleFormChange = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const handleSelectIngredient = (item) => {
    setComponentDraft((current) => ({
      ...current,
      ingredientId: String(item.id),
      ingredientName: item.nombre,
      ingredientSearch: item.nombre,
    }));
    setShowIngredientResults(false);
  };

  const handleAddComponent = () => {
    if (!componentDraft.ingredientName.trim() || !componentDraft.cantidad.trim()) {
      setMessage('Selecciona un ingrediente y define cuánto se descontará.');
      return;
    }

    if (components.some((item) => item.ingredientName.toLowerCase() === componentDraft.ingredientName.trim().toLowerCase())) {
      setMessage('Ese ingrediente ya está agregado en la subreceta.');
      return;
    }

    const ingredient = inventory.find((item) => String(item.id) === String(componentDraft.ingredientId));
    setComponents((current) => ([
      ...current,
      {
        ingredientId: componentDraft.ingredientId,
        ingredientName: componentDraft.ingredientName.trim(),
        cantidad: componentDraft.cantidad,
        unidad: ingredient?.unidad_medida || 'unidad',
      },
    ]));
    setComponentDraft(emptyDraft);
    setShowIngredientResults(false);
    setMessage('');
  };

  const handleRemoveComponent = (ingredientName) => {
    setComponents((current) => current.filter((item) => item.ingredientName !== ingredientName));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!form.nombre.trim()) {
      setMessage('Debes indicar el nombre de la subreceta.');
      return;
    }
    if (components.length === 0) {
      setMessage('Agrega al menos un ingrediente a la subreceta.');
      return;
    }

    setSaving(true);
    try {
      const response = await fetch('/api/admin/catalogo/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tipo: 'recetas',
          nombre: form.nombre,
          rendimiento_cantidad: form.rendimiento_cantidad,
          rendimiento_unidad: form.rendimiento_unidad,
          componentes: components.map((item) => ({
            tipo: 'ingrediente',
            nombre: item.ingredientName,
            cantidad: item.cantidad,
          })),
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo guardar la subreceta.');
      }

      setMessage(data.message || 'Subreceta guardada correctamente.');
      setForm(emptyForm);
      setComponentDraft(emptyDraft);
      setComponents([]);
      setShowIngredientResults(false);
    } catch (error) {
      setMessage(error.message || 'No se pudo guardar la subreceta.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <section style={containerStyle(isMobile)}>
      <style>
        {`.subrecipe-picker-option:hover { background: rgba(255, 90, 90, 0.16); }
          .subrecipe-picker-option:focus-visible { outline: 1px solid rgba(255, 132, 132, 0.8); }
          .subrecipe-dark-select option { background: #120b0b; color: #fff4f4; }
        `}
      </style>
      <div style={badgeStyle}>Preparaciones</div>
      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Registro de subrecetas</h2>
          <p style={subtitleStyle}>Define el nombre de la subreceta, su rendimiento y los ingredientes con la cantidad exacta que se descontará del inventario cuando esa subreceta se use.</p>
        </div>
      </div>

      {message ? <div style={noticeStyle}>{message}</div> : null}

      <form onSubmit={handleSubmit} style={panelStyle}>
        {loading ? <div style={emptyStateStyle}>Cargando ingredientes...</div> : null}
        {!loading ? (
          <>
            <div style={formGridStyle(isMobile)}>
              <label style={fieldStyle}>
                <span style={labelStyle}>Nombre de la subreceta</span>
                <input value={form.nombre} onChange={(event) => handleFormChange('nombre', event.target.value)} style={inputStyle} placeholder="Ej. Salsa de ajo" />
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Rendimiento</span>
                <input type="number" min="0.001" step="0.001" value={form.rendimiento_cantidad} onChange={(event) => handleFormChange('rendimiento_cantidad', event.target.value)} style={inputStyle} />
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Unidad del rendimiento</span>
                <select value={form.rendimiento_unidad} onChange={(event) => handleFormChange('rendimiento_unidad', event.target.value)} style={selectStyle} className="subrecipe-dark-select">
                  <option value="g">Gramos</option>
                  <option value="ml">Mililitros</option>
                  <option value="unidad">Unidad</option>
                </select>
              </label>
            </div>

            <div style={helperCardStyle}>
              <div style={helperTitleStyle}>Ingredientes que consumirá esta subreceta</div>
              <div style={helperTextStyle}>Agrega cada ingrediente con la cantidad que se descontará del inventario para producir una tanda según el rendimiento indicado.</div>

              <div style={componentComposerStyle(isMobile)}>
                <div ref={ingredientPickerRef} style={pickerWrapStyle}>
                  <input
                    value={componentDraft.ingredientSearch}
                    onChange={(event) => {
                      setComponentDraft((current) => ({
                        ...current,
                        ingredientSearch: event.target.value,
                        ingredientId: '',
                        ingredientName: event.target.value,
                      }));
                      setShowIngredientResults(true);
                    }}
                    onFocus={() => setShowIngredientResults(true)}
                    placeholder="Busca un ingrediente del inventario"
                    style={inputStyle}
                  />
                  {showIngredientResults ? (
                    <div style={pickerListStyle}>
                      {filteredInventory.length > 0 ? filteredInventory.map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          className="subrecipe-picker-option"
                          onMouseDown={(event) => event.preventDefault()}
                          onClick={() => handleSelectIngredient(item)}
                          style={pickerItemStyle}
                        >
                          <span style={pickerItemTitleStyle}>{item.nombre}</span>
                          <span style={pickerItemMetaStyle}>{item.unidad_medida || 'unidad'} · stock {item.stock_actual || '0'}</span>
                        </button>
                      )) : (
                        <div style={pickerEmptyStyle}>No hay ingredientes que coincidan con esa búsqueda.</div>
                      )}
                    </div>
                  ) : null}
                </div>

                <input
                  type="number"
                  min="0.001"
                  step="0.001"
                  value={componentDraft.cantidad}
                  onChange={(event) => setComponentDraft((current) => ({ ...current, cantidad: event.target.value }))}
                  placeholder="Cantidad a descontar"
                  style={inputStyle}
                />

                <button type="button" onClick={handleAddComponent} style={secondaryButtonStyle}>
                  Agregar ingrediente
                </button>
              </div>
            </div>

            <div style={componentsPanelStyle}>
              <div style={sectionTitleStyle}>Consumo definido para esta subreceta</div>
              {components.length === 0 ? (
                <div style={emptyStateStyle}>Todavía no has agregado ingredientes a la subreceta.</div>
              ) : (
                <div style={{ display: 'grid', gap: 10 }}>
                  {components.map((item) => (
                    <article key={item.ingredientName} style={componentCardStyle}>
                      <div>
                        <div style={componentTitleStyle}>{item.ingredientName}</div>
                        <div style={componentMetaStyle}>{item.cantidad} {item.unidad} se descontarán por tanda.</div>
                      </div>
                      <button type="button" onClick={() => handleRemoveComponent(item.ingredientName)} style={dangerButtonStyle}>
                        Quitar
                      </button>
                    </article>
                  ))}
                </div>
              )}
            </div>

            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <button type="submit" style={primaryButtonStyle} disabled={saving}>
                {saving ? 'Guardando...' : 'Guardar subreceta'}
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
  gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, minmax(0, 1fr))',
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

const helperCardStyle = {
  display: 'grid',
  gap: 10,
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

const componentComposerStyle = (isMobile) => ({
  display: 'grid',
  gridTemplateColumns: isMobile ? '1fr' : 'minmax(0, 1.5fr) minmax(180px, 0.6fr) auto',
  gap: 12,
  alignItems: 'start',
});

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

const pickerEmptyStyle = {
  padding: '14px',
  color: '#cfb8b8',
  fontSize: 13,
};

const componentsPanelStyle = {
  display: 'grid',
  gap: 12,
};

const sectionTitleStyle = {
  color: '#fff',
  fontSize: 19,
  fontWeight: 700,
};

const componentCardStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 12,
  padding: '14px 16px',
  borderRadius: 18,
  border: '1px solid rgba(255, 255, 255, 0.08)',
  background: 'rgba(255, 255, 255, 0.03)',
  flexWrap: 'wrap',
};

const componentTitleStyle = {
  color: '#fff',
  fontWeight: 700,
};

const componentMetaStyle = {
  color: '#d2c4c4',
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

const dangerButtonStyle = {
  border: '1px solid rgba(255, 125, 125, 0.28)',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'rgba(255, 82, 82, 0.18)',
  color: '#ffd5d5',
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

export default AnalystPreparationsPage;
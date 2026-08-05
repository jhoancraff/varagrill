import { useEffect, useMemo, useRef, useState } from 'react';

const emptyDraft = {
  ingredientSearch: '',
  ingredientId: '',
  preparationSearch: '',
  preparationId: '',
  cantidad: '',
};

const resolveCostoUnitario = (type, referenceId, ingredientsList, preparationsList) => {
  if (type === 'ingrediente') {
    const match = ingredientsList.find((item) => String(item.id) === String(referenceId));
    return match ? Number(match.costo_unitario || 0) : 0;
  }
  const match = preparationsList.find((item) => String(item.id) === String(referenceId));
  return match ? Number(match.costo_unitario_calculado || 0) : 0;
};

function AnalystEditRecipePage({ isMobile, isAdmin, recipeId, onBack }) {
  const ingredientPickerRef = useRef(null);
  const preparationPickerRef = useRef(null);
  const [ingredients, setIngredients] = useState([]);
  const [preparations, setPreparations] = useState([]);
  const [form, setForm] = useState({ id: null, nombre: '', descripcion: '' });
  const [draft, setDraft] = useState(emptyDraft);
  const [components, setComponents] = useState([]);
  const [showIngredientResults, setShowIngredientResults] = useState(false);
  const [showPreparationResults, setShowPreparationResults] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    const handlePointerDown = (event) => {
      if (ingredientPickerRef.current && !ingredientPickerRef.current.contains(event.target)) {
        setShowIngredientResults(false);
      }
      if (preparationPickerRef.current && !preparationPickerRef.current.contains(event.target)) {
        setShowPreparationResults(false);
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

    const loadData = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/admin/recetas/', {
          credentials: 'include',
          cache: 'no-store',
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || 'No se pudieron cargar los datos de recetas.');
        }

        const selectedRecipe = (data.recipes || []).find((entry) => String(entry.id) === String(recipeId));
        if (!selectedRecipe) {
          throw new Error('La receta seleccionada no existe.');
        }

        setIngredients(Array.isArray(data.ingredients) ? data.ingredients : []);
        setPreparations(Array.isArray(data.preparations) ? data.preparations : []);
        setForm({
          id: selectedRecipe.id,
          nombre: selectedRecipe.nombre || '',
          descripcion: selectedRecipe.descripcion || '',
        });
        setComponents(
          (selectedRecipe.componentes || []).map((item) => ({
            uid: `${item.tipo}-${item.referencia_id}`,
            tipo: item.tipo,
            referencia_id: item.referencia_id,
            nombre: item.nombre,
            unidad: item.unidad || 'unidad',
            cantidad: item.cantidad,
            costoUnitario: resolveCostoUnitario(item.tipo, item.referencia_id, data.ingredients || [], data.preparations || []),
          })),
        );
      } catch (error) {
        setMessage(error.message || 'No se pudieron cargar los datos de recetas.');
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [isAdmin, recipeId]);

  const filteredIngredients = useMemo(() => {
    const query = draft.ingredientSearch.trim().toLowerCase();
    if (!query) {
      return ingredients;
    }
    return ingredients.filter((item) => String(item.nombre || '').toLowerCase().includes(query));
  }, [ingredients, draft.ingredientSearch]);

  const filteredPreparations = useMemo(() => {
    const query = draft.preparationSearch.trim().toLowerCase();
    if (!query) {
      return preparations;
    }
    return preparations.filter((item) => String(item.nombre || '').toLowerCase().includes(query));
  }, [preparations, draft.preparationSearch]);

  const estimatedTotalCost = useMemo(
    () => components.reduce((total, item) => total + Number(item.costoUnitario || 0) * Number(item.cantidad || 0), 0),
    [components],
  );

  const handleFormChange = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const handleSelectIngredient = (item) => {
    setDraft((current) => ({
      ...current,
      ingredientId: String(item.id),
      ingredientSearch: item.nombre,
      preparationId: '',
      preparationSearch: '',
    }));
    setShowIngredientResults(false);
    setShowPreparationResults(false);
  };

  const handleSelectPreparation = (item) => {
    setDraft((current) => ({
      ...current,
      preparationId: String(item.id),
      preparationSearch: item.nombre,
      ingredientId: '',
      ingredientSearch: '',
    }));
    setShowPreparationResults(false);
    setShowIngredientResults(false);
  };

  const handleAddIngredient = () => {
    if (!draft.ingredientId || !draft.cantidad) {
      setMessage('Selecciona un ingrediente y define la cantidad a descontar.');
      return;
    }

    const ingredient = ingredients.find((item) => String(item.id) === String(draft.ingredientId));
    if (!ingredient) {
      setMessage('El ingrediente seleccionado ya no existe.');
      return;
    }

    if (components.some((item) => item.tipo === 'ingrediente' && String(item.referencia_id) === String(ingredient.id))) {
      setMessage('Ese ingrediente ya está agregado a la receta.');
      return;
    }

    setComponents((current) => ([
      ...current,
      {
        uid: `ingrediente-${ingredient.id}`,
        tipo: 'ingrediente',
        referencia_id: ingredient.id,
        nombre: ingredient.nombre,
        unidad: ingredient.unidad_medida || 'unidad',
        cantidad: draft.cantidad,
        costoUnitario: ingredient.costo_unitario || 0,
      },
    ]));
    setDraft((current) => ({ ...current, ingredientId: '', ingredientSearch: '', cantidad: '' }));
    setMessage('');
  };

  const handleAddPreparation = () => {
    if (!draft.preparationId || !draft.cantidad) {
      setMessage('Selecciona una subreceta y define la cantidad a usar.');
      return;
    }

    const preparation = preparations.find((item) => String(item.id) === String(draft.preparationId));
    if (!preparation) {
      setMessage('La subreceta seleccionada ya no existe.');
      return;
    }

    if (components.some((item) => item.tipo === 'sub_preparacion' && String(item.referencia_id) === String(preparation.id))) {
      setMessage('Esa subreceta ya está agregada a la receta.');
      return;
    }

    setComponents((current) => ([
      ...current,
      {
        uid: `sub-${preparation.id}`,
        tipo: 'sub_preparacion',
        referencia_id: preparation.id,
        nombre: preparation.nombre,
        unidad: preparation.rendimiento_unidad || 'unidad',
        cantidad: draft.cantidad,
        costoUnitario: preparation.costo_unitario_calculado || 0,
      },
    ]));
    setDraft((current) => ({ ...current, preparationId: '', preparationSearch: '', cantidad: '' }));
    setMessage('');
  };

  const handleRemoveComponent = (uid) => {
    setComponents((current) => current.filter((item) => item.uid !== uid));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (!form.nombre.trim()) {
      setMessage('Debes indicar el nombre de la receta.');
      return;
    }

    if (components.length === 0) {
      setMessage('Debes agregar ingredientes o subrecetas a la receta.');
      return;
    }

    setSaving(true);
    try {
      const response = await fetch('/api/admin/recetas/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'update',
          id: form.id,
          nombre: form.nombre,
          descripcion: form.descripcion,
          componentes: components.map((item) => ({
            tipo: item.tipo,
            referencia_id: item.referencia_id,
            cantidad: item.cantidad,
          })),
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo actualizar la receta.');
      }

      setMessage(data.message || 'Receta actualizada correctamente.');
    } catch (error) {
      setMessage(error.message || 'No se pudo actualizar la receta.');
    } finally {
      setSaving(false);
    }
  };

  if (!isAdmin) {
    return (
      <section style={containerStyle(isMobile)}>
        <div style={badgeStyle}>Editar receta</div>
        <h2 style={titleStyle(isMobile)}>Acceso restringido</h2>
        <div style={noticeStyle}>Solo el rol Administrador puede modificar recetas.</div>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          Volver al reporte
        </button>
      </section>
    );
  }

  return (
    <section style={containerStyle(isMobile)}>
      <style>
        {`.recipe-picker-option:hover { background: rgba(255, 90, 90, 0.16); }
          .recipe-picker-option:focus-visible { outline: 1px solid rgba(255, 132, 132, 0.8); }
          .recipe-dark-textarea::placeholder { color: #cfb8b8; }
        `}
      </style>

      <div style={badgeStyle}>Editar receta</div>
      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Modificar receta</h2>
          <p style={subtitleStyle}>Actualiza nombre, descripción y los componentes que se descontarán de ingredientes y subrecetas.</p>
        </div>
      </div>

      {message ? <div style={noticeStyle}>{message}</div> : null}

      <form onSubmit={handleSubmit} style={panelStyle}>
        {loading ? <div style={emptyStateStyle}>Cargando receta...</div> : null}

        {!loading ? (
          <>
            <div style={formGridStyle(isMobile)}>
              <label style={fieldStyle}>
                <span style={labelStyle}>Nombre de la receta</span>
                <input
                  value={form.nombre}
                  onChange={(event) => handleFormChange('nombre', event.target.value)}
                  style={inputStyle}
                />
              </label>

              <label style={{ ...fieldStyle, gridColumn: isMobile ? 'auto' : '1 / -1' }}>
                <span style={labelStyle}>Descripción</span>
                <textarea
                  value={form.descripcion}
                  onChange={(event) => handleFormChange('descripcion', event.target.value)}
                  style={textareaStyle}
                  className="recipe-dark-textarea"
                  rows={3}
                />
              </label>
            </div>

            <div style={helperCardStyle}>
              <div style={helperTitleStyle}>Agregar ingredientes</div>
              <div style={helperTextStyle}>Busca el ingrediente, define la cantidad y agrégalo a esta receta.</div>

              <div style={composerRowStyle(isMobile)}>
                <div ref={ingredientPickerRef} style={pickerWrapStyle}>
                  <input
                    value={draft.ingredientSearch}
                    onChange={(event) => {
                      setDraft((current) => ({
                        ...current,
                        ingredientSearch: event.target.value,
                        ingredientId: '',
                      }));
                      setShowIngredientResults(true);
                      setShowPreparationResults(false);
                    }}
                    onFocus={() => {
                      setShowIngredientResults(true);
                      setShowPreparationResults(false);
                    }}
                    placeholder="Buscar ingrediente"
                    style={inputStyle}
                  />

                  {showIngredientResults ? (
                    <div style={pickerListStyle}>
                      {filteredIngredients.length > 0 ? filteredIngredients.map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          className="recipe-picker-option"
                          onMouseDown={(event) => event.preventDefault()}
                          onClick={() => handleSelectIngredient(item)}
                          style={pickerItemStyle}
                        >
                          <span style={pickerItemTitleStyle}>{item.nombre}</span>
                          <span style={pickerItemMetaStyle}>{item.unidad_medida || 'unidad'} · stock {item.stock_actual || '0'}</span>
                        </button>
                      )) : (
                        <div style={pickerEmptyStyle}>No hay ingredientes que coincidan.</div>
                      )}
                    </div>
                  ) : null}
                </div>

                <input
                  type="number"
                  min="0.001"
                  step="0.001"
                  value={draft.cantidad}
                  onChange={(event) => setDraft((current) => ({ ...current, cantidad: event.target.value }))}
                  placeholder="Cantidad"
                  style={inputStyle}
                />

                <button type="button" onClick={handleAddIngredient} style={secondaryButtonStyle}>
                  Agregar ingrediente
                </button>
              </div>
            </div>

            <div style={helperCardStyle}>
              <div style={helperTitleStyle}>Agregar subrecetas</div>
              <div style={helperTextStyle}>Busca la subreceta y define cuánta se usa en esta receta.</div>

              <div style={composerRowStyle(isMobile)}>
                <div ref={preparationPickerRef} style={pickerWrapStyle}>
                  <input
                    value={draft.preparationSearch}
                    onChange={(event) => {
                      setDraft((current) => ({
                        ...current,
                        preparationSearch: event.target.value,
                        preparationId: '',
                      }));
                      setShowPreparationResults(true);
                      setShowIngredientResults(false);
                    }}
                    onFocus={() => {
                      setShowPreparationResults(true);
                      setShowIngredientResults(false);
                    }}
                    placeholder="Buscar subreceta"
                    style={inputStyle}
                  />

                  {showPreparationResults ? (
                    <div style={pickerListStyle}>
                      {filteredPreparations.length > 0 ? filteredPreparations.map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          className="recipe-picker-option"
                          onMouseDown={(event) => event.preventDefault()}
                          onClick={() => handleSelectPreparation(item)}
                          style={pickerItemStyle}
                        >
                          <span style={pickerItemTitleStyle}>{item.nombre}</span>
                          <span style={pickerItemMetaStyle}>Rinde {item.rendimiento_cantidad || '0'} {item.rendimiento_unidad || 'unidad'}</span>
                        </button>
                      )) : (
                        <div style={pickerEmptyStyle}>No hay subrecetas que coincidan.</div>
                      )}
                    </div>
                  ) : null}
                </div>

                <input
                  type="number"
                  min="0.001"
                  step="0.001"
                  value={draft.cantidad}
                  onChange={(event) => setDraft((current) => ({ ...current, cantidad: event.target.value }))}
                  placeholder="Cantidad"
                  style={inputStyle}
                />

                <button type="button" onClick={handleAddPreparation} style={secondaryButtonStyle}>
                  Agregar subreceta
                </button>
              </div>
            </div>

            <section style={componentsPanelStyle}>
              <div style={sectionTitleStyle}>Componentes cargados para la receta</div>
              {components.length === 0 ? (
                <div style={emptyStateStyle}>Aún no has agregado componentes.</div>
              ) : (
                <div style={{ display: 'grid', gap: 10 }}>
                  {components.map((item) => (
                    <article key={item.uid} style={componentCardStyle}>
                      <div>
                        <div style={componentTitleStyle}>{item.nombre}</div>
                        <div style={componentMetaStyle}>
                          {item.tipo === 'ingrediente' ? 'Ingrediente' : 'Subreceta'} · {item.cantidad} {item.unidad} · ${Number(item.costoUnitario || 0).toFixed(2)}/u
                        </div>
                      </div>
                      <button type="button" onClick={() => handleRemoveComponent(item.uid)} style={dangerButtonStyle}>
                        Quitar
                      </button>
                    </article>
                  ))}
                </div>
              )}
            </section>

            <div style={costSummaryStyle}>
              <div style={costLabelStyle}>Costo total estimado de la receta</div>
              <div style={costValueStyle}>${estimatedTotalCost.toFixed(2)}</div>
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

const helperCardStyle = {
  display: 'grid',
  gap: 12,
  padding: '16px',
  borderRadius: 18,
  border: '1px solid rgba(255, 255, 255, 0.08)',
  background: 'rgba(255, 255, 255, 0.02)',
};

const helperTitleStyle = {
  color: '#fff',
  fontWeight: 700,
};

const helperTextStyle = {
  color: '#d2c3c3',
  fontSize: 13,
  lineHeight: 1.5,
};

const composerRowStyle = (isMobile) => ({
  display: 'grid',
  gridTemplateColumns: isMobile ? '1fr' : 'minmax(220px, 2fr) minmax(120px, 0.8fr) auto',
  gap: 10,
  alignItems: 'center',
});

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

const componentsPanelStyle = {
  display: 'grid',
  gap: 10,
};

const sectionTitleStyle = {
  color: '#fff',
  fontSize: 17,
  fontWeight: 700,
};

const componentCardStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 12,
  padding: '12px 14px',
  borderRadius: 14,
  border: '1px solid rgba(255, 255, 255, 0.08)',
  background: 'rgba(255, 255, 255, 0.03)',
};

const componentTitleStyle = {
  color: '#fff',
  fontWeight: 700,
};

const componentMetaStyle = {
  color: '#d2c3c3',
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

const costSummaryStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 12,
  flexWrap: 'wrap',
  padding: '14px 16px',
  borderRadius: 14,
  border: '1px solid rgba(125,255,160,0.25)',
  background: 'rgba(70,200,120,0.08)',
};

const costLabelStyle = {
  color: '#c2f0d2',
  fontSize: 13,
  fontWeight: 700,
};

const costValueStyle = {
  color: '#7dffa0',
  fontSize: 22,
  fontWeight: 800,
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
  border: '1px solid rgba(255, 126, 126, 0.4)',
  borderRadius: 999,
  padding: '8px 14px',
  background: 'rgba(145, 33, 33, 0.25)',
  color: '#ffd3d3',
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

export default AnalystEditRecipePage;

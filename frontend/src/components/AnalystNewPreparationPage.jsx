import { useEffect, useMemo, useRef, useState } from 'react';

const emptyForm = { nombre: '', rendimiento_cantidad: '1', rendimiento_unidad: 'unidad' };
const emptyDraft = { ingredientSearch: '', ingredientId: '', preparationSearch: '', preparationId: '', cantidad: '' };

const unidadOptions = [
  { value: 'kg', label: 'Kilogramos (kg)' },
  { value: 'g', label: 'Gramos (g)' },
  { value: 'l', label: 'Litros (l)' },
  { value: 'ml', label: 'Mililitros (ml)' },
  { value: 'unidad', label: 'Unidad' },
];

function AnalystNewPreparationPage({ isMobile, onBack }) {
  const ingredientPickerRef = useRef(null);
  const preparationPickerRef = useRef(null);
  const [inventory, setInventory] = useState([]);
  const [preparations, setPreparations] = useState([]);
  const [form, setForm] = useState(emptyForm);
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
    const loadData = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/admin/catalogo/', { credentials: 'include', cache: 'no-store' });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || 'No se pudo cargar la data.');
        }
        setInventory(Array.isArray(data.inventory) ? data.inventory : []);
        setPreparations(Array.isArray(data.recipes) ? data.recipes : []);
      } catch (error) {
        setMessage(error.message || 'No se pudo cargar la data.');
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, []);

  const filteredIngredients = useMemo(() => {
    const query = draft.ingredientSearch.trim().toLowerCase();
    if (!query) {
      return inventory;
    }
    return inventory.filter((item) => String(item.nombre || '').toLowerCase().includes(query));
  }, [inventory, draft.ingredientSearch]);

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

  const rendimientoCantidad = Number(form.rendimiento_cantidad || 0);
  const estimatedUnitCost = rendimientoCantidad > 0 ? estimatedTotalCost / rendimientoCantidad : 0;

  const handleAdd = (type) => {
    const isIngredient = type === 'ingrediente';
    const referenceId = isIngredient ? draft.ingredientId : draft.preparationId;
    if (!referenceId || !draft.cantidad) {
      setMessage('Debes seleccionar un componente y su cantidad.');
      return;
    }

    const sourceList = isIngredient ? inventory : preparations;
    const selected = sourceList.find((item) => String(item.id) === String(referenceId));
    if (!selected) {
      setMessage('El componente seleccionado no existe.');
      return;
    }

    if (components.some((item) => item.tipo === type && String(item.referencia_id) === String(referenceId))) {
      setMessage('Ese componente ya fue agregado.');
      return;
    }

    const costoUnitario = isIngredient ? (selected.costo_unitario || 0) : (selected.costo_unitario_calculado || 0);

    setComponents((current) => ([
      ...current,
      {
        uid: `${type}-${referenceId}`,
        tipo: type,
        referencia_id: referenceId,
        nombre: selected.nombre,
        cantidad: draft.cantidad,
        costoUnitario,
      },
    ]));
    setDraft((current) => ({ ...current, ingredientSearch: '', ingredientId: '', preparationSearch: '', preparationId: '', cantidad: '' }));
    setMessage('');
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!form.nombre.trim()) {
      setMessage('Debes indicar el nombre de la subreceta.');
      return;
    }
    if (components.length === 0) {
      setMessage('Debes agregar al menos un componente.');
      return;
    }

    setSaving(true);
    try {
      const response = await fetch('/api/admin/catalogo/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tipo: 'crear_preparacion',
          nombre: form.nombre,
          rendimiento_cantidad: form.rendimiento_cantidad,
          rendimiento_unidad: form.rendimiento_unidad,
          componentes: components.map((item) => ({ tipo: item.tipo, referencia_id: item.referencia_id, cantidad: item.cantidad })),
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo crear la subreceta.');
      }

      setMessage(data.message || 'Subreceta creada correctamente.');
      setForm(emptyForm);
      setDraft(emptyDraft);
      setComponents([]);
    } catch (error) {
      setMessage(error.message || 'No se pudo crear la subreceta.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <section style={containerStyle(isMobile)}>
      <h2 style={titleStyle(isMobile)}>Nueva subreceta</h2>
      {message ? <div style={noticeStyle}>{message}</div> : null}

      <form onSubmit={handleSubmit} style={panelStyle}>
        {loading ? <div style={emptyStyle}>Cargando datos...</div> : null}
        {!loading ? (
          <>
            <div style={gridStyle(isMobile)}>
              <label style={fieldStyle}><span style={labelStyle}>Nombre</span><input value={form.nombre} onChange={(e) => setForm((c) => ({ ...c, nombre: e.target.value }))} style={inputStyle} /></label>
              <label style={fieldStyle}><span style={labelStyle}>Rendimiento</span><input type="number" min="0.001" step="0.001" value={form.rendimiento_cantidad} onChange={(e) => setForm((c) => ({ ...c, rendimiento_cantidad: e.target.value }))} style={inputStyle} /></label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Unidad</span>
                <select value={form.rendimiento_unidad} onChange={(e) => setForm((c) => ({ ...c, rendimiento_unidad: e.target.value }))} style={inputStyle}>
                  {unidadOptions.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>
            </div>

            <div style={helperCardStyle}>
              <div style={helperTitleStyle}>Agregar ingrediente</div>
              <div style={composerStyle(isMobile)}>
                <div ref={ingredientPickerRef} style={pickerWrapStyle}>
                  <input
                    value={draft.ingredientSearch}
                    onChange={(e) => {
                      setDraft((c) => ({ ...c, ingredientSearch: e.target.value, ingredientId: '' }));
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
                      {filteredIngredients.map((item) => (
                        <button key={item.id} type="button" style={pickerItemStyle} onMouseDown={(e) => e.preventDefault()} onClick={() => {
                          setDraft((c) => ({ ...c, ingredientId: String(item.id), ingredientSearch: item.nombre, preparationId: '', preparationSearch: '' }));
                          setShowIngredientResults(false);
                        }}>
                          {item.nombre}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
                <input type="number" min="0.001" step="0.001" value={draft.cantidad} onChange={(e) => setDraft((c) => ({ ...c, cantidad: e.target.value }))} placeholder="Cantidad" style={inputStyle} />
                <button type="button" onClick={() => handleAdd('ingrediente')} style={secondaryButtonStyle}>Agregar ingrediente</button>
              </div>
            </div>

            <div style={helperCardStyle}>
              <div style={helperTitleStyle}>Agregar subreceta</div>
              <div style={composerStyle(isMobile)}>
                <div ref={preparationPickerRef} style={pickerWrapStyle}>
                  <input
                    value={draft.preparationSearch}
                    onChange={(e) => {
                      setDraft((c) => ({ ...c, preparationSearch: e.target.value, preparationId: '' }));
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
                      {filteredPreparations.map((item) => (
                        <button key={item.id} type="button" style={pickerItemStyle} onMouseDown={(e) => e.preventDefault()} onClick={() => {
                          setDraft((c) => ({ ...c, preparationId: String(item.id), preparationSearch: item.nombre, ingredientId: '', ingredientSearch: '' }));
                          setShowPreparationResults(false);
                        }}>
                          {item.nombre}
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>
                <input type="number" min="0.001" step="0.001" value={draft.cantidad} onChange={(e) => setDraft((c) => ({ ...c, cantidad: e.target.value }))} placeholder="Cantidad" style={inputStyle} />
                <button type="button" onClick={() => handleAdd('sub_preparacion')} style={secondaryButtonStyle}>Agregar subreceta</button>
              </div>
            </div>

            <div style={{ display: 'grid', gap: 8 }}>
              {components.length === 0 ? <div style={emptyStyle}>Sin componentes</div> : components.map((item) => (
                <div key={item.uid} style={componentRowStyle}>
                  <div>{item.nombre} ({item.tipo}) - {item.cantidad} · ${Number(item.costoUnitario || 0).toFixed(2)}/u</div>
                  <button type="button" onClick={() => setComponents((current) => current.filter((entry) => entry.uid !== item.uid))} style={dangerButtonStyle}>Quitar</button>
                </div>
              ))}
            </div>

            <div style={costSummaryStyle}>
              <div>
                <div style={costLabelStyle}>Costo total estimado</div>
                <div style={costValueStyle}>${estimatedTotalCost.toFixed(2)}</div>
              </div>
              <div>
                <div style={costLabelStyle}>Costo por {form.rendimiento_unidad || 'unidad'}</div>
                <div style={costValueStyle}>${estimatedUnitCost.toFixed(2)}</div>
              </div>
            </div>

            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <button type="submit" style={primaryButtonStyle} disabled={saving}>{saving ? 'Guardando...' : 'Crear subreceta'}</button>
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
const emptyStyle = { minHeight: 70, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const gridStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, minmax(0, 1fr))', gap: 12 });
const fieldStyle = { display: 'grid', gap: 6 };
const labelStyle = { color: '#f0b4b4', fontSize: 13, fontWeight: 700 };
const inputStyle = { borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff' };
const helperCardStyle = { display: 'grid', gap: 10, padding: 14, borderRadius: 14, border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(255,255,255,0.02)' };
const helperTitleStyle = { color: '#fff', fontWeight: 700 };
const composerStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'minmax(220px,2fr) minmax(120px,1fr) auto', gap: 10 });
const pickerWrapStyle = { position: 'relative' };
const pickerListStyle = { position: 'absolute', zIndex: 10, top: 'calc(100% + 6px)', left: 0, right: 0, maxHeight: 220, overflowY: 'auto', borderRadius: 12, border: '1px solid rgba(255,132,132,0.4)', background: '#140d0d' };
const pickerItemStyle = { width: '100%', textAlign: 'left', border: 'none', background: 'transparent', color: '#ffeaea', padding: '10px 12px', cursor: 'pointer' };
const componentRowStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, padding: '10px 12px', borderRadius: 12, border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(255,255,255,0.03)', color: '#fff' };
const costSummaryStyle = { display: 'flex', gap: 20, flexWrap: 'wrap', padding: '14px 16px', borderRadius: 14, border: '1px solid rgba(125,255,160,0.25)', background: 'rgba(70,200,120,0.08)' };
const costLabelStyle = { color: '#c2f0d2', fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em' };
const costValueStyle = { color: '#7dffa0', fontSize: 20, fontWeight: 800 };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const secondaryButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const dangerButtonStyle = { border: '1px solid rgba(255,126,126,0.4)', borderRadius: 999, padding: '8px 12px', background: 'rgba(145,33,33,0.25)', color: '#ffd3d3', fontWeight: 700, cursor: 'pointer' };

export default AnalystNewPreparationPage;

import { Fragment, useEffect, useMemo, useState } from 'react';
import Toast from './Toast';
import UnsavedChangesModal from './UnsavedChangesModal';
import useToast from '../hooks/useToast';
import useUnsavedChangesGuard from '../hooks/useUnsavedChangesGuard';
import { badgeEstadoStyle, estadoHoja, formatFechaHora, nombreMes } from '../utils/ajusteInventario';

const emptyItemForm = { nombre: '', ingrediente_id: '', tipo: 'suma', cantidad: '', motivo: '' };

async function postJson(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    throw new Error(data.message || 'No se pudo completar la operación.');
  }
  return data;
}

// Una hoja de ajuste de inventario: el borrador al que se le agregan lineas (ingrediente, suma/resta,
// cantidad) y que recien afecta el stock al confirmarla. Se abre desde la lista
// (AnalystAjusteInventarioPage, ruta 'admin-ingredients-ajuste:<id>' en WelcomeScreen).
function AnalystAjusteInventarioHojaPage({ isMobile, ajusteId, onBack }) {
  const [inventory, setInventory] = useState([]);
  const [ajuste, setAjuste] = useState(null);
  const [loading, setLoading] = useState(true);
  const [itemForm, setItemForm] = useState(emptyItemForm);
  const [isNameFocused, setIsNameFocused] = useState(false);
  const [addingItem, setAddingItem] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editValue, setEditValue] = useState('');
  const [savingEdit, setSavingEdit] = useState(false);
  const [saving, setSaving] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [editingTitulo, setEditingTitulo] = useState(false);
  const [tituloValue, setTituloValue] = useState('');
  const [savingTitulo, setSavingTitulo] = useState(false);
  const { toast, showSuccess, showError, hideToast } = useToast();
  // Lo unico que se perderia al salir sin guardar es la fila a medio llenar
  // (itemForm) — cada linea ya agregada a la hoja queda persistida en el
  // servidor de inmediato, igual que en el borrador de compras.
  const { guard, isConfirmOpen, confirmLeave, cancelLeave, markClean } = useUnsavedChangesGuard({ itemForm });

  useEffect(() => {
    const loadAll = async () => {
      setLoading(true);
      try {
        const [catalogoRes, ajusteRes] = await Promise.all([
          fetch('/api/admin/catalogo/', { credentials: 'include', cache: 'no-store' }),
          fetch(`/api/admin/inventario/ajuste/${ajusteId}/`, { credentials: 'include', cache: 'no-store' }),
        ]);
        const catalogoData = await catalogoRes.json();
        const ajusteData = await ajusteRes.json();
        if (catalogoRes.ok && catalogoData.ok) {
          setInventory(Array.isArray(catalogoData.inventory) ? catalogoData.inventory : []);
        }
        if (ajusteRes.ok && ajusteData.ok) {
          setAjuste(ajusteData.ajuste);
        } else {
          showError(ajusteData.message || 'No se pudo cargar la hoja de ajuste.');
        }
      } catch (error) {
        showError('No se pudo cargar la información inicial.');
      } finally {
        setLoading(false);
      }
    };
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ajusteId]);

  const nameQuery = itemForm.nombre.trim().toLowerCase();

  const nameMatches = useMemo(() => {
    if (!nameQuery) return [];
    return inventory.filter((item) => (item.nombre || '').toLowerCase().includes(nameQuery)).slice(0, 6);
  }, [inventory, nameQuery]);

  const handleNombreChange = (value) => {
    // Cambiar el texto invalida la seleccion anterior — este modulo solo
    // trabaja con ingredientes que ya existen en el catalogo, no crea nuevos.
    setItemForm((current) => ({ ...current, nombre: value, ingrediente_id: '' }));
  };

  const handleSelectExisting = (item) => {
    setItemForm((current) => ({ ...current, nombre: item.nombre, ingrediente_id: item.id }));
    setIsNameFocused(false);
  };

  const detalles = useMemo(() => (ajuste && Array.isArray(ajuste.detalles) ? ajuste.detalles : []), [ajuste]);
  const hasItems = detalles.length > 0;
  const tieneAplicadas = detalles.some((detalle) => detalle.aplicado);
  const readOnly = !!ajuste?.mes_cerrado;
  const estado = ajuste ? estadoHoja(ajuste) : null;
  const hayPendientes = !!ajuste && ajuste.lineas_pendientes > 0;

  const handleAddItem = async (event) => {
    event.preventDefault();
    if (!itemForm.ingrediente_id) {
      showError('Selecciona un ingrediente existente del catálogo.');
      return;
    }

    setAddingItem(true);
    try {
      const data = await postJson('/api/admin/inventario/ajuste/agregar/', {
        ajuste_id: ajusteId,
        ingrediente_id: itemForm.ingrediente_id,
        tipo: itemForm.tipo,
        cantidad: itemForm.cantidad,
        motivo: itemForm.motivo,
      });
      setAjuste(data.ajuste);
      setItemForm(emptyItemForm);
      markClean({ itemForm: emptyItemForm });
    } catch (error) {
      showError(error.message || 'No se pudo agregar la línea a la hoja.');
    } finally {
      setAddingItem(false);
    }
  };

  const handleRemoveItem = async (detalleId) => {
    if (!window.confirm('¿Deseas quitar esta línea de la hoja?')) {
      return;
    }
    try {
      const data = await postJson('/api/admin/inventario/ajuste/quitar/', { detalle_id: detalleId });
      setAjuste(data.ajuste);
    } catch (error) {
      showError(error.message || 'No se pudo quitar esa línea.');
    }
  };

  const handleStartEdit = (detalle) => {
    setEditingId(detalle.id);
    setEditValue(detalle.cantidad);
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setEditValue('');
  };

  const handleSaveEdit = async (detalleId) => {
    setSavingEdit(true);
    try {
      const data = await postJson('/api/admin/inventario/ajuste/editar/', { detalle_id: detalleId, cantidad: editValue });
      setAjuste(data.ajuste);
      setEditingId(null);
      setEditValue('');
    } catch (error) {
      showError(error.message || 'No se pudo actualizar esa línea.');
    } finally {
      setSavingEdit(false);
    }
  };

  const handleGuardar = async () => {
    setSaving(true);
    try {
      const data = await postJson('/api/admin/inventario/ajuste/guardar/', { ajuste_id: ajusteId });
      setAjuste(data.ajuste);
      showSuccess(data.message || 'Ajuste guardado.');
    } catch (error) {
      showError(error.message || 'No se pudo guardar el ajuste.');
    } finally {
      setSaving(false);
    }
  };

  const handleDiscard = async () => {
    if (!window.confirm('¿Deseas descartar esta hoja? Se perderán las líneas agregadas.')) {
      return;
    }
    setDiscarding(true);
    try {
      await postJson('/api/admin/inventario/ajuste/descartar/', { ajuste_id: ajusteId });
      onBack();
    } catch (error) {
      showError(error.message || 'No se pudo descartar la hoja.');
      setDiscarding(false);
    }
  };

  const handleStartTitulo = () => {
    setTituloValue(ajuste?.titulo || '');
    setEditingTitulo(true);
  };

  const handleSaveTitulo = async () => {
    setSavingTitulo(true);
    try {
      const data = await postJson('/api/admin/inventario/ajuste/actualizar/', { ajuste_id: ajusteId, titulo: tituloValue });
      setAjuste((current) => ({ ...current, titulo: data.ajuste.titulo, notas: data.ajuste.notas }));
      setEditingTitulo(false);
    } catch (error) {
      showError(error.message || 'No se pudo cambiar el título.');
    } finally {
      setSavingTitulo(false);
    }
  };

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={() => guard(onBack)} style={backButtonStyle}>
        ← Volver a las hojas
      </button>

      <div>
        <h2 style={titleStyle(isMobile)}>
          {ajuste ? `Ajuste #${ajuste.id}${ajuste.titulo ? ` — ${ajuste.titulo}` : ''}` : 'Hoja de ajuste'}
        </h2>
        {ajuste ? (
          <div style={metaRowStyle}>
            <span style={badgeEstadoStyle(estado.clave)}>{estado.label}</span>
            <span style={subtitleStyle}>Creada el {formatFechaHora(ajuste.fecha_creacion)}</span>
            {!readOnly && !editingTitulo ? (
              <button type="button" onClick={handleStartTitulo} style={smallSecondaryButtonStyle}>
                {ajuste.titulo ? 'Cambiar título' : 'Ponerle título'}
              </button>
            ) : null}
          </div>
        ) : null}
        {editingTitulo ? (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
            <input
              value={tituloValue}
              onChange={(e) => setTituloValue(e.target.value)}
              maxLength={120}
              placeholder="Ejemplo: Conteo cocina"
              style={{ ...inputStyle, maxWidth: 360 }}
              autoFocus
            />
            <button type="button" onClick={handleSaveTitulo} style={smallActionButtonStyle} disabled={savingTitulo}>
              {savingTitulo ? '...' : 'Guardar'}
            </button>
            <button type="button" onClick={() => setEditingTitulo(false)} style={smallSecondaryButtonStyle} disabled={savingTitulo}>
              Cancelar
            </button>
          </div>
        ) : null}
      </div>

      <Toast toast={toast} onClose={hideToast} />
      <UnsavedChangesModal open={isConfirmOpen} onConfirm={confirmLeave} onCancel={cancelLeave} />

      {loading ? (
        <div style={emptyStyle}>Cargando...</div>
      ) : !ajuste ? (
        <div style={emptyStyle}>No se encontró esta hoja de ajuste.</div>
      ) : (
        <>
          {readOnly ? (
            <section style={panelStyle}>
              <div style={sectionTitleStyle}>Mes cerrado</div>
              <p style={{ color: 'var(--vg-f-d2c3c3)', margin: 0 }}>
                El mes de {nombreMes(ajuste.mes)} ya fue cerrado: esta hoja queda de solo lectura.
              </p>
            </section>
          ) : (
            <section style={panelStyle}>
              <div style={sectionTitleStyle}>Agregar línea</div>
              <form onSubmit={handleAddItem} style={itemFormStyle(isMobile)}>
                <div style={{ ...fieldStyle, position: 'relative' }}>
                  <span style={labelStyle}>Ingrediente</span>
                  <input
                    value={itemForm.nombre}
                    onChange={(e) => handleNombreChange(e.target.value)}
                    onFocus={() => setIsNameFocused(true)}
                    onBlur={() => setTimeout(() => setIsNameFocused(false), 150)}
                    placeholder="Busca un ingrediente..."
                    style={inputStyle}
                    autoComplete="off"
                  />
                  {isNameFocused && nameQuery && nameMatches.length > 0 ? (
                    <div style={suggestionsPanelStyle}>
                      {nameMatches.map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          onMouseDown={(event) => event.preventDefault()}
                          onClick={() => handleSelectExisting(item)}
                          style={suggestionRowStyle}
                        >
                          <span style={{ color: 'var(--vg-text-strong)', fontWeight: 600 }}>{item.nombre}</span>
                          <span style={{ color: 'var(--vg-f-e8bcbc)', fontSize: 12 }}>{item.unidad_medida || ''}</span>
                        </button>
                      ))}
                    </div>
                  ) : null}
                  {nameQuery && !itemForm.ingrediente_id ? (
                    <div style={hintStyle}>Selecciona un ingrediente de la lista.</div>
                  ) : null}
                </div>

                <label style={fieldStyle}>
                  <span style={labelStyle}>Tipo</span>
                  <select
                    value={itemForm.tipo}
                    onChange={(e) => setItemForm((c) => ({ ...c, tipo: e.target.value }))}
                    style={inputStyle}
                  >
                    <option value="suma">Suma al stock</option>
                    <option value="resta">Resta al stock</option>
                  </select>
                </label>

                <label style={fieldStyle}>
                  <span style={labelStyle}>Cantidad</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0.01"
                    value={itemForm.cantidad}
                    onChange={(e) => setItemForm((c) => ({ ...c, cantidad: e.target.value }))}
                    style={inputStyle}
                    required
                  />
                </label>

                <label style={fieldStyle}>
                  <span style={labelStyle}>Motivo (opcional)</span>
                  <input
                    value={itemForm.motivo}
                    onChange={(e) => setItemForm((c) => ({ ...c, motivo: e.target.value }))}
                    style={inputStyle}
                    placeholder="Ejemplo: conteo físico, merma..."
                  />
                </label>

                <button type="submit" style={primaryButtonStyle} disabled={addingItem}>
                  {addingItem ? 'Agregando...' : 'Agregar línea'}
                </button>
              </form>
            </section>
          )}

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Líneas de la hoja {hasItems ? `(${detalles.length})` : ''}</div>
            {!hasItems ? (
              <div style={emptyStyle}>Todavía no has agregado ninguna línea.</div>
            ) : (
              <div style={tableWrapStyle}>
                <div style={tableStyle}>
                  <div style={headStyle}>Ingrediente</div>
                  <div style={headStyle}>Tipo</div>
                  <div style={headStyle}>Cantidad</div>
                  <div style={headStyle}>Motivo</div>
                  <div style={headStyle}>Estado</div>
                  <div style={headStyle}></div>
                  {detalles.map((detalle) => (
                    <Fragment key={detalle.id}>
                      <div style={cellPrimaryStyle}>{detalle.ingrediente_nombre}</div>
                      <div style={cellStyle}>{detalle.tipo === 'suma' ? 'Suma' : 'Resta'}</div>
                      <div style={cellStyle}>
                        {editingId === detalle.id ? (
                          <input
                            type="number"
                            step="0.01"
                            min="0.01"
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            style={{ ...inputStyle, padding: '4px 6px', fontSize: 12, width: 90 }}
                            autoFocus
                          />
                        ) : (
                          `${detalle.cantidad} ${detalle.unidad_medida}`
                        )}
                      </div>
                      <div style={cellStyle}>{detalle.motivo || '—'}</div>
                      <div style={cellStyle}>
                        <span style={lineBadgeStyle(detalle.aplicado)}>{detalle.aplicado ? 'Aplicada' : 'Pendiente'}</span>
                      </div>
                      <div style={{ ...cellStyle, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        {readOnly ? null : editingId === detalle.id ? (
                          <>
                            <button type="button" onClick={() => handleSaveEdit(detalle.id)} style={smallActionButtonStyle} disabled={savingEdit}>
                              {savingEdit ? '...' : 'Guardar'}
                            </button>
                            <button type="button" onClick={handleCancelEdit} style={smallSecondaryButtonStyle} disabled={savingEdit}>Cancelar</button>
                          </>
                        ) : (
                          <>
                            <button type="button" onClick={() => handleStartEdit(detalle)} style={smallSecondaryButtonStyle}>Editar</button>
                            <button type="button" onClick={() => handleRemoveItem(detalle.id)} style={dangerButtonStyle}>Quitar</button>
                          </>
                        )}
                      </div>
                    </Fragment>
                  ))}
                </div>
              </div>
            )}

            {!readOnly && (hayPendientes || !tieneAplicadas) ? (
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                {hayPendientes ? (
                  <button type="button" onClick={handleGuardar} style={primaryButtonStyle} disabled={saving}>
                    {saving ? 'Guardando...' : ajuste.estado === 'confirmado' ? 'Guardar cambios' : 'Confirmar hoja'}
                  </button>
                ) : null}
                {!tieneAplicadas ? (
                  <button type="button" onClick={handleDiscard} style={secondaryButtonStyle} disabled={discarding}>
                    {discarding ? 'Descartando...' : 'Descartar hoja'}
                  </button>
                ) : null}
              </div>
            ) : null}
          </section>
        </>
      )}
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const titleStyle = (isMobile) => ({ margin: 0, color: 'var(--vg-text-strong)', fontSize: isMobile ? 26 : 32 });
const subtitleStyle = { color: 'var(--vg-f-d2c3c3)', lineHeight: 1.6, fontSize: 14 };
const metaRowStyle = { display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginTop: 8 };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)' };
const sectionTitleStyle = { color: 'var(--vg-text-strong)', fontSize: 17, fontWeight: 700 };
const emptyStyle = { minHeight: 60, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(var(--vg-ink), 0.12)', color: 'var(--vg-f-c8bbbb)' };

const itemFormStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1.6fr 1fr 1fr 1.4fr auto', gap: 10, alignItems: 'end' });
const fieldStyle = { display: 'grid', gap: 6 };
const labelStyle = { color: 'var(--vg-f-f0b4b4)', fontSize: 12.5, fontWeight: 700 };
const inputStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 10, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-161010)', padding: '9px 10px', color: 'var(--vg-text-strong)', fontSize: 13 };
const hintStyle = { margin: 0, color: 'var(--vg-f-a89999)', fontSize: 12 };

const suggestionsPanelStyle = { position: 'absolute', top: '100%', left: 0, right: 0, marginTop: 6, zIndex: 5, borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-0a0808-a980)', boxShadow: '0 12px 30px rgba(0, 0, 0, calc(0.4 * var(--vg-shadow-k)))', padding: 8, display: 'grid', gap: 4, maxHeight: 220, overflowY: 'auto' };
const suggestionRowStyle = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, border: '1px solid rgba(var(--vg-ink), 0.08)', borderRadius: 10, padding: '8px 10px', background: 'rgba(var(--vg-ink), 0.04)', cursor: 'pointer', textAlign: 'left' };

const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(160px,1.2fr) 90px 130px minmax(140px,1.4fr) 100px minmax(160px,auto)', gap: '10px 12px', alignItems: 'center', minWidth: 860 };
const headStyle = { color: 'var(--vg-f-f0b4b4)', fontSize: 11.5, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em', padding: '4px 2px', borderBottom: '1px solid rgba(var(--vg-ink), 0.1)' };
const cellStyle = { color: 'var(--vg-text-strong)', fontSize: 13, padding: '6px 2px', borderBottom: '1px solid rgba(var(--vg-ink), 0.06)' };
const cellPrimaryStyle = { ...cellStyle, fontWeight: 700 };

const lineBadgeStyle = (aplicado) => ({
  display: 'inline-block',
  padding: '3px 10px',
  borderRadius: 999,
  fontSize: 11.5,
  fontWeight: 800,
  background: aplicado ? 'rgba(52, 211, 153, 0.18)' : 'rgba(255, 205, 86, 0.18)',
  color: aplicado ? 'var(--vg-f-34d399)' : 'var(--vg-f-ffcd56)',
  border: `1px solid ${aplicado ? 'var(--vg-f-34d399-a400)' : 'var(--vg-f-ffcd56-a400)'}`,
});

const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, var(--vg-accent-primary) 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const secondaryButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(var(--vg-ink), 0.04)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer', width: 'fit-content' };
const dangerButtonStyle = { border: '1px solid var(--vg-f-ff7e7e-a400)', borderRadius: 999, padding: '6px 12px', background: 'rgba(145,33,33,0.25)', color: 'var(--vg-f-ffd3d3)', fontWeight: 700, cursor: 'pointer', fontSize: 12, width: 'fit-content' };
const smallActionButtonStyle = { border: 'none', borderRadius: 999, padding: '6px 12px', background: 'linear-gradient(90deg, #1f7a3f 0%, #34d399 100%)', color: '#04140a', fontWeight: 700, cursor: 'pointer', fontSize: 12 };
const smallSecondaryButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.14)', borderRadius: 999, padding: '6px 12px', background: 'rgba(var(--vg-ink), 0.04)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer', fontSize: 12 };

export default AnalystAjusteInventarioHojaPage;

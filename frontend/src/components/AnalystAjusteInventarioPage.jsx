import { useEffect, useMemo, useState } from 'react';
import ConfirmModal from './ConfirmModal';
import Toast from './Toast';
import UnsavedChangesModal from './UnsavedChangesModal';
import useToast from '../hooks/useToast';
import useUnsavedChangesGuard from '../hooks/useUnsavedChangesGuard';

const emptyItemForm = { nombre: '', ingrediente_id: '', tipo: 'suma', cantidad: '', motivo: '' };

const MESES = [
  'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
];

function nombreMes(mes) {
  return MESES[(mes || 1) - 1] || '';
}

function AnalystAjusteInventarioPage({ isMobile, onBack }) {
  const [inventory, setInventory] = useState([]);
  const [estado, setEstado] = useState({ anio: null, mes: null, mes_cerrado: false, ajuste: null, historico: [] });
  const [loading, setLoading] = useState(true);
  const [itemForm, setItemForm] = useState(emptyItemForm);
  const [isNameFocused, setIsNameFocused] = useState(false);
  const [addingItem, setAddingItem] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editValue, setEditValue] = useState('');
  const [savingEdit, setSavingEdit] = useState(false);
  const [saving, setSaving] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [cierreModalOpen, setCierreModalOpen] = useState(false);
  const [cerrandoMes, setCerrandoMes] = useState(false);
  const { toast, showSuccess, showError, hideToast } = useToast();
  // Lo unico que se perderia al salir sin guardar es la fila a medio llenar
  // (itemForm) — cada linea ya agregada al ajuste queda persistida en el
  // servidor de inmediato, igual que en el borrador de compras.
  const { guard, isConfirmOpen, confirmLeave, cancelLeave, markClean } = useUnsavedChangesGuard({ itemForm });

  useEffect(() => {
    const loadAll = async () => {
      setLoading(true);
      try {
        const [catalogoRes, ajusteRes] = await Promise.all([
          fetch('/api/admin/catalogo/', { credentials: 'include', cache: 'no-store' }),
          fetch('/api/admin/inventario/ajuste/', { credentials: 'include', cache: 'no-store' }),
        ]);
        const catalogoData = await catalogoRes.json();
        const ajusteData = await ajusteRes.json();
        if (catalogoRes.ok && catalogoData.ok) {
          setInventory(Array.isArray(catalogoData.inventory) ? catalogoData.inventory : []);
        }
        if (ajusteRes.ok && ajusteData.ok) {
          setEstado(ajusteData);
        } else {
          showError(ajusteData.message || 'No se pudo cargar el ajuste de inventario.');
        }
      } catch (error) {
        showError('No se pudo cargar la informacion inicial.');
      } finally {
        setLoading(false);
      }
    };
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  const mesCerrado = !!estado.mes_cerrado;
  const ajuste = estado.ajuste;
  const detalles = useMemo(() => (ajuste && Array.isArray(ajuste.detalles) ? ajuste.detalles : []), [ajuste]);
  const hasItems = detalles.length > 0;
  const tieneAplicadas = detalles.some((detalle) => detalle.aplicado);

  const handleAddItem = async (event) => {
    event.preventDefault();
    if (!itemForm.ingrediente_id) {
      showError('Selecciona un ingrediente existente del catálogo.');
      return;
    }

    setAddingItem(true);
    try {
      const response = await fetch('/api/admin/inventario/ajuste/agregar/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ingrediente_id: itemForm.ingrediente_id,
          tipo: itemForm.tipo,
          cantidad: itemForm.cantidad,
          motivo: itemForm.motivo,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo agregar la línea al ajuste.');
      }
      setEstado((current) => ({ ...current, ajuste: data.ajuste }));
      setItemForm(emptyItemForm);
      markClean({ itemForm: emptyItemForm });
    } catch (error) {
      showError(error.message || 'No se pudo agregar la línea al ajuste.');
    } finally {
      setAddingItem(false);
    }
  };

  const handleRemoveItem = async (detalleId) => {
    if (!window.confirm('¿Deseas quitar esta línea del ajuste?')) {
      return;
    }
    try {
      const response = await fetch('/api/admin/inventario/ajuste/quitar/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ detalle_id: detalleId }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo quitar esa línea.');
      }
      setEstado((current) => ({ ...current, ajuste: data.ajuste }));
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
      const response = await fetch('/api/admin/inventario/ajuste/editar/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ detalle_id: detalleId, cantidad: editValue }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo actualizar esa línea.');
      }
      setEstado((current) => ({ ...current, ajuste: data.ajuste }));
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
      const response = await fetch('/api/admin/inventario/ajuste/guardar/', {
        method: 'POST',
        credentials: 'include',
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo guardar el ajuste.');
      }
      setEstado((current) => ({ ...current, ajuste: data.ajuste }));
      showSuccess(data.message || 'Ajuste guardado.');
    } catch (error) {
      showError(error.message || 'No se pudo guardar el ajuste.');
    } finally {
      setSaving(false);
    }
  };

  const handleDiscard = async () => {
    if (!window.confirm('¿Deseas descartar todo el ajuste? Se perderán las líneas agregadas.')) {
      return;
    }
    setDiscarding(true);
    try {
      const response = await fetch('/api/admin/inventario/ajuste/descartar/', {
        method: 'POST',
        credentials: 'include',
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo descartar el ajuste.');
      }
      setEstado((current) => ({ ...current, ajuste: data.ajuste }));
    } catch (error) {
      showError(error.message || 'No se pudo descartar el ajuste.');
    } finally {
      setDiscarding(false);
    }
  };

  const handleCerrarMes = async () => {
    setCerrandoMes(true);
    try {
      const response = await fetch('/api/admin/inventario/cierre/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo cerrar el mes.');
      }
      setCierreModalOpen(false);
      setEstado((current) => ({ ...current, mes_cerrado: true }));
      showSuccess(data.message || 'Mes cerrado.');
    } catch (error) {
      showError(error.message || 'No se pudo cerrar el mes.');
    } finally {
      setCerrandoMes(false);
    }
  };

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={() => guard(onBack)} style={backButtonStyle}>
        ← Volver
      </button>

      <div>
        <h2 style={titleStyle(isMobile)}>Ajuste de inventario</h2>
        {estado.mes ? (
          <p style={subtitleStyle}>Mes en curso: {nombreMes(estado.mes)} de {estado.anio}</p>
        ) : null}
      </div>

      <Toast toast={toast} onClose={hideToast} />
      <UnsavedChangesModal open={isConfirmOpen} onConfirm={confirmLeave} onCancel={cancelLeave} />

      {loading ? (
        <div style={emptyStyle}>Cargando...</div>
      ) : mesCerrado ? (
        <section style={panelStyle}>
          <div style={sectionTitleStyle}>Mes cerrado</div>
          <p style={{ color: '#d2c3c3', margin: 0 }}>
            El mes de {nombreMes(estado.mes)} ya fue cerrado, no se pueden hacer más ajustes.
          </p>
        </section>
      ) : (
        <>
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
                        <span style={{ color: '#fff', fontWeight: 600 }}>{item.nombre}</span>
                        <span style={{ color: '#e8bcbc', fontSize: 12 }}>{item.unidad_medida || ''}</span>
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

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>
              Líneas del ajuste {ajuste ? `#${ajuste.id}` : ''} {hasItems ? `(${detalles.length})` : ''}
            </div>
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
                    <>
                      <div key={`name-${detalle.id}`} style={cellPrimaryStyle}>{detalle.ingrediente_nombre}</div>
                      <div key={`tipo-${detalle.id}`} style={cellStyle}>{detalle.tipo === 'suma' ? 'Suma' : 'Resta'}</div>
                      <div key={`cant-${detalle.id}`} style={cellStyle}>
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
                      <div key={`motivo-${detalle.id}`} style={cellStyle}>{detalle.motivo || '—'}</div>
                      <div key={`badge-${detalle.id}`} style={cellStyle}>
                        <span style={badgeStyle(detalle.aplicado)}>{detalle.aplicado ? 'Aplicada' : 'Pendiente'}</span>
                      </div>
                      <div key={`actions-${detalle.id}`} style={{ ...cellStyle, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        {editingId === detalle.id ? (
                          <>
                            <button type="button" onClick={() => handleSaveEdit(detalle.id)} style={smallActionButtonStyle} disabled={savingEdit}>
                              {savingEdit ? '...' : 'Guardar'}
                            </button>
                            <button type="button" onClick={handleCancelEdit} style={smallSecondaryButtonStyle} disabled={savingEdit}>Cancelar</button>
                          </>
                        ) : (
                          <button type="button" onClick={() => handleStartEdit(detalle)} style={smallSecondaryButtonStyle}>Editar</button>
                        )}
                        <button type="button" onClick={() => handleRemoveItem(detalle.id)} style={dangerButtonStyle}>Quitar</button>
                      </div>
                    </>
                  ))}
                </div>
              </div>
            )}

            {hasItems ? (
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                <button type="button" onClick={handleGuardar} style={primaryButtonStyle} disabled={saving}>
                  {saving ? 'Guardando...' : 'Guardar ajuste'}
                </button>
                {!tieneAplicadas ? (
                  <button type="button" onClick={handleDiscard} style={secondaryButtonStyle} disabled={discarding}>
                    {discarding ? 'Descartando...' : 'Descartar ajuste'}
                  </button>
                ) : null}
              </div>
            ) : null}
          </section>

          {estado.historico && estado.historico.length > 0 ? (
            <section style={panelStyle}>
              <div style={sectionTitleStyle}>Histórico del mes</div>
              <div style={{ display: 'grid', gap: 6 }}>
                {estado.historico.map((item) => (
                  <div key={item.id} style={{ color: '#d2c3c3', fontSize: 13 }}>
                    Ajuste #{item.id} — {item.total_lineas} línea(s) — {new Date(item.fecha_creacion).toLocaleString()}
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Cierre mensual</div>
            <p style={hintStyle}>
              Cerrar el mes bloquea crear o editar ajustes de {nombreMes(estado.mes)} — el histórico queda de solo lectura.
            </p>
            <button type="button" onClick={() => setCierreModalOpen(true)} style={dangerButtonStyle}>
              Cerrar mes
            </button>
          </section>

          <ConfirmModal
            open={cierreModalOpen}
            title="Cerrar mes"
            message={`Vas a cerrar el mes de ${nombreMes(estado.mes)} de ${estado.anio}. Ya no podrás crear ni editar ajustes de este mes. ¿Confirmas?`}
            confirmLabel="Sí, cerrar mes"
            cancelLabel="Cancelar"
            onConfirm={handleCerrarMes}
            onCancel={() => setCierreModalOpen(false)}
            busy={cerrandoMes}
          />
        </>
      )}
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 26 : 32 });
const subtitleStyle = { margin: '8px 0 0', color: '#d2c3c3', lineHeight: 1.6, maxWidth: 760 };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const sectionTitleStyle = { color: '#fff', fontSize: 17, fontWeight: 700 };
const emptyStyle = { minHeight: 60, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };

const itemFormStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1.6fr 1fr 1fr 1.4fr auto', gap: 10, alignItems: 'end' });
const fieldStyle = { display: 'grid', gap: 6 };
const labelStyle = { color: '#f0b4b4', fontSize: 12.5, fontWeight: 700 };
const inputStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 10, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '9px 10px', color: '#fff', fontSize: 13 };
const hintStyle = { margin: 0, color: '#a89999', fontSize: 12 };

const suggestionsPanelStyle = { position: 'absolute', top: '100%', left: 0, right: 0, marginTop: 6, zIndex: 5, borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: 'rgba(10, 8, 8, 0.98)', boxShadow: '0 12px 30px rgba(0,0,0,0.4)', padding: 8, display: 'grid', gap: 4, maxHeight: 220, overflowY: 'auto' };
const suggestionRowStyle = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 10, padding: '8px 10px', background: 'rgba(255,255,255,0.04)', cursor: 'pointer', textAlign: 'left' };

const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(160px,1.2fr) 90px 130px minmax(140px,1.4fr) 100px minmax(160px,auto)', gap: '10px 12px', alignItems: 'center', minWidth: 860 };
const headStyle = { color: '#f0b4b4', fontSize: 11.5, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em', padding: '4px 2px', borderBottom: '1px solid rgba(255,255,255,0.1)' };
const cellStyle = { color: '#fff', fontSize: 13, padding: '6px 2px', borderBottom: '1px solid rgba(255,255,255,0.06)' };
const cellPrimaryStyle = { ...cellStyle, fontWeight: 700 };

const badgeStyle = (aplicado) => ({
  display: 'inline-block',
  padding: '3px 10px',
  borderRadius: 999,
  fontSize: 11.5,
  fontWeight: 800,
  background: aplicado ? 'rgba(52, 211, 153, 0.18)' : 'rgba(255, 205, 86, 0.18)',
  color: aplicado ? '#34d399' : '#ffcd56',
  border: `1px solid ${aplicado ? 'rgba(52, 211, 153, 0.4)' : 'rgba(255, 205, 86, 0.4)'}`,
});

const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const secondaryButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer', width: 'fit-content' };
const dangerButtonStyle = { border: '1px solid rgba(255,126,126,0.4)', borderRadius: 999, padding: '6px 12px', background: 'rgba(145,33,33,0.25)', color: '#ffd3d3', fontWeight: 700, cursor: 'pointer', fontSize: 12, width: 'fit-content' };
const smallActionButtonStyle = { border: 'none', borderRadius: 999, padding: '6px 12px', background: 'linear-gradient(90deg, #1f7a3f 0%, #34d399 100%)', color: '#04140a', fontWeight: 700, cursor: 'pointer', fontSize: 12 };
const smallSecondaryButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '6px 12px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: 12 };

export default AnalystAjusteInventarioPage;

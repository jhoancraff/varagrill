import { useEffect, useMemo, useState } from 'react';
import Toast from './Toast';
import useToast from '../hooks/useToast';

const emptyItemForm = { nombre: '', unidad: 'g', cantidad: '', precio_total: '' };
const emptyLote = { proveedor_nombre: '', numero_factura_proveedor: '' };

function AnalystComprasBorradorPage({ isMobile, onBack }) {
  const [inventory, setInventory] = useState([]);
  const [borrador, setBorrador] = useState({ id: null, detalles: [], total: '0' });
  const [loading, setLoading] = useState(true);
  const [itemForm, setItemForm] = useState(emptyItemForm);
  const [isNameFocused, setIsNameFocused] = useState(false);
  const [addingItem, setAddingItem] = useState(false);
  const [lote, setLote] = useState(emptyLote);
  const [confirming, setConfirming] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const { toast, showSuccess, showError, hideToast } = useToast();
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    const loadAll = async () => {
      setLoading(true);
      try {
        const [catalogoRes, borradorRes] = await Promise.all([
          fetch('/api/admin/catalogo/', { credentials: 'include', cache: 'no-store' }),
          fetch('/api/admin/compras/borrador/', { credentials: 'include', cache: 'no-store' }),
        ]);
        const catalogoData = await catalogoRes.json();
        const borradorData = await borradorRes.json();
        if (catalogoRes.ok && catalogoData.ok) {
          setInventory(Array.isArray(catalogoData.inventory) ? catalogoData.inventory : []);
        }
        if (borradorRes.ok && borradorData.ok) {
          setBorrador(borradorData.borrador);
        } else {
          showError(borradorData.message || 'No se pudo cargar el borrador.');
        }
      } catch (error) {
        showError('No se pudo cargar la informacion inicial.');
      } finally {
        setLoading(false);
      }
    };
    loadAll();
  }, []);

  const nameQuery = itemForm.nombre.trim().toLowerCase();

  const nameMatches = useMemo(() => {
    if (!nameQuery) return [];
    return inventory.filter((item) => (item.nombre || '').toLowerCase().includes(nameQuery)).slice(0, 6);
  }, [inventory, nameQuery]);

  const exactMatch = useMemo(
    () => inventory.find((item) => (item.nombre || '').toLowerCase() === nameQuery) || null,
    [inventory, nameQuery],
  );

  const handleSelectExisting = (item) => {
    setItemForm((current) => ({ ...current, nombre: item.nombre }));
    setIsNameFocused(false);
  };

  const handleAddItem = async (event) => {
    event.preventDefault();
    if (!itemForm.nombre.trim()) {
      showError('Escribe el nombre del ingrediente.');
      return;
    }

    setAddingItem(true);
    try {
      const body = exactMatch
        ? { ingrediente_id: exactMatch.id, cantidad: itemForm.cantidad, precio_total: itemForm.precio_total }
        : { nombre: itemForm.nombre, unidad: itemForm.unidad, cantidad: itemForm.cantidad, precio_total: itemForm.precio_total };

      const response = await fetch('/api/admin/compras/borrador/agregar/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo agregar el ingrediente al borrador.');
      }
      setBorrador(data.borrador);
      setItemForm(emptyItemForm);
      if (!exactMatch) {
        setInventory((current) => [...current, { id: undefined, nombre: itemForm.nombre }]);
      }
    } catch (error) {
      showError(error.message || 'No se pudo agregar el ingrediente al borrador.');
    } finally {
      setAddingItem(false);
    }
  };

  const handleRemoveItem = async (detalleId) => {
    try {
      const response = await fetch('/api/admin/compras/borrador/quitar/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ detalle_id: detalleId }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo quitar esa fila.');
      }
      setBorrador(data.borrador);
    } catch (error) {
      showError(error.message || 'No se pudo quitar esa fila.');
    }
  };

  const handleDiscard = async () => {
    if (!window.confirm('Deseas descartar todo el borrador? Se perderan los ingredientes agregados.')) {
      return;
    }
    setDiscarding(true);
    try {
      const response = await fetch('/api/admin/compras/borrador/descartar/', {
        method: 'POST',
        credentials: 'include',
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo descartar el borrador.');
      }
      setBorrador(data.borrador);
      setSummary(null);
    } catch (error) {
      showError(error.message || 'No se pudo descartar el borrador.');
    } finally {
      setDiscarding(false);
    }
  };

  const handleConfirm = async (event) => {
    event.preventDefault();
    if (!lote.proveedor_nombre.trim()) {
      showError('El proveedor es obligatorio para confirmar la carga.');
      return;
    }

    setConfirming(true);
    try {
      const response = await fetch('/api/admin/compras/borrador/confirmar/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(lote),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo confirmar la carga.');
      }
      setSummary(data.compra);
      setBorrador({ id: null, detalles: [], total: '0' });
      setLote(emptyLote);
      showSuccess(data.message || 'Carga confirmada.');
    } catch (error) {
      showError(error.message || 'No se pudo confirmar la carga.');
    } finally {
      setConfirming(false);
    }
  };

  const hasItems = borrador.detalles && borrador.detalles.length > 0;

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>
        ← Volver
      </button>

      <div>
        <h2 style={titleStyle(isMobile)}>Cargar por lote (factura de proveedor)</h2>
        <p style={subtitleStyle}>
          Ve agregando cada ingrediente de la factura, uno por uno. Lo agregado queda guardado aunque cierres la
          pagina o vuelvas otro dia — recien se aplica al inventario cuando confirmes la carga completa, y ahi se
          genera la cuenta por pagar de ese lote.
        </p>
      </div>

      <Toast toast={toast} onClose={hideToast} />

      {loading ? (
        <div style={emptyStyle}>Cargando...</div>
      ) : (
        <>
          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Agregar ingrediente</div>
            <form onSubmit={handleAddItem} style={itemFormStyle(isMobile)}>
              <div style={{ ...fieldStyle, position: 'relative' }}>
                <span style={labelStyle}>Ingrediente</span>
                <input
                  value={itemForm.nombre}
                  onChange={(e) => setItemForm((c) => ({ ...c, nombre: e.target.value }))}
                  onFocus={() => setIsNameFocused(true)}
                  onBlur={() => setTimeout(() => setIsNameFocused(false), 150)}
                  placeholder="Ejemplo: Tomate, Queso blanco..."
                  style={inputStyle}
                  autoComplete="off"
                />
                {isNameFocused && nameQuery && nameMatches.length > 0 ? (
                  <div style={suggestionsPanelStyle}>
                    <div style={suggestionsHintStyle}>Ingredientes existentes:</div>
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
                {nameQuery && !exactMatch ? (
                  <div style={hintStyle}>No existe todavia — se creara con la unidad que elijas.</div>
                ) : null}
              </div>

              {!exactMatch ? (
                <label style={fieldStyle}>
                  <span style={labelStyle}>Unidad</span>
                  <select value={itemForm.unidad} onChange={(e) => setItemForm((c) => ({ ...c, unidad: e.target.value }))} style={inputStyle}>
                    <option value="g">Gramos (g)</option>
                    <option value="ml">Mililitros (ml)</option>
                    <option value="unidad">Unidad</option>
                  </select>
                </label>
              ) : (
                <div style={fieldStyle}>
                  <span style={labelStyle}>Unidad actual</span>
                  <div style={{ ...inputStyle, display: 'flex', alignItems: 'center', color: '#c8bbbb' }}>{exactMatch.unidad_medida}</div>
                </div>
              )}

              <label style={fieldStyle}>
                <span style={labelStyle}>Cantidad recibida</span>
                <input type="number" step="0.01" min="0" value={itemForm.cantidad} onChange={(e) => setItemForm((c) => ({ ...c, cantidad: e.target.value }))} style={inputStyle} required />
              </label>

              <label style={fieldStyle}>
                <span style={labelStyle}>Precio total pagado</span>
                <input type="number" step="0.01" min="0" value={itemForm.precio_total} onChange={(e) => setItemForm((c) => ({ ...c, precio_total: e.target.value }))} style={inputStyle} required />
              </label>

              <button type="submit" style={primaryButtonStyle} disabled={addingItem}>
                {addingItem ? 'Agregando...' : 'Agregar al borrador'}
              </button>
            </form>
          </section>

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Ingredientes en el borrador {hasItems ? `(${borrador.detalles.length})` : ''}</div>
            {!hasItems ? (
              <div style={emptyStyle}>Todavia no has agregado ningun ingrediente.</div>
            ) : (
              <>
                <div style={tableWrapStyle}>
                  <div style={tableStyle}>
                    <div style={headStyle}>Ingrediente</div>
                    <div style={headStyle}>Cantidad</div>
                    <div style={headStyle}>Costo unitario</div>
                    <div style={headStyle}>Precio total</div>
                    <div style={headStyle}></div>
                    {borrador.detalles.map((detalle) => (
                      <>
                        <div key={`name-${detalle.id}`} style={cellPrimaryStyle}>{detalle.ingrediente_nombre}</div>
                        <div key={`qty-${detalle.id}`} style={cellStyle}>{detalle.cantidad} {detalle.unidad_medida}</div>
                        <div key={`cost-${detalle.id}`} style={cellStyle}>${detalle.costo_unitario}</div>
                        <div key={`total-${detalle.id}`} style={cellStyle}>${detalle.precio_total}</div>
                        <div key={`actions-${detalle.id}`} style={cellStyle}>
                          <button type="button" onClick={() => handleRemoveItem(detalle.id)} style={dangerButtonStyle}>Quitar</button>
                        </div>
                      </>
                    ))}
                  </div>
                </div>
                <div style={{ color: '#ffcf7d', fontWeight: 800, textAlign: 'right' }}>Total del lote: ${borrador.total}</div>
              </>
            )}
          </section>

          {hasItems ? (
            <section style={panelStyle}>
              <div style={sectionTitleStyle}>Confirmar carga</div>
              <form onSubmit={handleConfirm} style={loteFormStyle(isMobile)}>
                <input
                  value={lote.proveedor_nombre}
                  onChange={(event) => setLote((c) => ({ ...c, proveedor_nombre: event.target.value }))}
                  style={inputStyle}
                  placeholder="Proveedor"
                  required
                />
                <input
                  value={lote.numero_factura_proveedor}
                  onChange={(event) => setLote((c) => ({ ...c, numero_factura_proveedor: event.target.value }))}
                  style={inputStyle}
                  placeholder="Numero de factura (opcional)"
                />
                <button type="submit" style={primaryButtonStyle} disabled={confirming}>
                  {confirming ? 'Confirmando...' : 'Confirmar y generar cuenta por pagar'}
                </button>
              </form>
              <p style={hintStyle}>La fecha de la carga se registra automaticamente con la fecha de hoy.</p>
              <button type="button" onClick={handleDiscard} style={secondaryButtonStyle} disabled={discarding}>
                {discarding ? 'Descartando...' : 'Descartar borrador'}
              </button>
            </section>
          ) : null}

          {summary ? (
            <section style={panelStyle}>
              <div style={sectionTitleStyle}>Compra registrada</div>
              <p style={{ color: '#d2c3c3', margin: 0 }}>
                Lote #{summary.id} — {summary.proveedor_nombre} — Total ${summary.total}. Cuenta por pagar generada con
                saldo pendiente de ${summary.saldo_pendiente}.
              </p>
            </section>
          ) : null}
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

const itemFormStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1.6fr 1fr 1fr 1fr auto', gap: 10, alignItems: 'end' });
const fieldStyle = { display: 'grid', gap: 6 };
const labelStyle = { color: '#f0b4b4', fontSize: 12.5, fontWeight: 700 };
const inputStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 10, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '9px 10px', color: '#fff', fontSize: 13 };
const hintStyle = { margin: 0, color: '#a89999', fontSize: 12 };

const suggestionsPanelStyle = { position: 'absolute', top: '100%', left: 0, right: 0, marginTop: 6, zIndex: 5, borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: 'rgba(10, 8, 8, 0.98)', boxShadow: '0 12px 30px rgba(0,0,0,0.4)', padding: 8, display: 'grid', gap: 4, maxHeight: 220, overflowY: 'auto' };
const suggestionsHintStyle = { color: '#e8bcbc', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', padding: '4px 6px' };
const suggestionRowStyle = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 10, padding: '8px 10px', background: 'rgba(255,255,255,0.04)', cursor: 'pointer', textAlign: 'left' };

const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(160px,1.4fr) 130px 130px 110px 90px', gap: '10px 12px', alignItems: 'center', minWidth: 700 };
const headStyle = { color: '#f0b4b4', fontSize: 11.5, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em', padding: '4px 2px', borderBottom: '1px solid rgba(255,255,255,0.1)' };
const cellStyle = { color: '#fff', fontSize: 13, padding: '6px 2px', borderBottom: '1px solid rgba(255,255,255,0.06)' };
const cellPrimaryStyle = { ...cellStyle, fontWeight: 700 };

const loteFormStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1.4fr 1.4fr auto', gap: 10 });

const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const secondaryButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer', width: 'fit-content' };
const dangerButtonStyle = { border: '1px solid rgba(255,126,126,0.4)', borderRadius: 999, padding: '6px 12px', background: 'rgba(145,33,33,0.25)', color: '#ffd3d3', fontWeight: 700, cursor: 'pointer', fontSize: 12 };

export default AnalystComprasBorradorPage;

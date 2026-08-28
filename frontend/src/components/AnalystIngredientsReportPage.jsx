import { useEffect, useMemo, useState } from 'react';
import Pagination from './Pagination';
import Toast from './Toast';
import useToast from '../hooks/useToast';

const PAGE_SIZE = 50;

function AnalystIngredientsReportPage({ isMobile, onBack, onEdit, onImport, onCargaPorLote }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [saving, setSaving] = useState(false);
  const { toast, showSuccess, showError, hideToast } = useToast();
  const [page, setPage] = useState(0);

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
          throw new Error(data.message || 'No se pudo cargar el inventario.');
        }
        setItems(Array.isArray(data.inventory) ? data.inventory : []);
      } catch (error) {
        showError(error.message || 'No se pudo cargar el inventario.');
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, []);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) {
      return items;
    }
    return items.filter((item) => {
      const source = `${item.nombre || ''} ${item.unidad_medida || ''} ${item.ultimo_proveedor || ''}`.toLowerCase();
      return source.includes(query);
    });
  }, [items, search]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const pagedItems = filtered.slice(currentPage * PAGE_SIZE, currentPage * PAGE_SIZE + PAGE_SIZE);

  const handleDelete = async (item) => {
    if (!window.confirm(`Deseas eliminar el ingrediente ${item.nombre}?`)) {
      return;
    }

    setSaving(true);
    try {
      const response = await fetch('/api/admin/catalogo/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tipo: 'eliminar_inventario', id: item.id }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo eliminar el ingrediente.');
      }
      setItems((current) => current.filter((entry) => entry.id !== item.id));
      showSuccess(data.message || 'Ingrediente eliminado correctamente.');
    } catch (error) {
      showError(error.message || 'No se pudo eliminar el ingrediente.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>
        ← Volver al panel
      </button>

      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Reporte de ingredientes</h2>
          <p style={subtitleStyle}>Busca, modifica o elimina ingredientes del inventario.</p>
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          {onCargaPorLote ? (
            <button type="button" onClick={onCargaPorLote} style={secondaryButtonStyle}>
              Cargar por lote (manual)
            </button>
          ) : null}
          {onImport ? (
            <button type="button" onClick={onImport} style={primaryButtonStyle}>
              Importar desde Excel
            </button>
          ) : null}
        </div>
      </div>

      <Toast toast={toast} onClose={hideToast} />

      <section style={panelStyle}>
        <div style={toolbarStyle(isMobile)}>
          <div style={sectionTitleStyle}>Listado</div>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Buscar por nombre, unidad o proveedor"
            style={searchInputStyle(isMobile)}
          />
        </div>

        {loading ? <div style={emptyStyle}>Cargando ingredientes...</div> : null}
        {!loading && filtered.length === 0 ? <div style={emptyStyle}>No hay ingredientes para esa busqueda.</div> : null}

        {!loading && filtered.length > 0 ? (
          <div style={tableWrapStyle}>
            <div style={tableStyle}>
              <div style={headStyle}>Ingrediente</div>
              <div style={headStyle}>Stock</div>
              <div style={headStyle}>Costo</div>
              <div style={headStyle}>Proveedor</div>
              <div style={headStyle}>Acciones</div>

              {pagedItems.map((item) => (
                <>
                  <div key={`name-${item.id}`} style={cellPrimaryStyle}>
                    <div style={{ fontWeight: 700 }}>{item.nombre}</div>
                    <div style={{ fontSize: 12, color: '#d2c4c4' }}>ID #{item.id}</div>
                  </div>
                  <div key={`stock-${item.id}`} style={cellStyle}>
                    {item.stock_actual || '0'} {item.unidad_medida || 'unidad'}
                  </div>
                  <div key={`cost-${item.id}`} style={cellStyle}>
                    {item.costo_unitario || '0'}
                  </div>
                  <div key={`provider-${item.id}`} style={cellStyle}>
                    {item.ultimo_proveedor || 'Sin proveedor'}
                  </div>
                  <div key={`actions-${item.id}`} style={cellActionsStyle}>
                    <button type="button" onClick={() => onEdit(item.id)} style={secondaryButtonStyle}>Modificar</button>
                    <button type="button" onClick={() => handleDelete(item)} style={dangerButtonStyle} disabled={saving}>Eliminar</button>
                  </div>
                </>
              ))}
            </div>
          </div>
        ) : null}

        <Pagination
          page={currentPage}
          pageCount={pageCount}
          totalCount={filtered.length}
          pageSize={PAGE_SIZE}
          isMobile={isMobile}
          onPrev={() => setPage((current) => Math.max(0, current - 1))}
          onNext={() => setPage((current) => Math.min(pageCount - 1, current + 1))}
        />
      </section>
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const headerRowStyle = (isMobile) => ({ display: 'flex', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center', flexDirection: isMobile ? 'column' : 'row', gap: 12 });
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: '#d2c3c3' };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const toolbarStyle = (isMobile) => ({ display: 'flex', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center', flexDirection: isMobile ? 'column' : 'row', gap: 10 });
const sectionTitleStyle = { color: '#fff', fontSize: 19, fontWeight: 700 };
const searchInputStyle = (isMobile) => ({ width: isMobile ? '100%' : 360, borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff' });
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(200px,1.2fr) minmax(150px,1fr) minmax(120px,0.8fr) minmax(160px,1fr) minmax(220px,1fr)', minWidth: 900, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(255,255,255,0.06)', color: '#ffb0b0', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '14px', borderTop: '1px solid rgba(255,255,255,0.08)', color: '#f2e6e6', display: 'grid', alignContent: 'center' };
const cellPrimaryStyle = { ...cellStyle, background: 'rgba(255,255,255,0.02)' };
const cellActionsStyle = { ...cellStyle, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const secondaryButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer', width: 'fit-content' };
const dangerButtonStyle = { border: '1px solid rgba(255,126,126,0.4)', borderRadius: 999, padding: '10px 16px', background: 'rgba(145,33,33,0.25)', color: '#ffd3d3', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default AnalystIngredientsReportPage;
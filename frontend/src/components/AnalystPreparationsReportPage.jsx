import { useEffect, useMemo, useState } from 'react';

function AnalystPreparationsReportPage({ isMobile, onBack, onCreateNew, onEdit }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

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
          throw new Error(data.message || 'No se pudo cargar el reporte de subrecetas.');
        }
        setItems(Array.isArray(data.recipes) ? data.recipes : []);
      } catch (error) {
        setMessage(error.message || 'No se pudo cargar el reporte de subrecetas.');
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
      const comps = (item.componentes || []).map((component) => component.nombre || '').join(' ');
      return `${item.nombre || ''} ${comps}`.toLowerCase().includes(query);
    });
  }, [items, search]);

  const handleDelete = async (item) => {
    if (!window.confirm(`Deseas eliminar la subreceta ${item.nombre}?`)) {
      return;
    }

    setSaving(true);
    try {
      const response = await fetch('/api/admin/catalogo/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tipo: 'eliminar_receta', id: item.id }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo eliminar la subreceta.');
      }
      setItems((current) => current.filter((entry) => entry.id !== item.id));
      setMessage(data.message || 'Subreceta eliminada correctamente.');
    } catch (error) {
      setMessage(error.message || 'No se pudo eliminar la subreceta.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <section style={containerStyle(isMobile)}>
      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Reporte de subrecetas</h2>
          <p style={subtitleStyle}>Busca, modifica o elimina preparaciones y subrecetas.</p>
        </div>
        <button type="button" onClick={onCreateNew} style={primaryButtonStyle}>Agregar subreceta</button>
      </div>

      {message ? <div style={noticeStyle}>{message}</div> : null}

      <section style={panelStyle}>
        <div style={toolbarStyle(isMobile)}>
          <div style={sectionTitleStyle}>Listado</div>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Buscar por nombre o componente"
            style={searchInputStyle(isMobile)}
          />
        </div>

        {loading ? <div style={emptyStyle}>Cargando subrecetas...</div> : null}
        {!loading && filtered.length === 0 ? <div style={emptyStyle}>No hay subrecetas para esa busqueda.</div> : null}

        {!loading && filtered.length > 0 ? (
          <div style={tableWrapStyle}>
            <div style={tableStyle}>
              <div style={headStyle}>Subreceta</div>
              <div style={headStyle}>Rendimiento</div>
              <div style={headStyle}>Componentes</div>
              <div style={headStyle}>Costo</div>
              <div style={headStyle}>Acciones</div>

              {filtered.map((item) => (
                <>
                  <div key={`name-${item.id}`} style={cellPrimaryStyle}>
                    <div style={{ fontWeight: 700 }}>{item.nombre}</div>
                    <div style={{ fontSize: 12, color: '#d2c4c4' }}>ID #{item.id}</div>
                  </div>
                  <div key={`yield-${item.id}`} style={cellStyle}>
                    {item.rendimiento_cantidad || '0'} {item.rendimiento_unidad || 'unidad'}
                  </div>
                  <div key={`components-${item.id}`} style={cellStyle}>
                    <div style={{ color: '#ffcaca', fontSize: 13, fontWeight: 700 }}>{item.componentes_total || 0} componentes</div>
                    <div style={{ color: '#d2c4c4', fontSize: 13 }}>{(item.componentes || []).slice(0, 3).map((component) => component.nombre).join(', ') || 'Sin componentes'}</div>
                  </div>
                  <div key={`cost-${item.id}`} style={cellStyle}>
                    <div style={{ color: '#fff', fontWeight: 700 }}>${item.costo_total || '0.00'} total</div>
                    <div style={{ color: '#7dffa0', fontSize: 13 }}>${item.costo_unitario_calculado || '0.00'} / {item.rendimiento_unidad || 'unidad'}</div>
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
      </section>

      <button type="button" onClick={onBack} style={secondaryButtonStyle}>Volver al panel</button>
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
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(200px,1.2fr) minmax(160px,0.9fr) minmax(220px,1.1fr) minmax(160px,0.9fr) minmax(220px,1fr)', minWidth: 1080, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(255,255,255,0.06)', color: '#ffb0b0', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '14px', borderTop: '1px solid rgba(255,255,255,0.08)', color: '#f2e6e6', display: 'grid', alignContent: 'center', gap: 4 };
const cellPrimaryStyle = { ...cellStyle, background: 'rgba(255,255,255,0.02)' };
const cellActionsStyle = { ...cellStyle, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const secondaryButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer', width: 'fit-content' };
const dangerButtonStyle = { border: '1px solid rgba(255,126,126,0.4)', borderRadius: 999, padding: '10px 16px', background: 'rgba(145,33,33,0.25)', color: '#ffd3d3', fontWeight: 700, cursor: 'pointer' };

export default AnalystPreparationsReportPage;

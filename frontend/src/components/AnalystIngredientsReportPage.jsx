import { Fragment, useEffect, useMemo, useState } from 'react';
import BotonDescargarPdf from './BotonDescargarPdf';
import ConfirmModal from './ConfirmModal';
import MenuAcciones from './MenuAcciones';
import Pagination from './Pagination';
import Toast from './Toast';
import useToast from '../hooks/useToast';
import descargarPdf from '../utils/descargarPdf';

const PAGE_SIZE = 50;

function AnalystIngredientsReportPage({ isMobile, onBack, onEdit, onImport, onCargaPorLote, onCategorias, onMovimientos }) {
  const [items, setItems] = useState([]);
  const [categorias, setCategorias] = useState([]);
  // '' = todas, 'sin' = sin categoría, o el id de la categoría.
  const [filtroCategoria, setFiltroCategoria] = useState('');
  const [seleccion, setSeleccion] = useState(() => new Set());
  const [categoriaLote, setCategoriaLote] = useState('');
  const [confirmarLote, setConfirmarLote] = useState(false);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [saving, setSaving] = useState(false);
  const { toast, showSuccess, showError, hideToast } = useToast();
  const [page, setPage] = useState(0);

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
      setCategorias(Array.isArray(data.categorias_inventario) ? data.categorias_inventario : []);
    } catch (error) {
      showError(error.message || 'No se pudo cargar el inventario.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return items.filter((item) => {
      if (filtroCategoria === 'sin' && item.categoria) {
        return false;
      }
      if (filtroCategoria && filtroCategoria !== 'sin' && String(item.categoria) !== filtroCategoria) {
        return false;
      }
      if (!query) {
        return true;
      }
      const source = `${item.nombre || ''} ${item.unidad_medida || ''} ${item.ultimo_proveedor || ''} ${item.categoria_nombre || ''}`.toLowerCase();
      return source.includes(query);
    });
  }, [items, search, filtroCategoria]);

  const alternarSeleccion = (id) => {
    setSeleccion((actual) => {
      const copia = new Set(actual);
      if (copia.has(id)) {
        copia.delete(id);
      } else {
        copia.add(id);
      }
      return copia;
    });
  };

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const pagedItems = filtered.slice(currentPage * PAGE_SIZE, currentPage * PAGE_SIZE + PAGE_SIZE);

  // Lleva los ingredientes marcados a una categoría (o los deja sin categoría).
  const handleAsignarCategoria = async () => {
    setConfirmarLote(false);
    if (seleccion.size === 0) {
      showError('Marca al menos un ingrediente.');
      return;
    }
    setSaving(true);
    try {
      const response = await fetch('/api/admin/catalogo/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tipo: 'asignar_categoria', ids: Array.from(seleccion), categoria_id: categoriaLote }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo asignar la categoría.');
      }
      showSuccess(data.message || 'Categoría asignada.');
      setSeleccion(new Set());
      await loadData();
    } catch (error) {
      showError(error.message || 'No se pudo asignar la categoría.');
    } finally {
      setSaving(false);
    }
  };

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

  // Acción independiente de facturar (ver VGIngrediente.ingrediente_crudo_equivalente):
  // "abre" N paquetes de un empacado y suma su contenido al ingrediente crudo, sin tocar
  // ninguna factura ni numeración fiscal — solo un ajuste de inventario trazable.
  const handleReponer = async (item) => {
    const crudo = items.find((entry) => String(entry.id) === String(item.ingrediente_crudo_equivalente));
    const crudoNombre = crudo ? crudo.nombre : 'el ingrediente crudo configurado';
    const cantidadStr = window.prompt(
      `¿Cuántos paquetes de "${item.nombre}" vas a abrir para reponer "${crudoNombre}"?`,
      '1',
    );
    if (!cantidadStr) {
      return;
    }
    const cantidad = Number(cantidadStr);
    if (!cantidad || cantidad <= 0) {
      showError('La cantidad de paquetes no es válida.');
      return;
    }

    setSaving(true);
    try {
      const response = await fetch('/api/admin/catalogo/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tipo: 'reponer_desde_empacado', empacado_id: item.id, cantidad_paquetes: cantidad }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo reponer el inventario.');
      }
      showSuccess(data.message || 'Inventario repuesto correctamente.');
      await loadData();
    } catch (error) {
      showError(error.message || 'No se pudo reponer el inventario.');
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
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <BotonDescargarPdf
            url="/api/admin/reportes/inventario-pdf/"
            params={{ categoria_id: filtroCategoria }}
            onError={showError}
          >
            {filtroCategoria ? 'Descargar PDF de esta categoría' : 'Descargar PDF'}
          </BotonDescargarPdf>
          <MenuAcciones
            label="Más acciones"
            items={[
              { label: 'Categorías de inventario', onClick: onCategorias, hidden: !onCategorias },
              { label: 'Ver movimientos del inventario', onClick: onMovimientos, hidden: !onMovimientos },
              { label: 'Cargar por lote (manual)', onClick: onCargaPorLote, hidden: !onCargaPorLote },
              { label: 'Importar desde Excel', onClick: onImport, hidden: !onImport },
            ]}
          />
        </div>
      </div>

      <Toast toast={toast} onClose={hideToast} />

      <section style={panelStyle}>
        <div style={toolbarStyle(isMobile)}>
          <div style={sectionTitleStyle}>Listado</div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <select
              value={filtroCategoria}
              onChange={(event) => { setFiltroCategoria(event.target.value); setPage(0); setSeleccion(new Set()); }}
              style={selectStyle}
              className="admin-dark-select"
            >
              <option value="">Todas las categorías</option>
              <option value="sin">Sin categoría</option>
              {categorias.map((categoria) => (
                <option key={categoria.id} value={String(categoria.id)}>
                  {categoria.nombre}{categoria.activo ? '' : ' (inactiva)'}
                </option>
              ))}
            </select>
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Buscar por nombre, unidad, proveedor o categoría"
              style={searchInputStyle(isMobile)}
            />
          </div>
        </div>

        {seleccion.size > 0 ? (
          <div style={loteBarStyle}>
            <strong>{seleccion.size} seleccionado(s)</strong>
            <select
              value={categoriaLote}
              onChange={(event) => setCategoriaLote(event.target.value)}
              style={selectStyle}
              className="admin-dark-select"
            >
              <option value="">Sin categoría</option>
              {categorias.filter((categoria) => categoria.activo).map((categoria) => (
                <option key={categoria.id} value={String(categoria.id)}>{categoria.nombre}</option>
              ))}
            </select>
            <button type="button" onClick={() => setConfirmarLote(true)} style={primaryButtonStyle} disabled={saving}>
              Asignar categoría
            </button>
            <button type="button" onClick={() => setSeleccion(new Set())} style={secondaryButtonStyle}>Limpiar</button>
          </div>
        ) : null}

        {loading ? <div style={emptyStyle}>Cargando ingredientes...</div> : null}
        {!loading && filtered.length === 0 ? <div style={emptyStyle}>No hay ingredientes para esa busqueda.</div> : null}

        {!loading && filtered.length > 0 ? (
          <div style={tableWrapStyle}>
            <div style={tableStyle}>
              <div style={headStyle}>
                <input
                  type="checkbox"
                  aria-label="Seleccionar los de esta página"
                  checked={pagedItems.length > 0 && pagedItems.every((item) => seleccion.has(item.id))}
                  onChange={(event) => setSeleccion((actual) => {
                    const copia = new Set(actual);
                    pagedItems.forEach((item) => (event.target.checked ? copia.add(item.id) : copia.delete(item.id)));
                    return copia;
                  })}
                />
              </div>
              <div style={headStyle}>Ingrediente</div>
              <div style={headStyle}>Categoría</div>
              <div style={headStyle}>Stock</div>
              <div style={headStyle}>Precio compra</div>
              <div style={headStyle}>Costo</div>
              <div style={headStyle}>Proveedor</div>
              <div style={headStyle}>Acciones</div>

              {pagedItems.map((item) => (
                <Fragment key={item.id}>
                  <div style={cellStyle}>
                    <input type="checkbox" checked={seleccion.has(item.id)} onChange={() => alternarSeleccion(item.id)} />
                  </div>
                  <div key={`name-${item.id}`} style={cellPrimaryStyle}>
                    <div style={{ fontWeight: 700 }}>{item.nombre}</div>
                    <div style={{ fontSize: 12, color: 'var(--vg-f-d2c4c4)' }}>ID #{item.id}</div>
                  </div>
                  <div style={cellStyle}>{item.categoria_nombre || <span style={{ color: 'var(--vg-f-a89999)' }}>Sin categoría</span>}</div>
                  <div key={`stock-${item.id}`} style={cellStyle}>
                    {item.stock_actual || '0'} {item.unidad_medida || 'unidad'}
                  </div>
                  <div key={`precio-compra-${item.id}`} style={cellStyle}>
                    {item.precio_compra || 'Sin dato'}
                  </div>
                  <div key={`cost-${item.id}`} style={cellStyle}>
                    {item.costo_unitario || '0'}
                  </div>
                  <div key={`provider-${item.id}`} style={cellStyle}>
                    {item.ultimo_proveedor || 'Sin proveedor'}
                  </div>
                  <div key={`actions-${item.id}`} style={cellActionsStyle}>
                    <button type="button" onClick={() => onEdit(item.id)} style={secondaryButtonStyle}>Modificar</button>
                    <MenuAcciones
                      disabled={saving}
                      items={[
                        { label: 'Reponer cocina', onClick: () => handleReponer(item), hidden: !item.ingrediente_crudo_equivalente },
                        { label: 'Eliminar', onClick: () => handleDelete(item), danger: true },
                      ]}
                    />
                  </div>
                </Fragment>
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
      <ConfirmModal
        open={confirmarLote}
        title="Asignar categoría"
        message={`¿Pasar ${seleccion.size} ingrediente(s) a ${
          categoriaLote ? `«${(categorias.find((c) => String(c.id) === String(categoriaLote)) || {}).nombre || 'la categoría'}»` : 'sin categoría'
        }?`}
        confirmLabel="Asignar"
        busy={saving}
        onCancel={() => setConfirmarLote(false)}
        onConfirm={handleAsignarCategoria}
      />
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const headerRowStyle = (isMobile) => ({ display: 'flex', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center', flexDirection: isMobile ? 'column' : 'row', gap: 12 });
const titleStyle = (isMobile) => ({ margin: 0, color: 'var(--vg-text-strong)', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: 'var(--vg-f-d2c3c3)' };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)' };
const toolbarStyle = (isMobile) => ({ display: 'flex', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center', flexDirection: isMobile ? 'column' : 'row', gap: 10 });
const sectionTitleStyle = { color: 'var(--vg-text-strong)', fontSize: 19, fontWeight: 700 };
const searchInputStyle = (isMobile) => ({ width: isMobile ? '100%' : 360, borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-161010)', padding: '10px 12px', color: 'var(--vg-text-strong)' });
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(var(--vg-ink), 0.12)', color: 'var(--vg-f-c8bbbb)' };
const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: '48px minmax(200px,1.2fr) minmax(140px,0.8fr) minmax(130px,0.9fr) minmax(140px,0.9fr) minmax(120px,0.8fr) minmax(160px,1fr) minmax(170px,0.8fr)', minWidth: 1180, border: '1px solid rgba(var(--vg-ink), 0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(var(--vg-ink), 0.06)', color: 'var(--vg-f-ffb0b0)', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '14px', borderTop: '1px solid rgba(var(--vg-ink), 0.08)', color: 'var(--vg-f-f2e6e6)', display: 'grid', alignContent: 'center' };
const cellPrimaryStyle = { ...cellStyle, background: 'rgba(var(--vg-ink), 0.02)' };
const cellActionsStyle = { ...cellStyle, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, var(--vg-accent-primary) 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const secondaryButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(var(--vg-ink), 0.04)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer', width: 'fit-content' };
const selectStyle = { borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-161010)', padding: '10px 12px', color: 'var(--vg-text-strong)', minWidth: 190 };
const loteBarStyle = { display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', padding: '10px 14px', borderRadius: 14, border: '1px solid var(--vg-f-ffcf85-a350)', background: 'rgba(255,207,133,0.06)', color: 'var(--vg-text-strong)' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default AnalystIngredientsReportPage;
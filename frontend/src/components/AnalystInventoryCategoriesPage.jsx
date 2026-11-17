import { useCallback, useEffect, useState } from 'react';
import ConfirmModal from './ConfirmModal';
import MenuAcciones from './MenuAcciones';
import Toast from './Toast';
import useToast from '../hooks/useToast';

async function pedir(opciones) {
  const response = await fetch('/api/admin/categorias-inventario/', {
    credentials: 'include',
    cache: 'no-store',
    ...opciones,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    throw new Error(data.message || 'No se pudo completar la operación.');
  }
  return data;
}

// Categorías del inventario (Condimentos, Carnes, Granos, Bolsas, Cajas...): crear,
// renombrar y activar/desactivar. Con ellas se clasifican los ingredientes y se
// filtra e imprime el inventario por categoría.
function AnalystInventoryCategoriesPage({ isMobile, onBack, onViewInventory }) {
  const [categorias, setCategorias] = useState([]);
  const [sinCategoria, setSinCategoria] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [nuevoNombre, setNuevoNombre] = useState('');
  const [editandoId, setEditandoId] = useState(null);
  const [nombreEnEdicion, setNombreEnEdicion] = useState('');
  const { toast, showSuccess, showError, hideToast } = useToast();
  const [confirmacion, setConfirmacion] = useState(null);

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const data = await pedir({});
      setCategorias(data.categorias || []);
      setSinCategoria(data.sin_categoria || 0);
    } catch (error) {
      showError(error.message);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const enviar = async (cuerpo, exito) => {
    setSaving(true);
    try {
      const data = await pedir({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cuerpo),
      });
      if (Array.isArray(data.categorias)) {
        setCategorias(data.categorias);
      }
      showSuccess(data.message || exito);
      return true;
    } catch (error) {
      showError(error.message);
      return false;
    } finally {
      setSaving(false);
    }
  };

  // Todo guardar/actualizar pasa primero por un diálogo de confirmación.
  const confirmar = async () => {
    if (!confirmacion) {
      return;
    }
    const hecho = await enviar(confirmacion.cuerpo, 'Listo.');
    if (hecho && confirmacion.alTerminar) {
      confirmacion.alTerminar();
    }
    setConfirmacion(null);
  };

  const handleCrear = (event) => {
    event.preventDefault();
    if (!nuevoNombre.trim()) {
      showError('Escribe el nombre de la categoría.');
      return;
    }
    setConfirmacion({
      title: 'Guardar categoría',
      message: `¿Crear la categoría «${nuevoNombre.trim()}»?`,
      confirmLabel: 'Guardar',
      cuerpo: { action: 'create', nombre: nuevoNombre.trim() },
      alTerminar: () => setNuevoNombre(''),
    });
  };

  const handleGuardarNombre = (categoria) => {
    if (!nombreEnEdicion.trim()) {
      showError('El nombre no puede quedar vacío.');
      return;
    }
    if (nombreEnEdicion.trim() === categoria.nombre) {
      setEditandoId(null);
      return;
    }
    setConfirmacion({
      title: 'Actualizar categoría',
      message: `¿Cambiar el nombre de «${categoria.nombre}» a «${nombreEnEdicion.trim()}»?`,
      confirmLabel: 'Actualizar',
      cuerpo: { action: 'update', id: categoria.id, nombre: nombreEnEdicion.trim() },
      alTerminar: () => setEditandoId(null),
    });
  };

  const handleToggleActivo = (categoria) => setConfirmacion({
    title: categoria.activo ? 'Desactivar categoría' : 'Activar categoría',
    message: categoria.activo
      ? `¿Desactivar «${categoria.nombre}»? Deja de ofrecerse al clasificar, pero los ingredientes que ya la tienen la conservan.`
      : `¿Activar «${categoria.nombre}» otra vez?`,
    confirmLabel: categoria.activo ? 'Desactivar' : 'Activar',
    cuerpo: { action: 'update', id: categoria.id, activo: !categoria.activo },
  });

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>← Volver</button>

      <div>
        <h2 style={titleStyle(isMobile)}>Categorías de inventario</h2>
        <p style={subtitleStyle}>
          Agrupa los ingredientes (Condimentos, Carnes, Granos, Bolsas, Cajas...) para filtrar el inventario
          e imprimirlo por categoría. Para llevar ingredientes a una categoría usa «Ver inventario actual»:
          puedes seleccionar varios y asignarlos de una vez.
        </p>
      </div>

      <Toast toast={toast} onClose={hideToast} />

      <form onSubmit={handleCrear} style={panelStyle}>
        <div style={sectionTitleStyle}>Nueva categoría</div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <input
            value={nuevoNombre}
            onChange={(event) => setNuevoNombre(event.target.value)}
            placeholder="Ej.: Condimentos"
            maxLength={80}
            style={{ ...inputStyle, flex: '1 1 260px' }}
          />
          <button type="submit" style={primaryButtonStyle} disabled={saving}>Crear categoría</button>
        </div>
      </form>

      <section style={panelStyle}>
        <div style={sectionTitleStyle}>Categorías</div>
        {loading ? <div style={emptyStyle}>Cargando...</div> : null}
        {!loading && categorias.length === 0 ? (
          <div style={emptyStyle}>Aún no hay categorías. Crea la primera arriba.</div>
        ) : null}

        {!loading && categorias.length > 0 ? (
          <div style={tableWrapStyle}>
            <div style={tableStyle}>
              <div style={headStyle}>Categoría</div>
              <div style={headStyle}>Ingredientes</div>
              <div style={headStyle}>Estado</div>
              <div style={headStyle}>Acciones</div>
              {categorias.map((categoria) => (
                <div key={categoria.id} style={{ display: 'contents' }}>
                  <div style={cellStyle}>
                    {editandoId === categoria.id ? (
                      <input
                        value={nombreEnEdicion}
                        onChange={(event) => setNombreEnEdicion(event.target.value)}
                        maxLength={80}
                        style={inputStyle}
                        autoFocus
                      />
                    ) : (
                      <strong>{categoria.nombre}</strong>
                    )}
                  </div>
                  <div style={cellStyle}>{categoria.ingredientes}</div>
                  <div style={cellStyle}>{categoria.activo ? 'Activa' : 'Inactiva'}</div>
                  <div style={cellActionsStyle}>
                    {editandoId === categoria.id ? (
                      <>
                        <button type="button" style={primaryButtonStyle} disabled={saving} onClick={() => handleGuardarNombre(categoria)}>Guardar</button>
                        <button type="button" style={secondaryButtonStyle} onClick={() => setEditandoId(null)}>Cancelar</button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          style={secondaryButtonStyle}
                          disabled={saving}
                          onClick={() => { setEditandoId(categoria.id); setNombreEnEdicion(categoria.nombre); }}
                        >
                          Renombrar
                        </button>
                        <MenuAcciones
                          disabled={saving}
                          items={[{ label: categoria.activo ? 'Desactivar' : 'Activar', onClick: () => handleToggleActivo(categoria) }]}
                        />
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        <div style={mutedStyle}>
          {sinCategoria} ingrediente(s) sin categoría.
          {onViewInventory ? (
            <>
              {' '}
              <button type="button" onClick={onViewInventory} style={linkButtonStyle}>Ir al inventario para clasificarlos</button>
            </>
          ) : null}
        </div>
      </section>
      <ConfirmModal
        open={Boolean(confirmacion)}
        title={confirmacion?.title || ''}
        message={confirmacion?.message || ''}
        confirmLabel={confirmacion?.confirmLabel}
        busy={saving}
        onCancel={() => setConfirmacion(null)}
        onConfirm={confirmar}
      />
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const titleStyle = (isMobile) => ({ margin: 0, color: 'var(--vg-text-strong)', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: 'var(--vg-f-d2c3c3)', lineHeight: 1.6, maxWidth: 760 };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)' };
const sectionTitleStyle = { color: 'var(--vg-text-strong)', fontSize: 19, fontWeight: 700 };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(var(--vg-ink), 0.12)', color: 'var(--vg-f-c8bbbb)' };
const mutedStyle = { color: 'var(--vg-f-a89999)', fontSize: 13 };
const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(220px,1.4fr) minmax(110px,0.6fr) minmax(110px,0.6fr) minmax(260px,1.2fr)', minWidth: 720, border: '1px solid rgba(var(--vg-ink), 0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(var(--vg-ink), 0.06)', color: 'var(--vg-f-ffb0b0)', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '12px 14px', borderTop: '1px solid rgba(var(--vg-ink), 0.08)', color: 'var(--vg-f-f2e6e6)', display: 'grid', alignContent: 'center' };
const cellActionsStyle = { ...cellStyle, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' };
const inputStyle = { borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-161010)', padding: '10px 12px', color: 'var(--vg-text-strong)', width: '100%', boxSizing: 'border-box' };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, var(--vg-accent-primary) 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const secondaryButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(var(--vg-ink), 0.04)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer', width: 'fit-content' };
const linkButtonStyle = { border: 'none', background: 'transparent', color: 'var(--vg-f-ff8f8f)', fontWeight: 700, cursor: 'pointer', padding: 0, textDecoration: 'underline' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default AnalystInventoryCategoriesPage;

import { Fragment, useEffect, useState } from 'react';
import Toast from './Toast';
import useToast from '../hooks/useToast';

// Zonas del delivery con su tarifa (Cerca / Media / Lejos o los sectores que se quieran). Al registrar un
// pedido delivery se elige una zona y su tarifa se copia al pedido; cambiarla aquí no toca pedidos ya
// registrados. La cajera siempre puede ajustar el monto de un pedido (ver NewOrderPage / CheckoutPage).
function AnalystZonasDeliveryPage({ isMobile, onBack }) {
  const [zonas, setZonas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  // Lo que se está escribiendo en cada fila: { [id]: { nombre, tarifa } }
  const [borradores, setBorradores] = useState({});
  const [nuevoNombre, setNuevoNombre] = useState('');
  const [nuevaTarifa, setNuevaTarifa] = useState('');
  const { toast, showSuccess, showError, hideToast } = useToast();

  const cargar = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/delivery/zonas/?todas=1', { credentials: 'include', cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudieron cargar las zonas de delivery.');
      }
      setZonas(Array.isArray(data.zonas) ? data.zonas : []);
      setBorradores({});
    } catch (error) {
      showError(error.message || 'No se pudieron cargar las zonas de delivery.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    cargar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const enviar = async (cuerpo, mensajeOk) => {
    setSaving(true);
    try {
      const response = await fetch('/api/delivery/zonas/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cuerpo),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo guardar la zona.');
      }
      showSuccess(mensajeOk || data.message || 'Listo.');
      await cargar();
      return true;
    } catch (error) {
      showError(error.message || 'No se pudo guardar la zona.');
      return false;
    } finally {
      setSaving(false);
    }
  };

  const valorFila = (zona) => borradores[zona.id] || { nombre: zona.nombre, tarifa: zona.tarifa };
  const cambiarFila = (zona, campo, valor) => {
    setBorradores((actual) => ({ ...actual, [zona.id]: { ...valorFila(zona), [campo]: valor } }));
  };
  const filaModificada = (zona) => {
    const valor = borradores[zona.id];
    return Boolean(valor) && (valor.nombre.trim() !== zona.nombre || Number(valor.tarifa) !== Number(zona.tarifa));
  };

  const guardarFila = (zona) => {
    const valor = valorFila(zona);
    if (!valor.nombre.trim()) {
      showError('La zona necesita un nombre.');
      return;
    }
    if (valor.tarifa === '' || Number.isNaN(Number(valor.tarifa)) || Number(valor.tarifa) < 0) {
      showError('Escribe una tarifa válida (0 o más).');
      return;
    }
    enviar({ action: 'update', id: zona.id, nombre: valor.nombre.trim(), tarifa: valor.tarifa }, 'Zona actualizada.');
  };

  const crear = async (event) => {
    event.preventDefault();
    if (!nuevoNombre.trim()) {
      showError('Escribe el nombre de la zona.');
      return;
    }
    if (nuevaTarifa === '' || Number.isNaN(Number(nuevaTarifa)) || Number(nuevaTarifa) < 0) {
      showError('Escribe una tarifa válida (0 o más).');
      return;
    }
    const creada = await enviar({ action: 'create', nombre: nuevoNombre.trim(), tarifa: nuevaTarifa }, 'Zona creada.');
    if (creada) {
      setNuevoNombre('');
      setNuevaTarifa('');
    }
  };

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>
        ← Volver al panel
      </button>

      <div>
        <h2 style={titleStyle(isMobile)}>Zonas de delivery</h2>
        <p style={hintStyle}>
          La tarifa es lo que se cobra por defecto al registrar un delivery en esa zona. Caja puede cambiar el monto de
          cada pedido si el cliente lo reclama. Cambiar una tarifa aquí no modifica los pedidos ya registrados.
        </p>
      </div>

      <Toast toast={toast} onClose={hideToast} />

      <section style={panelStyle}>
        <div style={sectionTitleStyle}>Zonas</div>
        {loading ? <div style={emptyStyle}>Cargando...</div> : null}
        {!loading && zonas.length === 0 ? <div style={emptyStyle}>Aún no hay zonas de delivery.</div> : null}
        {!loading && zonas.length > 0 ? (
          <div style={tableWrapStyle}>
            <div style={tableStyle}>
              <div style={headStyle}>Zona</div>
              <div style={headStyle}>Tarifa ($)</div>
              <div style={headStyle}>Estado</div>
              <div style={headStyle}>Acciones</div>
              {zonas.map((zona) => {
                const valor = valorFila(zona);
                const sinPrecio = !zona.activo && Number(zona.tarifa) === 0;
                return (
                  <Fragment key={zona.id}>
                    <div style={cellStyle}>
                      <input
                        type="text"
                        value={valor.nombre}
                        onChange={(event) => cambiarFila(zona, 'nombre', event.target.value)}
                        style={inputStyle}
                        maxLength={80}
                      />
                    </div>
                    <div style={cellStyle}>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        value={valor.tarifa}
                        onChange={(event) => cambiarFila(zona, 'tarifa', event.target.value)}
                        style={{ ...inputStyle, maxWidth: 140 }}
                      />
                    </div>
                    <div style={cellStyle}>
                      {zona.activo ? 'Activa' : 'Inactiva'}
                      {sinPrecio ? <span style={avisoStyle}>Ponle precio y actívala para usarla</span> : null}
                    </div>
                    <div style={cellActionsStyle}>
                      <button
                        type="button"
                        disabled={saving || !filaModificada(zona)}
                        onClick={() => guardarFila(zona)}
                        style={filaModificada(zona) ? primaryButtonStyle : disabledButtonStyle}
                      >
                        Guardar
                      </button>
                      <button
                        type="button"
                        disabled={saving}
                        onClick={() => enviar({ action: 'toggle', id: zona.id }, zona.activo ? 'Zona desactivada.' : 'Zona activada.')}
                        style={zona.activo ? dangerButtonStyle : secondaryButtonStyle}
                      >
                        {zona.activo ? 'Desactivar' : 'Activar'}
                      </button>
                    </div>
                  </Fragment>
                );
              })}
            </div>
          </div>
        ) : null}
      </section>

      <section style={panelStyle}>
        <div style={sectionTitleStyle}>Agregar zona</div>
        <form onSubmit={crear} style={formRowStyle(isMobile)}>
          <input
            type="text"
            placeholder="Nombre (ej. Centro)"
            value={nuevoNombre}
            onChange={(event) => setNuevoNombre(event.target.value)}
            style={{ ...inputStyle, flex: 1 }}
            maxLength={80}
          />
          <input
            type="number"
            min="0"
            step="0.01"
            placeholder="Tarifa en $"
            value={nuevaTarifa}
            onChange={(event) => setNuevaTarifa(event.target.value)}
            style={{ ...inputStyle, maxWidth: 160 }}
          />
          <button type="submit" disabled={saving} style={primaryButtonStyle}>
            Agregar
          </button>
        </form>
      </section>
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const titleStyle = (isMobile) => ({ margin: 0, color: 'var(--vg-text-strong)', fontSize: isMobile ? 28 : 34 });
const hintStyle = { margin: '8px 0 0', color: 'var(--vg-f-d2c3c3)', maxWidth: 680, lineHeight: 1.6 };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)' };
const sectionTitleStyle = { color: 'var(--vg-text-strong)', fontSize: 19, fontWeight: 700 };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(var(--vg-ink), 0.12)', color: 'var(--vg-f-c8bbbb)' };
const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(180px,1.2fr) minmax(140px,0.7fr) minmax(160px,0.9fr) minmax(240px,1.1fr)', minWidth: 760, border: '1px solid rgba(var(--vg-ink), 0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(var(--vg-ink), 0.06)', color: 'var(--vg-f-ffb0b0)', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '14px', borderTop: '1px solid rgba(var(--vg-ink), 0.08)', color: 'var(--vg-f-f2e6e6)', display: 'grid', alignContent: 'center', gap: 4 };
const cellActionsStyle = { ...cellStyle, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' };
const avisoStyle = { color: 'var(--vg-f-ffcf7d)', fontSize: 12 };
const formRowStyle = (isMobile) => ({ display: 'flex', gap: 12, flexWrap: 'wrap', flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'stretch' : 'center' });
const inputStyle = { borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-161010)', padding: '10px 12px', color: 'var(--vg-text-strong)', width: '100%', boxSizing: 'border-box' };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, var(--vg-accent-primary) 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const disabledButtonStyle = { ...primaryButtonStyle, opacity: 0.4, cursor: 'default' };
const secondaryButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(var(--vg-ink), 0.04)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer', width: 'fit-content' };
const dangerButtonStyle = { border: '1px solid var(--vg-f-ff7e7e-a400)', borderRadius: 999, padding: '10px 16px', background: 'rgba(145,33,33,0.25)', color: 'var(--vg-f-ffd3d3)', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default AnalystZonasDeliveryPage;

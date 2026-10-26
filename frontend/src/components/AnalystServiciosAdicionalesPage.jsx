import { Fragment, useEffect, useState } from 'react';
import Toast from './Toast';
import useToast from '../hooks/useToast';

// Catálogo de servicios adicionales (descorche, decoración, torta de cumpleaños...): lo que se le cobra al cliente
// junto con su pedido y no es un plato. Sin IVA y sin costo: lo cobrado es una entrada neta. Los crea y edita el
// administrador o el contador; cualquier rol puede agregarlos a un pedido. Cambiar un precio aquí no toca los
// pedidos ya registrados, y un servicio no se borra: se desactiva.
function getCookie(name) {
  const partes = `; ${document.cookie}`.split(`; ${name}=`);
  return partes.length === 2 ? partes.pop().split(';').shift() : '';
}

function AnalystServiciosAdicionalesPage({ isMobile, onBack }) {
  const [servicios, setServicios] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  // Lo que se está escribiendo en cada fila: { [id]: { nombre, precio, descripcion } }
  const [borradores, setBorradores] = useState({});
  const [nuevo, setNuevo] = useState({ nombre: '', precio: '', descripcion: '' });
  const { toast, showSuccess, showError, hideToast } = useToast();

  const llamar = async (url, cuerpo) => {
    const response = await fetch(url, {
      method: cuerpo ? 'POST' : 'GET',
      credentials: 'include',
      cache: 'no-store',
      headers: cuerpo ? { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') || '' } : undefined,
      body: cuerpo ? JSON.stringify(cuerpo) : undefined,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) throw new Error(data.message || 'No se pudo completar la operación.');
    return data;
  };

  const cargar = async () => {
    setLoading(true);
    try {
      const data = await llamar('/api/servicios-adicionales/?todos=1');
      setServicios(Array.isArray(data.servicios) ? data.servicios : []);
      setBorradores({});
    } catch (error) {
      showError(error.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    cargar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const enviar = async (url, cuerpo, mensajeOk) => {
    setSaving(true);
    try {
      const data = await llamar(url, cuerpo);
      showSuccess(mensajeOk || data.message || 'Listo.');
      await cargar();
      return true;
    } catch (error) {
      showError(error.message);
      return false;
    } finally {
      setSaving(false);
    }
  };

  const valorFila = (s) => borradores[s.id] || { nombre: s.nombre, precio: s.precio, descripcion: s.descripcion };
  const cambiarFila = (s, campo, valor) => setBorradores((actual) => ({ ...actual, [s.id]: { ...valorFila(s), [campo]: valor } }));
  const filaModificada = (s) => {
    const v = borradores[s.id];
    return Boolean(v) && (v.nombre.trim() !== s.nombre || Number(v.precio) !== Number(s.precio) || v.descripcion.trim() !== s.descripcion);
  };
  const precioValido = (valor) => valor !== '' && !Number.isNaN(Number(valor)) && Number(valor) >= 0;

  const guardarFila = (s) => {
    const v = valorFila(s);
    if (!v.nombre.trim()) { showError('El servicio necesita un nombre.'); return; }
    if (!precioValido(v.precio)) { showError('Escribe un precio válido (0 o más).'); return; }
    enviar(`/api/servicios-adicionales/${s.id}/`, { nombre: v.nombre.trim(), precio: v.precio, descripcion: v.descripcion.trim() }, 'Servicio actualizado.');
  };

  const crear = async (event) => {
    event.preventDefault();
    if (!nuevo.nombre.trim()) { showError('Escribe el nombre del servicio.'); return; }
    if (!precioValido(nuevo.precio)) { showError('Escribe un precio válido (0 o más).'); return; }
    const creado = await enviar(
      '/api/servicios-adicionales/', { nombre: nuevo.nombre.trim(), precio: nuevo.precio, descripcion: nuevo.descripcion.trim() }, 'Servicio creado.',
    );
    if (creado) setNuevo({ nombre: '', precio: '', descripcion: '' });
  };

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>← Volver al panel</button>

      <div>
        <h2 style={titleStyle(isMobile)}>Servicios adicionales</h2>
        <p style={hintStyle}>
          Se cobran junto con el pedido, sin IVA y sin costo: todo lo cobrado es ganancia. El precio siempre es el de esta lista
          y cambiarlo no modifica los pedidos ya registrados.
        </p>
      </div>

      <Toast toast={toast} onClose={hideToast} />

      <section style={panelStyle}>
        <div style={sectionTitleStyle}>Servicios</div>
        {loading ? <div style={emptyStyle}>Cargando...</div> : null}
        {!loading && servicios.length === 0 ? <div style={emptyStyle}>Aún no hay servicios adicionales. Agrega el primero abajo.</div> : null}
        {!loading && servicios.length > 0 ? (
          <div style={tableWrapStyle}>
            <div style={tableStyle}>
              <div style={headStyle}>Servicio</div>
              <div style={headStyle}>Precio ($)</div>
              <div style={headStyle}>Estado</div>
              <div style={headStyle}>Acciones</div>
              {servicios.map((s) => {
                const v = valorFila(s);
                return (
                  <Fragment key={s.id}>
                    <div style={cellStyle}>
                      <input type="text" value={v.nombre} onChange={(e) => cambiarFila(s, 'nombre', e.target.value)} style={inputStyle} maxLength={120} />
                      <input
                        type="text" value={v.descripcion} onChange={(e) => cambiarFila(s, 'descripcion', e.target.value)}
                        style={{ ...inputStyle, fontSize: 12.5 }} maxLength={255} placeholder="Descripción (opcional)"
                      />
                    </div>
                    <div style={cellStyle}>
                      <input
                        type="number" min="0" step="0.01" value={v.precio} onChange={(e) => cambiarFila(s, 'precio', e.target.value)}
                        style={{ ...inputStyle, maxWidth: 140 }}
                      />
                    </div>
                    <div style={cellStyle}>{s.activo ? 'Activo' : 'Inactivo'}</div>
                    <div style={cellActionsStyle}>
                      <button
                        type="button" disabled={saving || !filaModificada(s)} onClick={() => guardarFila(s)}
                        style={filaModificada(s) ? primaryButtonStyle : disabledButtonStyle}
                      >
                        Guardar
                      </button>
                      <button
                        type="button" disabled={saving}
                        onClick={() => enviar(`/api/servicios-adicionales/${s.id}/`, { activo: !s.activo }, s.activo ? 'Servicio desactivado.' : 'Servicio activado.')}
                        style={s.activo ? dangerButtonStyle : secondaryButtonStyle}
                      >
                        {s.activo ? 'Desactivar' : 'Activar'}
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
        <div style={sectionTitleStyle}>Agregar servicio</div>
        <form onSubmit={crear} style={formRowStyle(isMobile)}>
          <input
            type="text" placeholder="Nombre (ej. Descorche)" value={nuevo.nombre}
            onChange={(e) => setNuevo({ ...nuevo, nombre: e.target.value })} style={{ ...inputStyle, flex: 1 }} maxLength={120}
          />
          <input
            type="number" min="0" step="0.01" placeholder="Precio en $" value={nuevo.precio}
            onChange={(e) => setNuevo({ ...nuevo, precio: e.target.value })} style={{ ...inputStyle, maxWidth: 160 }}
          />
          <input
            type="text" placeholder="Descripción (opcional)" value={nuevo.descripcion}
            onChange={(e) => setNuevo({ ...nuevo, descripcion: e.target.value })} style={{ ...inputStyle, flex: 1 }} maxLength={255}
          />
          <button type="submit" disabled={saving} style={primaryButtonStyle}>Agregar</button>
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
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(220px,1.4fr) minmax(130px,0.6fr) minmax(100px,0.5fr) minmax(240px,1.1fr)', minWidth: 760, border: '1px solid rgba(var(--vg-ink), 0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(var(--vg-ink), 0.06)', color: 'var(--vg-f-ffb0b0)', fontSize: 12, fontWeight: 800 };
const cellStyle = { padding: '14px', borderTop: '1px solid rgba(var(--vg-ink), 0.08)', color: 'var(--vg-f-f2e6e6)', display: 'grid', alignContent: 'center', gap: 6 };
const cellActionsStyle = { ...cellStyle, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' };
const formRowStyle = (isMobile) => ({ display: 'flex', gap: 12, flexWrap: 'wrap', flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'stretch' : 'center' });
const inputStyle = { borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-161010)', padding: '10px 12px', color: 'var(--vg-text-strong)', width: '100%', boxSizing: 'border-box' };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, var(--vg-accent-primary) 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const disabledButtonStyle = { ...primaryButtonStyle, opacity: 0.4, cursor: 'default' };
const secondaryButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(var(--vg-ink), 0.04)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer', width: 'fit-content' };
const dangerButtonStyle = { border: '1px solid var(--vg-f-ff7e7e-a400)', borderRadius: 999, padding: '10px 16px', background: 'rgba(145,33,33,0.25)', color: 'var(--vg-f-ffd3d3)', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default AnalystServiciosAdicionalesPage;

import { Fragment, useEffect, useState } from 'react';
import UnsavedChangesModal from './UnsavedChangesModal';
import Toast from './Toast';
import useUnsavedChangesGuard from '../hooks/useUnsavedChangesGuard';
import useToast from '../hooks/useToast';

function AnalystPaymentMethodsPage({ isMobile, onBack }) {
  const [metodos, setMetodos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const { toast, showSuccess, showError, hideToast } = useToast();
  const [nombre, setNombre] = useState('');
  const [moneda, setMoneda] = useState('USD');
  const [esEfectivo, setEsEfectivo] = useState(false);
  const [cuentaBancaria, setCuentaBancaria] = useState('');
  const [editandoBancoId, setEditandoBancoId] = useState(null);
  const [bancoEnEdicion, setBancoEnEdicion] = useState('');
  const { guard, isConfirmOpen, confirmLeave, cancelLeave, markClean } = useUnsavedChangesGuard({ nombre, moneda, esEfectivo, cuentaBancaria });

  const loadMetodos = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/admin/metodos-pago/', { credentials: 'include', cache: 'no-store' });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudieron cargar los metodos de pago.');
      }
      setMetodos(Array.isArray(data.metodos_pago) ? data.metodos_pago : []);
    } catch (error) {
      showError(error.message || 'No se pudieron cargar los metodos de pago.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMetodos();
  }, []);

  const handleCreate = async (event) => {
    event.preventDefault();
    if (!nombre.trim()) {
      showError('Escribe un nombre para el metodo de pago.');
      return;
    }

    setSaving(true);
    try {
      const response = await fetch('/api/admin/metodos-pago/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'create',
          nombre: nombre.trim(),
          moneda,
          es_efectivo: esEfectivo,
          cuenta_bancaria: cuentaBancaria.trim(),
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo crear el metodo de pago.');
      }
      setNombre('');
      setMoneda('USD');
      setEsEfectivo(false);
      setCuentaBancaria('');
      markClean({ nombre: '', moneda: 'USD', esEfectivo: false, cuentaBancaria: '' });
      showSuccess(data.message || 'Metodo de pago creado.');
      loadMetodos();
    } catch (error) {
      showError(error.message || 'No se pudo crear el metodo de pago.');
    } finally {
      setSaving(false);
    }
  };

  const handleGuardarBanco = async (metodo) => {
    setSaving(true);
    try {
      const response = await fetch('/api/admin/metodos-pago/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'actualizar_cuenta_bancaria',
          id: metodo.id,
          cuenta_bancaria: bancoEnEdicion.trim(),
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo actualizar el banco.');
      }
      setEditandoBancoId(null);
      showSuccess(data.message || 'Banco actualizado.');
      loadMetodos();
    } catch (error) {
      showError(error.message || 'No se pudo actualizar el banco.');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleActivo = async (metodo) => {
    setSaving(true);
    try {
      const response = await fetch('/api/admin/metodos-pago/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'toggle_activo', id: metodo.id }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo actualizar el metodo de pago.');
      }
      loadMetodos();
    } catch (error) {
      showError(error.message || 'No se pudo actualizar el metodo de pago.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={() => guard(onBack)} style={backButtonStyle}>
        ← Volver al panel
      </button>

      <div>
        <h2 style={titleStyle(isMobile)}>Metodos de pago</h2>
        <p style={subtitleStyle}>Agrega los tipos de pago que se pueden usar al cobrar (efectivo, tarjeta, Binance, Zelle, etc.).</p>
      </div>

      <Toast toast={toast} onClose={hideToast} />

      <section style={panelStyle}>
        <div style={sectionTitleStyle}>Agregar metodo de pago</div>
        <form onSubmit={handleCreate} style={formRowStyle(isMobile)}>
          <input
            type="text"
            placeholder="Nombre (ej. Binance)"
            value={nombre}
            onChange={(event) => setNombre(event.target.value)}
            style={{ ...inputStyle, flex: 1 }}
          />
          <select value={moneda} onChange={(event) => setMoneda(event.target.value)} style={inputStyle}>
            <option value="USD">Dólares (USD)</option>
            <option value="VES">Bolívares (VES)</option>
          </select>
          <input
            type="text"
            placeholder="Banco (ej. Banesco)"
            value={cuentaBancaria}
            onChange={(event) => setCuentaBancaria(event.target.value)}
            style={{ ...inputStyle, flex: 1 }}
          />
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#f2e6e6' }}>
            <input type="checkbox" checked={esEfectivo} onChange={(event) => setEsEfectivo(event.target.checked)} />
            Cuenta como efectivo fisico
          </label>
          <button type="submit" disabled={saving} style={primaryButtonStyle}>
            Agregar
          </button>
        </form>
        <p style={hintStyle}>
          El banco es opcional: escribe el mismo nombre de banco (ej. "Banesco") en dos métodos distintos —como Pago Móvil y Punto de Venta— para que Disponibilidad Bancaria los muestre agrupados bajo esa cuenta.
        </p>
      </section>

      <section style={panelStyle}>
        <div style={sectionTitleStyle}>Metodos existentes</div>
        {loading ? <div style={emptyStyle}>Cargando...</div> : null}
        {!loading && metodos.length === 0 ? <div style={emptyStyle}>Aun no hay metodos de pago.</div> : null}
        {!loading && metodos.length > 0 ? (
          <div style={tableWrapStyle}>
            <div style={tableStyle}>
              <div style={headStyle}>Nombre</div>
              <div style={headStyle}>Moneda</div>
              <div style={headStyle}>Banco</div>
              <div style={headStyle}>Efectivo</div>
              <div style={headStyle}>Estado</div>
              <div style={headStyle}>Acciones</div>
              {metodos.map((metodo) => (
                <Fragment key={metodo.id}>
                  <div style={cellStyle}>{metodo.nombre}</div>
                  <div style={cellStyle}>{metodo.moneda === 'VES' ? 'Bolívares' : 'Dólares'}</div>
                  <div style={cellStyle}>
                    {editandoBancoId === metodo.id ? (
                      <div style={{ display: 'flex', gap: 6 }}>
                        <input
                          type="text"
                          autoFocus
                          value={bancoEnEdicion}
                          onChange={(event) => setBancoEnEdicion(event.target.value)}
                          style={{ ...inputStyle, padding: '6px 8px', width: 110 }}
                        />
                        <button type="button" disabled={saving} onClick={() => handleGuardarBanco(metodo)} style={secondaryButtonStyle}>
                          Guardar
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => {
                          setEditandoBancoId(metodo.id);
                          setBancoEnEdicion(metodo.cuenta_bancaria || '');
                        }}
                        style={bancoButtonStyle}
                      >
                        {metodo.cuenta_bancaria || 'Sin banco — asignar'}
                      </button>
                    )}
                  </div>
                  <div style={cellStyle}>{metodo.es_efectivo ? 'Si' : 'No'}</div>
                  <div style={cellStyle}>{metodo.activo ? 'Activo' : 'Inactivo'}</div>
                  <div style={cellActionsStyle}>
                    <button
                      type="button"
                      onClick={() => handleToggleActivo(metodo)}
                      disabled={saving}
                      style={metodo.activo ? dangerButtonStyle : secondaryButtonStyle}
                    >
                      {metodo.activo ? 'Desactivar' : 'Activar'}
                    </button>
                  </div>
                </Fragment>
              ))}
            </div>
          </div>
        ) : null}
      </section>

      <UnsavedChangesModal open={isConfirmOpen} onConfirm={confirmLeave} onCancel={cancelLeave} />
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: '#d2c3c3' };
const hintStyle = { margin: 0, color: '#a89999', fontSize: 13 };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const sectionTitleStyle = { color: '#fff', fontSize: 19, fontWeight: 700 };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(160px,1fr) minmax(110px,0.6fr) minmax(150px,0.8fr) minmax(100px,0.6fr) minmax(100px,0.6fr) minmax(160px,1fr)', minWidth: 850, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const bancoButtonStyle = { border: '1px dashed rgba(255,255,255,0.25)', borderRadius: 10, padding: '6px 10px', background: 'transparent', color: '#f2e6e6', cursor: 'pointer', fontSize: 13, textAlign: 'left' };
const headStyle = { padding: '12px 14px', background: 'rgba(255,255,255,0.06)', color: '#ffb0b0', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '14px', borderTop: '1px solid rgba(255,255,255,0.08)', color: '#f2e6e6', display: 'grid', alignContent: 'center' };
const cellActionsStyle = { ...cellStyle, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' };
const formRowStyle = (isMobile) => ({ display: 'flex', gap: 12, flexWrap: 'wrap', flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'stretch' : 'center' });
const inputStyle = { borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff' };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const secondaryButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer', width: 'fit-content' };
const dangerButtonStyle = { border: '1px solid rgba(255,126,126,0.4)', borderRadius: 999, padding: '10px 16px', background: 'rgba(145,33,33,0.25)', color: '#ffd3d3', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default AnalystPaymentMethodsPage;

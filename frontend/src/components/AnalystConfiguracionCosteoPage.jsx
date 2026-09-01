import { useEffect, useState } from 'react';
import Toast from './Toast';
import useToast from '../hooks/useToast';

function AnalystConfiguracionCosteoPage({ isMobile, onBack }) {
  const [rendimiento, setRendimiento] = useState('0');
  const [margenDefecto, setMargenDefecto] = useState('50');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const { toast, showSuccess, showError, hideToast } = useToast();

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/admin/configuracion-costeo/', { credentials: 'include', cache: 'no-store' });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || 'No se pudo cargar la configuración de costeo.');
        }
        setRendimiento(data.rendimiento_receta_pct);
        setMargenDefecto(data.margen_ganancia_defecto_pct);
      } catch (error) {
        showError(error.message || 'No se pudo cargar la configuración de costeo.');
      } finally {
        setLoading(false);
      }
    };
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSave = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      const response = await fetch('/api/admin/configuracion-costeo/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          rendimiento_receta_pct: rendimiento,
          margen_ganancia_defecto_pct: margenDefecto,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo guardar la configuración.');
      }
      setRendimiento(data.rendimiento_receta_pct);
      setMargenDefecto(data.margen_ganancia_defecto_pct);
      showSuccess(data.message || 'Configuración guardada.');
    } catch (error) {
      showError(error.message || 'No se pudo guardar la configuración.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <section style={containerStyle(isMobile)}>
      <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          ← Volver al panel analista
        </button>
      </div>

      <div>
        <h2 style={titleStyle(isMobile)}>Configuración de costeo</h2>
        <p style={subtitleStyle}>
          Estos dos porcentajes son globales: cambiarlos afecta a todas las recetas y a los productos
          nuevos que no tengan su propio margen definido.
        </p>
      </div>

      <Toast toast={toast} onClose={hideToast} />

      {loading ? (
        <div style={emptyStyle}>Cargando configuración...</div>
      ) : (
        <form onSubmit={handleSave} style={panelStyle}>
          <label style={fieldStyle}>
            <span style={labelStyle}>% de rendimiento por costo (recetas)</span>
            <input
              type="number"
              min="0"
              step="0.01"
              value={rendimiento}
              onChange={(event) => setRendimiento(event.target.value)}
              style={inputStyle}
              required
            />
            <p style={hintStyle}>
              Se suma al costo de ingredientes de CADA receta de producto, para compensar mermas de cocina
              (ej: una carne que pierde peso al cocinarse). No aplica a subrecetas — solo a recetas.
            </p>
          </label>

          <label style={fieldStyle}>
            <span style={labelStyle}>% de margen de ganancia por defecto</span>
            <input
              type="number"
              min="0"
              step="0.01"
              value={margenDefecto}
              onChange={(event) => setMargenDefecto(event.target.value)}
              style={inputStyle}
              required
            />
            <p style={hintStyle}>
              Se usa para sugerir el precio de venta de un producto nuevo (costo con rendimiento x este
              margen), a menos que ese producto defina su propio margen en su ficha.
            </p>
          </label>

          <button type="submit" disabled={saving} style={saveButtonStyle}>
            {saving ? 'Guardando...' : 'Guardar configuración'}
          </button>
        </form>
      )}
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10, maxWidth: 640 });
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: '#d2c3c3', maxWidth: 560, lineHeight: 1.6 };
const panelStyle = { display: 'grid', gap: 18, padding: 22, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const fieldStyle = { display: 'grid', gap: 6 };
const labelStyle = { color: '#f2e6e6', fontSize: 13.5, fontWeight: 700 };
const inputStyle = { borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff', fontSize: 15 };
const hintStyle = { margin: 0, color: '#a99', fontSize: 12.5, lineHeight: 1.5 };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const saveButtonStyle = { justifySelf: 'start', border: 'none', borderRadius: 999, padding: '11px 22px', background: 'linear-gradient(90deg, #d81d1d 0%, #ff5252 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default AnalystConfiguracionCosteoPage;

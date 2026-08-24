import { useEffect, useState } from 'react';

const emptyForm = {
  rif: '',
  razon_social: '',
  nombre_comercial: '',
  domicilio_fiscal: '',
  telefono: '',
  porcentaje_iva_default: '16.00',
};

function AnalystDatosFiscalesPage({ isMobile, onBack }) {
  const [form, setForm] = useState(emptyForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  const loadDatos = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/admin/datos-fiscales/', { credentials: 'include', cache: 'no-store' });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudieron cargar los datos fiscales.');
      }
      if (data.datos_fiscales) {
        setForm({ ...emptyForm, ...data.datos_fiscales });
      }
    } catch (error) {
      setMessage(error.message || 'No se pudieron cargar los datos fiscales.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDatos();
  }, []);

  const handleChange = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setMessage('');
    try {
      const response = await fetch('/api/admin/datos-fiscales/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudieron guardar los datos fiscales.');
      }
      setMessage(data.message || 'Datos fiscales guardados correctamente.');
      if (data.datos_fiscales) {
        setForm({ ...emptyForm, ...data.datos_fiscales });
      }
    } catch (error) {
      setMessage(error.message || 'No se pudieron guardar los datos fiscales.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>
        ← Volver al panel
      </button>

      <div>
        <h2 style={titleStyle(isMobile)}>Datos fiscales del negocio</h2>
        <p style={subtitleStyle}>
          Esta información se usa en el encabezado de cada factura (RIF, razón social, domicilio) y como
          porcentaje de IVA por defecto al facturar.
        </p>
      </div>

      {message ? <div style={noticeStyle}>{message}</div> : null}

      <section style={panelStyle}>
        {loading ? (
          <div style={emptyStyle}>Cargando...</div>
        ) : (
          <form onSubmit={handleSubmit} style={formGridStyle(isMobile)}>
            <label style={fieldStyle}>
              <span style={labelStyle}>RIF</span>
              <input
                value={form.rif}
                onChange={(event) => handleChange('rif', event.target.value)}
                style={inputStyle}
                placeholder="J-12345678-9"
                required
              />
            </label>

            <label style={fieldStyle}>
              <span style={labelStyle}>Razón social</span>
              <input
                value={form.razon_social}
                onChange={(event) => handleChange('razon_social', event.target.value)}
                style={inputStyle}
                placeholder="Vara Grill C.A."
                required
              />
            </label>

            <label style={fieldStyle}>
              <span style={labelStyle}>Nombre comercial</span>
              <input
                value={form.nombre_comercial}
                onChange={(event) => handleChange('nombre_comercial', event.target.value)}
                style={inputStyle}
                placeholder="Vara Grill"
              />
            </label>

            <label style={fieldStyle}>
              <span style={labelStyle}>Teléfono</span>
              <input
                value={form.telefono}
                onChange={(event) => handleChange('telefono', event.target.value)}
                style={inputStyle}
              />
            </label>

            <label style={{ ...fieldStyle, gridColumn: isMobile ? 'auto' : '1 / -1' }}>
              <span style={labelStyle}>Domicilio fiscal</span>
              <input
                value={form.domicilio_fiscal}
                onChange={(event) => handleChange('domicilio_fiscal', event.target.value)}
                style={inputStyle}
              />
            </label>

            <label style={fieldStyle}>
              <span style={labelStyle}>IVA por defecto (%)</span>
              <input
                type="number"
                min="0"
                max="100"
                step="0.01"
                value={form.porcentaje_iva_default}
                onChange={(event) => handleChange('porcentaje_iva_default', event.target.value)}
                style={inputStyle}
              />
            </label>

            <div style={{ display: 'flex', gap: 10, gridColumn: isMobile ? 'auto' : '1 / -1' }}>
              <button type="submit" disabled={saving} style={primaryButtonStyle}>
                {saving ? 'Guardando...' : 'Guardar datos fiscales'}
              </button>
            </div>
          </form>
        )}
      </section>
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: '#d2c3c3', maxWidth: 640, lineHeight: 1.6 };
const panelStyle = {
  display: 'grid',
  gap: 14,
  padding: 18,
  borderRadius: 20,
  border: '1px solid rgba(255,255,255,0.1)',
  background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)',
};
const emptyStyle = {
  minHeight: 80,
  display: 'grid',
  placeItems: 'center',
  borderRadius: 14,
  border: '1px dashed rgba(255,255,255,0.12)',
  color: '#c8bbbb',
};
const formGridStyle = (isMobile) => ({
  display: 'grid',
  gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 1fr))',
  gap: 12,
});
const fieldStyle = { display: 'grid', gap: 6 };
const labelStyle = { color: '#f0b4b4', fontSize: 13, fontWeight: 700 };
const inputStyle = {
  width: '100%',
  boxSizing: 'border-box',
  borderRadius: 12,
  border: '1px solid rgba(255,255,255,0.14)',
  background: '#161010',
  padding: '10px 12px',
  color: '#fff',
};
const noticeStyle = {
  padding: '12px 14px',
  borderRadius: 12,
  border: '1px solid rgba(255,145,145,0.22)',
  background: 'rgba(255,98,98,0.12)',
  color: '#ffd8d8',
};
const primaryButtonStyle = {
  border: 'none',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
};
const backButtonStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  width: 'fit-content',
  border: 'none',
  borderRadius: 999,
  padding: '11px 18px',
  background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
  boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)',
};

export default AnalystDatosFiscalesPage;

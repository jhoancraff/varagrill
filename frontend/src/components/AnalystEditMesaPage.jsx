import { useEffect, useState } from 'react';

const emptyForm = {
  id: null,
  numero: '',
  capacidad: '4',
  ubicacion: '',
  estado: 'libre',
};

const estadoOptions = [
  { value: 'libre', label: 'Libre' },
  { value: 'ocupada', label: 'Ocupada' },
  { value: 'reservada', label: 'Reservada' },
  { value: 'mantenimiento', label: 'Mantenimiento' },
];

function AnalystEditMesaPage({ isMobile, isAdmin, mesaId, onBack, onMesasChanged }) {
  const [form, setForm] = useState(emptyForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (!isAdmin) {
      setLoading(false);
      return;
    }

    const loadMesa = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/admin/mesas/', {
          credentials: 'include',
          cache: 'no-store',
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || 'No se pudo cargar la mesa.');
        }

        const selectedMesa = (data.mesas || []).find((entry) => String(entry.id) === String(mesaId));
        if (!selectedMesa) {
          throw new Error('La mesa seleccionada no existe.');
        }

        setForm({
          id: selectedMesa.id,
          numero: String(selectedMesa.numero ?? ''),
          capacidad: String(selectedMesa.capacidad ?? '4'),
          ubicacion: selectedMesa.ubicacion || '',
          estado: selectedMesa.estado || 'libre',
        });
      } catch (error) {
        setMessage(error.message || 'No se pudo cargar la mesa.');
      } finally {
        setLoading(false);
      }
    };

    loadMesa();
  }, [isAdmin, mesaId]);

  const handleChange = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      const response = await fetch('/api/admin/mesas/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'update',
          id: form.id,
          numero: form.numero,
          capacidad: form.capacidad,
          ubicacion: form.ubicacion,
          estado: form.estado,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo actualizar la mesa.');
      }

      setMessage(data.message || 'Mesa actualizada correctamente.');
      if (onMesasChanged) {
        onMesasChanged();
      }
    } catch (error) {
      setMessage(error.message || 'No se pudo actualizar la mesa.');
    } finally {
      setSaving(false);
    }
  };

  if (!isAdmin) {
    return (
      <section style={containerStyle(isMobile)}>
        <div style={badgeStyle}>Editar mesa</div>
        <h2 style={titleStyle(isMobile)}>Acceso restringido</h2>
        <div style={noticeStyle}>Solo el rol Administrador puede modificar mesas.</div>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          Volver al reporte
        </button>
      </section>
    );
  }

  return (
    <section style={containerStyle(isMobile)}>
      <div style={badgeStyle}>Editar mesa</div>
      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Actualización de mesa</h2>
          <p style={subtitleStyle}>Modifica número, capacidad, ubicación y estado de la mesa.</p>
        </div>
      </div>

      {message ? <div style={noticeStyle}>{message}</div> : null}

      <form onSubmit={handleSubmit} style={panelStyle}>
        {loading ? <div style={emptyStateStyle}>Cargando mesa...</div> : null}
        {!loading ? (
          <>
            <div style={formGridStyle(isMobile)}>
              <label style={fieldStyle}>
                <span style={labelStyle}>Número de mesa</span>
                <input type="number" min="1" value={form.numero} onChange={(event) => handleChange('numero', event.target.value)} style={inputStyle} />
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Capacidad (personas)</span>
                <input type="number" min="1" value={form.capacidad} onChange={(event) => handleChange('capacidad', event.target.value)} style={inputStyle} />
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Ubicación</span>
                <input value={form.ubicacion} onChange={(event) => handleChange('ubicacion', event.target.value)} placeholder="Ej. Terraza, Salón principal" style={inputStyle} />
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Estado</span>
                <select value={form.estado} onChange={(event) => handleChange('estado', event.target.value)} style={inputStyle}>
                  {estadoOptions.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>
            </div>

            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <button type="submit" style={primaryButtonStyle} disabled={saving}>
                {saving ? 'Guardando...' : 'Guardar cambios'}
              </button>
              <button type="button" onClick={onBack} style={secondaryButtonStyle}>
                Volver al reporte
              </button>
            </div>
          </>
        ) : null}
      </form>
    </section>
  );
}

const containerStyle = (isMobile) => ({
  display: 'grid',
  gap: 18,
  padding: isMobile ? 6 : 10,
});

const badgeStyle = {
  display: 'inline-flex',
  width: 'fit-content',
  padding: '7px 12px',
  borderRadius: 999,
  background: 'rgba(255, 163, 163, 0.12)',
  color: '#ffb5b5',
  fontSize: 12,
  fontWeight: 800,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
};

const titleStyle = (isMobile) => ({
  margin: 0,
  color: '#fff',
  fontSize: isMobile ? 28 : 34,
});

const subtitleStyle = {
  margin: '8px 0 0',
  color: '#d2c3c3',
  lineHeight: 1.6,
  maxWidth: 720,
};

const headerRowStyle = (isMobile) => ({
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: isMobile ? 'flex-start' : 'center',
  gap: 14,
  flexDirection: isMobile ? 'column' : 'row',
});

const panelStyle = {
  display: 'grid',
  gap: 16,
  padding: '20px 18px',
  borderRadius: 24,
  border: '1px solid rgba(255, 255, 255, 0.1)',
  background: 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)',
};

const emptyStateStyle = {
  minHeight: 80,
  display: 'grid',
  placeItems: 'center',
  borderRadius: 18,
  border: '1px dashed rgba(255, 255, 255, 0.12)',
  color: '#c8bbbb',
};

const formGridStyle = (isMobile) => ({
  display: 'grid',
  gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 1fr))',
  gap: 12,
});

const fieldStyle = {
  display: 'grid',
  gap: 6,
};

const labelStyle = {
  color: '#f0b4b4',
  fontSize: 13,
  fontWeight: 700,
};

const inputStyle = {
  width: '100%',
  boxSizing: 'border-box',
  borderRadius: 14,
  border: '1px solid rgba(255, 255, 255, 0.14)',
  background: 'rgba(255, 255, 255, 0.04)',
  padding: '11px 12px',
  color: '#fff',
  fontSize: 14,
};

const noticeStyle = {
  padding: '12px 14px',
  borderRadius: 16,
  border: '1px solid rgba(255, 145, 145, 0.22)',
  background: 'rgba(255, 98, 98, 0.12)',
  color: '#ffd8d8',
};

const primaryButtonStyle = {
  border: 'none',
  borderRadius: 999,
  padding: '11px 18px',
  background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
};

const secondaryButtonStyle = {
  border: '1px solid rgba(255, 255, 255, 0.14)',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'rgba(255, 255, 255, 0.04)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
};

const backButtonStyle = {
  justifySelf: 'flex-start',
  border: '1px solid rgba(255, 255, 255, 0.14)',
  borderRadius: 999,
  padding: '11px 18px',
  background: 'rgba(255, 255, 255, 0.04)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
};

export default AnalystEditMesaPage;

import { useEffect, useState } from 'react';
import UnsavedChangesModal from './UnsavedChangesModal';
import useUnsavedChangesGuard from '../hooks/useUnsavedChangesGuard';

const emptyForm = {
  username: '',
  password: '',
  first_name: '',
  last_name: '',
  email: '',
  cedula: '',
  telefono: '',
  fecha_nacimiento: '',
  role_id: '',
  is_active: true,
};

function AnalystNewUserPage({ isMobile, isAdmin, onBack }) {
  const [roles, setRoles] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const { guard, isConfirmOpen, confirmLeave, cancelLeave, markClean } = useUnsavedChangesGuard(form);

  useEffect(() => {
    if (!isAdmin) {
      setLoading(false);
      return;
    }

    const loadRoles = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/admin/usuarios/', {
          credentials: 'include',
          cache: 'no-store',
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || 'No se pudieron cargar los roles.');
        }
        setRoles(Array.isArray(data.roles) ? data.roles : []);
      } catch (error) {
        setMessage(error.message || 'No se pudieron cargar los roles.');
      } finally {
        setLoading(false);
      }
    };

    loadRoles();
  }, [isAdmin]);

  const handleChange = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      const response = await fetch('/api/admin/usuarios/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'create',
          username: form.username,
          password: form.password,
          first_name: form.first_name,
          last_name: form.last_name,
          email: form.email,
          cedula: form.cedula,
          telefono: form.telefono,
          fecha_nacimiento: form.fecha_nacimiento,
          role_id: form.role_id || null,
          is_active: form.is_active,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo crear el usuario.');
      }

      setMessage(data.message || 'Usuario creado correctamente.');
      setForm(emptyForm);
      markClean(emptyForm);
    } catch (error) {
      setMessage(error.message || 'No se pudo crear el usuario.');
    } finally {
      setSaving(false);
    }
  };

  if (!isAdmin) {
    return (
      <section style={containerStyle(isMobile)}>
        <div style={badgeStyle}>Nuevo usuario</div>
        <h2 style={titleStyle(isMobile)}>Acceso restringido</h2>
        <div style={noticeStyle}>Solo el rol Administrador puede crear usuarios.</div>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          Volver a usuarios
        </button>
      </section>
    );
  }

  return (
    <section style={containerStyle(isMobile)}>
      <div style={badgeStyle}>Nuevo usuario</div>
      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Crear usuario nuevo</h2>
          <p style={subtitleStyle}>Esta página contiene solo el formulario para registrar un nuevo usuario.</p>
        </div>
      </div>

      {message ? <div style={noticeStyle}>{message}</div> : null}

      <form onSubmit={handleSubmit} style={panelStyle}>
        {loading ? <div style={emptyStateStyle}>Cargando roles...</div> : null}
        {!loading ? (
          <>
            <div style={formGridStyle(isMobile)}>
              <label style={fieldStyle}>
                <span style={labelStyle}>Usuario</span>
                <input value={form.username} onChange={(event) => handleChange('username', event.target.value)} style={inputStyle} />
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Cédula</span>
                <input value={form.cedula} onChange={(event) => handleChange('cedula', event.target.value)} style={inputStyle} />
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Nombre</span>
                <input value={form.first_name} onChange={(event) => handleChange('first_name', event.target.value)} style={inputStyle} />
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Apellido</span>
                <input value={form.last_name} onChange={(event) => handleChange('last_name', event.target.value)} style={inputStyle} />
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Correo</span>
                <input type="email" value={form.email} onChange={(event) => handleChange('email', event.target.value)} style={inputStyle} />
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Teléfono</span>
                <input value={form.telefono} onChange={(event) => handleChange('telefono', event.target.value)} style={inputStyle} />
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Fecha de nacimiento</span>
                <input type="date" value={form.fecha_nacimiento} onChange={(event) => handleChange('fecha_nacimiento', event.target.value)} style={inputStyle} />
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Rol</span>
                <select value={form.role_id} onChange={(event) => handleChange('role_id', event.target.value)} style={inputStyle}>
                  <option value="">Selecciona un rol</option>
                  {roles.map((role) => (
                    <option key={role.id} value={role.id}>{role.nombre_role}</option>
                  ))}
                </select>
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Contraseña</span>
                <input type="password" value={form.password} onChange={(event) => handleChange('password', event.target.value)} style={inputStyle} />
              </label>
              <label style={toggleRowStyle}>
                <input type="checkbox" checked={form.is_active} onChange={(event) => handleChange('is_active', event.target.checked)} />
                <span>Usuario activo</span>
              </label>
            </div>

            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <button type="submit" style={primaryButtonStyle} disabled={saving}>
                {saving ? 'Guardando...' : 'Crear usuario'}
              </button>
              <button type="button" onClick={() => guard(onBack)} style={secondaryButtonStyle}>
                Volver a usuarios
              </button>
            </div>
          </>
        ) : null}
      </form>

      <UnsavedChangesModal open={isConfirmOpen} onConfirm={confirmLeave} onCancel={cancelLeave} />
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

const toggleRowStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 10,
  color: '#fff',
  fontWeight: 600,
  minHeight: 42,
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

export default AnalystNewUserPage;
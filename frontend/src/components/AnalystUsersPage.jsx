import { useEffect, useState } from 'react';
import Pagination from './Pagination';
import Toast from './Toast';
import useToast from '../hooks/useToast';

const PAGE_SIZE = 50;

function AnalystUsersPage({ isMobile, isAdmin, onBack, onCreateNewUser, onEditUser }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const { toast, showSuccess, showError, hideToast } = useToast();
  const [page, setPage] = useState(0);

  useEffect(() => {
    if (!isAdmin) {
      setLoading(false);
      return;
    }

    const loadUsers = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/admin/usuarios/', {
          credentials: 'include',
          cache: 'no-store',
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || 'No se pudo cargar la gestión de usuarios.');
        }
        setUsers(Array.isArray(data.users) ? data.users : []);
      } catch (error) {
        showError(error.message || 'No se pudo cargar la gestión de usuarios.');
      } finally {
        setLoading(false);
      }
    };

    loadUsers();
  }, [isAdmin]);

  const handleDelete = async (user) => {
    if (!window.confirm(`¿Deseas eliminar al usuario ${user.username}?`)) {
      return;
    }

    setSaving(true);
    try {
      const response = await fetch('/api/admin/usuarios/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'delete', id: user.id }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo eliminar el usuario.');
      }
      setUsers((current) => current.filter((entry) => entry.id !== user.id));
      showSuccess(data.message || 'Usuario eliminado correctamente.');
    } catch (error) {
      showError(error.message || 'No se pudo eliminar el usuario.');
    } finally {
      setSaving(false);
    }
  };

  if (!isAdmin) {
    return (
      <section style={containerStyle(isMobile)}>
        <div style={badgeStyle}>Usuarios</div>
        <h2 style={titleStyle(isMobile)}>Acceso restringido</h2>
        <div style={noticeStyle}>Solo el rol Administrador puede entrar a esta sección.</div>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          ← Volver al panel del analista
        </button>
      </section>
    );
  }

  const pageCount = Math.max(1, Math.ceil(users.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const pagedUsers = users.slice(currentPage * PAGE_SIZE, currentPage * PAGE_SIZE + PAGE_SIZE);

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>
        ← Volver al panel del analista
      </button>

      <div style={badgeStyle}>Usuarios</div>
      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Gestión de usuarios</h2>
          <p style={subtitleStyle}>Consulta los usuarios registrados, actualiza sus datos, cambia contraseñas y asigna roles.</p>
        </div>
        <button type="button" onClick={onCreateNewUser} style={primaryButtonStyle}>
          Agregar usuario nuevo
        </button>
      </div>

      <Toast toast={toast} onClose={hideToast} />

      <div style={summaryGridStyle(isMobile)}>
        <article style={summaryCardStyle}>
          <div style={summaryLabelStyle}>Usuarios totales</div>
          <div style={summaryValueStyle}>{users.length}</div>
        </article>
        <article style={summaryCardStyle}>
          <div style={summaryLabelStyle}>Activos</div>
          <div style={summaryValueStyle}>{users.filter((user) => user.is_active).length}</div>
        </article>
        <article style={summaryCardStyle}>
          <div style={summaryLabelStyle}>Administradores</div>
          <div style={summaryValueStyle}>{users.filter((user) => user.role?.nombre_role === 'Administrador').length}</div>
        </article>
        <article style={summaryCardStyle}>
          <div style={summaryLabelStyle}>Roles en uso</div>
          <div style={summaryValueStyle}>{new Set(users.map((user) => user.role?.nombre_role || 'Sin rol')).size}</div>
        </article>
      </div>

      <section style={panelStyle}>
        <div style={reportHeaderStyle(isMobile)}>
          <div style={sectionTitleStyle}>Reporte administrativo de usuarios</div>
          <div style={reportHintStyle}>Consulta estado, rol, identificación y acciones de control por cada cuenta.</div>
        </div>

        {loading ? <div style={emptyStateStyle}>Cargando usuarios...</div> : null}
        {!loading && users.length === 0 ? <div style={emptyStateStyle}>No hay usuarios registrados.</div> : null}

        {!loading && users.length > 0 ? (
          <div style={tableWrapStyle}>
            <div style={tableStyle}>
              <div style={tableHeadStyle}>Usuario</div>
              <div style={tableHeadStyle}>Perfil</div>
              <div style={tableHeadStyle}>Rol</div>
              <div style={tableHeadStyle}>Estado</div>
              <div style={tableHeadStyle}>Acciones</div>

              {pagedUsers.map((user) => (
                <>
                  <div key={`user-${user.id}`} style={tableCellPrimaryStyle}>
                    <div style={userNameStyle}>{user.username}</div>
                    <div style={userMetaStyle}>{user.email || 'Sin correo'}</div>
                  </div>
                  <div key={`profile-${user.id}`} style={tableCellStyle}>
                    <div>{[user.first_name, user.last_name].filter(Boolean).join(' ') || 'Sin nombre'}</div>
                    <div style={userMetaStyle}>{user.cedula || 'Sin cédula'}</div>
                  </div>
                  <div key={`role-${user.id}`} style={tableCellStyle}>
                    <span style={rolePillStyle}>{user.role?.nombre_role || 'Sin rol'}</span>
                  </div>
                  <div key={`status-${user.id}`} style={tableCellStyle}>
                    <span style={statusPillStyle(user.is_active)}>{user.is_active ? 'Activo' : 'Inactivo'}</span>
                  </div>
                  <div key={`actions-${user.id}`} style={tableCellActionStyle}>
                    <button type="button" onClick={() => onEditUser(user.id)} style={secondaryButtonStyle}>
                      Modificar
                    </button>
                    <button type="button" onClick={() => handleDelete(user)} style={dangerButtonStyle} disabled={saving}>
                      Eliminar
                    </button>
                  </div>
                </>
              ))}
            </div>
          </div>
        ) : null}

        <Pagination
          page={currentPage}
          pageCount={pageCount}
          totalCount={users.length}
          pageSize={PAGE_SIZE}
          isMobile={isMobile}
          onPrev={() => setPage((current) => Math.max(0, current - 1))}
          onNext={() => setPage((current) => Math.min(pageCount - 1, current + 1))}
        />
      </section>
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

const summaryGridStyle = (isMobile) => ({
  display: 'grid',
  gridTemplateColumns: isMobile ? 'repeat(2, minmax(0, 1fr))' : 'repeat(4, minmax(0, 1fr))',
  gap: 18,
});

const summaryCardStyle = {
  display: 'grid',
  gap: 10,
  padding: '18px 16px',
  borderRadius: 20,
  border: '1px solid rgba(255, 255, 255, 0.1)',
  background: 'linear-gradient(180deg, rgba(27, 10, 10, 0.96) 0%, rgba(10, 10, 10, 0.98) 100%)',
};

const summaryLabelStyle = {
  color: '#f0b1b1',
  fontSize: 12,
  fontWeight: 800,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
};

const summaryValueStyle = {
  color: '#fff',
  fontSize: 28,
  fontWeight: 800,
};

const panelStyle = {
  display: 'grid',
  gap: 16,
  padding: '20px 18px',
  borderRadius: 24,
  border: '1px solid rgba(255, 255, 255, 0.1)',
  background: 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)',
};

const sectionTitleStyle = {
  color: '#fff',
  fontSize: 20,
  fontWeight: 700,
};

const reportHeaderStyle = (isMobile) => ({
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: isMobile ? 'flex-start' : 'center',
  flexDirection: isMobile ? 'column' : 'row',
  gap: 10,
});

const reportHintStyle = {
  color: '#d2c4c4',
  fontSize: 13,
  maxWidth: 420,
};

const emptyStateStyle = {
  minHeight: 80,
  display: 'grid',
  placeItems: 'center',
  borderRadius: 18,
  border: '1px dashed rgba(255, 255, 255, 0.12)',
  color: '#c8bbbb',
};

const tableWrapStyle = {
  overflowX: 'auto',
};

const tableStyle = {
  display: 'grid',
  gridTemplateColumns: 'minmax(180px, 1.1fr) minmax(200px, 1.2fr) minmax(140px, 0.9fr) minmax(120px, 0.7fr) minmax(210px, 1fr)',
  alignItems: 'stretch',
  border: '1px solid rgba(255, 255, 255, 0.08)',
  borderRadius: 18,
  overflow: 'hidden',
  minWidth: 920,
};

const tableHeadStyle = {
  padding: '14px 16px',
  background: 'rgba(255, 255, 255, 0.06)',
  color: '#ffb0b0',
  fontSize: 12,
  fontWeight: 800,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
  borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
};

const tableCellStyle = {
  padding: '16px',
  borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
  color: '#f2e6e6',
  display: 'grid',
  alignContent: 'center',
  gap: 4,
};

const tableCellPrimaryStyle = {
  ...tableCellStyle,
  background: 'rgba(255, 255, 255, 0.02)',
};

const tableCellActionStyle = {
  ...tableCellStyle,
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  flexWrap: 'wrap',
};

const userNameStyle = {
  color: '#fff',
  fontWeight: 700,
  fontSize: 17,
};

const userMetaStyle = {
  color: '#d2c4c4',
  fontSize: 13,
};

const rolePillStyle = {
  display: 'inline-flex',
  width: 'fit-content',
  padding: '7px 11px',
  borderRadius: 999,
  background: 'rgba(255, 141, 141, 0.12)',
  border: '1px solid rgba(255, 141, 141, 0.2)',
  color: '#ffc5c5',
  fontWeight: 700,
  fontSize: 12,
};

const statusPillStyle = (isActive) => ({
  display: 'inline-flex',
  width: 'fit-content',
  padding: '7px 11px',
  borderRadius: 999,
  background: isActive ? 'rgba(94, 197, 135, 0.14)' : 'rgba(255, 145, 145, 0.12)',
  border: isActive ? '1px solid rgba(94, 197, 135, 0.22)' : '1px solid rgba(255, 145, 145, 0.22)',
  color: isActive ? '#c8ffe0' : '#ffd0d0',
  fontWeight: 700,
  fontSize: 12,
});

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

const dangerButtonStyle = {
  border: '1px solid rgba(255, 125, 125, 0.28)',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'rgba(255, 82, 82, 0.18)',
  color: '#ffd5d5',
  fontWeight: 700,
  cursor: 'pointer',
};

const backButtonStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  justifySelf: 'flex-start',
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

export default AnalystUsersPage;
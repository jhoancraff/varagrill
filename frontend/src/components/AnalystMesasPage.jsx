import { useEffect, useState } from 'react';

const estadoLabels = {
  libre: 'Libre',
  ocupada: 'Ocupada',
  reservada: 'Reservada',
  mantenimiento: 'Mantenimiento',
};

function AnalystMesasPage({ isMobile, isAdmin, onBack, onCreateNewMesa, onEditMesa, onMesasChanged }) {
  const [mesas, setMesas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (!isAdmin) {
      setLoading(false);
      return;
    }

    const loadMesas = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/admin/mesas/', {
          credentials: 'include',
          cache: 'no-store',
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || 'No se pudo cargar la gestión de mesas.');
        }
        setMesas(Array.isArray(data.mesas) ? data.mesas : []);
      } catch (error) {
        setMessage(error.message || 'No se pudo cargar la gestión de mesas.');
      } finally {
        setLoading(false);
      }
    };

    loadMesas();
  }, [isAdmin]);

  const handleDelete = async (mesa) => {
    if (!window.confirm(`¿Deseas eliminar la mesa ${mesa.numero}?`)) {
      return;
    }

    setSaving(true);
    try {
      const response = await fetch('/api/admin/mesas/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'delete', id: mesa.id }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo eliminar la mesa.');
      }
      setMesas((current) => current.filter((entry) => entry.id !== mesa.id));
      setMessage(data.message || 'Mesa eliminada correctamente.');
      if (onMesasChanged) {
        onMesasChanged();
      }
    } catch (error) {
      setMessage(error.message || 'No se pudo eliminar la mesa.');
    } finally {
      setSaving(false);
    }
  };

  if (!isAdmin) {
    return (
      <section style={containerStyle(isMobile)}>
        <div style={badgeStyle}>Mesas</div>
        <h2 style={titleStyle(isMobile)}>Acceso restringido</h2>
        <div style={noticeStyle}>Solo el rol Administrador puede entrar a esta sección.</div>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          Volver al panel del analista
        </button>
      </section>
    );
  }

  return (
    <section style={containerStyle(isMobile)}>
      <div style={badgeStyle}>Mesas</div>
      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Gestión de mesas</h2>
          <p style={subtitleStyle}>Registra las mesas del local, actualiza su capacidad, ubicación y estado. Si el local crece, agrega aquí las mesas nuevas para que queden disponibles al tomar pedidos.</p>
        </div>
        <button type="button" onClick={onCreateNewMesa} style={primaryButtonStyle}>
          Agregar mesa nueva
        </button>
      </div>

      {message ? <div style={noticeStyle}>{message}</div> : null}

      <div style={summaryGridStyle(isMobile)}>
        <article style={summaryCardStyle}>
          <div style={summaryLabelStyle}>Mesas totales</div>
          <div style={summaryValueStyle}>{mesas.length}</div>
        </article>
        <article style={summaryCardStyle}>
          <div style={summaryLabelStyle}>Libres</div>
          <div style={summaryValueStyle}>{mesas.filter((mesa) => mesa.estado === 'libre').length}</div>
        </article>
        <article style={summaryCardStyle}>
          <div style={summaryLabelStyle}>Ocupadas</div>
          <div style={summaryValueStyle}>{mesas.filter((mesa) => mesa.estado === 'ocupada').length}</div>
        </article>
        <article style={summaryCardStyle}>
          <div style={summaryLabelStyle}>Capacidad total</div>
          <div style={summaryValueStyle}>{mesas.reduce((total, mesa) => total + (Number(mesa.capacidad) || 0), 0)}</div>
        </article>
      </div>

      <section style={panelStyle}>
        <div style={reportHeaderStyle(isMobile)}>
          <div style={sectionTitleStyle}>Reporte administrativo de mesas</div>
          <div style={reportHintStyle}>Consulta número, capacidad, ubicación y estado de cada mesa registrada.</div>
        </div>

        {loading ? <div style={emptyStateStyle}>Cargando mesas...</div> : null}
        {!loading && mesas.length === 0 ? <div style={emptyStateStyle}>No hay mesas registradas.</div> : null}

        {!loading && mesas.length > 0 ? (
          <div style={tableWrapStyle}>
            <div style={tableStyle}>
              <div style={tableHeadStyle}>Mesa</div>
              <div style={tableHeadStyle}>Capacidad</div>
              <div style={tableHeadStyle}>Ubicación</div>
              <div style={tableHeadStyle}>Estado</div>
              <div style={tableHeadStyle}>Acciones</div>

              {mesas.map((mesa) => (
                <>
                  <div key={`mesa-${mesa.id}`} style={tableCellPrimaryStyle}>
                    <div style={mesaNameStyle}>Mesa {mesa.numero}</div>
                  </div>
                  <div key={`capacidad-${mesa.id}`} style={tableCellStyle}>
                    {mesa.capacidad} personas
                  </div>
                  <div key={`ubicacion-${mesa.id}`} style={tableCellStyle}>
                    {mesa.ubicacion || 'Sin especificar'}
                  </div>
                  <div key={`estado-${mesa.id}`} style={tableCellStyle}>
                    <span style={estadoPillStyle(mesa.estado)}>{estadoLabels[mesa.estado] || mesa.estado}</span>
                  </div>
                  <div key={`actions-${mesa.id}`} style={tableCellActionStyle}>
                    <button type="button" onClick={() => onEditMesa(mesa.id)} style={secondaryButtonStyle}>
                      Modificar
                    </button>
                    <button type="button" onClick={() => handleDelete(mesa)} style={dangerButtonStyle} disabled={saving}>
                      Eliminar
                    </button>
                  </div>
                </>
              ))}
            </div>
          </div>
        ) : null}
      </section>

      <button type="button" onClick={onBack} style={backButtonStyle}>
        Volver al panel del analista
      </button>
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
  gridTemplateColumns: 'minmax(120px, 0.8fr) minmax(140px, 0.8fr) minmax(180px, 1.1fr) minmax(140px, 0.8fr) minmax(210px, 1fr)',
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

const mesaNameStyle = {
  color: '#fff',
  fontWeight: 700,
  fontSize: 17,
};

const estadoColors = {
  libre: { background: 'rgba(94, 197, 135, 0.14)', border: 'rgba(94, 197, 135, 0.22)', color: '#c8ffe0' },
  ocupada: { background: 'rgba(255, 145, 145, 0.12)', border: 'rgba(255, 145, 145, 0.22)', color: '#ffd0d0' },
  reservada: { background: 'rgba(255, 205, 100, 0.14)', border: 'rgba(255, 205, 100, 0.24)', color: '#ffe6b0' },
  mantenimiento: { background: 'rgba(180, 180, 180, 0.14)', border: 'rgba(180, 180, 180, 0.24)', color: '#e0e0e0' },
};

const estadoPillStyle = (estado) => {
  const colors = estadoColors[estado] || estadoColors.mantenimiento;
  return {
    display: 'inline-flex',
    width: 'fit-content',
    padding: '7px 11px',
    borderRadius: 999,
    background: colors.background,
    border: `1px solid ${colors.border}`,
    color: colors.color,
    fontWeight: 700,
    fontSize: 12,
  };
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
  justifySelf: 'flex-start',
  border: '1px solid rgba(255, 255, 255, 0.14)',
  borderRadius: 999,
  padding: '11px 18px',
  background: 'rgba(255, 255, 255, 0.04)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
};

export default AnalystMesasPage;

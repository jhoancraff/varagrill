import { useEffect, useState } from 'react';
import Pagination from './Pagination';
import Toast from './Toast';
import useToast from '../hooks/useToast';

const PAGE_SIZE = 50;

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
  const { toast, showSuccess, showError, hideToast } = useToast();
  const [page, setPage] = useState(0);

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
        showError(error.message || 'No se pudo cargar la gestión de mesas.');
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
      showSuccess(data.message || 'Mesa eliminada correctamente.');
      if (onMesasChanged) {
        onMesasChanged();
      }
    } catch (error) {
      showError(error.message || 'No se pudo eliminar la mesa.');
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
          ← Volver al panel de configuración
        </button>
      </section>
    );
  }

  const pageCount = Math.max(1, Math.ceil(mesas.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const pagedMesas = mesas.slice(currentPage * PAGE_SIZE, currentPage * PAGE_SIZE + PAGE_SIZE);

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>
        ← Volver al panel de configuración
      </button>

      <div style={badgeStyle}>Mesas</div>
      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Gestión de mesas</h2>
        </div>
        <button type="button" onClick={onCreateNewMesa} style={primaryButtonStyle}>
          Agregar mesa nueva
        </button>
      </div>

      <Toast toast={toast} onClose={hideToast} />

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

              {pagedMesas.map((mesa) => (
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

        <Pagination
          page={currentPage}
          pageCount={pageCount}
          totalCount={mesas.length}
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
  color: 'var(--vg-f-ffb5b5)',
  fontSize: 12,
  fontWeight: 800,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
};

const titleStyle = (isMobile) => ({
  margin: 0,
  color: 'var(--vg-text-strong)',
  fontSize: isMobile ? 28 : 34,
});

const subtitleStyle = {
  margin: '8px 0 0',
  color: 'var(--vg-f-d2c3c3)',
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
  border: '1px solid rgba(var(--vg-ink), 0.1)',
  background: 'linear-gradient(180deg, var(--vg-s-1b0a0a-a960) 0%, var(--vg-s-0a0a0a-a980) 100%)',
};

const summaryLabelStyle = {
  color: 'var(--vg-f-f0b1b1)',
  fontSize: 12,
  fontWeight: 800,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
};

const summaryValueStyle = {
  color: 'var(--vg-text-strong)',
  fontSize: 28,
  fontWeight: 800,
};

const panelStyle = {
  display: 'grid',
  gap: 16,
  padding: '20px 18px',
  borderRadius: 24,
  border: '1px solid rgba(var(--vg-ink), 0.1)',
  background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)',
};

const sectionTitleStyle = {
  color: 'var(--vg-text-strong)',
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
  color: 'var(--vg-f-d2c4c4)',
  fontSize: 13,
  maxWidth: 420,
};

const emptyStateStyle = {
  minHeight: 80,
  display: 'grid',
  placeItems: 'center',
  borderRadius: 18,
  border: '1px dashed rgba(var(--vg-ink), 0.12)',
  color: 'var(--vg-f-c8bbbb)',
};

const tableWrapStyle = {
  overflowX: 'auto',
};

const tableStyle = {
  display: 'grid',
  gridTemplateColumns: 'minmax(120px, 0.8fr) minmax(140px, 0.8fr) minmax(180px, 1.1fr) minmax(140px, 0.8fr) minmax(210px, 1fr)',
  alignItems: 'stretch',
  border: '1px solid rgba(var(--vg-ink), 0.08)',
  borderRadius: 18,
  overflow: 'hidden',
  minWidth: 920,
};

const tableHeadStyle = {
  padding: '14px 16px',
  background: 'rgba(var(--vg-ink), 0.06)',
  color: 'var(--vg-f-ffb0b0)',
  fontSize: 12,
  fontWeight: 800,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
  borderBottom: '1px solid rgba(var(--vg-ink), 0.08)',
};

const tableCellStyle = {
  padding: '16px',
  borderBottom: '1px solid rgba(var(--vg-ink), 0.08)',
  color: 'var(--vg-f-f2e6e6)',
  display: 'grid',
  alignContent: 'center',
  gap: 4,
};

const tableCellPrimaryStyle = {
  ...tableCellStyle,
  background: 'rgba(var(--vg-ink), 0.02)',
};

const tableCellActionStyle = {
  ...tableCellStyle,
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  flexWrap: 'wrap',
};

const mesaNameStyle = {
  color: 'var(--vg-text-strong)',
  fontWeight: 700,
  fontSize: 17,
};

const estadoColors = {
  libre: { background: 'rgba(94, 197, 135, 0.14)', border: 'var(--vg-f-5ec587-a220)', color: 'var(--vg-f-c8ffe0)' },
  ocupada: { background: 'rgba(255, 145, 145, 0.12)', border: 'var(--vg-f-ff9191-a220)', color: 'var(--vg-f-ffd0d0)' },
  reservada: { background: 'rgba(255, 205, 100, 0.14)', border: 'var(--vg-f-ffcd64-a240)', color: 'var(--vg-f-ffe6b0)' },
  mantenimiento: { background: 'rgba(180, 180, 180, 0.14)', border: 'var(--vg-f-b4b4b4-a240)', color: 'var(--vg-f-e0e0e0)' },
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
  border: '1px solid var(--vg-f-ff9191-a220)',
  background: 'rgba(255, 98, 98, 0.12)',
  color: 'var(--vg-f-ffd8d8)',
};

const primaryButtonStyle = {
  border: 'none',
  borderRadius: 999,
  padding: '11px 18px',
  background: 'linear-gradient(90deg, #bf1f1f 0%, var(--vg-accent-primary) 100%)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
};

const secondaryButtonStyle = {
  border: '1px solid rgba(var(--vg-ink), 0.14)',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'rgba(var(--vg-ink), 0.04)',
  color: 'var(--vg-text-strong)',
  fontWeight: 700,
  cursor: 'pointer',
};

const dangerButtonStyle = {
  border: '1px solid var(--vg-f-ff7d7d-a280)',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'rgba(255, 82, 82, 0.18)',
  color: 'var(--vg-f-ffd5d5)',
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

export default AnalystMesasPage;
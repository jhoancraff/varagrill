import { useEffect, useState } from 'react';

const options = [
  { id: 'create', title: 'Crear ingredientes' },
  { id: 'view', title: 'Ver inventario actual' },
  { id: 'adjust', title: 'Ajuste de inventario' },
  { id: 'movements', title: 'Ver movimiento de inventario' },
  { id: 'alerts', title: 'Alertas de precios' },
];

function AnalystInventoryHubPage({ isMobile, onBack, onCreate, onViewInventory, onAdjustInventory, onViewMovements, onViewAlerts }) {
  const handlers = { create: onCreate, view: onViewInventory, adjust: onAdjustInventory, movements: onViewMovements, alerts: onViewAlerts };
  const [alertasPendientes, setAlertasPendientes] = useState(0);

  // Cuantas alertas de precio esperan revision, para que se noten desde el menu sin abrir la pantalla.
  useEffect(() => {
    let cancelado = false;
    fetch('/api/admin/alertas-costos/?limite=1', { credentials: 'include', cache: 'no-store' })
      .then((respuesta) => respuesta.json().catch(() => ({})))
      .then((json) => { if (!cancelado && json.ok) setAlertasPendientes(Number(json.pendientes) || 0); })
      .catch(() => {});
    return () => { cancelado = true; };
  }, []);

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>
        ← Volver a Contabilidad
      </button>

      <div>
        <h2 style={titleStyle(isMobile)}>Inventario</h2>
      </div>

      <div style={gridStyle(isMobile)}>
        {options.map((option) => (
          <button
            key={option.id}
            type="button"
            onClick={handlers[option.id]}
            style={cardButtonStyle}
          >
            <div style={cardTitleStyle}>
              {option.title}
              {option.id === 'alerts' && alertasPendientes > 0 ? (
                <span style={{ marginLeft: 10, padding: '2px 9px', borderRadius: 999, background: '#d81d1d', color: '#fff', fontSize: 13, fontWeight: 800 }}>{alertasPendientes}</span>
              ) : null}
            </div>
            <span style={cardLinkStyle}>Continuar</span>
          </button>
        ))}
      </div>
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const titleStyle = (isMobile) => ({ margin: 0, color: 'var(--vg-text-strong)', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: 'var(--vg-f-d2c3c3)', lineHeight: 1.6, maxWidth: 760 };

const gridStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 1fr))', gap: 16 });
const cardButtonStyle = {
  display: 'grid', gap: 12, textAlign: 'left', padding: '24px 22px', borderRadius: 24,
  border: '1px solid rgba(var(--vg-ink), 0.1)',
  background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)',
  color: 'var(--vg-text-strong)', cursor: 'pointer', boxShadow: '0 12px 30px rgba(0, 0, 0, calc(0.24 * var(--vg-shadow-k)))',
};
const cardTitleStyle = { fontSize: 20, fontWeight: 700 };
const cardDescriptionStyle = { color: 'var(--vg-f-d0c4c4)', lineHeight: 1.6, fontSize: 14 };
const cardLinkStyle = { color: 'var(--vg-f-ff8f8f)', fontWeight: 700, letterSpacing: '0.04em' };

export default AnalystInventoryHubPage;

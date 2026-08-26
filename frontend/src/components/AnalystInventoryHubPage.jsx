const options = [
  {
    id: 'create',
    title: 'Crear ingredientes',
    description: 'Da de alta ingredientes nuevos, uno por uno o en lote por Excel sin costo ni cantidad — ideal para el montaje inicial del inventario.',
  },
  {
    id: 'view',
    title: 'Ver inventario actual',
    description: 'Reporte con buscador para modificar stock y costo, eliminar ingredientes, o registrar reabastecimientos reales por Excel.',
  },
];

function AnalystInventoryHubPage({ isMobile, onBack, onCreate, onViewInventory }) {
  const handlers = { create: onCreate, view: onViewInventory };

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>
        ← Volver a Contabilidad
      </button>

      <div>
        <h2 style={titleStyle(isMobile)}>Inventario</h2>
        <p style={subtitleStyle}>Elige si quieres dar de alta ingredientes o consultar el inventario actual.</p>
      </div>

      <div style={gridStyle(isMobile)}>
        {options.map((option) => (
          <button
            key={option.id}
            type="button"
            onClick={handlers[option.id]}
            style={cardButtonStyle}
          >
            <div style={cardTitleStyle}>{option.title}</div>
            <div style={cardDescriptionStyle}>{option.description}</div>
            <span style={cardLinkStyle}>Continuar</span>
          </button>
        ))}
      </div>
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: '#d2c3c3', lineHeight: 1.6, maxWidth: 760 };

const gridStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 1fr))', gap: 16 });
const cardButtonStyle = {
  display: 'grid', gap: 12, textAlign: 'left', padding: '24px 22px', borderRadius: 24,
  border: '1px solid rgba(255, 255, 255, 0.1)',
  background: 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)',
  color: '#fff', cursor: 'pointer', boxShadow: '0 12px 30px rgba(0, 0, 0, 0.24)',
};
const cardTitleStyle = { fontSize: 20, fontWeight: 700 };
const cardDescriptionStyle = { color: '#d0c4c4', lineHeight: 1.6, fontSize: 14 };
const cardLinkStyle = { color: '#ff8f8f', fontWeight: 700, letterSpacing: '0.04em' };

export default AnalystInventoryHubPage;

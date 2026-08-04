function PromotionsPage({ isMobile, onBack }) {
  return (
    <section style={containerStyle(isMobile)}>
      <div style={badgeStyle}>Promociones</div>
      <h2 style={titleStyle(isMobile)}>Catálogo de promociones</h2>
      <p style={subtitleStyle}>
        Esta sección mostrará el catálogo de promociones vigentes para el servicio de hoy.
        El contenido se cargará próximamente desde el panel del analista.
      </p>

      <div style={emptyStateStyle}>Todavía no hay promociones cargadas.</div>

      <button type="button" onClick={onBack} style={backButtonStyle}>
        Volver al inicio
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
  margin: 0,
  color: '#d2c3c3',
  lineHeight: 1.6,
  maxWidth: 760,
};

const emptyStateStyle = {
  minHeight: 160,
  display: 'grid',
  placeItems: 'center',
  borderRadius: 24,
  border: '1px dashed rgba(255, 255, 255, 0.14)',
  background: 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)',
  color: '#c8bbbb',
  textAlign: 'center',
  padding: 20,
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

export default PromotionsPage;

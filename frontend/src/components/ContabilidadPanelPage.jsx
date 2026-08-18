const iconProps = {
  viewBox: '0 0 24 24',
  width: 26,
  height: 26,
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
};

const CashRegisterIcon = () => (
  <svg {...iconProps}>
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <path d="M3 9h18" />
    <path d="M8 14h.01" />
    <path d="M12 14h4" />
    <path d="M8 17h.01" />
    <path d="M12 17h4" />
  </svg>
);

const IngredientsIcon = () => (
  <svg {...iconProps}>
    <path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z" />
    <path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12" />
  </svg>
);

const reportSections = [
  {
    id: 'contabilidad-cuadre-caja',
    title: 'Cuadre de caja diario',
    description: 'Compara el efectivo esperado contra lo contado en físico, con consignaciones del turno y el cierre del día.',
    icon: CashRegisterIcon,
  },
  {
    id: 'admin-ingredients',
    title: 'Inventario de Ingredientes',
    description: 'Abre el reporte con buscador para modificar, eliminar o agregar ingredientes.',
    icon: IngredientsIcon,
  },
];

function ContabilidadPanelPage({ isMobile, onBack, onNavigate }) {
  return (
    <section style={panelContainerStyle(isMobile)}>
      <div style={heroStyle}>
        <div style={heroBadgeStyle}>Contabilidad</div>
        <h2 style={titleStyle(isMobile)}>Reportes contables</h2>
        <p style={subtitleStyle}>
          Punto de entrada para todos los reportes de cierre y contabilidad del negocio.
        </p>
      </div>

      <div style={gridStyle(isMobile)}>
        {reportSections.map((section) => {
          const SectionIcon = section.icon;
          return (
            <button
              key={section.id}
              type="button"
              onClick={() => onNavigate(section.id)}
              style={cardButtonStyle}
            >
              <div style={cardHeaderStyle}>
                <span style={cardIconWrapStyle} aria-hidden="true">
                  <SectionIcon />
                </span>
                <div style={cardTitleStyle}>{section.title}</div>
              </div>
              <div style={cardDescriptionStyle}>{section.description}</div>
              <span style={cardLinkStyle}>Abrir reporte</span>
            </button>
          );
        })}
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          Volver al inicio
        </button>
      </div>
    </section>
  );
}

const panelContainerStyle = (isMobile) => ({
  display: 'grid',
  gap: 22,
  width: '100%',
  padding: isMobile ? 4 : 8,
  boxSizing: 'border-box',
});

const heroStyle = {
  display: 'grid',
  gap: 12,
  padding: '24px clamp(18px, 3vw, 32px)',
  borderRadius: 28,
  background: 'linear-gradient(145deg, rgba(96, 17, 17, 0.96) 0%, rgba(24, 8, 8, 0.92) 100%)',
  border: '1px solid rgba(255, 110, 110, 0.22)',
  boxShadow: '0 18px 48px rgba(0, 0, 0, 0.28)',
};

const heroBadgeStyle = {
  display: 'inline-flex',
  width: 'fit-content',
  padding: '7px 12px',
  borderRadius: 999,
  background: 'rgba(255, 255, 255, 0.08)',
  color: '#ffb0b0',
  fontSize: 12,
  fontWeight: 800,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
};

const titleStyle = (isMobile) => ({
  margin: 0,
  color: '#fff4f4',
  fontSize: isMobile ? 30 : 38,
  lineHeight: 1.05,
});

const subtitleStyle = {
  margin: 0,
  maxWidth: 720,
  color: '#f1cfcf',
  lineHeight: 1.6,
  fontSize: 15,
};

const gridStyle = (isMobile) => ({
  display: 'grid',
  gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 1fr))',
  gap: 16,
});

const cardButtonStyle = {
  display: 'grid',
  gap: 12,
  textAlign: 'left',
  padding: '24px 22px',
  borderRadius: 24,
  border: '1px solid rgba(255, 255, 255, 0.1)',
  background: 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)',
  color: '#fff',
  cursor: 'pointer',
  boxShadow: '0 12px 30px rgba(0, 0, 0, 0.24)',
};

const cardHeaderStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 14,
};

const cardIconWrapStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 44,
  height: 44,
  flexShrink: 0,
  borderRadius: 14,
  background: 'rgba(255, 102, 102, 0.14)',
  color: '#ff8f8f',
};

const cardTitleStyle = {
  fontSize: 22,
  fontWeight: 700,
};

const cardDescriptionStyle = {
  color: '#d0c4c4',
  lineHeight: 1.6,
  fontSize: 14,
};

const cardLinkStyle = {
  color: '#ff8f8f',
  fontWeight: 700,
  letterSpacing: '0.04em',
};

const backButtonStyle = {
  border: '1px solid rgba(255, 255, 255, 0.14)',
  borderRadius: 999,
  padding: '11px 18px',
  background: 'rgba(255, 255, 255, 0.04)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
};

export default ContabilidadPanelPage;

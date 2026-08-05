const analystSections = [
  {
    id: 'admin-users',
    title: 'Usuarios',
    description: 'Gestiona el acceso del personal y entra al espacio de trabajo de usuarios.',
  },
  {
    id: 'admin-mesas',
    title: 'Mesas',
    description: 'Registra mesas nuevas, actualiza su capacidad y estado para el flujo de pedidos.',
  },
  {
    id: 'admin-products',
    title: 'Productos',
    description: 'Crea platos y bebidas con imagen y categoría, y edítalos desde el reporte del menú.',
  },
  {
    id: 'admin-ingredients',
    title: 'Reporte de ingredientes',
    description: 'Abre el reporte con buscador para modificar, eliminar o agregar ingredientes.',
  },
  {
    id: 'admin-preparations',
    title: 'Reporte de subrecetas',
    description: 'Abre el reporte con buscador para modificar, eliminar o agregar subrecetas.',
  },
  {
    id: 'admin-recipes',
    title: 'Creación de recetas',
    description: 'Redirige a la página en blanco destinada a la construcción de recetas.',
  },
  {
    id: 'admin-promotions',
    title: 'Promociones',
    description: 'Abre el reporte de productos para aplicar descuentos, uno por uno o en bloque.',
  },
  {
    id: 'admin-chef-recommendations',
    title: 'Recomendaciones del chef',
    description: 'Abre el reporte de platos recomendados y permite agregar nuevas recomendaciones.',
  },
];

function AdminPanelPage({ isMobile, onBack, onNavigate }) {
  return (
    <section style={panelContainerStyle(isMobile)}>
      <div style={heroStyle}>
        <div style={heroBadgeStyle}>Panel del analista</div>
        <h2 style={titleStyle(isMobile)}>Elige un área de trabajo</h2>
        <p style={subtitleStyle}>
          Este panel ahora funciona como punto de entrada. Cada opción redirige a una página
          separada que dejé lista para completar después.
        </p>
      </div>

      <div style={gridStyle(isMobile)}>
        {analystSections.map((section) => (
          <button
            key={section.id}
            type="button"
            onClick={() => onNavigate(section.id)}
            style={cardButtonStyle}
          >
            <div style={cardTitleStyle}>{section.title}</div>
            <div style={cardDescriptionStyle}>{section.description}</div>
            <span style={cardLinkStyle}>Abrir sección</span>
          </button>
        ))}
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

export default AdminPanelPage;
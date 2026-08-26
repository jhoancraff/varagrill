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

const UsersIcon = () => (
  <svg {...iconProps}>
    <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
    <circle cx="9" cy="7" r="4" />
    <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
    <path d="M16 3.13a4 4 0 0 1 0 7.75" />
  </svg>
);

const TablesIcon = () => (
  <svg {...iconProps}>
    <rect x="3" y="3" width="7" height="7" rx="1" />
    <rect x="14" y="3" width="7" height="7" rx="1" />
    <rect x="14" y="14" width="7" height="7" rx="1" />
    <rect x="3" y="14" width="7" height="7" rx="1" />
  </svg>
);

const ProductsIcon = () => (
  <svg {...iconProps}>
    <path d="M16.5 9.4 7.5 4.21" />
    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" />
    <path d="M3.27 6.96 12 12.01l8.73-5.05" />
    <path d="M12 22.08V12" />
  </svg>
);

const PreparationsIcon = () => (
  <svg {...iconProps}>
    <path d="M14 2v6a2 2 0 0 0 .245.96l5.51 10.08A2 2 0 0 1 18 22H6a2 2 0 0 1-1.755-2.96l5.51-10.08A2 2 0 0 0 10 8V2" />
    <path d="M6.453 15h11.094" />
    <path d="M8.5 2h7" />
  </svg>
);

const RecipesIcon = () => (
  <svg {...iconProps}>
    <path d="M12 7v14" />
    <path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z" />
  </svg>
);

const PromotionsIcon = () => (
  <svg {...iconProps}>
    <path d="M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z" />
    <circle cx="7.5" cy="7.5" r="1.5" fill="currentColor" stroke="none" />
  </svg>
);

const ChefHatIcon = () => (
  <svg {...iconProps}>
    <path d="M17 21a1 1 0 0 0 1-1v-5.35c0-.457.316-.844.727-1.041a4 4 0 0 0-2.134-7.589 5 5 0 0 0-9.186 0 4 4 0 0 0-2.134 7.588c.411.198.727.585.727 1.041V20a1 1 0 0 0 1 1Z" />
    <path d="M6 17h12" />
  </svg>
);

const PrinterIcon = () => (
  <svg {...iconProps}>
    <polyline points="6 9 6 2 18 2 18 9" />
    <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" />
    <rect x="6" y="14" width="12" height="8" />
  </svg>
);

const PaymentMethodsIcon = () => (
  <svg {...iconProps}>
    <rect x="2" y="5" width="20" height="14" rx="2" />
    <path d="M2 10h20" />
    <path d="M6 15h4" />
  </svg>
);

const FiscalDataIcon = () => (
  <svg {...iconProps}>
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <path d="M7 8h10" />
    <path d="M7 12h10" />
    <path d="M7 16h6" />
  </svg>
);

const PurchasesIcon = () => (
  <svg {...iconProps}>
    <path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z" />
    <path d="M3 6h18" />
    <path d="M16 10a4 4 0 0 1-8 0" />
  </svg>
);

const analystSections = [
  {
    id: 'admin-users',
    title: 'Gestión de Usuarios',
    description: 'Gestiona el acceso del personal y entra al espacio de trabajo de usuarios.',
    icon: UsersIcon,
  },
  {
    id: 'admin-mesas',
    title: 'Gestión de Mesas',
    description: 'Registra mesas nuevas, actualiza su capacidad y estado para el flujo de pedidos.',
    icon: TablesIcon,
  },
  {
    id: 'admin-products',
    title: 'Catálogo de Productos',
    description: 'Crea platos y bebidas con imagen y categoría, y edítalos desde el reporte del menú.',
    icon: ProductsIcon,
  },
  {
    id: 'admin-preparations',
    title: 'Subrecetas y Preparaciones',
    description: 'Abre el reporte con buscador para modificar, eliminar o agregar subrecetas.',
    icon: PreparationsIcon,
  },
  {
    id: 'admin-recipes',
    title: 'Gestión de Recetas',
    description: 'Redirige a la página en blanco destinada a la construcción de recetas.',
    icon: RecipesIcon,
  },
  {
    id: 'admin-promotions',
    title: 'Promociones y Descuentos',
    description: 'Abre el reporte de productos para aplicar descuentos, uno por uno o en bloque.',
    icon: PromotionsIcon,
  },
  {
    id: 'admin-chef-recommendations',
    title: 'Recomendaciones del Chef',
    description: 'Abre el reporte de platos recomendados y permite agregar nuevas recomendaciones.',
    icon: ChefHatIcon,
  },
  {
    id: 'admin-printers',
    title: 'Impresoras de cocina',
    description: 'Asigna la IP de la impresora térmica que imprime la comanda de cada categoría de producto.',
    icon: PrinterIcon,
  },
  {
    id: 'admin-payment-methods',
    title: 'Métodos de pago',
    description: 'Crea los tipos de pago que se pueden usar al cobrar (efectivo, tarjeta, Binance, Zelle, etc.).',
    icon: PaymentMethodsIcon,
  },
  {
    id: 'admin-datos-fiscales',
    title: 'Datos fiscales',
    description: 'RIF, razón social y domicilio fiscal que aparecen en el encabezado de cada factura, y el IVA por defecto.',
    icon: FiscalDataIcon,
  },
  {
    id: 'admin-compras',
    title: 'Historial de compras',
    description: 'Cada lote de ingredientes cargado al inventario, de qué proveedor y factura vino, y qué costó.',
    icon: PurchasesIcon,
  },
];

// Reservadas al dueño real del negocio (superusuario) o al Contador — un Administrador
// de rol común no las ve, ver WelcomeScreen.jsx (canSeeCartasRestringidas).
const CARTAS_RESTRINGIDAS = ['admin-printers', 'admin-datos-fiscales', 'admin-compras'];

function AdminPanelPage({ isMobile, onBack, onNavigate, canSeeCartasRestringidas }) {
  const visibleSections = canSeeCartasRestringidas
    ? analystSections
    : analystSections.filter((section) => !CARTAS_RESTRINGIDAS.includes(section.id));

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
        {visibleSections.map((section) => {
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
              <span style={cardLinkStyle}>Abrir sección</span>
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

export default AdminPanelPage;
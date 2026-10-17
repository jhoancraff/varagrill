const iconProps = {
  viewBox: '0 0 24 24',
  width: 18,
  height: 18,
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

const DeliveryZonesIcon = () => (
  <svg {...iconProps}>
    <rect x="1" y="6" width="14" height="10" rx="1" />
    <path d="M15 9h4l3 3v4h-7" />
    <circle cx="6" cy="18" r="2" />
    <circle cx="18" cy="18" r="2" />
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

const CosteoConfigIcon = () => (
  <svg {...iconProps}>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" />
  </svg>
);

const MealsIcon = () => (
  <svg {...iconProps}>
    <path d="M4 3v7a2 2 0 0 0 2 2h0a2 2 0 0 0 2-2V3" />
    <path d="M6 3v18" />
    <path d="M16 21V3c-2.5 1.5-4 4-4 7 0 2 1 3 4 3" />
  </svg>
);

const analystSections = [
  { id: 'admin-users', title: 'Usuarios', icon: UsersIcon },
  { id: 'admin-mesas', title: 'Mesas', icon: TablesIcon },
  { id: 'admin-products', title: 'Productos', icon: ProductsIcon },
  { id: 'admin-preparations', title: 'Subrecetas y Preparaciones', icon: PreparationsIcon },
  { id: 'admin-recipes', title: 'Recetas', icon: RecipesIcon },
  { id: 'admin-configuracion-costeo', title: 'Costeo', icon: CosteoConfigIcon },
  { id: 'admin-promotions', title: 'Promociones', icon: PromotionsIcon },
  { id: 'admin-chef-recommendations', title: 'Recomendaciones del Chef', icon: ChefHatIcon },
  { id: 'admin-printers', title: 'Impresoras', icon: PrinterIcon },
  { id: 'admin-payment-methods', title: 'Métodos de pago', icon: PaymentMethodsIcon },
  { id: 'admin-delivery-zonas', title: 'Zonas de delivery', icon: DeliveryZonesIcon },
  { id: 'admin-datos-fiscales', title: 'Datos fiscales', icon: FiscalDataIcon },
  { id: 'admin-compras', title: 'Compras', icon: PurchasesIcon },
  { id: 'admin-comida-empleados', title: 'Comida de empleados', icon: MealsIcon },
];

// Reservadas al dueño real del negocio (superusuario) o al Contador — un Administrador
// de rol común no las ve, ver WelcomeScreen.jsx (canSeeCartasRestringidas).
const CARTAS_RESTRINGIDAS = ['admin-printers', 'admin-datos-fiscales', 'admin-compras'];

// Cómo se agrupan las secciones en pantalla. Solo lista ids de analystSections: una sección
// que el usuario no puede ver (cartas restringidas) simplemente no se dibuja, y un grupo sin
// secciones visibles tampoco.
const analystGroups = [
  {
    id: 'menu-produccion',
    title: 'Menú & Producción',
    ids: ['admin-products', 'admin-recipes', 'admin-preparations', 'admin-configuracion-costeo', 'admin-promotions', 'admin-chef-recommendations'],
  },
  {
    id: 'operacion-local',
    title: 'Operación del local',
    ids: ['admin-mesas', 'admin-users', 'admin-comida-empleados', 'admin-printers', 'admin-delivery-zonas'],
  },
  {
    id: 'pagos-administracion',
    title: 'Pagos & Administración',
    ids: ['admin-payment-methods', 'admin-compras', 'admin-datos-fiscales'],
  },
];

function AdminPanelPage({ isMobile, onBack, onNavigate, canSeeCartasRestringidas }) {
  const visibleSections = canSeeCartasRestringidas
    ? analystSections
    : analystSections.filter((section) => !CARTAS_RESTRINGIDAS.includes(section.id));
  const sectionsById = new Map(visibleSections.map((section) => [section.id, section]));
  const groups = analystGroups
    .map((group) => ({ ...group, sections: group.ids.filter((id) => sectionsById.has(id)).map((id) => sectionsById.get(id)) }))
    .filter((group) => group.sections.length > 0);

  const renderTile = (section) => {
    const SectionIcon = section.icon;
    const isRestricted = CARTAS_RESTRINGIDAS.includes(section.id);
    return (
      <button
        key={section.id}
        type="button"
        className="vg-admin-tile"
        onClick={() => onNavigate(section.id)}
        style={{
          ...tileStyle,
          borderLeft: isRestricted ? '3px solid var(--vg-f-ffc832-a500)' : tileStyle.border,
        }}
        aria-label={isRestricted ? `${section.title} (restringido)` : section.title}
      >
        <span style={tileIconStyle} aria-hidden="true">
          <SectionIcon />
        </span>
        <span style={tileTitleStyle}>{section.title}</span>
        {isRestricted ? <span style={restrictedPillStyle}>Restringido</span> : null}
        <span style={tileChevronStyle} aria-hidden="true">›</span>
      </button>
    );
  };

  return (
    <>
      <style>{`
        .vg-admin-tile {
          transition: background 160ms ease, border-color 160ms ease, transform 160ms ease;
        }
        .vg-admin-tile:hover {
          background: rgba(var(--vg-accent-rgb), 0.08) !important;
          border-color: rgba(var(--vg-accent-rgb), 0.3) !important;
          transform: translateY(-1px);
        }
        .vg-admin-tile:focus-visible {
          outline: 2px solid var(--vg-f-ff7d7d);
          outline-offset: 2px;
        }
        @media (prefers-reduced-motion: reduce) {
          .vg-admin-tile { transition: none; }
          .vg-admin-tile:hover { transform: none; }
        }
      `}</style>
      <section style={panelContainerStyle(isMobile)}>
        <h2 style={titleStyle(isMobile)}>Panel de configuración</h2>

        {groups.map((group) => (
          <section key={group.id} style={groupStyle} aria-label={group.title}>
            <div style={groupHeadingStyle}>
              <span>{group.title}</span>
              <span style={groupRuleStyle} aria-hidden="true" />
            </div>
            <div style={gridStyle(isMobile)}>{group.sections.map(renderTile)}</div>
          </section>
        ))}

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button type="button" onClick={onBack} style={backButtonStyle}>
            Volver al inicio
          </button>
        </div>
      </section>
    </>
  );
}

const panelContainerStyle = (isMobile) => ({
  display: 'grid',
  gap: 18,
  width: '100%',
  padding: isMobile ? 4 : 8,
  boxSizing: 'border-box',
});

const titleStyle = (isMobile) => ({
  margin: 0,
  color: 'var(--vg-f-fff4f4)',
  fontSize: isMobile ? 20 : 22,
  fontWeight: 700,
  lineHeight: 1.2,
});

const groupStyle = {
  display: 'grid',
  gap: 10,
};

const groupHeadingStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  color: 'rgba(var(--vg-ink), 0.55)',
  fontSize: 12.5,
  fontWeight: 600,
  letterSpacing: '0.02em',
};

const groupRuleStyle = {
  flex: 1,
  height: 1,
  background: 'rgba(var(--vg-ink), 0.08)',
};

const gridStyle = (isMobile) => ({
  display: 'grid',
  gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fill, minmax(280px, 1fr))',
  gap: 10,
});

const tileStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  width: '100%',
  minWidth: 0,
  padding: '10px 14px',
  borderRadius: 12,
  background: 'rgba(var(--vg-ink), 0.03)',
  border: '1px solid rgba(var(--vg-ink), 0.07)',
  color: 'var(--vg-text-main)',
  textAlign: 'left',
  cursor: 'pointer',
  boxSizing: 'border-box',
};

const tileIconStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 34,
  height: 34,
  flexShrink: 0,
  borderRadius: 10,
  background: 'rgba(var(--vg-accent-rgb), 0.1)',
  color: 'var(--vg-f-ff7d7d)',
};

const tileTitleStyle = {
  flex: 1,
  minWidth: 0,
  fontSize: 14,
  fontWeight: 600,
  color: 'var(--vg-text-main)',
};

const restrictedPillStyle = {
  flexShrink: 0,
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  color: 'var(--vg-f-ffd700)',
  background: 'rgba(255, 215, 0, 0.1)',
  border: '1px solid var(--vg-f-ffd700-a250)',
  borderRadius: 999,
  padding: '2px 8px',
};

const tileChevronStyle = {
  color: 'rgba(var(--vg-ink), 0.25)',
  fontSize: 20,
  lineHeight: 1,
};

const backButtonStyle = {
  border: '1px solid rgba(var(--vg-ink), 0.14)',
  borderRadius: 999,
  padding: '11px 18px',
  background: 'rgba(var(--vg-ink), 0.04)',
  color: 'var(--vg-text-strong)',
  fontWeight: 700,
  cursor: 'pointer',
};

export default AdminPanelPage;

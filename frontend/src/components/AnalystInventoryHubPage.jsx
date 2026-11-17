import { useEffect, useState } from 'react';

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

const CreateIcon = () => (
  <svg {...iconProps}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 8v8" />
    <path d="M8 12h8" />
  </svg>
);

const StockIcon = () => (
  <svg {...iconProps}>
    <path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z" />
    <path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12" />
  </svg>
);

const AdjustIcon = () => (
  <svg {...iconProps}>
    <path d="M4 6h10" />
    <path d="M18 6h2" />
    <circle cx="16" cy="6" r="2" />
    <path d="M4 12h2" />
    <path d="M10 12h10" />
    <circle cx="8" cy="12" r="2" />
    <path d="M4 18h12" />
    <path d="M20 18h0" />
    <circle cx="18" cy="18" r="2" />
  </svg>
);

const TagIcon = () => (
  <svg {...iconProps}>
    <path d="M3 12V4a1 1 0 0 1 1-1h8l9 9-9 9-9-9Z" />
    <circle cx="8" cy="8" r="1.4" />
  </svg>
);

const AlertIcon = () => (
  <svg {...iconProps}>
    <path d="M12 3 2 20h20L12 3Z" />
    <path d="M12 10v4" />
    <path d="M12 17h0" />
  </svg>
);

const MovementIcon = () => (
  <svg {...iconProps}>
    <path d="M7 4v16" />
    <path d="m3 8 4-4 4 4" />
    <path d="M17 20V4" />
    <path d="m13 16 4 4 4-4" />
  </svg>
);

// Las opciones van agrupadas, igual que en Sevens: lo que se hace con los ingredientes y el seguimiento.
const grupos = [
  {
    id: 'ingredientes',
    titulo: 'Ingredientes',
    opciones: [
      { id: 'create', title: 'Crear ingredientes', detalle: 'Uno por uno, por lote o desde Excel', icon: CreateIcon },
      { id: 'view', title: 'Ver inventario actual', detalle: 'Stock, costos, categorías y PDF', icon: StockIcon },
      { id: 'adjust', title: 'Ajuste de inventario', detalle: 'Corregir el stock tras un conteo', icon: AdjustIcon },
      { id: 'categories', title: 'Categorías de inventario', detalle: 'Condimentos, carnes, granos, bolsas...', icon: TagIcon },
    ],
  },
  {
    id: 'seguimiento',
    titulo: 'Seguimiento',
    opciones: [
      { id: 'movements', title: 'Movimientos del inventario', detalle: 'Qué entró, salió o se ajustó, y por qué hay ese stock', icon: MovementIcon },
      {
        id: 'alerts', title: 'Alertas de precios', detalle: 'Cambios fuertes en el costo de un ingrediente', icon: AlertIcon,
        badgeKey: 'alertasPrecio', badgeTexto: 'alertas pendientes', badgeTitulo: 'Alertas de precio pendientes de revisión',
      },
    ],
  },
];

function AnalystInventoryHubPage({
  isMobile, onBack, onCreate, onViewInventory, onAdjustInventory, onCategories, onViewMovements, onViewAlerts,
}) {
  const [alertasPrecio, setAlertasPrecio] = useState(0);

  // Cuantas alertas de precio de ingredientes esperan revision (ver Alertas de precios).
  useEffect(() => {
    let cancelado = false;
    fetch('/api/admin/alertas-costos/?limite=1', { credentials: 'include', cache: 'no-store' })
      .then((respuesta) => respuesta.json().catch(() => ({})))
      .then((json) => { if (!cancelado && json.ok) setAlertasPrecio(Number(json.pendientes) || 0); })
      .catch(() => {});
    return () => { cancelado = true; };
  }, []);

  const handlers = {
    create: onCreate, view: onViewInventory, adjust: onAdjustInventory, categories: onCategories,
    movements: onViewMovements, alerts: onViewAlerts,
  };
  const badges = { alertasPrecio };

  const renderTile = (opcion) => {
    const Icono = opcion.icon;
    const badge = opcion.badgeKey ? badges[opcion.badgeKey] : 0;
    return (
      <button
        key={opcion.id}
        type="button"
        className="vg-inv-tile"
        onClick={handlers[opcion.id]}
        style={tileStyle}
        aria-label={badge > 0 ? `${opcion.title}, ${badge} ${opcion.badgeTexto || 'bajo el mínimo'}` : opcion.title}
      >
        <span style={tileIconStyle} aria-hidden="true"><Icono /></span>
        <span style={tileTextStyle}>
          <span style={tileTitleStyle}>{opcion.title}</span>
          <span style={tileDetailStyle}>{opcion.detalle}</span>
        </span>
        {badge > 0 ? <span style={tileBadgeStyle} title={opcion.badgeTitulo || 'Artículos en su mínimo o por debajo'}>{badge}</span> : null}
        <span style={tileChevronStyle} aria-hidden="true">›</span>
      </button>
    );
  };

  return (
    <>
      <style>{`
        .vg-inv-tile {
          transition: background 160ms ease, border-color 160ms ease, transform 160ms ease;
        }
        .vg-inv-tile:hover {
          background: rgba(var(--vg-accent-rgb), 0.08) !important;
          border-color: rgba(var(--vg-accent-rgb), 0.3) !important;
          transform: translateY(-1px);
        }
        .vg-inv-tile:focus-visible {
          outline: 2px solid var(--vg-f-ff7d7d);
          outline-offset: 2px;
        }
        @media (prefers-reduced-motion: reduce) {
          .vg-inv-tile { transition: none; }
          .vg-inv-tile:hover { transform: none; }
        }
      `}</style>
      <section style={panelContainerStyle(isMobile)}>
        <h2 style={titleStyle(isMobile)}>Inventario</h2>

        {grupos.map((grupo) => (
          <section key={grupo.id} style={groupStyle} aria-label={grupo.titulo}>
            <div style={groupHeadingStyle}>
              <span>{grupo.titulo}</span>
              <span style={groupRuleStyle} aria-hidden="true" />
            </div>
            <div style={gridStyle(isMobile)}>{grupo.opciones.map(renderTile)}</div>
          </section>
        ))}

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button type="button" onClick={onBack} style={backButtonStyle}>
            Volver a Contabilidad
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

const groupStyle = { display: 'grid', gap: 10 };

const groupHeadingStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  color: 'rgba(var(--vg-ink), 0.55)',
  fontSize: 12.5,
  fontWeight: 600,
  letterSpacing: '0.02em',
};

const groupRuleStyle = { flex: 1, height: 1, background: 'rgba(var(--vg-ink), 0.08)' };

const gridStyle = (isMobile) => ({
  display: 'grid',
  gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fill, minmax(300px, 1fr))',
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

const tileTextStyle = { flex: 1, minWidth: 0, display: 'grid', gap: 2 };

const tileTitleStyle = { fontSize: 14, fontWeight: 600, color: 'var(--vg-text-main)' };

const tileDetailStyle = {
  fontSize: 12,
  color: 'rgba(var(--vg-ink), 0.5)',
  whiteSpace: 'nowrap',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
};

const tileBadgeStyle = {
  minWidth: 22,
  height: 22,
  padding: '0 7px',
  display: 'grid',
  placeItems: 'center',
  borderRadius: 999,
  background: '#ff5c5c',
  color: '#2a0505',
  fontWeight: 800,
  fontSize: 12,
  boxSizing: 'border-box',
};

const tileChevronStyle = { color: 'rgba(var(--vg-ink), 0.25)', fontSize: 20, lineHeight: 1 };

const backButtonStyle = {
  border: '1px solid rgba(var(--vg-ink), 0.14)',
  borderRadius: 999,
  padding: '11px 18px',
  background: 'rgba(var(--vg-ink), 0.04)',
  color: 'var(--vg-text-strong)',
  fontWeight: 700,
  cursor: 'pointer',
};

export default AnalystInventoryHubPage;

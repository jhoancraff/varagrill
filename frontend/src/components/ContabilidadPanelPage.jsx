import { useEffect, useState } from 'react';
import { limpiarFechaSeleccionada, limpiarRangoSeleccionado } from '../utils/fechaContabilidad';

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

const ReceivablesIcon = () => (
  <svg {...iconProps}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 3" />
  </svg>
);

const DateRangeIcon = () => (
  <svg {...iconProps}>
    <rect x="3" y="4" width="18" height="17" rx="2" />
    <path d="M3 9h18" />
    <path d="M8 2v4" />
    <path d="M16 2v4" />
    <path d="M7 13h3v3H7z" />
    <path d="M13 13h4" />
    <path d="M13 17h4" />
  </svg>
);

const HistoryIcon = () => (
  <svg {...iconProps}>
    <path d="M3 3v5h5" />
    <path d="M3.05 13A9 9 0 1 0 6 5.3L3 8" />
    <path d="M12 7v5l4 2" />
  </svg>
);

const MarginIcon = () => (
  <svg {...iconProps}>
    <path d="M3 3v18h18" />
    <path d="M7 15l4-4 3 3 5-6" />
  </svg>
);

const PayablesIcon = () => (
  <svg {...iconProps}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 17V7" />
    <path d="M8.5 10a2.5 2.5 0 0 1 2.5-2.5h1.5a2 2 0 0 1 0 4h-1a2 2 0 0 0 0 4H13a2.5 2.5 0 0 0 2.5-2.5" />
  </svg>
);

const AvailabilityIcon = () => (
  <svg {...iconProps}>
    <rect x="2" y="5" width="20" height="14" rx="2" />
    <circle cx="12" cy="12" r="3" />
    <path d="M6 5v14" />
    <path d="M18 5v14" />
  </svg>
);

const ReconciliationIcon = () => (
  <svg {...iconProps}>
    <rect x="2" y="4" width="7" height="16" rx="1.5" />
    <rect x="15" y="4" width="7" height="16" rx="1.5" />
    <path d="M10.5 9.5l2 2 2-2" />
    <path d="M10.5 14.5l2-2 2 2" />
  </svg>
);

const ExpensesIcon = () => (
  <svg {...iconProps}>
    <rect x="3" y="5" width="18" height="14" rx="2" />
    <path d="M3 10h18" />
    <path d="M7 15h4" />
  </svg>
);

const ResultsIcon = () => (
  <svg {...iconProps}>
    <path d="M4 19V10" />
    <path d="M10 19V5" />
    <path d="M16 19v-7" />
    <path d="M3 19h18" />
  </svg>
);

const MovementIcon = () => (
  <svg {...iconProps}>
    <path d="M3 12h6l2-4 4 8 2-4h4" />
  </svg>
);

const BankFlowIcon = () => (
  <svg {...iconProps}>
    <path d="M3 21h18" />
    <path d="M5 21V10l7-6 7 6v11" />
    <path d="M9 21v-6h6v6" />
    <path d="M9 13h6" />
  </svg>
);

const PosTerminalIcon = () => (
  <svg {...iconProps}>
    <rect x="5" y="2" width="14" height="20" rx="2" />
    <path d="M9 6h6" />
    <path d="M9 11h.01" />
    <path d="M12 11h.01" />
    <path d="M15 11h.01" />
    <path d="M9 15h.01" />
    <path d="M12 15h.01" />
    <path d="M15 15h.01" />
  </svg>
);

// Conciliación bancaria: construida pero oculta a pedido del usuario (2026-09)
// mientras se termina de definir el flujo — la página y el backend siguen
// intactos, solo se le quita el acceso desde este panel.
const CONCILIACION_BANCARIA_HABILITADA = false;

const reportSections = [
  { id: 'contabilidad-cuadre-caja', title: 'Cuadre de caja diario', icon: CashRegisterIcon },
  { id: 'contabilidad-cuadre-caja-rango', title: 'Cuadre de caja por rango', icon: DateRangeIcon },
  { id: 'contabilidad-disponibilidad-cuentas', title: 'Disponibilidad diaria', icon: AvailabilityIcon },
  { id: 'flujo-bancario', title: 'Flujo bancario diario', icon: BankFlowIcon },
  { id: 'contabilidad-lotes-pos', title: 'Lotes de punto de venta', icon: PosTerminalIcon },
  ...(CONCILIACION_BANCARIA_HABILITADA ? [{
    id: 'contabilidad-conciliacion-bancaria',
    title: 'Conciliación bancaria',
    icon: ReconciliationIcon,
  }] : []),
  { id: 'cuentas-cobrar', title: 'Cuentas por cobrar', icon: ReceivablesIcon, badgeKey: 'cuentasPorCobrar' },
  { id: 'cuentas-pagar', title: 'Cuentas por pagar', icon: PayablesIcon, badgeKey: 'cuentasPorPagar' },
  { id: 'gastos-operativos', title: 'Gastos operativos', icon: ExpensesIcon },
  { id: 'estado-resultados', title: 'Estado de resultados', icon: ResultsIcon },
  { id: 'facturas-historial', title: 'Historial de facturas', icon: HistoryIcon },
  { id: 'margen-ganancia', title: 'Margen de ganancia por plato', icon: MarginIcon },
  { id: 'movimiento-productos', title: 'Movimiento de productos', icon: MovementIcon },
  { id: 'admin-ingredients', title: 'Inventario', icon: IngredientsIcon },
];

// Cómo se agrupan los reportes en pantalla. Cada grupo solo lista ids de reportSections: una opción
// que no exista (p. ej. la conciliación mientras está oculta) simplemente no se dibuja.
const reportGroups = [
  {
    id: 'caja-bancos',
    title: 'Caja & Bancos (Operación diaria)',
    ids: [
      'contabilidad-cuadre-caja',
      'contabilidad-cuadre-caja-rango',
      'contabilidad-disponibilidad-cuentas',
      'flujo-bancario',
      'contabilidad-lotes-pos',
      'contabilidad-conciliacion-bancaria',
    ],
  },
  {
    id: 'cuentas-tesoreria',
    title: 'Cuentas & Tesorería',
    ids: ['cuentas-cobrar', 'cuentas-pagar', 'gastos-operativos', 'estado-resultados'],
  },
  {
    id: 'auditoria-inventario',
    title: 'Auditoría & Inventario',
    ids: ['facturas-historial', 'margen-ganancia', 'movimiento-productos', 'admin-ingredients'],
  },
];

function ContabilidadPanelPage({ isMobile, onBack, onNavigate, onlyCardIds }) {
  const [cuentasPorPagarCount, setCuentasPorPagarCount] = useState(0);
  const [cuentasPorCobrarCount, setCuentasPorCobrarCount] = useState(0);

  useEffect(() => {
    // La cajera (onlyCardIds restringido a cuadre de caja + cuentas por cobrar) no tiene
    // permiso para consultar cuentas por pagar — ni falta le hace ese badge aquí.
    if (onlyCardIds) {
      return;
    }
    const loadCount = async () => {
      try {
        const response = await fetch('/api/cuentas-por-pagar/', { credentials: 'include', cache: 'no-store' });
        const data = await response.json().catch(() => ({}));
        if (response.ok && data.ok) {
          setCuentasPorPagarCount(Array.isArray(data.compras) ? data.compras.length : 0);
        }
      } catch (error) {
        // El badge simplemente no aparece si falla.
      }
    };
    loadCount();
  }, [onlyCardIds]);

  useEffect(() => {
    const loadCount = async () => {
      try {
        const response = await fetch('/api/cuentas-por-cobrar/', { credentials: 'include', cache: 'no-store' });
        const data = await response.json().catch(() => ({}));
        if (response.ok && data.ok) {
          setCuentasPorCobrarCount(Array.isArray(data.ordenes_cobro) ? data.ordenes_cobro.length : 0);
        }
      } catch (error) {
        // El badge simplemente no aparece si falla.
      }
    };
    loadCount();
  }, []);

  const badgeCounts = { cuentasPorPagar: cuentasPorPagarCount, cuentasPorCobrar: cuentasPorCobrarCount };
  const visibleSections = onlyCardIds ? reportSections.filter((section) => onlyCardIds.includes(section.id)) : reportSections;
  const visibleIds = new Set(visibleSections.map((section) => section.id));
  const sectionsById = new Map(visibleSections.map((section) => [section.id, section]));
  // Sin onlyCardIds se muestran los tres grupos con su subtítulo; con él (cajera) solo las tarjetas
  // permitidas, sin títulos de grupo que quedarían vacíos o con una sola opción.
  const groups = onlyCardIds
    ? []
    : reportGroups
      .map((group) => ({ ...group, sections: group.ids.filter((id) => visibleIds.has(id)).map((id) => sectionsById.get(id)) }))
      .filter((group) => group.sections.length > 0);

  const handleOpen = (section) => {
    if (section.id === 'contabilidad-cuadre-caja') {
      // Entrar desde esta tarjeta es un arranque nuevo del cuadre
      // diario — debe mostrar hoy, no la fecha que haya quedado
      // guardada de una visita anterior a algún reporte de
      // detalle. Esa fecha guardada solo debe sobrevivir cuando
      // se vuelve AL cuadre DESDE un detalle (botón Volver), lo
      // cual no pasa por acá. Tambien se limpia el rango
      // guardado, para que esos mismos 4 reportes de detalle no
      // se queden en "modo rango" de una visita anterior al
      // cuadre por rango.
      limpiarFechaSeleccionada();
      limpiarRangoSeleccionado();
    } else if (section.id === 'contabilidad-cuadre-caja-rango') {
      // Mismo razonamiento que arriba pero al reves: arrancar de
      // nuevo el cuadre por rango no debe arrastrar un rango
      // viejo, y los 4 reportes de detalle no deben quedarse en
      // "modo dia" de una visita anterior al cuadre diario.
      limpiarRangoSeleccionado();
      limpiarFechaSeleccionada();
    }
    onNavigate(section.id);
  };

  const renderTile = (section) => {
    const SectionIcon = section.icon;
    const badgeCount = section.badgeKey ? badgeCounts[section.badgeKey] : 0;
    return (
      <button
        key={section.id}
        type="button"
        className="vg-conta-tile"
        onClick={() => handleOpen(section)}
        style={tileStyle}
        aria-label={badgeCount > 0 ? `${section.title}, ${badgeCount} pendientes` : section.title}
      >
        <span style={tileIconStyle} aria-hidden="true">
          <SectionIcon />
        </span>
        <span style={tileTitleStyle}>{section.title}</span>
        {badgeCount > 0 ? <span style={tileBadgeStyle}>{badgeCount}</span> : null}
        <span style={tileChevronStyle} aria-hidden="true">›</span>
      </button>
    );
  };

  return (
    <>
      <style>{`
        .vg-conta-tile {
          transition: background 160ms ease, border-color 160ms ease, transform 160ms ease;
        }
        .vg-conta-tile:hover {
          background: rgba(var(--vg-accent-rgb), 0.08) !important;
          border-color: rgba(var(--vg-accent-rgb), 0.3) !important;
          transform: translateY(-1px);
        }
        .vg-conta-tile:focus-visible {
          outline: 2px solid var(--vg-f-ff7d7d);
          outline-offset: 2px;
        }
        @media (prefers-reduced-motion: reduce) {
          .vg-conta-tile { transition: none; }
          .vg-conta-tile:hover { transform: none; }
        }
      `}</style>
      <section style={panelContainerStyle(isMobile)}>
        <h2 style={titleStyle(isMobile)}>Reportes contables</h2>

        {onlyCardIds ? (
          <div style={gridStyle(isMobile)}>{visibleSections.map(renderTile)}</div>
        ) : (
          groups.map((group) => (
            <section key={group.id} style={groupStyle} aria-label={group.title}>
              <div style={groupHeadingStyle}>
                <span>{group.title}</span>
                <span style={groupRuleStyle} aria-hidden="true" />
              </div>
              <div style={gridStyle(isMobile)}>{group.sections.map(renderTile)}</div>
            </section>
          ))
        )}

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

export default ContabilidadPanelPage;

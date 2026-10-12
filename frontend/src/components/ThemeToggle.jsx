import { useTheme } from '../context/ThemeContext';

const iconProps = {
  viewBox: '0 0 24 24',
  width: 18,
  height: 18,
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': 'true',
};

const SunIcon = () => (
  <svg {...iconProps}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2" />
    <path d="M12 20v2" />
    <path d="m4.93 4.93 1.41 1.41" />
    <path d="m17.66 17.66 1.41 1.41" />
    <path d="M2 12h2" />
    <path d="M20 12h2" />
    <path d="m6.34 17.66-1.41 1.41" />
    <path d="m19.07 4.93-1.41 1.41" />
  </svg>
);

const MoonIcon = () => (
  <svg {...iconProps}>
    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
  </svg>
);

// Interruptor de tema. Muestra el icono del modo al que se va a cambiar (sol en oscuro, luna en claro).
//   <ThemeToggle compact />      botón redondo solo con el icono (login, esquinas)
//   <ThemeToggle variant="menu" buttonStyle={...} iconStyle={...} />   fila de un menú, con texto
function ThemeToggle({ compact = false, variant = 'default', buttonStyle, iconStyle }) {
  const { isDark, toggleTheme } = useTheme();
  const label = isDark ? 'Modo claro' : 'Modo oscuro';
  const Icon = isDark ? SunIcon : MoonIcon;

  if (variant === 'menu') {
    return (
      <button
        type="button"
        className="no-print"
        onClick={toggleTheme}
        style={buttonStyle}
        aria-label={`Cambiar a ${label.toLowerCase()}`}
      >
        <span aria-hidden="true" style={iconStyle}>
          <Icon />
        </span>
        <span style={{ flex: 1, textAlign: 'left' }}>{label}</span>
      </button>
    );
  }

  return (
    <button
      type="button"
      className="no-print"
      onClick={toggleTheme}
      title={label}
      aria-label={`Cambiar a ${label.toLowerCase()}`}
      style={{ ...baseStyle, ...(compact ? compactStyle : fullStyle), ...buttonStyle }}
    >
      <Icon />
      {compact ? null : <span>{label}</span>}
    </button>
  );
}

const baseStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: 8,
  border: '1px solid var(--vg-border-card)',
  background: 'var(--vg-bg-input)',
  color: 'var(--vg-text-main)',
  fontWeight: 600,
  fontSize: 13,
  cursor: 'pointer',
  boxSizing: 'border-box',
};

const compactStyle = {
  width: 38,
  height: 38,
  borderRadius: 12,
  padding: 0,
};

const fullStyle = {
  borderRadius: 999,
  padding: '9px 14px',
};

export default ThemeToggle;

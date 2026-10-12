import ThemeToggle from './ThemeToggle';

function ScreenShell({ children, maxWidth = 430, compact = false }) {
  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--vg-bg-app)',
      fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
      color: 'var(--vg-text-main)',
      padding: 24,
      boxSizing: 'border-box',
      overflow: 'auto',
      position: 'relative',
    }}>
      <div style={{ position: 'absolute', top: 16, right: 16, zIndex: 2 }}>
        <ThemeToggle compact />
      </div>
      <div style={{
        width: '100%',
        maxWidth,
        minHeight: compact ? 'auto' : 'min(100vh - 48px, 760px)',
        background: 'linear-gradient(180deg, var(--vg-s-180808-a980) 0%, var(--vg-s-0a0a0a-a980) 100%)',
        border: '1px solid rgba(var(--vg-accent-rgb), 0.22)',
        borderRadius: 28,
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04), 0 18px 50px rgba(0, 0, 0, calc(0.45 * var(--vg-shadow-k)))',
        padding: compact ? '24px' : '18px 24px 40px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
      }}>
        {children}
      </div>
    </div>
  );
}

export default ScreenShell;

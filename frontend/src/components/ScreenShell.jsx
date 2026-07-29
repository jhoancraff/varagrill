function ScreenShell({ children, maxWidth = 430, compact = false }) {
  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'radial-gradient(circle at top, #2f0b0b 0%, #120606 45%, #050505 100%)',
      fontFamily: 'Arial, sans-serif',
      color: '#f5f5f5',
      padding: 24,
      boxSizing: 'border-box',
      overflow: 'auto',
    }}>
      <div style={{
        width: '100%',
        maxWidth,
        minHeight: compact ? 'auto' : 'min(100vh - 48px, 760px)',
        background: 'linear-gradient(180deg, rgba(24, 8, 8, 0.98) 0%, rgba(10, 10, 10, 0.98) 100%)',
        border: '1px solid rgba(255, 77, 77, 0.22)',
        borderRadius: 28,
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04), 0 18px 50px rgba(0,0,0,0.45)',
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

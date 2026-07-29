function WelcomeScreen({ name, onBack }) {
  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'radial-gradient(circle at top, #2f0b0b 0%, #120606 45%, #050505 100%)',
      padding: 24,
      boxSizing: 'border-box',
    }}>
      <div style={{
        width: '100%',
        maxWidth: 460,
        background: 'linear-gradient(180deg, rgba(24, 8, 8, 0.98) 0%, rgba(10, 10, 10, 0.98) 100%)',
        border: '1px solid rgba(255, 77, 77, 0.22)',
        borderRadius: 28,
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04), 0 18px 50px rgba(0,0,0,0.45)',
        padding: '32px 24px',
        color: '#f5f5f5',
        textAlign: 'center',
      }}>
        <div style={{ fontSize: 34, fontWeight: 700, color: '#ff4d4d', marginBottom: 12 }}>Bienvenido</div>
        <div style={{ fontSize: 20, marginBottom: 10 }}>{name || 'Usuario'}</div>
        <div style={{ color: '#c8c8c8', marginBottom: 24 }}>Tu acceso a Varagrill ha sido confirmado. Prepárate para gestionar pedidos, mesas y cocina desde aquí.</div>
        <button
          type="button"
          onClick={onBack}
          style={{
            padding: '12px 18px',
            borderRadius: 999,
            border: 'none',
            background: 'linear-gradient(90deg, #b51d1d 0%, #ff4d4d 100%)',
            color: '#fff',
            fontWeight: 700,
            cursor: 'pointer',
          }}
        >
          Volver al login
        </button>
      </div>
    </div>
  );
}

export default WelcomeScreen;

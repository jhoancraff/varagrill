function SplashScreen() {
  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'radial-gradient(circle at top, #4b1010 0%, #140606 45%, #050505 100%)',
      color: '#fff',
      padding: 24,
      boxSizing: 'border-box',
    }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{
          width: 92,
          height: 92,
          borderRadius: 30,
          margin: '0 auto 16px',
          background: 'linear-gradient(135deg, #bf1f1f 0%, #7a0d0d 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 10px 25px rgba(191, 31, 31, 0.3)',
          overflow: 'hidden',
        }}>
          <img src="/assets/varagrill-logo.jpg" alt="Varagrill logo" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        </div>
        <div style={{ fontSize: 26, fontWeight: 700 }}>Varagrill</div>
        <div style={{ marginTop: 8, color: '#d7b0b0' }}>Preparando tu experiencia</div>
      </div>
    </div>
  );
}

export default SplashScreen;

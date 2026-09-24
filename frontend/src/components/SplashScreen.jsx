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
      <style>{`
        @keyframes splashFadeIn {
          from { opacity: 0; transform: translateY(12px) scale(0.97); }
          to   { opacity: 1; transform: translateY(0)   scale(1); }
        }
        @keyframes splashLogoPulse {
          0%, 100% { box-shadow: 0 10px 25px rgba(191, 31, 31, 0.3), 0 0 0 0 rgba(191, 31, 31, 0.25); }
          50%       { box-shadow: 0 10px 35px rgba(191, 31, 31, 0.5), 0 0 0 12px rgba(191, 31, 31, 0); }
        }
        @keyframes splashDots {
          0%   { content: ''; }
          33%  { content: '.'; }
          66%  { content: '..'; }
          100% { content: '...'; }
        }
        .splash-content {
          animation: splashFadeIn 0.55s ease-out both;
          text-align: center;
        }
        .splash-logo {
          animation: splashLogoPulse 2s ease-in-out infinite;
        }
        .splash-dots::after {
          content: '';
          animation: splashDots 1.4s steps(1) infinite;
        }
      `}</style>
      <div className="splash-content">
        <div
          className="splash-logo"
          style={{
            width: 92,
            height: 92,
            borderRadius: 30,
            margin: '0 auto 20px',
            background: 'linear-gradient(135deg, #bf1f1f 0%, #7a0d0d 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            overflow: 'hidden',
          }}
        >
          <img
            src="/assets/varagrill-logo.jpg"
            alt="Varagrill logo"
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          />
        </div>
        <div style={{ fontSize: 28, fontWeight: 700, letterSpacing: '0.01em' }}>
          Varagrill
        </div>
        <div style={{ marginTop: 10, color: '#d7b0b0', fontSize: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
          <span>Preparando tu experiencia</span>
          <span className="splash-dots" aria-hidden="true" />
        </div>
      </div>
    </div>
  );
}

export default SplashScreen;

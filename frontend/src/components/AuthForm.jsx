import { useState } from 'react';

function AuthForm({ username, password, loading, onUsernameChange, onPasswordChange, onSubmit, message, isInstalled, onInstall }) {
  const [showPassword, setShowPassword] = useState(false);
  const [usernameFocused, setUsernameFocused] = useState(false);
  const [passwordFocused, setPasswordFocused] = useState(false);

  const isSuccess = message && message.includes('Acceso concedido');

  return (
    <>
      <style>{`
        @keyframes inputFocusIn {
          from { box-shadow: 0 0 0 0 rgba(255, 77, 77, 0); }
          to   { box-shadow: 0 0 0 3px rgba(255, 77, 77, 0.35); }
        }
        .vg-btn-install:hover {
          background: rgba(191, 31, 31, 0.18) !important;
          border-color: rgba(255, 100, 100, 0.65) !important;
        }
        .vg-btn-submit:hover:not(:disabled) {
          filter: brightness(1.12);
          box-shadow: 0 6px 20px rgba(191, 31, 31, 0.5) !important;
        }
        .vg-btn-eye:hover {
          color: #ff7d7d !important;
        }
        .vg-toggle-password {
          background: transparent;
          border: none;
          padding: 0 10px;
          cursor: pointer;
          color: #9a9a9a;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: color 150ms ease;
          flex-shrink: 0;
        }
      `}</style>

      {!isInstalled && (
        <button
          type="button"
          onClick={onInstall}
          className="vg-btn-install"
          style={{
            width: '100%',
            marginBottom: 16,
            padding: '11px 14px',
            borderRadius: 999,
            border: '1px solid rgba(255, 103, 103, 0.45)',
            background: 'rgba(43, 18, 18, 0.75)',
            color: '#ffaaaa',
            fontWeight: 600,
            cursor: 'pointer',
            fontSize: 14,
            transition: 'background 180ms ease, border-color 180ms ease',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
          }}
        >
          {/* Ícono de descarga */}
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="7 10 12 15 17 10" />
            <line x1="12" y1="15" x2="12" y2="3" />
          </svg>
          Instalar app
        </button>
      )}

      <form onSubmit={onSubmit}>
        {/* ── Campo Usuario ── */}
        <label style={{ display: 'block', marginBottom: 8, color: '#e6e6e6', fontSize: 14, fontWeight: 500 }}>
          Usuario
        </label>
        <input
          type="text"
          value={username}
          onChange={onUsernameChange}
          onFocus={() => setUsernameFocused(true)}
          onBlur={() => setUsernameFocused(false)}
          style={inputStyle(usernameFocused)}
          placeholder="Ingrese su usuario"
          autoComplete="username"
          required
        />

        {/* ── Campo Contraseña ── */}
        <label style={{ display: 'block', marginTop: 18, marginBottom: 8, color: '#e6e6e6', fontSize: 14, fontWeight: 500 }}>
          Contraseña
        </label>
        <div style={{
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          borderRadius: 14,
          border: passwordFocused ? '1px solid rgba(255, 77, 77, 0.65)' : '1px solid rgba(255, 255, 255, 0.1)',
          background: 'rgba(255, 255, 255, 0.04)',
          boxShadow: passwordFocused ? '0 0 0 3px rgba(255, 77, 77, 0.2)' : 'none',
          transition: 'border-color 180ms ease, box-shadow 180ms ease',
          overflow: 'hidden',
        }}>
          <input
            type={showPassword ? 'text' : 'password'}
            value={password}
            onChange={onPasswordChange}
            onFocus={() => setPasswordFocused(true)}
            onBlur={() => setPasswordFocused(false)}
            style={{
              flex: 1,
              padding: '12px 14px',
              border: 'none',
              background: 'transparent',
              color: '#fff',
              outline: 'none',
              fontSize: 15,
              boxSizing: 'border-box',
            }}
            placeholder="Ingrese su contraseña"
            autoComplete="current-password"
            required
          />
          <button
            type="button"
            onClick={() => setShowPassword((v) => !v)}
            aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
            className="vg-toggle-password vg-btn-eye"
          >
            {showPassword ? (
              /* Ojo tachado (ocultar) */
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
                <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
                <line x1="1" y1="1" x2="23" y2="23" />
              </svg>
            ) : (
              /* Ojo abierto (mostrar) */
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
            )}
          </button>
        </div>

        {/* ── Botón Entrar ── */}
        <button
          type="submit"
          disabled={loading}
          className="vg-btn-submit"
          style={{
            width: '100%',
            marginTop: 24,
            padding: '14px 16px',
            borderRadius: 999,
            border: 'none',
            background: loading
              ? 'rgba(90, 30, 30, 0.8)'
              : 'linear-gradient(90deg, #b51d1d 0%, #ff4d4d 100%)',
            color: '#fff',
            fontWeight: 700,
            cursor: loading ? 'wait' : 'pointer',
            fontSize: 16,
            letterSpacing: '0.03em',
            boxShadow: loading ? 'none' : '0 4px 14px rgba(191, 31, 31, 0.4)',
            transition: 'filter 180ms ease, box-shadow 180ms ease',
          }}
        >
          {loading ? 'Ingresando...' : 'Entrar'}
        </button>
      </form>

      {/* ── Mensaje de estado ── */}
      {message && (
        <div style={{
          marginTop: 18,
          padding: '12px 14px',
          borderRadius: 14,
          background: isSuccess ? 'rgba(23, 61, 26, 0.9)' : 'rgba(75, 24, 24, 0.9)',
          border: isSuccess ? '1px solid rgba(125, 255, 160, 0.3)' : '1px solid rgba(255, 100, 100, 0.3)',
          color: '#fff',
          fontSize: 13.5,
          display: 'flex',
          alignItems: 'flex-start',
          gap: 10,
        }}>
          {/* Ícono de estado */}
          <span style={{
            flexShrink: 0,
            width: 22,
            height: 22,
            borderRadius: '50%',
            display: 'grid',
            placeItems: 'center',
            background: isSuccess ? 'rgba(74, 222, 128, 0.2)' : 'rgba(255, 77, 77, 0.2)',
            color: isSuccess ? '#4ade80' : '#ff7d7d',
            fontSize: 12,
            fontWeight: 800,
          }}>
            {isSuccess ? '✓' : '!'}
          </span>
          <span style={{ flex: 1, lineHeight: 1.5 }}>{message}</span>
        </div>
      )}
    </>
  );
}

const inputStyle = (isFocused) => ({
  width: '100%',
  padding: '12px 14px',
  borderRadius: 14,
  border: isFocused ? '1px solid rgba(255, 77, 77, 0.65)' : '1px solid rgba(255, 255, 255, 0.1)',
  background: 'rgba(255, 255, 255, 0.04)',
  color: '#fff',
  boxSizing: 'border-box',
  outline: 'none',
  fontSize: 15,
  boxShadow: isFocused ? '0 0 0 3px rgba(255, 77, 77, 0.2)' : 'none',
  transition: 'border-color 180ms ease, box-shadow 180ms ease',
});

export default AuthForm;

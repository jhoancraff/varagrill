function AuthForm({ username, password, loading, onUsernameChange, onPasswordChange, onSubmit, message, isInstalled, onInstall }) {
  return (
    <>
      {!isInstalled && (
        <button
          type="button"
          onClick={onInstall}
          style={{
            width: '100%',
            marginBottom: 16,
            padding: '11px 14px',
            borderRadius: 999,
            border: '1px solid rgba(255, 103, 103, 0.35)',
            background: 'rgba(43, 18, 18, 0.9)',
            color: '#fff',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          Instalar app
        </button>
      )}

      <form onSubmit={onSubmit}>
        <label style={{ display: 'block', marginBottom: 8, color: '#e6e6e6' }}>Usuario</label>
        <input
          type="text"
          value={username}
          onChange={onUsernameChange}
          style={inputStyle}
          placeholder="Ingrese su usuario"
          autoComplete="username"
          required
        />

        <label style={{ display: 'block', marginTop: 16, marginBottom: 8, color: '#e6e6e6' }}>Contraseña</label>
        <input
          type="password"
          value={password}
          onChange={onPasswordChange}
          style={inputStyle}
          placeholder="Ingrese su contraseña"
          autoComplete="current-password"
          required
        />

        <button
          type="submit"
          disabled={loading}
          style={{
            width: '100%',
            marginTop: 22,
            padding: '13px 16px',
            borderRadius: 999,
            border: 'none',
            background: loading ? '#7a2a2a' : 'linear-gradient(90deg, #b51d1d 0%, #ff4d4d 100%)',
            color: '#fff',
            fontWeight: 700,
            cursor: loading ? 'wait' : 'pointer',
            fontSize: 16,
          }}
        >
          {loading ? 'Ingresando...' : 'Entrar'}
        </button>
      </form>

      {message && (
        <div style={{
          marginTop: 20,
          padding: 12,
          borderRadius: 14,
          background: message.includes('Acceso concedido') ? 'rgba(23, 61, 26, 0.9)' : 'rgba(75, 24, 24, 0.9)',
          color: '#fff',
          textAlign: 'center',
          fontSize: 14,
        }}>
          {message}
        </div>
      )}
    </>
  );
}

const inputStyle = {
  width: '100%',
  padding: '12px 14px',
  borderRadius: 14,
  border: '1px solid rgba(255,255,255,0.1)',
  background: 'rgba(255,255,255,0.04)',
  color: '#fff',
  boxSizing: 'border-box',
  outline: 'none',
};

export default AuthForm;

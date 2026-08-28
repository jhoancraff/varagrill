function Toast({ toast, onClose }) {
  if (!toast) {
    return null;
  }

  const isError = toast.type === 'error';

  return (
    <div style={wrapStyle}>
      <style>
        {`@keyframes toastSlideIn {
            from { transform: translateX(24px); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
          }
        `}
      </style>
      <div style={isError ? errorCardStyle : successCardStyle} role="status">
        <span style={iconStyle}>{isError ? '⚠' : '✓'}</span>
        <span style={textStyle}>
          {toast.message}
          {toast.action ? (
            <button type="button" onClick={toast.action.onClick} style={actionButtonStyle}>
              {toast.action.label}
            </button>
          ) : null}
        </span>
        <button type="button" onClick={onClose} style={closeButtonStyle} aria-label="Cerrar aviso">×</button>
      </div>
    </div>
  );
}

const wrapStyle = {
  position: 'fixed',
  top: 18,
  right: 18,
  zIndex: 9999,
  maxWidth: 'min(360px, calc(100vw - 36px))',
};

const baseCardStyle = {
  display: 'flex',
  alignItems: 'flex-start',
  gap: 10,
  padding: '14px 16px',
  borderRadius: 16,
  boxShadow: '0 14px 30px rgba(0, 0, 0, 0.35)',
  animation: 'toastSlideIn 0.2s ease-out',
  backdropFilter: 'blur(6px)',
};

const successCardStyle = {
  ...baseCardStyle,
  border: '1px solid rgba(125, 255, 160, 0.4)',
  background: 'rgba(20, 60, 32, 0.96)',
  color: '#c2f0d2',
};

const errorCardStyle = {
  ...baseCardStyle,
  border: '1px solid rgba(255, 145, 145, 0.45)',
  background: 'rgba(70, 16, 16, 0.96)',
  color: '#ffd8d8',
};

const iconStyle = {
  fontSize: 16,
  fontWeight: 800,
  lineHeight: '20px',
};

const textStyle = {
  flex: 1,
  fontSize: 13.5,
  fontWeight: 600,
  lineHeight: 1.5,
};

const actionButtonStyle = {
  display: 'block',
  marginTop: 6,
  border: 'none',
  background: 'transparent',
  color: 'inherit',
  textDecoration: 'underline',
  fontWeight: 700,
  cursor: 'pointer',
  padding: 0,
  fontSize: 13,
};

const closeButtonStyle = {
  border: 'none',
  background: 'transparent',
  color: 'inherit',
  fontSize: 18,
  lineHeight: '18px',
  cursor: 'pointer',
  opacity: 0.7,
  padding: 0,
};

export default Toast;

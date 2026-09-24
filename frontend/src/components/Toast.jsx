import { useEffect, useState } from 'react';

function Toast({ toast, onClose, position = 'top-right', durationMs = 4500 }) {
  const [progress, setProgress] = useState(100);

  useEffect(() => {
    if (!toast) return;

    setProgress(100);
    const startTime = Date.now();
    const interval = window.setInterval(() => {
      const elapsed = Date.now() - startTime;
      const remaining = Math.max(0, 100 - (elapsed / durationMs) * 100);
      setProgress(remaining);
      if (remaining <= 0) {
        window.clearInterval(interval);
      }
    }, 40);

    return () => window.clearInterval(interval);
  }, [toast, durationMs]);

  if (!toast) return null;

  const isError = toast.type === 'error';

  return (
    <div style={wrapStyle(position)}>
      <style>{`
        @keyframes toastSlideIn {
          from { transform: translateX(${position === 'top-left' ? '-24px' : '24px'}); opacity: 0; }
          to   { transform: translateX(0);    opacity: 1; }
        }
        .vg-toast-close:hover { opacity: 1 !important; }
      `}</style>
      <div
        style={isError ? errorCardStyle : successCardStyle}
        role="status"
        aria-live="polite"
      >
        {/* Ícono SVG */}
        <span style={iconWrapStyle(isError)} aria-hidden="true">
          {isError ? (
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 6 9 17l-5-5" />
            </svg>
          )}
        </span>

        {/* Texto */}
        <span style={textStyle}>
          {toast.message}
          {toast.action ? (
            <button type="button" onClick={toast.action.onClick} style={actionButtonStyle}>
              {toast.action.label}
            </button>
          ) : null}
        </span>

        {/* Botón cerrar */}
        <button
          type="button"
          onClick={onClose}
          style={closeButtonStyle}
          className="vg-toast-close"
          aria-label="Cerrar aviso"
        >
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
            <path d="M18 6 6 18" />
            <path d="m6 6 12 12" />
          </svg>
        </button>

        {/* Barra de progreso */}
        <div style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          height: 3,
          borderRadius: '0 0 0 16px',
          width: `${progress}%`,
          background: isError
            ? 'rgba(255, 130, 130, 0.7)'
            : 'rgba(74, 222, 128, 0.7)',
          transition: 'width 40ms linear',
        }} aria-hidden="true" />
      </div>
    </div>
  );
}

const wrapStyle = (position) => ({
  position: 'fixed',
  top: 18,
  ...(position === 'top-left' ? { left: 18 } : { right: 18 }),
  zIndex: 9999,
  maxWidth: 'min(360px, calc(100vw - 36px))',
});

const baseCardStyle = {
  position: 'relative',
  display: 'flex',
  alignItems: 'flex-start',
  gap: 10,
  padding: '14px 16px 17px',
  borderRadius: 16,
  boxShadow: '0 14px 30px rgba(0, 0, 0, 0.35)',
  animation: 'toastSlideIn 0.2s ease-out',
  backdropFilter: 'blur(6px)',
  overflow: 'hidden',
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

const iconWrapStyle = (isError) => ({
  flexShrink: 0,
  width: 26,
  height: 26,
  borderRadius: 8,
  display: 'grid',
  placeItems: 'center',
  background: isError ? 'rgba(255, 100, 100, 0.2)' : 'rgba(74, 222, 128, 0.2)',
  color: isError ? '#ff9d9d' : '#4ade80',
  marginTop: 1,
});

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
  display: 'grid',
  placeItems: 'center',
  cursor: 'pointer',
  opacity: 0.55,
  padding: 4,
  borderRadius: 6,
  transition: 'opacity 150ms ease',
};

export default Toast;

import useMobileBackHandler from '../hooks/useMobileBackHandler';

function ConfirmModal({ open, title, message, confirmLabel = 'Confirmar', cancelLabel = 'Cancelar', onConfirm, onCancel, busy }) {
  // Componente compartido por ~30 pantallas — wireando el Atrás móvil UNA vez
  // acá alcanza a todas, sin tocar cada pantalla que lo usa. Mientras esté
  // "busy" (guardando) no se cierra con Atrás, igual que el backdrop no cierra
  // con click en ese estado.
  useMobileBackHandler(open && !busy, onCancel);

  if (!open) {
    return null;
  }

  return (
    <div style={backdropStyle} onClick={busy ? undefined : onCancel}>
      <div style={cardStyle} onClick={(event) => event.stopPropagation()}>
        <div style={titleStyle}>{title}</div>
        <p style={textStyle}>{message}</p>
        <div style={footerStyle}>
          <button type="button" onClick={onCancel} style={cancelButtonStyle} disabled={busy}>
            {cancelLabel}
          </button>
          <button type="button" onClick={onConfirm} style={confirmButtonStyle} disabled={busy}>
            {busy ? 'Procesando...' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

const backdropStyle = {
  position: 'fixed',
  inset: 0,
  background: 'rgba(0, 0, 0, 0.6)',
  display: 'grid',
  placeItems: 'center',
  zIndex: 1000,
  padding: 16,
};

const cardStyle = {
  width: '100%',
  maxWidth: 420,
  borderRadius: 20,
  border: '1px solid var(--vg-f-ff9191-a300)',
  background: 'linear-gradient(180deg, var(--vg-s-1c0c0c-a980) 0%, var(--vg-s-0a0808-a990) 100%)',
  padding: '22px 22px 18px',
  boxShadow: '0 20px 50px rgba(0, 0, 0, calc(0.45 * var(--vg-shadow-k)))',
};

const titleStyle = {
  color: 'var(--vg-text-strong)',
  fontSize: 19,
  fontWeight: 800,
  marginBottom: 8,
};

const textStyle = {
  margin: 0,
  color: 'var(--vg-f-d2c3c3)',
  lineHeight: 1.6,
  fontSize: 14,
};

const footerStyle = {
  display: 'flex',
  justifyContent: 'flex-end',
  gap: 10,
  marginTop: 20,
  flexWrap: 'wrap',
};

const cancelButtonStyle = {
  border: '1px solid rgba(var(--vg-ink), 0.16)',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'rgba(var(--vg-ink), 0.05)',
  color: 'var(--vg-text-strong)',
  fontWeight: 700,
  cursor: 'pointer',
};

const confirmButtonStyle = {
  border: '1px solid var(--vg-f-ff7e7e-a400)',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'rgba(145, 33, 33, 0.35)',
  color: 'var(--vg-f-ffd3d3)',
  fontWeight: 700,
  cursor: 'pointer',
};

export default ConfirmModal;

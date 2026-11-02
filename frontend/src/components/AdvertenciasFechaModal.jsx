import { useEffect, useState } from 'react';
import useMobileBackHandler from '../hooks/useMobileBackHandler';

// El servidor respondio 409 `requiere_confirmacion`: lo que se esta registrando o corrigiendo toca un dia ya
// cerrado (caja o conciliacion), cambia de mes, etc. Cada advertencia se muestra completa y hay que marcar que se
// entiende antes de continuar; al confirmar, se devuelven los codigos aceptados para reenviar la peticion.
function AdvertenciasFechaModal({ open, advertencias = [], onConfirm, onCancel, busy = false }) {
  const [entendido, setEntendido] = useState(false);
  useMobileBackHandler(open && !busy, onCancel);

  useEffect(() => {
    if (open) setEntendido(false);
  }, [open]);

  if (!open) return null;

  return (
    <div style={backdropStyle} onClick={busy ? undefined : onCancel}>
      <div style={cardStyle} onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
        <div style={titleStyle}>Revisa antes de continuar</div>
        <div style={{ display: 'grid', gap: 10 }}>
          {advertencias.map((advertencia) => (
            <div key={advertencia.codigo} style={warningStyle}>
              <div style={{ fontWeight: 700 }}>{advertencia.mensaje}</div>
              {(advertencia.detalle || []).map((linea) => (
                <div key={linea} style={{ fontSize: 12.5, opacity: 0.85 }}>{linea}</div>
              ))}
            </div>
          ))}
        </div>
        <label style={checkStyle}>
          <input type="checkbox" checked={entendido} onChange={(event) => setEntendido(event.target.checked)} disabled={busy} />
          <span>Entiendo que esto cambia los totales de esos días y quiero continuar.</span>
        </label>
        <div style={footerStyle}>
          <button type="button" onClick={onCancel} style={cancelButtonStyle} disabled={busy}>Cancelar</button>
          <button
            type="button"
            onClick={() => onConfirm(advertencias.map((advertencia) => advertencia.codigo))}
            style={{ ...confirmButtonStyle, opacity: entendido && !busy ? 1 : 0.5, cursor: entendido && !busy ? 'pointer' : 'not-allowed' }}
            disabled={!entendido || busy}
          >
            {busy ? 'Procesando...' : 'Confirmar y continuar'}
          </button>
        </div>
      </div>
    </div>
  );
}

const backdropStyle = { position: 'fixed', inset: 0, background: 'rgba(0, 0, 0, 0.6)', display: 'grid', placeItems: 'center', zIndex: 1100, padding: 16 };
const cardStyle = {
  width: '100%', maxWidth: 480, maxHeight: '90vh', overflowY: 'auto', borderRadius: 20,
  border: '1px solid var(--vg-f-ff9191-a300)',
  background: 'linear-gradient(180deg, var(--vg-s-1c0c0c-a980) 0%, var(--vg-s-0a0808-a990) 100%)',
  padding: '22px 22px 18px', boxShadow: '0 20px 50px rgba(0, 0, 0, calc(0.45 * var(--vg-shadow-k)))',
};
const titleStyle = { color: 'var(--vg-text-strong)', fontSize: 19, fontWeight: 800, marginBottom: 12 };
const warningStyle = {
  padding: '10px 12px', borderRadius: 12, border: '1px solid var(--vg-f-ffcd56-a400)',
  background: 'rgba(255, 205, 86, 0.12)', color: 'var(--vg-f-ffcd56)', fontSize: 13.5, lineHeight: 1.5,
};
const checkStyle = { display: 'flex', gap: 10, alignItems: 'flex-start', marginTop: 14, color: 'var(--vg-f-d2c3c3)', fontSize: 13.5, lineHeight: 1.5 };
const footerStyle = { display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 18, flexWrap: 'wrap' };
const cancelButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.16)', borderRadius: 999, padding: '10px 16px', background: 'rgba(var(--vg-ink), 0.05)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer' };
const confirmButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, var(--vg-accent-primary) 100%)', color: '#fff', fontWeight: 700 };

export default AdvertenciasFechaModal;

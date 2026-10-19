import { useState } from 'react';
import { formatMonto, postLotePos } from '../utils/lotesPos';

// ID del reporte detallado que imprime el punto de venta al cerrar su lote (ej. 0061). El banco lo repite en cada
// credito del punto, asi la conciliacion bancaria une esos creditos con este lote aunque el banco los acredite en
// varias partes. Al cerrar un lote es opcional (se puede cargar despues); al editar se puede corregir o borrar.
export default function IdReporteLoteModal({ modo, lote, onClose, onDone }) {
  const [valor, setValor] = useState(lote.id_reporte_punto || '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const cerrando = modo === 'cerrar';

  const guardar = async (event) => {
    event.preventDefault();
    setError('');
    setSaving(true);
    try {
      const json = await postLotePos(
        cerrando
          ? { action: 'cerrar_lote', lote_id: lote.id, id_reporte_punto: valor }
          : { action: 'registrar_id_reporte', lote_id: lote.id, id_reporte_punto: valor },
      );
      onDone(json.message || 'Listo.');
    } catch (requestError) {
      setError(requestError.message);
      setSaving(false);
    }
  };

  return (
    <div style={backdropStyle} onClick={saving ? undefined : onClose}>
      <form style={modalCardStyle} onClick={(event) => event.stopPropagation()} onSubmit={guardar}>
        <div style={modalTitleStyle}>{cerrando ? `Cerrar ${lote.codigo}` : `ID del reporte · ${lote.codigo}`}</div>
        {cerrando ? (
          <div style={mutedStyle}>
            ¿Cerrar el lote por ${formatMonto(lote.monto_usd)}? Se imprimirá el detalle de cada cobro para compararlo con el cierre del punto, y los
            próximos cobros de {lote.metodo_pago_nombre} abrirán un lote nuevo.
          </div>
        ) : null}
        <label style={fieldStyle}>ID del reporte detallado del punto{cerrando ? ' (opcional, se puede cargar después)' : ''}
          <input
            type="text"
            value={valor}
            onChange={(event) => setValor(event.target.value)}
            placeholder="Ej: 0061"
            maxLength={40}
            autoFocus
            style={inputStyle}
          />
        </label>
        <div style={mutedStyle}>
          Es el número del reporte (cierre de lote) que imprime el punto de venta. El banco lo repite en cada crédito del punto
          (por ejemplo «POS MAE 88013794 001 <strong>0061</strong> 3009»): con ese ID la conciliación bancaria une esos créditos con este lote.
          {!cerrando ? ' Déjalo vacío para borrarlo.' : ''}
        </div>
        {error ? <div style={noticeStyle}>{error}</div> : null}
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button type="button" onClick={onClose} disabled={saving} style={secondaryButtonStyle}>Cancelar</button>
          <button type="submit" disabled={saving} style={primaryButtonStyle}>
            {saving ? 'Guardando...' : cerrando ? 'Cerrar lote' : 'Guardar'}
          </button>
        </div>
      </form>
    </div>
  );
}

const backdropStyle = { position: 'fixed', inset: 0, background: 'rgba(0, 0, 0, 0.65)', display: 'grid', placeItems: 'center', zIndex: 1000, padding: 16, overflowY: 'auto' };
const modalCardStyle = { width: 'min(640px, 100%)', maxHeight: '92vh', overflowY: 'auto', display: 'grid', gap: 14, padding: 22, borderRadius: 20, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-140b0b)', boxShadow: '0 30px 80px rgba(0, 0, 0, calc(0.6 * var(--vg-shadow-k)))' };
const modalTitleStyle = { color: 'var(--vg-text-strong)', fontSize: 21, fontWeight: 800 };
const fieldStyle = { display: 'grid', gap: 6, color: 'var(--vg-f-f2e6e6)', fontSize: 13, fontWeight: 700 };
const inputStyle = { borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-161010)', padding: '10px 12px', color: 'var(--vg-text-strong)', width: '100%', boxSizing: 'border-box' };
const mutedStyle = { color: 'var(--vg-f-a89999)', fontSize: 12, display: 'block' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid var(--vg-f-ff9191-a220)', background: 'rgba(255,98,98,0.12)', color: 'var(--vg-f-ffd8d8)' };
const secondaryButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.18)', borderRadius: 999, padding: '10px 18px', background: 'rgba(var(--vg-ink), 0.05)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer' };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 18px', background: 'linear-gradient(90deg, #bf1f1f 0%, var(--vg-accent-primary) 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };

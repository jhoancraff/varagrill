import { useEffect, useState } from 'react';

// Inhabilitar (o rehabilitar) un gasto: el sistema primero calcula qué va a cambiar (vista previa), cada advertencia
// hay que aceptarla y el motivo es obligatorio — todo queda guardado como auditoría (ver gastos_inhabilitacion.py).
function getCookie(name) {
  const partes = `; ${document.cookie}`.split(`; ${name}=`);
  return partes.length === 2 ? partes.pop().split(';').shift() : '';
}

function InhabilitarGastoModal({ gasto, onClose, onDone }) {
  const rehabilita = Boolean(gasto.inhabilitado);
  const accion = rehabilita ? 'rehabilitar' : 'inhabilitar';
  const url = `/api/admin/gastos/${gasto.id}/inhabilitar/`;
  const [vista, setVista] = useState(null);
  const [error, setError] = useState('');
  const [aceptadas, setAceptadas] = useState({});
  const [motivo, setMotivo] = useState('');
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    let cancelado = false;
    fetch(`${url}?accion=${accion}`, { credentials: 'include', cache: 'no-store' })
      .then((respuesta) => respuesta.json().then((data) => ({ respuesta, data })))
      .then(({ respuesta, data }) => {
        if (cancelado) return;
        if (!respuesta.ok || !data.ok) setError(data.message || 'No se pudo calcular el efecto.');
        else setVista(data);
      })
      .catch(() => { if (!cancelado) setError('Error de red al calcular el efecto.'); });
    return () => { cancelado = true; };
  }, [url, accion]);

  const advertencias = vista?.advertencias || [];
  const bloqueos = vista?.bloqueos || [];
  const minimo = vista?.motivo_minimo || 10;
  const todoAceptado = advertencias.every((a) => aceptadas[a.codigo]);
  const motivoValido = motivo.trim().length >= minimo;
  const puedeConfirmar = Boolean(vista) && bloqueos.length === 0 && todoAceptado && motivoValido && !guardando;

  const confirmar = async () => {
    setGuardando(true);
    setError('');
    try {
      const respuesta = await fetch(url, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') || '' },
        body: JSON.stringify({
          accion, motivo: motivo.trim(), aceptadas: advertencias.filter((a) => aceptadas[a.codigo]).map((a) => a.codigo),
        }),
      });
      const data = await respuesta.json().catch(() => ({}));
      if (!respuesta.ok || !data.ok) {
        // Si el efecto cambió mientras tanto (otra advertencia nueva), se vuelve a mostrar completo.
        throw new Error(data.message || 'No se pudo completar.');
      }
      onDone(data.message);
    } catch (e) {
      setError(e.message);
      setGuardando(false);
    }
  };

  return (
    <div style={backdropStyle} onClick={guardando ? undefined : onClose}>
      <div style={cardStyle} onClick={(e) => e.stopPropagation()}>
        <div style={headerStyle}>
          <div style={titleStyle}>{rehabilita ? 'Rehabilitar' : 'Inhabilitar'} gasto #{gasto.id}</div>
          <button type="button" onClick={onClose} style={closeStyle} disabled={guardando} aria-label="Cerrar">✕</button>
        </div>
        <div style={mutedStyle}>{gasto.descripcion} · ${Number(gasto.monto).toFixed(2)} · {gasto.fecha_gasto}</div>

        {!vista && !error ? <div style={mutedStyle}>Calculando qué cambia...</div> : null}

        {bloqueos.map((b) => <div key={b.codigo} style={bloqueoStyle}>{b.mensaje}</div>)}

        {advertencias.map((a) => (
          <label key={a.codigo} style={{ ...avisoStyle, cursor: bloqueos.length ? 'default' : 'pointer' }}>
            <input
              type="checkbox"
              checked={Boolean(aceptadas[a.codigo])}
              onChange={(e) => setAceptadas({ ...aceptadas, [a.codigo]: e.target.checked })}
              disabled={bloqueos.length > 0}
              style={{ marginTop: 3 }}
            />
            <span style={{ display: 'grid', gap: 3 }}>
              <span style={{ fontWeight: 700 }}>{a.mensaje}</span>
              {(a.detalle || []).map((linea) => <span key={linea} style={{ fontSize: 12.5, opacity: 0.9 }}>{linea}</span>)}
            </span>
          </label>
        ))}

        {vista && bloqueos.length === 0 ? (
          <label style={{ display: 'grid', gap: 6 }}>
            <span style={labelStyle}>Motivo para la auditoría (obligatorio)</span>
            <textarea
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              rows={3}
              placeholder={rehabilita ? 'Ej: se había inhabilitado por error' : 'Ej: el gasto se cargó dos veces'}
              style={inputStyle}
            />
            <span style={{ ...mutedStyle, color: motivoValido ? 'var(--vg-f-9fe3b0)' : undefined }}>
              {motivo.trim().length} / {minimo} caracteres como mínimo
            </span>
          </label>
        ) : null}

        {error ? <div style={bloqueoStyle}>{error}</div> : null}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button type="button" onClick={onClose} style={secondaryButtonStyle} disabled={guardando}>Cancelar</button>
          <button type="button" onClick={confirmar} style={rehabilita ? primaryButtonStyle : peligroButtonStyle(puedeConfirmar)} disabled={!puedeConfirmar}>
            {guardando ? 'Guardando...' : rehabilita ? 'Rehabilitar gasto' : 'Inhabilitar gasto'}
          </button>
        </div>
      </div>
    </div>
  );
}

const backdropStyle = { position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,0.6)', display: 'grid', placeItems: 'center', padding: 16, overflowY: 'auto' };
const cardStyle = { width: '100%', maxWidth: 520, maxHeight: '90vh', overflowY: 'auto', borderRadius: 20, border: '1px solid var(--vg-f-ff9191-a300)', background: 'linear-gradient(180deg, var(--vg-s-1c0c0c-a980) 0%, var(--vg-s-0a0808-a990) 100%)', padding: '22px 22px 18px', boxShadow: '0 20px 50px rgba(0, 0, 0, calc(0.45 * var(--vg-shadow-k)))', display: 'grid', gap: 12 };
const headerStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center' };
const titleStyle = { color: 'var(--vg-text-strong)', fontSize: 19, fontWeight: 800 };
const closeStyle = { border: 'none', background: 'rgba(var(--vg-ink), 0.08)', color: 'var(--vg-text-strong)', width: 30, height: 30, borderRadius: 999, cursor: 'pointer', fontSize: 14 };
const mutedStyle = { color: 'var(--vg-f-c8bbbb)', fontSize: 12.5 };
const labelStyle = { color: 'var(--vg-f-f0b4b4)', fontSize: 12.5, fontWeight: 700 };
const inputStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 10, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-161010)', padding: '9px 10px', color: 'var(--vg-text-strong)', fontSize: 13, resize: 'vertical' };
const avisoStyle = { display: 'flex', gap: 10, alignItems: 'flex-start', padding: '10px 12px', borderRadius: 12, border: '1px solid var(--vg-f-ffcf7d-a450)', background: 'rgba(255, 207, 125, 0.08)', color: 'var(--vg-f-ffe3a3)', fontSize: 13 };
const bloqueoStyle = { padding: '10px 12px', borderRadius: 12, border: '1px solid var(--vg-f-ff9191-a220)', background: 'rgba(255, 98, 98, 0.12)', color: 'var(--vg-f-ffd8d8)', fontSize: 13 };
const secondaryButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.14)', borderRadius: 999, padding: '9px 16px', background: 'rgba(var(--vg-ink), 0.04)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer', fontSize: 13 };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 18px', background: 'linear-gradient(90deg, #bf1f1f 0%, var(--vg-accent-primary) 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const peligroButtonStyle = (activo) => ({ ...primaryButtonStyle, opacity: activo ? 1 : 0.5, cursor: activo ? 'pointer' : 'not-allowed' });

export default InhabilitarGastoModal;

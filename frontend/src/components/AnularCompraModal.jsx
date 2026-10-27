import { useEffect, useState } from 'react';

// Anular una factura de compra: el sistema primero calcula qué va a cambiar (vista previa: cómo queda el stock de cada
// ingrediente, qué pasa con lo ya pagado), cada advertencia hay que aceptarla y el motivo es obligatorio — todo queda
// guardado como auditoría (ver compras_anulacion.py).
function getCookie(name) {
  const partes = `; ${document.cookie}`.split(`; ${name}=`);
  return partes.length === 2 ? partes.pop().split(';').shift() : '';
}

const formatoCantidad = (valor) => {
  const numero = Number(valor);
  return Number.isFinite(numero) ? numero.toLocaleString('es-VE', { maximumFractionDigits: 2 }) : valor;
};

function AnularCompraModal({ compra, onClose, onDone }) {
  const url = `/api/admin/compras/${compra.id}/anular/`;
  const [vista, setVista] = useState(null);
  const [error, setError] = useState('');
  const [aceptadas, setAceptadas] = useState({});
  const [motivo, setMotivo] = useState('');
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    let cancelado = false;
    fetch(url, { credentials: 'include', cache: 'no-store' })
      .then((respuesta) => respuesta.json().then((data) => ({ respuesta, data })))
      .then(({ respuesta, data }) => {
        if (cancelado) return;
        if (!respuesta.ok || !data.ok) setError(data.message || 'No se pudo calcular el efecto.');
        else setVista(data);
      })
      .catch(() => { if (!cancelado) setError('Error de red al calcular el efecto.'); });
    return () => { cancelado = true; };
  }, [url]);

  const advertencias = vista?.advertencias || [];
  const bloqueos = vista?.bloqueos || [];
  const stock = vista?.stock || [];
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
        body: JSON.stringify({ motivo: motivo.trim(), aceptadas: advertencias.filter((a) => aceptadas[a.codigo]).map((a) => a.codigo) }),
      });
      const data = await respuesta.json().catch(() => ({}));
      if (!respuesta.ok || !data.ok) {
        // Si el efecto cambió mientras tanto (otra advertencia nueva, otro stock), hay que volver a abrirlo.
        throw new Error(data.message || 'No se pudo anular la factura.');
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
          <div style={titleStyle}>Anular factura · Lote #{compra.id}</div>
          <button type="button" onClick={onClose} style={closeStyle} disabled={guardando} aria-label="Cerrar">✕</button>
        </div>
        <div style={mutedStyle}>
          {compra.proveedor_nombre}{compra.numero_factura_proveedor ? ` · Factura ${compra.numero_factura_proveedor}` : ''} · ${Number(compra.total).toFixed(2)}
        </div>

        {!vista && !error ? <div style={mutedStyle}>Calculando qué cambia...</div> : null}

        {stock.length > 0 ? (
          <div style={stockBoxStyle}>
            <div style={{ fontWeight: 800, color: 'var(--vg-text-strong)', fontSize: 13 }}>Así queda el stock</div>
            {stock.map((linea) => {
              const negativo = Number(linea.stock_despues) < 0;
              return (
                <div key={linea.ingrediente_id} style={stockRowStyle}>
                  <span>{linea.nombre}</span>
                  <span style={{ color: negativo ? 'var(--vg-f-ff9d9d)' : undefined, fontWeight: 700 }}>
                    {formatoCantidad(linea.stock_antes)} → {formatoCantidad(linea.stock_despues)} {linea.unidad}
                  </span>
                </div>
              );
            })}
          </div>
        ) : null}

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
              placeholder="Ej: la factura se cargó con el proveedor equivocado"
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
          <button type="button" onClick={confirmar} style={peligroButtonStyle(puedeConfirmar)} disabled={!puedeConfirmar}>
            {guardando ? 'Anulando...' : 'Anular factura'}
          </button>
        </div>
      </div>
    </div>
  );
}

const backdropStyle = { position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,0.6)', display: 'grid', placeItems: 'center', padding: 16, overflowY: 'auto' };
const cardStyle = { width: '100%', maxWidth: 540, maxHeight: '90vh', overflowY: 'auto', borderRadius: 20, border: '1px solid var(--vg-f-ff9191-a300)', background: 'linear-gradient(180deg, var(--vg-s-1c0c0c-a980) 0%, var(--vg-s-0a0808-a990) 100%)', padding: '22px 22px 18px', boxShadow: '0 20px 50px rgba(0, 0, 0, calc(0.45 * var(--vg-shadow-k)))', display: 'grid', gap: 12 };
const headerStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center' };
const titleStyle = { color: 'var(--vg-text-strong)', fontSize: 19, fontWeight: 800 };
const closeStyle = { border: 'none', background: 'rgba(var(--vg-ink), 0.08)', color: 'var(--vg-text-strong)', width: 30, height: 30, borderRadius: 999, cursor: 'pointer', fontSize: 14 };
const mutedStyle = { color: 'var(--vg-f-c8bbbb)', fontSize: 12.5 };
const labelStyle = { color: 'var(--vg-f-f0b4b4)', fontSize: 12.5, fontWeight: 700 };
const inputStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 10, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-161010)', padding: '9px 10px', color: 'var(--vg-text-strong)', fontSize: 13, resize: 'vertical' };
const stockBoxStyle = { display: 'grid', gap: 6, padding: '10px 12px', borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.12)', background: 'rgba(var(--vg-ink), 0.04)' };
const stockRowStyle = { display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 13, color: 'var(--vg-f-d2c4c4)' };
const avisoStyle = { display: 'flex', gap: 10, alignItems: 'flex-start', padding: '10px 12px', borderRadius: 12, border: '1px solid var(--vg-f-ffcf7d-a450)', background: 'rgba(255, 207, 125, 0.08)', color: 'var(--vg-f-ffe3a3)', fontSize: 13 };
const bloqueoStyle = { padding: '10px 12px', borderRadius: 12, border: '1px solid var(--vg-f-ff9191-a220)', background: 'rgba(255, 98, 98, 0.12)', color: 'var(--vg-f-ffd8d8)', fontSize: 13 };
const secondaryButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.14)', borderRadius: 999, padding: '9px 16px', background: 'rgba(var(--vg-ink), 0.04)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer', fontSize: 13 };
const peligroButtonStyle = (activo) => ({ border: 'none', borderRadius: 999, padding: '10px 18px', background: 'linear-gradient(90deg, #bf1f1f 0%, var(--vg-accent-primary) 100%)', color: '#fff', fontWeight: 700, opacity: activo ? 1 : 0.5, cursor: activo ? 'pointer' : 'not-allowed' });

export default AnularCompraModal;

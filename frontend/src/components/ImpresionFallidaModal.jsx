import { useEffect, useState } from 'react';
import useMobileBackHandler from '../hooks/useMobileBackHandler';

function getCookie(name) {
  const all = `; ${document.cookie}`;
  const parts = all.split(`; ${name}=`);
  if (parts.length === 2) {
    return parts.pop().split(';').shift();
  }
  return '';
}

// Aviso que NO se quita solo cuando la comanda física no salió en alguna impresora,
// aunque el pedido ya quedó registrado (y visible en Caja). `aviso` es
// { pedidoId, fallidas: [{ nombre, destino, motivo }] } — la forma en que el backend
// reporta `impresion` (ver resumir_resultados_impresion). "Reintentar" reenvía la
// comanda SOLO a las impresoras que fallaron, para no duplicarla en las que sí
// imprimieron; si vuelve a fallar, el aviso se queda con lo que siga fallando.
function ImpresionFallidaModal({ aviso, onCerrar }) {
  const [fallidas, setFallidas] = useState(aviso ? aviso.fallidas : []);
  const [reintentando, setReintentando] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setFallidas(aviso ? aviso.fallidas : []);
    setError('');
  }, [aviso]);

  useMobileBackHandler(Boolean(aviso) && !reintentando, onCerrar);

  if (!aviso) {
    return null;
  }

  const handleReintentar = async () => {
    if (reintentando) return;
    setReintentando(true);
    setError('');
    try {
      const destinos = fallidas.map((f) => f.destino).filter(Boolean);
      const response = await fetch(`/api/pedidos/${aviso.pedidoId}/reimprimir-comanda/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') || '' },
        credentials: 'include',
        body: JSON.stringify({ destinos }),
      });
      const data = await response.json().catch(() => ({}));
      if (response.ok && data.ok) {
        onCerrar();
        return;
      }
      if (data.impresion && Array.isArray(data.impresion.fallidas) && data.impresion.fallidas.length > 0) {
        setFallidas(data.impresion.fallidas);
      }
      setError('Sigue sin imprimir. Revisa la impresora o avísale a cocina de palabra.');
    } catch (requestError) {
      setError('Error de red al reintentar la impresión.');
    } finally {
      setReintentando(false);
    }
  };

  return (
    <div style={backdropStyle} role="alertdialog" aria-modal="true" aria-labelledby="vg-impresion-fallida-titulo">
      <div style={cardStyle}>
        <div id="vg-impresion-fallida-titulo" style={titleStyle}>La comanda NO se imprimió</div>
        <p style={textStyle}>
          El pedido #{aviso.pedidoId} quedó registrado y ya está en Caja, pero el ticket físico no salió
          en {fallidas.length > 1 ? 'estas impresoras' : 'esta impresora'}. Avísale a cocina o reintenta.
        </p>
        <ul style={listStyle}>
          {fallidas.map((f) => (
            <li key={`${f.nombre}-${f.destino}`} style={itemStyle}>
              <strong>{f.nombre}</strong>
              {f.destino ? <span style={destinoStyle}> {f.destino}</span> : null}
              {f.motivo ? <div style={motivoStyle}>{f.motivo}</div> : null}
            </li>
          ))}
        </ul>
        {error ? <div style={errorStyle}>{error}</div> : null}
        <div style={footerStyle}>
          <button type="button" onClick={onCerrar} style={cancelButtonStyle} disabled={reintentando}>
            Entendido
          </button>
          <button type="button" onClick={handleReintentar} style={retryButtonStyle} disabled={reintentando}>
            {reintentando ? 'Reintentando...' : 'Reintentar impresión'}
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
  zIndex: 1100,
  padding: 16,
};

const cardStyle = {
  width: '100%',
  maxWidth: 440,
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

const listStyle = {
  listStyle: 'none',
  margin: '14px 0 0',
  padding: 0,
  display: 'grid',
  gap: 8,
};

const itemStyle = {
  borderRadius: 12,
  border: '1px solid rgba(var(--vg-ink), 0.14)',
  background: 'rgba(var(--vg-ink), 0.05)',
  padding: '10px 12px',
  color: 'var(--vg-text-strong)',
  fontSize: 14,
};

const destinoStyle = {
  color: 'var(--vg-f-d2c3c3)',
  fontSize: 12.5,
};

const motivoStyle = {
  color: 'var(--vg-f-d2c3c3)',
  fontSize: 12.5,
  marginTop: 2,
};

const errorStyle = {
  marginTop: 12,
  color: 'var(--vg-text-strong)',
  fontSize: 13,
  fontWeight: 700,
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

const retryButtonStyle = {
  border: '1px solid var(--vg-f-ff7e7e-a400)',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'rgba(145, 33, 33, 0.35)',
  color: 'var(--vg-f-ffd3d3)',
  fontWeight: 700,
  cursor: 'pointer',
};

export default ImpresionFallidaModal;

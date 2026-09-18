import { useCallback, useEffect, useState } from 'react';
import BsAmount from './BsAmount';
import Toast from './Toast';
import useExchangeRate from '../hooks/useExchangeRate';
import useToast from '../hooks/useToast';

function getCookie(name) {
  const all = `; ${document.cookie}`;
  const parts = all.split(`; ${name}=`);
  if (parts.length === 2) {
    return parts.pop().split(';').shift();
  }
  return '';
}

const TIPO_LABEL = {
  llevar: 'Para llevar',
  delivery: 'Delivery',
  local: 'Local',
};

// Mismos estados que BILLABLE_ORDER_STATES en el backend (ver pedidos_cobro_view):
// el pedido ya aparece en Caja apenas llega a alguno de estos.
const ESTADOS_FACTURABLES = ['en_preparacion', 'listo', 'entregado'];

function formatItemLabel(item) {
  if (item.venta_por_peso && item.peso_gramos) {
    return `${Number(item.peso_gramos)} g`;
  }
  return `${item.cantidad}x`;
}

function PedidoConfirmacionPage({ isMobile, pedidoId, onBack, onIrACaja }) {
  const tasaCambio = useExchangeRate();
  const { toast, showSuccess, showError, hideToast } = useToast();
  const [pedido, setPedido] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [confirmando, setConfirmando] = useState(false);
  const [reimprimiendo, setReimprimiendo] = useState(false);

  const loadPedido = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch(`/api/pedidos/${pedidoId}/`, { credentials: 'include', cache: 'no-store' });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo cargar el pedido.');
      }
      setPedido(data.pedido);
    } catch (requestError) {
      setError(requestError.message || 'No se pudo cargar el pedido.');
      setPedido(null);
    } finally {
      setLoading(false);
    }
  }, [pedidoId]);

  useEffect(() => {
    loadPedido();
  }, [loadPedido]);

  const esFacturable = pedido ? ESTADOS_FACTURABLES.includes(pedido.estado) : false;
  const necesitaConfirmar = pedido ? pedido.estado === 'pendiente' : false;

  // Igual que "Iniciar preparación" en MesasAtendidasPage: es lo que de verdad manda
  // a imprimir la comanda (ver _notify_cocina_event en el backend, solo imprime al
  // pasar a 'en_preparacion') y lo que hace que el pedido aparezca en Caja
  // (BILLABLE_ORDER_STATES). Sin este paso, un pedido para llevar/delivery sin mesa
  // se quedaba invisible: no aparecía en Mesas atendidas (requiere mesa) ni en Caja
  // (sigue 'pendiente'), así que no había forma de cobrarlo.
  const handleConfirmarEImprimir = async () => {
    if (confirmando) return;
    setConfirmando(true);
    try {
      const response = await fetch(`/api/pedidos/${pedidoId}/estado/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') || '' },
        credentials: 'include',
        body: JSON.stringify({ estado: 'en_preparacion' }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo confirmar el pedido.');
      }
      showSuccess('Comanda enviada a imprimir. El pedido ya está disponible en Caja para cobrarlo.');
      await loadPedido();
    } catch (requestError) {
      showError(requestError.message || 'No se pudo confirmar el pedido.');
    } finally {
      setConfirmando(false);
    }
  };

  const handleReimprimir = async () => {
    if (reimprimiendo) return;
    setReimprimiendo(true);
    try {
      const response = await fetch(`/api/pedidos/${pedidoId}/reimprimir-comanda/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCookie('csrftoken') || '' },
        credentials: 'include',
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo reimprimir la comanda.');
      }
      showSuccess(data.message || 'Comanda reimpresa correctamente.');
    } catch (requestError) {
      showError(requestError.message || 'No se pudo reimprimir la comanda.');
    } finally {
      setReimprimiendo(false);
    }
  };

  return (
    <section style={containerStyle(isMobile)}>
      <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          ← Volver
        </button>
      </div>

      <Toast toast={toast} onClose={hideToast} />

      {loading ? <div style={emptyStyle}>Cargando pedido...</div> : null}
      {!loading && error ? <div style={noticeStyle}>{error}</div> : null}

      {!loading && pedido ? (
        <>
          <div>
            <h2 style={titleStyle(isMobile)}>
              Pedido #{pedido.id} — {TIPO_LABEL[pedido.tipo_pedido] || pedido.tipo_pedido}
            </h2>
            <p style={subtitleStyle}>
              Revisa los datos antes de mandar a imprimir. Confirmar el pedido es lo que lo envía a cocina
              (si aplica) y lo hace aparecer en Caja para cobrarlo.
            </p>
          </div>

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Datos del cliente</div>
            <div style={datosGridStyle(isMobile)}>
              <div>
                <div style={labelStyle}>Cliente</div>
                <div style={valueStyle}>{pedido.cliente_nombre || '—'}</div>
              </div>
              <div>
                <div style={labelStyle}>Cédula</div>
                <div style={valueStyle}>{pedido.cliente_cedula || '—'}</div>
              </div>
              <div>
                <div style={labelStyle}>Teléfono</div>
                <div style={valueStyle}>{pedido.cliente_telefono || '—'}</div>
              </div>
            </div>
            {pedido.notas ? (
              <div>
                <div style={labelStyle}>Notas / dirección</div>
                <div style={valueStyle}>{pedido.notas}</div>
              </div>
            ) : null}
          </section>

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Platos</div>
            <div style={itemsListStyle}>
              {pedido.items.map((item) => (
                <div key={item.id} style={itemRowStyle}>
                  <div style={itemHeaderStyle}>
                    <span style={itemNombreStyle}>{formatItemLabel(item)} {item.producto_nombre}</span>
                    <span style={itemSubtotalStyle}>
                      ${Number(item.subtotal).toFixed(2)}
                      <BsAmount amountUsd={item.subtotal} tasa={tasaCambio} />
                    </span>
                  </div>
                  {(item.adicionales.length > 0 || item.opciones.length > 0) ? (
                    <div style={itemExtraStyle}>
                      {[...item.adicionales, ...item.opciones].map((extra) => extra.nombre).join(' · ')}
                    </div>
                  ) : null}
                  {item.notas ? <div style={itemExtraStyle}>Nota: {item.notas}</div> : null}
                </div>
              ))}
            </div>
          </section>

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Total</div>
            <div style={totalesGridStyle}>
              <div style={totalRowStyle}><span>Subtotal</span><span>${Number(pedido.subtotal).toFixed(2)}</span></div>
              {Number(pedido.impuesto) > 0 ? (
                <div style={totalRowStyle}><span>Impuesto</span><span>${Number(pedido.impuesto).toFixed(2)}</span></div>
              ) : null}
              {Number(pedido.descuento) > 0 ? (
                <div style={totalRowStyle}><span>Descuento</span><span>−${Number(pedido.descuento).toFixed(2)}</span></div>
              ) : null}
              {Number(pedido.propina) > 0 ? (
                <div style={totalRowStyle}><span>Propina</span><span>${Number(pedido.propina).toFixed(2)}</span></div>
              ) : null}
              <div style={{ ...totalRowStyle, fontWeight: 800, fontSize: 17, color: '#fff' }}>
                <span>Total</span>
                <span>
                  ${Number(pedido.total).toFixed(2)}
                  <BsAmount amountUsd={pedido.total} tasa={tasaCambio} />
                </span>
              </div>
            </div>
          </section>

          <section style={{ ...panelStyle, gap: 12 }}>
            <div style={estadoBadgeRowStyle}>
              {esFacturable ? (
                <span style={estadoBadgeStyle(true)}>✓ Listo para cobrar en Caja</span>
              ) : (
                <span style={estadoBadgeStyle(false)}>Aún no está en Caja — confirma primero</span>
              )}
            </div>

            <div style={actionsRowStyle(isMobile)}>
              {necesitaConfirmar ? (
                <button type="button" onClick={handleConfirmarEImprimir} disabled={confirmando} style={primaryButtonStyle}>
                  {confirmando ? 'Enviando...' : 'Confirmar y mandar a imprimir'}
                </button>
              ) : (
                <button type="button" onClick={handleReimprimir} disabled={reimprimiendo} style={secondaryButtonStyle}>
                  {reimprimiendo ? 'Reimprimiendo...' : 'Reimprimir comanda'}
                </button>
              )}
              <button
                type="button"
                onClick={onIrACaja}
                disabled={!esFacturable}
                style={esFacturable ? primaryButtonStyle : disabledButtonStyle}
                title={esFacturable ? '' : 'Confirma el pedido antes de ir a Caja.'}
              >
                Ir a Caja →
              </button>
            </div>
          </section>
        </>
      ) : null}
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 26 : 32 });
const subtitleStyle = { margin: '8px 0 0', color: '#d2c3c3', lineHeight: 1.6, maxWidth: 680 };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const sectionTitleStyle = { color: '#fff', fontSize: 17, fontWeight: 700 };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };

const datosGridStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, minmax(0,1fr))', gap: 14 });
const labelStyle = { color: '#ffb0b0', fontSize: 11.5, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' };
const valueStyle = { color: '#f2e6e6', fontSize: 14.5, marginTop: 2 };

const itemsListStyle = { display: 'grid', gap: 10 };
const itemRowStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(255,255,255,0.03)' };
const itemHeaderStyle = { display: 'flex', justifyContent: 'space-between', gap: 10 };
const itemNombreStyle = { color: '#fff', fontWeight: 700, fontSize: 14.5 };
const itemSubtotalStyle = { color: '#fff', fontWeight: 700, fontSize: 14.5, whiteSpace: 'nowrap' };
const itemExtraStyle = { color: '#c8bbbb', fontSize: 12.5, marginTop: 4 };

const totalesGridStyle = { display: 'grid', gap: 8 };
const totalRowStyle = { display: 'flex', justifyContent: 'space-between', color: '#d2c3c3', fontSize: 14 };

const estadoBadgeRowStyle = { display: 'flex' };
const estadoBadgeStyle = (ok) => ({
  display: 'inline-flex', alignItems: 'center', padding: '6px 14px', borderRadius: 999,
  fontSize: 13, fontWeight: 700,
  color: ok ? '#8fffb0' : '#ffcf7d',
  background: ok ? 'rgba(70,200,120,0.14)' : 'rgba(255,190,120,0.14)',
  border: ok ? '1px solid rgba(80,200,130,0.3)' : '1px solid rgba(255,190,120,0.3)',
});
const actionsRowStyle = (isMobile) => ({ display: 'flex', flexDirection: isMobile ? 'column' : 'row', gap: 10, flexWrap: 'wrap' });
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '12px 20px', background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: 14 };
const secondaryButtonStyle = { border: '1px solid rgba(255,255,255,0.16)', borderRadius: 999, padding: '12px 20px', background: 'rgba(255,255,255,0.05)', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: 14 };
const disabledButtonStyle = { ...primaryButtonStyle, background: 'rgba(255,255,255,0.06)', color: '#7a6f6f', cursor: 'not-allowed' };

export default PedidoConfirmacionPage;

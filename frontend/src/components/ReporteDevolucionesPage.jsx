import { useCallback, useEffect, useMemo, useState } from 'react';
import useMobileBackHandler from '../hooks/useMobileBackHandler';
import { getFechaSeleccionada, getRangoSeleccionado, setFechaSeleccionada } from '../utils/fechaContabilidad';

function todayIso() {
  const now = new Date();
  const offset = now.getTimezoneOffset();
  const local = new Date(now.getTime() - offset * 60000);
  return local.toISOString().slice(0, 10);
}

function formatMonto(value) {
  const number = Number(value || 0);
  return number.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const FILAS_POR_PAGINA = 50;

// Detalle de la card "Devoluciones" del cuadre de caja (diario y por rango):
// una fila por cada VGNotaCredito emitida en el período, con un botón que
// abre el detalle completo (a qué documento anuló/ajustó, qué pasó con el
// dinero, mermas...) en un modal — ver nota_credito_detail_view en
// devoluciones_views.py, mismo endpoint que ya usaba el reporte embebido en
// Cobro (eliminado de ahí: este reemplaza esa pantalla).
function ReporteDevolucionesPage({ isMobile, onBack, onArmarCanje }) {
  const [rango] = useState(() => getRangoSeleccionado());
  const [fecha, setFecha] = useState(() => getFechaSeleccionada(todayIso()));
  const [notas, setNotas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [pagina, setPagina] = useState(0);

  const [notaSeleccionadaId, setNotaSeleccionadaId] = useState(null);
  const [detalle, setDetalle] = useState(null);
  const [loadingDetalle, setLoadingDetalle] = useState(false);
  const [detalleError, setDetalleError] = useState('');

  const loadReport = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (rango) {
        params.set('desde', rango.desde);
        params.set('hasta', rango.hasta);
      } else {
        params.set('desde', fecha);
        params.set('hasta', fecha);
      }
      const response = await fetch(`/api/notas-credito/?${params.toString()}`, {
        credentials: 'include',
        cache: 'no-store',
      });
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudieron cargar las devoluciones.');
      }
      setNotas(Array.isArray(json.notas_credito) ? json.notas_credito : []);
    } catch (requestError) {
      setError(requestError.message || 'No se pudieron cargar las devoluciones.');
      setNotas([]);
    } finally {
      setLoading(false);
    }
  }, [rango, fecha]);

  useEffect(() => {
    loadReport();
    if (!rango) {
      setFechaSeleccionada(fecha);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fecha, rango]);

  const abrirDetalle = async (notaId) => {
    setNotaSeleccionadaId(notaId);
    setDetalle(null);
    setDetalleError('');
    setLoadingDetalle(true);
    try {
      const response = await fetch(`/api/notas-credito/${notaId}/`, { credentials: 'include', cache: 'no-store' });
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cargar el detalle de la nota de crédito.');
      }
      setDetalle(json.nota_credito);
    } catch (requestError) {
      setDetalleError(requestError.message || 'No se pudo cargar el detalle de la nota de crédito.');
    } finally {
      setLoadingDetalle(false);
    }
  };

  const totalMonto = useMemo(
    () => notas.reduce((acc, nota) => acc + Number(nota.monto || 0), 0),
    [notas],
  );

  const totalPaginas = Math.max(1, Math.ceil(notas.length / FILAS_POR_PAGINA));
  const paginaActual = Math.min(pagina, totalPaginas - 1);
  const notasPagina = notas.slice(paginaActual * FILAS_POR_PAGINA, (paginaActual + 1) * FILAS_POR_PAGINA);

  return (
    <section style={containerStyle(isMobile)}>
      <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          ← Volver a Cuadre de caja{rango ? ' por rango' : ''}
        </button>
      </div>

      <div>
        <h2 style={titleStyle(isMobile)}>Devoluciones</h2>
        <p style={subtitleStyle}>
          {rango
            ? `Notas de crédito emitidas entre ${rango.desde} y ${rango.hasta}.`
            : 'Notas de crédito emitidas el'}
          {!rango ? (
            <label style={{ marginLeft: 8 }}>
              <input
                type="date"
                value={fecha}
                max={todayIso()}
                onChange={(event) => setFecha(event.target.value)}
                style={dateInputStyle}
              />
            </label>
          ) : null}
        </p>
      </div>

      {loading ? <div style={emptyStyle}>Cargando devoluciones...</div> : null}
      {!loading && error ? <div style={noticeStyle}>{error}</div> : null}

      {!loading && !error ? (
        notas.length === 0 ? (
          <div style={emptyStyle}>No hay devoluciones registradas en este período.</div>
        ) : (
          <section style={panelStyle}>
            <div style={tableWrapStyle}>
              <div style={tableStyle}>
                <div style={headStyle}>ID</div>
                <div style={headStyle}>Nota de crédito</div>
                <div style={headStyle}>Anclada a</div>
                <div style={headStyle}>Tipo</div>
                <div style={headStyle}>Monto</div>
                <div style={headStyle}>Fecha</div>
                <div style={headStyle}>Detalle</div>
                {notasPagina.map((nota) => (
                  <div key={nota.id} style={rowGroupStyle}>
                    <div style={cellStyle}>{nota.id}</div>
                    <div style={cellStyle}>{nota.codigo}</div>
                    <div style={cellStyle}>
                      {nota.documento_tipo === 'factura' ? 'Factura' : 'Nota de entrega'} {nota.documento_codigo}
                    </div>
                    <div style={cellStyle}>{nota.tipo_resolucion_display}</div>
                    <div style={cellStyle}>${formatMonto(nota.monto)}</div>
                    <div style={cellStyle}>{new Date(nota.fecha_emision).toLocaleString('es-VE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}</div>
                    <div style={cellStyle}>
                      <button type="button" onClick={() => abrirDetalle(nota.id)} style={detalleLinkStyle}>
                        Ver detalle →
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {notas.length > FILAS_POR_PAGINA ? (
              <div style={paginacionRowStyle(isMobile)}>
                <div style={paginacionInfoStyle}>
                  Mostrando {paginaActual * FILAS_POR_PAGINA + 1}–{Math.min((paginaActual + 1) * FILAS_POR_PAGINA, notas.length)} de {notas.length} nota(s)
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <button
                    type="button"
                    onClick={() => setPagina((p) => Math.max(0, p - 1))}
                    disabled={paginaActual === 0}
                    style={paginacionButtonStyle(paginaActual === 0)}
                  >
                    ← Anteriores
                  </button>
                  <span style={{ color: '#c8bbbb', fontSize: 12.5 }}>Página {paginaActual + 1} de {totalPaginas}</span>
                  <button
                    type="button"
                    onClick={() => setPagina((p) => Math.min(totalPaginas - 1, p + 1))}
                    disabled={paginaActual >= totalPaginas - 1}
                    style={paginacionButtonStyle(paginaActual >= totalPaginas - 1)}
                  >
                    Siguientes →
                  </button>
                </div>
              </div>
            ) : null}

            <div style={{ fontWeight: 700, color: '#fff' }}>
              Total devuelto: ${formatMonto(totalMonto)}
            </div>
          </section>
        )
      ) : null}

      {notaSeleccionadaId ? (
        <NotaCreditoDetalleModal
          loading={loadingDetalle}
          error={detalleError}
          detalle={detalle}
          onArmarCanje={onArmarCanje}
          onClose={() => setNotaSeleccionadaId(null)}
        />
      ) : null}
    </section>
  );
}

function NotaCreditoDetalleModal({ loading, error, detalle, onArmarCanje, onClose }) {
  useMobileBackHandler(true, onClose);

  return (
    <div style={modalBackdropStyle} onClick={onClose}>
      <div style={modalCardStyle} onClick={(event) => event.stopPropagation()}>
        <div style={modalHeaderStyle}>
          <div style={modalTitleStyle}>{detalle ? detalle.codigo : 'Detalle de la nota de crédito'}</div>
          <button type="button" onClick={onClose} style={modalCloseButtonStyle}>✕</button>
        </div>

        {loading ? <div style={emptyStyle}>Cargando detalle...</div> : null}
        {!loading && error ? <div style={noticeStyle}>{error}</div> : null}

        {!loading && detalle ? (
          <div style={{ display: 'grid', gap: 10 }}>
            <span style={tipoResolucionBadgeStyle(detalle.tipo_resolucion)}>{detalle.tipo_resolucion_display}</span>
            <div style={{ color: '#d2c4c4', fontSize: 13 }}>{detalle.motivo_display}</div>
            {detalle.motivo_detalle ? (
              <div style={{ color: '#d2c4c4', fontSize: 13, fontStyle: 'italic' }}>&ldquo;{detalle.motivo_detalle}&rdquo;</div>
            ) : null}
            <div style={{ color: '#d2c4c4', fontSize: 13 }}>
              Autorizó: {detalle.autorizado_por} · Registró: {detalle.creado_por || '—'} · {new Date(detalle.fecha_emision).toLocaleString('es-VE')}
            </div>

            <div style={seccionTituloStyle}>
              {['ajuste_parcial', 'canje_item'].includes(detalle.tipo_resolucion) ? 'Documento (sigue vigente)' : 'Documento original anulado'}
            </div>
            {detalle.documento_original ? (
              <div style={lineaRowStyle}>
                <span>{detalle.documento_tipo === 'factura' ? 'Factura' : 'Nota de entrega'} {detalle.documento_codigo} — {detalle.documento_original.estado}</span>
                <span>
                  {['ajuste_parcial', 'canje_item'].includes(detalle.tipo_resolucion)
                    ? `total $${formatMonto(detalle.documento_original.total)}`
                    : `$${formatMonto(detalle.documento_original.total)}`}
                </span>
              </div>
            ) : <div style={{ color: '#a89999', fontSize: 12.5 }}>Documento no disponible.</div>}

            {detalle.item_cambiado ? (
              <>
                <div style={seccionTituloStyle}>Ítem cambiado (el resto del pedido no se tocó)</div>
                <div style={lineaRowStyle}>
                  <span>{detalle.item_cambiado.cantidad}x {detalle.item_cambiado.producto} — Pedido #{detalle.item_cambiado.pedido_id}</span>
                  <span>${formatMonto(detalle.item_cambiado.subtotal)}</span>
                </div>
              </>
            ) : null}

            {detalle.pedidos_reabiertos.length > 0 ? (
              <>
                <div style={seccionTituloStyle}>Plato(s) de cambio (ya cubiertos por el pago original)</div>
                {detalle.pedidos_reabiertos.map((pedido) => (
                  <div key={pedido.id} style={lineaRowStyle}>
                    <span>Pedido #{pedido.id} — {pedido.estado}</span>
                    <span>${formatMonto(pedido.total)}</span>
                  </div>
                ))}
              </>
            ) : ['canje', 'canje_item'].includes(detalle.tipo_resolucion) && onArmarCanje ? (
              <div style={{ ...lineaRowStyle, alignItems: 'center' }}>
                <span style={{ color: '#ffcf7d' }}>Todavía no se armó el plato de cambio.</span>
                <button
                  type="button"
                  onClick={() => {
                    onArmarCanje({ notaCreditoId: detalle.id, cliente: '' });
                    onClose();
                  }}
                  style={armarCanjeButtonStyle}
                >
                  Armar plato de cambio
                </button>
              </div>
            ) : null}

            <div style={seccionTituloStyle}>Pagos revertidos (descontados del cuadre de caja)</div>
            {detalle.pagos_revertidos.length > 0 ? detalle.pagos_revertidos.map((pago) => (
              <div key={pago.id} style={lineaRowStyle}>
                <span>{pago.metodo_pago} · {new Date(pago.fecha_pago).toLocaleDateString('es-VE')}</span>
                <span>-${formatMonto(pago.monto)}</span>
              </div>
            )) : (
              <div style={{ color: '#a89999', fontSize: 12.5 }}>
                {detalle.tipo_resolucion === 'reembolso'
                  ? 'El documento no tenía pagos registrados (se anuló antes de cobrarse).'
                  : 'Ninguno — el dinero nunca salió del negocio, así que no se tocó el cuadre de caja.'}
              </div>
            )}

            {detalle.credito_generado ? (
              <>
                <div style={seccionTituloStyle}>Crédito a favor del cliente</div>
                <div style={lineaRowStyle}>
                  <span>{detalle.credito_generado.cliente} — {detalle.credito_generado.estado}</span>
                  <span>${formatMonto(detalle.credito_generado.saldo_disponible)} disponible</span>
                </div>
              </>
            ) : null}

            {detalle.mermas.length > 0 ? (
              <>
                <div style={seccionTituloStyle}>Mermas registradas (no vuelven al inventario)</div>
                {detalle.mermas.map((merma) => (
                  <div key={merma.id} style={lineaRowStyle}>
                    <span>{merma.cantidad}x {merma.producto}</span>
                    <span style={{ color: '#a89999', fontSize: 11.5 }}>{merma.registrado_por}</span>
                  </div>
                ))}
              </>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: '#d2c3c3', display: 'flex', alignItems: 'center', flexWrap: 'wrap' };
const dateInputStyle = { borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '8px 10px', color: '#fff' };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };
const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = {
  display: 'grid',
  gridTemplateColumns: '70px minmax(110px,1fr) minmax(160px,1.4fr) minmax(140px,1fr) minmax(90px,0.8fr) minmax(140px,1fr) minmax(110px,0.8fr)',
  minWidth: 820,
  border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: 14,
  overflow: 'hidden',
};
const rowGroupStyle = { display: 'contents' };
const headStyle = { padding: '12px 14px', background: 'rgba(255,255,255,0.06)', color: '#ffb0b0', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '14px', borderTop: '1px solid rgba(255,255,255,0.08)', color: '#f2e6e6', display: 'grid', alignContent: 'center' };
const detalleLinkStyle = { border: 'none', background: 'none', color: '#ff9d9d', fontSize: 12.5, fontWeight: 700, cursor: 'pointer', padding: 0, textAlign: 'left' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const paginacionRowStyle = (isMobile) => ({ display: 'flex', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center', flexDirection: isMobile ? 'column' : 'row', gap: 8 });
const paginacionInfoStyle = { color: '#c8bbbb', fontSize: 12.5 };
const paginacionButtonStyle = (disabled) => ({
  border: '1px solid rgba(255, 173, 173, 0.35)',
  borderRadius: 12,
  padding: '7px 12px',
  background: disabled ? 'rgba(255, 255, 255, 0.02)' : 'rgba(255, 255, 255, 0.05)',
  color: disabled ? '#8a7a7a' : '#ffe0e0',
  fontWeight: 600,
  fontSize: 13,
  cursor: disabled ? 'not-allowed' : 'pointer',
  opacity: disabled ? 0.6 : 1,
});

const modalBackdropStyle = { position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,0.6)', display: 'grid', placeItems: 'center', padding: 16 };
const modalCardStyle = { width: '100%', maxWidth: 560, maxHeight: '85vh', overflowY: 'auto', borderRadius: 20, border: '1px solid rgba(255,145,145,0.3)', background: 'linear-gradient(180deg, rgba(28,12,12,0.98) 0%, rgba(10,8,8,0.99) 100%)', padding: '22px 22px 18px', boxShadow: '0 20px 50px rgba(0,0,0,0.45)', display: 'grid', gap: 14 };
const modalHeaderStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center' };
const modalTitleStyle = { color: '#fff', fontSize: 19, fontWeight: 800 };
const modalCloseButtonStyle = { border: 'none', background: 'rgba(255,255,255,0.08)', color: '#fff', width: 30, height: 30, borderRadius: 999, cursor: 'pointer', fontSize: 14 };

const seccionTituloStyle = {
  color: '#9fe3b0',
  fontWeight: 700,
  fontSize: 11.5,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  marginTop: 6,
  borderTop: '1px solid rgba(255,255,255,0.06)',
  paddingTop: 8,
};

const lineaRowStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  fontSize: 13,
  color: '#e8dede',
};

// 'reembolso' es el único tipo de resolución que de verdad saca plata del
// banco/caja — se distingue en rojo a propósito, los otros van en tono neutro.
const tipoResolucionBadgeStyle = (tipo) => ({
  padding: '3px 10px',
  borderRadius: 999,
  fontSize: 10.5,
  fontWeight: 700,
  width: 'fit-content',
  background: tipo === 'reembolso' ? 'rgba(255, 98, 98, 0.14)' : 'rgba(159, 227, 176, 0.14)',
  color: tipo === 'reembolso' ? '#ffb0b0' : '#9fe3b0',
});

const armarCanjeButtonStyle = {
  border: '1px solid rgba(255, 200, 120, 0.4)',
  borderRadius: 999,
  padding: '7px 12px',
  background: 'rgba(255, 200, 120, 0.12)',
  color: '#ffcf7d',
  fontWeight: 700,
  fontSize: 12,
  cursor: 'pointer',
  whiteSpace: 'nowrap',
};

export default ReporteDevolucionesPage;

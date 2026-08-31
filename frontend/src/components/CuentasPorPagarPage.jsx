import { useCallback, useEffect, useState } from 'react';
import useExchangeRate from '../hooks/useExchangeRate';
import { formatBs } from '../utils/currency';

function formatUsdBs(amount, tasa) {
  const usd = `$${Number(amount).toFixed(2)}`;
  const bs = formatBs(amount, tasa);
  return bs ? `${usd} (${bs})` : usd;
}

function CuentasPorPagarPage({ isMobile, onBack, onVerComprobante }) {
  const tasaCambio = useExchangeRate();
  const [compras, setCompras] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [metodosPago, setMetodosPago] = useState([]);
  const [selectedCompraId, setSelectedCompraId] = useState(null);
  const [compraDetalle, setCompraDetalle] = useState(null);
  const [loadingDetalle, setLoadingDetalle] = useState(false);
  const [montoAbono, setMontoAbono] = useState('');
  const [metodoAbono, setMetodoAbono] = useState('');
  const [savingAbono, setSavingAbono] = useState(false);
  const [feedback, setFeedback] = useState('');
  const [feedbackType, setFeedbackType] = useState('success');
  const [ultimoAbonoId, setUltimoAbonoId] = useState(null);

  const fetchCompras = useCallback(async () => {
    try {
      const response = await fetch('/api/cuentas-por-pagar/', { credentials: 'include', cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setError(data.message || 'No se pudieron cargar las cuentas por pagar.');
        return;
      }
      setCompras(Array.isArray(data.compras) ? data.compras : []);
      setError('');
    } catch (requestError) {
      setError('Error de red al cargar las cuentas por pagar.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    fetchCompras();
  }, [fetchCompras]);

  useEffect(() => {
    const loadMetodosPago = async () => {
      try {
        const response = await fetch('/api/metodos-pago/', { credentials: 'include', cache: 'no-store' });
        const data = await response.json().catch(() => ({}));
        if (response.ok && data.ok) {
          setMetodosPago(Array.isArray(data.metodos_pago) ? data.metodos_pago : []);
        }
      } catch (requestError) {
        // El selector queda vacio si falla.
      }
    };
    loadMetodosPago();
  }, []);

  const fetchCompraDetalle = useCallback(async (compraId) => {
    setLoadingDetalle(true);
    try {
      const response = await fetch(`/api/admin/compras/${compraId}/`, { credentials: 'include', cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setFeedbackType('error');
        setFeedback(data.message || 'No se pudo cargar el detalle de la compra.');
        return;
      }
      setCompraDetalle(data.compra);
    } catch (requestError) {
      setFeedbackType('error');
      setFeedback('Error de red al cargar el detalle de la compra.');
    } finally {
      setLoadingDetalle(false);
    }
  }, []);

  const handleSelectCompra = (compra) => {
    setFeedback('');
    setMontoAbono('');
    setSelectedCompraId(compra.id);
    fetchCompraDetalle(compra.id);
  };

  const handleRegistrarAbono = async (event) => {
    event.preventDefault();
    if (!selectedCompraId) {
      return;
    }
    const metodoPagoId = metodoAbono || (metodosPago[0] && metodosPago[0].id);
    if (!metodoPagoId) {
      setFeedbackType('error');
      setFeedback('No hay metodos de pago activos configurados.');
      return;
    }

    setSavingAbono(true);
    setFeedback('');
    setUltimoAbonoId(null);
    try {
      const response = await fetch(`/api/admin/compras/${selectedCompraId}/abonos/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ monto: montoAbono, metodo_pago_id: metodoPagoId }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setFeedbackType('error');
        setFeedback(data.message || 'No se pudo registrar el abono.');
        return;
      }
      setFeedbackType('success');
      setFeedback(`Abono de ${formatUsdBs(data.abono.monto, data.abono.tasa_cambio_referencia ?? tasaCambio)} registrado. Saldo pendiente: ${formatUsdBs(data.compra.saldo_pendiente, data.compra.tasa_cambio_referencia ?? tasaCambio)}.`);
      setCompraDetalle(data.compra);
      setUltimoAbonoId(data.abono.id);
      setMontoAbono('');
      await fetchCompras();
    } catch (requestError) {
      setFeedbackType('error');
      setFeedback('Error de red al registrar el abono.');
    } finally {
      setSavingAbono(false);
    }
  };

  return (
    <section style={containerStyle(isMobile)}>
      <div style={headerWrapStyle(isMobile)}>
        <div>
          <div style={eyebrowStyle}>Contabilidad</div>
          <h2 style={titleStyle(isMobile)}>Cuentas por pagar</h2>
          <p style={subtitleStyle}>
            Lotes de compra a proveedores con saldo pendiente. Selecciona uno para registrar los abonos hasta saldarlo.
          </p>
        </div>
        <button type="button" onClick={onBack} style={backButtonStyle(isMobile)}>
          Volver
        </button>
      </div>

      {feedback ? (
        <div style={feedbackStyle(feedbackType)}>
          {feedback}
          {ultimoAbonoId && onVerComprobante ? (
            <button
              type="button"
              onClick={() => onVerComprobante('compra', selectedCompraId, ultimoAbonoId)}
              style={comprobanteLinkStyle}
            >
              Ver comprobante de pago
            </button>
          ) : null}
        </div>
      ) : null}

      {loading ? <div style={emptyStateStyle}>Cargando cuentas por pagar...</div> : null}
      {!loading && error ? <div style={errorStyle}>{error}</div> : null}
      {!loading && !error && compras.length === 0 ? (
        <div style={emptyStateStyle}>No hay deudas pendientes con proveedores en este momento.</div>
      ) : null}

      {!loading && !error && compras.length > 0 ? (
        <div style={layoutStyle(isMobile)}>
          <div style={listStyle}>
            {compras.map((compra) => (
              <button
                key={compra.id}
                type="button"
                onClick={() => handleSelectCompra(compra)}
                style={compraCardStyle(selectedCompraId === compra.id)}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                  <span style={{ color: '#fff', fontWeight: 700 }}>Lote #{compra.id}</span>
                  <span style={estadoBadgeStyle(compra.estado_pago)}>{estadoLabel(compra.estado_pago)}</span>
                </div>
                <div style={{ color: '#d2c4c4', fontSize: 13 }}>
                  {compra.proveedor_nombre}
                  {compra.numero_factura_proveedor ? ` · Factura ${compra.numero_factura_proveedor}` : ''}
                </div>
                <div style={{ color: '#ffcf7d', fontWeight: 700 }}>Saldo: {formatUsdBs(compra.saldo_pendiente, compra.tasa_cambio_referencia ?? tasaCambio)}</div>
              </button>
            ))}
          </div>

          <div style={detailPanelStyle}>
            {!selectedCompraId ? (
              <div style={emptyStateStyle}>Selecciona un lote para ver su detalle y registrar un abono.</div>
            ) : loadingDetalle || !compraDetalle ? (
              <div style={emptyStateStyle}>Cargando compra...</div>
            ) : (
              <>
                <div style={{ color: '#ffb0b0', fontWeight: 800, fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                  Lote #{compraDetalle.id} · {compraDetalle.proveedor_nombre}
                </div>
                <div style={{ color: '#d2c4c4', fontSize: 13 }}>
                  {compraDetalle.numero_factura_proveedor ? `Factura ${compraDetalle.numero_factura_proveedor} · ` : ''}
                  Cargado el {new Date(compraDetalle.fecha_creacion).toLocaleDateString('es-VE')}
                </div>

                <div style={{ display: 'grid', gap: 4 }}>
                  {compraDetalle.detalles.map((detalle) => (
                    <div key={detalle.id} style={lineaRowStyle}>
                      <span>{detalle.cantidad} {detalle.unidad_medida} — {detalle.ingrediente_nombre}</span>
                      <span>{formatUsdBs(detalle.subtotal, compraDetalle.tasa_cambio_referencia ?? tasaCambio)}</span>
                    </div>
                  ))}
                </div>

                <div style={detailTotalsStyle}>
                  <span style={{ fontWeight: 800, color: '#fff' }}>Total: {formatUsdBs(compraDetalle.total, compraDetalle.tasa_cambio_referencia ?? tasaCambio)}</span>
                  <span style={{ fontWeight: 800, color: '#ffcf7d' }}>Saldo pendiente: {formatUsdBs(compraDetalle.saldo_pendiente, compraDetalle.tasa_cambio_referencia ?? tasaCambio)}</span>
                </div>

                {compraDetalle.abonos.length > 0 ? (
                  <div style={{ display: 'grid', gap: 4 }}>
                    <div style={{ color: '#9fe3b0', fontWeight: 700, fontSize: 12, textTransform: 'uppercase' }}>Abonos registrados</div>
                    {compraDetalle.abonos.map((abono) => (
                      <div key={abono.id} style={lineaRowStyle}>
                        <span>{abono.metodo_pago} — {new Date(abono.fecha_pago).toLocaleString('es-VE')}</span>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          {formatUsdBs(abono.monto, abono.tasa_cambio_referencia ?? tasaCambio)}
                          {onVerComprobante ? (
                            <button type="button" onClick={() => onVerComprobante('compra', compraDetalle.id, abono.id)} style={miniPrintButtonStyle} title="Ver comprobante">
                              🖨
                            </button>
                          ) : null}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : null}

                {compraDetalle.estado_pago !== 'pagada' ? (
                  <form onSubmit={handleRegistrarAbono} style={abonoFormStyle(isMobile)}>
                    <input
                      type="number"
                      min="0.01"
                      step="0.01"
                      placeholder="Monto del abono"
                      value={montoAbono}
                      onChange={(event) => setMontoAbono(event.target.value)}
                      style={inputStyle}
                      required
                    />
                    <select
                      value={metodoAbono || (metodosPago[0] && metodosPago[0].id) || ''}
                      onChange={(event) => setMetodoAbono(Number(event.target.value))}
                      style={selectStyle}
                      className="admin-dark-select"
                    >
                      {metodosPago.map((metodo) => (
                        <option key={metodo.id} value={metodo.id}>{metodo.nombre}</option>
                      ))}
                    </select>
                    <button type="submit" style={primaryButtonStyle} disabled={savingAbono}>
                      {savingAbono ? 'Registrando...' : 'Registrar abono'}
                    </button>
                  </form>
                ) : (
                  <div style={{ color: '#9fe3b0', fontWeight: 700 }}>Esta cuenta ya esta saldada.</div>
                )}
              </>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function estadoLabel(estado) {
  if (estado === 'pendiente') return 'Pendiente';
  if (estado === 'abonada_parcial') return 'Abonada';
  if (estado === 'pagada') return 'Pagada';
  return estado;
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 4 : 8 });
const headerWrapStyle = (isMobile) => ({ display: 'flex', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center', flexDirection: isMobile ? 'column' : 'row', gap: 12 });
const eyebrowStyle = { fontSize: 12, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#f7a5a5', marginBottom: 8 };
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 26 : 32, fontWeight: 700 });
const subtitleStyle = { margin: '8px 0 0', color: '#d2c3c3', lineHeight: 1.6, maxWidth: 640 };
const backButtonStyle = (isMobile) => ({ border: '1px solid rgba(255, 115, 115, 0.34)', borderRadius: 999, padding: isMobile ? '11px 16px' : '10px 16px', background: 'rgba(255,255,255,0.03)', color: '#fff', fontWeight: 600, cursor: 'pointer', width: isMobile ? '100%' : 'auto' });

const emptyStateStyle = { minHeight: 100, display: 'grid', placeItems: 'center', borderRadius: 24, border: '1px dashed rgba(255, 255, 255, 0.14)', background: 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)', color: '#c8bbbb', textAlign: 'center', padding: 20 };
const errorStyle = { padding: '12px 14px', borderRadius: 16, border: '1px solid rgba(255, 145, 145, 0.22)', background: 'rgba(255, 98, 98, 0.12)', color: '#ffd8d8' };
const feedbackStyle = (feedbackType) => ({
  borderRadius: 12,
  border: feedbackType === 'error' ? '1px solid rgba(223, 102, 102, 0.5)' : '1px solid rgba(82, 206, 123, 0.35)',
  background: feedbackType === 'error' ? 'rgba(102, 29, 29, 0.55)' : 'rgba(31, 89, 48, 0.45)',
  color: feedbackType === 'error' ? '#ffe2e2' : '#dbffe4',
  padding: '10px 12px',
  fontSize: 13,
});

const layoutStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'minmax(260px, 340px) 1fr', gap: 16, alignItems: 'start' });
const listStyle = { display: 'grid', gap: 10 };
const compraCardStyle = (selected) => ({
  display: 'grid', gap: 6, textAlign: 'left', padding: '14px 16px', borderRadius: 16,
  border: selected ? '1px solid rgba(255, 130, 130, 0.6)' : '1px solid rgba(255, 255, 255, 0.1)',
  background: selected ? 'rgba(255, 90, 90, 0.12)' : 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)',
  color: '#fff', cursor: 'pointer',
});
const estadoBadgeStyle = (estado) => ({
  padding: '3px 10px', borderRadius: 999, fontSize: 11, fontWeight: 800, textTransform: 'uppercase', height: 'fit-content',
  background: estado === 'pendiente' ? 'rgba(255, 145, 145, 0.16)' : 'rgba(255, 200, 120, 0.16)',
  color: estado === 'pendiente' ? '#ff9b9b' : '#ffcf7d',
});
const detailPanelStyle = { display: 'grid', gap: 12, padding: '18px 18px', borderRadius: 20, background: 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)', border: '1px solid rgba(255, 255, 255, 0.1)', boxShadow: '0 12px 28px rgba(0,0,0,0.24)', minHeight: 200 };
const lineaRowStyle = { display: 'flex', justifyContent: 'space-between', fontSize: 13, color: '#e8dede' };
const detailTotalsStyle = { display: 'flex', flexWrap: 'wrap', gap: 14, paddingTop: 8, borderTop: '1px solid rgba(255, 255, 255, 0.06)', color: '#d2c4c4', fontSize: 13 };
const abonoFormStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr auto', gap: 8, paddingTop: 10, borderTop: '1px solid rgba(255, 255, 255, 0.08)' });
const inputStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 12, border: '1px solid rgba(255, 255, 255, 0.14)', background: '#161010', padding: '9px 10px', color: '#fff4f4', fontSize: 13 };
const selectStyle = { ...inputStyle, appearance: 'auto', colorScheme: 'dark', cursor: 'pointer' };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #1f7a3f 0%, #34d399 100%)', color: '#04140a', fontWeight: 800, cursor: 'pointer' };
const comprobanteLinkStyle = { display: 'block', marginTop: 8, border: 'none', background: 'transparent', color: 'inherit', textDecoration: 'underline', fontWeight: 700, cursor: 'pointer', padding: 0, fontSize: 13 };
const miniPrintButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 8, padding: '2px 6px', background: 'rgba(255,255,255,0.04)', cursor: 'pointer', fontSize: 12, lineHeight: 1 };

export default CuentasPorPagarPage;

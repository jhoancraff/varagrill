import { useEffect, useMemo, useState } from 'react';
import useExchangeRate from '../hooks/useExchangeRate';
import { formatBs } from '../utils/currency';

function formatUsdBs(amount, tasa) {
  const usd = `$${Number(amount).toFixed(2)}`;
  const bs = formatBs(amount, tasa);
  return bs ? `${usd} (${bs})` : usd;
}

function ComprobantePagoPage({ isMobile, onBack, tipo, documentoId, abonoId }) {
  const tasaCambio = useExchangeRate();
  const [emisor, setEmisor] = useState(null);
  const [documento, setDocumento] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError('');
      try {
        const docUrl = tipo === 'gasto' ? `/api/admin/gastos/${documentoId}/` : `/api/admin/compras/${documentoId}/`;
        const [emisorRes, docRes] = await Promise.all([
          fetch('/api/admin/datos-fiscales/', { credentials: 'include', cache: 'no-store' }),
          fetch(docUrl, { credentials: 'include', cache: 'no-store' }),
        ]);
        const emisorData = await emisorRes.json().catch(() => ({}));
        const docData = await docRes.json().catch(() => ({}));
        if (emisorRes.ok && emisorData.ok) {
          setEmisor(emisorData.datos_fiscales);
        }
        if (!docRes.ok || !docData.ok) {
          throw new Error(docData.message || 'No se pudo cargar el comprobante.');
        }
        setDocumento(tipo === 'gasto' ? docData.gasto : docData.compra);
      } catch (requestError) {
        setError(requestError.message || 'No se pudo cargar el comprobante.');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [tipo, documentoId]);

  const { abono, saldoDespues, indice } = useMemo(() => {
    if (!documento || !Array.isArray(documento.abonos)) {
      return { abono: null, saldoDespues: null, indice: -1 };
    }
    const ordenados = [...documento.abonos].sort((a, b) => new Date(a.fecha_pago) - new Date(b.fecha_pago));
    const idx = ordenados.findIndex((item) => item.id === abonoId);
    if (idx === -1) {
      return { abono: null, saldoDespues: null, indice: -1 };
    }
    const totalDoc = Number(documento.total ?? documento.monto);
    const acumuladoHastaEste = ordenados.slice(0, idx + 1).reduce((sum, item) => sum + Number(item.monto), 0);
    return { abono: ordenados[idx], saldoDespues: (totalDoc - acumuladoHastaEste).toFixed(2), indice: idx };
  }, [documento, abonoId]);

  const nombreEmisor = emisor ? (emisor.nombre_comercial || emisor.razon_social) : '';
  const pagadoA = tipo === 'gasto' ? (documento?.proveedor_nombre || documento?.categoria_nombre) : documento?.proveedor_nombre;
  const concepto = tipo === 'gasto'
    ? `${documento?.categoria_nombre || ''} — ${documento?.descripcion || ''}`
    : `Abono a compra #${documento?.id} — Factura ${documento?.numero_factura_proveedor || 's/n'}`;
  const numeroDocRef = tipo === 'gasto' ? `Gasto #${documentoId}` : `Compra #${documentoId}`;

  return (
    <section style={containerStyle(isMobile)}>
      <div className="no-print" style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          ← Volver
        </button>
        {documento && abono ? (
          <button type="button" onClick={() => window.print()} style={printButtonStyle}>
            Imprimir / Guardar PDF
          </button>
        ) : null}
      </div>

      {loading ? <div style={emptyStyle}>Cargando comprobante...</div> : null}
      {!loading && error ? <div style={errorStyle}>{error}</div> : null}
      {!loading && documento && !abono ? <div style={errorStyle}>Ese abono ya no existe.</div> : null}

      {!loading && documento && abono ? (
        <div style={voucherStyle}>
          <div style={voucherHeaderStyle}>
            {nombreEmisor ? <div style={{ fontWeight: 800, fontSize: 18 }}>{nombreEmisor}</div> : null}
            {emisor?.rif ? <div style={{ fontSize: 12.5, color: '#555' }}>RIF: {emisor.rif}</div> : null}
            {emisor?.domicilio_fiscal ? <div style={{ fontSize: 12.5, color: '#555' }}>{emisor.domicilio_fiscal}</div> : null}
          </div>

          <div style={voucherTitleStyle}>COMPROBANTE DE PAGO</div>
          <div style={{ textAlign: 'center', fontSize: 12.5, color: '#666' }}>
            {numeroDocRef} · Abono N.º {indice + 1} · Ref. interna #{abono.id}
          </div>

          <div style={voucherGridStyle}>
            <div><span style={voucherLabelStyle}>Fecha de pago</span><div>{new Date(abono.fecha_pago).toLocaleString('es-VE')}</div></div>
            <div><span style={voucherLabelStyle}>Pagado a</span><div>{pagadoA || 'N/A'}</div></div>
            <div style={{ gridColumn: '1 / -1' }}><span style={voucherLabelStyle}>Concepto</span><div>{concepto}</div></div>
            <div><span style={voucherLabelStyle}>Método de pago</span><div>{abono.metodo_pago}</div></div>
            <div><span style={voucherLabelStyle}>Referencia</span><div>{abono.referencia || '—'}</div></div>
          </div>

          <div style={voucherMontoStyle}>
            <div style={voucherLabelStyle}>Monto pagado</div>
            <div style={{ fontSize: 26, fontWeight: 800 }}>{formatUsdBs(abono.monto, tasaCambio)}</div>
          </div>

          <div style={{ fontSize: 13, color: '#444' }}>
            Saldo pendiente después de este pago: <strong>{formatUsdBs(saldoDespues, tasaCambio)}</strong>
          </div>

          <div style={{ fontSize: 12, color: '#666' }}>
            Registrado por: {abono.creado_por || '—'}
          </div>

          <div style={firmaRowStyle(isMobile)}>
            <div style={firmaBoxStyle}>Firma de quien entrega</div>
            <div style={firmaBoxStyle}>Firma de quien recibe</div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const printButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const errorStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };

const voucherStyle = {
  display: 'grid', gap: 14, padding: '28px 32px', borderRadius: 16, background: '#fff', color: '#161010',
  maxWidth: 560, margin: '0 auto', width: '100%', boxSizing: 'border-box', border: '1px solid rgba(0,0,0,0.08)',
};
const voucherHeaderStyle = { textAlign: 'center', borderBottom: '1px solid #ddd', paddingBottom: 12 };
const voucherTitleStyle = { textAlign: 'center', fontSize: 20, fontWeight: 800, letterSpacing: '0.04em' };
const voucherGridStyle = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, fontSize: 14 };
const voucherLabelStyle = { display: 'block', fontSize: 11, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#999' };
const voucherMontoStyle = { textAlign: 'center', padding: '14px 0', borderTop: '1px dashed #ccc', borderBottom: '1px dashed #ccc' };
const firmaRowStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 24, marginTop: 20 });
const firmaBoxStyle = { borderTop: '1px solid #999', paddingTop: 6, textAlign: 'center', fontSize: 12, color: '#666' };

export default ComprobantePagoPage;

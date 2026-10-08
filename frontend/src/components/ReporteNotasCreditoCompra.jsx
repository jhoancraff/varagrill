import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import { formatFecha, formatMonto } from '../utils/lotesPos';
import { RangoFechas } from './FiltroFechas';

function todayIso() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

function firstOfMonthIso() {
  return `${todayIso().slice(0, 8)}01`;
}

const ESTADOS = [
  ['', 'Todas'],
  ['vigente', 'Vigentes'],
  ['anulada', 'Anuladas'],
];

// Reporte de notas de credito de PROVEEDOR (las que bajan la deuda de una factura de
// compra, ver VGNotaCreditoCompra): por rango de fecha de la nota, con totales,
// resumen por proveedor y el detalle nota por nota. Las anuladas se listan pero no suman.
function ReporteNotasCreditoCompra({ isMobile }) {
  const [desde, setDesde] = useState(firstOfMonthIso());
  const [hasta, setHasta] = useState(todayIso());
  const [estado, setEstado] = useState('');
  const [busqueda, setBusqueda] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({ desde, hasta });
      if (estado) params.set('estado', estado);
      const response = await fetch(`/api/admin/reportes/notas-credito-compra/?${params.toString()}`, { credentials: 'include', cache: 'no-store' });
      const json = await response.json().catch(() => ({}));
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cargar el reporte.');
      }
      setData(json);
    } catch (requestError) {
      setError(requestError.message || 'No se pudo cargar el reporte.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [desde, hasta, estado]);

  useEffect(() => {
    load();
  }, [load]);

  const notas = useMemo(() => {
    const texto = busqueda.trim().toLowerCase();
    const todas = data?.notas || [];
    if (!texto) return todas;
    return todas.filter((nota) => [
      nota.codigo, nota.proveedor_nombre, nota.numero_factura_proveedor, nota.numero_documento_proveedor, nota.motivo, String(nota.compra_id),
    ].some((campo) => (campo || '').toLowerCase().includes(texto)));
  }, [data, busqueda]);

  return (
    <section style={containerStyle}>
      <div className="no-print" style={filtrosStyle(isMobile)}>
        <RangoFechas
          desde={desde}
          hasta={hasta}
          onChange={(rango) => { setDesde(rango.desde); setHasta(rango.hasta); }}
        />
        <label style={fieldStyle}>Estado
          <select value={estado} onChange={(event) => setEstado(event.target.value)} style={inputStyle} className="admin-dark-select">
            {ESTADOS.map(([valor, etiqueta]) => <option key={valor} value={valor}>{etiqueta}</option>)}
          </select>
        </label>
        <label style={{ ...fieldStyle, flex: 1 }}>Buscar
          <input
            type="text"
            value={busqueda}
            onChange={(event) => setBusqueda(event.target.value)}
            placeholder="Proveedor, factura, Nº de nota o motivo..."
            style={inputStyle}
          />
        </label>
        <button type="button" onClick={() => window.print()} style={printButtonStyle}>Imprimir / Guardar PDF</button>
      </div>

      {loading ? <div style={emptyStyle}>Cargando notas de crédito...</div> : null}
      {!loading && error ? <div style={noticeStyle}>{error}</div> : null}

      {!loading && data ? (
        <>
          <div style={tilesStyle(isMobile)}>
            <div style={tileStyle}>
              <div style={tileLabelStyle}>Notas vigentes</div>
              <div style={tileValueStyle}>{data.cantidad_vigentes}</div>
            </div>
            <div style={tileStyle}>
              <div style={tileLabelStyle}>Total rebajado</div>
              <div style={tileValueStyle}>${formatMonto(data.total_usd)}</div>
              <div style={tileHintStyle}>Bs {formatMonto(data.total_bs)}</div>
            </div>
            <div style={tileStyle}>
              <div style={tileLabelStyle}>Período</div>
              <div style={{ ...tileValueStyle, fontSize: 16 }}>{formatFecha(data.desde)} — {formatFecha(data.hasta)}</div>
              <div style={tileHintStyle}>Por fecha de la nota</div>
            </div>
          </div>

          {data.por_proveedor.length > 0 ? (
            <div style={{ display: 'grid', gap: 6 }}>
              <div style={sectionLabelStyle}>Por proveedor</div>
              <div style={tableWrapStyle}>
                <div style={provTableStyle}>
                  <div style={headStyle}>Proveedor</div>
                  <div style={headStyle}>Notas</div>
                  <div style={headStyle}>Rebajado</div>
                  {data.por_proveedor.map((item) => (
                    <Fragment key={item.proveedor}>
                      <div style={cellStyle}>{item.proveedor}</div>
                      <div style={cellStyle}>{item.cantidad}</div>
                      <div style={cellStyle}>${formatMonto(item.monto_usd)}</div>
                    </Fragment>
                  ))}
                </div>
              </div>
            </div>
          ) : null}

          <div style={{ display: 'grid', gap: 6 }}>
            <div style={sectionLabelStyle}>Detalle</div>
            {notas.length === 0 ? <div style={emptyStyle}>No hay notas de crédito en este período.</div> : (
              <div style={tableWrapStyle}>
                <div style={tableStyle}>
                  <div style={headStyle}>Nota</div>
                  <div style={headStyle}>Fecha</div>
                  <div style={headStyle}>Proveedor / Factura</div>
                  <div style={headStyle}>Motivo</div>
                  <div style={headStyle}>Monto</div>
                  <div style={headStyle}>Estado</div>
                  {notas.map((nota) => {
                    const anulada = nota.estado === 'anulada';
                    return (
                      <Fragment key={nota.id}>
                        <div style={cellStyle}>
                          <strong>{nota.codigo}</strong>
                          {nota.numero_documento_proveedor ? <span style={mutedStyle}>Proveedor: {nota.numero_documento_proveedor}</span> : null}
                        </div>
                        <div style={cellStyle}>{formatFecha(nota.fecha)}</div>
                        <div style={cellStyle}>
                          {nota.proveedor_nombre}
                          <span style={mutedStyle}>
                            Lote #{nota.compra_id}{nota.numero_factura_proveedor ? ` · Factura ${nota.numero_factura_proveedor}` : ''}
                          </span>
                        </div>
                        <div style={cellStyle}>
                          {nota.motivo}
                          {anulada ? <span style={{ ...mutedStyle, color: '#ffcf85' }}>Anulada: {nota.motivo_anulacion}</span> : null}
                          <span style={mutedStyle}>Registrada por {nota.registrada_por || '—'}</span>
                        </div>
                        <div style={{ ...cellStyle, textDecoration: anulada ? 'line-through' : 'none', opacity: anulada ? 0.6 : 1 }}>
                          −${formatMonto(nota.monto)}
                          {nota.monto_bs ? <span style={mutedStyle}>Bs {formatMonto(nota.monto_bs)}</span> : null}
                        </div>
                        <div style={cellStyle}>
                          <span style={badgeStyle(anulada)}>{anulada ? 'Anulada' : 'Vigente'}</span>
                        </div>
                      </Fragment>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </>
      ) : null}
    </section>
  );
}

const containerStyle = { display: 'grid', gap: 16 };
const filtrosStyle = (isMobile) => ({ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end', flexDirection: isMobile ? 'column' : 'row' });
const fieldStyle = { display: 'grid', gap: 6, color: '#f2e6e6', fontSize: 13, fontWeight: 700 };
const inputStyle = { borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff', width: '100%', boxSizing: 'border-box' };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb', textAlign: 'center', padding: 12 };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };
const tilesStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, minmax(0, 1fr))', gap: 10 });
const tileStyle = { display: 'grid', gap: 4, padding: '14px 16px', borderRadius: 14, border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.03)' };
const tileLabelStyle = { color: '#ffb0b0', fontSize: 11.5, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' };
const tileValueStyle = { color: '#fff', fontSize: 24, fontWeight: 800 };
const tileHintStyle = { color: '#c8bbbb', fontSize: 12.5 };
const sectionLabelStyle = { color: '#9ecbff', fontSize: 12, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase' };
const tableWrapStyle = { overflowX: 'auto' };
const provTableStyle = { display: 'grid', gridTemplateColumns: 'minmax(180px,1.6fr) minmax(70px,0.4fr) minmax(120px,0.8fr)', minWidth: 420, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(130px,0.9fr) minmax(90px,0.6fr) minmax(190px,1.3fr) minmax(220px,1.6fr) minmax(120px,0.8fr) minmax(90px,0.6fr)', minWidth: 880, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(255,255,255,0.06)', color: '#ffb0b0', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '12px 14px', borderTop: '1px solid rgba(255,255,255,0.08)', color: '#f2e6e6', display: 'grid', alignContent: 'center', gap: 2 };
const mutedStyle = { color: '#a89999', fontSize: 12, display: 'block' };
const badgeStyle = (anulada) => ({ fontSize: 11, fontWeight: 800, padding: '3px 10px', borderRadius: 999, textTransform: 'uppercase', letterSpacing: '0.04em', width: 'fit-content', color: anulada ? '#c8bbbb' : '#bdf0cf', background: anulada ? 'rgba(255,255,255,0.08)' : 'rgba(70,200,120,0.16)' });
const printButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };

export default ReporteNotasCreditoCompra;

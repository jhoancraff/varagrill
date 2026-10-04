import { useCallback, useEffect, useState } from 'react';
import Toast from './Toast';
import useToast from '../hooks/useToast';
import { getFechaSeleccionada } from '../utils/fechaContabilidad';
import {
  ESTADO_LOTE_ESTILO,
  formatFechaConDia,
  formatMonto,
  postLotePos,
} from '../utils/lotesPos';

function todayIso() {
  const now = new Date();
  const offset = now.getTimezoneOffset();
  const local = new Date(now.getTime() - offset * 60000);
  return local.toISOString().slice(0, 10);
}

// Pantalla a la que lleva el boton "Cerrar caja" del cuadre diario. Ya no se
// cuenta el efectivo a mano: aqui se revisan/cierran los lotes de punto de venta
// (cierre parcial o autoclausura al cerrar) y se cierra la caja del dia.
function CierreCajaPage({ isMobile, onBack }) {
  const [fecha] = useState(() => getFechaSeleccionada(todayIso()));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [notas, setNotas] = useState('');
  const { toast, showSuccess, showError, hideToast } = useToast();

  const loadReport = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch(`/api/admin/reportes/cuadre-caja/?fecha=${fecha}`, { credentials: 'include', cache: 'no-store' });
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cargar el cierre de caja.');
      }
      setData(json);
    } catch (requestError) {
      setError(requestError.message || 'No se pudo cargar el cierre de caja.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [fecha]);

  useEffect(() => {
    loadReport();
  }, [loadReport]);

  const pos = data?.pos || null;
  const cierre = data?.cierre || null;
  const lotesAbiertos = pos
    ? [...pos.lotes_abiertos_anteriores, ...pos.lotes_dia.filter((lote) => lote.estado === 'abierto')]
    : [];
  const lotesAbiertosConCobros = lotesAbiertos.filter((lote) => lote.num_pagos > 0);
  const lotesCerradosDia = pos ? pos.lotes_dia.filter((lote) => lote.estado !== 'abierto') : [];

  const handleCerrarLote = async (lote) => {
    setSaving(true);
    try {
      const json = await postLotePos({
        action: 'cerrar_lote',
        lote_id: lote.id,
      });
      showSuccess(json.message || 'Lote cerrado.');
      await loadReport();
    } catch (requestError) {
      showError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  const handleCerrarCaja = async (event) => {
    event.preventDefault();
    const aviso = lotesAbiertosConCobros.length > 0
      ? `¿Cerrar la caja de este día? Se cerrarán automáticamente ${lotesAbiertosConCobros.length} lote(s) de punto de venta. Esta acción queda registrada de forma permanente.`
      : '¿Cerrar la caja de este día? Esta acción queda registrada de forma permanente.';
    if (!window.confirm(aviso)) {
      return;
    }

    setSaving(true);
    try {
      const response = await fetch('/api/admin/reportes/cuadre-caja/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'cerrar_caja',
          fecha,
          notas,
        }),
      });
      const json = await response.json().catch(() => ({}));
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cerrar la caja.');
      }
      showSuccess(json.message || 'Caja cerrada.');
      await loadReport();
    } catch (requestError) {
      showError(requestError.message || 'No se pudo cerrar la caja.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <section style={containerStyle(isMobile)}>
      <Toast toast={toast} onClose={hideToast} />

      <div className="no-print" style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          ← Volver al cuadre de caja
        </button>
      </div>

      <div>
        <h2 style={titleStyle(isMobile)}>Cerrar caja — {formatFechaConDia(fecha)}</h2>
      </div>

      {loading ? <div style={emptyStyle}>Cargando cierre de caja...</div> : null}
      {!loading && error ? <div style={noticeStyle}>{error}</div> : null}

      {!loading && !error && data ? (
        <>
          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Efectivo del día</div>
            <div style={resumenGridStyle(isMobile)}>
              <div style={tileStyle}>
                <div style={tileLabelStyle}>Efectivo en bolívares</div>
                <div style={tileValueStyle}>
                  {data.efectivo_por_moneda?.bs !== null && data.efectivo_por_moneda?.bs !== undefined
                    ? `Bs. ${formatMonto(data.efectivo_por_moneda.bs)}`
                    : '—'}
                </div>
                <div style={tileHintStyle}>
                  {data.efectivo_por_moneda?.bs === null ? 'Falta la tasa de algún movimiento' : `≈ $${formatMonto(data.efectivo_por_moneda?.bs_en_usd)}`}
                </div>
              </div>
              <div style={tileStyle}>
                <div style={tileLabelStyle}>Efectivo en dólares</div>
                <div style={tileValueStyle}>${formatMonto(data.efectivo_por_moneda?.usd)}</div>
              </div>
              <div style={tileStyle}>
                <div style={tileLabelStyle}>Efectivo esperado total</div>
                <div style={tileValueStyle}>${formatMonto(cierre ? cierre.efectivo_esperado : data.efectivo_esperado_preview)}</div>
                <div style={tileHintStyle}>Bs + $ en dólares. Cobros + propinas/extra − gastos, todo en efectivo</div>
              </div>
              {Number(data.gastos_efectivo_dia) > 0 ? (
                <div style={tileStyle}>
                  <div style={tileLabelStyle}>Gastos pagados en efectivo</div>
                  <div style={{ ...tileValueStyle, color: '#ff9d9d' }}>−${formatMonto(data.gastos_efectivo_dia)}</div>
                  {data.efectivo_por_moneda?.gastos_bs && Number(data.efectivo_por_moneda.gastos_bs) > 0 ? (
                    <div style={tileHintStyle}>Incluye Bs. {formatMonto(data.efectivo_por_moneda.gastos_bs)} pagados en bolívares</div>
                  ) : null}
                </div>
              ) : null}
            </div>
          </section>

          {pos ? (
            <section style={panelStyle}>
              <div style={sectionTitleStyle}>Puntos de venta — lotes</div>
              <div style={resumenGridStyle(isMobile)}>
                <div style={tileStyle}>
                  <div style={tileLabelStyle}>Cobrado hoy por punto de venta</div>
                  <div style={tileValueStyle}>${formatMonto(pos.cobrado_dia_usd)}</div>
                </div>
                <div style={tileStyle}>
                  <div style={tileLabelStyle}>Por acreditar (en lotes)</div>
                  <div style={{ ...tileValueStyle, color: '#ffe3a3' }}>${formatMonto(pos.por_acreditar_usd)}</div>
                  <div style={tileHintStyle}>Se suma a la cuenta al acreditar el lote</div>
                </div>
                <div style={tileStyle}>
                  <div style={tileLabelStyle}>Disponibilidad real</div>
                  <div style={{ ...tileValueStyle, color: '#8fffb0' }}>${formatMonto(pos.disponibilidad_real_usd)}</div>
                  <div style={tileHintStyle}>Excluye los lotes sin acreditar</div>
                </div>
                <div style={tileStyle}>
                  <div style={tileLabelStyle}>Acreditado hoy</div>
                  <div style={tileValueStyle}>${formatMonto(pos.acreditado_hoy_usd)}</div>
                </div>
              </div>

              {!cierre && lotesAbiertos.length > 0 ? (
                <div style={{ display: 'grid', gap: 10 }}>
                  <div style={subTitleStyle}>Lotes abiertos</div>
                  {lotesAbiertos.map((lote) => (
                    <article key={lote.id} style={loteCardStyle}>
                      <div style={loteHeaderStyle}>
                        <div style={{ fontWeight: 800, color: '#fff' }}>
                          {lote.codigo} · {lote.metodo_pago_nombre}
                          {lote.cuenta_bancaria ? <span style={mutedStyle}> ({lote.cuenta_bancaria})</span> : null}
                        </div>
                        <span style={{ ...badgeStyle, ...ESTADO_LOTE_ESTILO.abierto }}>Abierto</span>
                      </div>
                      <div style={loteDatosStyle}>
                        <span>{lote.num_pagos} cobro(s)</span>
                        <span>${formatMonto(lote.monto_usd)} · Bs {formatMonto(lote.monto_bs)}</span>
                      </div>
                      {lote.num_pagos > 0 ? (
                        <button type="button" disabled={saving} onClick={() => handleCerrarLote(lote)} style={secondaryButtonStyle}>
                          Cerrar este lote
                        </button>
                      ) : (
                        <div style={mutedStyle}>Sin cobros vigentes: se descarta solo al cerrar la caja.</div>
                      )}
                    </article>
                  ))}
                </div>
              ) : null}

              {lotesCerradosDia.length > 0 ? (
                <div style={{ display: 'grid', gap: 8 }}>
                  <div style={subTitleStyle}>Lotes del día</div>
                  {lotesCerradosDia.map((lote) => (
                    <article key={lote.id} style={loteCardStyle}>
                      <div style={loteHeaderStyle}>
                        <div style={{ fontWeight: 700, color: '#fff' }}>{lote.codigo} · {lote.metodo_pago_nombre}</div>
                        <span style={{ ...badgeStyle, ...(ESTADO_LOTE_ESTILO[lote.estado] || {}) }}>{lote.estado_label}</span>
                      </div>
                      <div style={loteDatosStyle}>
                        <span>${formatMonto(lote.monto_usd)} · Bs {formatMonto(lote.monto_bs)}</span>
                        {lote.estado === 'acreditado' ? <span>Acreditado {formatFechaConDia(lote.fecha_abono)}</span> : <span style={{ color: '#ffe3a3' }}>Por acreditar</span>}
                      </div>
                    </article>
                  ))}
                </div>
              ) : null}

              {!cierre && lotesAbiertosConCobros.length === 0 && lotesCerradosDia.length === 0 ? (
                <div style={mutedStyle}>Hoy no hay cobros por punto de venta.</div>
              ) : null}
            </section>
          ) : null}

          <section style={panelStyle}>
            <div style={sectionTitleStyle}>Cierre del día</div>
            {cierre ? (
              <div style={{ display: 'grid', gap: 8, color: '#f2e6e6' }}>
                <div style={{ color: '#8fffb0', fontWeight: 800 }}>La caja de este día ya está cerrada.</div>
                <div>Efectivo esperado: <strong>${formatMonto(cierre.efectivo_esperado)}</strong></div>
                {cierre.conteo_efectivo_realizado ? (
                  <>
                    <div>Efectivo contado al cerrar: <strong>${formatMonto(cierre.efectivo_contado_final)}</strong></div>
                    <div style={{ color: Number(cierre.diferencia) === 0 ? '#8fffb0' : '#ff9d9d', fontWeight: 800 }}>
                      Diferencia: ${formatMonto(cierre.diferencia)}
                    </div>
                  </>
                ) : null}
                <div>POS por acreditar al cerrar: <strong>${formatMonto(cierre.pos_por_acreditar_usd)}</strong></div>
                {cierre.notas ? <div>Notas: {cierre.notas}</div> : null}
                <div style={{ fontSize: 13, color: '#c8bbbb' }}>
                  Cerrado por {cierre.cerrado_por || '—'} el {new Date(cierre.fecha_creacion).toLocaleString('es-VE')}
                </div>
              </div>
            ) : (
              <form onSubmit={handleCerrarCaja} className="no-print" style={{ display: 'grid', gap: 12, maxWidth: 520 }}>
                {lotesAbiertosConCobros.length > 0 ? (
                  <div style={{ padding: 12, borderRadius: 12, border: '1px dashed rgba(255,207,133,0.4)', background: 'rgba(255,207,133,0.05)', color: '#ffe3a3', fontWeight: 700 }}>
                    Al cerrar la caja se cerrarán automáticamente {lotesAbiertosConCobros.length} lote(s) abiertos de punto de venta.
                  </div>
                ) : null}
                <label style={{ display: 'grid', gap: 6, color: '#f2e6e6' }}>
                  Notas (opcional)
                  <input type="text" value={notas} onChange={(event) => setNotas(event.target.value)} style={inputStyle} />
                </label>
                <button type="submit" disabled={saving} style={dangerButtonStyle}>
                  {saving ? 'Cerrando...' : 'Cerrar caja del día'}
                </button>
              </form>
            )}
          </section>
        </>
      ) : null}
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 26 : 34 });
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const sectionTitleStyle = { color: '#fff', fontSize: 19, fontWeight: 700 };
const subTitleStyle = { color: '#ffb0b0', fontSize: 12, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase' };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };
const resumenGridStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(auto-fit, minmax(190px, 1fr))', gap: 10 });
const tileStyle = { display: 'grid', gap: 4, padding: '14px 16px', borderRadius: 14, border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.03)' };
const tileLabelStyle = { color: '#ffb0b0', fontSize: 11.5, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' };
const tileValueStyle = { color: '#fff', fontSize: 22, fontWeight: 800 };
const tileHintStyle = { color: '#c8bbbb', fontSize: 12 };
const loteCardStyle = { display: 'grid', gap: 8, padding: '12px 14px', borderRadius: 14, border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.03)' };
const loteHeaderStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' };
const loteDatosStyle = { display: 'flex', gap: 14, flexWrap: 'wrap', color: '#d2c3c3', fontSize: 13 };
const badgeStyle = { fontSize: 11, fontWeight: 800, padding: '3px 10px', borderRadius: 999, textTransform: 'uppercase', letterSpacing: '0.04em' };
const mutedStyle = { color: '#a89999', fontSize: 12.5 };
const inputStyle = { borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff' };
const secondaryButtonStyle = { border: '1px solid rgba(255,255,255,0.18)', borderRadius: 999, padding: '9px 16px', background: 'rgba(255,255,255,0.05)', color: '#fff', fontWeight: 700, cursor: 'pointer', width: 'fit-content' };
const dangerButtonStyle = { border: '1px solid rgba(255,126,126,0.4)', borderRadius: 999, padding: '12px 16px', background: 'rgba(145,33,33,0.35)', color: '#ffd3d3', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default CierreCajaPage;

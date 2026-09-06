import { useCallback, useEffect, useState } from 'react';

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

function ReporteConciliacionBancariaPage({ isMobile, onBack }) {
  const [fecha, setFecha] = useState(todayIso());
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [formByBanco, setFormByBanco] = useState({});
  const [savingBanco, setSavingBanco] = useState('');

  const loadReport = useCallback(async (fechaConsultada) => {
    setLoading(true);
    setError('');
    try {
      const response = await fetch(`/api/admin/reportes/conciliacion-bancaria/?fecha=${fechaConsultada}`, {
        credentials: 'include',
        cache: 'no-store',
      });
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cargar la conciliación bancaria.');
      }
      setData(json);
    } catch (requestError) {
      setError(requestError.message || 'No se pudo cargar la conciliación bancaria.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadReport(fecha);
  }, [fecha, loadReport]);

  const updateForm = (bancoNombre, campo, valor) => {
    setFormByBanco((current) => ({
      ...current,
      [bancoNombre]: { ...(current[bancoNombre] || { saldoBanco: '', notas: '' }), [campo]: valor },
    }));
  };

  const handleConciliar = async (banco) => {
    const form = formByBanco[banco.nombre] || {};
    if (form.saldoBanco === undefined || form.saldoBanco === '' || Number.isNaN(Number(form.saldoBanco))) {
      setError(`Escribe el saldo que muestra el banco para "${banco.nombre}".`);
      return;
    }

    setSavingBanco(banco.nombre);
    setError('');
    try {
      const response = await fetch('/api/admin/reportes/conciliacion-bancaria/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'conciliar',
          fecha,
          banco_nombre: banco.nombre,
          saldo_banco: form.saldoBanco,
          notas: form.notas || '',
        }),
      });
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo registrar la conciliación.');
      }
      setFormByBanco((current) => {
        const copy = { ...current };
        delete copy[banco.nombre];
        return copy;
      });
      loadReport(fecha);
    } catch (requestError) {
      setError(requestError.message || 'No se pudo registrar la conciliación.');
    } finally {
      setSavingBanco('');
    }
  };

  const bancos = data?.bancos || [];
  const resumen = data?.resumen || null;

  return (
    <section style={containerStyle(isMobile)}>
      <div className="no-print" style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          ← Volver a Contabilidad
        </button>
        <button type="button" onClick={() => window.print()} style={printButtonStyle}>
          Imprimir / Guardar PDF
        </button>
      </div>

      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Conciliación bancaria</h2>
          <p style={subtitleStyle}>
            Por cada cuenta que cae en un banco real, compara el saldo que calcula el sistema contra lo
            que de verdad muestra el estado de cuenta — para que quede un registro de que sí coinciden,
            o de cuánto y por qué no. El efectivo físico se cuadra aparte, desde Cuadre de Caja.
          </p>
        </div>
        <label className="no-print" style={dateLabelStyle}>
          Fecha
          <input
            type="date"
            value={fecha}
            max={todayIso()}
            onChange={(event) => setFecha(event.target.value)}
            style={dateInputStyle}
          />
        </label>
      </div>

      {error ? <div style={noticeStyle} className="no-print">{error}</div> : null}
      {loading ? <div style={emptyStyle}>Cargando conciliación bancaria...</div> : null}

      {!loading && !error && data ? (
        <>
          {resumen ? (
            <section style={panelStyle}>
              <div style={sectionTitleStyle}>Resumen — {fecha}</div>
              <div style={resumenGridStyle(isMobile)}>
                <div style={desgloseTileStyle}>
                  <div style={desgloseLabelStyle}>Cuentas conciliadas</div>
                  <div style={desgloseValueStyle}>{resumen.conciliados} / {resumen.total_bancos}</div>
                </div>
                <div style={desgloseTileStyle}>
                  <div style={desgloseLabelStyle}>Pendientes por conciliar</div>
                  <div style={{ ...desgloseValueStyle, color: resumen.pendientes > 0 ? '#ffcf7d' : '#8fffb0' }}>
                    {resumen.pendientes}
                  </div>
                </div>
                <div style={desgloseTileStyle}>
                  <div style={desgloseLabelStyle}>Diferencia total (USD)</div>
                  <div style={{ ...desgloseValueStyle, color: Number(resumen.suma_diferencias) === 0 ? '#8fffb0' : '#ff9d9d' }}>
                    ${formatMonto(resumen.suma_diferencias)}
                  </div>
                </div>
              </div>
              {data.tasa_bcv ? (
                <div style={{ fontSize: 12, color: '#c8bbbb' }}>Tasa BCV usada: Bs. {formatMonto(data.tasa_bcv)} / $</div>
              ) : (
                <div style={{ fontSize: 12, color: '#ffcf85' }}>No hay tasa BCV registrada para esta fecha; las cuentas en bolívares no se pueden conciliar hasta que exista una.</div>
              )}
            </section>
          ) : null}

          {bancos.length === 0 ? (
            <div style={emptyStyle}>No hay cuentas bancarias configuradas todavía (solo efectivo).</div>
          ) : (
            <div style={bancosGridStyle(isMobile)}>
              {bancos.map((banco) => {
                const conciliado = banco.conciliacion;
                const form = formByBanco[banco.nombre] || { saldoBanco: '', notas: '' };
                const guardando = savingBanco === banco.nombre;
                const diferenciaOk = conciliado && Math.abs(Number(conciliado.diferencia)) < 0.01;
                return (
                  <article key={banco.nombre} style={bancoCardStyle(conciliado ? diferenciaOk : null)}>
                    <div style={bancoHeaderStyle}>
                      <div style={bancoNombreStyle}>
                        {banco.nombre}
                        {banco.num_metodos > 1 ? <span style={infoBadgeStyle}>{banco.num_metodos} métodos</span> : null}
                        {banco.moneda_mixta ? <span style={warnBadgeStyle}>Monedas mixtas</span> : null}
                      </div>
                      {conciliado ? (
                        <span style={diferenciaOk ? okBadgeStyle : warnBadgeStyle}>
                          {diferenciaOk ? 'Coincide' : 'No coincide'}
                        </span>
                      ) : (
                        <span style={pendingBadgeStyle}>Pendiente</span>
                      )}
                    </div>

                    <div style={saldoSistemaRowStyle}>
                      <span style={saldoSistemaLabelStyle}>Según el sistema</span>
                      <span style={saldoSistemaValueStyle}>
                        {banco.moneda === 'VES' ? (
                          <>
                            {banco.saldo_sistema_bs !== null ? `Bs. ${formatMonto(banco.saldo_sistema_bs)}` : '—'}
                            <span style={secondaryAmountStyle}> (${formatMonto(banco.saldo_sistema)})</span>
                          </>
                        ) : (
                          <>${formatMonto(banco.saldo_sistema)}</>
                        )}
                      </span>
                    </div>

                    {conciliado ? (
                      <div style={conciliadoBoxStyle}>
                        <div style={saldoSistemaRowStyle}>
                          <span style={saldoSistemaLabelStyle}>Según el banco</span>
                          <span style={saldoSistemaValueStyle}>
                            {banco.moneda === 'VES' && conciliado.saldo_banco_bs !== null
                              ? `Bs. ${formatMonto(conciliado.saldo_banco_bs)}`
                              : `$${formatMonto(conciliado.saldo_banco)}`}
                          </span>
                        </div>
                        <div style={{ color: diferenciaOk ? '#8fffb0' : '#ff9d9d', fontWeight: 800, fontSize: 14 }}>
                          Diferencia: {banco.moneda === 'VES' && conciliado.diferencia_bs !== null
                            ? `Bs. ${formatMonto(conciliado.diferencia_bs)} `
                            : ''}
                          (${formatMonto(conciliado.diferencia)})
                        </div>
                        {conciliado.notas ? <div style={notasTextStyle}>{conciliado.notas}</div> : null}
                        <div style={metaTextStyle}>
                          Conciliado por {conciliado.conciliado_por || '—'} el {new Date(conciliado.fecha_creacion).toLocaleString('es-VE')}
                        </div>
                      </div>
                    ) : (
                      <form
                        className="no-print"
                        onSubmit={(event) => { event.preventDefault(); handleConciliar(banco); }}
                        style={formStyle}
                      >
                        <label style={fieldLabelStyle}>
                          Saldo según el banco {banco.moneda === 'VES' ? '(en Bs.)' : '(en $)'}
                          <input
                            type="number"
                            step="0.01"
                            value={form.saldoBanco}
                            onChange={(event) => updateForm(banco.nombre, 'saldoBanco', event.target.value)}
                            style={inputStyle}
                            placeholder={banco.moneda === 'VES' ? 'Ej: 5.505,79' : 'Ej: 5.76'}
                          />
                        </label>
                        <label style={fieldLabelStyle}>
                          Notas (opcional)
                          <input
                            type="text"
                            value={form.notas}
                            onChange={(event) => updateForm(banco.nombre, 'notas', event.target.value)}
                            style={inputStyle}
                          />
                        </label>
                        <button type="submit" disabled={guardando} style={primaryButtonStyle}>
                          {guardando ? 'Guardando...' : 'Conciliar'}
                        </button>
                      </form>
                    )}
                  </article>
                );
              })}
            </div>
          )}
        </>
      ) : null}
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const headerRowStyle = (isMobile) => ({ display: 'flex', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center', flexDirection: isMobile ? 'column' : 'row', gap: 12 });
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: '#d2c3c3', maxWidth: 680, lineHeight: 1.6 };
const dateLabelStyle = { display: 'flex', flexDirection: 'column', gap: 6, color: '#f2e6e6', fontSize: 13, fontWeight: 700 };
const dateInputStyle = { borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff' };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const sectionTitleStyle = { color: '#fff', fontSize: 19, fontWeight: 700 };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };
const secondaryAmountStyle = { color: '#c8bbbb', fontSize: 12.5, marginLeft: 6 };

const resumenGridStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, 1fr)', gap: 10 });
const desgloseTileStyle = { display: 'grid', gap: 4, padding: '14px 16px', borderRadius: 14, border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.03)' };
const desgloseLabelStyle = { color: '#ffb0b0', fontSize: 11.5, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' };
const desgloseValueStyle = { color: '#fff', fontSize: 22, fontWeight: 800 };

const bancosGridStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fill, minmax(300px, 1fr))', gap: 14 });
const bancoCardStyle = (ok) => ({
  display: 'grid', gap: 12, padding: '18px 20px', borderRadius: 18,
  border: ok === null ? '1px solid rgba(255,255,255,0.1)' : ok ? '1px solid rgba(120,255,170,0.28)' : '1px solid rgba(255,145,145,0.3)',
  background: ok === null ? 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' : ok ? 'rgba(90,220,140,0.06)' : 'rgba(255,98,98,0.07)',
});
const bancoHeaderStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 };
const bancoNombreStyle = { color: '#fff', fontWeight: 700, fontSize: 16, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' };
const badgeBase = { fontSize: 10.5, fontWeight: 800, padding: '2px 9px', borderRadius: 999, textTransform: 'uppercase', letterSpacing: '0.04em', whiteSpace: 'nowrap' };
const infoBadgeStyle = { ...badgeBase, color: '#c8bbbb', background: 'rgba(255,255,255,0.08)' };
const warnBadgeStyle = { ...badgeBase, color: '#ffcf7d', background: 'rgba(255,183,77,0.16)' };
const okBadgeStyle = { ...badgeBase, color: '#8fffb0', background: 'rgba(90,220,140,0.16)' };
const pendingBadgeStyle = { ...badgeBase, color: '#ffcf7d', background: 'rgba(255,183,77,0.14)' };

const saldoSistemaRowStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 10 };
const saldoSistemaLabelStyle = { color: '#c8bbbb', fontSize: 12.5 };
const saldoSistemaValueStyle = { color: '#fff', fontSize: 17, fontWeight: 700 };
const conciliadoBoxStyle = { display: 'grid', gap: 6, paddingTop: 10, borderTop: '1px dashed rgba(255,255,255,0.14)' };
const notasTextStyle = { color: '#d2c3c3', fontSize: 12.5, fontStyle: 'italic' };
const metaTextStyle = { color: '#8f8080', fontSize: 11.5 };

const formStyle = { display: 'grid', gap: 10, paddingTop: 10, borderTop: '1px dashed rgba(255,255,255,0.14)' };
const fieldLabelStyle = { display: 'grid', gap: 6, color: '#f2e6e6', fontSize: 12.5, fontWeight: 600 };
const inputStyle = { borderRadius: 10, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '9px 11px', color: '#fff', fontSize: 14 };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const printButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default ReporteConciliacionBancariaPage;

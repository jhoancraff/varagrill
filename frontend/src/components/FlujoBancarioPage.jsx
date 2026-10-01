import { useCallback, useEffect, useMemo, useState } from 'react';
import { formatBsRaw } from '../utils/currency';

function pad2(value) {
  return String(value).padStart(2, '0');
}

function mesActualIso() {
  const now = new Date();
  return `${now.getFullYear()}-${pad2(now.getMonth() + 1)}`;
}

function formatMonto(value) {
  const number = Number(value || 0);
  return number.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatFechaCorta(isoDate) {
  const [anio, mes, dia] = isoDate.split('-');
  return `${dia}/${mes}`;
}

function formatDiaSemana(isoDate) {
  const fecha = new Date(`${isoDate}T00:00:00`);
  return fecha.toLocaleDateString('es-VE', { weekday: 'short' });
}

function formatHora(isoString) {
  const fecha = new Date(isoString);
  return fecha.toLocaleTimeString('es-VE', { hour: '2-digit', minute: '2-digit' });
}

const TIPO_REGISTRO_LABEL = {
  pago: 'Pago',
  ingreso_extra: 'Ingreso extra',
  abono_gasto: 'Gasto',
  abono_compra: 'Compra',
};

// Los gastos se agrupan por su fecha REAL (fecha_gasto, sin hora) en vez de
// cuándo se cargó el abono al sistema — no hay una hora real que mostrar.
// Las compras SÍ tienen hora real (cada abono se agrupa por su propia
// fecha_pago), así que no entran en este set.
const TIPOS_SIN_HORA = new Set(['abono_gasto']);

// Un movimiento con monto_bs es de una cuenta en bolívares (ver
// detalle_flujo_bancario_dia en reportes.py, que solo lo calcula cuando
// metodo.moneda == 'VES') — se muestra SOLO en bolívares, con el monto EXACTO
// que se cobró/pagó (tasa histórica ya congelada, nunca la tasa de hoy).
// Nunca se muestran las dos monedas juntas — mismo criterio que
// formatMontoDocumento (utils/currency.js), usado en el resto del sistema
// para notas de entrega/facturas.
function formatMontoMovimiento(movimiento) {
  if (movimiento.monto_bs != null) {
    return formatBsRaw(movimiento.monto_bs);
  }
  return `$${formatMonto(movimiento.monto)}`;
}

// Mismo criterio para la tabla del mes: si ese día tuvo bolívares (entrada_bs/
// salida_bs no viene null), se muestra SOLO el monto en bolívares — nunca los
// dos juntos.
function formatMontoDia(usd, bs) {
  if (bs != null) {
    return formatBsRaw(bs);
  }
  return Number(usd) > 0 ? `$${formatMonto(usd)}` : '—';
}

function FlujoBancarioPage({ isMobile, onBack }) {
  const [mesIso, setMesIso] = useState(mesActualIso());
  const [bancoClave, setBancoClave] = useState('');
  const [bancos, setBancos] = useState([]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // vista === 'detalle' reemplaza la tabla mensual por el detalle de un
  // dia+tipo puntual (se ve y navega como "otra pagina", sin depender del
  // router de la app — "Volver" regresa al mismo mes/banco seleccionado).
  const [vista, setVista] = useState('resumen');
  const [detalleParams, setDetalleParams] = useState(null);
  const [detalleData, setDetalleData] = useState(null);
  const [detalleLoading, setDetalleLoading] = useState(false);
  const [detalleError, setDetalleError] = useState('');

  const cargarResumen = useCallback(async (mes, banco) => {
    setLoading(true);
    setError('');
    try {
      const [anio, mesNum] = mes.split('-');
      const params = banco ? `?anio=${anio}&mes=${Number(mesNum)}&banco=${encodeURIComponent(banco)}` : '';
      const response = await fetch(`/api/admin/reportes/flujo-bancario/${params}`, { credentials: 'include', cache: 'no-store' });
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cargar el flujo bancario.');
      }
      setData(json);
      setBancos(json.bancos || []);
      if (!banco && json.bancos && json.bancos.length > 0) {
        setBancoClave(json.bancos[0].clave);
      }
    } catch (requestError) {
      setError(requestError.message || 'No se pudo cargar el flujo bancario.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    cargarResumen(mesIso, bancoClave);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!bancoClave) return;
    cargarResumen(mesIso, bancoClave);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mesIso, bancoClave]);

  const abrirDetalle = async (fecha, tipo) => {
    setVista('detalle');
    setDetalleParams({ fecha, tipo });
    setDetalleData(null);
    setDetalleError('');
    setDetalleLoading(true);
    try {
      const response = await fetch(
        `/api/admin/reportes/flujo-bancario/detalle/?fecha=${fecha}&banco=${encodeURIComponent(bancoClave)}&tipo=${tipo}`,
        { credentials: 'include', cache: 'no-store' },
      );
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cargar el detalle de ese día.');
      }
      setDetalleData(json);
    } catch (requestError) {
      setDetalleError(requestError.message || 'No se pudo cargar el detalle de ese día.');
    } finally {
      setDetalleLoading(false);
    }
  };

  const volverAlResumen = () => {
    setVista('resumen');
    setDetalleParams(null);
    setDetalleData(null);
    setDetalleError('');
  };

  const dias = data?.dias || [];
  const totalesMes = useMemo(() => {
    let entrada = 0;
    let salida = 0;
    dias.forEach((dia) => {
      entrada += Number(dia.entrada || 0);
      salida += Number(dia.salida || 0);
    });
    const entradaBs = Number(data?.total_entrada_bs || 0);
    const salidaBs = Number(data?.total_salida_bs || 0);
    return {
      entrada, salida, neto: entrada - salida,
      entradaBs, salidaBs, netoBs: entradaBs - salidaBs,
      hayBs: entradaBs > 0 || salidaBs > 0,
    };
  }, [dias, data]);

  if (vista === 'detalle' && detalleParams) {
    const movimientos = detalleData?.movimientos || [];
    const esEntrada = detalleParams.tipo === 'entrada';
    // Igual que cada fila: nunca se suman bolívares y dólares en un solo
    // número. Lo normal es que todos los movimientos de un banco compartan
    // moneda; si por algo raro hay mezcla, se muestran los dos totales aparte.
    const totalBs = movimientos.filter((m) => m.monto_bs != null).reduce((acc, m) => acc + Number(m.monto_bs), 0);
    const totalUsd = movimientos.filter((m) => m.monto_bs == null).reduce((acc, m) => acc + Number(m.monto), 0);
    return (
      <section style={containerStyle(isMobile)}>
        <button type="button" onClick={volverAlResumen} style={backButtonStyle}>
          ← Volver al flujo del mes
        </button>

        <div>
          <h2 style={titleStyle(isMobile)}>
            {esEntrada ? 'Entradas' : 'Salidas'} del {formatFechaCorta(detalleParams.fecha)}
          </h2>
          <p style={subtitleStyle}>{data?.banco} — {formatFechaCorta(detalleParams.fecha)}/{mesIso.split('-')[0]}</p>
        </div>

        {detalleLoading ? <div style={emptyStyle}>Cargando...</div> : null}
        {!detalleLoading && detalleError ? <div style={noticeStyle}>{detalleError}</div> : null}

        {!detalleLoading && !detalleError && detalleData ? (
          movimientos.length === 0 ? (
            <div style={emptyStyle}>No hay {esEntrada ? 'entradas' : 'salidas'} registradas ese día para este banco.</div>
          ) : (
            <div style={tableWrapStyle}>
              <div style={detalleTableStyle(esEntrada)}>
                <div style={headStyle}>Hora</div>
                <div style={headStyle}>Tipo</div>
                {!esEntrada ? <div style={headStyle}>ID</div> : null}
                <div style={headStyle}>Nombre</div>
                <div style={headStyle}>Método</div>
                <div style={headStyle}>Referencia</div>
                <div style={headStyle}>Monto</div>
                {movimientos.map((movimiento) => (
                  <div key={`${movimiento.tipo_registro}-${movimiento.id}`} style={rowFragmentStyle}>
                    <div style={cellStyle}>{TIPOS_SIN_HORA.has(movimiento.tipo_registro) ? '—' : formatHora(movimiento.fecha_hora)}</div>
                    <div style={cellStyle}>{TIPO_REGISTRO_LABEL[movimiento.tipo_registro] || movimiento.tipo_registro}</div>
                    {!esEntrada ? <div style={{ ...cellStyle, fontWeight: 700, color: '#ffd9a0' }}>{movimiento.documento_codigo || '—'}</div> : null}
                    <div style={cellStyle}>{movimiento.nombre}</div>
                    <div style={cellStyle}>{movimiento.metodo_pago_nombre}</div>
                    <div style={cellStyle}>{movimiento.referencia || '—'}</div>
                    <div style={{ ...cellStyle, fontWeight: 700, color: esEntrada ? '#8fffb0' : '#ff9d9d' }}>
                      {formatMontoMovimiento(movimiento)}
                    </div>
                  </div>
                ))}
                <div style={{ ...cellStyle, ...totalCellStyle, fontWeight: 800 }}>Total</div>
                {!esEntrada ? <div style={{ ...cellStyle, ...totalCellStyle }} /> : null}
                <div style={{ ...cellStyle, ...totalCellStyle }} />
                <div style={{ ...cellStyle, ...totalCellStyle }} />
                <div style={{ ...cellStyle, ...totalCellStyle }} />
                <div style={{ ...cellStyle, ...totalCellStyle }} />
                <div style={{ ...cellStyle, ...totalCellStyle, fontWeight: 800, color: esEntrada ? '#8fffb0' : '#ff9d9d' }}>
                  {totalBs > 0 ? formatBsRaw(totalBs) : null}
                  {totalBs > 0 && totalUsd > 0 ? ' + ' : ''}
                  {totalUsd > 0 ? `$${formatMonto(totalUsd)}` : null}
                </div>
              </div>
            </div>
          )
        ) : null}
      </section>
    );
  }

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>
        ← Volver a Contabilidad
      </button>

      <div>
        <h2 style={titleStyle(isMobile)}>Flujo bancario diario</h2>
        <p style={subtitleStyle}>Entradas y salidas de dinero, día por día, para el banco que elijas.</p>
      </div>

      <div style={filtersRowStyle(isMobile)}>
        <label style={dateLabelStyle}>
          Mes
          <input type="month" value={mesIso} onChange={(event) => setMesIso(event.target.value)} style={dateInputStyle} />
        </label>
        <label style={dateLabelStyle}>
          Banco
          <select value={bancoClave} onChange={(event) => setBancoClave(event.target.value)} style={dateInputStyle}>
            {bancos.length === 0 ? <option value="">Sin bancos configurados</option> : null}
            {bancos.map((banco) => (
              <option key={banco.clave} value={banco.clave}>{banco.nombre}</option>
            ))}
          </select>
        </label>
      </div>

      {loading ? <div style={emptyStyle}>Cargando reporte...</div> : null}
      {!loading && error ? <div style={noticeStyle}>{error}</div> : null}

      {!loading && !error && data && data.banco ? (
        <section style={panelStyle}>
          <div style={sectionTitleStyle}>{data.banco} — {mesIso}</div>

          <div style={tableWrapStyle}>
            <div style={resumenTableStyle}>
              <div style={headStyle}>Fecha</div>
              <div style={headStyle}>Entrada</div>
              <div style={headStyle}>Salida</div>
              {dias.map((dia) => (
                <div key={dia.fecha} style={rowFragmentStyle}>
                  <div style={cellStyle}>{formatFechaCorta(dia.fecha)} <span style={diaSemanaStyle}>{formatDiaSemana(dia.fecha)}</span></div>
                  <button
                    type="button"
                    onClick={() => Number(dia.entrada) > 0 && abrirDetalle(dia.fecha, 'entrada')}
                    style={montoCellButtonStyle(Number(dia.entrada) > 0, '#8fffb0')}
                    disabled={Number(dia.entrada) <= 0}
                  >
                    {formatMontoDia(dia.entrada, dia.entrada_bs)}
                  </button>
                  <button
                    type="button"
                    onClick={() => Number(dia.salida) > 0 && abrirDetalle(dia.fecha, 'salida')}
                    style={montoCellButtonStyle(Number(dia.salida) > 0, '#ff9d9d')}
                    disabled={Number(dia.salida) <= 0}
                  >
                    {formatMontoDia(dia.salida, dia.salida_bs)}
                  </button>
                </div>
              ))}
              <div style={{ ...cellStyle, ...totalCellStyle, fontWeight: 800 }}>Total del mes</div>
              <div style={{ ...cellStyle, ...totalCellStyle, fontWeight: 800, color: '#8fffb0' }}>
                {totalesMes.hayBs ? formatBsRaw(totalesMes.entradaBs) : `$${formatMonto(totalesMes.entrada)}`}
              </div>
              <div style={{ ...cellStyle, ...totalCellStyle, fontWeight: 800, color: '#ff9d9d' }}>
                {totalesMes.hayBs ? formatBsRaw(totalesMes.salidaBs) : `$${formatMonto(totalesMes.salida)}`}
              </div>
            </div>
          </div>

          <div style={summaryStyle}>
            Neto del mes:{' '}
            <span style={{ color: (totalesMes.hayBs ? totalesMes.netoBs : totalesMes.neto) >= 0 ? '#8fffb0' : '#ff9d9d', fontWeight: 800 }}>
              {totalesMes.hayBs ? formatBsRaw(totalesMes.netoBs) : `$${formatMonto(totalesMes.neto)}`}
            </span>
          </div>
        </section>
      ) : null}

      {!loading && !error && data && !data.banco ? (
        <div style={emptyStyle}>Elige un banco para ver su flujo del mes.</div>
      ) : null}
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 26 : 32 });
const subtitleStyle = { margin: '8px 0 0', color: '#d2c3c3', lineHeight: 1.6 };
const filtersRowStyle = (isMobile) => ({
  display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: isMobile ? 'stretch' : 'flex-end', flexDirection: isMobile ? 'column' : 'row',
});
const dateLabelStyle = { display: 'flex', flexDirection: 'column', gap: 6, color: '#f2e6e6', fontSize: 13, fontWeight: 700, minWidth: 200 };
const dateInputStyle = { borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff' };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const sectionTitleStyle = { color: '#fff', fontSize: 19, fontWeight: 700 };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const tableWrapStyle = { overflowX: 'auto' };
const resumenTableStyle = { display: 'grid', gridTemplateColumns: 'minmax(120px,0.6fr) minmax(140px,1fr) minmax(140px,1fr)', minWidth: 460, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
// En las salidas hay una columna extra "ID" (Lote #36 / Gasto #536) para ubicar rapido
// la compra o el gasto en Cuentas por pagar.
const detalleTableStyle = (esEntrada) => ({ display: 'grid', gridTemplateColumns: esEntrada ? 'minmax(80px,0.5fr) minmax(100px,0.6fr) minmax(200px,1.6fr) minmax(140px,0.9fr) minmax(120px,0.8fr) minmax(130px,0.9fr)' : 'minmax(80px,0.5fr) minmax(100px,0.6fr) minmax(110px,0.7fr) minmax(200px,1.6fr) minmax(140px,0.9fr) minmax(120px,0.8fr) minmax(130px,0.9fr)', minWidth: esEntrada ? 900 : 1010, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' });
const headStyle = { padding: '12px 14px', background: 'rgba(255,255,255,0.06)', color: '#ffb0b0', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '14px', borderTop: '1px solid rgba(255,255,255,0.08)', color: '#f2e6e6', display: 'grid', alignContent: 'center' };
const totalCellStyle = { background: 'rgba(255,255,255,0.04)' };
const diaSemanaStyle = { color: '#c8bbbb', fontSize: 11, textTransform: 'uppercase', marginLeft: 6 };
const rowFragmentStyle = { display: 'contents' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const summaryStyle = { color: '#c8bbbb', fontSize: 14 };

const montoCellButtonStyle = (clickable, color) => ({
  ...cellStyle,
  fontWeight: 700,
  color: clickable ? color : '#6b6060',
  background: 'transparent',
  border: 'none',
  textAlign: 'left',
  cursor: clickable ? 'pointer' : 'default',
  textDecoration: clickable ? 'underline' : 'none',
  fontSize: 14,
  fontFamily: 'inherit',
});

export default FlujoBancarioPage;

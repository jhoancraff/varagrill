import { Fragment, useCallback, useEffect, useState } from 'react';
import { RangoFechas } from './FiltroFechas';

function todayIso() {
  const now = new Date();
  const offset = now.getTimezoneOffset();
  const local = new Date(now.getTime() - offset * 60000);
  return local.toISOString().slice(0, 10);
}

function startOfMonthIso() {
  const now = new Date();
  const offset = now.getTimezoneOffset();
  const local = new Date(now.getFullYear(), now.getMonth(), 1);
  const localAdjusted = new Date(local.getTime() - offset * 60000);
  return localAdjusted.toISOString().slice(0, 10);
}

function formatMonto(value) {
  const number = Number(value || 0);
  return number.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatMontoCuenta(monto, moneda) {
  return moneda === 'VES' ? `Bs. ${formatMonto(monto)}` : `$${formatMonto(monto)}`;
}

const FILTROS_INICIALES = { desde: startOfMonthIso(), hasta: todayIso(), id: '', cuentaId: '' };

function HistorialTransferenciasPage({ isMobile, onBack }) {
  const [filtros, setFiltros] = useState(FILTROS_INICIALES);
  const [metodos, setMetodos] = useState([]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetch('/api/admin/metodos-pago/', { credentials: 'include', cache: 'no-store' })
      .then((response) => response.json())
      .then((json) => {
        if (json.ok) setMetodos(Array.isArray(json.metodos_pago) ? json.metodos_pago : []);
      })
      .catch(() => {});
  }, []);

  const buscar = useCallback(async (filtrosActuales) => {
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      if (filtrosActuales.id) {
        params.set('id', filtrosActuales.id);
      } else {
        if (filtrosActuales.desde) params.set('desde', filtrosActuales.desde);
        if (filtrosActuales.hasta) params.set('hasta', filtrosActuales.hasta);
        if (filtrosActuales.cuentaId) params.set('cuenta_id', filtrosActuales.cuentaId);
      }
      const response = await fetch(`/api/admin/transferencias-cuentas/?${params.toString()}`, {
        credentials: 'include', cache: 'no-store',
      });
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cargar el historial de transferencias.');
      }
      setData(json);
    } catch (requestError) {
      setError(requestError.message || 'No se pudo cargar el historial de transferencias.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    buscar(filtros);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleBuscar = (event) => {
    event.preventDefault();
    buscar(filtros);
  };

  const handleLimpiar = () => {
    setFiltros(FILTROS_INICIALES);
    buscar(FILTROS_INICIALES);
  };

  const transferencias = data?.transferencias || [];

  return (
    <section style={containerStyle(isMobile)}>
      <div className="no-print" style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          ← Volver a Disponibilidad
        </button>
        <button type="button" onClick={() => window.print()} style={printButtonStyle}>
          Imprimir / Guardar PDF
        </button>
      </div>

      <div>
        <h2 style={titleStyle(isMobile)}>Historial de transferencias</h2>
      </div>

      <form onSubmit={handleBuscar} className="no-print" style={filtrosRowStyle(isMobile)}>
        <RangoFechas
          desde={filtros.desde}
          hasta={filtros.hasta}
          onChange={(rango) => setFiltros((f) => ({ ...f, desde: rango.desde, hasta: rango.hasta }))}
        />
        <label style={fieldStyle}>
          <span style={labelStyle}>ID de transferencia</span>
          <input
            type="number" placeholder="Ej: 42" value={filtros.id}
            onChange={(event) => setFiltros((f) => ({ ...f, id: event.target.value }))}
            style={inputStyle}
          />
        </label>
        <label style={fieldStyle}>
          <span style={labelStyle}>Cuenta</span>
          <select
            value={filtros.cuentaId}
            onChange={(event) => setFiltros((f) => ({ ...f, cuentaId: event.target.value }))}
            style={inputStyle}
          >
            <option value="">Todas</option>
            {metodos.map((metodo) => (
              <option key={metodo.id} value={metodo.id}>{metodo.nombre}{!metodo.activo ? ' (inactiva)' : ''}</option>
            ))}
          </select>
        </label>
        <div style={botonesFiltroStyle}>
          <button type="submit" style={buscarButtonStyle}>Buscar</button>
          <button type="button" onClick={handleLimpiar} style={limpiarButtonStyle}>Limpiar filtros</button>
        </div>
      </form>

      {loading ? <div style={emptyStyle}>Cargando...</div> : null}
      {!loading && error ? <div style={noticeStyle}>{error}</div> : null}

      {!loading && !error && data ? (
        <section style={panelStyle}>
          <div style={resumenStyle}>
            <span><strong>{data.total}</strong> transferencia(s) encontrada(s)</span>
            <span>Suma en USD: <strong>${formatMonto(data.total_usd)}</strong></span>
          </div>

          {transferencias.length === 0 ? (
            <div style={emptyStyle}>No hay transferencias para este filtro.</div>
          ) : (
            <div style={tableWrapStyle}>
              <div style={tableStyle}>
                <div style={headStyle}>ID</div>
                <div style={headStyle}>Fecha</div>
                <div style={headStyle}>Origen</div>
                <div style={headStyle}>Destino</div>
                <div style={headStyle}>USD</div>
                <div style={headStyle}>Tasa</div>
                <div style={headStyle}>Concepto</div>
                <div style={headStyle}>Referencia</div>
                <div style={headStyle}>Registrado por</div>
                {transferencias.map((t) => (
                  <Fragment key={t.id}>
                    <div style={cellStyle}>#{t.id}</div>
                    <div style={cellStyle}>{t.fecha}</div>
                    <div style={cellStyle}>
                      {t.cuenta_origen_nombre}
                      <div style={submontoStyle}>{formatMontoCuenta(t.monto_origen, t.moneda_origen)}</div>
                    </div>
                    <div style={cellStyle}>
                      {t.cuenta_destino_nombre}
                      <div style={submontoStyle}>{formatMontoCuenta(t.monto_destino, t.moneda_destino)}</div>
                    </div>
                    <div style={{ ...cellStyle, fontWeight: 700, color: '#c9b8ff' }}>${formatMonto(t.monto_usd)}</div>
                    <div style={cellStyle}>{t.tasa_cambio ? formatMonto(t.tasa_cambio) : '—'}</div>
                    <div style={cellStyle}>{t.concepto}</div>
                    <div style={cellStyle}>{t.referencia || '—'}</div>
                    <div style={cellStyle}>{t.creado_por || '—'}</div>
                  </Fragment>
                ))}
              </div>
            </div>
          )}
        </section>
      ) : null}
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 26 : 32 });
const filtrosRowStyle = (isMobile) => ({ display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'flex-end', flexDirection: isMobile ? 'column' : 'row' });
const fieldStyle = { display: 'grid', gap: 6, minWidth: 140 };
const labelStyle = { color: '#f2e6e6', fontSize: 12.5, fontWeight: 700 };
const inputStyle = { borderRadius: 10, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '9px 10px', color: '#fff', fontSize: 13.5 };
const botonesFiltroStyle = { display: 'flex', gap: 8 };
const buscarButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 18px', background: 'linear-gradient(90deg, #6d28d9 0%, #4f46e5 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const limpiarButtonStyle = { border: '1px solid rgba(255,255,255,0.16)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.05)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const resumenStyle = { display: 'flex', gap: 20, flexWrap: 'wrap', color: '#d2c3c3', fontSize: 14 };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8' };
const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(60px,0.5fr) minmax(100px,0.7fr) minmax(150px,1.1fr) minmax(150px,1.1fr) minmax(100px,0.7fr) minmax(90px,0.6fr) minmax(180px,1.4fr) minmax(110px,0.8fr) minmax(120px,0.8fr)', minWidth: 1180, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(255,255,255,0.06)', color: '#c9b8ff', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '14px', borderTop: '1px solid rgba(255,255,255,0.08)', color: '#f2e6e6', display: 'grid', alignContent: 'center' };
const submontoStyle = { color: '#c8bbbb', fontSize: 12, marginTop: 2 };
const printButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default HistorialTransferenciasPage;

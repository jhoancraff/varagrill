import { Fragment, useCallback, useEffect, useState } from 'react';
import { formatMontoDocumento } from '../utils/currency';

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

function formatFechaHora(fechaIso) {
  const date = new Date(fechaIso);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  return date.toLocaleString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

const FILTROS_INICIALES = { desde: startOfMonthIso(), hasta: todayIso(), cuentaId: '' };

function HistorialIngresosNoFacturadosPage({ isMobile, onBack }) {
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
      if (filtrosActuales.desde) params.set('desde', filtrosActuales.desde);
      if (filtrosActuales.hasta) params.set('hasta', filtrosActuales.hasta);
      if (filtrosActuales.cuentaId) params.set('metodo_pago_id', filtrosActuales.cuentaId);
      const response = await fetch(`/api/admin/reportes/ingresos-no-facturados/?${params.toString()}`, {
        credentials: 'include', cache: 'no-store',
      });
      const json = await response.json();
      if (!response.ok || !json.ok) {
        throw new Error(json.message || 'No se pudo cargar el historial de ingresos no facturados.');
      }
      setData(json);
    } catch (requestError) {
      setError(requestError.message || 'No se pudo cargar el historial de ingresos no facturados.');
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

  const ingresos = data?.ingresos || [];

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
        <h2 style={titleStyle(isMobile)}>Ingresos no facturados</h2>
      </div>

      <form onSubmit={handleBuscar} className="no-print" style={filtrosRowStyle(isMobile)}>
        <label style={fieldStyle}>
          <span style={labelStyle}>Desde</span>
          <input
            type="date" value={filtros.desde} max={filtros.hasta}
            onChange={(event) => setFiltros((f) => ({ ...f, desde: event.target.value }))}
            style={inputStyle}
          />
        </label>
        <label style={fieldStyle}>
          <span style={labelStyle}>Hasta</span>
          <input
            type="date" value={filtros.hasta} max={todayIso()}
            onChange={(event) => setFiltros((f) => ({ ...f, hasta: event.target.value }))}
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
            <span><strong>{data.total}</strong> ingreso(s) encontrado(s)</span>
            <span>Suma en USD: <strong>${formatMonto(data.total_usd)}</strong></span>
          </div>

          {ingresos.length === 0 ? (
            <div style={emptyStyle}>No hay ingresos no facturados para este filtro.</div>
          ) : (
            <div style={tableWrapStyle}>
              <div style={tableStyle}>
                <div style={headStyle}>Fecha</div>
                <div style={headStyle}>Cuenta</div>
                <div style={headStyle}>Monto</div>
                <div style={headStyle}>Motivo / descripcion</div>
                <div style={headStyle}>Registrado por</div>
                {ingresos.map((ingreso) => (
                  <Fragment key={ingreso.id}>
                    <div style={cellStyle}>{formatFechaHora(ingreso.fecha_creacion)}</div>
                    <div style={cellStyle}>{ingreso.metodo_pago_nombre}</div>
                    <div style={{ ...cellStyle, fontWeight: 700, color: '#8fffb0' }}>
                      {formatMontoDocumento(ingreso.monto, ingreso.moneda, ingreso.tasa_cambio_referencia)}
                    </div>
                    <div style={cellStyle}>{ingreso.descripcion || '—'}</div>
                    <div style={cellStyle}>{ingreso.registrado_por || '—'}</div>
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
const tableStyle = { display: 'grid', gridTemplateColumns: 'minmax(150px,0.8fr) minmax(150px,0.9fr) minmax(120px,0.7fr) minmax(220px,1.6fr) minmax(140px,0.9fr)', minWidth: 1000, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 14, overflow: 'hidden' };
const headStyle = { padding: '12px 14px', background: 'rgba(255,255,255,0.06)', color: '#c9b8ff', fontSize: 12, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 800 };
const cellStyle = { padding: '14px', borderTop: '1px solid rgba(255,255,255,0.08)', color: '#f2e6e6', display: 'grid', alignContent: 'center' };
const printButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default HistorialIngresosNoFacturadosPage;

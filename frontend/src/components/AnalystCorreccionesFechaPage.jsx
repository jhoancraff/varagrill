import { useCallback, useEffect, useRef, useState } from 'react';
import ConfirmModal from './ConfirmModal';
import { RangoFechas, toIso, todayIso } from './FiltroFechas';
import Toast from './Toast';
import useConfirmacionesFecha, { postConAdvertencias } from '../hooks/useConfirmacionesFecha';
import useToast from '../hooks/useToast';
import { formatearFecha, hoyIso } from '../utils/fechas';

const TABS = [
  { id: 'abono_gasto', label: 'Pagos de gastos' },
  { id: 'abono_compra', label: 'Pagos de compras' },
  { id: 'compra', label: 'Compras' },
  { id: 'historial', label: 'Historial de correcciones' },
];

const MOTIVO_MINIMO = 10;

function primerDiaDelMesIso() {
  const hoy = new Date();
  return toIso(new Date(hoy.getFullYear(), hoy.getMonth(), 1));
}

function formatMonto(valor) {
  return `$${Number(valor || 0).toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatFechaHora(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString('es-VE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// Corregir la fecha de un pago (de un gasto o de una compra) o de una compra ya registrados, cuando se cargaron
// con una fecha equivocada. El momento exacto del registro nunca cambia; cada correccion pide un motivo, una
// confirmacion (y la aceptacion de advertencias si toca un dia con la caja o la conciliacion cerradas) y queda en
// el historial con quien la hizo (ver correcciones_fecha_views.py). Se abre desde Contabilidad > "Corregir fechas".
function AnalystCorreccionesFechaPage({ isMobile, onBack }) {
  const [tab, setTab] = useState('abono_gasto');
  const [desde, setDesde] = useState(primerDiaDelMesIso());
  const [hasta, setHasta] = useState(todayIso());
  const [busqueda, setBusqueda] = useState('');
  const [busquedaAplicada, setBusquedaAplicada] = useState('');
  const [items, setItems] = useState([]);
  const [truncado, setTruncado] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editando, setEditando] = useState(null);
  const [fechaNueva, setFechaNueva] = useState('');
  const [motivo, setMotivo] = useState('');
  const [confirmando, setConfirmando] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const peticionRef = useRef(0);
  const { toast, showSuccess, showError, hideToast } = useToast();
  const { confirmarAdvertencias, modales } = useConfirmacionesFecha();

  // Espera a que se deje de escribir para no pedir la lista en cada tecla.
  useEffect(() => {
    const timer = setTimeout(() => setBusquedaAplicada(busqueda.trim()), 300);
    return () => clearTimeout(timer);
  }, [busqueda]);

  const cargar = useCallback(async () => {
    const numeroPeticion = peticionRef.current + 1;
    peticionRef.current = numeroPeticion;
    setLoading(true);
    setError('');
    try {
      const params = new URLSearchParams({ tipo: tab, desde, hasta });
      if (busquedaAplicada) params.set('q', busquedaAplicada);
      const response = await fetch(`/api/admin/correcciones-fecha/?${params.toString()}`, { credentials: 'include', cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (numeroPeticion !== peticionRef.current) return;
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo cargar la información.');
      }
      setItems(Array.isArray(data.items) ? data.items : []);
      setTruncado(Boolean(data.truncado));
    } catch (requestError) {
      if (numeroPeticion !== peticionRef.current) return;
      setItems([]);
      setError(requestError.message || 'No se pudo cargar la información.');
    } finally {
      if (numeroPeticion === peticionRef.current) setLoading(false);
    }
  }, [tab, desde, hasta, busquedaAplicada]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const abrirEdicion = (item) => {
    setEditando(item);
    setFechaNueva(item.fecha);
    setMotivo('');
  };

  const cerrarEdicion = () => {
    if (guardando) return;
    setEditando(null);
    setConfirmando(false);
  };

  const motivoValido = motivo.trim().length >= MOTIVO_MINIMO;
  const fechaCambia = Boolean(editando) && Boolean(fechaNueva) && fechaNueva !== editando.fecha;
  const puedeContinuar = fechaCambia && motivoValido;

  const aplicarCorreccion = async () => {
    setGuardando(true);
    try {
      const resultado = await postConAdvertencias('/api/admin/correcciones-fecha/', {
        tipo: editando.tipo,
        objeto_id: editando.id,
        fecha_nueva: fechaNueva,
        motivo: motivo.trim(),
      }, confirmarAdvertencias);
      if (resultado.cancelado) {
        setConfirmando(false);
        return;
      }
      const { response, data } = resultado;
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo corregir la fecha.');
      }
      setConfirmando(false);
      setEditando(null);
      showSuccess(data.message || 'Fecha corregida.');
      cargar();
    } catch (requestError) {
      setConfirmando(false);
      showError(requestError.message || 'No se pudo corregir la fecha.');
    } finally {
      setGuardando(false);
    }
  };

  const esHistorial = tab === 'historial';
  const etiquetaFecha = tab === 'compra' ? 'Fecha de la compra' : 'Fecha del pago';

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>← Volver</button>

      <div>
        <h2 style={titleStyle(isMobile)}>Corregir fechas</h2>
        <p style={subtitleStyle}>
          Si un pago o una compra se registró con una fecha equivocada, cámbiala aquí. El momento exacto en que se
          registró no cambia, y cada corrección queda en el historial con quién la hizo y por qué.
        </p>
      </div>

      <Toast toast={toast} onClose={hideToast} />
      {modales}

      <div style={tabsStyle}>
        {TABS.map((opcion) => (
          <button key={opcion.id} type="button" onClick={() => setTab(opcion.id)} style={tabButtonStyle(tab === opcion.id)}>
            {opcion.label}
          </button>
        ))}
      </div>

      <RangoFechas
        desde={desde}
        hasta={hasta}
        onChange={(rango) => {
          setDesde(rango.desde);
          setHasta(rango.hasta);
        }}
      />

      <input
        type="text"
        value={busqueda}
        onChange={(event) => setBusqueda(event.target.value)}
        placeholder={esHistorial ? 'Buscar por descripción, motivo o número...' : 'Buscar por descripción, proveedor, factura, referencia o número...'}
        style={inputStyle}
        aria-label="Buscar"
      />
      {esHistorial ? (
        <p style={hintStyle}>El rango filtra por el día en que se hizo la corrección.</p>
      ) : (
        <p style={hintStyle}>El rango filtra por la fecha actual del {tab === 'compra' ? 'documento' : 'pago'}.</p>
      )}

      {loading ? <div style={emptyStyle}>Cargando...</div> : null}
      {!loading && error ? <div style={noticeStyle}>{error}</div> : null}

      {!loading && !error ? (
        items.length === 0 ? (
          <div style={emptyStyle}>
            {esHistorial ? 'No hay correcciones en este período.' : 'No hay registros en este período.'}
          </div>
        ) : (
          <div style={{ display: 'grid', gap: 10 }}>
            {truncado ? <div style={hintStyle}>Se muestran los primeros 300 resultados: acota las fechas o busca para ver el resto.</div> : null}

            {esHistorial ? items.map((item) => (
              <div key={item.id} style={rowStyle}>
                <div style={{ display: 'grid', gap: 4, minWidth: 0 }}>
                  <div style={rowTitleStyle}>{item.descripcion}</div>
                  <div style={rowDetailStyle}>
                    <strong>{formatearFecha(item.fecha_anterior)}</strong> → <strong>{formatearFecha(item.fecha_nueva)}</strong>
                    {' '}· Motivo: {item.motivo}
                  </div>
                  <div style={rowDetailStyle}>{item.por || 'Usuario'} · {formatFechaHora(item.fecha)}</div>
                </div>
              </div>
            )) : items.map((item) => (
              <div key={`${item.tipo}-${item.id}`} style={rowStyle}>
                <div style={{ display: 'grid', gap: 4, minWidth: 0 }}>
                  <div style={rowTitleStyle}>{item.titulo}</div>
                  {item.detalle ? <div style={rowDetailStyle}>{item.detalle}</div> : null}
                  <div style={rowDetailStyle}>
                    {formatMonto(item.monto)}{item.metodo_pago ? ` · ${item.metodo_pago}` : ''}
                    {' '}· {etiquetaFecha}: <strong>{formatearFecha(item.fecha)}</strong>
                    {' '}· Registrado {formatFechaHora(item.fecha_registro)}
                  </div>
                  {item.correcciones > 0 ? (
                    <div style={{ ...rowDetailStyle, color: 'var(--vg-f-ffcd56)' }}>
                      Corregida {item.correcciones} {item.correcciones === 1 ? 'vez' : 'veces'} (ver historial)
                    </div>
                  ) : null}
                  {!item.editable ? <div style={{ ...rowDetailStyle, color: 'var(--vg-f-ffb0b0)' }}>{item.motivo_bloqueo}</div> : null}
                </div>
                <button type="button" onClick={() => abrirEdicion(item)} style={editButtonStyle} disabled={!item.editable}>
                  Cambiar fecha
                </button>
              </div>
            ))}
          </div>
        )
      ) : null}

      {editando ? (
        <div style={backdropStyle} onClick={cerrarEdicion}>
          <div style={cardStyle} onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true">
            <div style={modalTitleStyle}>Cambiar fecha</div>
            <div style={{ ...rowDetailStyle, marginBottom: 12 }}>
              <div style={rowTitleStyle}>{editando.titulo}</div>
              <div>{formatMonto(editando.monto)}{editando.metodo_pago ? ` · ${editando.metodo_pago}` : ''}</div>
              <div>{etiquetaFecha} actual: <strong>{formatearFecha(editando.fecha)}</strong></div>
            </div>

            <label style={fieldStyle}>
              <span style={labelStyle}>Nueva fecha</span>
              <input
                type="date"
                value={fechaNueva}
                max={hoyIso()}
                onChange={(event) => setFechaNueva(event.target.value)}
                style={inputStyle}
              />
            </label>
            <label style={{ ...fieldStyle, marginTop: 12 }}>
              <span style={labelStyle}>Motivo de la corrección (obligatorio, queda en la auditoría)</span>
              <textarea
                value={motivo}
                onChange={(event) => setMotivo(event.target.value)}
                rows={3}
                maxLength={255}
                placeholder="Ejemplo: se registró hoy pero el pago se hizo el viernes"
                style={{ ...inputStyle, resize: 'vertical' }}
              />
              <span style={hintStyle}>
                {motivoValido ? 'Motivo listo.' : `Escribe al menos ${MOTIVO_MINIMO} caracteres (${motivo.trim().length}/${MOTIVO_MINIMO}).`}
              </span>
            </label>

            <div style={footerStyle}>
              <button type="button" onClick={cerrarEdicion} style={cancelButtonStyle}>Cancelar</button>
              <button
                type="button"
                onClick={() => setConfirmando(true)}
                style={{ ...confirmButtonStyle, opacity: puedeContinuar ? 1 : 0.5, cursor: puedeContinuar ? 'pointer' : 'not-allowed' }}
                disabled={!puedeContinuar}
              >
                Continuar
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <ConfirmModal
        open={Boolean(editando) && confirmando}
        title="Confirmar corrección de fecha"
        message={
          editando
            ? `Vas a cambiar la fecha de "${editando.titulo}" del ${formatearFecha(editando.fecha)} al ${formatearFecha(fechaNueva)}. `
              + 'Los reportes de caja, banco y conciliación de esos días van a cambiar. Queda registrado con tu usuario y el motivo. ¿Confirmas?'
            : ''
        }
        confirmLabel="Sí, cambiar la fecha"
        cancelLabel="Volver"
        onConfirm={aplicarCorreccion}
        onCancel={() => setConfirmando(false)}
        busy={guardando}
      />
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const titleStyle = (isMobile) => ({ margin: 0, color: 'var(--vg-text-strong)', fontSize: isMobile ? 26 : 32 });
const subtitleStyle = { margin: '8px 0 0', color: 'var(--vg-f-d2c3c3)', lineHeight: 1.6, maxWidth: 760 };
const tabsStyle = { display: 'flex', gap: 8, flexWrap: 'wrap' };
const tabButtonStyle = (activo) => ({
  border: `1px solid ${activo ? 'var(--vg-f-ff9191-a300)' : 'rgba(var(--vg-ink), 0.14)'}`,
  borderRadius: 999, padding: '9px 16px', fontWeight: 700, cursor: 'pointer', fontSize: 13,
  background: activo ? 'linear-gradient(90deg, #bf1f1f 0%, var(--vg-accent-primary) 100%)' : 'rgba(var(--vg-ink), 0.04)',
  color: activo ? '#fff' : 'var(--vg-text-strong)',
});
const inputStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 10, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-161010)', padding: '9px 10px', color: 'var(--vg-text-strong)', fontSize: 13 };
const fieldStyle = { display: 'grid', gap: 6 };
const labelStyle = { color: 'var(--vg-f-f0b4b4)', fontSize: 12.5, fontWeight: 700 };
const hintStyle = { margin: 0, color: 'var(--vg-f-a89999)', fontSize: 12 };
const emptyStyle = { minHeight: 60, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(var(--vg-ink), 0.12)', color: 'var(--vg-f-c8bbbb)' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid var(--vg-f-ff7e7e-a400)', background: 'rgba(145,33,33,0.25)', color: 'var(--vg-f-ffd3d3)' };
const rowStyle = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '14px 16px', borderRadius: 16, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)' };
const rowTitleStyle = { color: 'var(--vg-text-strong)', fontWeight: 700, fontSize: 15 };
const rowDetailStyle = { color: 'var(--vg-f-d2c3c3)', fontSize: 12.5, lineHeight: 1.5 };
const editButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.14)', borderRadius: 999, padding: '8px 14px', background: 'rgba(var(--vg-ink), 0.04)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer', fontSize: 12.5, whiteSpace: 'nowrap' };

const backdropStyle = { position: 'fixed', inset: 0, background: 'rgba(0, 0, 0, 0.6)', display: 'grid', placeItems: 'center', zIndex: 900, padding: 16 };
const cardStyle = {
  width: '100%', maxWidth: 460, maxHeight: '90vh', overflowY: 'auto', borderRadius: 20,
  border: '1px solid var(--vg-f-ff9191-a300)',
  background: 'linear-gradient(180deg, var(--vg-s-1c0c0c-a980) 0%, var(--vg-s-0a0808-a990) 100%)',
  padding: '22px 22px 18px', boxShadow: '0 20px 50px rgba(0, 0, 0, calc(0.45 * var(--vg-shadow-k)))',
};
const modalTitleStyle = { color: 'var(--vg-text-strong)', fontSize: 19, fontWeight: 800, marginBottom: 10 };
const footerStyle = { display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 18, flexWrap: 'wrap' };
const cancelButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.16)', borderRadius: 999, padding: '10px 16px', background: 'rgba(var(--vg-ink), 0.05)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer' };
const confirmButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, var(--vg-accent-primary) 100%)', color: '#fff', fontWeight: 700 };

export default AnalystCorreccionesFechaPage;

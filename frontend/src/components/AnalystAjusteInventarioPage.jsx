import { useCallback, useEffect, useRef, useState } from 'react';
import ConfirmModal from './ConfirmModal';
import { RangoFechas, toIso, todayIso } from './FiltroFechas';
import Toast from './Toast';
import useToast from '../hooks/useToast';
import { badgeEstadoStyle, estadoHoja, formatFechaHora, nombreHoja, nombreMes } from '../utils/ajusteInventario';

function primerDiaDelMesIso() {
  const hoy = new Date();
  return toIso(new Date(hoy.getFullYear(), hoy.getMonth(), 1));
}

// Lista de hojas de ajuste de inventario: cada hoja agrupa los ajustes de una tarea (un mismo dia puede tener
// varias) y se busca por fecha, numero, titulo o ingrediente. "Nueva hoja" crea una y la abre; tocar una abre
// su detalle (AnalystAjusteInventarioHojaPage, ruta 'admin-ingredients-ajuste:<id>' en WelcomeScreen). Aqui
// tambien vive el cierre mensual, que deja de solo lectura todas las hojas del mes.
function AnalystAjusteInventarioPage({ isMobile, onBack, onOpenHoja }) {
  const [desde, setDesde] = useState(primerDiaDelMesIso());
  const [hasta, setHasta] = useState(todayIso());
  const [busqueda, setBusqueda] = useState('');
  const [busquedaAplicada, setBusquedaAplicada] = useState('');
  const [estado, setEstado] = useState({ anio: null, mes: null, mes_cerrado: false, hojas: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [titulo, setTitulo] = useState('');
  const [creando, setCreando] = useState(false);
  const [cierreModalOpen, setCierreModalOpen] = useState(false);
  const [cerrandoMes, setCerrandoMes] = useState(false);
  const peticionRef = useRef(0);
  const { toast, showSuccess, showError, hideToast } = useToast();

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
      const params = new URLSearchParams({ desde, hasta });
      if (busquedaAplicada) params.set('q', busquedaAplicada);
      const response = await fetch(`/api/admin/inventario/ajuste/?${params.toString()}`, { credentials: 'include', cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (numeroPeticion !== peticionRef.current) return;
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudieron cargar las hojas de ajuste.');
      }
      setEstado(data);
    } catch (requestError) {
      if (numeroPeticion !== peticionRef.current) return;
      setError(requestError.message || 'No se pudieron cargar las hojas de ajuste.');
    } finally {
      if (numeroPeticion === peticionRef.current) setLoading(false);
    }
  }, [desde, hasta, busquedaAplicada]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const handleCrear = async (event) => {
    event.preventDefault();
    setCreando(true);
    try {
      const response = await fetch('/api/admin/inventario/ajuste/crear/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ titulo }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo crear la hoja.');
      }
      setTitulo('');
      onOpenHoja(data.ajuste.id);
    } catch (requestError) {
      showError(requestError.message || 'No se pudo crear la hoja.');
    } finally {
      setCreando(false);
    }
  };

  const handleCerrarMes = async () => {
    setCerrandoMes(true);
    try {
      const response = await fetch('/api/admin/inventario/cierre/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo cerrar el mes.');
      }
      setCierreModalOpen(false);
      showSuccess(data.message || 'Mes cerrado.');
      cargar();
    } catch (requestError) {
      setCierreModalOpen(false);
      showError(requestError.message || 'No se pudo cerrar el mes.');
    } finally {
      setCerrandoMes(false);
    }
  };

  const mesCerrado = !!estado.mes_cerrado;
  const hojas = estado.hojas || [];

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>
        ← Volver a Inventario
      </button>

      <div>
        <h2 style={titleStyle(isMobile)}>Ajuste de inventario</h2>
        <p style={subtitleStyle}>
          Cada hoja agrupa los ajustes de una tarea (un conteo, una merma...). Se arma como borrador y recién afecta el
          stock cuando la confirmas. Un mismo día puede tener varias hojas.
          {estado.mes ? ` Mes en curso: ${nombreMes(estado.mes)} de ${estado.anio}.` : ''}
        </p>
      </div>

      <Toast toast={toast} onClose={hideToast} />

      <section style={panelStyle}>
        <div style={sectionTitleStyle}>Nueva hoja</div>
        {mesCerrado ? (
          <p style={{ ...hintStyle, fontSize: 13 }}>
            El mes de {nombreMes(estado.mes)} ya fue cerrado, no se pueden crear más hojas de ajuste.
          </p>
        ) : (
          <form onSubmit={handleCrear} style={nuevaHojaStyle(isMobile)}>
            <label style={fieldStyle}>
              <span style={labelStyle}>Título (opcional)</span>
              <input
                value={titulo}
                onChange={(event) => setTitulo(event.target.value)}
                maxLength={120}
                placeholder="Ejemplo: Conteo cocina, Merma pork belly..."
                style={inputStyle}
              />
            </label>
            <button type="submit" style={primaryButtonStyle} disabled={creando}>
              {creando ? 'Creando...' : 'Crear hoja'}
            </button>
          </form>
        )}
      </section>

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
        placeholder="Buscar por número, título o ingrediente..."
        style={inputStyle}
        aria-label="Buscar hoja de ajuste"
      />

      {loading ? <div style={emptyStyle}>Cargando hojas...</div> : null}
      {!loading && error ? <div style={noticeStyle}>{error}</div> : null}

      {!loading && !error ? (
        hojas.length === 0 ? (
          <div style={emptyStyle}>No hay hojas de ajuste para este filtro.</div>
        ) : (
          <div style={{ display: 'grid', gap: 10 }}>
            <div style={resumenStyle}>
              <strong>{hojas.length}</strong> {hojas.length === 1 ? 'hoja' : 'hojas'}
            </div>
            {hojas.map((hoja) => {
              const estadoDeHoja = estadoHoja(hoja);
              return (
                <button key={hoja.id} type="button" onClick={() => onOpenHoja(hoja.id)} style={hojaRowStyle}>
                  <span style={{ display: 'grid', gap: 4, textAlign: 'left' }}>
                    <span style={{ color: 'var(--vg-text-strong)', fontWeight: 700, fontSize: 15 }}>{nombreHoja(hoja)}</span>
                    <span style={{ color: 'var(--vg-f-d2c3c3)', fontSize: 12.5 }}>
                      {formatFechaHora(hoja.fecha_creacion)} · {hoja.total_lineas} {hoja.total_lineas === 1 ? 'línea' : 'líneas'}
                      {hoja.lineas_pendientes > 0 && hoja.estado === 'confirmado' ? ` (${hoja.lineas_pendientes} sin guardar)` : ''}
                    </span>
                  </span>
                  <span style={badgeEstadoStyle(estadoDeHoja.clave)}>{estadoDeHoja.label}</span>
                </button>
              );
            })}
          </div>
        )
      ) : null}

      {!mesCerrado && estado.mes ? (
        <section style={panelStyle}>
          <div style={sectionTitleStyle}>Cierre mensual</div>
          <p style={hintStyle}>
            Cerrar el mes bloquea crear o editar hojas de {nombreMes(estado.mes)} — todas quedan de solo lectura. Antes de
            cerrar, confirma o quita las líneas pendientes de cada hoja.
          </p>
          <button type="button" onClick={() => setCierreModalOpen(true)} style={dangerButtonStyle}>
            Cerrar mes
          </button>
        </section>
      ) : null}

      <ConfirmModal
        open={cierreModalOpen}
        title="Cerrar mes"
        message={`Vas a cerrar el mes de ${nombreMes(estado.mes)} de ${estado.anio}. Ya no podrás crear ni editar hojas de ajuste de este mes. ¿Confirmas?`}
        confirmLabel="Sí, cerrar mes"
        cancelLabel="Cancelar"
        onConfirm={handleCerrarMes}
        onCancel={() => setCierreModalOpen(false)}
        busy={cerrandoMes}
      />
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const titleStyle = (isMobile) => ({ margin: 0, color: 'var(--vg-text-strong)', fontSize: isMobile ? 26 : 32 });
const subtitleStyle = { margin: '8px 0 0', color: 'var(--vg-f-d2c3c3)', lineHeight: 1.6, maxWidth: 760 };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)' };
const sectionTitleStyle = { color: 'var(--vg-text-strong)', fontSize: 17, fontWeight: 700 };
const emptyStyle = { minHeight: 60, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(var(--vg-ink), 0.12)', color: 'var(--vg-f-c8bbbb)' };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid var(--vg-f-ff7e7e-a400)', background: 'rgba(145,33,33,0.25)', color: 'var(--vg-f-ffd3d3)' };
const resumenStyle = { color: 'var(--vg-f-d2c3c3)', fontSize: 13 };

const nuevaHojaStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr auto', gap: 10, alignItems: 'end' });
const fieldStyle = { display: 'grid', gap: 6 };
const labelStyle = { color: 'var(--vg-f-f0b4b4)', fontSize: 12.5, fontWeight: 700 };
const inputStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 10, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-161010)', padding: '9px 10px', color: 'var(--vg-text-strong)', fontSize: 13 };
const hintStyle = { margin: 0, color: 'var(--vg-f-a89999)', fontSize: 12 };

const hojaRowStyle = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, width: '100%', boxSizing: 'border-box', padding: '14px 16px', borderRadius: 16, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)', cursor: 'pointer' };

const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, var(--vg-accent-primary) 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const dangerButtonStyle = { border: '1px solid var(--vg-f-ff7e7e-a400)', borderRadius: 999, padding: '6px 12px', background: 'rgba(145,33,33,0.25)', color: 'var(--vg-f-ffd3d3)', fontWeight: 700, cursor: 'pointer', fontSize: 12, width: 'fit-content' };

export default AnalystAjusteInventarioPage;

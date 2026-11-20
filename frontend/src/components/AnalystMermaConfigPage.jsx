import { useCallback, useEffect, useMemo, useState } from 'react';
import ConfirmModal from './ConfirmModal';
import Toast from './Toast';
import useToast from '../hooks/useToast';

const URL_MERMA = '/api/admin/merma-ingredientes/';
const EJEMPLO_RECETA = 500;

async function pedir(opciones) {
  const response = await fetch(URL_MERMA, { credentials: 'include', cache: 'no-store', ...opciones });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    throw new Error(data.message || 'No se pudo completar la operación.');
  }
  return data;
}

const numero = (valor, decimales = 2) => Number(valor).toLocaleString('es-ES', { maximumFractionDigits: decimales });
const sinTildes = (texto) => String(texto || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

// Qué se descuenta del inventario por cada 500 de receta: «500 g de receta → 1.000 g del inventario».
const ejemplo = (fila) => `${numero(EJEMPLO_RECETA)} → ${numero(EJEMPLO_RECETA * Number(fila.factor))} ${fila.unidad}`;

const AVISO_RECETAS = 'Actívalo solo si las recetas de este ingrediente están escritas en gramos ya limpios (lo aprovechable). '
  + 'Si la receta ya cuenta la pérdida (por ejemplo, 1.400 g crudos que rinden 1.000 g), se descontaría dos veces.';

// Costeo → Configuración de merma. Un ingrediente con «peso real» menor que el «contenido del envase» pierde una
// parte al prepararlo (pelar el aguacate, limpiar el cebollín...). El costo ya lo considera; con el interruptor
// encendido, el inventario también: al vender descuenta receta × envase ÷ peso real.
function AnalystMermaConfigPage({ isMobile, onBack }) {
  const [ingredientes, setIngredientes] = useState([]);
  const [resumen, setResumen] = useState({ con_merma: 0, activos: 0 });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busqueda, setBusqueda] = useState('');
  const [filtro, setFiltro] = useState('todos');
  const [seleccion, setSeleccion] = useState(() => new Set());
  const [abiertos, setAbiertos] = useState(() => new Set());
  const [confirmacion, setConfirmacion] = useState(null);
  const { toast, showSuccess, showError, hideToast } = useToast();

  const aplicar = (data) => {
    setIngredientes(data.ingredientes || []);
    setResumen(data.resumen || { con_merma: 0, activos: 0 });
  };

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      aplicar(await pedir({}));
    } catch (error) {
      showError(error.message);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const visibles = useMemo(() => {
    const texto = sinTildes(busqueda.trim());
    return ingredientes.filter((fila) => {
      if (filtro === 'activos' && !fila.descuenta_merma) return false;
      if (filtro === 'apagados' && fila.descuenta_merma) return false;
      return !texto || sinTildes(fila.nombre).includes(texto) || sinTildes(fila.categoria).includes(texto);
    });
  }, [ingredientes, busqueda, filtro]);

  const todosMarcados = visibles.length > 0 && visibles.every((fila) => seleccion.has(fila.id));

  const alternarSeleccion = (id) => setSeleccion((actual) => {
    const nuevo = new Set(actual);
    if (nuevo.has(id)) nuevo.delete(id); else nuevo.add(id);
    return nuevo;
  });

  const alternarTodos = () => setSeleccion((actual) => {
    const nuevo = new Set(actual);
    if (todosMarcados) visibles.forEach((fila) => nuevo.delete(fila.id));
    else visibles.forEach((fila) => nuevo.add(fila.id));
    return nuevo;
  });

  const alternarAbierto = (id) => setAbiertos((actual) => {
    const nuevo = new Set(actual);
    if (nuevo.has(id)) nuevo.delete(id); else nuevo.add(id);
    return nuevo;
  });

  // Todo cambio pasa primero por un diálogo que explica qué va a pasar con el inventario.
  const pedirCambio = (filas, activar) => {
    if (!filas.length) return;
    const una = filas.length === 1 ? filas[0] : null;
    const cuerpo = { action: 'actualizar', ids: filas.map((fila) => fila.id), descuenta_merma: activar };
    if (activar) {
      setConfirmacion({
        title: una ? `Activar el descuento de merma: ${una.nombre}` : `Activar el descuento de merma en ${filas.length} ingredientes`,
        message: (una
          ? `Al vender, cada ${numero(EJEMPLO_RECETA)} ${una.unidad} que diga la receta descontarán ${numero(EJEMPLO_RECETA * Number(una.factor))} ${una.unidad} `
            + `del inventario (envase de ${numero(una.contenido_envase)}, peso real de ${numero(una.peso_real)}). `
          : 'Al vender, cada ingrediente descontará del inventario la receta × envase ÷ peso real (el costo no cambia). ')
          + `${AVISO_RECETAS} El stock de ahora no se corrige solo: después conviene hacer un conteo en Ajuste de inventario.`,
        confirmLabel: 'Activar',
        cuerpo,
      });
    } else {
      setConfirmacion({
        title: una ? `Apagar el descuento de merma: ${una.nombre}` : `Apagar el descuento de merma en ${filas.length} ingredientes`,
        message: 'Al vender volverá a descontarse del inventario lo que diga la receta, sin la merma.',
        confirmLabel: 'Apagar',
        cuerpo,
      });
    }
  };

  const confirmar = async () => {
    if (!confirmacion) return;
    setSaving(true);
    try {
      const data = await pedir({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(confirmacion.cuerpo),
      });
      aplicar(data);
      setSeleccion(new Set());
      showSuccess(data.message || 'Listo.');
      setConfirmacion(null);
    } catch (error) {
      showError(error.message);
      setConfirmacion(null);
    } finally {
      setSaving(false);
    }
  };

  const marcados = ingredientes.filter((fila) => seleccion.has(fila.id));
  const columnas = isMobile ? '1fr' : '34px minmax(160px, 1.5fr) 120px 80px 150px 100px minmax(120px, 1fr) 120px';

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>← Volver a Costeo</button>

      <div>
        <h2 style={titleStyle(isMobile)}>Configuración de merma</h2>
        <p style={subtitleStyle}>
          Cuando llegan 100 kg de aguacate y solo se aprovechan 50, el inventario debería bajar los 100. Con el
          interruptor encendido, al vender se descuenta del inventario <strong>lo de la receta × envase ÷ peso real</strong>:
          500 g de aguacate en la receta, con envase de 1.000 g y peso real de 500 g, descuentan 1.000 g. El costo no
          cambia (ya cuenta la merma).
        </p>
        <p style={avisoStyle}>{AVISO_RECETAS}</p>
      </div>

      <Toast toast={toast} onClose={hideToast} />

      <div style={barraStyle(isMobile)}>
        <input
          value={busqueda}
          onChange={(event) => setBusqueda(event.target.value)}
          placeholder="Buscar ingrediente o categoría"
          style={inputStyle}
          aria-label="Buscar ingrediente"
        />
        <select value={filtro} onChange={(event) => setFiltro(event.target.value)} style={inputStyle} aria-label="Filtrar por estado">
          <option value="todos">Todos</option>
          <option value="activos">Con el descuento encendido</option>
          <option value="apagados">Sin activar</option>
        </select>
        <span style={contadorStyle}>
          {resumen.con_merma} con merma · {resumen.activos} {resumen.activos === 1 ? 'encendido' : 'encendidos'}
        </span>
      </div>

      {marcados.length > 0 ? (
        <div style={accionesStyle}>
          <span style={{ fontWeight: 700 }}>{marcados.length} seleccionado(s)</span>
          <button type="button" style={botonPrimarioStyle} disabled={saving} onClick={() => pedirCambio(marcados, true)}>
            Activar el descuento
          </button>
          <button type="button" style={botonSecundarioStyle} disabled={saving} onClick={() => pedirCambio(marcados, false)}>
            Apagar
          </button>
          <button type="button" style={botonSecundarioStyle} onClick={() => setSeleccion(new Set())}>Quitar selección</button>
        </div>
      ) : null}

      {loading ? (
        <div style={vacioStyle}>Cargando ingredientes...</div>
      ) : ingredientes.length === 0 ? (
        <div style={vacioStyle}>
          Ningún ingrediente tiene merma: para tenerla, el «peso real» del ingrediente debe ser menor que el «contenido del envase».
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          {!isMobile ? (
            <div style={{ ...filaStyle(columnas), ...cabeceraStyle }}>
              <input type="checkbox" checked={todosMarcados} onChange={alternarTodos} aria-label="Seleccionar todos los visibles" />
              <div>Ingrediente</div>
              <div>Envase → real</div>
              <div>Merma</div>
              <div title="Lo que se descuenta del inventario por cada 500 de receta">Receta → inventario</div>
              <div>Stock</div>
              <div>Recetas que lo usan</div>
              <div>Descuento</div>
            </div>
          ) : null}

          {visibles.length === 0 ? (
            <div style={vacioStyle}>Ningún ingrediente coincide con la búsqueda.</div>
          ) : visibles.map((fila) => (
            <div key={fila.id} style={bloqueStyle}>
              <div style={filaStyle(columnas)} data-testid={`merma-fila-${fila.id}`}>
                <input
                  type="checkbox"
                  checked={seleccion.has(fila.id)}
                  onChange={() => alternarSeleccion(fila.id)}
                  aria-label={`Seleccionar ${fila.nombre}`}
                />
                <div>
                  <div style={{ fontWeight: 700 }}>{fila.nombre}</div>
                  {fila.categoria ? <div style={notaStyle}>{fila.categoria}</div> : null}
                </div>
                <div>{isMobile ? 'Envase → real: ' : ''}{numero(fila.contenido_envase)} → {numero(fila.peso_real)} {fila.unidad}</div>
                <div>{isMobile ? 'Merma: ' : ''}{numero(fila.merma_pct, 1)}%</div>
                <div>{isMobile ? 'Receta → inventario: ' : ''}{ejemplo(fila)}</div>
                <div>{isMobile ? 'Stock: ' : ''}{numero(fila.stock_actual)} {fila.unidad}</div>
                <div>
                  {fila.usos_total > 0 ? (
                    <button type="button" style={enlaceStyle} onClick={() => alternarAbierto(fila.id)} aria-expanded={abiertos.has(fila.id)}>
                      {fila.usos_total} {fila.usos_total === 1 ? 'uso' : 'usos'} {abiertos.has(fila.id) ? '▴' : '▾'}
                    </button>
                  ) : <span style={notaStyle}>Sin recetas</span>}
                </div>
                <div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={fila.descuenta_merma}
                    aria-label={`Descuento de merma de ${fila.nombre}`}
                    disabled={saving}
                    onClick={() => pedirCambio([fila], !fila.descuenta_merma)}
                    style={interruptorStyle(fila.descuenta_merma)}
                  >
                    {fila.descuenta_merma ? 'Encendido' : 'Apagado'}
                  </button>
                  {fila.descuenta_merma && !fila.aplica ? (
                    <div style={{ ...notaStyle, color: '#ffb3b3' }}>Ya no tiene merma: no descuenta de más</div>
                  ) : null}
                </div>
              </div>
              {abiertos.has(fila.id) ? (
                <ul style={usosStyle}>
                  {fila.usos.map((uso, indice) => (
                    <li key={`${uso.tipo}-${uso.nombre}-${indice}`}>
                      {uso.nombre} <span style={notaStyle}>({uso.tipo}) · {numero(uso.cantidad, 3)} {fila.unidad}</span>
                    </li>
                  ))}
                  {fila.usos_total > fila.usos.length ? <li style={notaStyle}>y {fila.usos_total - fila.usos.length} más</li> : null}
                </ul>
              ) : null}
            </div>
          ))}
        </div>
      )}

      <ConfirmModal
        open={Boolean(confirmacion)}
        title={confirmacion?.title || ''}
        message={confirmacion?.message || ''}
        confirmLabel={confirmacion?.confirmLabel}
        busy={saving}
        onCancel={() => setConfirmacion(null)}
        onConfirm={confirmar}
      />
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 14, padding: isMobile ? 6 : 10 });
const titleStyle = (isMobile) => ({ margin: 0, color: 'var(--vg-text-strong)', fontSize: isMobile ? 26 : 32 });
const subtitleStyle = { margin: '8px 0 0', color: 'var(--vg-f-d2c3c3)', maxWidth: 780, lineHeight: 1.6 };
const avisoStyle = { margin: '8px 0 0', color: 'var(--vg-f-ffd9a0)', maxWidth: 780, lineHeight: 1.5, fontSize: 13.5 };
const barraStyle = (isMobile) => ({ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: isMobile ? 'stretch' : 'center', flexDirection: isMobile ? 'column' : 'row' });
const inputStyle = { borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-161010)', padding: '9px 12px', color: 'var(--vg-text-strong)', fontSize: 14, minWidth: 200 };
const contadorStyle = { color: 'var(--vg-f-c8bbbb)', fontSize: 13 };
const accionesStyle = { display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center', padding: '10px 14px', borderRadius: 14, background: 'rgba(var(--vg-accent-rgb), 0.08)', border: '1px solid rgba(var(--vg-accent-rgb), 0.25)' };
const vacioStyle = { minHeight: 80, display: 'grid', placeItems: 'center', textAlign: 'center', padding: 16, borderRadius: 14, border: '1px dashed rgba(var(--vg-ink), 0.12)', color: 'var(--vg-f-c8bbbb)' };
const filaStyle = (columnas) => ({ display: 'grid', gridTemplateColumns: columnas, gap: '8px 12px', alignItems: 'center', padding: '10px 6px', minWidth: 0 });
const cabeceraStyle = { color: 'var(--vg-f-aa9999)', fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.03em', borderBottom: '1px solid rgba(var(--vg-ink), 0.12)' };
const bloqueStyle = { borderBottom: '1px solid rgba(var(--vg-ink), 0.07)' };
const notaStyle = { fontSize: 12, color: 'var(--vg-f-a89999)' };
const enlaceStyle = { border: 'none', background: 'none', color: 'var(--vg-f-ff7d7d)', cursor: 'pointer', fontWeight: 700, padding: 0 };
const usosStyle = { margin: '0 0 10px 40px', padding: '0 0 0 16px', display: 'grid', gap: 3, color: 'var(--vg-f-d2c3c3)', fontSize: 13 };
const interruptorStyle = (encendido) => ({
  border: 'none', borderRadius: 999, padding: '7px 14px', fontWeight: 800, fontSize: 12.5, cursor: 'pointer',
  color: encendido ? '#04210f' : 'var(--vg-text-strong)',
  background: encendido ? '#5be08f' : 'rgba(var(--vg-ink), 0.12)',
});
const botonPrimarioStyle = { border: 'none', borderRadius: 999, padding: '8px 16px', background: 'linear-gradient(90deg, #d81d1d 0%, #ff5252 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const botonSecundarioStyle = { border: '1px solid rgba(var(--vg-ink), 0.18)', borderRadius: 999, padding: '8px 16px', background: 'rgba(var(--vg-ink), 0.05)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer' };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default AnalystMermaConfigPage;

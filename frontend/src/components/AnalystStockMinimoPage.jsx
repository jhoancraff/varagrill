import { useCallback, useEffect, useMemo, useState } from 'react';
import Toast from './Toast';
import useToast from '../hooks/useToast';
import { guardarSugeridos } from '../utils/comprasSugeridas';

const ESTADOS = {
  sin_stock: { label: 'Sin stock', color: '#ffb3b3', fondo: 'rgba(255, 92, 92, 0.2)' },
  bajo: { label: 'Bajo el mínimo', color: 'var(--vg-f-ffd9a0)', fondo: 'rgba(255, 176, 59, 0.18)' },
  en_minimo: { label: 'En el mínimo', color: 'var(--vg-f-c8bbbb)', fondo: 'rgba(var(--vg-ink), 0.1)' },
};
const PRIORIDAD = { sin_stock: 0, bajo: 1, en_minimo: 2 };

const numero = (valor) => Number(valor).toLocaleString('es-ES', { maximumFractionDigits: 2 });
const sinTildes = (texto) => String(texto || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

function textoAviso(aviso) {
  if (!aviso) return 'Todavía no hay avisos de Telegram registrados.';
  const cuando = aviso.es_de_hoy ? 'hoy' : `el ${aviso.fecha.split('-').reverse().join('/')}`;
  if (aviso.estado === 'enviado') {
    const hora = aviso.completado_en ? ` a las ${new Date(aviso.completado_en).toLocaleTimeString('es-VE', { hour: '2-digit', minute: '2-digit' })}` : '';
    return `Aviso de Telegram ${cuando}: enviado${hora} (${aviso.cantidad_ingredientes} ingredientes).`;
  }
  if (aviso.estado === 'sin_alertas') return `Aviso de Telegram ${cuando}: no había ingredientes en su mínimo.`;
  if (aviso.estado === 'fallido') return `Aviso de Telegram ${cuando}: falló (intento ${aviso.intentos}). Se reintenta cada hora. ${aviso.ultimo_error || ''}`.trim();
  return `Aviso de Telegram ${cuando}: pendiente, todavía no se ha enviado.`;
}

// Inventario → Stock mínimo. El mismo reporte que se manda cada día por Telegram (ingredientes con stock mínimo
// definido que están en ese mínimo o por debajo), para darle seguimiento y reponerlos cargando una compra.
function AnalystStockMinimoPage({ isMobile, onBack, onEdit, onCargarCompra }) {
  const [datos, setDatos] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busqueda, setBusqueda] = useState('');
  const [filtro, setFiltro] = useState('todos');
  const [orden, setOrden] = useState('nombre');
  const [seleccion, setSeleccion] = useState(() => new Set());
  const { toast, showError, hideToast } = useToast();

  const cargar = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/admin/stock-minimo/', { credentials: 'include', cache: 'no-store' });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo cargar el stock mínimo.');
      }
      setDatos(data);
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

  const ingredientes = datos?.ingredientes || [];

  const visibles = useMemo(() => {
    const texto = sinTildes(busqueda.trim());
    const filas = ingredientes.filter((fila) => (
      (filtro === 'todos' || fila.estado === filtro)
      && (!texto || sinTildes(fila.nombre).includes(texto) || sinTildes(fila.categoria).includes(texto))
    ));
    if (orden === 'urgentes') {
      // Primero los que ya no tienen, luego los más lejos de su mínimo (stock / mínimo), al final los justos.
      return [...filas].sort((a, b) => (
        PRIORIDAD[a.estado] - PRIORIDAD[b.estado]
        || (Number(a.stock_actual) / Number(a.stock_minimo)) - (Number(b.stock_actual) / Number(b.stock_minimo))
        || a.nombre.localeCompare(b.nombre, 'es')
      ));
    }
    return filas; // como llegan del servidor: por nombre, igual que el aviso de Telegram
  }, [ingredientes, busqueda, filtro, orden]);

  const alternar = (id) => setSeleccion((actual) => {
    const nuevo = new Set(actual);
    if (nuevo.has(id)) nuevo.delete(id); else nuevo.add(id);
    return nuevo;
  });
  const todosMarcados = visibles.length > 0 && visibles.every((fila) => seleccion.has(fila.id));
  const alternarTodos = () => setSeleccion((actual) => {
    const nuevo = new Set(actual);
    if (todosMarcados) visibles.forEach((fila) => nuevo.delete(fila.id));
    else visibles.forEach((fila) => nuevo.add(fila.id));
    return nuevo;
  });

  // Lleva a "Cargar por lote" con estos ingredientes como atajos (nombre, unidad y lo que falta para el mínimo).
  const cargarCompra = (filas) => {
    if (!filas.length) return;
    guardarSugeridos(filas.map((fila) => ({ id: fila.id, nombre: fila.nombre, unidad: fila.unidad, faltante: fila.faltante })));
    onCargarCompra();
  };

  const marcados = visibles.filter((fila) => seleccion.has(fila.id));
  const filasParaCompra = marcados.length > 0 ? marcados : visibles;
  const resumen = datos?.resumen || { total: 0, sin_stock: 0, bajo: 0, en_minimo: 0 };
  const columnas = isMobile ? '1fr' : '34px minmax(160px, 1.5fr) 110px 110px 110px 130px 110px';

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>← Volver a Inventario</button>

      <div>
        <h2 style={titleStyle(isMobile)}>Stock mínimo</h2>
        <p style={subtitleStyle}>
          Ingredientes con stock mínimo definido que están en ese mínimo o por debajo: el mismo reporte que se envía cada
          día por Telegram. Selecciona los que vas a comprar (o ninguno, para todos) y pulsa «Cargar compra» para sumarlos
          al inventario.
        </p>
      </div>

      <Toast toast={toast} onClose={hideToast} />

      {datos ? <div style={avisoStyle}>{textoAviso(datos.ultimo_aviso)}</div> : null}

      {datos ? (
        <div style={resumenStyle}>
          <span style={{ fontWeight: 800 }}>{resumen.total} {resumen.total === 1 ? 'ingrediente' : 'ingredientes'}</span>
          <span style={{ color: ESTADOS.sin_stock.color }}>{resumen.sin_stock} sin stock</span>
          <span style={{ color: ESTADOS.bajo.color }}>{resumen.bajo} bajo el mínimo</span>
          <span style={{ color: ESTADOS.en_minimo.color }}>{resumen.en_minimo} en el mínimo</span>
        </div>
      ) : null}

      {loading ? (
        <div style={vacioStyle}>Cargando stock mínimo...</div>
      ) : !datos ? null : ingredientes.length === 0 ? (
        <div style={vacioStyle}>
          Ningún ingrediente está en su mínimo. Para que un ingrediente aparezca aquí, define su stock mínimo al crearlo o al
          modificarlo.
        </div>
      ) : (
        <>
          <div style={barraStyle(isMobile)}>
            <input
              value={busqueda}
              onChange={(event) => setBusqueda(event.target.value)}
              placeholder="Buscar ingrediente o categoría"
              style={inputStyle}
              aria-label="Buscar ingrediente"
            />
            <select value={filtro} onChange={(event) => setFiltro(event.target.value)} style={inputStyle} aria-label="Filtrar por estado">
              <option value="todos">Todos los estados</option>
              <option value="sin_stock">Sin stock</option>
              <option value="bajo">Bajo el mínimo</option>
              <option value="en_minimo">En el mínimo</option>
            </select>
            <select value={orden} onChange={(event) => setOrden(event.target.value)} style={inputStyle} aria-label="Ordenar">
              <option value="nombre">Por nombre</option>
              <option value="urgentes">Más urgentes primero</option>
            </select>
            <button type="button" style={botonPrimarioStyle} disabled={filasParaCompra.length === 0} onClick={() => cargarCompra(filasParaCompra)}>
              {marcados.length > 0 ? `Cargar compra de ${marcados.length} seleccionado(s)` : `Cargar compra de todos (${visibles.length})`}
            </button>
          </div>

          <div style={{ overflowX: 'auto' }}>
            {!isMobile ? (
              <div style={{ ...filaStyle(columnas), ...cabeceraStyle }}>
                <input type="checkbox" checked={todosMarcados} onChange={alternarTodos} aria-label="Seleccionar todos los visibles" />
                <div>Ingrediente</div>
                <div>Stock actual</div>
                <div>Mínimo</div>
                <div title="Cuánto falta para llegar al mínimo">Falta</div>
                <div>Estado</div>
                <div>Acciones</div>
              </div>
            ) : null}

            {visibles.length === 0 ? (
              <div style={vacioStyle}>Ningún ingrediente coincide con el filtro.</div>
            ) : visibles.map((fila) => {
              const estado = ESTADOS[fila.estado] || ESTADOS.en_minimo;
              return (
                <div key={fila.id} style={{ ...filaStyle(columnas), borderBottom: '1px solid rgba(var(--vg-ink), 0.07)' }} data-testid={`stock-fila-${fila.id}`}>
                  <input type="checkbox" checked={seleccion.has(fila.id)} onChange={() => alternar(fila.id)} aria-label={`Seleccionar ${fila.nombre}`} />
                  <div>
                    <div style={{ fontWeight: 700 }}>{fila.nombre}</div>
                    {fila.categoria ? <div style={notaStyle}>{fila.categoria}</div> : null}
                  </div>
                  <div style={{ fontWeight: 700, color: Number(fila.stock_actual) <= 0 ? ESTADOS.sin_stock.color : undefined }}>
                    {isMobile ? 'Stock: ' : ''}{numero(fila.stock_actual)} {fila.unidad}
                  </div>
                  <div>{isMobile ? 'Mínimo: ' : ''}{numero(fila.stock_minimo)} {fila.unidad}</div>
                  <div>{isMobile ? 'Falta: ' : ''}{Number(fila.faltante) > 0 ? `${numero(fila.faltante)} ${fila.unidad}` : '—'}</div>
                  <div><span style={badgeStyle(estado)}>{estado.label}</span></div>
                  <div>
                    {onEdit ? (
                      <button type="button" style={botonPequenoSecundarioStyle} onClick={() => onEdit(fila.id)} aria-label={`Modificar ${fila.nombre}`}>
                        Modificar
                      </button>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 14, padding: isMobile ? 6 : 10 });
const titleStyle = (isMobile) => ({ margin: 0, color: 'var(--vg-text-strong)', fontSize: isMobile ? 26 : 32 });
const subtitleStyle = { margin: '8px 0 0', color: 'var(--vg-f-d2c3c3)', maxWidth: 780, lineHeight: 1.6 };
const avisoStyle = { padding: '10px 14px', borderRadius: 12, background: 'rgba(var(--vg-ink), 0.05)', border: '1px solid rgba(var(--vg-ink), 0.1)', color: 'var(--vg-f-d2c3c3)', fontSize: 13.5, lineHeight: 1.5 };
const resumenStyle = { display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'center', fontSize: 14 };
const barraStyle = (isMobile) => ({ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: isMobile ? 'stretch' : 'center', flexDirection: isMobile ? 'column' : 'row' });
const inputStyle = { borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-161010)', padding: '9px 12px', color: 'var(--vg-text-strong)', fontSize: 14, minWidth: 190 };
const vacioStyle = { minHeight: 80, display: 'grid', placeItems: 'center', textAlign: 'center', padding: 16, borderRadius: 14, border: '1px dashed rgba(var(--vg-ink), 0.12)', color: 'var(--vg-f-c8bbbb)' };
const filaStyle = (columnas) => ({ display: 'grid', gridTemplateColumns: columnas, gap: '8px 12px', alignItems: 'center', padding: '10px 6px', minWidth: 0 });
const cabeceraStyle = { color: 'var(--vg-f-aa9999)', fontSize: 12, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.03em', borderBottom: '1px solid rgba(var(--vg-ink), 0.12)' };
const notaStyle = { fontSize: 12, color: 'var(--vg-f-a89999)' };
const badgeStyle = (estado) => ({ display: 'inline-block', padding: '3px 10px', borderRadius: 999, fontSize: 11.5, fontWeight: 800, color: estado.color, background: estado.fondo });
const botonPrimarioStyle = { border: 'none', borderRadius: 999, padding: '10px 18px', background: 'linear-gradient(90deg, #d81d1d 0%, #ff5252 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const botonPequenoSecundarioStyle = { border: '1px solid rgba(var(--vg-ink), 0.14)', borderRadius: 999, padding: '6px 12px', background: 'rgba(var(--vg-ink), 0.04)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer', fontSize: 12 };
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };

export default AnalystStockMinimoPage;

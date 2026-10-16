import { useCallback, useEffect, useMemo, useState } from 'react';
import { RangoFechas } from './FiltroFechas';

function toIso(date) {
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60000);
  return local.toISOString().slice(0, 10);
}

function todayIso() {
  return toIso(new Date());
}

function formatCantidad(value) {
  const number = Number(value || 0);
  return number.toLocaleString('es-VE', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

function formatMonto(value) {
  const number = Number(value || 0);
  return number.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatFechaHora(isoString) {
  if (!isoString) return '';
  return new Date(isoString).toLocaleString('es-VE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

const TIPOS = [
  { value: '', label: 'Todos los movimientos' },
  { value: 'entrada', label: 'Solo entradas' },
  { value: 'salida', label: 'Solo salidas' },
  { value: 'ajuste', label: 'Solo ajustes' },
];

const TIPO_LABEL = { entrada: 'Entrada', salida: 'Salida', ajuste: 'Ajuste' };

const ESTADO_NOTA = {
  pagada: 'Pagada',
  abonada_parcial: 'Abonada parcial',
  pendiente_pago: 'Pendiente de pago',
  anulada: 'Anulada',
};

const TIPO_PEDIDO = { local: 'En mesa', llevar: 'Para llevar', delivery: 'Delivery' };

async function pedirJson(url) {
  const response = await fetch(url, { credentials: 'include', cache: 'no-store' });
  const json = await response.json().catch(() => ({}));
  if (!response.ok || !json.ok) {
    throw new Error(json.message || 'No se pudo cargar la información.');
  }
  return json;
}

// Reporte de movimiento de inventario: los ingredientes que tuvieron movimiento en el rango, cuánto
// entró, salió o se ajustó, y de dónde vino cada movimiento. Un movimiento de venta (o de reverso por
// anulación) trae un enlace que abre una ventana con los productos del pedido y la nota de entrega en
// que se vendió. No incluye los rollbacks. Se abre desde el botón "Ver movimiento de inventario" de
// AnalystInventoryHubPage (ruta 'admin-ingredients-movimientos' en WelcomeScreen).
function AnalystMovimientoInventarioPage({ isMobile, onBack }) {
  const [desde, setDesde] = useState(todayIso());
  const [hasta, setHasta] = useState(todayIso());
  const [tipo, setTipo] = useState('');
  const [busqueda, setBusqueda] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [abiertos, setAbiertos] = useState({});
  const [detalles, setDetalles] = useState({});
  const [origenAbierto, setOrigenAbierto] = useState(null);

  const cargar = useCallback(async () => {
    setLoading(true);
    setError('');
    setAbiertos({});
    setDetalles({});
    try {
      const params = new URLSearchParams({ desde, hasta });
      if (tipo) params.set('tipo', tipo);
      setData(await pedirJson(`/api/admin/reportes/movimiento-inventario/?${params.toString()}`));
    } catch (requestError) {
      setError(requestError.message || 'No se pudo cargar el movimiento de inventario.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [desde, hasta, tipo]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const cargarDetalle = async (ingredienteId) => {
    setDetalles((actual) => ({ ...actual, [ingredienteId]: { loading: true } }));
    try {
      const params = new URLSearchParams({ desde, hasta });
      if (tipo) params.set('tipo', tipo);
      const json = await pedirJson(`/api/admin/reportes/movimiento-inventario/ingrediente/${ingredienteId}/?${params.toString()}`);
      setDetalles((actual) => ({ ...actual, [ingredienteId]: { loading: false, ...json } }));
    } catch (requestError) {
      setDetalles((actual) => ({ ...actual, [ingredienteId]: { loading: false, error: requestError.message } }));
    }
  };

  const alternar = (ingredienteId) => {
    const abierto = Boolean(abiertos[ingredienteId]);
    setAbiertos((actual) => ({ ...actual, [ingredienteId]: !abierto }));
    if (!abierto && !detalles[ingredienteId]) {
      cargarDetalle(ingredienteId);
    }
  };

  const termino = busqueda.trim().toLowerCase();
  const ingredientes = useMemo(() => {
    const lista = data?.ingredientes || [];
    return termino ? lista.filter((item) => item.nombre.toLowerCase().includes(termino)) : lista;
  }, [data, termino]);

  const totalMovimientos = ingredientes.reduce((suma, item) => suma + item.movimientos, 0);

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>
        ← Volver a Inventario
      </button>

      <div>
        <h2 style={titleStyle(isMobile)}>Movimiento de inventario</h2>
        <p style={subtitleStyle}>
          Ingredientes que tuvieron movimiento en el período. No incluye los rollbacks de inventario.
        </p>
      </div>

      <RangoFechas
        desde={desde}
        hasta={hasta}
        onChange={(rango) => {
          setDesde(rango.desde);
          setHasta(rango.hasta);
        }}
      />

      <div style={filtrosStyle(isMobile)}>
        <input
          type="text"
          value={busqueda}
          onChange={(event) => setBusqueda(event.target.value)}
          placeholder="Buscar ingrediente..."
          style={inputStyle}
          aria-label="Buscar ingrediente"
        />
        <select value={tipo} onChange={(event) => setTipo(event.target.value)} style={inputStyle} aria-label="Tipo de movimiento">
          {TIPOS.map((opcion) => (
            <option key={opcion.value} value={opcion.value}>{opcion.label}</option>
          ))}
        </select>
      </div>

      {loading ? <div style={emptyStyle}>Cargando movimientos...</div> : null}
      {!loading && error ? <div style={noticeStyle}>{error}</div> : null}

      {!loading && !error && data ? (
        <>
          <div style={resumenStyle}>
            <strong>{ingredientes.length}</strong> {ingredientes.length === 1 ? 'ingrediente' : 'ingredientes'} con movimiento
            {' · '}
            <strong>{totalMovimientos}</strong> {totalMovimientos === 1 ? 'movimiento' : 'movimientos'}
          </div>

          {ingredientes.length === 0 ? (
            <div style={emptyStyle}>No hay movimientos de inventario para este período.</div>
          ) : (
            <div style={{ display: 'grid', gap: 10 }}>
              {ingredientes.map((item) => {
                const abierto = Boolean(abiertos[item.ingrediente_id]);
                const detalle = detalles[item.ingrediente_id];
                const neto = Number(item.neto);
                return (
                  <article key={item.ingrediente_id} style={cardStyle}>
                    <div style={cardHeaderStyle(isMobile)}>
                      <div style={{ minWidth: 0 }}>
                        <div style={nombreStyle}>{item.nombre}</div>
                        <div style={mutedStyle}>
                          Stock actual: {formatCantidad(item.stock_actual)} {item.unidad}
                        </div>
                      </div>
                      <div style={cifrasStyle(isMobile)}>
                        <Cifra etiqueta="Entradas" valor={Number(item.entradas) > 0 ? `+${formatCantidad(item.entradas)}` : '0'} color="var(--vg-f-8fffb0)" />
                        <Cifra etiqueta="Salidas" valor={Number(item.salidas) > 0 ? `−${formatCantidad(item.salidas)}` : '0'} color="var(--vg-f-ff9d9d)" />
                        <Cifra etiqueta="Ajustes" valor={formatCantidad(item.ajustes)} />
                        <Cifra
                          etiqueta="Neto"
                          valor={`${neto > 0 ? '+' : ''}${formatCantidad(item.neto)} ${item.unidad}`}
                          color={neto < 0 ? 'var(--vg-f-ff9d9d)' : 'var(--vg-f-8fffb0)'}
                          fuerte
                        />
                      </div>
                      <button
                        type="button"
                        onClick={() => alternar(item.ingrediente_id)}
                        style={toggleButtonStyle}
                        aria-expanded={abierto}
                      >
                        {abierto ? 'Ocultar' : `Ver movimientos (${item.movimientos})`}
                      </button>
                    </div>

                    {abierto ? (
                      <div style={detalleWrapStyle}>
                        {!detalle || detalle.loading ? <div style={mutedStyle}>Cargando movimientos...</div> : null}
                        {detalle && detalle.error ? <div style={noticeStyle}>{detalle.error}</div> : null}
                        {detalle && !detalle.loading && !detalle.error ? (
                          <>
                            {detalle.truncado ? (
                              <div style={avisoStyle}>
                                Se muestran los {detalle.limite} movimientos más recientes de {detalle.total}. Acota las fechas para ver el resto.
                              </div>
                            ) : null}
                            <div style={tablaScrollStyle}>
                              <table style={tablaStyle}>
                                <thead>
                                  <tr>
                                    <th style={thStyle}>Fecha y hora</th>
                                    <th style={thStyle}>Tipo</th>
                                    <th style={{ ...thStyle, textAlign: 'right' }}>Cantidad</th>
                                    <th style={thStyle}>Motivo</th>
                                    <th style={thStyle}>Usuario</th>
                                    <th style={thStyle}>Origen</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {detalle.movimientos.map((mov) => (
                                    <tr key={mov.id}>
                                      <td style={tdStyle}>{formatFechaHora(mov.fecha_hora)}</td>
                                      <td style={tdStyle}><span style={tipoBadgeStyle(mov.tipo)}>{TIPO_LABEL[mov.tipo] || mov.tipo}</span></td>
                                      <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, whiteSpace: 'nowrap' }}>
                                        {mov.tipo === 'entrada' ? '+' : mov.tipo === 'salida' ? '−' : ''}{formatCantidad(mov.cantidad)} {item.unidad}
                                      </td>
                                      <td style={{ ...tdStyle, minWidth: 180 }}>{mov.motivo || '—'}</td>
                                      <td style={tdStyle}>{mov.usuario || '—'}</td>
                                      <td style={tdStyle}>
                                        <OrigenCelda
                                          origen={mov.origen}
                                          onAbrir={() => setOrigenAbierto({ origen: mov.origen, ingrediente: item, movimiento: mov })}
                                        />
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </>
                        ) : null}
                      </div>
                    ) : null}
                  </article>
                );
              })}
            </div>
          )}
        </>
      ) : null}

      {origenAbierto ? <OrigenModal {...origenAbierto} onClose={() => setOrigenAbierto(null)} /> : null}
    </section>
  );
}

function Cifra({ etiqueta, valor, color, fuerte = false }) {
  return (
    <div style={{ display: 'grid', gap: 2, textAlign: 'right' }}>
      <span style={{ fontSize: 11, color: 'var(--vg-f-c8bbbb)' }}>{etiqueta}</span>
      <span style={{ fontSize: fuerte ? 15 : 13.5, fontWeight: fuerte ? 800 : 700, color: color || 'var(--vg-text-strong)', whiteSpace: 'nowrap' }}>
        {valor}
      </span>
    </div>
  );
}

// El origen de un movimiento: si viene de un pedido o de una nota de entrega es un enlace que abre el
// detalle; compras y ajustes se muestran como texto.
function OrigenCelda({ origen, onAbrir }) {
  if (!origen) return <span style={mutedStyle}>—</span>;
  if (origen.tipo === 'pedido' || origen.tipo === 'nota_entrega' || origen.tipo === 'comida_empleados') {
    return (
      <button
        type="button"
        onClick={onAbrir}
        style={linkButtonStyle}
        title={origen.tipo === 'comida_empleados' ? 'Ver la comida de empleados y sus ingredientes' : 'Ver los productos y la nota de entrega'}
      >
        {origen.etiqueta}
      </button>
    );
  }
  return <span>{origen.etiqueta}</span>;
}

function OrigenModal({ origen, ingrediente, movimiento, onClose }) {
  const [estado, setEstado] = useState({ loading: true, error: '', pedidos: [], nota: null, comida: null });

  useEffect(() => {
    let cancelado = false;
    if (origen.tipo === 'comida_empleados') {
      pedirJson(`/api/admin/comida-empleados/${origen.id}/`)
        .then((json) => {
          if (!cancelado) setEstado({ loading: false, error: '', pedidos: [], nota: null, comida: json.comida });
        })
        .catch((requestError) => {
          if (!cancelado) setEstado({ loading: false, error: requestError.message, pedidos: [], nota: null, comida: null });
        });
      return () => {
        cancelado = true;
      };
    }
    const url = origen.tipo === 'pedido'
      ? `/api/admin/reportes/movimiento-inventario/pedido/${origen.id}/`
      : `/api/admin/reportes/movimiento-inventario/nota-entrega/${origen.id}/`;
    pedirJson(url)
      .then((json) => {
        if (cancelado) return;
        setEstado(origen.tipo === 'pedido'
          ? { loading: false, error: '', pedidos: [json.pedido], nota: null }
          : { loading: false, error: '', pedidos: json.pedidos, nota: json.nota });
      })
      .catch((requestError) => {
        if (!cancelado) setEstado({ loading: false, error: requestError.message, pedidos: [], nota: null });
      });
    return () => {
      cancelado = true;
    };
  }, [origen.tipo, origen.id]);

  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const titulo = origen.tipo === 'pedido'
    ? `Pedido #${origen.id}`
    : origen.tipo === 'comida_empleados'
      ? `Comida de empleados #${origen.id}`
      : `Nota de entrega ${String(origen.id).padStart(8, '0')}`;

  return (
    <div style={backdropStyle} onClick={onClose} role="presentation">
      <div
        style={modalStyle}
        role="dialog"
        aria-modal="true"
        aria-label={titulo}
        onClick={(event) => event.stopPropagation()}
      >
        <button type="button" onClick={onClose} style={closeButtonStyle} aria-label="Cerrar">×</button>
        <h3 style={modalTitleStyle}>{titulo}</h3>
        <p style={{ ...mutedStyle, margin: 0 }}>
          Movimiento de {ingrediente.nombre}: {TIPO_LABEL[movimiento.tipo]?.toLowerCase()} de {formatCantidad(movimiento.cantidad)} {ingrediente.unidad}
          {' · '}{formatFechaHora(movimiento.fecha_hora)}
        </p>

        {estado.loading ? <div style={mutedStyle}>Cargando...</div> : null}
        {estado.error ? <div style={noticeStyle}>{estado.error}</div> : null}

        {estado.comida ? (
          <div style={bloqueStyle}>
            <div style={bloqueTituloStyle}>
              {estado.comida.nombre}
              {estado.comida.estado === 'anulada' ? <span style={estadoBadgeStyle('anulada')}> Anulada</span> : null}
            </div>
            <div style={mutedStyle}>
              {estado.comida.tipo_origen_label} · {formatCantidad(estado.comida.cantidad)} {estado.comida.unidad}
              {' · '}{estado.comida.fecha.split('-').reverse().join('/')}
              {estado.comida.turno_label ? ` · ${estado.comida.turno_label}` : ''}
            </div>
            <div style={mutedStyle}>Registrada por {estado.comida.registrada_por || '—'} · costo ${formatMonto(estado.comida.costo_total)}</div>
            {estado.comida.nota ? <div style={mutedStyle}>Nota: {estado.comida.nota}</div> : null}
            {estado.comida.estado === 'anulada' ? (
              <div style={mutedStyle}>Anulada por {estado.comida.anulada_por || '—'}: {estado.comida.motivo_anulacion}</div>
            ) : null}
            <div style={subtituloStyle}>Ingredientes que descontó</div>
            <ul style={listaStyle}>
              {(estado.comida.lineas || []).map((linea) => (
                <li key={linea.ingrediente_id} style={productoFilaStyle}>
                  <span>{linea.nombre}</span>
                  <span style={{ fontWeight: 700, whiteSpace: 'nowrap' }}>{formatCantidad(linea.cantidad)} {linea.unidad}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {estado.nota ? (
          <div style={bloqueStyle}>
            <div style={bloqueTituloStyle}>Nota de entrega</div>
            <NotaResumen nota={estado.nota} />
          </div>
        ) : null}

        {estado.pedidos.map((pedido) => (
          <div key={pedido.id} style={bloqueStyle}>
            <div style={bloqueTituloStyle}>
              Pedido #{pedido.id}
              <span style={mutedStyle}>
                {' · '}{TIPO_PEDIDO[pedido.tipo_pedido] || pedido.tipo_pedido}
                {pedido.mesa ? ` · Mesa ${pedido.mesa}` : ''}
                {pedido.cliente ? ` · ${pedido.cliente}` : ''}
                {pedido.mesero ? ` · ${pedido.mesero}` : ''}
              </span>
            </div>
            <div style={{ ...mutedStyle, marginBottom: 6 }}>{formatFechaHora(pedido.fecha_hora)}</div>

            <div style={subtituloStyle}>Productos del pedido</div>
            {pedido.productos.length === 0 ? (
              <div style={mutedStyle}>Este pedido no tiene productos registrados.</div>
            ) : (
              <ul style={listaStyle}>
                {pedido.productos.map((producto, indice) => (
                  <li key={`${producto.producto}-${indice}`} style={productoFilaStyle}>
                    <span>
                      {producto.cantidad} × {producto.producto}
                      {producto.peso_gramos ? ` (${formatCantidad(producto.peso_gramos)} g)` : ''}
                      {producto.notas ? <span style={mutedStyle}> — {producto.notas}</span> : null}
                    </span>
                    <span style={{ fontWeight: 700, whiteSpace: 'nowrap' }}>${formatMonto(producto.subtotal)}</span>
                  </li>
                ))}
                <li style={{ ...productoFilaStyle, fontWeight: 800, borderTop: '1px solid rgba(var(--vg-ink), 0.12)' }}>
                  <span>Total del pedido</span>
                  <span>${formatMonto(pedido.total)}</span>
                </li>
              </ul>
            )}

            <div style={subtituloStyle}>Nota de entrega</div>
            {pedido.notas_entrega.length === 0 && pedido.facturas.length === 0 ? (
              <div style={mutedStyle}>Este pedido no tiene nota de entrega ni factura.</div>
            ) : null}
            {pedido.notas_entrega.map((nota) => <NotaResumen key={nota.id} nota={nota} />)}
            {pedido.facturas.map((factura) => (
              <div key={factura.id} style={notaStyle}>
                <strong>Factura {factura.codigo}</strong>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function NotaResumen({ nota }) {
  return (
    <div style={notaStyle}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
        <strong>Nota de entrega {nota.codigo}</strong>
        <span style={estadoBadgeStyle(nota.estado)}>{ESTADO_NOTA[nota.estado] || nota.estado}</span>
      </div>
      <div style={mutedStyle}>
        {formatFechaHora(nota.fecha_emision)}
        {nota.metodo_pago ? ` · ${nota.metodo_pago}` : ''}
        {' · '}${formatMonto(nota.total)}
      </div>
      {nota.pedidos && nota.pedidos.length > 1 ? (
        <div style={mutedStyle}>
          Esta nota cubre {nota.pedidos.length} pedidos ({nota.pedidos.map((id) => `#${id}`).join(', ')}); su total es el de todos.
        </div>
      ) : null}
      {nota.estado === 'anulada' && nota.motivo_anulacion ? (
        <div style={mutedStyle}>Motivo de anulación: {nota.motivo_anulacion}</div>
      ) : null}
    </div>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 14, padding: isMobile ? 6 : 10 });
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const titleStyle = (isMobile) => ({ margin: 0, color: 'var(--vg-text-strong)', fontSize: isMobile ? 26 : 32 });
const subtitleStyle = { margin: '6px 0 0', color: 'var(--vg-f-d2c3c3)', lineHeight: 1.5, fontSize: 14 };
const mutedStyle = { color: 'var(--vg-f-c8bbbb)', fontSize: 12.5 };
const emptyStyle = { minHeight: 90, display: 'grid', placeItems: 'center', borderRadius: 16, border: '1px dashed rgba(var(--vg-ink), 0.14)', color: 'var(--vg-f-c8bbbb)', textAlign: 'center', padding: 16 };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid var(--vg-f-ff9191-a220)', background: 'rgba(255, 98, 98, 0.12)', color: 'var(--vg-f-ffd8d8)' };
const avisoStyle = { padding: '8px 12px', borderRadius: 10, border: '1px solid var(--vg-f-ffcf7d-a450)', background: 'rgba(255, 207, 125, 0.08)', color: 'var(--vg-f-ffe3a3)', fontSize: 13, marginBottom: 8 };
const filtrosStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'minmax(0, 1fr) 260px', gap: 10 });
const inputStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.16)', background: 'var(--vg-s-161010)', padding: '10px 12px', color: 'var(--vg-text-strong)', fontSize: 14 };
const resumenStyle = { color: 'var(--vg-f-d2c3c3)', fontSize: 14 };
const cardStyle = { borderRadius: 16, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)', padding: 14 };
const cardHeaderStyle = (isMobile) => ({ display: 'flex', flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'stretch' : 'center', justifyContent: 'space-between', gap: 12 });
const nombreStyle = { color: 'var(--vg-text-strong)', fontWeight: 700, fontSize: 16 };
const cifrasStyle = (isMobile) => ({ display: 'flex', gap: isMobile ? 14 : 22, flexWrap: 'wrap', justifyContent: isMobile ? 'flex-start' : 'flex-end', marginLeft: isMobile ? 0 : 'auto' });
const toggleButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.16)', borderRadius: 999, padding: '8px 14px', background: 'rgba(var(--vg-ink), 0.05)', color: 'var(--vg-text-strong)', fontWeight: 700, fontSize: 12.5, cursor: 'pointer', whiteSpace: 'nowrap' };
const detalleWrapStyle = { marginTop: 12, paddingTop: 12, borderTop: '1px solid rgba(var(--vg-ink), 0.08)' };
const tablaScrollStyle = { overflowX: 'auto', maxHeight: 460, overflowY: 'auto' };
const tablaStyle = { width: '100%', borderCollapse: 'collapse', fontSize: 13 };
const thStyle = { textAlign: 'left', padding: '8px 10px', color: 'var(--vg-f-c8bbbb)', fontSize: 11.5, fontWeight: 700, borderBottom: '1px solid rgba(var(--vg-ink), 0.12)', position: 'sticky', top: 0, background: 'var(--vg-s-0a0808-a990)' };
const tdStyle = { padding: '8px 10px', borderBottom: '1px solid rgba(var(--vg-ink), 0.06)', color: 'var(--vg-text-strong)', verticalAlign: 'top' };
const linkButtonStyle = { border: 'none', background: 'transparent', padding: 0, color: 'var(--vg-f-bfe0ff)', fontWeight: 700, fontSize: 13, textDecoration: 'underline', cursor: 'pointer', textAlign: 'left' };

const tipoBadgeStyle = (tipo) => ({
  display: 'inline-block', padding: '2px 8px', borderRadius: 999, fontSize: 11, fontWeight: 800,
  color: tipo === 'entrada' ? 'var(--vg-f-8fffb0)' : tipo === 'salida' ? 'var(--vg-f-ff9d9d)' : 'var(--vg-f-ffcf7d)',
  background: tipo === 'entrada' ? 'rgba(70, 200, 120, 0.14)' : tipo === 'salida' ? 'rgba(255, 98, 98, 0.14)' : 'rgba(255, 190, 120, 0.14)',
});

const estadoBadgeStyle = (estado) => ({
  display: 'inline-block', padding: '2px 10px', borderRadius: 999, fontSize: 11, fontWeight: 800,
  color: estado === 'anulada' ? 'var(--vg-f-ffb3b3)' : estado === 'pagada' ? 'var(--vg-f-8fffb0)' : 'var(--vg-f-ffcf7d)',
  background: estado === 'anulada' ? 'rgba(255, 98, 98, 0.14)' : estado === 'pagada' ? 'rgba(70, 200, 120, 0.14)' : 'rgba(255, 190, 120, 0.14)',
});

const backdropStyle = { position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0, 0, 0, 0.6)', display: 'grid', placeItems: 'center', padding: 16 };
const modalStyle = { position: 'relative', width: '100%', maxWidth: 560, maxHeight: '88vh', overflowY: 'auto', borderRadius: 20, border: '1px solid var(--vg-f-ff9191-a300)', background: 'linear-gradient(180deg, var(--vg-s-1c0c0c-a980) 0%, var(--vg-s-0a0808-a990) 100%)', padding: '22px 22px 20px', boxShadow: '0 20px 50px rgba(0, 0, 0, calc(0.45 * var(--vg-shadow-k)))', display: 'grid', gap: 12 };
const closeButtonStyle = { position: 'absolute', top: 10, right: 10, width: 32, height: 32, borderRadius: '50%', border: 'none', background: 'rgba(var(--vg-ink), 0.1)', color: 'var(--vg-text-strong)', fontSize: 20, lineHeight: 1, cursor: 'pointer', display: 'grid', placeItems: 'center' };
const modalTitleStyle = { margin: 0, color: 'var(--vg-text-strong)', fontSize: 20, fontWeight: 800, paddingRight: 34 };
const bloqueStyle = { borderRadius: 14, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'rgba(var(--vg-ink), 0.03)', padding: '12px 14px', display: 'grid', gap: 4 };
const bloqueTituloStyle = { color: 'var(--vg-text-strong)', fontWeight: 800, fontSize: 14.5 };
const subtituloStyle = { marginTop: 8, color: 'var(--vg-f-ffb0b0)', fontSize: 11.5, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.06em' };
const listaStyle = { listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 2 };
const productoFilaStyle = { display: 'flex', justifyContent: 'space-between', gap: 12, padding: '5px 0', color: 'var(--vg-text-strong)', fontSize: 13.5 };
const notaStyle = { borderRadius: 10, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'rgba(var(--vg-ink), 0.04)', padding: '8px 10px', display: 'grid', gap: 2, color: 'var(--vg-text-strong)', fontSize: 13.5 };

export default AnalystMovimientoInventarioPage;

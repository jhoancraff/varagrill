import { useCallback, useEffect, useMemo, useState } from 'react';
import ConfirmModal from './ConfirmModal';
import { RangoFechas } from './FiltroFechas';
import Toast from './Toast';
import useToast from '../hooks/useToast';

function toIso(date) {
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60000).toISOString().slice(0, 10);
}

function todayIso() {
  return toIso(new Date());
}

function startOfMonthIso() {
  const hoy = new Date();
  return toIso(new Date(hoy.getFullYear(), hoy.getMonth(), 1));
}

function formatCantidad(value) {
  return Number(value || 0).toLocaleString('es-VE', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

function formatMonto(value) {
  return Number(value || 0).toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatFecha(iso) {
  if (!iso) return '';
  const [anio, mes, dia] = iso.split('-');
  return `${dia}/${mes}/${anio}`;
}

function formatFechaHora(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString('es-VE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function getCookie(name) {
  const match = document.cookie.split('; ').find((row) => row.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split('=')[1]) : '';
}

async function api(url, { method = 'GET', body } = {}) {
  const response = await fetch(url, {
    method,
    credentials: 'include',
    cache: 'no-store',
    headers: method === 'GET' ? undefined : { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') || '' },
    body: body ? JSON.stringify(body) : undefined,
  });
  const json = await response.json().catch(() => ({}));
  return { ok: response.ok && json.ok, status: response.status, json };
}

const TIPO_LABEL = { receta: 'Receta', subreceta: 'Subreceta', ingrediente: 'Ingrediente' };
const TIPO_ARTICULO = { receta: 'la receta', subreceta: 'la subreceta', ingrediente: 'el ingrediente' };

// Comida de empleados: se elige una receta (marcada "para empleados"), una subreceta o un ingrediente, se ve
// qué ingredientes se descontarán del inventario y, tras confirmar, se descuentan. No se vende ni se factura.
// Solo administradores y contadores (ver comida_empleados_views.py).
function ComidaEmpleadosPage({ isMobile, onBack }) {
  const { toast, showSuccess, showError, hideToast } = useToast();
  const [opciones, setOpciones] = useState(null);
  const [errorOpciones, setErrorOpciones] = useState('');

  // formulario
  const [busqueda, setBusqueda] = useState('');
  const [seleccion, setSeleccion] = useState('');
  const [cantidad, setCantidad] = useState('');
  const [fecha, setFecha] = useState(todayIso());
  const [turno, setTurno] = useState('');
  const [nota, setNota] = useState('');
  const [vistaPrevia, setVistaPrevia] = useState(null);
  const [cargandoVista, setCargandoVista] = useState(false);
  const [errorVista, setErrorVista] = useState('');
  const [confirmando, setConfirmando] = useState(false);
  const [guardando, setGuardando] = useState(false);

  // historial
  const [desde, setDesde] = useState(startOfMonthIso());
  const [hasta, setHasta] = useState(todayIso());
  const [historial, setHistorial] = useState(null);
  const [cargandoHistorial, setCargandoHistorial] = useState(true);
  const [abiertas, setAbiertas] = useState({});
  const [lineas, setLineas] = useState({});
  const [anulando, setAnulando] = useState(null);
  const [motivoAnulacion, setMotivoAnulacion] = useState('');
  const [anulandoBusy, setAnulandoBusy] = useState(false);

  const [tipo, origenId] = seleccion ? seleccion.split(':') : ['', ''];

  useEffect(() => {
    let cancelado = false;
    api('/api/admin/comida-empleados/opciones/').then(({ ok, json }) => {
      if (cancelado) return;
      if (ok) setOpciones(json);
      else setErrorOpciones(json.message || 'No se pudieron cargar las opciones.');
    }).catch(() => {
      if (!cancelado) setErrorOpciones('No se pudieron cargar las opciones.');
    });
    return () => {
      cancelado = true;
    };
  }, []);

  const cargarHistorial = useCallback(async () => {
    setCargandoHistorial(true);
    try {
      const { ok, json } = await api(`/api/admin/comida-empleados/?desde=${desde}&hasta=${hasta}`);
      if (ok) {
        setHistorial(json);
        setAbiertas({});
        setLineas({});
      } else {
        showError(json.message || 'No se pudo cargar el historial.');
      }
    } catch (requestError) {
      showError('No se pudo cargar el historial.');
    } finally {
      setCargandoHistorial(false);
    }
  }, [desde, hasta, showError]);

  useEffect(() => {
    cargarHistorial();
  }, [cargarHistorial]);

  // lo elegido, con su nombre y su unidad
  const elegido = useMemo(() => {
    if (!opciones || !tipo) return null;
    const lista = tipo === 'receta' ? opciones.recetas : tipo === 'subreceta' ? opciones.subrecetas : opciones.ingredientes;
    const item = lista.find((entrada) => String(entrada.id) === origenId);
    if (!item) return null;
    return {
      nombre: item.nombre,
      unidad: tipo === 'receta' ? 'porciones' : (item.rendimiento_unidad || item.unidad_medida || ''),
    };
  }, [opciones, tipo, origenId]);

  const termino = busqueda.trim().toLowerCase();
  const filtrar = (lista) => (termino ? lista.filter((item) => item.nombre.toLowerCase().includes(termino)) : lista);

  // Vista previa: cada vez que cambia lo elegido, la cantidad, la fecha o el turno (con una pausa al teclear).
  useEffect(() => {
    setVistaPrevia(null);
    setErrorVista('');
    const cantidadNumero = Number(cantidad);
    if (!tipo || !origenId || !(cantidadNumero > 0)) return undefined;
    let cancelado = false;
    const temporizador = setTimeout(async () => {
      setCargandoVista(true);
      try {
        const { ok, json } = await api('/api/admin/comida-empleados/previsualizar/', {
          method: 'POST', body: { tipo, origen_id: Number(origenId), cantidad, fecha, turno },
        });
        if (cancelado) return;
        if (ok) setVistaPrevia(json);
        else setErrorVista(json.message || 'No se pudo calcular la vista previa.');
      } catch (requestError) {
        if (!cancelado) setErrorVista('No se pudo calcular la vista previa.');
      } finally {
        if (!cancelado) setCargandoVista(false);
      }
    }, 350);
    return () => {
      cancelado = true;
      clearTimeout(temporizador);
    };
  }, [tipo, origenId, cantidad, fecha, turno]);

  const registrar = async () => {
    setGuardando(true);
    try {
      const { ok, json } = await api('/api/admin/comida-empleados/', {
        method: 'POST',
        body: {
          tipo,
          origen_id: Number(origenId),
          cantidad,
          fecha,
          turno,
          nota,
          // La cajera ya vio y aceptó el aviso de stock en la confirmación.
          confirmar_stock_insuficiente: Boolean(vistaPrevia && vistaPrevia.sin_stock.length > 0),
        },
      });
      if (!ok) {
        showError(json.message || 'No se pudo registrar la comida.');
        return;
      }
      showSuccess(json.message || 'Comida registrada.');
      setConfirmando(false);
      setSeleccion('');
      setCantidad('');
      setNota('');
      setTurno('');
      setBusqueda('');
      cargarHistorial();
    } catch (requestError) {
      showError('Error de red al registrar la comida.');
    } finally {
      setGuardando(false);
    }
  };

  const alternarLineas = async (comida) => {
    const abierta = Boolean(abiertas[comida.id]);
    setAbiertas((actual) => ({ ...actual, [comida.id]: !abierta }));
    if (!abierta && !lineas[comida.id]) {
      const { ok, json } = await api(`/api/admin/comida-empleados/${comida.id}/`);
      setLineas((actual) => ({ ...actual, [comida.id]: ok ? json.comida.lineas : [] }));
    }
  };

  const anular = async () => {
    setAnulandoBusy(true);
    try {
      const { ok, json } = await api(`/api/admin/comida-empleados/${anulando.id}/anular/`, {
        method: 'POST', body: { motivo: motivoAnulacion },
      });
      if (!ok) {
        showError(json.message || 'No se pudo anular la comida.');
        return;
      }
      showSuccess(json.message || 'Comida anulada.');
      setAnulando(null);
      setMotivoAnulacion('');
      cargarHistorial();
    } catch (requestError) {
      showError('Error de red al anular la comida.');
    } finally {
      setAnulandoBusy(false);
    }
  };

  const puedeRegistrar = Boolean(vistaPrevia) && !cargandoVista && !errorVista && fecha;
  const sinStock = vistaPrevia ? vistaPrevia.sin_stock : [];
  const yaRegistradas = vistaPrevia ? vistaPrevia.ya_registradas : [];
  const hoyIso = todayIso();

  const mensajeConfirmacion = elegido && vistaPrevia ? (
    <>
      ¿Estás seguro de usar {TIPO_ARTICULO[tipo]} <strong>«{elegido.nombre}»</strong> para la comida del día
      ({formatCantidad(cantidad)} {elegido.unidad}{fecha !== hoyIso ? `, del ${formatFecha(fecha)}` : ''})?
      {' '}Se descontarán {vistaPrevia.lineas.length} ingredientes del inventario por un costo de ${formatMonto(vistaPrevia.costo_total)}.
      {sinStock.length > 0 ? (
        <>
          <br /><br />
          <strong style={{ color: 'var(--vg-f-ffcf7d)' }}>Atención:</strong> no alcanza el stock de {sinStock.join(', ')}; quedará en negativo.
        </>
      ) : null}
      {yaRegistradas.length > 0 ? (
        <>
          <br /><br />
          Ya hay {yaRegistradas.length} {yaRegistradas.length === 1 ? 'comida registrada' : 'comidas registradas'} {turno ? 'en ese turno' : 'ese día'}.
        </>
      ) : null}
    </>
  ) : '';

  return (
    <section style={containerStyle(isMobile)}>
      <Toast toast={toast} onClose={hideToast} />

      <div style={headerRowStyle}>
        <div>
          <h2 style={titleStyle(isMobile)}>Comida de empleados</h2>
          <p style={subtitleStyle}>
            Descuenta del inventario lo que se usa para cocinar al personal. No se vende ni se factura.
          </p>
        </div>
        <button type="button" onClick={onBack} style={secondaryButtonStyle}>Volver</button>
      </div>

      {errorOpciones ? <div style={noticeStyle}>{errorOpciones}</div> : null}

      <section style={panelStyle}>
        <div style={panelTitleStyle}>Registrar comida</div>
        {!opciones && !errorOpciones ? <div style={mutedStyle}>Cargando opciones...</div> : null}
        {opciones ? (
          <div style={{ display: 'grid', gap: 12 }}>
            <div style={formGridStyle(isMobile)}>
              <label style={campoStyle}>
                <span style={etiquetaStyle}>Qué se usa</span>
                <input
                  type="text"
                  value={busqueda}
                  onChange={(event) => setBusqueda(event.target.value)}
                  placeholder="Buscar receta, subreceta o ingrediente..."
                  style={{ ...inputStyle, marginBottom: 6 }}
                  aria-label="Buscar receta, subreceta o ingrediente"
                />
                <select value={seleccion} onChange={(event) => setSeleccion(event.target.value)} style={inputStyle}>
                  <option value="">Elige una opción...</option>
                  <optgroup label="Recetas para empleados">
                    {filtrar(opciones.recetas).map((item) => (
                      <option key={`r${item.id}`} value={`receta:${item.id}`}>{item.nombre}</option>
                    ))}
                    {opciones.recetas.length === 0 ? <option disabled>Ninguna receta marcada para empleados todavía</option> : null}
                  </optgroup>
                  <optgroup label="Subrecetas">
                    {filtrar(opciones.subrecetas).map((item) => (
                      <option key={`s${item.id}`} value={`subreceta:${item.id}`}>{item.nombre}</option>
                    ))}
                  </optgroup>
                  <optgroup label="Ingredientes">
                    {filtrar(opciones.ingredientes).map((item) => (
                      <option key={`i${item.id}`} value={`ingrediente:${item.id}`}>{item.nombre}</option>
                    ))}
                  </optgroup>
                </select>
              </label>

              <label style={campoStyle}>
                <span style={etiquetaStyle}>{elegido ? (tipo === 'receta' ? 'Porciones' : `Cantidad (${elegido.unidad})`) : 'Cantidad'}</span>
                <input
                  type="number"
                  min="0"
                  step="any"
                  inputMode="decimal"
                  value={cantidad}
                  onChange={(event) => setCantidad(event.target.value)}
                  placeholder={tipo === 'receta' ? 'Ej: 12 porciones' : 'Ej: 500'}
                  style={inputStyle}
                />
              </label>
            </div>

            <div style={formGridStyle(isMobile)}>
              <label style={campoStyle}>
                <span style={etiquetaStyle}>Fecha</span>
                <input
                  type="date"
                  value={fecha}
                  max={hoyIso}
                  disabled={!opciones.puede_fecha_pasada}
                  onChange={(event) => setFecha(event.target.value || hoyIso)}
                  style={inputStyle}
                />
                {!opciones.puede_fecha_pasada ? <span style={mutedStyle}>Solo un administrador puede registrar fechas pasadas.</span> : null}
              </label>
              <label style={campoStyle}>
                <span style={etiquetaStyle}>Turno</span>
                <select value={turno} onChange={(event) => setTurno(event.target.value)} style={inputStyle}>
                  <option value="">Sin turno</option>
                  {opciones.turnos.map((opcion) => (
                    <option key={opcion.value} value={opcion.value}>{opcion.label}</option>
                  ))}
                </select>
              </label>
            </div>

            <label style={campoStyle}>
              <span style={etiquetaStyle}>Nota (opcional)</span>
              <input type="text" value={nota} maxLength={255} onChange={(event) => setNota(event.target.value)} placeholder="Ej: almuerzo del personal de cocina" style={inputStyle} />
            </label>

            {cargandoVista ? <div style={mutedStyle}>Calculando ingredientes...</div> : null}
            {errorVista ? <div style={noticeStyle}>{errorVista}</div> : null}

            {vistaPrevia ? (
              <div style={previewStyle}>
                <div style={previewTituloStyle}>Se descontará del inventario</div>
                {sinStock.length > 0 ? (
                  <div style={avisoStyle}>No alcanza el stock de: {sinStock.join(', ')}. Se puede registrar igual, pero quedará en negativo.</div>
                ) : null}
                {yaRegistradas.length > 0 ? (
                  <div style={infoStyle}>
                    Ya hay {yaRegistradas.length === 1 ? 'una comida registrada' : `${yaRegistradas.length} comidas registradas`} {turno ? 'en ese turno' : 'ese día'}:
                    {' '}{yaRegistradas.map((comida) => `${comida.nombre} (${formatCantidad(comida.cantidad)} ${comida.unidad})`).join(', ')}.
                  </div>
                ) : null}
                <div style={tablaScrollStyle}>
                  <table style={tablaStyle}>
                    <thead>
                      <tr>
                        <th style={thStyle}>Ingrediente</th>
                        <th style={{ ...thStyle, textAlign: 'right' }}>Se descuenta</th>
                        <th style={{ ...thStyle, textAlign: 'right' }}>Stock actual</th>
                        <th style={{ ...thStyle, textAlign: 'right' }}>Quedaría</th>
                        <th style={{ ...thStyle, textAlign: 'right' }}>Costo</th>
                      </tr>
                    </thead>
                    <tbody>
                      {vistaPrevia.lineas.map((linea) => (
                        <tr key={linea.ingrediente_id}>
                          <td style={tdStyle}>{linea.nombre}</td>
                          <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700 }}>−{formatCantidad(linea.cantidad)} {linea.unidad}</td>
                          <td style={{ ...tdStyle, textAlign: 'right' }}>{formatCantidad(linea.stock_actual)}</td>
                          <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 700, color: linea.alcanza ? 'var(--vg-text-strong)' : 'var(--vg-f-ff9d9d)' }}>
                            {formatCantidad(linea.stock_despues)} {linea.unidad}
                          </td>
                          <td style={{ ...tdStyle, textAlign: 'right' }}>${formatMonto(linea.costo)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div style={totalStyle}>Costo total: <strong>${formatMonto(vistaPrevia.costo_total)}</strong></div>
              </div>
            ) : null}

            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button
                type="button"
                onClick={() => setConfirmando(true)}
                disabled={!puedeRegistrar}
                style={{ ...primaryButtonStyle, opacity: puedeRegistrar ? 1 : 0.5, cursor: puedeRegistrar ? 'pointer' : 'not-allowed' }}
              >
                Registrar comida
              </button>
            </div>
          </div>
        ) : null}
      </section>

      <section style={panelStyle}>
        <div style={panelTitleStyle}>Historial</div>
        <RangoFechas
          desde={desde}
          hasta={hasta}
          onChange={(rango) => {
            setDesde(rango.desde);
            setHasta(rango.hasta);
          }}
        />
        {historial ? (
          <div style={resumenStyle}>
            <strong>{historial.total_registradas}</strong> {historial.total_registradas === 1 ? 'comida registrada' : 'comidas registradas'}
            {' · '}costo total <strong>${formatMonto(historial.costo_total)}</strong>
          </div>
        ) : null}
        {cargandoHistorial ? <div style={mutedStyle}>Cargando historial...</div> : null}
        {!cargandoHistorial && historial && historial.comidas.length === 0 ? (
          <div style={emptyStyle}>No hay comidas de empleados en este período.</div>
        ) : null}
        <div style={{ display: 'grid', gap: 8 }}>
          {(historial ? historial.comidas : []).map((comida) => {
            const anulada = comida.estado === 'anulada';
            return (
              <article key={comida.id} style={{ ...itemStyle, opacity: anulada ? 0.7 : 1 }}>
                <div style={itemHeaderStyle(isMobile)}>
                  <div style={{ minWidth: 0 }}>
                    <div style={itemTituloStyle}>
                      {comida.nombre}
                      <span style={tipoBadgeStyle}>{TIPO_LABEL[comida.tipo_origen]}</span>
                      {anulada ? <span style={anuladaBadgeStyle}>Anulada</span> : null}
                    </div>
                    <div style={mutedStyle}>
                      {formatFecha(comida.fecha)}{comida.turno_label ? ` · ${comida.turno_label}` : ''}
                      {' · '}{formatCantidad(comida.cantidad)} {comida.unidad}
                      {' · '}Registrada por {comida.registrada_por || '—'} el {formatFechaHora(comida.fecha_creacion)}
                    </div>
                    {comida.nota ? <div style={mutedStyle}>Nota: {comida.nota}</div> : null}
                    {anulada ? (
                      <div style={mutedStyle}>Anulada por {comida.anulada_por || '—'}: {comida.motivo_anulacion}</div>
                    ) : null}
                  </div>
                  <div style={itemAccionesStyle}>
                    <strong style={{ color: 'var(--vg-text-strong)', whiteSpace: 'nowrap' }}>${formatMonto(comida.costo_total)}</strong>
                    <button type="button" onClick={() => alternarLineas(comida)} style={linkButtonStyle} aria-expanded={Boolean(abiertas[comida.id])}>
                      {abiertas[comida.id] ? 'Ocultar ingredientes' : 'Ver ingredientes'}
                    </button>
                    {!anulada && opciones && opciones.puede_anular ? (
                      <button type="button" onClick={() => { setAnulando(comida); setMotivoAnulacion(''); }} style={dangerButtonStyle}>Anular</button>
                    ) : null}
                  </div>
                </div>
                {abiertas[comida.id] ? (
                  <div style={{ marginTop: 8 }}>
                    {!lineas[comida.id] ? <div style={mutedStyle}>Cargando...</div> : (
                      <ul style={listaStyle}>
                        {lineas[comida.id].map((linea) => (
                          <li key={linea.ingrediente_id} style={lineaStyle}>
                            <span>{linea.nombre}</span>
                            <span>{formatCantidad(linea.cantidad)} {linea.unidad} · ${formatMonto(linea.costo)}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      </section>

      <ConfirmModal
        open={confirmando}
        title="Confirmar comida de empleados"
        message={mensajeConfirmacion}
        confirmLabel="Sí, descontar del inventario"
        busy={guardando}
        onCancel={() => setConfirmando(false)}
        onConfirm={registrar}
      />

      {anulando ? (
        <div style={backdropStyle} onClick={anulandoBusy ? undefined : () => setAnulando(null)} role="presentation">
          <div style={modalStyle} role="dialog" aria-modal="true" aria-label="Anular comida" onClick={(event) => event.stopPropagation()}>
            <div style={modalTituloStyle}>Anular comida de empleados</div>
            <p style={{ ...mutedStyle, margin: 0, lineHeight: 1.5 }}>
              «{anulando.nombre}» del {formatFecha(anulando.fecha)}. Se repondrá al inventario lo que se descontó.
            </p>
            <label style={campoStyle}>
              <span style={etiquetaStyle}>Motivo (obligatorio)</span>
              <input type="text" value={motivoAnulacion} maxLength={255} onChange={(event) => setMotivoAnulacion(event.target.value)} style={inputStyle} autoFocus />
            </label>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button type="button" onClick={() => setAnulando(null)} style={secondaryButtonStyle} disabled={anulandoBusy}>Cancelar</button>
              <button type="button" onClick={anular} style={primaryButtonStyle} disabled={anulandoBusy || !motivoAnulacion.trim()}>
                {anulandoBusy ? 'Anulando...' : 'Anular y reponer inventario'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 14, padding: isMobile ? 6 : 10 });
const headerRowStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' };
const titleStyle = (isMobile) => ({ margin: 0, color: 'var(--vg-text-strong)', fontSize: isMobile ? 26 : 32 });
const subtitleStyle = { margin: '6px 0 0', color: 'var(--vg-f-d2c3c3)', lineHeight: 1.5, fontSize: 14 };
const mutedStyle = { color: 'var(--vg-f-c8bbbb)', fontSize: 12.5 };
const panelStyle = { display: 'grid', gap: 12, padding: 16, borderRadius: 18, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)' };
const panelTitleStyle = { color: 'var(--vg-text-strong)', fontSize: 18, fontWeight: 800 };
const formGridStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 1fr))', gap: 12 });
const campoStyle = { display: 'grid', gap: 4, alignContent: 'start' };
const etiquetaStyle = { color: 'var(--vg-f-d2c3c3)', fontSize: 12.5, fontWeight: 700 };
const inputStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.16)', background: 'var(--vg-s-161010)', padding: '10px 12px', color: 'var(--vg-text-strong)', fontSize: 14 };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid var(--vg-f-ff9191-a220)', background: 'rgba(255, 98, 98, 0.12)', color: 'var(--vg-f-ffd8d8)' };
const avisoStyle = { padding: '8px 12px', borderRadius: 10, border: '1px solid var(--vg-f-ffcf7d-a450)', background: 'rgba(255, 207, 125, 0.08)', color: 'var(--vg-f-ffe3a3)', fontSize: 13 };
const infoStyle = { padding: '8px 12px', borderRadius: 10, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'rgba(var(--vg-ink), 0.04)', color: 'var(--vg-f-d2c3c3)', fontSize: 13 };
const previewStyle = { display: 'grid', gap: 8, padding: 12, borderRadius: 14, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'rgba(var(--vg-ink), 0.03)' };
const previewTituloStyle = { color: 'var(--vg-f-ffb0b0)', fontSize: 11.5, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.06em' };
const tablaScrollStyle = { overflowX: 'auto' };
const tablaStyle = { width: '100%', borderCollapse: 'collapse', fontSize: 13 };
const thStyle = { textAlign: 'left', padding: '6px 8px', color: 'var(--vg-f-c8bbbb)', fontSize: 11.5, fontWeight: 700, borderBottom: '1px solid rgba(var(--vg-ink), 0.12)' };
const tdStyle = { padding: '6px 8px', borderBottom: '1px solid rgba(var(--vg-ink), 0.06)', color: 'var(--vg-text-strong)' };
const totalStyle = { textAlign: 'right', color: 'var(--vg-f-d2c3c3)', fontSize: 14 };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '11px 20px', background: 'linear-gradient(90deg, #bf1f1f 0%, var(--vg-accent-primary) 100%)', color: '#fff', fontWeight: 800, cursor: 'pointer' };
const secondaryButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.16)', borderRadius: 999, padding: '10px 16px', background: 'rgba(var(--vg-ink), 0.05)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer' };
const dangerButtonStyle = { border: '1px solid var(--vg-f-ff6666-a450)', borderRadius: 999, padding: '6px 12px', background: 'rgba(255, 73, 73, 0.1)', color: 'var(--vg-f-ffb3b3)', fontWeight: 700, fontSize: 12.5, cursor: 'pointer' };
const linkButtonStyle = { border: 'none', background: 'transparent', padding: 0, color: 'var(--vg-f-bfe0ff)', fontWeight: 700, fontSize: 12.5, textDecoration: 'underline', cursor: 'pointer' };
const resumenStyle = { color: 'var(--vg-f-d2c3c3)', fontSize: 14 };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(var(--vg-ink), 0.14)', color: 'var(--vg-f-c8bbbb)', textAlign: 'center', padding: 14 };
const itemStyle = { borderRadius: 14, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'rgba(var(--vg-ink), 0.03)', padding: '12px 14px' };
const itemHeaderStyle = (isMobile) => ({ display: 'flex', flexDirection: isMobile ? 'column' : 'row', justifyContent: 'space-between', gap: 10 });
const itemTituloStyle = { color: 'var(--vg-text-strong)', fontWeight: 700, fontSize: 15, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' };
const itemAccionesStyle = { display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', justifyContent: 'flex-end' };
const tipoBadgeStyle = { padding: '2px 8px', borderRadius: 999, fontSize: 11, fontWeight: 700, color: 'var(--vg-f-bfe0ff)', background: 'rgba(90, 170, 255, 0.12)' };
const anuladaBadgeStyle = { padding: '2px 8px', borderRadius: 999, fontSize: 11, fontWeight: 800, color: 'var(--vg-f-ffb3b3)', background: 'rgba(255, 98, 98, 0.14)' };
const listaStyle = { listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 2 };
const lineaStyle = { display: 'flex', justifyContent: 'space-between', gap: 12, padding: '4px 0', borderBottom: '1px solid rgba(var(--vg-ink), 0.06)', color: 'var(--vg-text-strong)', fontSize: 13 };
const backdropStyle = { position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0, 0, 0, 0.6)', display: 'grid', placeItems: 'center', padding: 16 };
const modalStyle = { width: '100%', maxWidth: 440, borderRadius: 20, border: '1px solid var(--vg-f-ff9191-a300)', background: 'linear-gradient(180deg, var(--vg-s-1c0c0c-a980) 0%, var(--vg-s-0a0808-a990) 100%)', padding: '22px 22px 18px', boxShadow: '0 20px 50px rgba(0, 0, 0, calc(0.45 * var(--vg-shadow-k)))', display: 'grid', gap: 12 };
const modalTituloStyle = { color: 'var(--vg-text-strong)', fontSize: 19, fontWeight: 800 };

export default ComidaEmpleadosPage;

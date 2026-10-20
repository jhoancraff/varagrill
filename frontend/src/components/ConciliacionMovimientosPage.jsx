import { useCallback, useEffect, useMemo, useState } from 'react';
import BotonDescargarPdf from './BotonDescargarPdf';
import { RangoFechas } from './FiltroFechas';
import Toast from './Toast';
import useToast from '../hooks/useToast';

const API = '/api/admin/conciliacion-bancaria/';
const PAGINA = 100;

function toIso(date) {
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60000).toISOString().slice(0, 10);
}

function startOfMonthIso() {
  const hoy = new Date();
  return toIso(new Date(hoy.getFullYear(), hoy.getMonth(), 1));
}

function formatMonto(value) {
  return Number(value || 0).toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatFecha(iso) {
  if (!iso) return '';
  const [anio, mes, dia] = iso.slice(0, 10).split('-');
  return `${dia}/${mes}/${anio}`;
}

function formatFechaHora(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString('es-VE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
}

function getCookie(name) {
  const all = `; ${document.cookie}`;
  const parts = all.split(`; ${name}=`);
  return parts.length === 2 ? parts.pop().split(';').shift() : '';
}

const CUENTA_GUARDADA = 'vg_conciliacion_cuenta';

function cuentaGuardada() {
  try {
    return window.localStorage.getItem(CUENTA_GUARDADA) || '';
  } catch (e) {
    return '';
  }
}

function guardarCuenta(nombre) {
  try {
    window.localStorage.setItem(CUENTA_GUARDADA, nombre);
  } catch (e) {
    // Sin almacenamiento simplemente no se recuerda la cuenta.
  }
}

// Cambia un movimiento ya modificado dentro de los datos y recalcula los conteos por estado (sin volver a pedir todo).
function reemplazarMovimiento(datos, nuevo) {
  const movimientos = datos.movimientos.map((m) => (m.id === nuevo.id ? nuevo : m));
  const estados = {};
  Object.keys(datos.resumen.estados).forEach((e) => { estados[e] = { cantidad: 0, creditos: 0, debitos: 0 }; });
  movimientos.forEach((m) => {
    const bucket = estados[m.estado];
    if (!bucket) return;
    bucket.cantidad += 1;
    bucket[m.tipo === 'credito' ? 'creditos' : 'debitos'] += Number(m.monto);
  });
  Object.keys(estados).forEach((e) => {
    estados[e].creditos = estados[e].creditos.toFixed(2);
    estados[e].debitos = estados[e].debitos.toFixed(2);
  });
  return { ...datos, movimientos, resumen: { ...datos.resumen, estados } };
}

// Llama a la API y devuelve el JSON; si falla lanza un Error con el mensaje del servidor.
async function llamar(url, { method = 'GET', body, formData } = {}) {
  const options = { method, credentials: 'include', cache: 'no-store', headers: {} };
  if (method !== 'GET') options.headers['X-CSRFToken'] = getCookie('csrftoken') || '';
  if (formData) {
    options.body = formData;
  } else if (body) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    throw new Error(data.message || 'No se pudo completar la operación.');
  }
  return data;
}

// El estado se comunica con un punto y el texto del mismo color (sin recuadros): colores del tema, legibles en claro y oscuro.
const ESTADOS = {
  conciliado: { texto: 'Conciliado', color: 'var(--vg-f-9fe3b0)' },
  por_revisar: { texto: 'Por revisar', color: 'var(--vg-f-ffcf7d)' },
  sin_coincidencia: { texto: 'Sin coincidencia', color: 'var(--vg-f-ffb0b0)' },
  ignorado: { texto: 'Ignorado', color: 'var(--vg-f-c8bbbb)' },
  pendiente: { texto: 'Pendiente', color: 'var(--vg-f-9ecbff)' },
};

const PESTANAS = [
  { id: 'todos', texto: 'Todos' },
  { id: 'conciliado', texto: 'Conciliados' },
  { id: 'por_revisar', texto: 'Por revisar' },
  { id: 'sin_coincidencia', texto: 'Sin coincidencia' },
  { id: 'sistema', texto: 'Solo en el sistema' },
  { id: 'pos', texto: 'POS' },
  { id: 'cierres', texto: 'Cierres' },
];

function EstadoTexto({ estado, texto }) {
  const e = ESTADOS[estado] || ESTADOS.pendiente;
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: e.color, fontWeight: 700, fontSize: 12.5, whiteSpace: 'nowrap' }}>
      <span aria-hidden="true" style={{ width: 7, height: 7, borderRadius: '50%', background: e.color, flexShrink: 0 }} />
      {texto || e.texto}
    </span>
  );
}

function horaDe(iso) {
  return iso ? new Date(iso).toLocaleTimeString('es-VE', { hour: '2-digit', minute: '2-digit', hour12: false }) : '';
}

function diaLargo(iso) {
  const [anio, mes, dia] = iso.split('-').map(Number);
  const texto = new Date(anio, mes - 1, dia).toLocaleDateString('es-VE', { weekday: 'long', day: 'numeric', month: 'long' });
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

// Agrupa (en el orden recibido) los movimientos por dia: el dia se escribe una sola vez en un encabezado y cada fila solo lleva la hora.
function agruparPorDia(movs) {
  const grupos = [];
  movs.forEach((m) => {
    const dia = m.fecha.slice(0, 10);
    const ultimo = grupos[grupos.length - 1];
    if (ultimo && ultimo.dia === dia) ultimo.movs.push(m);
    else grupos.push({ dia, movs: [m] });
  });
  return grupos;
}

function ConciliacionMovimientosPage({ isMobile, onBack }) {
  const { toast, showSuccess, showError, hideToast } = useToast();
  const [cuentas, setCuentas] = useState([]);
  const [cuenta, setCuenta] = useState('');
  const [rango, setRango] = useState({ desde: startOfMonthIso(), hasta: toIso(new Date()) });
  const [datos, setDatos] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState('');
  const [pestana, setPestana] = useState('todos');
  const [busqueda, setBusqueda] = useState('');
  const [visibles, setVisibles] = useState(PAGINA);
  const [ocupado, setOcupado] = useState(false);
  const [sistema, setSistema] = useState(null);
  const [importando, setImportando] = useState(false);
  const [candidatosDe, setCandidatosDe] = useState(null);
  // Registros tildados en el modal para un pago dividido: { 'tipo-id': candidato }. Se guardan completos
  // para que sigan contando aunque se cambie entre "parecidos" y "todos los cercanos".
  const [seleccion, setSeleccion] = useState({});
  const [ignorando, setIgnorando] = useState(null);
  const [pdfConConciliados, setPdfConConciliados] = useState(false);
  const [cierres, setCierres] = useState(null);
  const [cerrandoDia, setCerrandoDia] = useState(null);
  const [reabriendo, setReabriendo] = useState(null);

  useEffect(() => {
    let cancelado = false;
    llamar(`${API}cuentas/`)
      .then((data) => {
        if (cancelado) return;
        setCuentas(data.cuentas);
        // La cuenta de la última vez; si no hay, la que ya tiene movimientos cargados; si no, la primera.
        const soportadas = data.cuentas.filter((c) => c.soportada);
        const elegida = soportadas.find((c) => c.nombre === cuentaGuardada())
          || [...soportadas].sort((a, b) => b.movimientos_cargados - a.movimientos_cargados)[0];
        if (elegida) setCuenta(elegida.nombre);
      })
      .catch((e) => setError(e.message));
    return () => { cancelado = true; };
  }, []);

  const cargar = useCallback(async (silencioso = false) => {
    if (!cuenta) return;
    if (!silencioso) setCargando(true);
    setError('');
    try {
      const qs = new URLSearchParams({ cuenta, desde: rango.desde, hasta: rango.hasta });
      setDatos(await llamar(`${API}movimientos/?${qs}`));
    } catch (e) {
      setError(e.message);
      setDatos(null);
    } finally {
      setCargando(false);
    }
  }, [cuenta, rango.desde, rango.hasta]);

  const cargarCierres = useCallback(async () => {
    if (!cuenta) return;
    try {
      const qs = new URLSearchParams({ cuenta, desde: rango.desde, hasta: rango.hasta });
      setCierres(await llamar(`${API}cierres/?${qs}`));
    } catch (e) {
      setCierres(null);
    }
  }, [cuenta, rango.desde, rango.hasta]);

  useEffect(() => {
    setVisibles(PAGINA);
    setSistema(null);
    cargar();
    cargarCierres();
  }, [cargar, cargarCierres]);

  useEffect(() => {
    if (pestana !== 'sistema' || !cuenta || sistema) return;
    const qs = new URLSearchParams({ cuenta, desde: rango.desde, hasta: rango.hasta });
    llamar(`${API}reverso/?${qs}`).then((data) => setSistema(data.registros)).catch((e) => showError(e.message));
  }, [pestana, cuenta, rango.desde, rango.hasta, sistema, showError]);

  const movimientos = datos?.movimientos || [];
  const resumen = datos?.resumen;
  const estados = resumen?.estados || {};
  const sugerenciasFuertes = useMemo(
    () => movimientos.filter((m) => m.estado === 'por_revisar' && m.vinculos.some((v) => v.estado === 'sugerido' && v.puntaje >= 66 && !v.nota && v.metodo !== 'comision_dia')).length,
    [movimientos],
  );

  const filtrados = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    return movimientos.filter((m) => {
      if (pestana !== 'todos' && m.estado !== pestana) return false;
      if (!q) return true;
      return `${m.descripcion} ${m.referencia} ${m.observacion} ${m.monto}`.toLowerCase().includes(q);
    });
  }, [movimientos, pestana, busqueda]);

  const ejecutar = async (accion, mensaje) => {
    setOcupado(true);
    try {
      const data = await accion();
      if (mensaje) showSuccess(typeof mensaje === 'function' ? mensaje(data) : mensaje);
      setSistema(null);
      await Promise.all([cargar(true), cargarCierres()]);
    } catch (e) {
      showError(e.message);
    } finally {
      setOcupado(false);
    }
  };

  // Una acción sobre un movimiento devuelve ese movimiento ya actualizado: se cambia en pantalla sin recargar todo.
  const postAccion = async (mov, body, mensaje) => {
    setOcupado(true);
    try {
      const data = await llamar(`${API}movimientos/${mov.id}/accion/`, { method: 'POST', body });
      setDatos((actual) => (actual ? reemplazarMovimiento(actual, data.movimiento) : actual));
      setSistema(null);
      cargarCierres();
      if (mensaje) showSuccess(mensaje);
    } catch (e) {
      showError(e.message);
    } finally {
      setOcupado(false);
    }
  };

  const cerrarDia = async (dia, nota) => {
    await llamar(`${API}cierres/cerrar/`, { method: 'POST', body: { cuenta, fecha: dia.fecha, nota, confirmo: true } });
    setCerrandoDia(null);
    showSuccess(`Día ${formatFecha(dia.fecha)} cerrado.`);
    await Promise.all([cargar(true), cargarCierres()]);
  };

  const reabrirDia = async (dia, motivo) => {
    await llamar(`${API}cierres/${dia.cierre.id}/reabrir/`, { method: 'POST', body: { motivo } });
    setReabriendo(null);
    showSuccess(`Día ${formatFecha(dia.fecha)} reabierto.`);
    await Promise.all([cargar(true), cargarCierres()]);
  };

  const verDia = (dia) => {
    setRango({ desde: dia.fecha, hasta: dia.fecha });
    setPestana('todos');
  };

  const volverACruzar = () => ejecutar(
    () => llamar(`${API}conciliar/`, { method: 'POST', body: { cuenta, ...rango } }),
    'Cruce actualizado.',
  );

  const confirmarProbables = () => ejecutar(
    () => llamar(`${API}confirmar-probables/`, { method: 'POST', body: { cuenta, ...rango } }),
    (data) => `${data.confirmados} movimientos confirmados.`,
  );

  const abrirCandidatos = async (mov, todos = false) => {
    setCandidatosDe({ mov, lista: null, todos });
    if (!candidatosDe || candidatosDe.mov.id !== mov.id) setSeleccion({});
    try {
      const data = await llamar(`${API}movimientos/${mov.id}/candidatos/${todos ? '?todos=1' : ''}`);
      setCandidatosDe({ mov, lista: data.candidatos, todos });
    } catch (e) {
      showError(e.message);
      setCandidatosDe(null);
    }
  };

  const cerrarCandidatos = () => {
    setCandidatosDe(null);
    setSeleccion({});
  };

  const vincular = async (candidato) => {
    const mov = candidatosDe.mov;
    cerrarCandidatos();
    await postAccion(mov, { accion: 'elegir', tipo: candidato.tipo, origen_id: candidato.id }, 'Movimiento conciliado.');
  };

  const alternarSeleccion = (candidato) => {
    const clave = `${candidato.tipo}-${candidato.id}`;
    setSeleccion((actual) => {
      const nueva = { ...actual };
      if (nueva[clave]) delete nueva[clave];
      else nueva[clave] = candidato;
      return nueva;
    });
  };

  const vincularSeleccion = async () => {
    const mov = candidatosDe.mov;
    const registros = Object.values(seleccion).map((c) => ({ tipo: c.tipo, origen_id: c.id }));
    cerrarCandidatos();
    await postAccion(
      mov,
      { accion: 'elegir', registros },
      registros.length > 1 ? `Movimiento conciliado con ${registros.length} registros.` : 'Movimiento conciliado.',
    );
  };

  const seleccionados = Object.values(seleccion);
  const sumaSeleccion = seleccionados.reduce((total, c) => total + Number(c.monto), 0);
  const faltante = candidatosDe ? Number(candidatosDe.mov.monto) - sumaSeleccion : 0;

  const cuentaActual = cuentas.find((c) => c.nombre === cuenta);

  return (
    <section style={containerStyle(isMobile)}>
      <Toast toast={toast} onClose={hideToast} />
      <button type="button" onClick={onBack} style={backButtonStyle}>← Volver</button>

      <div style={headerRowStyle}>
        <h2 style={titleStyle(isMobile)}>Conciliación de movimientos</h2>
        <button type="button" style={primaryButtonStyle} onClick={() => setImportando(true)} disabled={!cuentaActual?.soportada}>
          Importar extracto
        </button>
      </div>

      <div style={panelStyle}>
        <div style={controlesStyle(isMobile)}>
          <label style={campoStyle}>
            <span style={etiquetaStyle}>Cuenta bancaria</span>
            <select value={cuenta} onChange={(e) => { setCuenta(e.target.value); guardarCuenta(e.target.value); }} style={inputStyle}>
              {cuentas.length === 0 ? <option value="">Sin cuentas bancarias configuradas</option> : null}
              {cuentas.map((c) => (
                <option key={c.nombre} value={c.nombre} disabled={!c.soportada}>
                  {c.nombre}{c.soportada ? '' : ' (solo bolívares por ahora)'}
                </option>
              ))}
            </select>
          </label>
          <RangoFechas desde={rango.desde} hasta={rango.hasta} onChange={setRango} />
        </div>
        <div style={accionesStyle}>
          <button type="button" style={secondaryButtonStyle} onClick={volverACruzar} disabled={ocupado || !datos}>
            Volver a cruzar
          </button>
          {sugerenciasFuertes > 0 ? (
            <button type="button" style={secondaryButtonStyle} onClick={confirmarProbables} disabled={ocupado}>
              Confirmar {sugerenciasFuertes} probables
            </button>
          ) : null}
          <BotonDescargarPdf
            url={`${API}pdf/`}
            params={{ cuenta, desde: rango.desde, hasta: rango.hasta, conciliados: pdfConConciliados ? '1' : '0' }}
            onError={showError}
          >
            PDF
          </BotonDescargarPdf>
          <label style={checkStyle} title="Incluir en el PDF el detalle de los movimientos conciliados">
            <input type="checkbox" checked={pdfConConciliados} onChange={(e) => setPdfConConciliados(e.target.checked)} />
            con conciliados
          </label>
        </div>
      </div>

      {error ? <div style={noticeStyle}>{error}</div> : null}
      {cargando ? <div style={emptyStyle}>Cargando movimientos...</div> : null}

      {!cargando && resumen ? (
        <>
          <div style={resumenStyle(isMobile)}>
            <Cifra
              titulo="Conciliados"
              valor={`${estados.conciliado?.cantidad || 0} de ${resumen.total}`}
              avance={resumen.total ? (estados.conciliado?.cantidad || 0) / resumen.total : 0}
              onClick={() => setPestana('conciliado')}
            />
            <Cifra
              titulo="Por revisar"
              valor={estados.por_revisar?.cantidad || 0}
              color={(estados.por_revisar?.cantidad || 0) > 0 ? ESTADOS.por_revisar.color : undefined}
              onClick={() => setPestana('por_revisar')}
            />
            <Cifra
              titulo="Sin coincidencia"
              valor={estados.sin_coincidencia?.cantidad || 0}
              nota={(estados.sin_coincidencia?.cantidad || 0) > 0
                ? `Bs ${formatMonto(Number(estados.sin_coincidencia?.creditos || 0) + Number(estados.sin_coincidencia?.debitos || 0))}`
                : ''}
              color={(estados.sin_coincidencia?.cantidad || 0) > 0 ? ESTADOS.sin_coincidencia.color : undefined}
              onClick={() => setPestana('sin_coincidencia')}
            />
            <Cifra
              titulo="Días cerrados"
              valor={cierres ? `${cierres.resumen.cerrados} de ${cierres.resumen.dias}` : '—'}
              nota={cierres ? (cierres.resumen.completo ? 'Período cuadrado' : (cierres.resumen.pendientes ? `${cierres.resumen.pendientes} con pendientes` : '')) : ''}
              color={cierres && cierres.resumen.discontinuidades > 0 ? ESTADOS.por_revisar.color : undefined}
              onClick={() => setPestana('cierres')}
            />
            <div style={{ ...cifraStyle, cursor: 'default' }}>
              <span style={mutedStyle}>Entradas y salidas</span>
              <span style={{ ...cifraNotaStyle, color: ESTADOS.conciliado.color }}>+ Bs {formatMonto(resumen.creditos)}</span>
              <span style={cifraNotaStyle}>− Bs {formatMonto(resumen.debitos)}</span>
            </div>
          </div>

          <div style={pestanasStyle} role="tablist">
            {PESTANAS.map((p) => {
              const cantidad = ['conciliado', 'por_revisar', 'sin_coincidencia'].includes(p.id) ? estados[p.id]?.cantidad || 0 : null;
              return (
                <button
                  key={p.id}
                  type="button"
                  role="tab"
                  aria-selected={pestana === p.id}
                  onClick={() => { setPestana(p.id); setVisibles(PAGINA); }}
                  style={pestana === p.id ? pestanaActivaStyle : pestanaStyle}
                >
                  {p.texto}
                  {cantidad !== null ? <span style={{ marginLeft: 6, fontWeight: 600, opacity: 0.7 }}>{cantidad}</span> : null}
                </button>
              );
            })}
          </div>

          {pestana === 'pos' ? <TablaPos filas={datos.pos} /> : null}
          {pestana === 'sistema' ? <TablaSistema filas={sistema} /> : null}
          {pestana === 'cierres' ? (
            <TablaCierres
              datos={cierres}
              onCerrar={setCerrandoDia}
              onReabrir={setReabriendo}
              onVer={verDia}
            />
          ) : null}

          {pestana !== 'pos' && pestana !== 'sistema' && pestana !== 'cierres' ? (
            <>
              <input
                type="search"
                value={busqueda}
                onChange={(e) => { setBusqueda(e.target.value); setVisibles(PAGINA); }}
                placeholder="Buscar por descripción, referencia o monto"
                style={inputStyle}
              />
              {filtrados.length === 0 ? (
                <div style={emptyStyle}>
                  {movimientos.length === 0
                    ? 'No hay movimientos del banco cargados en este rango. Usa "Importar extracto del banco".'
                    : 'No hay movimientos con ese filtro.'}
                </div>
              ) : (
                <div style={tablaScrollStyle}>
                  <table style={isMobile ? { ...tablaStyle, display: 'block' } : tablaStyle}>
                    <thead style={isMobile ? { display: 'none' } : undefined}>
                      <tr>
                        <th style={thStyle}>Hora</th>
                        <th style={thStyle}>Movimiento del banco</th>
                        <th style={{ ...thStyle, textAlign: 'right' }}>Monto (Bs)</th>
                        <th style={thStyle}>En el sistema</th>
                        <th style={thStyle} />
                      </tr>
                    </thead>
                    {agruparPorDia(filtrados.slice(0, visibles)).map((grupo) => {
                      const porResolver = grupo.movs.filter((m) => m.estado === 'por_revisar' || m.estado === 'sin_coincidencia').length;
                      const cerrado = grupo.movs.every((m) => m.dia_cerrado);
                      return (
                        <tbody key={grupo.dia} style={isMobile ? { display: 'block' } : undefined}>
                          <tr style={isMobile ? { display: 'block' } : undefined}>
                            <td colSpan={5} style={isMobile ? { ...diaEncabezadoStyle, display: 'block' } : diaEncabezadoStyle}>
                              <span style={{ fontWeight: 800, color: 'var(--vg-text-strong)' }}>{diaLargo(grupo.dia)}</span>
                              <span style={{ ...mutedStyle, marginLeft: 12 }}>
                                {grupo.movs.length} {grupo.movs.length === 1 ? 'movimiento' : 'movimientos'}
                                {cerrado ? ' · día cerrado' : porResolver > 0 ? ` · ${porResolver} por resolver` : ''}
                              </span>
                            </td>
                          </tr>
                          {grupo.movs.map((m) => (
                            <FilaMovimiento
                              key={m.id}
                              mov={m}
                              bloqueado={m.dia_cerrado}
                              ocupado={ocupado}
                              compacto={isMobile}
                              onConfirmar={(v) => postAccion(m, { accion: 'confirmar', vinculo_id: v.id }, 'Movimiento conciliado.')}
                              onRechazar={(v) => postAccion(m, { accion: 'rechazar', vinculo_id: v.id }, 'Sugerencia rechazada.')}
                              onBuscar={() => abrirCandidatos(m)}
                              onIgnorar={() => setIgnorando({ mov: m, motivo: '' })}
                              onReabrir={() => postAccion(m, { accion: 'reabrir' }, 'Movimiento reabierto.')}
                            />
                          ))}
                        </tbody>
                      );
                    })}
                  </table>
                </div>
              )}
              {filtrados.length > visibles ? (
                <button type="button" style={secondaryButtonStyle} onClick={() => setVisibles((v) => v + PAGINA)}>
                  Mostrar más ({filtrados.length - visibles} restantes)
                </button>
              ) : null}
            </>
          ) : null}
        </>
      ) : null}

      {importando ? (
        <ImportarModal
          cuenta={cuenta}
          onCerrar={() => setImportando(false)}
          onImportado={(resultado) => {
            setImportando(false);
            showSuccess(resultado.message || 'Extracto importado.');
            const { desde, hasta } = resultado.extracto || {};
            if (desde && hasta) setRango({ desde, hasta });
            else cargar(true);
          }}
          onError={showError}
        />
      ) : null}

      {candidatosDe ? (
        <div style={backdropStyle} onClick={cerrarCandidatos}>
          <div style={modalStyle(true)} onClick={(e) => e.stopPropagation()}>
            <div style={modalTituloStyle}>Elegir el registro del sistema</div>
            <div style={mutedStyle}>
              {candidatosDe.mov.descripcion} · Bs {formatMonto(candidatosDe.mov.monto)} · {formatFechaHora(candidatosDe.mov.fecha)}
              {candidatosDe.mov.referencia ? ` · ref. ${candidatosDe.mov.referencia}` : ''}
            </div>
            <div style={mutedStyle}>¿Pagó varios registros a la vez, como una compra y un gasto? Tilda todos y vincúlalos juntos.</div>
            {candidatosDe.lista === null ? <div style={emptyStyle}>Buscando...</div> : null}
            {candidatosDe.lista && candidatosDe.lista.length === 0 ? (
              <div style={emptyStyle}>
                {candidatosDe.todos
                  ? 'No hay registros libres en esta cuenta cerca de esa fecha. Puede que esta operación no se haya registrado.'
                  : 'No hay registros parecidos en el sistema. Puede que esta operación no se haya registrado, o que sea un pago dividido: prueba "Ver todos los registros cercanos".'}
              </div>
            ) : null}
            {(candidatosDe.lista || []).map((c) => {
              const clave = `${c.tipo}-${c.id}`;
              return (
                <div key={clave} style={candidatoStyle}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer', flex: 1 }}>
                    <input type="checkbox" checked={Boolean(seleccion[clave])} onChange={() => alternarSeleccion(c)} />
                    <div style={{ display: 'grid', gap: 2 }}>
                      <strong style={{ color: 'var(--vg-text-strong)' }}>{c.etiqueta}</strong>
                      <span style={mutedStyle}>
                        {formatFecha(c.fecha)} · Bs {formatMonto(c.monto)}
                        {c.referencia ? ` · ref. ${c.referencia}` : ''}
                        {!c.nota && c.diferencia && Number(c.diferencia) !== 0 ? ` · diferencia Bs ${formatMonto(c.diferencia)}` : ''}
                      </span>
                      {c.nota ? <span style={avisoTextoStyle}>{c.nota}</span> : null}
                    </div>
                  </label>
                  <button type="button" style={chipStyle} onClick={() => vincular(c)} disabled={ocupado}>Vincular</button>
                </div>
              );
            })}
            {seleccionados.length > 0 ? (
              <div style={Math.abs(faltante) <= 2 ? infoStyle : avisoStyle}>
                <strong>{seleccionados.length} seleccionado{seleccionados.length === 1 ? '' : 's'}: Bs {formatMonto(sumaSeleccion)}</strong>
                {' '}de Bs {formatMonto(candidatosDe.mov.monto)} del banco.
                {Math.abs(faltante) <= 2
                  ? ' Cuadra.'
                  : ` ${faltante > 0 ? 'Faltan' : 'Sobran'} Bs ${formatMonto(Math.abs(faltante))}; se puede vincular igual y la diferencia queda anotada.`}
              </div>
            ) : null}
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
              <button
                type="button"
                style={secondaryButtonStyle}
                onClick={() => abrirCandidatos(candidatosDe.mov, !candidatosDe.todos)}
                disabled={candidatosDe.lista === null}
              >
                {candidatosDe.todos ? 'Ver solo los parecidos' : 'Ver todos los registros cercanos'}
              </button>
              <div style={{ display: 'flex', gap: 10 }}>
                <button type="button" style={secondaryButtonStyle} onClick={cerrarCandidatos}>Cerrar</button>
                {seleccionados.length > 0 ? (
                  <button type="button" style={primaryButtonStyle} onClick={vincularSeleccion} disabled={ocupado}>
                    {seleccionados.length === 1 ? 'Vincular el seleccionado' : `Vincular los ${seleccionados.length} juntos`}
                  </button>
                ) : null}
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {cerrandoDia ? (
        <CerrarDiaModal dia={cerrandoDia} onCerrar={() => setCerrandoDia(null)} onConfirmar={cerrarDia} onError={showError} />
      ) : null}

      {reabriendo ? (
        <ReabrirModal dia={reabriendo} onCerrar={() => setReabriendo(null)} onConfirmar={reabrirDia} onError={showError} />
      ) : null}

      {ignorando ? (
        <div style={backdropStyle} onClick={() => setIgnorando(null)}>
          <div style={modalStyle(false)} onClick={(e) => e.stopPropagation()}>
            <div style={modalTituloStyle}>Ignorar este movimiento</div>
            <div style={mutedStyle}>
              {ignorando.mov.descripcion} · Bs {formatMonto(ignorando.mov.monto)}. Queda fuera del cruce, con el motivo anotado.
            </div>
            <label style={campoStyle}>
              <span style={etiquetaStyle}>Motivo</span>
              <textarea
                rows={3}
                value={ignorando.motivo}
                onChange={(e) => setIgnorando({ ...ignorando, motivo: e.target.value })}
                placeholder="Ej: cargo del banco que no se lleva al sistema"
                style={{ ...inputStyle, resize: 'vertical' }}
              />
            </label>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button type="button" style={secondaryButtonStyle} onClick={() => setIgnorando(null)}>Cancelar</button>
              <button
                type="button"
                style={primaryButtonStyle}
                disabled={!ignorando.motivo.trim()}
                onClick={() => {
                  const { mov, motivo } = ignorando;
                  setIgnorando(null);
                  postAccion(mov, { accion: 'ignorar', motivo }, 'Movimiento ignorado.');
                }}
              >
                Ignorar
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

// Una cifra del resumen: titulo, valor grande y, si hace falta, una nota corta o una barra de avance. Es un boton cuando lleva a una pestana.
function Cifra({ titulo, valor, nota, color, avance, onClick }) {
  return (
    <button type="button" onClick={onClick} disabled={!onClick} style={{ ...cifraStyle, cursor: onClick ? 'pointer' : 'default' }}>
      <span style={mutedStyle}>{titulo}</span>
      <span style={{ ...cifraValorStyle, color: color || 'var(--vg-text-strong)' }}>{valor}</span>
      {avance !== undefined ? (
        <span aria-hidden="true" style={barraPistaStyle}>
          <span style={{ ...barraRellenoStyle, width: `${Math.round(avance * 100)}%` }} />
        </span>
      ) : null}
      {nota ? <span style={cifraNotaStyle}>{nota}</span> : null}
    </button>
  );
}

function FilaMovimiento({ mov, bloqueado, ocupado, compacto, onConfirmar, onRechazar, onBuscar, onIgnorar, onReabrir }) {
  const sugerido = mov.vinculos.find((v) => v.estado === 'sugerido');
  const confirmados = mov.vinculos.filter((v) => v.estado === 'confirmado');
  const confirmado = confirmados[0];
  const vinculo = confirmado || sugerido;
  // Un movimiento puede pagar varios registros a la vez (compra + gasto): se listan todos y su suma.
  const pagoDividido = confirmados.length > 1 && confirmado.metodo !== 'comision_dia';
  const esCredito = mov.tipo === 'credito';
  const esPos = mov.clase === 'pos';
  // Las referencias de puros ceros (ej. las del POS) no dicen nada: no se muestran.
  const detalle = [compacto ? horaDe(mov.fecha) : '', /[1-9]/.test(mov.referencia || '') ? `Ref. ${mov.referencia}` : '', mov.observacion].filter(Boolean).join(' · ');
  // En celular la fila es un bloque de dos columnas (descripcion + monto) con el estado y las acciones debajo.
  const celda = (normal, enCompacto) => (compacto ? { ...tdStyle, padding: 0, border: 'none', minWidth: 0, maxWidth: 'none', width: 'auto', ...enCompacto } : normal);
  // Solo se muestra en la fila lo que pide una decision; el resto (metodo del cruce, diferencias ya aceptadas) queda en el tooltip.
  const aviso = vinculo && mov.estado === 'por_revisar'
    ? (vinculo.nota || (Number(vinculo.diferencia) !== 0 ? `Diferencia de Bs ${formatMonto(vinculo.diferencia)}` : ''))
    : '';
  const avisoDivido = pagoDividido && Number(confirmado.diferencia) !== 0 ? confirmado.nota : '';

  return (
    <tr style={compacto ? { display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: '3px 12px', padding: '10px 2px', borderBottom: '1px solid rgba(var(--vg-ink), 0.06)' } : undefined}>
      <td style={compacto ? { display: 'none' } : { ...tdStyle, ...mutedStyle, whiteSpace: 'nowrap', width: 52 }} title={formatFechaHora(mov.fecha)}>{horaDe(mov.fecha)}</td>
      <td style={celda({ ...tdStyle, minWidth: 200, maxWidth: 340 }, {})}>
        <div style={{ ...unaLineaStyle, fontWeight: 700 }} title={mov.descripcion}>{mov.descripcion || '(sin descripción)'}</div>
        {detalle ? <div style={{ ...mutedStyle, ...unaLineaStyle }} title={detalle}>{detalle}</div> : null}
      </td>
      <td style={{
        ...celda(tdStyle, {}), textAlign: 'right', whiteSpace: 'nowrap', fontWeight: 700, fontVariantNumeric: 'tabular-nums',
        color: esCredito ? ESTADOS.conciliado.color : 'var(--vg-text-strong)',
      }}
      >
        {esCredito ? '+' : '−'} {formatMonto(mov.monto)}
      </td>
      <td style={celda({ ...tdStyle, minWidth: 220, maxWidth: 360 }, { gridColumn: '1 / -1' })}>
        <div style={{ display: 'grid', gap: 2 }}>
          <EstadoTexto
            estado={mov.estado}
            texto={pagoDividido ? 'Conciliado · pago dividido' : esPos ? 'POS · se concilia por lote' : undefined}
          />
          {pagoDividido ? (
            confirmados.map((v) => (
              <span key={v.id} style={{ ...unaLineaStyle, fontSize: 13 }} title={v.etiqueta}>
                {v.etiqueta} <span style={mutedStyle}>· Bs {formatMonto(v.monto_sistema)}</span>
              </span>
            ))
          ) : vinculo ? (
            <span style={{ ...unaLineaStyle, fontSize: 13 }} title={`${vinculo.etiqueta} · ${vinculo.metodo_texto}`}>{vinculo.etiqueta}</span>
          ) : mov.estado === 'ignorado' ? (
            <span style={mutedStyle}>{mov.motivo_ignorado}</span>
          ) : null}
          {aviso || avisoDivido ? <span style={avisoTextoStyle}>{aviso || avisoDivido}</span> : null}
        </div>
      </td>
      <td style={{ ...celda({ ...tdStyle, whiteSpace: 'nowrap', textAlign: 'right' }, { gridColumn: '1 / -1', paddingTop: 4 }) }}>
        <div style={{ display: 'flex', gap: 4, justifyContent: compacto ? 'flex-start' : 'flex-end', alignItems: 'center', flexWrap: 'wrap' }}>
          {!bloqueado && mov.estado === 'por_revisar' && sugerido ? (
            <>
              <button type="button" style={primaryChipStyle} disabled={ocupado} onClick={() => onConfirmar(sugerido)}>Confirmar</button>
              <button type="button" style={enlaceStyle} disabled={ocupado} onClick={() => onRechazar(sugerido)}>Rechazar</button>
              {mov.clase !== 'comision' ? <button type="button" style={enlaceStyle} disabled={ocupado} onClick={onBuscar}>Elegir otro</button> : null}
            </>
          ) : null}
          {!bloqueado && mov.estado === 'sin_coincidencia' ? (
            <>
              {mov.clase !== 'comision' ? <button type="button" style={chipStyle} disabled={ocupado} onClick={onBuscar}>Buscar</button> : null}
              <button type="button" style={enlaceStyle} disabled={ocupado} onClick={onIgnorar}>Ignorar</button>
            </>
          ) : null}
          {!bloqueado && (mov.estado === 'conciliado' || mov.estado === 'ignorado') ? (
            <button type="button" style={enlaceStyle} disabled={ocupado} onClick={onReabrir}>
              {mov.estado === 'ignorado' ? 'Reabrir' : 'Deshacer'}
            </button>
          ) : null}
        </div>
      </td>
    </tr>
  );
}

function TablaPos({ filas }) {
  return (
    <div style={{ display: 'grid', gap: 10 }}>
      <div style={mutedStyle}>Lo que el banco acreditó cada día por el punto de venta contra los lotes acreditados en el sistema.</div>
      {!filas || filas.length === 0 ? (
        <div style={emptyStyle}>No hay créditos de punto de venta ni lotes acreditados en este rango.</div>
      ) : (
        <div style={tablaScrollStyle}>
          <table style={tablaStyle}>
            <thead>
              <tr>
                <th style={thStyle}>Día de acreditación</th>
                <th style={{ ...thStyle, textAlign: 'right' }}>Banco (Bs)</th>
                <th style={{ ...thStyle, textAlign: 'right' }}>Sistema (Bs)</th>
                <th style={{ ...thStyle, textAlign: 'right' }}>Diferencia (Bs)</th>
                <th style={{ ...thStyle, textAlign: 'right' }}>%</th>
              </tr>
            </thead>
            <tbody>
              {filas.map((f) => (
                <tr key={f.fecha}>
                  <td style={tdStyle}>{formatFecha(f.fecha)}</td>
                  <td style={{ ...tdStyle, textAlign: 'right' }}>{formatMonto(f.banco)}</td>
                  <td style={{ ...tdStyle, textAlign: 'right' }}>{formatMonto(f.sistema)}</td>
                  <td style={{ ...tdStyle, textAlign: 'right' }}>{formatMonto(f.diferencia)}</td>
                  <td style={{ ...tdStyle, textAlign: 'right' }}>{f.porcentaje === null ? '—' : `${formatMonto(f.porcentaje)} %`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function TablaSistema({ filas }) {
  if (filas === null) return <div style={emptyStyle}>Buscando...</div>;
  return (
    <div style={{ display: 'grid', gap: 10 }}>
      <div style={mutedStyle}>Cobros y pagos del sistema que no aparecen en el banco: puede que aún no lleguen o que estén mal escritos.</div>
      {filas.length === 0 ? (
        <div style={emptyStyle}>Todo lo registrado en el sistema aparece en el banco.</div>
      ) : (
        <div style={tablaScrollStyle}>
          <table style={tablaStyle}>
            <thead>
              <tr>
                <th style={thStyle}>Fecha</th>
                <th style={thStyle}>Sentido</th>
                <th style={thStyle}>Registro del sistema</th>
                <th style={thStyle}>Referencia</th>
                <th style={{ ...thStyle, textAlign: 'right' }}>Monto (Bs)</th>
              </tr>
            </thead>
            <tbody>
              {filas.map((f) => (
                <tr key={`${f.tipo}-${f.id}`}>
                  <td style={tdStyle}>{formatFecha(f.fecha)}</td>
                  <td style={tdStyle}>{f.sentido === 'credito' ? 'Cobro' : 'Pago'}</td>
                  <td style={tdStyle}>{f.etiqueta}</td>
                  <td style={tdStyle}>{f.referencia || '—'}</td>
                  <td style={{ ...tdStyle, textAlign: 'right' }}>{formatMonto(f.monto)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const ESTADOS_DIA = {
  cerrado: { texto: 'Cerrado' },
  listo: { texto: 'Listo para cerrar' },
  pendiente: { texto: 'Con pendientes' },
  sin_movimientos: { texto: 'Sin movimientos' },
};
// El estado de un dia usa los mismos colores que el de un movimiento.
const ESTADO_A_COLOR = { cerrado: 'conciliado', listo: 'pendiente', pendiente: 'por_revisar', sin_movimientos: 'ignorado' };

function TablaCierres({ datos, onCerrar, onReabrir, onVer }) {
  if (!datos) return <div style={emptyStyle}>Cargando cierres...</div>;
  const { resumen, dias } = datos;
  return (
    <div style={{ display: 'grid', gap: 10 }}>
      <div style={mutedStyle}>
        Un día se cierra cuando todo está resuelto: queda guardado y bloqueado.
        {resumen.listos ? ` ${resumen.listos} listos para cerrar.` : ''}
        {resumen.sin_movimientos ? ` ${resumen.sin_movimientos} sin movimientos cargados.` : ''}
      </div>
      {resumen.discontinuidades > 0 ? (
        <div style={avisoStyle}>{resumen.discontinuidades} día(s) con saldo que no encadena con el anterior: puede faltar alguna línea del banco.</div>
      ) : null}
      <div style={tablaScrollStyle}>
        <table style={tablaStyle}>
          <thead>
            <tr>
              <th style={thStyle}>Día</th>
              <th style={thStyle}>Estado</th>
              <th style={{ ...thStyle, textAlign: 'right' }}>Entradas (Bs)</th>
              <th style={{ ...thStyle, textAlign: 'right' }}>Salidas (Bs)</th>
              <th style={{ ...thStyle, textAlign: 'right' }}>Saldo final (Bs)</th>
              <th style={thStyle}>Cierre</th>
              <th style={thStyle} />
            </tr>
          </thead>
          <tbody>
            {dias.map((d) => {
              const e = ESTADOS_DIA[d.estado];
              return (
                <tr key={d.fecha}>
                  <td style={{ ...tdStyle, whiteSpace: 'nowrap' }}>{formatFecha(d.fecha)}</td>
                  <td style={tdStyle}>
                    <div style={{ display: 'grid', gap: 2 }}>
                      <EstadoTexto estado={ESTADO_A_COLOR[d.estado]} texto={e.texto} />
                      <span style={mutedStyle}>
                        {d.total} {d.total === 1 ? 'movimiento' : 'movimientos'}{d.bloqueos ? ` · ${d.bloqueos} por resolver` : ''}
                        {d.reaperturas ? ` · reabierto ${d.reaperturas} ${d.reaperturas === 1 ? 'vez' : 'veces'}` : ''}
                      </span>
                    </div>
                  </td>
                  <td style={{ ...tdStyle, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{formatMonto(d.creditos)}</td>
                  <td style={{ ...tdStyle, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{formatMonto(d.debitos)}</td>
                  <td style={{ ...tdStyle, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                    {d.saldo_final === null ? '—' : formatMonto(d.saldo_final)}
                    {d.continuidad === false ? <div style={avisoTextoStyle}>No encadena con el día anterior</div> : null}
                  </td>
                  <td style={{ ...tdStyle, minWidth: 150 }} title={d.cierre?.nota || ''}>
                    {d.cierre ? (
                      <div style={{ display: 'grid', gap: 2 }}>
                        <span>{d.cierre.cerrado_por}</span>
                        <span style={mutedStyle}>{formatFechaHora(d.cierre.fecha_cierre)}</span>
                      </div>
                    ) : '—'}
                  </td>
                  <td style={{ ...tdStyle, whiteSpace: 'nowrap', textAlign: 'right' }}>
                    <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end', alignItems: 'center', flexWrap: 'wrap' }}>
                      {d.estado === 'listo' || d.estado === 'sin_movimientos' ? (
                        <button type="button" style={primaryChipStyle} onClick={() => onCerrar(d)}>Cerrar día</button>
                      ) : null}
                      {d.total > 0 ? <button type="button" style={enlaceStyle} onClick={() => onVer(d)}>Ver</button> : null}
                      {d.estado === 'cerrado' ? <button type="button" style={enlaceStyle} onClick={() => onReabrir(d)}>Reabrir</button> : null}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CerrarDiaModal({ dia, onCerrar, onConfirmar, onError }) {
  const [nota, setNota] = useState('');
  const [confirmo, setConfirmo] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const saltos = dia.saltos_saldo > 0;
  const noCuadra = dia.continuidad === false;
  const sinMovimientos = dia.total === 0;
  const pideNota = saltos || noCuadra || sinMovimientos;
  const diferenciaPos = Number(dia.pos_banco) - Number(dia.pos_sistema);

  const guardar = async () => {
    setGuardando(true);
    try {
      await onConfirmar(dia, nota.trim());
    } catch (e) {
      onError(e.message);
      setGuardando(false);
    }
  };

  return (
    <div style={backdropStyle} onClick={guardando ? undefined : onCerrar}>
      <div style={modalStyle(true)} onClick={(e) => e.stopPropagation()}>
        <div style={modalTituloStyle}>Cerrar el día {formatFecha(dia.fecha)}</div>
        <div style={mutedStyle}>Queda guardado que este día se concilió con el banco, y sus movimientos se bloquean.</div>
        <div style={previewStyle}>
          <div style={datosGridStyle}>
            <Dato etiqueta="Movimientos" valor={dia.total} />
            <Dato etiqueta="Conciliados" valor={dia.conciliados} />
            <Dato etiqueta="Ignorados" valor={dia.ignorados} />
            <Dato etiqueta="POS sin vincular" valor={dia.pendientes_pos} />
            <Dato etiqueta="Créditos (Bs)" valor={formatMonto(dia.creditos)} />
            <Dato etiqueta="Débitos (Bs)" valor={formatMonto(dia.debitos)} />
            <Dato etiqueta="Saldo final del banco (Bs)" valor={dia.saldo_final === null ? '—' : formatMonto(dia.saldo_final)} />
            <Dato etiqueta="Saldo vs. día anterior" valor={dia.continuidad === true ? 'Cuadra' : dia.continuidad === false ? 'No cuadra' : '—'} />
          </div>
        </div>
        {noCuadra ? (
          <div style={avisoStyle}>El saldo con que abre este día no coincide con el saldo con que cerró el último día cerrado: puede faltar alguna línea en el archivo.</div>
        ) : null}
        {saltos ? <div style={avisoStyle}>La columna Saldo tiene {dia.saltos_saldo} salto(s) dentro de este día: puede faltar alguna línea.</div> : null}
        {dia.registros_sin_banco > 0 ? (
          <div style={avisoStyle}>Hay {dia.registros_sin_banco} registro(s) del sistema ese día que no aparecen en el banco (pestaña "En el sistema, no en el banco").</div>
        ) : null}
        {dia.pos_banco !== '0.00' || dia.pos_sistema !== '0.00' ? (
          <div style={Math.abs(diferenciaPos) > 0.5 ? avisoStyle : infoStyle}>
            POS: el banco acreditó Bs {formatMonto(dia.pos_banco)} y el sistema acreditó Bs {formatMonto(dia.pos_sistema)} (diferencia Bs {formatMonto(diferenciaPos)}).
          </div>
        ) : null}
        <label style={campoStyle}>
          <span style={etiquetaStyle}>Nota{pideNota ? ' (obligatoria)' : ' (opcional)'}</span>
          <textarea
            rows={3}
            value={nota}
            onChange={(e) => setNota(e.target.value)}
            placeholder={pideNota ? 'Explica por qué se cierra así (ej. feriado sin movimientos, o falta una línea en el archivo)' : 'Ej: revisado con el estado de cuenta'}
            style={{ ...inputStyle, resize: 'vertical' }}
          />
        </label>
        <label style={checkStyle}>
          <input type="checkbox" checked={confirmo} onChange={(e) => setConfirmo(e.target.checked)} />
          Confirmo que revisé la conciliación de este día contra el extracto del banco
        </label>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, flexWrap: 'wrap' }}>
          <button type="button" style={secondaryButtonStyle} onClick={onCerrar} disabled={guardando}>Cancelar</button>
          <button type="button" style={primaryButtonStyle} onClick={guardar} disabled={!confirmo || guardando || (pideNota && !nota.trim())}>
            {guardando ? 'Cerrando...' : 'Cerrar día'}
          </button>
        </div>
      </div>
    </div>
  );
}

function ReabrirModal({ dia, onCerrar, onConfirmar, onError }) {
  const [motivo, setMotivo] = useState('');
  const [guardando, setGuardando] = useState(false);

  const guardar = async () => {
    setGuardando(true);
    try {
      await onConfirmar(dia, motivo.trim());
    } catch (e) {
      onError(e.message);
      setGuardando(false);
    }
  };

  return (
    <div style={backdropStyle} onClick={guardando ? undefined : onCerrar}>
      <div style={modalStyle(false)} onClick={(e) => e.stopPropagation()}>
        <div style={modalTituloStyle}>Reabrir el día {formatFecha(dia.fecha)}</div>
        <div style={mutedStyle}>
          El día vuelve a admitir cambios y quedará registrado quién lo reabrió y por qué. Después hay que cerrarlo de nuevo.
        </div>
        <label style={campoStyle}>
          <span style={etiquetaStyle}>Motivo</span>
          <textarea
            rows={3}
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder="Ej: faltaba una línea del banco"
            style={{ ...inputStyle, resize: 'vertical' }}
          />
        </label>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <button type="button" style={secondaryButtonStyle} onClick={onCerrar} disabled={guardando}>Cancelar</button>
          <button type="button" style={primaryButtonStyle} onClick={guardar} disabled={!motivo.trim() || guardando}>
            {guardando ? 'Reabriendo...' : 'Reabrir día'}
          </button>
        </div>
      </div>
    </div>
  );
}

function ImportarModal({ cuenta, onCerrar, onImportado, onError }) {
  const [archivo, setArchivo] = useState(null);
  const [vista, setVista] = useState(null);
  const [leyendo, setLeyendo] = useState(false);
  const [guardando, setGuardando] = useState(false);

  const enviar = (accion, file) => {
    const formData = new FormData();
    formData.append('action', accion);
    formData.append('cuenta', cuenta);
    formData.append('archivo', file);
    return llamar(`${API}importar/`, { method: 'POST', formData });
  };

  const elegir = async (file) => {
    setArchivo(file);
    setVista(null);
    if (!file) return;
    setLeyendo(true);
    try {
      setVista((await enviar('preview', file)).resumen);
    } catch (e) {
      onError(e.message);
      setArchivo(null);
    } finally {
      setLeyendo(false);
    }
  };

  const importar = async () => {
    setGuardando(true);
    try {
      onImportado(await enviar('confirm', archivo));
    } catch (e) {
      onError(e.message);
      setGuardando(false);
    }
  };

  return (
    <div style={backdropStyle} onClick={guardando ? undefined : onCerrar}>
      <div style={modalStyle(true)} onClick={(e) => e.stopPropagation()}>
        <div style={modalTituloStyle}>Importar extracto del banco</div>
        <div style={mutedStyle}>
          <strong style={{ color: 'var(--vg-text-strong)' }}>{cuenta}</strong> · Sube un día, un rango o el mes: lo ya cargado se omite solo.
        </div>
        <input
          type="file"
          accept=".xlsx,.csv"
          onChange={(e) => elegir(e.target.files?.[0] || null)}
          disabled={leyendo || guardando}
          style={inputStyle}
        />
        {leyendo ? <div style={emptyStyle}>Leyendo el archivo...</div> : null}
        {vista ? (
          <div style={previewStyle}>
            <div style={previewTituloStyle}>Vista previa · {vista.archivo}</div>
            <div style={datosGridStyle}>
              <Dato etiqueta="Movimientos leídos" valor={vista.leidos} />
              <Dato etiqueta="Nuevos" valor={vista.nuevos} />
              <Dato etiqueta="Ya cargados" valor={vista.ya_cargados} />
              <Dato etiqueta="Período" valor={`${formatFecha(vista.desde)} al ${formatFecha(vista.hasta)}`} />
              <Dato etiqueta="Créditos (Bs)" valor={formatMonto(vista.creditos)} />
              <Dato etiqueta="Débitos (Bs)" valor={formatMonto(vista.debitos)} />
            </div>
            {vista.saltos_saldo > 0 ? (
              <div style={avisoStyle}>
                La columna Saldo tiene {vista.saltos_saldo} salto(s): puede faltar alguna línea en el archivo. Conviene revisar que esté completo.
              </div>
            ) : null}
            {vista.total_errores > 0 ? (
              <div style={avisoStyle}>
                {vista.total_errores} fila(s) no se pudieron leer y se omitirán
                {vista.errores.slice(0, 3).map((e) => ` · hoja ${e.hoja}, fila ${e.fila}: ${e.motivo}`).join('')}
              </div>
            ) : null}
            {vista.hojas_omitidas.length > 0 ? (
              <div style={infoStyle}>Hojas sin movimientos (se ignoran): {vista.hojas_omitidas.join(', ')}</div>
            ) : null}
            {vista.en_dias_cerrados?.cantidad > 0 ? (
              <div style={avisoStyle}>
                {vista.en_dias_cerrados.cantidad} línea(s) nueva(s) caen en días ya cerrados ({vista.en_dias_cerrados.dias.map(formatFecha).join(', ')})
                y NO se importarán. Si necesitas agregarlas, reabre el cierre de ese día en "Cierres por día".
              </div>
            ) : null}
            {vista.nuevos === 0 ? <div style={infoStyle}>Todos los movimientos de este archivo ya estaban cargados.</div> : null}
          </div>
        ) : null}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, flexWrap: 'wrap' }}>
          <button type="button" style={secondaryButtonStyle} onClick={onCerrar} disabled={guardando}>Cancelar</button>
          <button type="button" style={primaryButtonStyle} onClick={importar} disabled={!vista || guardando}>
            {guardando ? 'Importando y cruzando...' : 'Importar y conciliar'}
          </button>
        </div>
      </div>
    </div>
  );
}

function Dato({ etiqueta, valor }) {
  return (
    <div style={{ display: 'grid', gap: 2 }}>
      <span style={mutedStyle}>{etiqueta}</span>
      <strong style={{ color: 'var(--vg-text-strong)' }}>{valor}</strong>
    </div>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 14, padding: isMobile ? 6 : 10 });
const headerRowStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap' };
const titleStyle = (isMobile) => ({ margin: 0, color: 'var(--vg-text-strong)', fontSize: isMobile ? 26 : 32 });
const mutedStyle = { color: 'var(--vg-f-c8bbbb)', fontSize: 12.5 };
const backButtonStyle = { justifySelf: 'start', border: '1px solid rgba(var(--vg-ink), 0.16)', borderRadius: 999, padding: '8px 14px', background: 'rgba(var(--vg-ink), 0.05)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer' };
const panelStyle = { display: 'grid', gap: 10, padding: 12, borderRadius: 16, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'rgba(var(--vg-ink), 0.03)' };
const controlesStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'minmax(220px, 320px) 1fr', gap: 14, alignItems: 'end' });
const accionesStyle = { display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' };
const checkStyle = { display: 'flex', alignItems: 'center', gap: 6, color: 'var(--vg-f-d2c3c3)', fontSize: 13, cursor: 'pointer' };
const campoStyle = { display: 'grid', gap: 4, alignContent: 'start' };
const etiquetaStyle = { color: 'var(--vg-f-d2c3c3)', fontSize: 12.5, fontWeight: 700 };
const inputStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.16)', background: 'var(--vg-s-161010)', padding: '10px 12px', color: 'var(--vg-text-strong)', fontSize: 14 };
const noticeStyle = { padding: '12px 14px', borderRadius: 12, border: '1px solid var(--vg-f-ff9191-a220)', background: 'rgba(255, 98, 98, 0.12)', color: 'var(--vg-f-ffd8d8)' };
const avisoStyle = { padding: '8px 12px', borderRadius: 10, border: '1px solid var(--vg-f-ffcf7d-a450)', background: 'rgba(255, 207, 125, 0.08)', color: 'var(--vg-f-ffe3a3)', fontSize: 13 };
const avisoTextoStyle = { color: 'var(--vg-f-ffe3a3)', fontSize: 12 };
const infoStyle = { padding: '8px 12px', borderRadius: 10, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'rgba(var(--vg-ink), 0.04)', color: 'var(--vg-f-d2c3c3)', fontSize: 13 };
const previewStyle = { display: 'grid', gap: 10, padding: 12, borderRadius: 14, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'rgba(var(--vg-ink), 0.03)' };
const previewTituloStyle = { color: 'var(--vg-f-ffb0b0)', fontSize: 11.5, fontWeight: 800 };
const datosGridStyle = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 10 };
// Resumen en una sola franja (una sola caja con divisores, no cinco tarjetas sueltas).
const resumenStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? 'repeat(2, minmax(0, 1fr))' : 'repeat(5, minmax(0, 1fr))', gap: 1, borderRadius: 16, overflow: 'hidden', border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'rgba(var(--vg-ink), 0.1)' });
const cifraStyle = { display: 'grid', gap: 3, alignContent: 'start', textAlign: 'left', padding: '12px 14px', border: 'none', background: 'var(--vg-s-161010)', color: 'var(--vg-text-strong)', font: 'inherit' };
const cifraValorStyle = { fontSize: 22, fontWeight: 800, fontVariantNumeric: 'tabular-nums' };
const cifraNotaStyle = { color: 'var(--vg-f-c8bbbb)', fontSize: 12.5, fontVariantNumeric: 'tabular-nums' };
const barraPistaStyle = { display: 'block', height: 4, borderRadius: 999, background: 'rgba(var(--vg-ink), 0.12)', overflow: 'hidden' };
const barraRellenoStyle = { display: 'block', height: '100%', borderRadius: 999, background: 'var(--vg-f-9fe3b0)' };
const unaLineaStyle = { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' };
const enlaceStyle = { border: 'none', background: 'none', padding: '4px 6px', color: 'var(--vg-f-d2c3c3)', fontSize: 12.5, fontWeight: 600, cursor: 'pointer', textDecoration: 'underline', textUnderlineOffset: 3 };
const diaEncabezadoStyle = { padding: '16px 8px 6px', borderBottom: '1px solid rgba(var(--vg-ink), 0.12)' };
const pestanasStyle = { display: 'flex', gap: 4, flexWrap: 'wrap', borderBottom: '1px solid rgba(var(--vg-ink), 0.12)' };
const pestanaStyle = { border: 'none', borderBottom: '2px solid transparent', marginBottom: -1, padding: '8px 12px', background: 'none', color: 'var(--vg-f-c8bbbb)', fontWeight: 600, cursor: 'pointer', fontSize: 13.5 };
const pestanaActivaStyle = { ...pestanaStyle, color: 'var(--vg-text-strong)', fontWeight: 800, borderBottomColor: 'var(--vg-accent-primary)' };
const tablaScrollStyle = { overflowX: 'auto' };
const tablaStyle = { width: '100%', borderCollapse: 'collapse', fontSize: 13 };
const thStyle = { textAlign: 'left', padding: '6px 8px', color: 'var(--vg-f-c8bbbb)', fontSize: 11.5, fontWeight: 700, borderBottom: '1px solid rgba(var(--vg-ink), 0.12)' };
const tdStyle = { padding: '9px 8px', borderBottom: '1px solid rgba(var(--vg-ink), 0.06)', color: 'var(--vg-text-strong)', verticalAlign: 'middle' };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '11px 20px', background: 'linear-gradient(90deg, #bf1f1f 0%, var(--vg-accent-primary) 100%)', color: '#fff', fontWeight: 800, cursor: 'pointer' };
const secondaryButtonStyle = { border: '1px solid rgba(var(--vg-ink), 0.16)', borderRadius: 999, padding: '10px 16px', background: 'rgba(var(--vg-ink), 0.05)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer' };
const chipStyle = { border: '1px solid rgba(var(--vg-ink), 0.16)', borderRadius: 999, padding: '5px 11px', background: 'rgba(var(--vg-ink), 0.05)', color: 'var(--vg-text-strong)', fontWeight: 700, fontSize: 12, cursor: 'pointer' };
const primaryChipStyle = { ...chipStyle, border: '1px solid rgba(46, 204, 113, 0.6)', background: 'rgba(46, 204, 113, 0.16)' };
const emptyStyle = { minHeight: 80, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(var(--vg-ink), 0.14)', color: 'var(--vg-f-c8bbbb)', textAlign: 'center', padding: 14 };
const candidatoStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, padding: '10px 12px', borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.1)', background: 'rgba(var(--vg-ink), 0.03)' };
const backdropStyle = { position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0, 0, 0, 0.6)', display: 'grid', placeItems: 'center', padding: 16, overflowY: 'auto' };
const modalStyle = (ancho) => ({ width: '100%', maxWidth: ancho ? 640 : 440, maxHeight: '90vh', overflowY: 'auto', borderRadius: 20, border: '1px solid var(--vg-f-ff9191-a300)', background: 'linear-gradient(180deg, var(--vg-s-1c0c0c-a980) 0%, var(--vg-s-0a0808-a990) 100%)', padding: '22px 22px 18px', boxShadow: '0 20px 50px rgba(0, 0, 0, calc(0.45 * var(--vg-shadow-k)))', display: 'grid', gap: 12 });
const modalTituloStyle = { color: 'var(--vg-text-strong)', fontSize: 19, fontWeight: 800 };

export default ConciliacionMovimientosPage;

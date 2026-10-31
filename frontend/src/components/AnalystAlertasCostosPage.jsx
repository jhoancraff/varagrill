import { useCallback, useEffect, useState } from 'react';

// Alertas de precio de ingredientes: cada vez que el costo de un ingrediente cambia más que el umbral configurado
// (Configuración de costeo) queda una alerta con el costo anterior y el nuevo, de dónde vino el cambio y qué recetas
// cambian de costo por eso. Sirve para notar a tiempo un precio mal cargado. También se ve el historial completo de
// cambios de costo. Se abre desde "Alertas de precios" en AnalystInventoryHubPage (ruta 'admin-alertas-costos').
const PESTANAS = [
  { id: 'pendientes', label: 'Pendientes', vista: 'alertas', estado: 'pendientes' },
  { id: 'revisadas', label: 'Revisadas', vista: 'alertas', estado: 'revisadas' },
  { id: 'historial', label: 'Historial de cambios', vista: 'historial', estado: 'todas' },
];

const formatoCosto = (valor) => {
  const numero = Number(valor);
  if (!Number.isFinite(numero)) return valor;
  return `$${numero.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 6 })}`;
};

const formatoMonto = (valor) => `$${Number(valor || 0).toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const formatoFecha = (iso) => (iso
  ? new Date(iso).toLocaleString('es-VE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
  : '');

const formatoVariacion = (valor) => {
  if (valor === null || valor === undefined) return 'nuevo';
  const numero = Number(valor);
  return `${numero > 0 ? '+' : ''}${numero.toLocaleString('es-VE', { maximumFractionDigits: 2 })} %`;
};

function getCookie(name) {
  const partes = `; ${document.cookie}`.split(`; ${name}=`);
  return partes.length === 2 ? partes.pop().split(';').shift() : '';
}

function AnalystAlertasCostosPage({ isMobile, onBack, onEditIngredient }) {
  const [pestana, setPestana] = useState('pendientes');
  const [datos, setDatos] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState('');
  const [aviso, setAviso] = useState('');
  const [revisando, setRevisando] = useState(null);
  const [nota, setNota] = useState('');
  const [guardando, setGuardando] = useState(false);

  const cargar = useCallback(async () => {
    const definicion = PESTANAS.find((item) => item.id === pestana);
    setCargando(true);
    setError('');
    try {
      const respuesta = await fetch(
        `/api/admin/alertas-costos/?vista=${definicion.vista}&estado=${definicion.estado}`,
        { credentials: 'include', cache: 'no-store' },
      );
      const json = await respuesta.json().catch(() => ({}));
      if (!respuesta.ok || !json.ok) throw new Error(json.message || 'No se pudieron cargar las alertas.');
      setDatos(json);
    } catch (e) {
      setError(e.message);
    } finally {
      setCargando(false);
    }
  }, [pestana]);

  useEffect(() => { cargar(); }, [cargar]);

  const abrirRevision = (alerta) => {
    setRevisando(alerta.id);
    setNota('');
    setAviso('');
  };

  const confirmarRevision = async (alerta) => {
    setGuardando(true);
    setError('');
    try {
      const respuesta = await fetch(`/api/admin/alertas-costos/${alerta.id}/revisar/`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') || '' },
        body: JSON.stringify({ nota: nota.trim() }),
      });
      const json = await respuesta.json().catch(() => ({}));
      if (!respuesta.ok || !json.ok) throw new Error(json.message || 'No se pudo marcar como revisada.');
      setRevisando(null);
      setAviso(`Alerta de ${alerta.ingrediente.nombre} marcada como revisada.`);
      await cargar();
    } catch (e) {
      setError(e.message);
    } finally {
      setGuardando(false);
    }
  };

  const items = datos?.items || [];
  const esHistorial = pestana === 'historial';

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>← Volver a Inventario</button>

      <div>
        <h2 style={titleStyle(isMobile)}>Alertas de precios</h2>
        <p style={subtitleStyle}>
          Avisa cuando el costo de un ingrediente cambia más de {datos ? Number(datos.umbral_pct) : 30} %
          (se configura en Configuración de costeo) y muestra qué recetas cambian de costo por eso.
        </p>
      </div>

      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {PESTANAS.map((item) => (
          <button key={item.id} type="button" onClick={() => { setPestana(item.id); setRevisando(null); setAviso(''); }} style={pestanaStyle(pestana === item.id)}>
            {item.label}
            {item.id === 'pendientes' && datos && datos.pendientes > 0 ? <span style={contadorStyle}>{datos.pendientes}</span> : null}
          </button>
        ))}
      </div>

      {aviso ? <div style={avisoStyle}>{aviso}</div> : null}
      {error ? <div style={errorStyle}>{error}</div> : null}
      {cargando ? <div style={vacioStyle}>Cargando...</div> : null}
      {!cargando && !error && items.length === 0 ? (
        <div style={vacioStyle}>
          {pestana === 'pendientes' ? 'No hay alertas pendientes. Todos los cambios de precio están dentro del umbral.' : 'No hay registros.'}
        </div>
      ) : null}

      <div style={{ display: 'grid', gap: 12 }}>
        {items.map((fila) => (
          <article key={fila.id} style={tarjetaStyle(fila.es_alerta && !fila.revisada)}>
            <div style={filaTituloStyle}>
              <div style={{ display: 'grid', gap: 2 }}>
                <div style={nombreStyle}>{fila.ingrediente.nombre}</div>
                <div style={metaStyle}>
                  {formatoFecha(fila.fecha)} · {fila.origen || 'Otro'}{fila.usuario ? ` · ${fila.usuario}` : ''}
                  {fila.compra_id ? ` · Compra #${fila.compra_id}` : ''}
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={cambioStyle}>
                  {formatoCosto(fila.costo_anterior)} → {formatoCosto(fila.costo_nuevo)} <span style={{ color: 'var(--vg-f-c8bbbb)', fontSize: 12 }}>por {fila.ingrediente.unidad}</span>
                </div>
                <div style={variacionStyle(fila.es_alerta, Number(fila.variacion_pct) > 0)}>{formatoVariacion(fila.variacion_pct)}</div>
              </div>
            </div>

            {!esHistorial && (fila.recetas_afectadas || []).length > 0 ? (
              <div style={recetasBoxStyle}>
                <div style={{ fontWeight: 800, fontSize: 12.5, color: 'var(--vg-text-strong)' }}>Recetas que cambian de costo</div>
                {fila.recetas_afectadas.map((receta) => (
                  <div key={receta.id} style={recetaRowStyle}>
                    <span>{receta.nombre}</span>
                    <span style={{ fontWeight: 700 }}>{formatoMonto(receta.costo_antes)} → {formatoMonto(receta.costo_despues)}</span>
                  </div>
                ))}
                {fila.recetas_afectadas_mas > 0 ? <div style={metaStyle}>y {fila.recetas_afectadas_mas} más</div> : null}
              </div>
            ) : null}

            {fila.revisada ? (
              <div style={metaStyle}>
                Revisada el {formatoFecha(fila.fecha_revision)}{fila.revisada_por ? ` por ${fila.revisada_por}` : ''}
                {fila.nota_revision ? `: ${fila.nota_revision}` : ''}
              </div>
            ) : null}
            {esHistorial && fila.es_alerta && !fila.revisada ? <div style={{ ...metaStyle, color: 'var(--vg-f-ffcf7d)' }}>Alerta pendiente de revisión</div> : null}

            {!esHistorial && !fila.revisada ? (
              revisando === fila.id ? (
                <div style={{ display: 'grid', gap: 8 }}>
                  <input value={nota} onChange={(e) => setNota(e.target.value)} placeholder="Nota (opcional): ej. precio correcto, o ya lo corregí" style={inputStyle} maxLength={255} />
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <button type="button" onClick={() => confirmarRevision(fila)} disabled={guardando} style={primarioStyle}>{guardando ? 'Guardando...' : 'Marcar como revisada'}</button>
                    <button type="button" onClick={() => setRevisando(null)} disabled={guardando} style={secundarioStyle}>Cancelar</button>
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {onEditIngredient ? <button type="button" onClick={() => onEditIngredient(fila.ingrediente.id)} style={secundarioStyle}>Corregir el ingrediente</button> : null}
                  <button type="button" onClick={() => abrirRevision(fila)} style={primarioStyle}>Revisada</button>
                </div>
              )
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10, maxWidth: 960 });
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const titleStyle = (isMobile) => ({ margin: 0, color: 'var(--vg-text-strong)', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: 'var(--vg-f-d2c3c3)', maxWidth: 700, lineHeight: 1.6 };
const pestanaStyle = (activa) => ({ display: 'inline-flex', alignItems: 'center', gap: 8, border: `1px solid ${activa ? 'var(--vg-f-ff9191-a300)' : 'rgba(var(--vg-ink), 0.14)'}`, borderRadius: 999, padding: '9px 16px', background: activa ? 'rgba(255, 98, 98, 0.14)' : 'rgba(var(--vg-ink), 0.04)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer', fontSize: 13.5 });
const contadorStyle = { minWidth: 20, height: 20, padding: '0 6px', borderRadius: 999, background: '#d81d1d', color: '#fff', fontSize: 12, fontWeight: 800, display: 'inline-grid', placeItems: 'center' };
const tarjetaStyle = (pendiente) => ({ display: 'grid', gap: 10, padding: 16, borderRadius: 18, border: `1px solid ${pendiente ? 'var(--vg-f-ffcf7d-a450)' : 'rgba(var(--vg-ink), 0.1)'}`, background: 'linear-gradient(180deg, var(--vg-bg-card) 0%, var(--vg-s-080808-a980) 100%)' });
const filaTituloStyle = { display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'flex-start' };
const nombreStyle = { color: 'var(--vg-text-strong)', fontWeight: 800, fontSize: 16 };
const metaStyle = { color: 'var(--vg-f-c8bbbb)', fontSize: 12.5 };
const cambioStyle = { color: 'var(--vg-text-strong)', fontWeight: 800, fontSize: 15 };
const variacionStyle = (alerta, sube) => ({ color: !alerta ? 'var(--vg-f-c8bbbb)' : sube ? 'var(--vg-f-ff9d9d)' : 'var(--vg-f-8fffb0)', fontWeight: 800, fontSize: 14 });
const recetasBoxStyle = { display: 'grid', gap: 4, padding: '10px 12px', borderRadius: 12, border: '1px solid rgba(var(--vg-ink), 0.12)', background: 'rgba(var(--vg-ink), 0.04)' };
const recetaRowStyle = { display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 13, color: 'var(--vg-f-d2c4c4)' };
const inputStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 10, border: '1px solid rgba(var(--vg-ink), 0.14)', background: 'var(--vg-s-161010)', padding: '9px 10px', color: 'var(--vg-text-strong)', fontSize: 13 };
const primarioStyle = { border: 'none', borderRadius: 999, padding: '9px 18px', background: 'linear-gradient(90deg, #d81d1d 0%, #ff5252 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: 13 };
const secundarioStyle = { border: '1px solid rgba(var(--vg-ink), 0.14)', borderRadius: 999, padding: '9px 16px', background: 'rgba(var(--vg-ink), 0.04)', color: 'var(--vg-text-strong)', fontWeight: 700, cursor: 'pointer', fontSize: 13 };
const vacioStyle = { minHeight: 80, display: 'grid', placeItems: 'center', textAlign: 'center', padding: 12, borderRadius: 14, border: '1px dashed rgba(var(--vg-ink), 0.12)', color: 'var(--vg-f-c8bbbb)' };
const avisoStyle = { padding: '10px 12px', borderRadius: 12, border: '1px solid rgba(143, 255, 176, 0.35)', background: 'rgba(143, 255, 176, 0.08)', color: 'var(--vg-f-8fffb0)', fontSize: 13 };
const errorStyle = { padding: '10px 12px', borderRadius: 12, border: '1px solid var(--vg-f-ff9191-a220)', background: 'rgba(255, 98, 98, 0.12)', color: 'var(--vg-f-ffd8d8)', fontSize: 13 };

export default AnalystAlertasCostosPage;

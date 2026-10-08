import './FiltroFechas.css';

const DIAS_SEMANA = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'];
const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

export function toIso(date) {
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60000);
  return local.toISOString().slice(0, 10);
}

export function todayIso() {
  return toIso(new Date());
}

function parseIso(value) {
  const [year, month, day] = String(value || '').split('-').map(Number);
  if (!year || !month || !day) return null;
  return new Date(year, month - 1, day);
}

function shiftIso(value, days) {
  const date = parseIso(value);
  if (!date) return value;
  date.setDate(date.getDate() + days);
  return toIso(date);
}

function formatFecha(value) {
  const date = parseIso(value);
  if (!date) return 'Elegir fecha';
  return `${DIAS_SEMANA[date.getDay()]} ${date.getDate()} ${MESES[date.getMonth()]} ${date.getFullYear()}`;
}

function diasEntre(desde, hasta) {
  const a = parseIso(desde);
  const b = parseIso(hasta);
  if (!a || !b) return 0;
  return Math.round((b - a) / 86400000) + 1;
}

function rangoPreset(clave) {
  const hoy = new Date();
  if (clave === 'hoy') return { desde: toIso(hoy), hasta: toIso(hoy) };
  if (clave === 'ayer') {
    const ayer = new Date(hoy);
    ayer.setDate(hoy.getDate() - 1);
    return { desde: toIso(ayer), hasta: toIso(ayer) };
  }
  if (clave === 'semana') {
    const lunes = new Date(hoy);
    lunes.setDate(hoy.getDate() - (hoy.getDay() === 0 ? 6 : hoy.getDay() - 1));
    return { desde: toIso(lunes), hasta: toIso(hoy) };
  }
  if (clave === '7dias') {
    const inicio = new Date(hoy);
    inicio.setDate(hoy.getDate() - 6);
    return { desde: toIso(inicio), hasta: toIso(hoy) };
  }
  if (clave === 'mes') {
    return { desde: toIso(new Date(hoy.getFullYear(), hoy.getMonth(), 1)), hasta: toIso(hoy) };
  }
  if (clave === 'mes_pasado') {
    return {
      desde: toIso(new Date(hoy.getFullYear(), hoy.getMonth() - 1, 1)),
      hasta: toIso(new Date(hoy.getFullYear(), hoy.getMonth(), 0)),
    };
  }
  return { desde: toIso(new Date(hoy.getFullYear(), 0, 1)), hasta: toIso(hoy) };
}

const PRESETS = [
  { clave: 'hoy', label: 'Hoy' },
  { clave: 'ayer', label: 'Ayer' },
  { clave: 'semana', label: 'Esta semana' },
  { clave: '7dias', label: 'Últimos 7 días' },
  { clave: 'mes', label: 'Este mes' },
  { clave: 'mes_pasado', label: 'Mes pasado' },
];

function IconoCalendario() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3.5" y="5" width="17" height="15.5" rx="3" />
      <path d="M3.5 10h17M8 3v4M16 3v4" />
    </svg>
  );
}

// Casilla de una fecha: toda el area abre el calendario del navegador. El
// <input type="date"> real queda encima, invisible, para que el clic, el teclado
// y el selector nativo del celular funcionen sin codigo extra.
function CasillaFecha({ etiqueta, value, onChange, min, max }) {
  const abrir = (event) => {
    try {
      if (typeof event.currentTarget.showPicker === 'function') event.currentTarget.showPicker();
    } catch {
      // El navegador abre el calendario por su cuenta.
    }
  };

  return (
    <label className="vg-fecha">
      <span className="vg-fecha__icono"><IconoCalendario /></span>
      <span className="vg-fecha__texto">
        <span className="vg-fecha__etiqueta">{etiqueta}</span>
        <span className="vg-fecha__valor">{formatFecha(value)}</span>
      </span>
      <input
        type="date"
        className="vg-fecha__nativo"
        value={value || ''}
        min={min || undefined}
        max={max || undefined}
        aria-label={`${etiqueta}: ${formatFecha(value)}`}
        onClick={abrir}
        onChange={(event) => {
          if (event.target.value) onChange(event.target.value);
        }}
      />
    </label>
  );
}

// Filtro de rango: dos fechas + atajos. `max` por defecto es hoy; pasar null para
// permitir fechas futuras.
export function RangoFechas({ desde, hasta, onChange, max, presets = true, children }) {
  const tope = max === undefined ? todayIso() : max;

  const cambiarDesde = (nueva) => {
    onChange({ desde: nueva, hasta: nueva > hasta ? nueva : hasta });
  };
  const cambiarHasta = (nueva) => {
    onChange({ desde: nueva < desde ? nueva : desde, hasta: nueva });
  };

  const dias = diasEntre(desde, hasta);

  return (
    <div className="vg-rango no-print">
      <div className="vg-rango__fechas">
        <CasillaFecha etiqueta="Desde" value={desde} onChange={cambiarDesde} max={hasta && tope && hasta < tope ? hasta : tope} />
        <span className="vg-rango__union" aria-hidden="true" />
        <CasillaFecha etiqueta="Hasta" value={hasta} onChange={cambiarHasta} min={desde} max={tope} />
        {dias > 0 ? (
          <span className="vg-rango__dias">{dias === 1 ? '1 día' : `${dias} días`}</span>
        ) : null}
      </div>
      {presets ? (
        <div className="vg-rango__atajos" role="group" aria-label="Atajos de fechas">
          {PRESETS.map((preset) => {
            const rango = rangoPreset(preset.clave);
            const activo = rango.desde === desde && rango.hasta === hasta;
            return (
              <button
                key={preset.clave}
                type="button"
                className={`vg-atajo${activo ? ' vg-atajo--activo' : ''}`}
                aria-pressed={activo}
                onClick={() => onChange(rango)}
              >
                {preset.label}
              </button>
            );
          })}
        </div>
      ) : null}
      {children}
    </div>
  );
}

// Filtro de un solo dia: casilla + flechas para ir al dia anterior/siguiente + "Hoy".
export function DiaFecha({ value, onChange, max, etiqueta = 'Fecha' }) {
  const tope = max === undefined ? todayIso() : max;
  const esHoy = value === todayIso();
  const puedeAvanzar = !tope || value < tope;

  return (
    <div className="vg-dia no-print">
      <button type="button" className="vg-dia__flecha" aria-label="Día anterior" onClick={() => onChange(shiftIso(value, -1))}>
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M15 5l-7 7 7 7" /></svg>
      </button>
      <CasillaFecha etiqueta={etiqueta} value={value} onChange={onChange} max={tope} />
      <button type="button" className="vg-dia__flecha" aria-label="Día siguiente" disabled={!puedeAvanzar} onClick={() => onChange(shiftIso(value, 1))}>
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M9 5l7 7-7 7" /></svg>
      </button>
      <button
        type="button"
        className={`vg-atajo${esHoy ? ' vg-atajo--activo' : ''}`}
        aria-pressed={esHoy}
        onClick={() => onChange(todayIso())}
      >
        Hoy
      </button>
    </div>
  );
}

export default RangoFechas;

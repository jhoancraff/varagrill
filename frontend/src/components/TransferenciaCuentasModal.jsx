import { useEffect, useMemo, useState } from 'react';
import useMobileBackHandler from '../hooks/useMobileBackHandler';
import useToast from '../hooks/useToast';
import Toast from './Toast';

function formatMonto(value) {
  const number = Number(value || 0);
  return number.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatSaldoCuenta(cuenta) {
  if (!cuenta) return null;
  if (cuenta.moneda === 'VES') {
    return cuenta.saldo_disponible_bs !== null && cuenta.saldo_disponible_bs !== undefined
      ? `Bs. ${formatMonto(cuenta.saldo_disponible_bs)}`
      : `$${formatMonto(cuenta.saldo_disponible)}`;
  }
  return `$${formatMonto(cuenta.saldo_disponible)}`;
}

function TransferenciaCuentasModal({ open, onClose, fechaInicial, onSuccess }) {
  useMobileBackHandler(open, onClose);

  const [fecha, setFecha] = useState(fechaInicial);
  const [metodos, setMetodos] = useState([]);
  const [cargandoMetodos, setCargandoMetodos] = useState(true);
  const [disponibilidad, setDisponibilidad] = useState({});
  const [cargandoDisponibilidad, setCargandoDisponibilidad] = useState(false);

  const [cuentaOrigenId, setCuentaOrigenId] = useState('');
  const [cuentaDestinoId, setCuentaDestinoId] = useState('');
  const [montoUnico, setMontoUnico] = useState('');
  const [montoOrigen, setMontoOrigen] = useState('');
  const [montoDestino, setMontoDestino] = useState('');
  const [montoDestinoTocado, setMontoDestinoTocado] = useState(false);
  const [tasaCambio, setTasaCambio] = useState('');
  const [referencia, setReferencia] = useState('');
  const [concepto, setConcepto] = useState('');
  const [enviando, setEnviando] = useState(false);

  const { toast, showError, hideToast } = useToast();

  // Reinicia el formulario cada vez que se abre — un modal reusado no debe
  // arrastrar los datos de la transferencia anterior.
  useEffect(() => {
    if (!open) return;
    setFecha(fechaInicial);
    setCuentaOrigenId('');
    setCuentaDestinoId('');
    setMontoUnico('');
    setMontoOrigen('');
    setMontoDestino('');
    setMontoDestinoTocado(false);
    setTasaCambio('');
    setReferencia('');
    setConcepto('');
    hideToast();
  }, [open, fechaInicial]);

  useEffect(() => {
    if (!open) return;
    let cancelado = false;
    setCargandoMetodos(true);
    fetch('/api/metodos-pago/', { credentials: 'include', cache: 'no-store' })
      .then((response) => response.json())
      .then((json) => {
        if (!cancelado && json.ok) {
          setMetodos(Array.isArray(json.metodos_pago) ? json.metodos_pago : []);
        }
      })
      .finally(() => {
        if (!cancelado) setCargandoMetodos(false);
      });
    return () => {
      cancelado = true;
    };
  }, [open]);

  // El saldo disponible de cada cuenta depende de la FECHA elegida para el
  // movimiento — se vuelve a pedir cada vez que cambia, para que el badge
  // muestre lo disponible EN ESA fecha, no un total generico de hoy.
  useEffect(() => {
    if (!open || !fecha) return;
    let cancelado = false;
    setCargandoDisponibilidad(true);
    fetch(`/api/admin/reportes/disponibilidad-cuentas/?fecha=${fecha}`, { credentials: 'include', cache: 'no-store' })
      .then((response) => response.json())
      .then((json) => {
        if (!cancelado && json.ok) {
          const mapa = {};
          (json.cuentas || []).forEach((cuenta) => {
            mapa[cuenta.id] = cuenta;
          });
          setDisponibilidad(mapa);
        }
      })
      .finally(() => {
        if (!cancelado) setCargandoDisponibilidad(false);
      });
    return () => {
      cancelado = true;
    };
  }, [open, fecha]);

  const cuentaOrigen = useMemo(
    () => metodos.find((metodo) => String(metodo.id) === String(cuentaOrigenId)) || null,
    [metodos, cuentaOrigenId],
  );
  const cuentaDestino = useMemo(
    () => metodos.find((metodo) => String(metodo.id) === String(cuentaDestinoId)) || null,
    [metodos, cuentaDestinoId],
  );
  const saldoOrigen = cuentaOrigen ? disponibilidad[cuentaOrigen.id] : null;
  const saldoDestino = cuentaDestino ? disponibilidad[cuentaDestino.id] : null;

  const mismaMoneda = cuentaOrigen && cuentaDestino && cuentaOrigen.moneda === cuentaDestino.moneda;
  const crucesMoneda = cuentaOrigen && cuentaDestino && !mismaMoneda;

  // Auto-calcula "Monto a recibir" a partir de "Monto a debitar" x tasa,
  // en la direccion que corresponda segun cual lado es USD — pero solo
  // mientras el usuario no haya editado el campo a mano el mismo (ver
  // handleMontoDestinoChange): esto es un punto de partida, no una
  // imposicion, para que pueda ajustar los centimos exactos que le cobro
  // su banco.
  useEffect(() => {
    if (!crucesMoneda || montoDestinoTocado) return;
    const origenNum = Number(montoOrigen);
    const tasaNum = Number(tasaCambio);
    if (!origenNum || !tasaNum) {
      setMontoDestino('');
      return;
    }
    const calculado = cuentaOrigen.moneda === 'USD' ? origenNum * tasaNum : origenNum / tasaNum;
    setMontoDestino(calculado.toFixed(2));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [crucesMoneda, montoOrigen, tasaCambio]);

  const handleMontoDestinoChange = (value) => {
    setMontoDestino(value);
    setMontoDestinoTocado(true);
  };

  const handleSelectOrigen = (value) => {
    setCuentaOrigenId(value);
    setMontoDestinoTocado(false);
  };
  const handleSelectDestino = (value) => {
    setCuentaDestinoId(value);
    setMontoDestinoTocado(false);
  };

  if (!open) {
    return null;
  }

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (!cuentaOrigenId || !cuentaDestinoId) {
      showError('Selecciona la cuenta origen y la cuenta destino.');
      return;
    }
    if (cuentaOrigenId === cuentaDestinoId) {
      showError('La cuenta origen y la cuenta destino no pueden ser la misma.');
      return;
    }
    if (!concepto.trim()) {
      showError('El concepto/motivo es obligatorio.');
      return;
    }

    const finalMontoOrigen = mismaMoneda ? montoUnico : montoOrigen;
    const finalMontoDestino = mismaMoneda ? montoUnico : montoDestino;

    const montoOrigenNum = Number(finalMontoOrigen);
    const montoDestinoNum = Number(finalMontoDestino);
    if (!montoOrigenNum || montoOrigenNum <= 0 || !montoDestinoNum || montoDestinoNum <= 0) {
      showError('Los montos deben ser mayores a cero.');
      return;
    }
    if (crucesMoneda && (!tasaCambio || Number(tasaCambio) <= 0)) {
      showError('Indica la tasa de cambio acordada para esta transferencia.');
      return;
    }

    // Feedback inmediato contra el saldo que ya se cargó — la validación
    // real y definitiva la hace el backend igual.
    if (saldoOrigen && montoOrigenNum > Number(saldoOrigen.saldo_disponible) && cuentaOrigen.moneda === 'USD') {
      showError(`${cuentaOrigen.nombre} no tiene saldo suficiente — disponible: $${formatMonto(saldoOrigen.saldo_disponible)}.`);
      return;
    }

    setEnviando(true);
    try {
      const response = await fetch('/api/admin/transferencias-cuentas/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          fecha,
          cuenta_origen_id: cuentaOrigenId,
          cuenta_destino_id: cuentaDestinoId,
          monto_origen: finalMontoOrigen,
          monto_destino: finalMontoDestino,
          tasa_cambio: crucesMoneda ? tasaCambio : null,
          referencia,
          concepto,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo registrar la transferencia.');
      }
      onSuccess(data.transferencia);
    } catch (error) {
      showError(error.message || 'No se pudo registrar la transferencia.');
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div style={backdropStyle} onClick={enviando ? undefined : onClose}>
      <Toast toast={toast} onClose={hideToast} position="top-left" />
      <div style={cardStyle} onClick={(event) => event.stopPropagation()}>
        <div style={titleStyle}>⇄ Transferencia entre cuentas</div>
        <p style={subtitleStyle}>Mueve dinero entre dos cuentas propias del negocio — no es una venta ni un gasto.</p>

        <form onSubmit={handleSubmit} style={formStyle}>
          <label style={fieldStyle}>
            <span style={labelStyle}>Fecha</span>
            <input type="date" value={fecha} onChange={(event) => setFecha(event.target.value)} style={inputStyle} required />
          </label>

          <div style={cuentasRowStyle}>
            <label style={fieldStyle}>
              <span style={labelStyle}>Cuenta origen (debitar)</span>
              <select
                value={cuentaOrigenId}
                onChange={(event) => handleSelectOrigen(event.target.value)}
                style={inputStyle}
                disabled={cargandoMetodos}
                required
              >
                <option value="">Selecciona...</option>
                {metodos.map((metodo) => (
                  <option key={metodo.id} value={metodo.id} disabled={String(metodo.id) === String(cuentaDestinoId)}>
                    {metodo.nombre} ({metodo.moneda})
                  </option>
                ))}
              </select>
              {cuentaOrigen ? (
                <span style={saldoBadgeStyle}>
                  {cargandoDisponibilidad ? 'Consultando...' : `Disponible: ${formatSaldoCuenta(saldoOrigen) ?? '—'}`}
                </span>
              ) : null}
            </label>

            <span style={flechaStyle}>→</span>

            <label style={fieldStyle}>
              <span style={labelStyle}>Cuenta destino (acreditar)</span>
              <select
                value={cuentaDestinoId}
                onChange={(event) => handleSelectDestino(event.target.value)}
                style={inputStyle}
                disabled={cargandoMetodos}
                required
              >
                <option value="">Selecciona...</option>
                {metodos.map((metodo) => (
                  <option key={metodo.id} value={metodo.id} disabled={String(metodo.id) === String(cuentaOrigenId)}>
                    {metodo.nombre} ({metodo.moneda})
                  </option>
                ))}
              </select>
              {cuentaDestino ? (
                <span style={saldoBadgeStyle}>
                  {cargandoDisponibilidad ? 'Consultando...' : `Disponible: ${formatSaldoCuenta(saldoDestino) ?? '—'}`}
                </span>
              ) : null}
            </label>
          </div>

          {mismaMoneda ? (
            <label style={fieldStyle}>
              <span style={labelStyle}>Monto ({cuentaOrigen.moneda})</span>
              <input
                type="number" step="0.01" min="0.01"
                value={montoUnico}
                onChange={(event) => setMontoUnico(event.target.value)}
                style={inputStyle}
                required
              />
            </label>
          ) : crucesMoneda ? (
            <div style={cuentasRowStyle}>
              <label style={fieldStyle}>
                <span style={labelStyle}>Monto a debitar ({cuentaOrigen.moneda})</span>
                <input
                  type="number" step="0.01" min="0.01"
                  value={montoOrigen}
                  onChange={(event) => setMontoOrigen(event.target.value)}
                  style={inputStyle}
                  required
                />
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Tasa acordada (Bs/USD)</span>
                <input
                  type="number" step="0.0001" min="0.0001"
                  value={tasaCambio}
                  onChange={(event) => setTasaCambio(event.target.value)}
                  style={inputStyle}
                  required
                />
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Monto a recibir ({cuentaDestino.moneda})</span>
                <input
                  type="number" step="0.01" min="0.01"
                  value={montoDestino}
                  onChange={(event) => handleMontoDestinoChange(event.target.value)}
                  style={inputStyle}
                  required
                />
              </label>
            </div>
          ) : (
            <div style={hintStyle}>Selecciona ambas cuentas para continuar.</div>
          )}

          <label style={fieldStyle}>
            <span style={labelStyle}>Número de referencia (opcional)</span>
            <input value={referencia} onChange={(event) => setReferencia(event.target.value)} style={inputStyle} />
          </label>

          <label style={fieldStyle}>
            <span style={labelStyle}>Concepto / Motivo</span>
            <input
              value={concepto}
              onChange={(event) => setConcepto(event.target.value)}
              placeholder="Ej: Traslado de fondos para pagar proveedores"
              style={inputStyle}
              required
            />
          </label>

          <div style={footerStyle}>
            <button type="button" onClick={onClose} style={cancelButtonStyle} disabled={enviando}>
              Cancelar
            </button>
            <button type="submit" style={confirmButtonStyle} disabled={enviando}>
              {enviando ? 'Registrando...' : 'Registrar transferencia'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const backdropStyle = {
  position: 'fixed', inset: 0, background: 'rgba(0, 0, 0, 0.6)',
  display: 'grid', placeItems: 'center', zIndex: 1000, padding: 16,
};

const cardStyle = {
  width: '100%', maxWidth: 560, borderRadius: 20,
  border: '1px solid rgba(150, 130, 255, 0.35)',
  background: 'linear-gradient(180deg, rgba(18, 14, 28, 0.98) 0%, rgba(8, 8, 12, 0.99) 100%)',
  padding: '22px 22px 18px',
  boxShadow: '0 20px 50px rgba(0, 0, 0, 0.45)',
  maxHeight: '90vh', overflowY: 'auto',
};

const titleStyle = { color: '#fff', fontSize: 19, fontWeight: 800, marginBottom: 4 };
const subtitleStyle = { margin: '0 0 16px', color: '#c8bbd8', fontSize: 13, lineHeight: 1.5 };
const formStyle = { display: 'grid', gap: 14 };
const fieldStyle = { display: 'grid', gap: 6, flex: 1 };
const labelStyle = { color: '#d3bff5', fontSize: 12.5, fontWeight: 700 };
const inputStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 10, border: '1px solid rgba(255,255,255,0.14)', background: '#141019', padding: '9px 10px', color: '#fff', fontSize: 13.5 };
const cuentasRowStyle = { display: 'flex', gap: 10, alignItems: 'flex-end', flexWrap: 'wrap' };
const flechaStyle = { color: '#9d8fd4', fontSize: 20, fontWeight: 800, paddingBottom: 8 };
const saldoBadgeStyle = { color: '#8fffb0', fontSize: 11.5, fontWeight: 700 };
const hintStyle = { color: '#a89bc9', fontSize: 12.5, fontStyle: 'italic' };
const footerStyle = { display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 6, flexWrap: 'wrap' };
const cancelButtonStyle = { border: '1px solid rgba(255,255,255,0.16)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.05)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const confirmButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 18px', background: 'linear-gradient(90deg, #6d28d9 0%, #4f46e5 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(109, 40, 217, 0.35)' };

export default TransferenciaCuentasModal;

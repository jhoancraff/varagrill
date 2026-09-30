import { useEffect, useState } from 'react';
import useMobileBackHandler from '../hooks/useMobileBackHandler';

function IngresoParcialModal({ open, onClose, onSubmit, submitting }) {
  useMobileBackHandler(open, onClose);

  const [metodos, setMetodos] = useState([]);
  const [cargandoMetodos, setCargandoMetodos] = useState(true);
  const [metodoPagoId, setMetodoPagoId] = useState('');
  const [monto, setMonto] = useState('');
  const [descripcion, setDescripcion] = useState('');
  const [errorLocal, setErrorLocal] = useState('');

  // Reinicia el formulario cada vez que se abre.
  useEffect(() => {
    if (!open) return;
    setMetodoPagoId('');
    setMonto('');
    setDescripcion('');
    setErrorLocal('');
  }, [open]);

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

  if (!open) {
    return null;
  }

  const metodoSeleccionado = metodos.find((metodo) => String(metodo.id) === String(metodoPagoId));
  // El monto se cuenta siempre en la moneda REAL de la cuenta elegida (igual
  // que un abono de nota de entrega/factura o una propina/pago extra): si la
  // cuenta es en bolivares, aca se escriben bolivares tal cual se contaron,
  // no dolares — el backend congela la tasa del momento para poder mostrar
  // despues exactamente ese mismo monto en bolivares (ver ingresos_extra_view).
  const esBs = metodoSeleccionado?.moneda === 'VES';

  const handleSubmit = (event) => {
    event.preventDefault();
    setErrorLocal('');

    if (!metodoPagoId) {
      setErrorLocal('Selecciona la cuenta donde entro el dinero.');
      return;
    }
    const montoNumber = Number(monto);
    if (!montoNumber || montoNumber <= 0) {
      setErrorLocal('Ingresa un monto valido.');
      return;
    }
    if (!descripcion.trim()) {
      setErrorLocal('La descripcion es obligatoria.');
      return;
    }

    onSubmit({ monto: montoNumber, descripcion: descripcion.trim(), metodoPagoId });
  };

  return (
    <div style={backdropStyle} onClick={submitting ? undefined : onClose}>
      <div style={cardStyle} onClick={(event) => event.stopPropagation()}>
        <div style={titleStyle}>+ Ingreso parcial</div>
        <p style={subtitleStyle}>
          Dinero que entro a una cuenta sin una nota de entrega asociada (ej. un deposito que solo se puede documentar
          con una descripcion) — se suma al saldo de la cuenta y aparece en el flujo bancario diario.
        </p>

        <form onSubmit={handleSubmit} style={formStyle}>
          <label style={fieldStyle}>
            <span style={labelStyle}>Cuenta donde entro el dinero</span>
            <select
              value={metodoPagoId}
              onChange={(event) => setMetodoPagoId(event.target.value)}
              style={inputStyle}
              className="admin-dark-select"
              disabled={cargandoMetodos}
              required
            >
              <option value="">Selecciona una cuenta...</option>
              {metodos.map((metodo) => (
                <option key={metodo.id} value={metodo.id}>
                  {metodo.nombre} ({metodo.moneda === 'VES' ? 'Bs' : '$'})
                </option>
              ))}
            </select>
          </label>

          <label style={fieldStyle}>
            <span style={labelStyle}>Monto ({esBs ? 'Bs' : '$'})</span>
            <input
              type="number"
              min="0.01"
              step="0.01"
              value={monto}
              onChange={(event) => setMonto(event.target.value)}
              style={inputStyle}
              placeholder="0.00"
              required
            />
          </label>

          <label style={fieldStyle}>
            <span style={labelStyle}>Descripcion / motivo</span>
            <input
              type="text"
              value={descripcion}
              onChange={(event) => setDescripcion(event.target.value)}
              style={inputStyle}
              placeholder="Ej: Deposito de socio, reembolso de proveedor..."
              required
            />
          </label>

          {errorLocal ? <div style={errorStyle}>{errorLocal}</div> : null}

          <div style={footerStyle}>
            <button type="button" onClick={onClose} style={cancelButtonStyle} disabled={submitting}>
              Cancelar
            </button>
            <button type="submit" style={confirmButtonStyle} disabled={submitting}>
              {submitting ? 'Registrando...' : 'Registrar ingreso'}
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
  width: '100%', maxWidth: 480, borderRadius: 20,
  border: '1px solid rgba(150, 130, 255, 0.35)',
  background: 'linear-gradient(180deg, rgba(18, 14, 28, 0.98) 0%, rgba(8, 8, 12, 0.99) 100%)',
  padding: '22px 22px 18px',
  boxShadow: '0 20px 50px rgba(0, 0, 0, 0.45)',
  maxHeight: '90vh', overflowY: 'auto',
};

const titleStyle = { color: '#fff', fontSize: 19, fontWeight: 800, marginBottom: 4 };
const subtitleStyle = { margin: '0 0 16px', color: '#c8bbd8', fontSize: 13, lineHeight: 1.5 };
const formStyle = { display: 'grid', gap: 14 };
const fieldStyle = { display: 'grid', gap: 6 };
const labelStyle = { color: '#d3bff5', fontSize: 12.5, fontWeight: 700 };
const inputStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 10, border: '1px solid rgba(255,255,255,0.14)', background: '#141019', padding: '9px 10px', color: '#fff', fontSize: 13.5 };
const errorStyle = { padding: '10px 12px', borderRadius: 10, border: '1px solid rgba(255,145,145,0.28)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8', fontSize: 12.5 };
const footerStyle = { display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 6, flexWrap: 'wrap' };
const cancelButtonStyle = { border: '1px solid rgba(255,255,255,0.16)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.05)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const confirmButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 18px', background: 'linear-gradient(90deg, #6d28d9 0%, #4f46e5 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(109, 40, 217, 0.35)' };

export default IngresoParcialModal;

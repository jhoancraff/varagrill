import { useState } from 'react';
import useMobileBackHandler from '../hooks/useMobileBackHandler';

// Modal compartido por MesasAtendidasPage y CheckoutPage para dos ajustes a un
// item de un pedido en curso: quitarlo (completo o solo parte de la cantidad)
// o moverlo a otra mesa. Las dos acciones son distintas en la UI (una pide
// cuanto quitar, la otra a que mesa) pero comparten lo importante: una
// advertencia clara y un motivo obligatorio, que queda guardado para
// auditoria (ver VGAjustePedido en varagrill/models/restaurant.py).
function AjustePedidoModal({
  modo, // 'eliminar' | 'mover'
  item, // { id, nombre, cantidad, esPorPeso }
  mesasCatalogo = [],
  mesaActualId,
  busy = false,
  error = '',
  requiereUsuario = false,
  meserosDisponibles = [],
  onClose,
  onConfirmarEliminar,
  onConfirmarMover,
}) {
  useMobileBackHandler(true, onClose);
  const [motivo, setMotivo] = useState('');
  const [cantidad, setCantidad] = useState(1);
  const [mesaDestinoId, setMesaDestinoId] = useState('');
  const [usuarioId, setUsuarioId] = useState('');

  const puedeElegirCantidad = modo === 'eliminar' && !item.esPorPeso && item.cantidad > 1;
  const puedeConfirmar = motivo.trim().length > 0
    && (modo === 'eliminar' || mesaDestinoId !== '')
    && (!requiereUsuario || usuarioId !== '');

  const handleConfirmar = () => {
    if (!puedeConfirmar || busy) return;
    if (modo === 'eliminar') {
      onConfirmarEliminar({ motivo: motivo.trim(), cantidad: puedeElegirCantidad ? cantidad : item.cantidad });
    } else {
      onConfirmarMover({
        motivo: motivo.trim(),
        mesaDestinoId: Number(mesaDestinoId),
        usuarioId: usuarioId !== '' ? Number(usuarioId) : undefined,
      });
    }
  };

  return (
    <div style={modalBackdropStyle} onClick={busy ? undefined : onClose}>
      <div style={modalCardStyle} onClick={(event) => event.stopPropagation()}>
        <div style={modalTitleStyle}>
          {modo === 'eliminar' ? 'Quitar item' : 'Mover item a otra mesa'}
        </div>

        <p style={modalDescStyle}>
          {modo === 'eliminar' ? (
            <>
              Vas a quitar {item.esPorPeso ? '' : `${item.cantidad}x `}<strong>{item.nombre}</strong> de este pedido.
              Esta acción no se puede deshacer.
            </>
          ) : (
            <>
              Vas a mover <strong>{item.cantidad}x {item.nombre}</strong> a otra mesa.
              La mesa destino debe tener ya un pedido abierto.
            </>
          )}
          {' '}Escribe el motivo — queda guardado para auditoría.
        </p>

        {puedeElegirCantidad ? (
          <label style={fieldLabelStyle}>
            Cantidad a quitar (de {item.cantidad})
            <input
              type="number"
              min={1}
              max={item.cantidad}
              value={cantidad}
              onChange={(event) => {
                const valor = Number(event.target.value);
                if (Number.isNaN(valor)) return;
                setCantidad(Math.min(Math.max(valor, 1), item.cantidad));
              }}
              style={numberInputStyle}
            />
          </label>
        ) : null}

        {modo === 'mover' ? (
          <label style={fieldLabelStyle}>
            Mesa destino
            <select
              value={mesaDestinoId}
              onChange={(event) => setMesaDestinoId(event.target.value)}
              style={selectStyle}
              className="admin-dark-select"
            >
              <option value="">Seleccionar mesa</option>
              {mesasCatalogo
                .filter((mesa) => mesa.id !== mesaActualId)
                .map((mesa) => (
                  <option key={mesa.id} value={mesa.id}>Mesa {mesa.numero}</option>
                ))}
            </select>
          </label>
        ) : null}

        {modo === 'mover' && requiereUsuario ? (
          <>
            <p style={infoNoteStyle}>
              Esa mesa no tiene ningún pedido abierto — se va a abrir uno nuevo ahí. Elige quién la va a atender:
            </p>
            <label style={fieldLabelStyle}>
              Mesero
              <select
                value={usuarioId}
                onChange={(event) => setUsuarioId(event.target.value)}
                style={selectStyle}
                className="admin-dark-select"
              >
                <option value="">Seleccionar mesero</option>
                {meserosDisponibles.map((mesero) => (
                  <option key={mesero.id} value={mesero.id}>{mesero.nombre}</option>
                ))}
              </select>
            </label>
          </>
        ) : null}

        <label style={fieldLabelStyle}>
          Motivo *
          <textarea
            value={motivo}
            onChange={(event) => setMotivo(event.target.value)}
            style={textareaStyle}
            placeholder={modo === 'eliminar' ? 'Ej: El cliente ya no quiere una de las dos.' : 'Ej: Se cargó a la mesa equivocada.'}
            rows={3}
            autoFocus
          />
        </label>

        {error ? <div style={errorStyle}>{error}</div> : null}

        <div style={modalFooterStyle}>
          <button type="button" onClick={onClose} style={secondaryButtonStyle} disabled={busy}>
            Cancelar
          </button>
          <button type="button" onClick={handleConfirmar} style={primaryButtonStyle} disabled={busy || !puedeConfirmar}>
            {busy ? 'Guardando...' : 'Confirmar'}
          </button>
        </div>
      </div>
    </div>
  );
}

const modalBackdropStyle = { position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,0.65)', display: 'grid', placeItems: 'center', padding: 16 };
const modalCardStyle = { width: '100%', maxWidth: 440, borderRadius: 20, border: '1px solid rgba(255,145,145,0.3)', background: 'linear-gradient(180deg, rgba(28,12,12,0.98) 0%, rgba(10,8,8,0.99) 100%)', padding: '22px 22px 18px', boxShadow: '0 20px 50px rgba(0,0,0,0.45)', display: 'grid', gap: 12 };
const modalTitleStyle = { color: '#fff', fontSize: 19, fontWeight: 800 };
const modalDescStyle = { margin: 0, color: '#d2c3c3', lineHeight: 1.55, fontSize: 13.5 };
const fieldLabelStyle = { display: 'grid', gap: 6, color: '#e8dede', fontSize: 13, fontWeight: 700 };
const numberInputStyle = { borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff', fontSize: 14, width: 100 };
const selectStyle = { borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff', fontSize: 14 };
const textareaStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 12, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '10px 12px', color: '#fff4f4', fontSize: 14, fontFamily: 'inherit', resize: 'vertical' };
const errorStyle = { padding: '10px 12px', borderRadius: 12, border: '1px solid rgba(255,145,145,0.22)', background: 'rgba(255,98,98,0.12)', color: '#ffd8d8', fontSize: 13 };
const infoNoteStyle = { margin: 0, padding: '10px 12px', borderRadius: 12, border: '1px solid rgba(245, 158, 11, 0.3)', background: 'rgba(245, 158, 11, 0.1)', color: '#f5c778', fontSize: 13, lineHeight: 1.5 };
const modalFooterStyle = { display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 6, flexWrap: 'wrap' };
const secondaryButtonStyle = { border: '1px solid rgba(255,255,255,0.16)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.05)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };

export default AjustePedidoModal;

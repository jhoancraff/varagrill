import ConfirmModal from './ConfirmModal';
import { diasAtras, formatearFecha, hoyIso } from '../utils/fechas';

// Alerta cuando la fecha elegida al registrar no es la de hoy (ej. se olvidaron de cargar algo de ayer): pide
// confirmar que de verdad ocurrio ese dia, porque los reportes de caja y banco lo contaran en esa fecha.
// `queEs` es lo que se esta registrando: 'gasto', 'compra' o 'pago'.
function ConfirmarFechaModal({ open, fecha, queEs = 'gasto', onConfirm, onCancel }) {
  const dias = diasAtras(fecha);
  const cuando = dias === 1 ? 'ayer' : `hace ${dias} días`;
  return (
    <ConfirmModal
      open={open}
      title="La fecha no es la de hoy"
      message={
        `Elegiste el ${formatearFecha(fecha)} (${cuando}) como fecha del ${queEs}, y hoy es ${formatearFecha(hoyIso())}. `
        + `El sistema guarda igual el momento exacto en que lo registras, pero los reportes lo contarán el ${formatearFecha(fecha)}. `
        + `¿Confirmas que el ${queEs} fue ese día?`
      }
      confirmLabel={`Sí, fue el ${formatearFecha(fecha)}`}
      cancelLabel="Corregir fecha"
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  );
}

export default ConfirmarFechaModal;

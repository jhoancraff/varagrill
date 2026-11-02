import { useCallback, useState } from 'react';
import AdvertenciasFechaModal from '../components/AdvertenciasFechaModal';
import ConfirmarFechaModal from '../components/ConfirmarFechaModal';
import { esHoy } from '../utils/fechas';

// Las dos confirmaciones que acompañan a la fecha real de un gasto, una compra o un pago:
//   confirmarFecha(fecha, queEs)       -> alerta si la fecha no es la de hoy; resuelve true/false.
//   confirmarAdvertencias(advertencias) -> las advertencias del servidor (dia cerrado...); resuelve la lista de
//                                          codigos aceptados, o null si se cancela.
// `modales` hay que renderizarlo una vez en la pantalla. Se usan con await para no partir cada formulario en callbacks.
export default function useConfirmacionesFecha() {
  const [fechaPendiente, setFechaPendiente] = useState(null);
  const [advertenciasPendientes, setAdvertenciasPendientes] = useState(null);

  const confirmarFecha = useCallback((fecha, queEs) => {
    if (esHoy(fecha)) return Promise.resolve(true);
    return new Promise((resolve) => setFechaPendiente({ fecha, queEs, resolve }));
  }, []);

  const confirmarAdvertencias = useCallback(
    (advertencias) => new Promise((resolve) => setAdvertenciasPendientes({ advertencias, resolve })),
    [],
  );

  const cerrarFecha = (valor) => {
    fechaPendiente?.resolve(valor);
    setFechaPendiente(null);
  };
  const cerrarAdvertencias = (valor) => {
    advertenciasPendientes?.resolve(valor);
    setAdvertenciasPendientes(null);
  };

  const modales = (
    <>
      <ConfirmarFechaModal
        open={Boolean(fechaPendiente)}
        fecha={fechaPendiente?.fecha}
        queEs={fechaPendiente?.queEs}
        onConfirm={() => cerrarFecha(true)}
        onCancel={() => cerrarFecha(false)}
      />
      <AdvertenciasFechaModal
        open={Boolean(advertenciasPendientes)}
        advertencias={advertenciasPendientes?.advertencias || []}
        onConfirm={(codigos) => cerrarAdvertencias(codigos)}
        onCancel={() => cerrarAdvertencias(null)}
      />
    </>
  );

  return { confirmarFecha, confirmarAdvertencias, modales };
}

// POST JSON que, si el servidor responde 409 con `requiere_confirmacion`, muestra las advertencias y reenvia con
// `aceptadas`. Devuelve { response, data } o { cancelado: true } si quien registra no las acepta.
export async function postConAdvertencias(url, body, confirmarAdvertencias) {
  let aceptadas = [];
  for (;;) {
    const response = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...body, aceptadas }),
    });
    const data = await response.json().catch(() => ({}));
    if (response.status === 409 && data.requiere_confirmacion) {
      const codigos = await confirmarAdvertencias(data.advertencias || []);
      if (!codigos) return { cancelado: true };
      aceptadas = codigos;
    } else {
      return { response, data };
    }
  }
}

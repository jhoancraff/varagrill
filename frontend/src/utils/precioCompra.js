// Precio de compra de una fila de la importación de ingredientes por Excel. El Excel ya no lo trae: se calcula
// con lo que se pagó en total. Misma regla que el servidor (api_views._trio_desde_precio_total), que es quien
// manda al confirmar; esto solo sirve para mostrarlo al instante mientras se corrige la fila.
//
//   g y ml:  precio de compra = precio total × peso neto ÷ cantidad   (precio de UN envase)
//   unidad:  precio de compra = precio total ÷ cantidad                (precio de una unidad)
//
// Los pesos salen de la fila o, si la fila no los trae, de los que el ingrediente ya tiene guardados.

const aNumero = (valor) => {
  const texto = String(valor ?? '').trim().replace(',', '.');
  if (texto === '') return null;
  const numero = Number(texto);
  return Number.isFinite(numero) ? numero : null;
};

// Devuelve el precio de compra con 2 decimales ("5.00") o '' si todavía no se puede calcular.
export function calcularPrecioCompra(fila) {
  const cantidad = aNumero(fila.cantidad);
  const precioTotal = aNumero(fila.precio_total);
  const pesoNeto = aNumero(fila.contenido_envase) ?? aNumero(fila.contenido_envase_actual);
  const pesoReal = aNumero(fila.peso_real) ?? aNumero(fila.peso_real_actual);
  if (cantidad === null || cantidad <= 0 || precioTotal === null || precioTotal < 0) return '';
  if (pesoNeto === null || pesoReal === null || pesoNeto <= 0 || pesoReal <= 0 || pesoReal > pesoNeto) return '';

  const unidad = fila.unidad_actual || fila.unidad;
  const precioEnvase = unidad === 'unidad' ? precioTotal / cantidad : (precioTotal * pesoNeto) / cantidad;
  return (Math.round((precioEnvase + Number.EPSILON) * 100) / 100).toFixed(2);
}

const aMillonesimas = (numero) => Math.round(numero * 1e6) / 1e6;

// Costo unitario (el efectivo: el que usan reportes y recetas y el que mide la alerta de precio) que tendría el
// ingrediente tras importar la fila, y cuánto cambia contra el de hoy. Misma regla que el servidor
// (api_views._costo_efectivo_tras_la_carga); `umbral` es el porcentaje de alerta configurado en el costeo.
// Devuelve { costoNuevo, costoActual, variacion, alerta } con números (o null si no aplica).
export function calcularCostoNuevo(fila, umbral) {
  const costoActual = aNumero(fila.costo_actual);
  const precioCompra = calcularPrecioCompra(fila);
  let costoNuevo = null;
  if (precioCompra !== '') {
    // Con los pesos conocidos: precio del envase ÷ peso real, redondeado a 6 decimales como lo guarda el servidor.
    const pesoReal = aNumero(fila.peso_real) ?? aNumero(fila.peso_real_actual);
    costoNuevo = aMillonesimas(Number(precioCompra) / pesoReal);
  } else {
    const cantidad = aNumero(fila.cantidad);
    const precioTotal = aNumero(fila.precio_total);
    if (fila.ingrediente_id && cantidad !== null && cantidad > 0 && precioTotal !== null && precioTotal >= 0) {
      const tieneEnvaseGuardado = aNumero(fila.precio_compra_actual) !== null && (aNumero(fila.peso_real_actual) ?? 0) > 0;
      // Con envase y peso real ya guardados los reportes siguen usando ese costo; sin ellos, total ÷ cantidad.
      costoNuevo = tieneEnvaseGuardado ? costoActual : aMillonesimas(precioTotal / cantidad);
    }
  }
  const variacion = costoNuevo !== null && costoActual !== null && costoActual > 0
    ? Math.round(((costoNuevo - costoActual) / costoActual) * 10000) / 100
    : null;
  const limite = aNumero(umbral);
  const alerta = variacion !== null && limite !== null && limite > 0 && Math.abs(variacion) >= limite;
  return { costoNuevo, costoActual, variacion, alerta };
}

// 0.0094444 -> "0.009444"; 1.5 -> "1.50": hasta 6 decimales, sin ceros de sobra pero con 2 como mínimo.
export function formatearCosto(numero) {
  if (numero === null || numero === undefined) return '';
  const texto = numero.toFixed(6).replace(/0+$/, '');
  const decimales = texto.split('.')[1] || '';
  return decimales.length >= 2 ? texto : numero.toFixed(2);
}

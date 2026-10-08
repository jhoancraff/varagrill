// Descarga un PDF que arma el servidor (ver varagrill/reportes_pdf_views.py).
//
// Se baja con fetch (y no con un simple enlace) para poder mostrar el mensaje de error del
// servidor — sesion vencida, falta de permisos, etc. — en vez de dejar una pestaña en blanco.
// `params` son los filtros del reporte (ej. { desde, hasta }); se mandan en la URL.
export async function descargarPdf(url, params = {}) {
  const consulta = new URLSearchParams(
    Object.entries(params).filter(([, valor]) => valor !== undefined && valor !== null && valor !== ''),
  ).toString();

  const response = await fetch(consulta ? `${url}?${consulta}` : url, {
    credentials: 'include',
    cache: 'no-store',
  });

  if (!response.ok) {
    let mensaje = 'No se pudo generar el PDF.';
    try {
      const data = await response.json();
      mensaje = data.message || mensaje;
    } catch {
      // La respuesta no era JSON; se deja el mensaje por defecto.
    }
    throw new Error(mensaje);
  }

  const blob = await response.blob();
  const disposition = response.headers.get('Content-Disposition') || '';
  const nombre = /filename="?([^";]+)"?/.exec(disposition)?.[1] || 'reporte.pdf';

  const enlaceTemporal = URL.createObjectURL(blob);
  const enlace = document.createElement('a');
  enlace.href = enlaceTemporal;
  enlace.download = nombre;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  URL.revokeObjectURL(enlaceTemporal);
}

export default descargarPdf;

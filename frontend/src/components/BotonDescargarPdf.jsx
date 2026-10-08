import { useState } from 'react';
import { descargarPdf } from '../utils/descargarPdf';

// Boton "Descargar PDF" de cualquier reporte:
//   <BotonDescargarPdf url="/api/admin/reportes/inventario-pdf/" params={{ desde, hasta }} onError={showError} />
// Mientras genera queda deshabilitado (evita el doble clic) y avisa por onError si falla.
function BotonDescargarPdf({ url, params, onError, style, children = 'Descargar PDF' }) {
  const [generando, setGenerando] = useState(false);

  const handleClick = async () => {
    setGenerando(true);
    try {
      await descargarPdf(url, params);
    } catch (error) {
      if (onError) onError(error.message || 'No se pudo generar el PDF.');
    } finally {
      setGenerando(false);
    }
  };

  return (
    <button type="button" className="no-print" onClick={handleClick} disabled={generando} style={{ ...baseStyle, ...style }}>
      {generando ? 'Generando PDF...' : children}
    </button>
  );
}

const baseStyle = {
  border: '1px solid rgba(255,255,255,0.14)',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'rgba(255,255,255,0.04)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
};

export default BotonDescargarPdf;

import { useEffect, useLayoutEffect, useRef, useState } from 'react';

// Menú desplegable de acciones: deja a la vista solo la acción principal y esconde el resto detrás
// de un solo botón («⋯» en una fila, «Más acciones ▾» en la cabecera), para no llenar los reportes
// de botones sueltos.
//
//   <MenuAcciones
//     items={[
//       { label: 'Modificar', onClick: () => editar(fila) },
//       { label: 'Eliminar', onClick: () => borrar(fila), danger: true },
//       { label: 'Reponer', onClick: ..., hidden: !fila.puedeReponer },
//     ]}
//   />
//
// El panel va con position: fixed (calculada desde el botón) para que no lo recorte el scroll
// horizontal de las tablas; se cierra al elegir una acción, al hacer clic fuera, con Escape o al
// mover/redimensionar la pantalla.
function MenuAcciones({ items, label = null, ariaLabel = 'Más acciones', disabled = false, style }) {
  const [abierto, setAbierto] = useState(false);
  const [posicion, setPosicion] = useState({ top: 0, right: 0 });
  const botonRef = useRef(null);
  const panelRef = useRef(null);
  const visibles = (items || []).filter((item) => item && !item.hidden);

  useLayoutEffect(() => {
    if (!abierto || !botonRef.current) {
      return;
    }
    const caja = botonRef.current.getBoundingClientRect();
    const alto = panelRef.current ? panelRef.current.offsetHeight : 0;
    const abajo = caja.bottom + 6;
    // Si no cabe debajo, se abre hacia arriba.
    const top = abajo + alto > window.innerHeight - 8 ? Math.max(8, caja.top - alto - 6) : abajo;
    setPosicion({ top, right: Math.max(8, window.innerWidth - caja.right) });
  }, [abierto]);

  useEffect(() => {
    if (!abierto) {
      return undefined;
    }
    const cerrarFuera = (event) => {
      if (
        panelRef.current && !panelRef.current.contains(event.target)
        && botonRef.current && !botonRef.current.contains(event.target)
      ) {
        setAbierto(false);
      }
    };
    const cerrarConEscape = (event) => {
      if (event.key === 'Escape') {
        setAbierto(false);
      }
    };
    const cerrar = () => setAbierto(false);
    document.addEventListener('mousedown', cerrarFuera);
    document.addEventListener('keydown', cerrarConEscape);
    window.addEventListener('resize', cerrar);
    window.addEventListener('scroll', cerrar, true);
    return () => {
      document.removeEventListener('mousedown', cerrarFuera);
      document.removeEventListener('keydown', cerrarConEscape);
      window.removeEventListener('resize', cerrar);
      window.removeEventListener('scroll', cerrar, true);
    };
  }, [abierto]);

  if (visibles.length === 0) {
    return null;
  }

  return (
    <>
      <button
        ref={botonRef}
        type="button"
        aria-label={ariaLabel}
        aria-haspopup="menu"
        aria-expanded={abierto}
        disabled={disabled}
        onClick={() => setAbierto((actual) => !actual)}
        style={{ ...(label ? botonConEtiquetaStyle : botonIconoStyle), ...style }}
      >
        {label ? `${label} ▾` : '⋯'}
      </button>
      {abierto ? (
        <div ref={panelRef} role="menu" style={{ ...panelStyle, top: posicion.top, right: posicion.right }}>
          {visibles.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              disabled={item.disabled}
              onClick={() => {
                setAbierto(false);
                item.onClick();
              }}
              style={item.danger ? itemPeligroStyle : itemStyle}
            >
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
    </>
  );
}

const botonBase = {
  border: '1px solid rgba(var(--vg-ink), 0.18)',
  background: 'rgba(var(--vg-ink), 0.05)',
  color: 'var(--vg-text-strong)',
  fontWeight: 700,
  cursor: 'pointer',
};
const botonIconoStyle = { ...botonBase, borderRadius: 999, width: 34, height: 30, fontSize: 18, lineHeight: 1, padding: 0 };
const botonConEtiquetaStyle = { ...botonBase, borderRadius: 999, padding: '10px 16px', fontSize: 14 };
const panelStyle = {
  position: 'fixed',
  zIndex: 950,
  minWidth: 190,
  display: 'grid',
  gap: 2,
  padding: 6,
  borderRadius: 14,
  border: '1px solid rgba(var(--vg-ink), 0.16)',
  background: 'var(--vg-s-140b0b)',
  boxShadow: '0 16px 36px rgba(0, 0, 0, calc(0.5 * var(--vg-shadow-k)))',
};
const itemStyle = {
  border: 'none',
  background: 'transparent',
  color: 'var(--vg-text-strong)',
  textAlign: 'left',
  padding: '9px 12px',
  borderRadius: 10,
  fontSize: 13.5,
  fontWeight: 600,
  cursor: 'pointer',
};
const itemPeligroStyle = { ...itemStyle, color: 'var(--vg-f-ffb0b0)' };

export default MenuAcciones;

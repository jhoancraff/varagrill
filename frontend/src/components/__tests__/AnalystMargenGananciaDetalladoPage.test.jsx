import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import AnalystMargenGananciaDetalladoPage from '../AnalystMargenGananciaDetalladoPage';

vi.mock('../../hooks/useExchangeRate', () => ({ default: () => null }));

// Cada plato redondea su total al centavo: 3 platos de 1,004 dan 1,00 cada uno (3,00 sumados), pero el total real
// de las ventas es 3,01. La pantalla debe mostrar el del servidor, que redondea una sola vez.
const seccion = (id, nombre) => ({
  producto_id: id, nombre, categoria: 'Platos', categoria_id: 1,
  total_unidades: '1.00', total_kg: '0.00', total_ingreso: '2.00', total_costo: '1.00', total_costo_con_margen: '1.00',
  total_ganancia_monto: '1.00', total_ganancia_pct: '50.00', total_lineas: 1,
  tiene_costo_estimado: false, tiene_margen_estimado: false,
  filas: [{
    detalle_id: id, pedido_id: id, nota_entrega_id: id, nota_entrega_codigo: `0000000${id}`, fecha_hora: '2026-11-10T12:00:00-04:00',
    cantidad: '1', peso_gramos: null, unidad: 'unidad', costo_unitario: '1.0000', ingreso: '2.00', costo: '1.00',
    margen_produccion_pct: '0', costo_con_margen: '1.00', margen_estimado: false, ganancia_monto: '1.00', ganancia_pct: '50.00',
    costo_estimado: false, cobro_parcial: id === 3, fraccion_cobrada: id === 3 ? '0.6000' : '1.0000',
  }],
});

const REPORTE = {
  ok: true,
  desde: '2026-11-01',
  hasta: '2026-11-21',
  total_lineas: 3,
  secciones: [seccion(1, 'Arepa'), seccion(2, 'Pizza'), seccion(3, 'Tequeños')],
  totales: {
    ingreso_total: '6.02', costo_total: '3.01', costo_con_margen_total: '3.01', ganancia_monto: '3.01', ganancia_pct: '50.00',
  },
};

function montar() {
  global.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(REPORTE) }));
  return render(<AnalystMargenGananciaDetalladoPage isMobile={false} onBack={() => {}} />);
}

describe('Detalle de margen por plato — totales del período', () => {
  beforeEach(() => vi.stubGlobal('print', () => {}));
  afterEach(() => vi.restoreAllMocks());

  it('sin filtro muestra los totales del servidor y no la suma de los totales redondeados de cada plato', async () => {
    montar();
    expect(await screen.findAllByText(/\$3,01/)).not.toHaveLength(0);
    expect(screen.getByText('$6,02')).toBeTruthy();
    expect(screen.queryByText('$6,00')).toBeNull();
    expect(screen.queryByText('$3,00')).toBeNull();
  });

  it('con un plato elegido suma solo sus ventas', async () => {
    montar();
    await screen.findByText('$6,02');
    const buscador = screen.getByPlaceholderText(/Buscar plato/);
    fireEvent.focus(buscador);
    fireEvent.change(buscador, { target: { value: 'pizz' } });
    const sugerencia = await screen.findByText('Pizza', { selector: 'span' });
    fireEvent.mouseDown(sugerencia);
    fireEvent.click(sugerencia);
    expect((await screen.findAllByText('$2,00')).length).toBeGreaterThan(0);
    expect(screen.queryByText('$6,02')).toBeNull();
  });

  it('una nota abonada a medias lleva su etiqueta con el porcentaje cobrado', async () => {
    montar();
    expect(await screen.findByText('cobrado 60%')).toBeTruthy();
  });
});

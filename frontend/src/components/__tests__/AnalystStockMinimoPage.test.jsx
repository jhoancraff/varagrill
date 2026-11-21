import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import AnalystStockMinimoPage from '../AnalystStockMinimoPage';
import { leerSugeridos, limpiarSugeridos } from '../../utils/comprasSugeridas';

const fila = (id, nombre, estado, stock, minimo, extra = {}) => ({
  id, nombre, unidad: 'g', categoria: '', stock_actual: stock, stock_minimo: minimo,
  faltante: String(Math.max(Number(minimo) - Number(stock), 0)), estado, ...extra,
});

const REPORTE = {
  ok: true,
  fecha: '2026-11-21',
  ingredientes: [
    fila(1, 'Aguacate', 'bajo', '800', '2000', { categoria: 'Frutas' }),
    fila(2, 'Cilantro', 'sin_stock', '-50', '500'),
    fila(3, 'Sal', 'en_minimo', '500', '500'),
  ],
  resumen: { total: 3, sin_stock: 1, bajo: 1, en_minimo: 1 },
  ultimo_aviso: {
    fecha: '2026-11-21', es_de_hoy: true, estado: 'enviado', estado_label: 'Enviado', cantidad_ingredientes: 3,
    intentos: 1, ultimo_error: '', completado_en: '2026-11-21T08:02:00-04:00',
  },
};

function montar(reporte = REPORTE, extra = {}) {
  global.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(reporte) }));
  const manejadores = { onBack: vi.fn(), onEdit: vi.fn(), onCargarCompra: vi.fn() };
  render(<AnalystStockMinimoPage isMobile={false} {...manejadores} {...extra} />);
  return manejadores;
}

const nombresEnPantalla = () => screen.getAllByTestId(/^stock-fila-/).map((nodo) => nodo.textContent);

describe('Inventario → Stock mínimo', () => {
  beforeEach(() => limpiarSugeridos());
  afterEach(() => {
    limpiarSugeridos();
    vi.restoreAllMocks();
  });

  it('muestra el mismo reporte del aviso: stock, mínimo, lo que falta y el estado', async () => {
    montar();
    const aguacate = await screen.findByTestId('stock-fila-1');
    expect(aguacate.textContent).toContain('Aguacate');
    expect(aguacate.textContent).toContain('Frutas');
    expect(aguacate.textContent).toContain('800 g');
    expect(aguacate.textContent).toContain('2000 g');
    expect(aguacate.textContent).toContain('1200 g');
    expect(aguacate.textContent).toContain('Bajo el mínimo');
    expect(screen.getByTestId('stock-fila-2').textContent).toContain('Sin stock');
    const sal = screen.getByTestId('stock-fila-3').textContent;
    expect(sal).toContain('En el mínimo');
    expect(sal).toContain('—');
    expect(screen.getByText('3 ingredientes')).toBeTruthy();
    expect(screen.getByText('1 sin stock')).toBeTruthy();
  });

  it('informa cómo le fue al aviso de Telegram de hoy', async () => {
    montar();
    expect(await screen.findByText(/Aviso de Telegram hoy: enviado a las .* \(3 ingredientes\)/)).toBeTruthy();
  });

  it('avisa si el aviso falló y se reintenta', async () => {
    montar({ ...REPORTE, ultimo_aviso: { ...REPORTE.ultimo_aviso, estado: 'fallido', intentos: 2, ultimo_error: 'sin internet', completado_en: null } });
    expect(await screen.findByText(/falló \(intento 2\).*sin internet/)).toBeTruthy();
  });

  it('busca y filtra por estado', async () => {
    montar();
    await screen.findByTestId('stock-fila-1');
    fireEvent.change(screen.getByLabelText('Filtrar por estado'), { target: { value: 'sin_stock' } });
    expect(nombresEnPantalla()).toHaveLength(1);
    expect(screen.getByTestId('stock-fila-2')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Filtrar por estado'), { target: { value: 'todos' } });
    fireEvent.change(screen.getByLabelText('Buscar ingrediente'), { target: { value: 'FRUTAS' } });
    expect(nombresEnPantalla()).toHaveLength(1);
    expect(screen.getByTestId('stock-fila-1')).toBeTruthy();
  });

  it('ordena por nombre como Telegram o por los más urgentes primero', async () => {
    montar();
    await screen.findByTestId('stock-fila-1');
    expect(nombresEnPantalla().map((texto) => texto.slice(0, 6))).toEqual(['Aguaca', 'Cilant', 'Sal500']);
    fireEvent.change(screen.getByLabelText('Ordenar'), { target: { value: 'urgentes' } });
    expect(screen.getAllByTestId(/^stock-fila-/).map((nodo) => nodo.getAttribute('data-testid'))).toEqual([
      'stock-fila-2', 'stock-fila-1', 'stock-fila-3',
    ]);
  });

  it('hay un solo botón para cargar la compra, no uno por ingrediente', async () => {
    montar();
    await screen.findByTestId('stock-fila-1');
    expect(screen.getAllByRole('button', { name: /Cargar compra/ })).toHaveLength(1);
  });

  it('sin selección, «Cargar compra» lleva la carga por lote con todos como atajos', async () => {
    const m = montar();
    await screen.findByTestId('stock-fila-1');
    fireEvent.click(screen.getByRole('button', { name: 'Cargar compra de todos (3)' }));
    expect(leerSugeridos()).toEqual([
      { id: 1, nombre: 'Aguacate', unidad: 'g', faltante: '1200' },
      { id: 2, nombre: 'Cilantro', unidad: 'g', faltante: '550' },
      { id: 3, nombre: 'Sal', unidad: 'g', faltante: '0' },
    ]);
    expect(m.onCargarCompra).toHaveBeenCalledTimes(1);
  });

  it('con ingredientes seleccionados carga la compra solo de esos; sin selección, la de todos los visibles', async () => {
    const m = montar();
    await screen.findByTestId('stock-fila-1');
    expect(screen.getByRole('button', { name: 'Cargar compra de todos (3)' })).toBeTruthy();

    fireEvent.click(screen.getByLabelText('Seleccionar Aguacate'));
    fireEvent.click(screen.getByLabelText('Seleccionar Sal'));
    fireEvent.click(screen.getByRole('button', { name: 'Cargar compra de 2 seleccionado(s)' }));
    expect(leerSugeridos().map((item) => item.id)).toEqual([1, 3]);
    expect(m.onCargarCompra).toHaveBeenCalledTimes(1);
  });

  it('«Cargar compra de todos» respeta el filtro activo', async () => {
    montar();
    await screen.findByTestId('stock-fila-1');
    fireEvent.change(screen.getByLabelText('Filtrar por estado'), { target: { value: 'sin_stock' } });
    fireEvent.click(screen.getByRole('button', { name: 'Cargar compra de todos (1)' }));
    expect(leerSugeridos().map((item) => item.id)).toEqual([2]);
  });

  it('«Modificar» abre el ingrediente para cambiar su mínimo', async () => {
    const m = montar();
    await screen.findByTestId('stock-fila-1');
    fireEvent.click(screen.getByRole('button', { name: 'Modificar Cilantro' }));
    expect(m.onEdit).toHaveBeenCalledWith(2);
  });

  it('sin ingredientes en su mínimo lo explica', async () => {
    montar({ ok: true, fecha: '2026-11-21', ingredientes: [], resumen: { total: 0, sin_stock: 0, bajo: 0, en_minimo: 0 }, ultimo_aviso: null });
    expect(await screen.findByText(/Ningún ingrediente está en su mínimo/)).toBeTruthy();
    expect(screen.getByText(/Todavía no hay avisos de Telegram registrados/)).toBeTruthy();
  });
});

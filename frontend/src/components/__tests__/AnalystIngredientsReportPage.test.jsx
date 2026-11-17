import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import AnalystIngredientsReportPage from '../AnalystIngredientsReportPage';
import { limpiarFiltroInventario } from '../../utils/filtroInventario';

const INVENTARIO = [
  { id: 1, nombre: 'Pollo entero', categoria: 10, categoria_nombre: 'Pollo', stock_actual: '5', unidad_medida: 'g', costo_unitario: '0.01' },
  { id: 2, nombre: 'Sal fina', categoria: 11, categoria_nombre: 'Condimentos', stock_actual: '9', unidad_medida: 'g', costo_unitario: '0.002' },
  { id: 3, nombre: 'Caja pequeña', categoria: null, categoria_nombre: '', stock_actual: '3', unidad_medida: 'unidad', costo_unitario: '0.1' },
];
const CATEGORIAS = [
  { id: 10, nombre: 'Pollo', activo: true },
  { id: 11, nombre: 'Condimentos', activo: true },
];

function mockCatalogo() {
  global.fetch = vi.fn(() => Promise.resolve({
    ok: true,
    json: () => Promise.resolve({ ok: true, inventory: INVENTARIO, categorias_inventario: CATEGORIAS }),
  }));
}

function montar() {
  return render(<AnalystIngredientsReportPage isMobile={false} onBack={() => {}} onEdit={() => {}} />);
}

describe('Reporte de ingredientes — el filtro sobrevive a entrar a Modificar y volver', () => {
  beforeEach(() => {
    limpiarFiltroInventario();
    mockCatalogo();
  });
  afterEach(() => {
    limpiarFiltroInventario();
    vi.restoreAllMocks();
  });

  it('al volver a abrir el reporte conserva la categoría y la búsqueda elegidas', async () => {
    const primera = montar();
    await screen.findByText('Pollo entero');
    fireEvent.change(screen.getByDisplayValue('Todas las categorías'), { target: { value: '11' } });
    fireEvent.change(screen.getByPlaceholderText(/Buscar por nombre/), { target: { value: 'sal' } });
    expect(screen.queryByText('Pollo entero')).toBeNull();

    // Entrar a Modificar desmonta la pantalla; volver la monta de nuevo.
    primera.unmount();
    montar();

    await screen.findByText('Sal fina');
    expect(screen.getByDisplayValue('Condimentos')).toBeTruthy();
    expect(screen.getByPlaceholderText(/Buscar por nombre/).value).toBe('sal');
    expect(screen.queryByText('Pollo entero')).toBeNull();
    expect(screen.queryByText('Caja pequeña')).toBeNull();
  });

  it('entrando desde el menú (filtro limpiado) empieza sin filtros', async () => {
    const primera = montar();
    await screen.findByText('Pollo entero');
    fireEvent.change(screen.getByDisplayValue('Todas las categorías'), { target: { value: '10' } });
    primera.unmount();

    limpiarFiltroInventario();
    montar();
    await waitFor(() => expect(screen.getByText('Caja pequeña')).toBeTruthy());
    expect(screen.getByText('Pollo entero')).toBeTruthy();
    expect(screen.getByText('Sal fina')).toBeTruthy();
    expect(screen.getByDisplayValue('Todas las categorías')).toBeTruthy();
  });
});

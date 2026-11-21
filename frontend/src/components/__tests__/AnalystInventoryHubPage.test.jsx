import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import AnalystInventoryHubPage from '../AnalystInventoryHubPage';

function mockAlertas(pendientes = 0, enMinimo = 0) {
  global.fetch = vi.fn((url) => Promise.resolve({
    ok: true,
    json: () => Promise.resolve(
      String(url).includes('/api/admin/stock-minimo/')
        ? { ok: true, resumen: { total: enMinimo } }
        : { ok: true, pendientes },
    ),
  }));
}

function montar(extra = {}) {
  const manejadores = {
    onBack: vi.fn(), onCreate: vi.fn(), onViewInventory: vi.fn(), onAdjustInventory: vi.fn(),
    onCategories: vi.fn(), onViewMovements: vi.fn(), onViewAlerts: vi.fn(), onStockMinimo: vi.fn(),
  };
  render(<AnalystInventoryHubPage isMobile={false} {...manejadores} {...extra} />);
  return manejadores;
}

describe('Inventario — menú agrupado', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('muestra las opciones en dos grupos y cada ficha abre su pantalla', () => {
    mockAlertas();
    const m = montar();
    const ingredientes = within(screen.getByRole('region', { name: 'Ingredientes' }));
    const seguimiento = within(screen.getByRole('region', { name: 'Seguimiento' }));

    fireEvent.click(ingredientes.getByRole('button', { name: /Crear ingredientes/ }));
    fireEvent.click(ingredientes.getByRole('button', { name: /Ver inventario actual/ }));
    fireEvent.click(ingredientes.getByRole('button', { name: /Ajuste de inventario/ }));
    fireEvent.click(ingredientes.getByRole('button', { name: /Categorías de inventario/ }));
    fireEvent.click(seguimiento.getByRole('button', { name: /Movimientos del inventario/ }));
    fireEvent.click(seguimiento.getByRole('button', { name: /Stock mínimo/ }));
    fireEvent.click(seguimiento.getByRole('button', { name: /Alertas de precios/ }));
    fireEvent.click(screen.getByRole('button', { name: /Volver a Contabilidad/ }));

    expect(m.onCreate).toHaveBeenCalledTimes(1);
    expect(m.onViewInventory).toHaveBeenCalledTimes(1);
    expect(m.onAdjustInventory).toHaveBeenCalledTimes(1);
    expect(m.onCategories).toHaveBeenCalledTimes(1);
    expect(m.onViewMovements).toHaveBeenCalledTimes(1);
    expect(m.onStockMinimo).toHaveBeenCalledTimes(1);
    expect(m.onViewAlerts).toHaveBeenCalledTimes(1);
    expect(m.onBack).toHaveBeenCalledTimes(1);
  });

  it('avisa cuántos ingredientes están en su stock mínimo', async () => {
    mockAlertas(0, 4);
    montar();
    expect(await screen.findByRole('button', { name: /Stock mínimo, 4 ingredientes en su mínimo/ })).toBeTruthy();
  });

  it('sin ingredientes en su mínimo no muestra el aviso', async () => {
    mockAlertas(0, 0);
    montar();
    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(2));
    expect(screen.getByRole('button', { name: 'Stock mínimo' })).toBeTruthy();
  });

  it('avisa cuántas alertas de precio esperan revisión', async () => {
    mockAlertas(3);
    montar();
    expect(await screen.findByRole('button', { name: /Alertas de precios, 3 alertas pendientes/ })).toBeTruthy();
  });

  it('sin alertas pendientes no muestra el aviso', async () => {
    mockAlertas(0);
    montar();
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    expect(screen.getByRole('button', { name: 'Alertas de precios' })).toBeTruthy();
  });
});

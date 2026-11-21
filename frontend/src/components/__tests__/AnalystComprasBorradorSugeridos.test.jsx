import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import AnalystComprasBorradorPage from '../AnalystComprasBorradorPage';
import { guardarSugeridos, leerSugeridos, limpiarSugeridos } from '../../utils/comprasSugeridas';

const INVENTARIO = [
  { id: 1, nombre: 'Aguacate', unidad_medida: 'g' },
  { id: 2, nombre: 'Cilantro', unidad_medida: 'g' },
  { id: 3, nombre: 'Sal', unidad_medida: 'g' },
];

function mockServidor(detalles = []) {
  let borrador = { id: 1, detalles, total: '0' };
  global.fetch = vi.fn((url, opciones = {}) => {
    if (String(url).includes('/api/admin/catalogo/')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true, inventory: INVENTARIO }) });
    }
    if (String(url).includes('/borrador/agregar/')) {
      const cuerpo = JSON.parse(opciones.body);
      borrador = {
        ...borrador,
        detalles: [...borrador.detalles, { id: 99, ingrediente_id: cuerpo.ingrediente_id, ingrediente_nombre: 'Aguacate', cantidad: cuerpo.cantidad, precio_total: cuerpo.precio_total, unidad_medida: 'g', costo_unitario: '0' }],
      };
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true, borrador }) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true, borrador }) });
  });
}

const SUGERIDOS = [
  { id: 1, nombre: 'Aguacate', unidad: 'g', faltante: '1200' },
  { id: 2, nombre: 'Cilantro', unidad: 'g', faltante: '550' },
  { id: 3, nombre: 'Sal', unidad: 'g', faltante: '0' },
];

describe('Cargar por lote — ingredientes por reponer del stock mínimo', () => {
  beforeEach(() => limpiarSugeridos());
  afterEach(() => {
    limpiarSugeridos();
    vi.restoreAllMocks();
  });

  it('sin lista de reposición no muestra el panel', async () => {
    mockServidor();
    render(<AnalystComprasBorradorPage isMobile={false} onBack={() => {}} />);
    await screen.findByText('Agregar ingrediente');
    expect(screen.queryByText(/Por reponer/)).toBeNull();
  });

  it('muestra los ingredientes por reponer con lo que falta para el mínimo', async () => {
    guardarSugeridos(SUGERIDOS);
    mockServidor();
    render(<AnalystComprasBorradorPage isMobile={false} onBack={() => {}} />);
    expect(await screen.findByText('Por reponer (stock mínimo)')).toBeTruthy();
    expect(screen.getByRole('button', { name: /Aguacate · faltan 1200 g/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /Cilantro · faltan 550 g/ })).toBeTruthy();
    // El que justo está en el mínimo no tiene cantidad que sugerir.
    expect(screen.getByRole('button', { name: 'Sal' })).toBeTruthy();
  });

  it('un clic llena el ingrediente y la cantidad que falta', async () => {
    guardarSugeridos(SUGERIDOS);
    mockServidor();
    render(<AnalystComprasBorradorPage isMobile={false} onBack={() => {}} />);
    fireEvent.click(await screen.findByRole('button', { name: /Cilantro · faltan 550 g/ }));
    expect(screen.getByPlaceholderText(/Ejemplo: Tomate/).value).toBe('Cilantro');
    expect(screen.getByLabelText('Cantidad recibida').value).toBe('550');
  });

  it('no muestra los que ya están en la compra', async () => {
    guardarSugeridos(SUGERIDOS);
    mockServidor([{ id: 7, ingrediente_id: 1, ingrediente_nombre: 'Aguacate', cantidad: '1200', precio_total: '5', unidad_medida: 'g', costo_unitario: '0' }]);
    render(<AnalystComprasBorradorPage isMobile={false} onBack={() => {}} />);
    await screen.findByText('Por reponer (stock mínimo)');
    expect(screen.queryByRole('button', { name: /Aguacate · faltan/ })).toBeNull();
    expect(screen.getByRole('button', { name: /Cilantro · faltan/ })).toBeTruthy();
  });

  it('al agregar el ingrediente a la compra sale de la lista y de lo guardado', async () => {
    guardarSugeridos(SUGERIDOS);
    mockServidor();
    render(<AnalystComprasBorradorPage isMobile={false} onBack={() => {}} />);
    fireEvent.click(await screen.findByRole('button', { name: /Aguacate · faltan/ }));
    fireEvent.change(screen.getByLabelText('Cantidad recibida'), { target: { value: '1500' } });
    fireEvent.change(screen.getByPlaceholderText(/Precio total en \$/), { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: /^Agregar/ }));

    await waitFor(() => expect(screen.queryByRole('button', { name: /Aguacate · faltan/ })).toBeNull());
    expect(leerSugeridos().map((item) => item.id)).toEqual([2, 3]);
  });

  it('«Quitar lista» la borra', async () => {
    guardarSugeridos(SUGERIDOS);
    mockServidor();
    render(<AnalystComprasBorradorPage isMobile={false} onBack={() => {}} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Quitar lista' }));
    expect(screen.queryByText('Por reponer (stock mínimo)')).toBeNull();
    expect(leerSugeridos()).toEqual([]);
  });
});

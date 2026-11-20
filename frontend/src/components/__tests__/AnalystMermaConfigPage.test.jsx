import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import AnalystMermaConfigPage from '../AnalystMermaConfigPage';
import AnalystConfiguracionCosteoPage from '../AnalystConfiguracionCosteoPage';

const AGUACATE = {
  id: 1, nombre: 'aguacate', unidad: 'g', categoria: 'Frutas', contenido_envase: '1000.00', peso_real: '500.00',
  merma_pct: '50.0', factor: '2.00', stock_actual: '120000.00', descuenta_merma: false, aplica: false,
  usos: [
    { tipo: 'receta', nombre: 'Ensalada la vara', cantidad: '80' },
    { tipo: 'subreceta', nombre: 'Guacamole', cantidad: '700' },
  ],
  usos_total: 2,
};
const CEBOLLIN = {
  id: 2, nombre: 'cebollín', unidad: 'g', categoria: '', contenido_envase: '1000.00', peso_real: '500.00',
  merma_pct: '50.0', factor: '2.00', stock_actual: '8000.00', descuenta_merma: true, aplica: true,
  usos: [], usos_total: 0,
};
const LIMON = {
  id: 3, nombre: 'Limón', unidad: 'g', categoria: '', contenido_envase: '1000.00', peso_real: '350.00',
  merma_pct: '65.0', factor: '2.86', stock_actual: '500.00', descuenta_merma: false, aplica: false,
  usos: [], usos_total: 0,
};

const respuesta = (filas) => ({
  ok: true,
  ingredientes: filas,
  resumen: { con_merma: filas.length, activos: filas.filter((f) => f.descuenta_merma).length },
});

function mockServidor(filas = [AGUACATE, CEBOLLIN, LIMON]) {
  let actuales = filas;
  global.fetch = vi.fn((url, opciones = {}) => {
    if (opciones.method === 'POST') {
      const cuerpo = JSON.parse(opciones.body);
      actuales = actuales.map((fila) => (
        cuerpo.ids.includes(fila.id) ? { ...fila, descuenta_merma: cuerpo.descuenta_merma, aplica: cuerpo.descuenta_merma } : fila
      ));
      return Promise.resolve({
        ok: true, json: () => Promise.resolve({ ...respuesta(actuales), message: `${cuerpo.ids.length} ingrediente(s) actualizado(s).` }),
      });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve(respuesta(actuales)) });
  });
}

const montar = () => render(<AnalystMermaConfigPage isMobile={false} onBack={() => {}} />);
const posts = () => global.fetch.mock.calls.filter(([, opciones]) => opciones?.method === 'POST');

describe('Configuración de merma', () => {
  beforeEach(() => mockServidor());
  afterEach(() => vi.restoreAllMocks());

  it('lista los ingredientes con merma, con el envase, el % y lo que se descuenta por cada 500 de receta', async () => {
    montar();
    expect(await screen.findByText('aguacate')).toBeTruthy();
    expect(screen.getByText('cebollín')).toBeTruthy();
    const fila = screen.getByTestId('merma-fila-1');
    expect(fila.textContent).toContain('50%');
    expect(fila.textContent).toContain('500 → 1000 g');
    expect(screen.getByText(/3 con merma · 1 encendido/)).toBeTruthy();
    expect(screen.getByRole('switch', { name: /merma de aguacate/ }).getAttribute('aria-checked')).toBe('false');
    expect(screen.getByRole('switch', { name: /merma de cebollín/ }).getAttribute('aria-checked')).toBe('true');
  });

  it('busca sin importar tildes ni mayúsculas y filtra por estado', async () => {
    montar();
    await screen.findByText('aguacate');
    fireEvent.change(screen.getByLabelText('Buscar ingrediente'), { target: { value: 'CEBOLLIN' } });
    expect(screen.queryByText('aguacate')).toBeNull();
    expect(screen.getByText('cebollín')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Buscar ingrediente'), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText('Filtrar por estado'), { target: { value: 'activos' } });
    expect(screen.queryByText('aguacate')).toBeNull();
    expect(screen.getByText('cebollín')).toBeTruthy();
  });

  it('muestra en qué recetas se usa cada ingrediente', async () => {
    montar();
    await screen.findByText('aguacate');
    fireEvent.click(screen.getByText(/2 usos/));
    expect(screen.getByText('Ensalada la vara')).toBeTruthy();
    expect(screen.getByText('Guacamole')).toBeTruthy();
  });

  it('encender uno pide confirmar, advierte de las recetas y solo envía al confirmar', async () => {
    montar();
    await screen.findByText('aguacate');
    fireEvent.click(screen.getByRole('switch', { name: /merma de aguacate/ }));

    expect(screen.getByText(/Activar el descuento de merma: aguacate/)).toBeTruthy();
    expect(screen.getByText(/descontarán 1000 g del inventario/)).toBeTruthy();
    // La advertencia sobre cómo están escritas las recetas sale en la pantalla y de nuevo en el diálogo.
    expect(screen.getAllByText(/ya limpios/).length).toBeGreaterThanOrEqual(2);
    expect(posts()).toHaveLength(0);

    fireEvent.click(screen.getByRole('button', { name: 'Activar' }));
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(JSON.parse(posts()[0][1].body)).toEqual({ action: 'actualizar', ids: [1], descuenta_merma: true });
    await waitFor(() => expect(screen.getByRole('switch', { name: /merma de aguacate/ }).getAttribute('aria-checked')).toBe('true'));
    expect(screen.getByText(/2 encendidos/)).toBeTruthy();
  });

  it('cancelar el diálogo no cambia nada', async () => {
    montar();
    await screen.findByText('aguacate');
    fireEvent.click(screen.getByRole('switch', { name: /merma de aguacate/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
    expect(posts()).toHaveLength(0);
    expect(screen.getByRole('switch', { name: /merma de aguacate/ }).getAttribute('aria-checked')).toBe('false');
  });

  it('apagar uno envía descuenta_merma en falso', async () => {
    montar();
    await screen.findByText('cebollín');
    fireEvent.click(screen.getByRole('switch', { name: /merma de cebollín/ }));
    expect(screen.getByText(/Apagar el descuento de merma: cebollín/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Apagar' }));
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(JSON.parse(posts()[0][1].body)).toEqual({ action: 'actualizar', ids: [2], descuenta_merma: false });
  });

  it('activa varios a la vez con la selección', async () => {
    montar();
    await screen.findByText('aguacate');
    fireEvent.click(screen.getByLabelText('Seleccionar aguacate'));
    fireEvent.click(screen.getByLabelText('Seleccionar Limón'));
    expect(screen.getByText('2 seleccionado(s)')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Activar el descuento' }));
    expect(screen.getByText(/Activar el descuento de merma en 2 ingredientes/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Activar' }));
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(JSON.parse(posts()[0][1].body)).toEqual({ action: 'actualizar', ids: [1, 3], descuenta_merma: true });
    await waitFor(() => expect(screen.queryByText('2 seleccionado(s)')).toBeNull());
  });

  it('avisa si un ingrediente quedó encendido pero ya no tiene merma', async () => {
    mockServidor([{ ...CEBOLLIN, aplica: false }]);
    montar();
    expect(await screen.findByText(/Ya no tiene merma/)).toBeTruthy();
  });

  it('sin ingredientes con merma explica cómo se configura', async () => {
    mockServidor([]);
    montar();
    expect(await screen.findByText(/Ningún ingrediente tiene merma/)).toBeTruthy();
  });
});

describe('Costeo → botón de merma', () => {
  afterEach(() => vi.restoreAllMocks());

  it('la pantalla de Costeo tiene el botón «Configuración de merma» y lo abre', async () => {
    global.fetch = vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ ok: true, rendimiento_receta_pct: '0', margen_ganancia_defecto_pct: '50', alerta_variacion_costo_pct: '30' }),
    }));
    const alAbrir = vi.fn();
    render(<AnalystConfiguracionCosteoPage isMobile={false} onBack={() => {}} onMerma={alAbrir} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Configuración de merma' }));
    expect(alAbrir).toHaveBeenCalledTimes(1);
  });
});

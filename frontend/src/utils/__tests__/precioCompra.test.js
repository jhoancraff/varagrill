import { describe, expect, it } from 'vitest';
import { calcularCostoNuevo, calcularPrecioCompra, formatearCosto } from '../precioCompra';

describe('calcularPrecioCompra', () => {
  it('g/ml: precio total × peso neto ÷ cantidad (precio de un envase)', () => {
    // 5000 g por $25 en envases de 1000 g: 5 envases, $5 cada uno.
    expect(calcularPrecioCompra({
      unidad: 'g', cantidad: '5000', precio_total: '25', contenido_envase: '1000', peso_real: '900',
    })).toBe('5.00');
    // La plantilla: 20000 g por $170 en envases de 1000 g.
    expect(calcularPrecioCompra({
      unidad: 'g', cantidad: '20000', precio_total: '170', contenido_envase: '1000', peso_real: '900',
    })).toBe('8.50');
  });

  it('unidad: el precio de compra es el precio de una unidad', () => {
    expect(calcularPrecioCompra({
      unidad: 'unidad', cantidad: '24', precio_total: '26', contenido_envase: '355', peso_real: '355',
    })).toBe('1.08');
  });

  it('acepta coma decimal', () => {
    expect(calcularPrecioCompra({
      unidad: 'g', cantidad: '2000', precio_total: '20,5', contenido_envase: '1000', peso_real: '900',
    })).toBe('10.25');
  });

  it('usa los pesos que el ingrediente ya tiene guardados si la fila no los trae', () => {
    expect(calcularPrecioCompra({
      unidad: 'g', cantidad: '2000', precio_total: '20', contenido_envase: '', peso_real: '',
      contenido_envase_actual: '1000.00', peso_real_actual: '900.00',
    })).toBe('10.00');
  });

  it('los pesos de la fila mandan sobre los guardados', () => {
    expect(calcularPrecioCompra({
      unidad: 'g', cantidad: '2000', precio_total: '20', contenido_envase: '500', peso_real: '450',
      contenido_envase_actual: '1000', peso_real_actual: '900',
    })).toBe('5.00');
  });

  it('el costo del ingrediente existente se calcula con su unidad guardada', () => {
    expect(calcularPrecioCompra({
      unidad: 'g', unidad_actual: 'unidad', cantidad: '10', precio_total: '12', contenido_envase: '355', peso_real: '355',
    })).toBe('1.20');
  });

  it('queda vacío mientras falte un dato o sea inválido', () => {
    const base = { unidad: 'g', cantidad: '5000', precio_total: '25', contenido_envase: '1000', peso_real: '900' };
    expect(calcularPrecioCompra({ ...base, cantidad: '' })).toBe('');
    expect(calcularPrecioCompra({ ...base, cantidad: '0' })).toBe('');
    expect(calcularPrecioCompra({ ...base, cantidad: '-3' })).toBe('');
    expect(calcularPrecioCompra({ ...base, precio_total: '' })).toBe('');
    expect(calcularPrecioCompra({ ...base, contenido_envase: '' })).toBe('');
    expect(calcularPrecioCompra({ ...base, peso_real: '' })).toBe('');
    expect(calcularPrecioCompra({ ...base, peso_real: '1200' })).toBe('');
    expect(calcularPrecioCompra({ ...base, precio_total: 'abc' })).toBe('');
  });

  it('un total en 0 (cortesía) da precio de compra 0', () => {
    expect(calcularPrecioCompra({
      unidad: 'g', cantidad: '1000', precio_total: '0', contenido_envase: '1000', peso_real: '1000',
    })).toBe('0.00');
  });
});

describe('calcularCostoNuevo', () => {
  const papeleta = {
    ingrediente_id: 7, unidad: 'g', unidad_actual: 'g', cantidad: '2000', precio_total: '20',
    contenido_envase: '1000', peso_real: '900', contenido_envase_actual: '1000', peso_real_actual: '900',
    precio_compra_actual: '8.00', costo_actual: '0.008889',
  };

  it('costo = precio de compra ÷ peso real, y la variación contra el de hoy', () => {
    const r = calcularCostoNuevo(papeleta, '30');
    expect(r.costoNuevo).toBe(0.011111);
    expect(r.variacion).toBe(25);
    expect(r.alerta).toBe(false);
  });

  it('marca la alerta cuando la variación llega al umbral configurado, sube o baja', () => {
    expect(calcularCostoNuevo({ ...papeleta, precio_total: '30' }, '30').alerta).toBe(true);
    expect(calcularCostoNuevo({ ...papeleta, precio_total: '8' }, '30')).toMatchObject({ variacion: -50.01, alerta: true });
    expect(calcularCostoNuevo({ ...papeleta, precio_total: '30' }, '100').alerta).toBe(false);
  });

  it('usa los pesos guardados cuando la fila no los trae', () => {
    const r = calcularCostoNuevo({ ...papeleta, contenido_envase: '', peso_real: '' }, '30');
    expect(r.costoNuevo).toBe(0.011111);
  });

  it('un ingrediente nuevo muestra el costo pero no hay con qué compararlo', () => {
    const r = calcularCostoNuevo({
      unidad: 'g', cantidad: '5000', precio_total: '25', contenido_envase: '1000', peso_real: '900',
    }, '30');
    expect(r).toEqual({ costoNuevo: 0.005556, costoActual: null, variacion: null, alerta: false });
  });

  it('sin pesos usa total ÷ cantidad en un ingrediente existente', () => {
    const r = calcularCostoNuevo({
      ingrediente_id: 3, unidad: 'g', cantidad: '1000', precio_total: '2', costo_actual: '0.001',
    }, '30');
    expect(r).toMatchObject({ costoNuevo: 0.002, variacion: 100, alerta: true });
  });

  it('sin precio total o sin cantidad no cambia el costo', () => {
    expect(calcularCostoNuevo({ ...papeleta, precio_total: '' }, '30').costoNuevo).toBeNull();
    expect(calcularCostoNuevo({ ...papeleta, cantidad: '' }, '30').costoNuevo).toBeNull();
  });
});

describe('formatearCosto', () => {
  it('muestra hasta 6 decimales sin ceros de sobra y con 2 como mínimo', () => {
    expect(formatearCosto(0.0094444)).toBe('0.009444');
    expect(formatearCosto(1.5)).toBe('1.50');
    expect(formatearCosto(0.002)).toBe('0.002');
    expect(formatearCosto(8)).toBe('8.00');
    expect(formatearCosto(null)).toBe('');
  });
});

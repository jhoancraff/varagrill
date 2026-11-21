import { afterEach, describe, expect, it } from 'vitest';
import { guardarSugeridos, leerSugeridos, limpiarSugeridos } from '../comprasSugeridas';

describe('comprasSugeridas', () => {
  afterEach(() => limpiarSugeridos());

  it('guarda y lee los ingredientes por reponer', () => {
    guardarSugeridos([{ id: 1, nombre: 'Aguacate', unidad: 'g', faltante: '1200' }]);
    expect(leerSugeridos()).toEqual([{ id: 1, nombre: 'Aguacate', unidad: 'g', faltante: '1200' }]);
  });

  it('descarta lo que no es un ingrediente válido y completa los campos que falten', () => {
    guardarSugeridos([{ id: 1, nombre: 'Sal' }, { id: 'x', nombre: 'Mal' }, { id: 2, nombre: '  ' }, null]);
    expect(leerSugeridos()).toEqual([{ id: 1, nombre: 'Sal', unidad: '', faltante: '' }]);
  });

  it('limpiar deja la lista vacía y un contenido dañado no rompe', () => {
    guardarSugeridos([{ id: 1, nombre: 'Sal' }]);
    limpiarSugeridos();
    expect(leerSugeridos()).toEqual([]);
    window.sessionStorage.setItem('vg.compras.sugeridos', '{no es json');
    expect(leerSugeridos()).toEqual([]);
  });
});

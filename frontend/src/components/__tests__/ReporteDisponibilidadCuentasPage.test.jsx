import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import ReporteDisponibilidadCuentasPage from '../ReporteDisponibilidadCuentasPage';

function mockRespuesta(extra = {}) {
  global.fetch = vi.fn(() => Promise.resolve({
    ok: true,
    json: () => Promise.resolve({
      ok: true, fecha: '2026-11-14', tasa_bcv: '500.0000', cuentas: [], bancos: [],
      total_disponible: '460.00', total_por_acreditar: '0', pos_por_cobrar: null, ...extra,
    }),
  }));
}

async function totalGlobal() {
  const titulo = await screen.findByText(/Disponibilidad global en dólares/);
  return within(titulo.closest('section'));
}

describe('Disponibilidad diaria — total global en dólares', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('muestra solo el total en dólares (bancos en Bs convertidos + cuentas en dólares + efectivo) y la tasa usada', async () => {
    mockRespuesta({ total_disponible: '9581.2788' });
    render(<ReporteDisponibilidadCuentasPage isMobile={false} onBack={() => {}} />);
    const cuadro = await totalGlobal();
    expect(cuadro.getByText('$9.581,28')).toBeTruthy();
    expect(cuadro.getByText(/Bs\. 500,00 \/ \$/)).toBeTruthy();
    // no hay cuadro detallado: nada de filas por banco ni de grupos
    expect(screen.queryByText('Bancos en bolívares')).toBeNull();
    expect(screen.queryByText('Cuentas en dólares')).toBeNull();
  });

  it('avisa lo que está por acreditar en los puntos de venta y que no se incluye en el total', async () => {
    mockRespuesta({ total_por_acreditar: '35.50' });
    render(<ReporteDisponibilidadCuentasPage isMobile={false} onBack={() => {}} />);
    const cuadro = await totalGlobal();
    expect(cuadro.getByText(/No incluye \$35,50 por acreditar/)).toBeTruthy();
  });

  it('sin tasa del día avisa que los bolívares se cuentan con su valor histórico', async () => {
    mockRespuesta({ tasa_bcv: null });
    render(<ReporteDisponibilidadCuentasPage isMobile={false} onBack={() => {}} />);
    const cuadro = await totalGlobal();
    expect(cuadro.getByText(/No hay tasa BCV registrada/)).toBeTruthy();
  });
});

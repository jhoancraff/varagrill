import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import ComprobantePagoPage from '../ComprobantePagoPage';
import { formatBs } from '../../utils/currency';

// La tasa "en vivo" que devolvería useExchangeRate() en este momento — deliberadamente
// distinta de la tasa congelada del abono, para poder distinguir en las aserciones cuál
// de las dos usó el componente.
const TASA_EN_VIVO = 800;
const TASA_CONGELADA = '650.0000';

vi.mock('../../hooks/useExchangeRate', () => ({
  default: () => TASA_EN_VIVO,
}));

function mockFetchSecuencia({ documentoField, documento }) {
  global.fetch = vi.fn((url) => {
    if (String(url).includes('/datos-fiscales/')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ ok: true, datos_fiscales: { nombre_comercial: 'VaraGrill' } }),
      });
    }
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ ok: true, [documentoField]: documento }),
    });
  });
}

describe('ComprobantePagoPage — origen de la tasa de cambio', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('usa tasa_cambio_referencia del abono cuando está presente, ignorando useExchangeRate()', async () => {
    const documento = {
      id: 1,
      total: '100.00',
      proveedor_nombre: 'Proveedor X',
      numero_factura_proveedor: 'F-001',
      abonos: [
        {
          id: 10,
          monto: '100.00',
          fecha_pago: '2026-01-01T10:00:00Z',
          metodo_pago: 'Efectivo',
          tasa_cambio_referencia: TASA_CONGELADA,
          creado_por: 'admin',
        },
      ],
    };
    mockFetchSecuencia({ documentoField: 'compra', documento });

    const { container } = render(
      <ComprobantePagoPage isMobile={false} onBack={() => {}} tipo="compra" documentoId={1} abonoId={10} />,
    );

    const bsConTasaCongelada = formatBs('100.00', TASA_CONGELADA);
    const bsConTasaEnVivo = formatBs('100.00', TASA_EN_VIVO);

    await waitFor(() => {
      expect(container.textContent).toContain(bsConTasaCongelada);
    });
    // La tasa en vivo (mockeada, distinta) nunca debe aparecer — si apareciera,
    // significaría que el componente ignoró tasa_cambio_referencia del abono.
    expect(container.textContent).not.toContain(bsConTasaEnVivo);
  });

  it('usa la tasa en vivo de useExchangeRate() cuando el abono no tiene tasa_cambio_referencia (borrador/legacy)', async () => {
    const documento = {
      id: 2,
      total: '50.00',
      categoria_nombre: 'Servicios',
      descripcion: 'Internet',
      abonos: [
        {
          id: 20,
          monto: '50.00',
          fecha_pago: '2026-01-02T10:00:00Z',
          metodo_pago: 'Efectivo',
          tasa_cambio_referencia: null,
          creado_por: 'admin',
        },
      ],
    };
    mockFetchSecuencia({ documentoField: 'gasto', documento });

    const { container } = render(
      <ComprobantePagoPage isMobile={false} onBack={() => {}} tipo="gasto" documentoId={2} abonoId={20} />,
    );

    const bsConTasaEnVivo = formatBs('50.00', TASA_EN_VIVO);

    await waitFor(() => {
      expect(container.textContent).toContain(bsConTasaEnVivo);
    });
  });
});

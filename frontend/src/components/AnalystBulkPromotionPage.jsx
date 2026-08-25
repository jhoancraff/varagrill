import { useEffect, useMemo, useState } from 'react';
import BsAmount from './BsAmount';
import UnsavedChangesModal from './UnsavedChangesModal';
import useExchangeRate from '../hooks/useExchangeRate';
import useUnsavedChangesGuard from '../hooks/useUnsavedChangesGuard';

const emptyForm = {
  tipo_descuento: 'porcentaje',
  valor_descuento: '',
  duracion_dias: '',
  descripcion: '',
};

function AnalystBulkPromotionPage({ isMobile, isAdmin, productIds, onBack }) {
  const tasaCambio = useExchangeRate();
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [message, setMessage] = useState('');
  const [result, setResult] = useState(null);
  const { guard, isConfirmOpen, confirmLeave, cancelLeave, markClean } = useUnsavedChangesGuard(form);

  const requestedIds = useMemo(
    () => (productIds || '')
      .split(',')
      .map((value) => Number(value))
      .filter((value) => Number.isFinite(value)),
    [productIds],
  );

  useEffect(() => {
    if (!isAdmin) {
      setLoading(false);
      return;
    }

    const loadProducts = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/admin/promociones/', {
          credentials: 'include',
          cache: 'no-store',
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || 'No se pudieron cargar los productos seleccionados.');
        }
        const allProducts = Array.isArray(data.products) ? data.products : [];
        const idSet = new Set(requestedIds);
        setProducts(allProducts.filter((product) => idSet.has(product.id)));
      } catch (error) {
        setMessage(error.message || 'No se pudieron cargar los productos seleccionados.');
      } finally {
        setLoading(false);
      }
    };

    loadProducts();
  }, [isAdmin, requestedIds]);

  const handleChange = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const previewRows = useMemo(() => {
    const discountValue = Number(form.valor_descuento);
    return products.map((product) => {
      const basePrice = Number(product.precio_venta);
      let finalPrice = null;
      if (Number.isFinite(basePrice) && Number.isFinite(discountValue) && discountValue > 0) {
        finalPrice = form.tipo_descuento === 'porcentaje'
          ? basePrice - (basePrice * discountValue) / 100
          : basePrice - discountValue;
        finalPrice = finalPrice > 0 ? finalPrice : 0;
      }
      return { ...product, finalPrice };
    });
  }, [products, form.tipo_descuento, form.valor_descuento]);

  const eligibleCount = products.filter((product) => !product.promocion_activa).length;

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (products.length === 0) {
      setMessage('No hay productos válidos seleccionados.');
      return;
    }
    if (!form.valor_descuento || Number(form.valor_descuento) <= 0) {
      setMessage('Debes indicar un valor de descuento mayor a cero.');
      return;
    }
    if (!form.duracion_dias || Number(form.duracion_dias) <= 0) {
      setMessage('Debes indicar cuántos días durará la promoción.');
      return;
    }

    setSaving(true);
    setResult(null);
    try {
      const response = await fetch('/api/admin/promociones/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'create_bulk',
          producto_ids: products.map((product) => product.id),
          tipo_descuento: form.tipo_descuento,
          valor_descuento: form.valor_descuento,
          duracion_dias: form.duracion_dias,
          descripcion: form.descripcion,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        setMessage(data.message || 'No se pudo guardar la promoción masiva.');
        setResult(data);
        return;
      }

      setMessage(data.message || 'Promociones creadas correctamente.');
      setResult(data);
      setForm(emptyForm);
      markClean(emptyForm);
    } catch (error) {
      setMessage(error.message || 'No se pudo guardar la promoción masiva.');
    } finally {
      setSaving(false);
    }
  };

  if (!isAdmin) {
    return (
      <section style={containerStyle(isMobile)}>
        <div style={badgeStyle}>Promoción masiva</div>
        <h2 style={titleStyle(isMobile)}>Acceso restringido</h2>
        <div style={noticeStyle}>Solo el rol Administrador puede crear promociones.</div>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          Volver al reporte
        </button>
      </section>
    );
  }

  return (
    <section style={containerStyle(isMobile)}>
      <div style={badgeStyle}>Promoción masiva</div>
      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Aplicar el mismo descuento a varios productos</h2>
          <p style={subtitleStyle}>
            Define un solo descuento y una sola duración: se aplicará a todos los productos seleccionados de una vez.
          </p>
        </div>
      </div>

      {message ? <div style={noticeStyle}>{message}</div> : null}

      {result?.omitidas?.length > 0 ? (
        <div style={warningStyle}>
          {result.omitidas.length} producto(s) omitido(s):
          <ul style={omittedListStyle}>
            {result.omitidas.map((item) => (
              <li key={`omitido-${item.id}`}>{item.nombre || `Producto #${item.id}`} — {item.motivo}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {loading ? <div style={emptyStateStyle}>Cargando productos seleccionados...</div> : null}

      {!loading && products.length === 0 ? (
        <div style={emptyStateStyle}>No se encontraron productos válidos para esta selección.</div>
      ) : null}

      {!loading && products.length > 0 ? (
        <form onSubmit={handleSubmit} style={panelStyle}>
          <div style={sectionTitleStyle}>
            {products.length} producto(s) seleccionado(s) · {eligibleCount} recibirán la promoción
          </div>

          <div style={tableWrapStyle}>
            <div style={tableStyle}>
              <div style={tableHeadStyle}>Producto</div>
              <div style={tableHeadStyle}>Precio actual</div>
              <div style={tableHeadStyle}>Precio con descuento</div>
              <div style={tableHeadStyle}>Estado</div>

              {previewRows.map((product) => (
                <>
                  <div key={`name-${product.id}`} style={tableCellPrimaryStyle}>{product.nombre}</div>
                  <div key={`price-${product.id}`} style={tableCellStyle}>
                    ${product.precio_venta}
                    <BsAmount amountUsd={product.precio_venta} tasa={tasaCambio} />
                  </div>
                  <div key={`final-${product.id}`} style={tableCellStyle}>
                    {product.finalPrice !== null ? (
                      <>
                        ${product.finalPrice.toFixed(2)}
                        <BsAmount amountUsd={product.finalPrice} tasa={tasaCambio} />
                      </>
                    ) : '—'}
                  </div>
                  <div key={`status-${product.id}`} style={tableCellStyle}>
                    <span style={statusBadgeStyle(product.promocion_activa)}>
                      {product.promocion_activa ? 'Se omitirá: ya tiene promoción' : 'Recibirá la promoción'}
                    </span>
                  </div>
                </>
              ))}
            </div>
          </div>

          <div style={formGridStyle(isMobile)}>
            <label style={fieldStyle}>
              <span style={labelStyle}>Tipo de descuento</span>
              <select
                value={form.tipo_descuento}
                onChange={(event) => handleChange('tipo_descuento', event.target.value)}
                style={inputStyle}
              >
                <option value="porcentaje">Porcentaje</option>
                <option value="monto_fijo">Monto fijo</option>
              </select>
            </label>

            <label style={fieldStyle}>
              <span style={labelStyle}>
                {form.tipo_descuento === 'porcentaje' ? 'Porcentaje de descuento (%)' : 'Monto de descuento ($)'}
              </span>
              <input
                type="number"
                min="0"
                step="0.01"
                value={form.valor_descuento}
                onChange={(event) => handleChange('valor_descuento', event.target.value)}
                style={inputStyle}
                placeholder={form.tipo_descuento === 'porcentaje' ? 'Ej. 5' : 'Ej. 1.50'}
              />
            </label>

            <label style={fieldStyle}>
              <span style={labelStyle}>¿Cuántos días durará la promoción?</span>
              <input
                type="number"
                min="1"
                step="1"
                value={form.duracion_dias}
                onChange={(event) => handleChange('duracion_dias', event.target.value)}
                style={inputStyle}
                placeholder="Ej. 7"
              />
            </label>

            <label style={{ ...fieldStyle, gridColumn: isMobile ? 'auto' : '1 / -1' }}>
              <span style={labelStyle}>Descripción (opcional)</span>
              <textarea
                value={form.descripcion}
                onChange={(event) => handleChange('descripcion', event.target.value)}
                style={textareaStyle}
                className="promotion-dark-textarea"
                rows={3}
                placeholder="Notas visibles solo para el equipo administrativo"
              />
            </label>
          </div>

          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <button type="submit" style={primaryButtonStyle} disabled={saving}>
              {saving ? 'Guardando...' : `Aplicar a ${eligibleCount} producto(s)`}
            </button>
            <button type="button" onClick={() => guard(onBack)} style={secondaryButtonStyle}>
              Volver al reporte
            </button>
          </div>
        </form>
      ) : null}

      <UnsavedChangesModal open={isConfirmOpen} onConfirm={confirmLeave} onCancel={cancelLeave} />
    </section>
  );
}

const containerStyle = (isMobile) => ({
  display: 'grid',
  gap: 18,
  padding: isMobile ? 6 : 10,
});

const badgeStyle = {
  display: 'inline-flex',
  width: 'fit-content',
  padding: '7px 12px',
  borderRadius: 999,
  background: 'rgba(255, 163, 163, 0.12)',
  color: '#ffb5b5',
  fontSize: 12,
  fontWeight: 800,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
};

const titleStyle = (isMobile) => ({
  margin: 0,
  color: '#fff',
  fontSize: isMobile ? 28 : 34,
});

const subtitleStyle = {
  margin: '8px 0 0',
  color: '#d2c3c3',
  lineHeight: 1.6,
  maxWidth: 760,
};

const headerRowStyle = (isMobile) => ({
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: isMobile ? 'flex-start' : 'center',
  gap: 14,
  flexDirection: isMobile ? 'column' : 'row',
});

const panelStyle = {
  display: 'grid',
  gap: 16,
  padding: '20px 18px',
  borderRadius: 24,
  border: '1px solid rgba(255, 255, 255, 0.1)',
  background: 'linear-gradient(180deg, rgba(20, 10, 10, 0.95) 0%, rgba(8, 8, 8, 0.98) 100%)',
};

const sectionTitleStyle = {
  color: '#fff',
  fontSize: 17,
  fontWeight: 700,
};

const tableWrapStyle = {
  overflowX: 'auto',
};

const tableStyle = {
  display: 'grid',
  gridTemplateColumns: 'minmax(180px, 1fr) minmax(140px, 0.7fr) minmax(160px, 0.8fr) minmax(220px, 1fr)',
  alignItems: 'stretch',
  border: '1px solid rgba(255, 255, 255, 0.08)',
  borderRadius: 18,
  overflow: 'hidden',
  minWidth: 760,
};

const tableHeadStyle = {
  padding: '14px 16px',
  background: 'rgba(255, 255, 255, 0.06)',
  color: '#ffb0b0',
  fontSize: 12,
  fontWeight: 800,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
  borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
};

const tableCellStyle = {
  padding: '16px',
  borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
  color: '#f2e6e6',
  display: 'grid',
  alignContent: 'center',
  gap: 4,
};

const tableCellPrimaryStyle = {
  ...tableCellStyle,
  background: 'rgba(255, 255, 255, 0.02)',
  fontWeight: 700,
  color: '#fff',
};

const statusBadgeStyle = (isActive) => ({
  display: 'inline-flex',
  width: 'fit-content',
  padding: '5px 10px',
  borderRadius: 999,
  fontSize: 12,
  fontWeight: 700,
  color: isActive ? '#ffd8d8' : '#c8ffd8',
  background: isActive ? 'rgba(200, 60, 60, 0.18)' : 'rgba(70, 200, 120, 0.18)',
  border: isActive ? '1px solid rgba(220, 120, 120, 0.4)' : '1px solid rgba(120, 220, 160, 0.4)',
});

const formGridStyle = (isMobile) => ({
  display: 'grid',
  gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 1fr))',
  gap: 12,
});

const fieldStyle = {
  display: 'grid',
  gap: 6,
};

const labelStyle = {
  color: '#f0b4b4',
  fontSize: 13,
  fontWeight: 700,
};

const inputStyle = {
  width: '100%',
  boxSizing: 'border-box',
  borderRadius: 14,
  border: '1px solid rgba(255, 255, 255, 0.14)',
  background: '#161010',
  padding: '11px 12px',
  color: '#fff4f4',
  fontSize: 14,
};

const textareaStyle = {
  ...inputStyle,
  resize: 'vertical',
};

const emptyStateStyle = {
  minHeight: 80,
  display: 'grid',
  placeItems: 'center',
  borderRadius: 18,
  border: '1px dashed rgba(255, 255, 255, 0.12)',
  color: '#c8bbbb',
};

const noticeStyle = {
  padding: '12px 14px',
  borderRadius: 16,
  border: '1px solid rgba(255, 145, 145, 0.22)',
  background: 'rgba(255, 98, 98, 0.12)',
  color: '#ffd8d8',
};

const warningStyle = {
  padding: '12px 14px',
  borderRadius: 16,
  border: '1px solid rgba(255, 200, 120, 0.3)',
  background: 'rgba(255, 170, 60, 0.1)',
  color: '#ffe1b8',
};

const omittedListStyle = {
  margin: '8px 0 0',
  paddingLeft: 18,
  display: 'grid',
  gap: 4,
};

const primaryButtonStyle = {
  border: 'none',
  borderRadius: 999,
  padding: '11px 18px',
  background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
};

const secondaryButtonStyle = {
  border: '1px solid rgba(255, 255, 255, 0.14)',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'rgba(255, 255, 255, 0.04)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
};

const backButtonStyle = {
  justifySelf: 'flex-start',
  border: '1px solid rgba(255, 255, 255, 0.14)',
  borderRadius: 999,
  padding: '11px 18px',
  background: 'rgba(255, 255, 255, 0.04)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
};

export default AnalystBulkPromotionPage;
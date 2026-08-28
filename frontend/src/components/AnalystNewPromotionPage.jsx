import { useEffect, useMemo, useState } from 'react';
import BsAmount from './BsAmount';
import UnsavedChangesModal from './UnsavedChangesModal';
import Toast from './Toast';
import useExchangeRate from '../hooks/useExchangeRate';
import useUnsavedChangesGuard from '../hooks/useUnsavedChangesGuard';
import useToast from '../hooks/useToast';

const emptyForm = {
  titulo: '',
  descripcion: '',
  tipo_descuento: 'porcentaje',
  valor_descuento: '',
  duracion_dias: '',
};

function AnalystNewPromotionPage({ isMobile, isAdmin, productId, onBack }) {
  const tasaCambio = useExchangeRate();
  const [product, setProduct] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const { toast, showSuccess, showError, hideToast } = useToast();
  const { guard, isConfirmOpen, confirmLeave, cancelLeave, markClean } = useUnsavedChangesGuard(form);

  const isEditMode = Boolean(product?.promocion);

  const loadProduct = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/admin/promociones/', {
        credentials: 'include',
        cache: 'no-store',
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo cargar el producto seleccionado.');
      }
      const products = Array.isArray(data.products) ? data.products : [];
      const found = products.find((item) => String(item.id) === String(productId)) || null;
      setProduct(found);
      if (found?.promocion) {
        const loadedForm = {
          titulo: found.promocion.titulo || `Promoción ${found.nombre}`,
          descripcion: found.promocion.descripcion || '',
          tipo_descuento: found.promocion.tipo_descuento || 'porcentaje',
          valor_descuento: found.promocion.valor_descuento || '',
          duracion_dias: String(found.promocion.duracion_dias || ''),
        };
        setForm(loadedForm);
        markClean(loadedForm);
      } else if (found) {
        const loadedForm = { ...emptyForm, titulo: `Promoción ${found.nombre}` };
        setForm(loadedForm);
        markClean(loadedForm);
      }
    } catch (error) {
      showError(error.message || 'No se pudo cargar el producto seleccionado.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!isAdmin) {
      setLoading(false);
      return;
    }

    loadProduct();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin, productId]);

  const handleChange = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const previewPrice = useMemo(() => {
    if (!product) {
      return null;
    }
    const basePrice = Number(product.precio_venta);
    const discountValue = Number(form.valor_descuento);
    if (!Number.isFinite(basePrice) || !Number.isFinite(discountValue) || discountValue <= 0) {
      return null;
    }
    const finalPrice = form.tipo_descuento === 'porcentaje'
      ? basePrice - (basePrice * discountValue) / 100
      : basePrice - discountValue;
    return finalPrice > 0 ? finalPrice : 0;
  }, [product, form.tipo_descuento, form.valor_descuento]);

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (!product) {
      showError('No hay un producto válido seleccionado.');
      return;
    }
    if (!form.valor_descuento || Number(form.valor_descuento) <= 0) {
      showError('Debes indicar un valor de descuento mayor a cero.');
      return;
    }
    if (!form.duracion_dias || Number(form.duracion_dias) <= 0) {
      showError('Debes indicar cuántos días durará la promoción.');
      return;
    }

    setSaving(true);
    try {
      const response = await fetch('/api/admin/promociones/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(isEditMode ? {
          action: 'update',
          id: product.promocion.id,
          titulo: form.titulo,
          descripcion: form.descripcion,
          tipo_descuento: form.tipo_descuento,
          valor_descuento: form.valor_descuento,
          duracion_dias: form.duracion_dias,
        } : {
          action: 'create',
          producto_id: product.id,
          titulo: form.titulo,
          descripcion: form.descripcion,
          tipo_descuento: form.tipo_descuento,
          valor_descuento: form.valor_descuento,
          duracion_dias: form.duracion_dias,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo guardar la promoción.');
      }

      showSuccess(data.message || (isEditMode ? 'Promoción actualizada correctamente.' : 'Promoción creada correctamente.'));
      await loadProduct();
    } catch (error) {
      showError(error.message || 'No se pudo guardar la promoción.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!product?.promocion) {
      return;
    }
    if (!window.confirm(`¿Deseas eliminar la promoción de ${product.nombre}?`)) {
      return;
    }

    setSaving(true);
    try {
      const response = await fetch('/api/admin/promociones/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'delete', id: product.promocion.id }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo eliminar la promoción.');
      }
      showSuccess(data.message || 'Promoción eliminada correctamente.');
      onBack();
    } catch (error) {
      showError(error.message || 'No se pudo eliminar la promoción.');
    } finally {
      setSaving(false);
    }
  };

  if (!isAdmin) {
    return (
      <section style={containerStyle(isMobile)}>
        <div style={badgeStyle}>Nueva promoción</div>
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
      <div style={badgeStyle}>{isEditMode ? 'Editar promoción' : 'Nueva promoción'}</div>
      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>{isEditMode ? 'Actualizar descuento' : 'Aplicar descuento'}</h2>
          <p style={subtitleStyle}>
            {isEditMode
              ? 'Modifica el descuento o la duración: el cambio aplica de inmediato para este producto.'
              : 'Define el descuento y cuántos días estará vigente la promoción para este producto.'}
          </p>
        </div>
      </div>

      <Toast toast={toast} onClose={hideToast} />

      {loading ? <div style={emptyStateStyle}>Cargando producto...</div> : null}

      {!loading && !product ? (
        <div style={emptyStateStyle}>El producto seleccionado no existe o ya no está disponible.</div>
      ) : null}

      {!loading && product ? (
        <form onSubmit={handleSubmit} style={panelStyle}>
          <div style={productCardStyle}>
            <div style={productNameStyle}>{product.nombre}</div>
            <div style={productMetaStyle}>
              {product.categoria || 'Sin categoría'} · Precio actual ${product.precio_venta}
              <BsAmount amountUsd={product.precio_venta} tasa={tasaCambio} />
            </div>
          </div>

          <div style={formGridStyle(isMobile)}>
            <label style={fieldStyle}>
              <span style={labelStyle}>Título de la promoción</span>
              <input
                value={form.titulo}
                onChange={(event) => handleChange('titulo', event.target.value)}
                style={inputStyle}
                placeholder="Ej. Descuento especial de temporada"
              />
            </label>

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
                placeholder={form.tipo_descuento === 'porcentaje' ? 'Ej. 15' : 'Ej. 2.50'}
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

          {previewPrice !== null ? (
            <div style={previewCardStyle}>
              <div style={previewLabelStyle}>Precio con descuento</div>
              <div style={previewValueStyle}>
                ${previewPrice.toFixed(2)}
                <BsAmount amountUsd={previewPrice} tasa={tasaCambio} />
              </div>
            </div>
          ) : null}

          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <button type="submit" style={primaryButtonStyle} disabled={saving}>
              {saving ? 'Guardando...' : isEditMode ? 'Guardar cambios' : 'Guardar promoción'}
            </button>
            {isEditMode ? (
              <button type="button" onClick={handleDelete} style={dangerButtonStyle} disabled={saving}>
                Eliminar promoción
              </button>
            ) : null}
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

const productCardStyle = {
  display: 'grid',
  gap: 4,
  padding: '14px 16px',
  borderRadius: 16,
  background: 'rgba(255, 255, 255, 0.04)',
  border: '1px solid rgba(255, 255, 255, 0.08)',
};

const productNameStyle = {
  color: '#fff',
  fontWeight: 700,
  fontSize: 18,
};

const productMetaStyle = {
  color: '#d2c4c4',
  fontSize: 13,
};

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

const previewCardStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '14px 16px',
  borderRadius: 16,
  background: 'rgba(70, 200, 120, 0.1)',
  border: '1px solid rgba(120, 220, 160, 0.3)',
};

const previewLabelStyle = {
  color: '#c8ffd8',
  fontWeight: 700,
};

const previewValueStyle = {
  color: '#fff',
  fontWeight: 800,
  fontSize: 20,
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

const dangerButtonStyle = {
  border: '1px solid rgba(255, 126, 126, 0.4)',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'rgba(145, 33, 33, 0.25)',
  color: '#ffd3d3',
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

export default AnalystNewPromotionPage;
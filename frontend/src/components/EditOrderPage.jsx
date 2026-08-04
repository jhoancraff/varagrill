import { useEffect, useMemo, useState } from 'react';

function EditOrderPage({ isMobile, mesas, products, loadingData, orderId, onBack }) {
  const [orderHeader, setOrderHeader] = useState({
    mesaId: '',
    tipoPedido: 'local',
    cliente: '',
    notas: '',
  });
  const [lines, setLines] = useState([]);
  const [originalEstado, setOriginalEstado] = useState('');
  const [loadingOrder, setLoadingOrder] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [feedbackType, setFeedbackType] = useState('success');
  const [catalogType, setCatalogType] = useState('Comida');
  const [isTablet, setIsTablet] = useState(() => window.matchMedia('(max-width: 1100px)').matches);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [promotionsByProductId, setPromotionsByProductId] = useState({});

  const catalogOptions = useMemo(() => (
    [
      { key: 'Comida', label: 'Comida' },
      { key: 'Jugos', label: 'Jugos' },
      { key: 'Licores', label: 'Licores' },
      { key: 'Todos', label: 'Todos' },
    ]
  ), []);

  useEffect(() => {
    let cancelled = false;

    const loadPromotions = async () => {
      try {
        const response = await fetch('/api/promociones/', {
          credentials: 'include',
          cache: 'no-store',
        });
        const data = await response.json();
        if (!response.ok || !data.ok || cancelled) {
          return;
        }
        const map = {};
        (Array.isArray(data.promotions) ? data.promotions : []).forEach((promotion) => {
          map[promotion.producto_id] = promotion;
        });
        setPromotionsByProductId(map);
      } catch (error) {
        // Sin promociones disponibles no bloquea la edicion del pedido.
      }
    };

    loadPromotions();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    const loadOrder = async () => {
      setLoadingOrder(true);
      setLoadError('');
      try {
        const response = await fetch(`/api/pedidos/${orderId}/`, {
          credentials: 'include',
          cache: 'no-store',
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || 'No se pudo cargar el pedido.');
        }
        if (cancelled) {
          return;
        }

        const pedido = data.pedido;
        setOriginalEstado(pedido.estado);
        setOrderHeader({
          mesaId: pedido.mesa_id ? String(pedido.mesa_id) : '',
          tipoPedido: pedido.tipo_pedido,
          cliente: pedido.cliente_nombre || '',
          notas: pedido.notas || '',
        });
        setLines(pedido.items.length > 0 ? pedido.items.map((item) => ({
          id: `line-${item.id}`,
          productId: String(item.product_id),
          productName: item.producto_nombre,
          search: item.producto_nombre,
          quantity: item.cantidad,
          notes: item.notas || '',
          isOpen: false,
        })) : [createEmptyLine()]);
      } catch (error) {
        if (!cancelled) {
          setLoadError(error.message || 'No se pudo cargar el pedido.');
        }
      } finally {
        if (!cancelled) {
          setLoadingOrder(false);
        }
      }
    };

    loadOrder();
    return () => {
      cancelled = true;
    };
  }, [orderId]);

  useEffect(() => {
    const tabletQuery = window.matchMedia('(max-width: 1100px)');
    const handleViewportChange = (event) => setIsTablet(event.matches);
    setIsTablet(tabletQuery.matches);
    tabletQuery.addEventListener('change', handleViewportChange);
    return () => tabletQuery.removeEventListener('change', handleViewportChange);
  }, []);

  const isCompact = isMobile || isTablet;
  const canEdit = originalEstado === 'pendiente';

  const subtotal = useMemo(
    () => lines.reduce((accumulator, line) => accumulator + getLineSubtotal(line, products, promotionsByProductId), 0),
    [lines, products, promotionsByProductId],
  );

  const selectedMesa = useMemo(
    () => mesas.find((mesa) => String(mesa.id) === String(orderHeader.mesaId)),
    [mesas, orderHeader.mesaId],
  );

  const categoryFilteredProducts = useMemo(
    () => products.filter((product) => matchesCatalogType(product, catalogType)),
    [products, catalogType],
  );

  useEffect(() => {
    setFeedback('');
    setFeedbackType('success');
    setLines((current) => current.map((line) => ({ ...line, isOpen: false })));
  }, [catalogType]);

  const handleLineProductSearch = (lineId, search) => {
    setLines((current) => current.map((line) => (
      line.id === lineId ? { ...line, search, isOpen: true } : line
    )));
  };

  const handleSelectProduct = (lineId, product) => {
    setLines((current) => current.map((line) => (
      line.id === lineId
        ? {
          ...line,
          productId: product.id,
          productName: product.nombre,
          search: product.nombre,
          isOpen: false,
        }
        : line
    )));
  };

  const handleLineQtyChange = (lineId, quantity) => {
    const parsed = Number(quantity);
    setLines((current) => current.map((line) => (
      line.id === lineId
        ? { ...line, quantity: Number.isFinite(parsed) && parsed > 0 ? parsed : 1 }
        : line
    )));
  };

  const handleLineNotesChange = (lineId, notes) => {
    setLines((current) => current.map((line) => (
      line.id === lineId ? { ...line, notes } : line
    )));
  };

  const handleCloseOptions = (lineId) => {
    setLines((current) => current.map((line) => (
      line.id === lineId ? { ...line, isOpen: false } : line
    )));
  };

  const addLine = () => {
    setLines((current) => [...current, createEmptyLine()]);
  };

  const removeLine = (lineId) => {
    setLines((current) => {
      if (current.length === 1) {
        return current;
      }
      return current.filter((line) => line.id !== lineId);
    });
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    const validLines = lines.filter((line) => line.productId);
    if (validLines.length === 0) {
      setFeedbackType('error');
      setFeedback('Selecciona al menos un plato para el pedido.');
      return;
    }

    if (isSubmitting) {
      return;
    }

    setIsSubmitting(true);
    setFeedback('');

    try {
      const payload = {
        mesa_id: orderHeader.mesaId ? Number(orderHeader.mesaId) : null,
        tipo_pedido: orderHeader.tipoPedido,
        cliente_nombre: orderHeader.cliente,
        notas: orderHeader.notas,
        items: validLines.map((line) => ({
          product_id: Number(line.productId),
          cantidad: Number(line.quantity || 1),
          notas: line.notes,
        })),
      };

      const response = await fetch(`/api/pedidos/${orderId}/actualizar/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken') || '',
        },
        credentials: 'include',
        body: JSON.stringify(payload),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok) {
        setFeedbackType('error');
        setFeedback(data.message || 'No se pudo actualizar el pedido.');
        if (response.status === 409) {
          setOriginalEstado(data.pedido?.estado || 'en_preparacion');
        }
        return;
      }

      setFeedbackType('success');
      setFeedback(`Pedido #${data.pedido.id} actualizado: total $${data.pedido.total}.`);
    } catch (error) {
      setFeedbackType('error');
      setFeedback('Error de conexion al actualizar el pedido. Verifica la red e intenta otra vez.');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (loadingOrder) {
    return (
      <section style={orderContainerStyle(isCompact)}>
        <div style={{ color: '#ffd2d2', fontSize: 14 }}>Cargando pedido...</div>
      </section>
    );
  }

  if (loadError) {
    return (
      <section style={orderContainerStyle(isCompact)}>
        <div style={feedbackStyle('error')}>{loadError}</div>
        <button type="button" onClick={onBack} style={{ ...ghostButtonStyle(isCompact), marginTop: 12 }}>
          Volver a pedidos
        </button>
      </section>
    );
  }

  if (!canEdit) {
    return (
      <section style={orderContainerStyle(isCompact)}>
        <div style={feedbackStyle('error')}>
          Este pedido ya no se puede editar (estado actual: {originalEstado}). Solo los pedidos pendientes admiten cambios.
        </div>
        <button type="button" onClick={onBack} style={{ ...ghostButtonStyle(isCompact), marginTop: 12 }}>
          Volver a pedidos
        </button>
      </section>
    );
  }

  return (
    <section style={orderContainerStyle(isCompact)}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 12, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#f7a5a5', marginBottom: 8 }}>
            Edición de pedido
          </div>
          <div style={{ fontSize: isMobile ? 24 : 32, fontWeight: 700, color: '#fff' }}>
            Pedido #{orderId}
          </div>
          <div style={{ color: '#c6c6c6', marginTop: 8, fontSize: 14 }}>
            Solo se puede editar mientras el pedido esté pendiente.
          </div>
        </div>
        <button type="button" onClick={onBack} style={ghostButtonStyle(isCompact)}>
          Volver a pedidos
        </button>
      </div>

      <form onSubmit={handleSubmit} style={{ display: 'grid', gap: isCompact ? 14 : 16, marginTop: 18, paddingBottom: isCompact ? 84 : 0 }}>
        <div style={{
          display: 'grid',
          gridTemplateColumns: isMobile ? '1fr' : isTablet ? 'repeat(2, minmax(0, 1fr))' : 'repeat(3, minmax(0, 1fr))',
          gap: 12,
        }}>
          <label style={fieldWrapStyle}>
            <span style={labelStyle}>Mesa</span>
            <select
              value={orderHeader.mesaId}
              onChange={(event) => setOrderHeader((current) => ({ ...current, mesaId: event.target.value }))}
              style={inputStyle(isCompact)}
            >
              <option value="">Seleccionar mesa</option>
              {mesas.map((mesa) => (
                <option key={mesa.id} value={mesa.id}>
                  Mesa {mesa.numero} - {mesa.estado}
                </option>
              ))}
            </select>
          </label>

          <label style={fieldWrapStyle}>
            <span style={labelStyle}>Tipo</span>
            <select
              value={orderHeader.tipoPedido}
              onChange={(event) => setOrderHeader((current) => ({ ...current, tipoPedido: event.target.value }))}
              style={inputStyle(isCompact)}
            >
              <option value="local">Local</option>
              <option value="llevar">Para llevar</option>
              <option value="delivery">Delivery</option>
            </select>
          </label>

          <label style={fieldWrapStyle}>
            <span style={labelStyle}>Cliente</span>
            <input
              type="text"
              placeholder="Nombre del cliente"
              value={orderHeader.cliente}
              onChange={(event) => setOrderHeader((current) => ({ ...current, cliente: event.target.value }))}
              style={inputStyle(isCompact)}
            />
          </label>
        </div>

        <label style={fieldWrapStyle}>
          <span style={labelStyle}>Notas generales</span>
          <textarea
            rows={2}
            placeholder="Sin cebolla, poco picante, retirar ingredientes, etc."
            value={orderHeader.notas}
            onChange={(event) => setOrderHeader((current) => ({ ...current, notas: event.target.value }))}
            style={{ ...inputStyle(isCompact), resize: 'vertical', minHeight: isCompact ? 72 : 64 }}
          />
        </label>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginTop: 4, flexWrap: 'wrap' }}>
          <div style={{ fontSize: 14, color: '#f2c5c5' }}>Productos del pedido</div>
          <button type="button" onClick={addLine} style={primaryButtonStyle(isCompact)}>
            + Agregar plato
          </button>
        </div>

        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          overflowX: isCompact ? 'auto' : 'visible',
          paddingBottom: 2,
          scrollbarWidth: 'thin',
        }}>
          {catalogOptions.map((option) => (
            <button
              key={option.key}
              type="button"
              onClick={() => setCatalogType(option.key)}
              style={catalogTypeChipStyle(catalogType === option.key, isCompact)}
            >
              {option.label}
            </button>
          ))}
        </div>

        <div style={{ display: 'grid', gap: 12 }}>
          {lines.map((line, index) => {
            const filteredProducts = categoryFilteredProducts.filter((product) => (
              product.nombre.toLowerCase().includes(line.search.toLowerCase())
              || (product.categoria_nombre || '').toLowerCase().includes(line.search.toLowerCase())
            ));
            const lineSubtotal = getLineSubtotal(line, products, promotionsByProductId);
            const linePromotion = line.productId ? promotionsByProductId[line.productId] : null;

            return (
              <article key={line.id} style={lineCardStyle(isCompact, Boolean(linePromotion))}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
                  <div style={{ color: '#fff', fontWeight: 600 }}>
                    Plato #{index + 1}
                    {linePromotion ? (
                      <span style={promoInlineBadgeStyle}>En promoción -{linePromotion.porcentaje_descuento}%</span>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    onClick={() => removeLine(line.id)}
                    style={miniActionStyle(isCompact)}
                    disabled={lines.length === 1}
                  >
                    Quitar
                  </button>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: isCompact ? '1fr' : '2fr 1fr', gap: 12, marginTop: 10 }}>
                  <div style={{ position: 'relative' }}>
                    <label style={fieldWrapStyle}>
                      <span style={labelStyle}>Buscar plato</span>
                      <input
                        type="text"
                        value={line.search}
                        onChange={(event) => handleLineProductSearch(line.id, event.target.value)}
                        onFocus={() => setLines((current) => current.map((entry) => (entry.id === line.id ? { ...entry, isOpen: true } : entry)))}
                        placeholder="Ejemplo: arepa, pabellon, cachapa..."
                        style={inputStyle(isCompact)}
                      />
                    </label>

                    {line.isOpen && (
                      <div style={resultsPanelStyle(isCompact)}>
                        {filteredProducts.length > 0 ? (
                          filteredProducts.map((product) => {
                            const promotion = promotionsByProductId[product.id];
                            return (
                              <button
                                key={product.id}
                                type="button"
                                onClick={() => handleSelectProduct(line.id, product)}
                                style={resultRowButtonStyle(isCompact, Boolean(promotion))}
                              >
                                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                  <span style={{ color: '#fff', fontWeight: 600 }}>{product.nombre}</span>
                                  {promotion ? <span style={promoInlineBadgeStyle}>-{promotion.porcentaje_descuento}%</span> : null}
                                </span>
                                {promotion ? (
                                  <span style={{ fontSize: 12 }}>
                                    <span style={{ color: '#8f7676', textDecoration: 'line-through', marginRight: 6 }}>
                                      ${Number(product.precio_venta).toFixed(2)}
                                    </span>
                                    <span style={{ color: '#7dffa0', fontWeight: 700 }}>
                                      ${Number(promotion.precio_descuento).toFixed(2)}
                                    </span>
                                  </span>
                                ) : (
                                  <span style={{ color: '#e8bcbc', fontSize: 12 }}>{product.categoria_nombre} - ${Number(product.precio_venta).toFixed(2)}</span>
                                )}
                              </button>
                            );
                          })
                        ) : (
                          <div style={{ color: '#d8b9b9', padding: 12, fontSize: 13 }}>No hay resultados para esa busqueda.</div>
                        )}
                      </div>
                    )}
                  </div>

                  <label style={fieldWrapStyle}>
                    <span style={labelStyle}>Cantidad</span>
                    <input
                      type="number"
                      min="1"
                      step="1"
                      value={line.quantity}
                      onChange={(event) => handleLineQtyChange(line.id, event.target.value)}
                      style={inputStyle(isCompact)}
                    />
                  </label>
                </div>

                <label style={{ ...fieldWrapStyle, marginTop: 10 }}>
                  <span style={labelStyle}>Indicaciones del plato</span>
                  <input
                    type="text"
                    value={line.notes}
                    onChange={(event) => handleLineNotesChange(line.id, event.target.value)}
                    onBlur={() => handleCloseOptions(line.id)}
                    placeholder="Sin salsa, termino medio, extra queso..."
                    style={inputStyle(isCompact)}
                  />
                </label>

                <div style={{ marginTop: 10, color: '#ffdede', fontSize: 13 }}>
                  Subtotal del plato: ${lineSubtotal.toFixed(2)}
                </div>
              </article>
            );
          })}
        </div>

        <div style={checkoutBarStyle(isCompact)}>
          <div style={{ color: '#fff', fontWeight: 700 }}>Total estimado: ${subtotal.toFixed(2)}</div>
          <button type="submit" style={primaryButtonStyle(isCompact)} disabled={isSubmitting}>
            {isSubmitting ? 'Guardando...' : 'Guardar cambios'}
          </button>
        </div>

        {loadingData && <div style={{ color: '#ffd2d2', fontSize: 13 }}>Cargando mesas y platos...</div>}
        {feedback && <div style={feedbackStyle(feedbackType)}>{feedback}</div>}
      </form>
    </section>
  );
}

function createEmptyLine() {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    productId: '',
    productName: '',
    search: '',
    quantity: 1,
    notes: '',
    isOpen: false,
  };
}

function getLineSubtotal(line, products, promotionsByProductId = {}) {
  const product = products.find((item) => String(item.id) === String(line.productId));
  if (!product) {
    return 0;
  }
  const promotion = promotionsByProductId[product.id];
  const unitPrice = promotion ? Number(promotion.precio_descuento) : Number(product.precio_venta);
  return unitPrice * Number(line.quantity || 1);
}

function matchesCatalogType(product, catalogType) {
  const category = String(product.categoria_nombre || '').toLowerCase();

  if (catalogType === 'Todos') {
    return true;
  }

  if (catalogType === 'Jugos') {
    return category.includes('jugo');
  }

  if (catalogType === 'Licores') {
    return (
      category.includes('licor')
      || category.includes('trago')
      || category.includes('coctel')
      || category.includes('cocktail')
    );
  }

  return !category.includes('jugo') && !category.includes('licor') && !category.includes('trago') && !category.includes('coctel');
}

function getCookie(name) {
  const all = `; ${document.cookie}`;
  const parts = all.split(`; ${name}=`);
  if (parts.length === 2) {
    return parts.pop().split(';').shift();
  }
  return '';
}

const orderContainerStyle = (isCompact) => ({
  background: 'linear-gradient(180deg, rgba(18, 8, 8, 0.96) 0%, rgba(8, 8, 8, 0.98) 100%)',
  border: '1px solid rgba(255, 95, 95, 0.18)',
  borderRadius: 24,
  padding: isCompact ? 14 : 20,
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.05), 0 14px 30px rgba(0,0,0,0.32)',
});

const fieldWrapStyle = {
  display: 'grid',
  gap: 7,
};

const labelStyle = {
  fontSize: 12,
  color: '#f1b8b8',
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
};

const inputStyle = (isCompact) => ({
  width: '100%',
  borderRadius: 12,
  border: '1px solid rgba(255,255,255,0.14)',
  background: 'rgba(12, 12, 12, 0.95)',
  color: '#fff',
  padding: isCompact ? '12px 12px' : '10px 12px',
  fontSize: isCompact ? 16 : 14,
  minHeight: isCompact ? 46 : 40,
  boxSizing: 'border-box',
  outline: 'none',
  colorScheme: 'dark',
  appearance: 'auto',
});

const primaryButtonStyle = (isCompact) => ({
  border: 'none',
  borderRadius: 999,
  padding: isCompact ? '12px 16px' : '10px 16px',
  background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
  minHeight: 44,
});

const ghostButtonStyle = (isCompact) => ({
  border: '1px solid rgba(255, 115, 115, 0.34)',
  borderRadius: 999,
  padding: isCompact ? '11px 16px' : '10px 16px',
  background: 'rgba(255,255,255,0.03)',
  color: '#fff',
  fontWeight: 600,
  cursor: 'pointer',
  width: isCompact ? '100%' : 'auto',
  minHeight: 44,
});

const lineCardStyle = (isCompact, hasPromotion) => ({
  borderRadius: 18,
  border: hasPromotion ? '1px solid rgba(120, 220, 160, 0.5)' : '1px solid rgba(255,255,255,0.12)',
  background: hasPromotion ? 'rgba(70, 200, 120, 0.08)' : 'rgba(255,255,255,0.03)',
  padding: isCompact ? 12 : 14,
});

const promoInlineBadgeStyle = {
  display: 'inline-flex',
  marginLeft: 8,
  padding: '2px 8px',
  borderRadius: 999,
  background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)',
  color: '#fff',
  fontSize: 11,
  fontWeight: 800,
  verticalAlign: 'middle',
};

const miniActionStyle = (isCompact) => ({
  border: '1px solid rgba(255,255,255,0.2)',
  borderRadius: 10,
  background: 'transparent',
  color: '#f2c9c9',
  padding: isCompact ? '8px 12px' : '6px 10px',
  cursor: 'pointer',
  minHeight: 40,
});

const resultsPanelStyle = (isCompact) => ({
  marginTop: 8,
  border: '1px solid rgba(255,255,255,0.12)',
  borderRadius: 12,
  background: 'rgba(8, 8, 8, 0.98)',
  maxHeight: isCompact ? 260 : 220,
  overflowY: 'auto',
  display: 'grid',
  gap: 6,
  padding: 8,
  boxShadow: '0 12px 30px rgba(0,0,0,0.35)',
  zIndex: 2,
});

const resultRowButtonStyle = (isCompact, hasPromotion) => ({
  border: hasPromotion ? '1px solid rgba(120, 220, 160, 0.5)' : '1px solid rgba(255,255,255,0.08)',
  borderRadius: 10,
  padding: isCompact ? '12px 10px' : '10px 10px',
  background: hasPromotion ? 'rgba(70, 200, 120, 0.1)' : 'rgba(255,255,255,0.05)',
  textAlign: 'left',
  display: 'grid',
  gap: 4,
  cursor: 'pointer',
  minHeight: 44,
});

const catalogTypeChipStyle = (active, isCompact) => ({
  border: active ? '1px solid rgba(255, 106, 106, 0.6)' : '1px solid rgba(255,255,255,0.18)',
  borderRadius: 999,
  padding: isCompact ? '9px 14px' : '7px 12px',
  background: active ? 'rgba(191, 31, 31, 0.28)' : 'rgba(255,255,255,0.03)',
  color: '#fff',
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
  whiteSpace: 'nowrap',
  minHeight: 40,
});

const checkoutBarStyle = (isCompact) => ({
  borderTop: '1px solid rgba(255, 255, 255, 0.1)',
  paddingTop: 12,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  flexWrap: 'wrap',
  gap: 10,
  ...(isCompact
    ? {
      position: 'sticky',
      bottom: 8,
      padding: '12px 10px',
      borderRadius: 14,
      background: 'rgba(18, 8, 8, 0.94)',
      backdropFilter: 'blur(2px)',
      border: '1px solid rgba(255,255,255,0.12)',
      zIndex: 4,
    }
    : {}),
});

const feedbackStyle = (feedbackType) => ({
  marginTop: 4,
  borderRadius: 12,
  border: feedbackType === 'error' ? '1px solid rgba(223, 102, 102, 0.5)' : '1px solid rgba(82, 206, 123, 0.35)',
  background: feedbackType === 'error' ? 'rgba(102, 29, 29, 0.55)' : 'rgba(31, 89, 48, 0.45)',
  color: feedbackType === 'error' ? '#ffe2e2' : '#dbffe4',
  padding: '10px 12px',
  fontSize: 13,
});

export default EditOrderPage;

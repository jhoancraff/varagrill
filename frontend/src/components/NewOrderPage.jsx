import { useEffect, useMemo, useState } from 'react';
import { printKitchenTicket } from '../utils/kitchenTicket';

function NewOrderPage({ isMobile, mesas, products, adicionales = [], loadingData, waiterName, onBack }) {
  const [orderHeader, setOrderHeader] = useState({
    mesaId: '',
    tipoPedido: 'local',
    cliente: '',
    notas: '',
  });
  const [cartItems, setCartItems] = useState([]);
  const [feedback, setFeedback] = useState('');
  const [feedbackType, setFeedbackType] = useState('success');
  const [catalogType, setCatalogType] = useState('Todos');
  const [searchTerm, setSearchTerm] = useState('');
  const [isTablet, setIsTablet] = useState(() => window.matchMedia('(max-width: 1100px)').matches);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [queuedCount, setQueuedCount] = useState(() => getQueuedOrders().length);
  const [isSyncingQueue, setIsSyncingQueue] = useState(false);
  const [isOnline, setIsOnline] = useState(() => navigator.onLine);
  const [promotionsByProductId, setPromotionsByProductId] = useState({});

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
        // Sin promociones disponibles no bloquea la toma de pedidos.
      }
    };

    loadPromotions();
    return () => {
      cancelled = true;
    };
  }, []);

  const categories = useMemo(() => {
    const names = new Set();
    products.forEach((product) => {
      if (product.categoria_nombre) {
        names.add(product.categoria_nombre);
      }
    });
    return ['Todos', ...Array.from(names).sort((a, b) => a.localeCompare(b))];
  }, [products]);

  const visibleProducts = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    return products.filter((product) => {
      const matchesCategory = catalogType === 'Todos' || product.categoria_nombre === catalogType;
      const matchesSearch = !term || product.nombre.toLowerCase().includes(term);
      return matchesCategory && matchesSearch;
    });
  }, [products, catalogType, searchTerm]);

  const cartCount = useMemo(
    () => cartItems.reduce((total, item) => total + item.quantity, 0),
    [cartItems],
  );

  const subtotal = useMemo(
    () => cartItems.reduce((total, item) => {
      const product = products.find((entry) => String(entry.id) === String(item.productId));
      if (!product) {
        return total;
      }
      const addonsTotal = (item.adicionales || []).reduce((sum, addon) => sum + Number(addon.precioUnitario || 0) * addon.cantidad, 0);
      return total + getUnitPrice(product, promotionsByProductId) * item.quantity + addonsTotal;
    }, 0),
    [cartItems, products, promotionsByProductId],
  );

  const selectedMesa = useMemo(
    () => mesas.find((mesa) => String(mesa.id) === String(orderHeader.mesaId)),
    [mesas, orderHeader.mesaId],
  );

  useEffect(() => {
    const tabletQuery = window.matchMedia('(max-width: 1100px)');
    const handleViewportChange = (event) => setIsTablet(event.matches);
    setIsTablet(tabletQuery.matches);
    tabletQuery.addEventListener('change', handleViewportChange);
    return () => tabletQuery.removeEventListener('change', handleViewportChange);
  }, []);

  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true);
      syncQueuedOrders();
    };

    const handleOffline = () => {
      setIsOnline(false);
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    if (navigator.onLine) {
      syncQueuedOrders();
    }

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  const isCompact = isMobile || isTablet;

  const queueCurrentOrder = (payload) => {
    const queue = getQueuedOrders();
    queue.push({
      id: cryptoRandomId(),
      createdAt: new Date().toISOString(),
      payload,
    });
    setQueuedOrders(queue);
    setQueuedCount(queue.length);
  };

  const syncQueuedOrders = async () => {
    if (isSyncingQueue || !navigator.onLine) {
      return;
    }

    const queue = getQueuedOrders();
    if (queue.length === 0) {
      setQueuedCount(0);
      return;
    }

    setIsSyncingQueue(true);
    let synced = 0;
    const remaining = [];

    for (const item of queue) {
      try {
        const response = await fetch('/api/pedidos/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken') || '',
          },
          credentials: 'include',
          body: JSON.stringify(item.payload),
        });

        const data = await response.json().catch(() => ({}));
        if (response.ok && data.ok) {
          synced += 1;
          continue;
        }

        if (response.status === 401) {
          remaining.push(item);
          remaining.push(...queue.slice(queue.indexOf(item) + 1));
          break;
        }

        remaining.push(item);
      } catch (error) {
        remaining.push(item);
      }
    }

    setQueuedOrders(remaining);
    setQueuedCount(remaining.length);
    setIsSyncingQueue(false);

    if (synced > 0) {
      setFeedbackType('success');
      setFeedback(`Se sincronizaron ${synced} pedido(s) en cola.`);
    }
  };

  const addToCart = (product) => {
    setCartItems((current) => {
      const existing = current.find((item) => item.productId === product.id);
      if (existing) {
        return current.map((item) => (
          item.productId === product.id ? { ...item, quantity: item.quantity + 1 } : item
        ));
      }
      return [...current, { productId: product.id, quantity: 1, notes: '', adicionales: [] }];
    });
  };

  const addAddonToCartItem = (productId, addonId) => {
    if (!addonId) {
      return;
    }
    const addonInfo = adicionales.find((entry) => String(entry.id) === String(addonId));
    if (!addonInfo) {
      return;
    }
    setCartItems((current) => current.map((item) => {
      if (item.productId !== productId) {
        return item;
      }
      const existingAddon = (item.adicionales || []).find((entry) => String(entry.preparacionId) === String(addonId));
      if (existingAddon) {
        return {
          ...item,
          adicionales: item.adicionales.map((entry) => (
            String(entry.preparacionId) === String(addonId) ? { ...entry, cantidad: entry.cantidad + 1 } : entry
          )),
        };
      }
      return {
        ...item,
        adicionales: [
          ...(item.adicionales || []),
          { preparacionId: addonInfo.id, nombre: addonInfo.nombre, cantidad: 1, precioUnitario: addonInfo.precio },
        ],
      };
    }));
  };

  const changeAddonQuantity = (productId, addonId, delta) => {
    setCartItems((current) => current.map((item) => {
      if (item.productId !== productId) {
        return item;
      }
      return {
        ...item,
        adicionales: item.adicionales
          .map((entry) => (String(entry.preparacionId) === String(addonId) ? { ...entry, cantidad: entry.cantidad + delta } : entry))
          .filter((entry) => entry.cantidad > 0),
      };
    }));
  };

  const removeAddonFromCartItem = (productId, addonId) => {
    setCartItems((current) => current.map((item) => (
      item.productId === productId
        ? { ...item, adicionales: item.adicionales.filter((entry) => String(entry.preparacionId) !== String(addonId)) }
        : item
    )));
  };

  const changeCartQuantity = (productId, delta) => {
    setCartItems((current) => current
      .map((item) => (item.productId === productId ? { ...item, quantity: item.quantity + delta } : item))
      .filter((item) => item.quantity > 0));
  };

  const updateCartNotes = (productId, notes) => {
    setCartItems((current) => current.map((item) => (
      item.productId === productId ? { ...item, notes } : item
    )));
  };

  const removeCartItem = (productId) => {
    setCartItems((current) => current.filter((item) => item.productId !== productId));
  };

  const getCartQuantity = (productId) => {
    const item = cartItems.find((entry) => entry.productId === productId);
    return item ? item.quantity : 0;
  };

  const buildPayload = () => ({
    mesa_id: orderHeader.mesaId ? Number(orderHeader.mesaId) : null,
    tipo_pedido: orderHeader.tipoPedido,
    cliente_nombre: orderHeader.cliente,
    notas: orderHeader.notas,
    items: cartItems.map((item) => ({
      product_id: Number(item.productId),
      cantidad: Number(item.quantity || 1),
      notas: item.notes,
      adicionales: (item.adicionales || []).map((addon) => ({
        preparacion_id: Number(addon.preparacionId),
        cantidad: Number(addon.cantidad || 1),
      })),
    })),
  });

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (orderHeader.tipoPedido === 'local' && !orderHeader.mesaId) {
      setFeedbackType('error');
      setFeedback('Selecciona una mesa antes de registrar el pedido.');
      return;
    }

    if (cartItems.length === 0) {
      setFeedbackType('error');
      setFeedback('Agrega al menos un plato para registrar el pedido.');
      return;
    }

    if (isSubmitting) {
      return;
    }

    setIsSubmitting(true);
    setFeedback('');

    try {
      const payload = buildPayload();
      const response = await fetch('/api/pedidos/', {
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
        if (!navigator.onLine) {
          queueCurrentOrder(payload);
          setFeedbackType('success');
          setFeedback(`Sin conexion. Pedido guardado en cola (${queuedCount + 1} pendiente(s)).`);
          setCartItems([]);
          setOrderHeader((current) => ({ ...current, notas: '' }));
          return;
        }
        setFeedbackType('error');
        setFeedback(data.message || 'No se pudo registrar el pedido. Intenta nuevamente.');
        return;
      }

      const mesaLabel = selectedMesa ? `Mesa ${selectedMesa.numero}` : 'Sin mesa';
      setFeedbackType('success');
      setFeedback(`Pedido #${data.pedido.id} registrado: ${data.pedido.items} item(s), ${mesaLabel}, total $${data.pedido.total}.`);

      printKitchenTicket({
        pedidoId: data.pedido.id,
        mesa: selectedMesa ? selectedMesa.numero : null,
        tipoPedido: orderHeader.tipoPedido,
        mesero: waiterName,
        creadoEn: new Date().toISOString(),
        notasGenerales: orderHeader.notas,
        items: cartItems.map((item) => {
          const product = products.find((entry) => String(entry.id) === String(item.productId));
          return {
            cantidad: item.quantity,
            producto: product?.nombre || '',
            notas: item.notes,
            adicionales: (item.adicionales || []).map((addon) => ({ cantidad: addon.cantidad, nombre: addon.nombre })),
            composicion: product?.composicion || [],
          };
        }),
      });

      setCartItems([]);
      setOrderHeader((current) => ({ ...current, notas: '' }));
    } catch (error) {
      if (!navigator.onLine) {
        const payload = buildPayload();
        queueCurrentOrder(payload);
        setFeedbackType('success');
        setFeedback(`Sin conexion. Pedido guardado en cola (${queuedCount + 1} pendiente(s)).`);
        setCartItems([]);
        setOrderHeader((current) => ({ ...current, notas: '' }));
      } else {
        setFeedbackType('error');
        setFeedback('Error de conexion al registrar el pedido. Verifica la red e intenta otra vez.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section style={orderContainerStyle(isCompact)}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 12, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#f7a5a5', marginBottom: 8 }}>
            Toma de pedido
          </div>
          <div style={{ fontSize: isMobile ? 24 : 32, fontWeight: 700, color: '#fff' }}>
            Nuevo pedido
          </div>
          <div style={{ color: '#c6c6c6', marginTop: 8, fontSize: 14 }}>
            Mesero: {waiterName || 'Usuario'}
          </div>
        </div>
        <button type="button" onClick={onBack} style={ghostButtonStyle(isCompact)}>
          Volver a inicio
        </button>
      </div>

      <div style={offlineBannerStyle(isOnline, queuedCount > 0)}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span aria-hidden="true">{isOnline ? '●' : '○'}</span>
          {isOnline ? `En linea · Cola: ${queuedCount}` : `Sin conexion · Cola: ${queuedCount}`}
        </div>
        <button
          type="button"
          onClick={syncQueuedOrders}
          style={syncQueueButtonStyle}
          disabled={!isOnline || queuedCount === 0 || isSyncingQueue}
        >
          {isSyncingQueue ? 'Sincronizando...' : 'Sincronizar ahora'}
        </button>
      </div>

      <form onSubmit={handleSubmit} style={{ display: 'grid', gap: isCompact ? 14 : 16, marginTop: 18 }}>
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
              required={orderHeader.tipoPedido === 'local'}
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

        <div style={workspaceStyle(isCompact)}>
          <div style={menuColumnStyle}>
            <div style={catalogBarStyle}>
              <input
                type="text"
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                placeholder="Buscar plato o bebida..."
                style={searchInputStyle(isCompact)}
              />
              <div style={categoryScrollStyle}>
                {categories.map((category) => (
                  <button
                    key={category}
                    type="button"
                    onClick={() => setCatalogType(category)}
                    style={catalogTypeChipStyle(catalogType === category, isCompact)}
                  >
                    {category}
                  </button>
                ))}
              </div>
            </div>

            <div style={productGridStyle}>
              {loadingData ? (
                <div style={emptyGridStateStyle}>Cargando platos...</div>
              ) : visibleProducts.length === 0 ? (
                <div style={emptyGridStateStyle}>No hay productos en esta categoría.</div>
              ) : (
                visibleProducts.map((product) => {
                  const promotion = promotionsByProductId[product.id];
                  const quantityInCart = getCartQuantity(product.id);

                  return (
                    <button
                      key={product.id}
                      type="button"
                      onClick={() => addToCart(product)}
                      style={productCardStyle(Boolean(promotion))}
                    >
                      {quantityInCart > 0 ? <span style={cardQuantityBadgeStyle}>{quantityInCart}</span> : null}
                      <div style={productImageWrapStyle}>
                        {product.imagen_url ? (
                          <img src={product.imagen_url} alt={product.nombre} style={productImageStyle} loading="lazy" />
                        ) : (
                          <div style={productImagePlaceholderStyle}>{product.nombre.charAt(0).toUpperCase()}</div>
                        )}
                        {promotion ? <span style={cardPromoBadgeStyle}>-{promotion.porcentaje_descuento}%</span> : null}
                      </div>
                      <div style={productCardBodyStyle}>
                        <div style={productCardNameStyle}>{product.nombre}</div>
                        {product.descripcion ? (
                          <div style={productCardDescStyle}>{product.descripcion}</div>
                        ) : null}
                        <div style={productCardFooterStyle}>
                          {promotion ? (
                            <span style={productCardPriceGroupStyle}>
                              <span style={priceStrikeStyle}>${Number(product.precio_venta).toFixed(2)}</span>
                              <span style={pricePromoStyle}>${Number(promotion.precio_descuento).toFixed(2)}</span>
                            </span>
                          ) : (
                            <span style={priceStyle}>${Number(product.precio_venta).toFixed(2)}</span>
                          )}
                          <span style={addIconStyle} aria-hidden="true">+</span>
                        </div>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>

          <aside id="cart-panel" style={cartPanelStyle(isCompact)}>
            <div style={cartHeaderStyle}>
              <div style={cartTitleStyle}>Pedido actual</div>
              <span style={cartCountBadgeStyle}>{cartCount} {cartCount === 1 ? 'plato' : 'platos'}</span>
            </div>

            <div style={cartListStyle(isCompact)}>
              {cartItems.length === 0 ? (
                <div style={cartEmptyStyle}>Toca un plato del menú para agregarlo aquí.</div>
              ) : (
                cartItems.map((item) => {
                  const product = products.find((entry) => String(entry.id) === String(item.productId));
                  if (!product) {
                    return null;
                  }
                  const promotion = promotionsByProductId[product.id];
                  const unitPrice = getUnitPrice(product, promotionsByProductId);

                  return (
                    <div key={item.productId} style={cartLineStyle}>
                      <div style={cartLineTopStyle}>
                        <div style={cartLineNameStyle}>
                          {product.nombre}
                          {promotion ? <span style={promoInlineBadgeStyle}>-{promotion.porcentaje_descuento}%</span> : null}
                        </div>
                        <button type="button" onClick={() => removeCartItem(item.productId)} style={cartRemoveButtonStyle} aria-label={`Quitar ${product.nombre}`}>
                          ×
                        </button>
                      </div>
                      <div style={cartLineControlsStyle}>
                        <div style={qtyStepperStyle}>
                          <button type="button" onClick={() => changeCartQuantity(item.productId, -1)} style={qtyButtonStyle}>−</button>
                          <span style={qtyValueStyle}>{item.quantity}</span>
                          <button type="button" onClick={() => changeCartQuantity(item.productId, 1)} style={qtyButtonStyle}>+</button>
                        </div>
                        <div style={cartLineSubtotalStyle}>${(unitPrice * item.quantity).toFixed(2)}</div>
                      </div>
                      <input
                        type="text"
                        value={item.notes}
                        onChange={(event) => updateCartNotes(item.productId, event.target.value)}
                        placeholder="Indicaciones (sin cebolla, término medio...)"
                        style={cartNotesInputStyle}
                      />

                      {adicionales.length > 0 ? (
                        <div style={addonSectionStyle}>
                          {(item.adicionales || []).map((addon) => (
                            <div key={addon.preparacionId} style={addonChipStyle}>
                              <span>{addon.nombre}</span>
                              <div style={qtyStepperStyle}>
                                <button type="button" onClick={() => changeAddonQuantity(item.productId, addon.preparacionId, -1)} style={qtyButtonStyle}>−</button>
                                <span style={qtyValueStyle}>{addon.cantidad}</span>
                                <button type="button" onClick={() => changeAddonQuantity(item.productId, addon.preparacionId, 1)} style={qtyButtonStyle}>+</button>
                              </div>
                              <span style={addonPriceStyle}>${(Number(addon.precioUnitario || 0) * addon.cantidad).toFixed(2)}</span>
                              <button type="button" onClick={() => removeAddonFromCartItem(item.productId, addon.preparacionId)} style={cartRemoveButtonStyle} aria-label={`Quitar ${addon.nombre}`}>
                                ×
                              </button>
                            </div>
                          ))}
                          <select
                            value=""
                            onChange={(event) => addAddonToCartItem(item.productId, event.target.value)}
                            style={addonSelectStyle}
                          >
                            <option value="">+ Agregar adicional (extra pagado)...</option>
                            {adicionales.map((addon) => (
                              <option key={addon.id} value={addon.id}>
                                {addon.nombre} — ${Number(addon.precio || 0).toFixed(2)}
                              </option>
                            ))}
                          </select>
                        </div>
                      ) : null}
                    </div>
                  );
                })
              )}
            </div>

            <label style={fieldWrapStyle}>
              <span style={labelStyle}>Notas generales</span>
              <textarea
                rows={2}
                placeholder="Sin cebolla, poco picante, retirar ingredientes, etc."
                value={orderHeader.notas}
                onChange={(event) => setOrderHeader((current) => ({ ...current, notas: event.target.value }))}
                style={{ ...inputStyle(isCompact), resize: 'vertical', minHeight: 56 }}
              />
            </label>

            <div style={cartTotalRowStyle}>
              <span>Total estimado</span>
              <span style={cartTotalValueStyle}>${subtotal.toFixed(2)}</span>
            </div>

            <button type="submit" style={primaryButtonStyle(isCompact)} disabled={isSubmitting || cartItems.length === 0}>
              {isSubmitting ? 'Guardando...' : 'Registrar pedido'}
            </button>

            {feedback && <div style={feedbackStyle(feedbackType)}>{feedback}</div>}
          </aside>
        </div>
      </form>

      {isCompact && cartItems.length > 0 ? (
        <div style={mobileCartBarStyle}>
          <div style={{ color: '#fff', fontWeight: 700 }}>{cartCount} {cartCount === 1 ? 'plato' : 'platos'} · ${subtotal.toFixed(2)}</div>
          <button
            type="button"
            onClick={() => document.getElementById('cart-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
            style={mobileCartButtonStyle}
          >
            Ver pedido
          </button>
        </div>
      ) : null}
    </section>
  );
}

function getUnitPrice(product, promotionsByProductId = {}) {
  const promotion = promotionsByProductId[product.id];
  return promotion ? Number(promotion.precio_descuento) : Number(product.precio_venta);
}

function getCookie(name) {
  const all = `; ${document.cookie}`;
  const parts = all.split(`; ${name}=`);
  if (parts.length === 2) {
    return parts.pop().split(';').shift();
  }
  return '';
}

function getQueuedOrders() {
  try {
    const raw = localStorage.getItem('vg_pending_orders');
    const queue = raw ? JSON.parse(raw) : [];
    return Array.isArray(queue) ? queue : [];
  } catch (error) {
    return [];
  }
}

function setQueuedOrders(queue) {
  localStorage.setItem('vg_pending_orders', JSON.stringify(queue));
}

function cryptoRandomId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

const orderContainerStyle = (isCompact) => ({
  background: 'linear-gradient(180deg, rgba(18, 8, 8, 0.96) 0%, rgba(8, 8, 8, 0.98) 100%)',
  border: '1px solid rgba(255, 95, 95, 0.18)',
  borderRadius: 24,
  padding: isCompact ? 14 : 20,
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.05), 0 14px 30px rgba(0,0,0,0.32)',
  paddingBottom: isCompact ? 76 : 20,
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

const promoInlineBadgeStyle = {
  display: 'inline-flex',
  marginLeft: 8,
  padding: '2px 8px',
  borderRadius: 999,
  background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)',
  color: '#fff',
  fontSize: 10,
  fontWeight: 800,
  verticalAlign: 'middle',
};

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
  flexShrink: 0,
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

const offlineBannerStyle = (isOnline, hasQueue) => ({
  marginTop: 14,
  borderRadius: 12,
  border: isOnline ? '1px solid rgba(88, 208, 132, 0.35)' : '1px solid rgba(223, 162, 95, 0.45)',
  background: isOnline ? 'rgba(22, 76, 39, 0.35)' : 'rgba(86, 57, 19, 0.4)',
  color: '#fff',
  padding: '9px 12px',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 12,
  fontSize: 13,
  opacity: hasQueue || !isOnline ? 1 : 0.92,
});

const syncQueueButtonStyle = {
  border: '1px solid rgba(255,255,255,0.24)',
  borderRadius: 999,
  padding: '7px 12px',
  minHeight: 34,
  color: '#fff',
  background: 'rgba(255,255,255,0.06)',
  cursor: 'pointer',
};

// --- Workspace: menú (izquierda) + pedido actual (derecha / abajo) ---

const workspaceStyle = (isCompact) => (
  isCompact
    ? { display: 'grid', gap: 14 }
    : { display: 'grid', gridTemplateColumns: '1fr 340px', gap: 16, alignItems: 'start' }
);

const menuColumnStyle = {
  display: 'grid',
  gap: 10,
  minWidth: 0,
};

const catalogBarStyle = {
  position: 'sticky',
  top: 0,
  zIndex: 3,
  display: 'grid',
  gap: 8,
  padding: '8px 0',
  background: 'linear-gradient(180deg, rgba(16, 7, 7, 0.98) 0%, rgba(16, 7, 7, 0.94) 80%, rgba(16, 7, 7, 0) 100%)',
};

const searchInputStyle = (isCompact) => ({
  ...inputStyle(isCompact),
  minHeight: isCompact ? 44 : 38,
});

const categoryScrollStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  overflowX: 'auto',
  paddingBottom: 2,
  scrollbarWidth: 'thin',
};

// --- Grid de platos ---

const productGridStyle = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(136px, 1fr))',
  gap: 10,
};

const emptyGridStateStyle = {
  gridColumn: '1 / -1',
  minHeight: 100,
  display: 'grid',
  placeItems: 'center',
  borderRadius: 16,
  border: '1px dashed rgba(255,255,255,0.14)',
  color: '#c8bbbb',
  fontSize: 13,
};

const productCardStyle = (hasPromotion) => ({
  position: 'relative',
  display: 'grid',
  textAlign: 'left',
  padding: 0,
  overflow: 'hidden',
  borderRadius: 16,
  border: hasPromotion ? '1px solid rgba(120, 220, 160, 0.5)' : '1px solid rgba(255,255,255,0.12)',
  background: hasPromotion ? 'rgba(70, 200, 120, 0.06)' : 'rgba(255,255,255,0.03)',
  cursor: 'pointer',
});

const cardQuantityBadgeStyle = {
  position: 'absolute',
  top: 6,
  right: 6,
  zIndex: 2,
  minWidth: 20,
  height: 20,
  padding: '0 6px',
  borderRadius: 999,
  background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)',
  color: '#fff',
  fontSize: 12,
  fontWeight: 800,
  display: 'grid',
  placeItems: 'center',
  boxShadow: '0 2px 8px rgba(0,0,0,0.4)',
};

const productImageWrapStyle = {
  position: 'relative',
  width: '100%',
  aspectRatio: '4 / 3',
  background: 'rgba(255,255,255,0.04)',
};

const productImageStyle = {
  width: '100%',
  height: '100%',
  objectFit: 'cover',
  display: 'block',
};

const productImagePlaceholderStyle = {
  width: '100%',
  height: '100%',
  display: 'grid',
  placeItems: 'center',
  fontSize: 26,
  fontWeight: 800,
  color: '#7a5f5f',
  background: 'linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%)',
};

const cardPromoBadgeStyle = {
  position: 'absolute',
  bottom: 6,
  left: 6,
  padding: '2px 7px',
  borderRadius: 999,
  background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)',
  color: '#fff',
  fontSize: 10,
  fontWeight: 800,
};

const productCardBodyStyle = {
  display: 'grid',
  gap: 3,
  padding: '8px 9px 10px',
};

const productCardNameStyle = {
  color: '#fff',
  fontWeight: 700,
  fontSize: 12.5,
  lineHeight: 1.25,
  display: '-webkit-box',
  WebkitLineClamp: 2,
  WebkitBoxOrient: 'vertical',
  overflow: 'hidden',
};

const productCardDescStyle = {
  color: '#c2adad',
  fontSize: 10.5,
  lineHeight: 1.3,
  display: '-webkit-box',
  WebkitLineClamp: 2,
  WebkitBoxOrient: 'vertical',
  overflow: 'hidden',
};

const productCardFooterStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  marginTop: 4,
};

const productCardPriceGroupStyle = {
  display: 'flex',
  alignItems: 'baseline',
  gap: 5,
};

const priceStyle = {
  color: '#ffd9d9',
  fontWeight: 700,
  fontSize: 12.5,
};

const priceStrikeStyle = {
  color: '#8f7676',
  textDecoration: 'line-through',
  fontSize: 10.5,
};

const pricePromoStyle = {
  color: '#7dffa0',
  fontWeight: 800,
  fontSize: 12.5,
};

const addIconStyle = {
  width: 20,
  height: 20,
  borderRadius: '50%',
  background: 'rgba(255,255,255,0.08)',
  border: '1px solid rgba(255,255,255,0.18)',
  color: '#fff',
  fontWeight: 800,
  fontSize: 14,
  display: 'grid',
  placeItems: 'center',
  lineHeight: 1,
};

// --- Panel de "Pedido actual" (carrito / reporte) ---

const cartPanelStyle = (isCompact) => ({
  display: 'grid',
  gap: 10,
  padding: 14,
  borderRadius: 18,
  border: '1px solid rgba(255,255,255,0.12)',
  background: 'rgba(255,255,255,0.03)',
  ...(isCompact ? {} : { position: 'sticky', top: 8, maxHeight: 'calc(100vh - 120px)', overflowY: 'auto' }),
});

const cartHeaderStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
};

const cartTitleStyle = {
  color: '#fff',
  fontWeight: 700,
  fontSize: 16,
};

const cartCountBadgeStyle = {
  padding: '4px 10px',
  borderRadius: 999,
  background: 'rgba(255, 141, 141, 0.14)',
  border: '1px solid rgba(255, 141, 141, 0.22)',
  color: '#ffc5c5',
  fontSize: 12,
  fontWeight: 700,
};

const cartListStyle = (isCompact) => ({
  display: 'grid',
  gap: 8,
  maxHeight: isCompact ? 'none' : 320,
  overflowY: isCompact ? 'visible' : 'auto',
});

const cartEmptyStyle = {
  padding: '18px 10px',
  textAlign: 'center',
  borderRadius: 12,
  border: '1px dashed rgba(255,255,255,0.14)',
  color: '#c8bbbb',
  fontSize: 13,
};

const cartLineStyle = {
  display: 'grid',
  gap: 6,
  padding: 10,
  borderRadius: 12,
  border: '1px solid rgba(255,255,255,0.1)',
  background: 'rgba(0,0,0,0.2)',
};

const cartLineTopStyle = {
  display: 'flex',
  alignItems: 'flex-start',
  justifyContent: 'space-between',
  gap: 8,
};

const cartLineNameStyle = {
  color: '#fff',
  fontWeight: 600,
  fontSize: 13,
};

const cartRemoveButtonStyle = {
  border: 'none',
  background: 'transparent',
  color: '#e8a9a9',
  fontSize: 18,
  lineHeight: 1,
  cursor: 'pointer',
  padding: 0,
  minWidth: 22,
};

const cartLineControlsStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 8,
};

const qtyStepperStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  border: '1px solid rgba(255,255,255,0.14)',
  borderRadius: 999,
  padding: '2px 6px',
};

const qtyButtonStyle = {
  border: 'none',
  background: 'transparent',
  color: '#fff',
  fontSize: 16,
  fontWeight: 700,
  cursor: 'pointer',
  width: 22,
  height: 22,
  lineHeight: 1,
};

const qtyValueStyle = {
  color: '#fff',
  fontWeight: 700,
  fontSize: 13,
  minWidth: 14,
  textAlign: 'center',
};

const cartLineSubtotalStyle = {
  color: '#ffd9d9',
  fontWeight: 700,
  fontSize: 13,
};

const cartNotesInputStyle = {
  width: '100%',
  boxSizing: 'border-box',
  borderRadius: 10,
  border: '1px solid rgba(255,255,255,0.1)',
  background: 'rgba(255,255,255,0.03)',
  color: '#fff',
  padding: '7px 9px',
  fontSize: 12,
  outline: 'none',
};

const addonSectionStyle = {
  display: 'grid',
  gap: 6,
  paddingTop: 4,
  borderTop: '1px dashed rgba(255,255,255,0.12)',
};

const addonChipStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 8,
  padding: '4px 8px',
  borderRadius: 999,
  border: '1px solid rgba(255,196,110,0.3)',
  background: 'rgba(255,166,0,0.08)',
  color: '#ffcf85',
  fontSize: 12,
};

const addonPriceStyle = {
  color: '#ffcf85',
  fontWeight: 700,
  fontSize: 12,
};

const addonSelectStyle = {
  width: '100%',
  boxSizing: 'border-box',
  borderRadius: 10,
  border: '1px solid rgba(255,255,255,0.1)',
  background: 'rgba(255,255,255,0.03)',
  color: '#fff',
  padding: '7px 9px',
  fontSize: 12,
  outline: 'none',
};

const cartTotalRowStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  paddingTop: 8,
  borderTop: '1px solid rgba(255,255,255,0.1)',
  color: '#fff',
  fontWeight: 700,
};

const cartTotalValueStyle = {
  fontSize: 18,
};

// --- Barra flotante de resumen en móvil ---

const mobileCartBarStyle = {
  position: 'sticky',
  bottom: 8,
  marginTop: 12,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 10,
  padding: '12px 14px',
  borderRadius: 14,
  background: 'rgba(18, 8, 8, 0.96)',
  backdropFilter: 'blur(2px)',
  border: '1px solid rgba(255,255,255,0.14)',
  boxShadow: '0 12px 30px rgba(0,0,0,0.4)',
  zIndex: 5,
};

const mobileCartButtonStyle = {
  border: 'none',
  borderRadius: 999,
  padding: '10px 16px',
  background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
  minHeight: 40,
};

export default NewOrderPage;
import { useEffect, useMemo, useState } from 'react';
import BsAmount from './BsAmount';
import UnsavedChangesModal from './UnsavedChangesModal';
import useExchangeRate from '../hooks/useExchangeRate';
import useUnsavedChangesGuard from '../hooks/useUnsavedChangesGuard';
import { formatBs } from '../utils/currency';

// Los productos de estas categorías se piden únicamente como acompañante
// (grupo de opciones dinámico) de un plato principal, nunca sueltos desde el
// menú — por eso no deben aparecer en la barra de categorías ni en la grilla
// principal. El picker de acompañantes las sigue leyendo directo de `products`
// por categoria_id, así que esto no le afecta.
const HIDDEN_MENU_CATEGORIES = ['guarniciones'];

function isHiddenMenuCategory(categoriaNombre) {
  return HIDDEN_MENU_CATEGORIES.includes((categoriaNombre || '').trim().toLowerCase());
}

function EditOrderPage({ isMobile, mesas, products, adicionales = [], loadingData, orderId, onBack }) {
  const tasaCambio = useExchangeRate();
  const [orderHeader, setOrderHeader] = useState({
    mesaId: '',
    tipoPedido: 'local',
    cliente: '',
    clienteCedula: '',
    clienteTelefono: '',
    notas: '',
  });
  const [cartItems, setCartItems] = useState([]);
  const [originalEstado, setOriginalEstado] = useState('');
  const [loadingOrder, setLoadingOrder] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [feedbackType, setFeedbackType] = useState('success');
  const [catalogType, setCatalogType] = useState('Todos');
  const [searchTerm, setSearchTerm] = useState('');
  const [isTablet, setIsTablet] = useState(() => window.matchMedia('(max-width: 1100px)').matches);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [promotionsByProductId, setPromotionsByProductId] = useState({});
  const [pesoPickerFor, setPesoPickerFor] = useState(null);
  const [opcionesPickerFor, setOpcionesPickerFor] = useState(null);
  const [pendingPeso, setPendingPeso] = useState(null);
  const [armarPlatoActivo, setArmarPlatoActivo] = useState(false);
  const [grupoActual, setGrupoActual] = useState(null);
  const [nextGrupoId, setNextGrupoId] = useState(1);
  const { guard, isConfirmOpen, confirmLeave, cancelLeave, markClean } = useUnsavedChangesGuard({ cartItems, orderHeader });

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
        const loadedHeader = {
          mesaId: pedido.mesa_id ? String(pedido.mesa_id) : '',
          tipoPedido: pedido.tipo_pedido,
          cliente: pedido.cliente_nombre || '',
          clienteCedula: pedido.cliente_cedula || '',
          clienteTelefono: pedido.cliente_telefono || '',
          notas: pedido.notas || '',
        };
        setOrderHeader(loadedHeader);
        const loadedItems = pedido.items.map((item) => {
          const product = products.find((entry) => String(entry.id) === String(item.product_id));
          const gruposDelProducto = product && Array.isArray(product.grupos_opciones) ? product.grupos_opciones : [];
          return {
            id: cryptoRandomId(),
            productId: String(item.product_id),
            quantity: item.cantidad,
            notes: item.notas || '',
            pesoGramos: item.peso_gramos ? Number(item.peso_gramos) : null,
            grupoArmado: item.grupo_armado || null,
            adicionales: (item.adicionales || []).map((addon) => ({
              preparacionId: addon.preparacion_id,
              nombre: addon.nombre,
              cantidad: addon.cantidad,
              precioUnitario: addon.precio_unitario,
            })),
            // El detalle guardado solo trae grupo_nombre (snapshot histórico, ver
            // VGDetallePedidoOpcion) — para poder re-guardar la edición hace falta el
            // grupo_id VIVO del producto, así que se resuelve por nombre contra
            // product.grupos_opciones. Si el grupo ya no existe o fue renombrado, esa
            // opción se descarta del carrito editable (el mesero puede volver a elegirla).
            opciones: (item.opciones || [])
              .map((opcion) => {
                const grupo = gruposDelProducto.find((entry) => entry.nombre === opcion.grupo_nombre);
                if (!grupo) {
                  return null;
                }
                return {
                  grupoId: grupo.id,
                  preparacionId: opcion.preparacion_id || null,
                  productoId: opcion.producto_id || null,
                  nombre: opcion.nombre,
                  precioAdicional: Number(opcion.precio_unitario || 0),
                };
              })
              .filter(Boolean),
          };
        });
        setCartItems(loadedItems);
        markClean({ cartItems: loadedItems, orderHeader: loadedHeader });
        const maxGrupo = loadedItems.reduce((max, item) => Math.max(max, item.grupoArmado || 0), 0);
        setNextGrupoId(maxGrupo + 1);
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
  }, [orderId, products]);

  useEffect(() => {
    const tabletQuery = window.matchMedia('(max-width: 1100px)');
    const handleViewportChange = (event) => setIsTablet(event.matches);
    setIsTablet(tabletQuery.matches);
    tabletQuery.addEventListener('change', handleViewportChange);
    return () => tabletQuery.removeEventListener('change', handleViewportChange);
  }, []);

  const isCompact = isMobile || isTablet;
  const canEdit = originalEstado === 'pendiente';

  const categories = useMemo(() => {
    const names = new Set();
    products.forEach((product) => {
      if (product.categoria_nombre && !isHiddenMenuCategory(product.categoria_nombre)) {
        names.add(product.categoria_nombre);
      }
    });
    return ['Todos', ...Array.from(names).sort((a, b) => a.localeCompare(b))];
  }, [products]);

  const visibleProducts = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    return products.filter((product) => {
      if (isHiddenMenuCategory(product.categoria_nombre)) {
        return false;
      }
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
    () => cartItems.reduce((total, item) => total + computeItemTotal(item, products, promotionsByProductId), 0),
    [cartItems, products, promotionsByProductId],
  );

  const groupedCartItems = useMemo(() => {
    const groups = new Map();
    const ungrouped = [];
    cartItems.forEach((item) => {
      if (item.grupoArmado) {
        if (!groups.has(item.grupoArmado)) {
          groups.set(item.grupoArmado, []);
        }
        groups.get(item.grupoArmado).push(item);
      } else {
        ungrouped.push(item);
      }
    });
    const platos = Array.from(groups.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([grupoId, items]) => ({ grupoId, items }));
    return { platos, ungrouped };
  }, [cartItems]);

  const handleStartArmarPlato = () => {
    // El número de plato solo se reserva (avanza nextGrupoId) cuando se agrega el primer
    // producto a ese plato, dentro de addToCart — no aquí. Así, si el mesero abre "Armar
    // Plato" y no llega a registrar nada, el siguiente plato reutiliza el mismo número
    // en vez de saltárselo.
    setGrupoActual(nextGrupoId);
    setArmarPlatoActivo(true);
  };

  const handleNuevoPlato = () => {
    setGrupoActual(nextGrupoId);
  };

  const handleTerminarArmado = () => {
    setArmarPlatoActivo(false);
    setGrupoActual(null);
  };

  const resetArmarPlato = () => {
    setArmarPlatoActivo(false);
    setGrupoActual(null);
    setNextGrupoId(1);
  };

  const addToCart = (product, options = {}) => {
    const grupoArmado = armarPlatoActivo ? grupoActual : null;
    const opciones = options.opcionesElegidas || [];
    // Primer producto que cae en este plato: recién ahora se "consume" su número, para
    // que el próximo "+ Nuevo plato" avance de verdad en vez de saltar números vacíos.
    const consumesGrupo = grupoArmado && grupoArmado === nextGrupoId;

    if (product.venta_por_peso) {
      const pesoGramos = Number(options.pesoGramos);
      if (!pesoGramos || pesoGramos <= 0) {
        return;
      }
      if (consumesGrupo) {
        setNextGrupoId((current) => current + 1);
      }
      setCartItems((current) => [
        ...current,
        { id: cryptoRandomId(), productId: String(product.id), quantity: 1, notes: '', adicionales: [], opciones, pesoGramos, grupoArmado },
      ]);
      return;
    }

    if (consumesGrupo) {
      setNextGrupoId((current) => current + 1);
    }

    const opcionesKey = (list) => (list || []).map((o) => `${o.preparacionId || ''}:${o.productoId || ''}`).sort().join(',');

    setCartItems((current) => {
      const existing = current.find((item) => (
        item.productId === String(product.id)
        && item.grupoArmado === grupoArmado
        && !item.pesoGramos
        && opcionesKey(item.opciones) === opcionesKey(opciones)
      ));
      if (existing) {
        return current.map((item) => (
          item.id === existing.id ? { ...item, quantity: item.quantity + 1 } : item
        ));
      }
      return [
        ...current,
        { id: cryptoRandomId(), productId: String(product.id), quantity: 1, notes: '', adicionales: [], opciones, pesoGramos: null, grupoArmado },
      ];
    });
  };

  const productoTieneOpciones = (product) => (
    Array.isArray(product.grupos_opciones) && product.grupos_opciones.length > 0
  );

  const handleAgregarProducto = (product) => {
    // Primero el peso (si aplica) y después los acompañantes: así el mesero sabe
    // cuánto va a pesar el corte antes de que le pregunten con qué lo acompaña.
    if (product.venta_por_peso) {
      setPesoPickerFor(product);
      return;
    }
    if (productoTieneOpciones(product)) {
      setOpcionesPickerFor(product);
      return;
    }
    addToCart(product);
  };

  const addAddonToCartItem = (itemId, addonId) => {
    if (!addonId) {
      return;
    }
    const addonInfo = adicionales.find((entry) => String(entry.id) === String(addonId));
    if (!addonInfo) {
      return;
    }
    setCartItems((current) => current.map((item) => {
      if (item.id !== itemId) {
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

  const changeAddonQuantity = (itemId, addonId, delta) => {
    setCartItems((current) => current.map((item) => {
      if (item.id !== itemId) {
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

  const removeAddonFromCartItem = (itemId, addonId) => {
    setCartItems((current) => current.map((item) => (
      item.id === itemId
        ? { ...item, adicionales: item.adicionales.filter((entry) => String(entry.preparacionId) !== String(addonId)) }
        : item
    )));
  };

  const changeCartQuantity = (itemId, delta) => {
    setCartItems((current) => current
      .map((item) => (item.id === itemId ? { ...item, quantity: item.quantity + delta } : item))
      .filter((item) => item.quantity > 0));
  };

  const changeCartPeso = (itemId, delta) => {
    setCartItems((current) => current
      .map((item) => (item.id === itemId ? { ...item, pesoGramos: Number(item.pesoGramos || 0) + delta } : item))
      .filter((item) => item.pesoGramos === null || item.pesoGramos >= 10));
  };

  const updateCartNotes = (itemId, notes) => {
    setCartItems((current) => current.map((item) => (
      item.id === itemId ? { ...item, notes } : item
    )));
  };

  const removeCartItem = (itemId) => {
    setCartItems((current) => current.filter((item) => item.id !== itemId));
  };

  const getCartQuantity = (productId) => cartItems
    .filter((item) => item.productId === String(productId))
    .reduce((total, item) => total + (item.pesoGramos ? 1 : item.quantity), 0);

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (!orderHeader.cliente.trim()) {
      setFeedbackType('error');
      setFeedback('Ingresa el nombre del cliente antes de guardar el pedido.');
      return;
    }

    if (orderHeader.tipoPedido === 'local' && !orderHeader.mesaId) {
      setFeedbackType('error');
      setFeedback('Selecciona una mesa antes de guardar el pedido.');
      return;
    }

    if (cartItems.length === 0) {
      setFeedbackType('error');
      setFeedback('Agrega al menos un plato para el pedido.');
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
        cliente_cedula: orderHeader.clienteCedula,
        cliente_telefono: orderHeader.clienteTelefono,
        notas: orderHeader.notas,
        items: cartItems.map((item) => ({
          product_id: Number(item.productId),
          cantidad: Number(item.quantity || 1),
          peso_gramos: item.pesoGramos ? Number(item.pesoGramos) : null,
          grupo_armado: item.grupoArmado ? Number(item.grupoArmado) : null,
          notas: item.notes,
          adicionales: (item.adicionales || []).map((addon) => ({
            preparacion_id: Number(addon.preparacionId),
            cantidad: Number(addon.cantidad || 1),
          })),
          opciones: (item.opciones || []).map((opcion) => (
            opcion.productoId ? {
              grupo_id: Number(opcion.grupoId),
              producto_id: Number(opcion.productoId),
            } : {
              grupo_id: Number(opcion.grupoId),
              preparacion_id: Number(opcion.preparacionId),
            }
          )),
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
      markClean({ cartItems, orderHeader });
    } catch (error) {
      setFeedbackType('error');
      setFeedback('Error de conexion al actualizar el pedido. Verifica la red e intenta otra vez.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const renderCartLine = (item) => {
    const product = products.find((entry) => String(entry.id) === String(item.productId));
    if (!product) {
      return null;
    }
    const promotion = promotionsByProductId[product.id];
    const unitPrice = getUnitPrice(product, promotionsByProductId);
    const lineTotal = computeItemTotal(item, products, promotionsByProductId);

    return (
      <div key={item.id} style={cartLineStyle}>
        <div style={cartLineTopStyle}>
          <div style={cartLineNameStyle}>
            {product.nombre}
            {promotion ? <span style={promoInlineBadgeStyle}>-{promotion.porcentaje_descuento}%</span> : null}
          </div>
          <button type="button" onClick={() => removeCartItem(item.id)} style={cartRemoveButtonStyle} aria-label={`Quitar ${product.nombre}`}>
            ×
          </button>
        </div>
        <div style={cartLineControlsStyle}>
          {item.pesoGramos !== null ? (
            <div style={qtyStepperStyle}>
              <button type="button" onClick={() => changeCartPeso(item.id, -50)} style={qtyButtonStyle}>−</button>
              <span style={qtyValueStyle}>{item.pesoGramos} g</span>
              <button type="button" onClick={() => changeCartPeso(item.id, 50)} style={qtyButtonStyle}>+</button>
            </div>
          ) : (
            <div style={qtyStepperStyle}>
              <button type="button" onClick={() => changeCartQuantity(item.id, -1)} style={qtyButtonStyle}>−</button>
              <span style={qtyValueStyle}>{item.quantity}</span>
              <button type="button" onClick={() => changeCartQuantity(item.id, 1)} style={qtyButtonStyle}>+</button>
            </div>
          )}
          <div style={cartLineSubtotalStyle}>
            ${lineTotal.toFixed(2)}
            <BsAmount amountUsd={lineTotal} tasa={tasaCambio} />
          </div>
        </div>
        {item.pesoGramos !== null ? (
          <div style={pesoUnitPriceHintStyle}>${unitPrice.toFixed(2)}/kg</div>
        ) : null}
        <input
          type="text"
          value={item.notes}
          onChange={(event) => updateCartNotes(item.id, event.target.value)}
          placeholder="Indicaciones (sin cebolla, término medio...)"
          style={cartNotesInputStyle}
        />

        {(item.opciones || []).length > 0 ? (
          <div style={opcionesElegidasWrapStyle}>
            {item.opciones.map((opcion) => (
              <span key={`${opcion.grupoId}-${opcion.preparacionId || ''}-${opcion.productoId || ''}`} style={opcionElegidaChipStyle}>
                {opcion.nombre}
                {opcion.precioAdicional > 0 ? ` (+$${Number(opcion.precioAdicional).toFixed(2)})` : ''}
              </span>
            ))}
          </div>
        ) : null}

        {adicionales.length > 0 ? (
          <div style={addonSectionStyle}>
            {(item.adicionales || []).map((addon) => (
              <div key={addon.preparacionId} style={addonChipStyle}>
                <span>{addon.nombre}</span>
                <div style={qtyStepperStyle}>
                  <button type="button" onClick={() => changeAddonQuantity(item.id, addon.preparacionId, -1)} style={qtyButtonStyle}>−</button>
                  <span style={qtyValueStyle}>{addon.cantidad}</span>
                  <button type="button" onClick={() => changeAddonQuantity(item.id, addon.preparacionId, 1)} style={qtyButtonStyle}>+</button>
                </div>
                <span style={addonPriceStyle}>
                  ${(Number(addon.precioUnitario || 0) * addon.cantidad).toFixed(2)}
                  <BsAmount amountUsd={Number(addon.precioUnitario || 0) * addon.cantidad} tasa={tasaCambio} />
                </span>
                <button type="button" onClick={() => removeAddonFromCartItem(item.id, addon.preparacionId)} style={cartRemoveButtonStyle} aria-label={`Quitar ${addon.nombre}`}>
                  ×
                </button>
              </div>
            ))}
            <select
              value=""
              onChange={(event) => addAddonToCartItem(item.id, event.target.value)}
              style={addonSelectStyle}
            >
              <option value="">+ Agregar adicional (extra pagado)...</option>
              {adicionales.map((addon) => (
                <option key={addon.id} value={addon.id}>
                  {addon.nombre} — ${Number(addon.precio || 0).toFixed(2)}
                  {formatBs(addon.precio, tasaCambio) ? ` (${formatBs(addon.precio, tasaCambio)})` : ''}
                </option>
              ))}
            </select>
          </div>
        ) : null}
      </div>
    );
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
        <button type="button" onClick={() => guard(onBack)} style={ghostButtonStyle(isCompact)}>
          Volver a pedidos
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
            <span style={labelStyle}>Cliente *</span>
            <input
              type="text"
              placeholder="Nombre del cliente"
              value={orderHeader.cliente}
              onChange={(event) => setOrderHeader((current) => ({ ...current, cliente: event.target.value }))}
              style={inputStyle(isCompact)}
              required
            />
          </label>

          <label style={fieldWrapStyle}>
            <span style={labelStyle}>Cédula</span>
            <input
              type="text"
              placeholder="V-12345678"
              value={orderHeader.clienteCedula}
              onChange={(event) => setOrderHeader((current) => ({ ...current, clienteCedula: event.target.value }))}
              style={inputStyle(isCompact)}
            />
          </label>

          <label style={fieldWrapStyle}>
            <span style={labelStyle}>Teléfono</span>
            <input
              type="text"
              placeholder="0412-1234567"
              value={orderHeader.clienteTelefono}
              onChange={(event) => setOrderHeader((current) => ({ ...current, clienteTelefono: event.target.value }))}
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
                      onClick={() => handleAgregarProducto(product)}
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
                              <span style={pricePromoStyle}>${Number(promotion.precio_descuento).toFixed(2)}{product.venta_por_peso ? '/kg' : ''}</span>
                              <BsAmount amountUsd={promotion.precio_descuento} tasa={tasaCambio} style={{ marginLeft: 0 }} />
                            </span>
                          ) : (
                            <span style={productCardPriceGroupStyle}>
                              <span style={priceStyle}>${Number(product.precio_venta).toFixed(2)}{product.venta_por_peso ? '/kg' : ''}</span>
                              <BsAmount amountUsd={product.precio_venta} tasa={tasaCambio} style={{ marginLeft: 0 }} />
                            </span>
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

            <div style={armarPlatoBarStyle}>
              {!armarPlatoActivo ? (
                <button type="button" onClick={handleStartArmarPlato} style={armarPlatoButtonStyle}>
                  <span aria-hidden="true">🍽</span> Armar plato
                </button>
              ) : (
                <>
                  <span style={armarPlatoLabelStyle}>Armando Plato {grupoActual}</span>
                  <button type="button" onClick={handleNuevoPlato} style={nuevoPlatoButtonStyle}>+ Nuevo plato</button>
                  <button type="button" onClick={handleTerminarArmado} style={terminarArmadoButtonStyle}>Terminar</button>
                </>
              )}
            </div>

            <div style={cartListStyle(isCompact)}>
              {cartItems.length === 0 ? (
                <div style={cartEmptyStyle}>Toca un plato del menú para agregarlo aquí.</div>
              ) : (
                <>
                  {groupedCartItems.platos.map(({ grupoId, items }) => {
                    const isActivePlato = armarPlatoActivo && grupoId === grupoActual;
                    return (
                      <div key={`plato-${grupoId}`} style={platoGroupStyle(isActivePlato)}>
                        <div style={platoGroupHeaderStyle}>
                          <span style={platoGroupTitleRowStyle}>
                            <span>Plato {grupoId}</span>
                            <span style={platoStatusBadgeStyle(isActivePlato)}>
                              {isActivePlato ? '● Armando' : '✓ Armado'}
                            </span>
                          </span>
                          <span style={platoGroupSubtotalStyle}>
                            ${items.reduce((sum, item) => sum + computeItemTotal(item, products, promotionsByProductId), 0).toFixed(2)}
                          </span>
                        </div>
                        <div style={platoGroupItemsStyle}>
                          {items.map((item) => renderCartLine(item))}
                        </div>
                      </div>
                    );
                  })}
                  {groupedCartItems.ungrouped.length > 0 ? (
                    <div style={ungroupedGroupStyle}>
                      <div style={ungroupedHeaderStyle}>Otros ítems (sin plato armado)</div>
                      <div style={platoGroupItemsStyle}>
                        {groupedCartItems.ungrouped.map((item) => renderCartLine(item))}
                      </div>
                    </div>
                  ) : null}
                </>
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
              <span style={cartTotalValueStyle}>
                ${subtotal.toFixed(2)}
                <BsAmount amountUsd={subtotal} tasa={tasaCambio} />
              </span>
            </div>

            <button type="submit" style={primaryButtonStyle(isCompact)} disabled={isSubmitting || cartItems.length === 0}>
              {isSubmitting ? 'Guardando...' : 'Guardar cambios'}
            </button>

            {feedback && <div style={feedbackStyle(feedbackType)}>{feedback}</div>}
          </aside>
        </div>
      </form>

      {isCompact && cartItems.length > 0 ? (
        <div style={mobileCartBarStyle}>
          <div style={{ color: '#fff', fontWeight: 700 }}>
            {cartCount} {cartCount === 1 ? 'plato' : 'platos'} · ${subtotal.toFixed(2)}
            <BsAmount amountUsd={subtotal} tasa={tasaCambio} style={{ color: '#e0e0e0' }} />
          </div>
          <button
            type="button"
            onClick={() => document.getElementById('cart-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
            style={mobileCartButtonStyle}
          >
            Ver pedido
          </button>
        </div>
      ) : null}

      {pesoPickerFor ? (
        <PesoPickerModal
          product={pesoPickerFor}
          tasaCambio={tasaCambio}
          onClose={() => setPesoPickerFor(null)}
          onConfirm={(gramos) => {
            const product = pesoPickerFor;
            setPesoPickerFor(null);
            if (productoTieneOpciones(product)) {
              setPendingPeso(gramos);
              setOpcionesPickerFor(product);
              return;
            }
            addToCart(product, { pesoGramos: gramos });
          }}
        />
      ) : null}

      {opcionesPickerFor ? (
        <OpcionesProductoModal
          product={opcionesPickerFor}
          products={products}
          onClose={() => {
            setOpcionesPickerFor(null);
            setPendingPeso(null);
          }}
          onConfirm={(opcionesElegidas) => {
            const product = opcionesPickerFor;
            setOpcionesPickerFor(null);
            addToCart(product, { pesoGramos: pendingPeso, opcionesElegidas });
            setPendingPeso(null);
          }}
        />
      ) : null}

      <UnsavedChangesModal open={isConfirmOpen} onConfirm={confirmLeave} onCancel={cancelLeave} />
    </section>
  );
}

function PesoPickerModal({ product, tasaCambio, onClose, onConfirm }) {
  const [gramos, setGramos] = useState(250);
  const precioPorKg = Number(product.precio_venta) || 0;
  const precioEstimado = precioPorKg * (gramos / 1000);

  return (
    <div style={modalBackdropStyle} onClick={onClose}>
      <div style={modalCardStyle} onClick={(event) => event.stopPropagation()}>
        <button type="button" onClick={onClose} style={modalCloseButtonStyle} aria-label="Cerrar">
          ×
        </button>
        <div style={modalBodyStyle}>
          <div style={modalTitleStyle}>{product.nombre}</div>
          <div style={modalCategoryStyle}>Precio por kilogramo: ${precioPorKg.toFixed(2)}</div>

          <label style={fieldWrapStyle}>
            <span style={labelStyle}>Gramos a pedir</span>
            <div style={pesoStepperRowStyle}>
              <button type="button" onClick={() => setGramos((current) => Math.max(10, current - 50))} style={qtyButtonStyle}>−</button>
              <input
                type="number"
                min="10"
                step="10"
                value={gramos}
                onChange={(event) => setGramos(Math.max(0, Number(event.target.value) || 0))}
                style={pesoInputStyle}
              />
              <button type="button" onClick={() => setGramos((current) => current + 50)} style={qtyButtonStyle}>+</button>
            </div>
          </label>

          <div style={modalFooterStyle}>
            <span style={productCardPriceGroupStyle}>
              <span style={{ ...priceStyle, fontSize: 20 }}>${precioEstimado.toFixed(2)}</span>
              <BsAmount amountUsd={precioEstimado} tasa={tasaCambio} style={{ fontSize: 12, marginLeft: 0 }} />
            </span>
            <button type="button" onClick={() => onConfirm(gramos)} disabled={!gramos || gramos <= 0} style={modalAddButtonStyle}>
              Agregar al pedido
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function OpcionesProductoModal({ product, products, onClose, onConfirm }) {
  const grupos = Array.isArray(product.grupos_opciones) ? product.grupos_opciones : [];
  const [seleccion, setSeleccion] = useState({});
  const [error, setError] = useState('');
  const [gruposSinElegir, setGruposSinElegir] = useState(null);

  // Pool de un grupo dinámico: los productos disponibles de su categoría en este
  // momento (excluyendo el propio plato), no una lista curada de antemano — ver
  // VGGrupoOpcionProducto.categoria_opciones.
  const poolPorGrupo = useMemo(() => {
    const pools = {};
    grupos.forEach((grupo) => {
      if (grupo.categoria_opciones_id) {
        pools[grupo.id] = (products || []).filter((item) => (
          String(item.categoria_id) === String(grupo.categoria_opciones_id) && item.id !== product.id
        ));
      }
    });
    return pools;
  }, [grupos, products, product.id]);

  const toggleOpcion = (grupo, id) => {
    setError('');
    setGruposSinElegir(null);
    setSeleccion((current) => {
      const actuales = current[grupo.id] || [];
      const yaElegida = actuales.includes(id);
      let next;
      if (yaElegida) {
        next = actuales.filter((v) => v !== id);
      } else if (grupo.categoria_opciones_id) {
        const max = grupo.maximo_selecciones;
        if (max && actuales.length >= max) {
          return current;
        }
        next = [...actuales, id];
      } else if (grupo.seleccion_multiple) {
        next = [...actuales, id];
      } else {
        next = [id];
      }
      return { ...current, [grupo.id]: next };
    });
  };

  const buildOpcionesElegidas = () => {
    const opcionesElegidas = [];
    grupos.forEach((grupo) => {
      const elegidas = seleccion[grupo.id] || [];
      if (grupo.categoria_opciones_id) {
        const pool = poolPorGrupo[grupo.id] || [];
        elegidas.forEach((productoId) => {
          const productoInfo = pool.find((item) => String(item.id) === String(productoId));
          opcionesElegidas.push({
            grupoId: grupo.id,
            productoId,
            nombre: productoInfo ? productoInfo.nombre : '',
            precioAdicional: 0,
          });
        });
        return;
      }
      elegidas.forEach((preparacionId) => {
        const opcionInfo = grupo.opciones.find((op) => String(op.preparacion_id) === String(preparacionId));
        opcionesElegidas.push({
          grupoId: grupo.id,
          preparacionId,
          nombre: opcionInfo ? opcionInfo.nombre : '',
          precioAdicional: opcionInfo ? Number(opcionInfo.precio_adicional || 0) : 0,
        });
      });
    });
    return opcionesElegidas;
  };

  const handleConfirmar = () => {
    for (const grupo of grupos) {
      if (grupo.categoria_opciones_id) {
        continue;
      }
      const elegidas = seleccion[grupo.id] || [];
      if (grupo.obligatorio && elegidas.length === 0) {
        setError(`Elige una opción de "${grupo.nombre}".`);
        return;
      }
    }
    setError('');

    // A esta altura, cualquier grupo curado obligatorio sin elección ya hizo
    // return arriba — lo que queda son grupos dinámicos (nunca bloquean) y
    // grupos curados opcionales (ej. acompañantes por subreceta). Ninguno de
    // los dos debe bloquear, pero si el mesero no eligió nada se le avisa una
    // vez antes de continuar sin acompañante, igual que con las guarniciones.
    const sinElegir = grupos.filter((grupo) => (seleccion[grupo.id] || []).length === 0);
    if (sinElegir.length > 0) {
      setGruposSinElegir(sinElegir.map((grupo) => grupo.nombre));
      return;
    }

    onConfirm(buildOpcionesElegidas());
  };

  const handleContinuarSinAcompanante = () => {
    setGruposSinElegir(null);
    onConfirm(buildOpcionesElegidas());
  };

  return (
    <div style={modalBackdropStyle} onClick={onClose}>
      <div style={modalCardStyle} onClick={(event) => event.stopPropagation()}>
        <button type="button" onClick={onClose} style={modalCloseButtonStyle} aria-label="Cerrar">
          ×
        </button>
        <div style={modalBodyStyle}>
          <div style={modalTitleStyle}>{product.nombre}</div>
          <div style={modalCategoryStyle}>Elige cómo va este plato</div>

          {grupos.map((grupo) => {
            const elegidas = seleccion[grupo.id] || [];
            const esDinamico = Boolean(grupo.categoria_opciones_id);
            const pool = esDinamico ? (poolPorGrupo[grupo.id] || []) : [];
            const max = grupo.maximo_selecciones;
            const alcanzoMax = esDinamico && max && elegidas.length >= max;
            return (
              <label key={grupo.id} style={fieldWrapStyle}>
                <span style={labelStyle}>
                  {grupo.nombre}
                  {esDinamico
                    ? ` (opcional${max ? ` — hasta ${max}` : ''}, elegidas ${elegidas.length}${max ? `/${max}` : ''})`
                    : (grupo.obligatorio ? ' *' : ' (opcional)') + (grupo.seleccion_multiple ? ' — puedes elegir varias' : '')}
                </span>
                {esDinamico && pool.length === 0 ? (
                  <div style={{ color: '#c8bbbb', fontSize: 13 }}>No hay opciones disponibles en este momento.</div>
                ) : null}
                <div style={{ display: 'grid', gap: 8 }}>
                  {(esDinamico ? pool : grupo.opciones).map((opcion) => {
                    const optionId = esDinamico ? opcion.id : opcion.preparacion_id;
                    const isSelected = elegidas.includes(optionId);
                    const disabled = esDinamico && alcanzoMax && !isSelected;
                    return (
                      <button
                        key={optionId}
                        type="button"
                        onClick={() => toggleOpcion(grupo, optionId)}
                        style={opcionButtonStyle(isSelected, disabled)}
                        disabled={disabled}
                      >
                        <span>{opcion.nombre}</span>
                        {!esDinamico && Number(opcion.precio_adicional) > 0 ? (
                          <span style={{ color: '#ffcf7d', fontWeight: 700 }}>+${Number(opcion.precio_adicional).toFixed(2)}</span>
                        ) : null}
                      </button>
                    );
                  })}
                </div>
              </label>
            );
          })}

          {error ? <div style={{ color: '#ff9d9d', fontSize: 13 }}>{error}</div> : null}

          {gruposSinElegir ? (
            <div style={avisoAcompananteStyle}>
              <span>No elegiste {gruposSinElegir.join(', ')}. ¿Seguro que quieres continuar sin acompañante?</span>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button type="button" onClick={handleContinuarSinAcompanante} style={modalAddButtonStyle}>
                  Continuar sin acompañante
                </button>
                <button type="button" onClick={() => setGruposSinElegir(null)} style={opcionButtonStyle(false)}>
                  Volver a elegir
                </button>
              </div>
            </div>
          ) : (
            <div style={modalFooterStyle}>
              <button type="button" onClick={handleConfirmar} style={modalAddButtonStyle}>
                Agregar al pedido
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function getUnitPrice(product, promotionsByProductId = {}) {
  const promotion = promotionsByProductId[product.id];
  return promotion ? Number(promotion.precio_descuento) : Number(product.precio_venta);
}

function computeItemTotal(item, productsList, promotionsByProductId = {}) {
  const product = productsList.find((entry) => String(entry.id) === String(item.productId));
  if (!product) {
    return 0;
  }
  const addonsTotal = (item.adicionales || []).reduce((sum, addon) => sum + Number(addon.precioUnitario || 0) * addon.cantidad, 0);
  const pesoFactor = item.pesoGramos ? Number(item.pesoGramos) / 1000 : 1;
  const opcionesTotal = (item.opciones || []).reduce((sum, opcion) => sum + Number(opcion.precioAdicional || 0), 0) * pesoFactor * item.quantity;
  return getUnitPrice(product, promotionsByProductId) * pesoFactor * item.quantity + addonsTotal + opcionesTotal;
}

function getCookie(name) {
  const all = `; ${document.cookie}`;
  const parts = all.split(`; ${name}=`);
  if (parts.length === 2) {
    return parts.pop().split(';').shift();
  }
  return '';
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

// --- Armar plato (agrupar varias líneas del carrito en un mismo plato) ---

const armarPlatoBarStyle = {
  display: 'flex',
  alignItems: 'center',
  flexWrap: 'wrap',
  gap: 8,
};

const armarPlatoButtonStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  border: '1px dashed rgba(125, 200, 255, 0.45)',
  borderRadius: 999,
  padding: '8px 14px',
  background: 'rgba(90, 170, 255, 0.08)',
  color: '#bfe0ff',
  fontWeight: 700,
  fontSize: 13,
  cursor: 'pointer',
  minHeight: 38,
};

const armarPlatoLabelStyle = {
  padding: '6px 12px',
  borderRadius: 999,
  background: 'rgba(90, 170, 255, 0.16)',
  border: '1px solid rgba(125, 200, 255, 0.4)',
  color: '#bfe0ff',
  fontSize: 12.5,
  fontWeight: 700,
};

const nuevoPlatoButtonStyle = {
  border: '1px solid rgba(125, 200, 255, 0.4)',
  borderRadius: 999,
  padding: '7px 12px',
  background: 'rgba(90, 170, 255, 0.1)',
  color: '#bfe0ff',
  fontWeight: 700,
  fontSize: 12.5,
  cursor: 'pointer',
  minHeight: 34,
};

const terminarArmadoButtonStyle = {
  border: '1px solid rgba(255,255,255,0.18)',
  borderRadius: 999,
  padding: '7px 12px',
  background: 'rgba(255,255,255,0.04)',
  color: '#fff',
  fontWeight: 700,
  fontSize: 12.5,
  cursor: 'pointer',
  minHeight: 34,
};

const platoGroupStyle = (isActive) => ({
  display: 'grid',
  gap: 8,
  padding: 8,
  borderRadius: 14,
  border: isActive ? '1px solid rgba(255, 176, 59, 0.6)' : '1px solid rgba(110, 220, 150, 0.35)',
  background: isActive ? 'rgba(255, 176, 59, 0.09)' : 'rgba(80, 200, 130, 0.07)',
  boxShadow: isActive ? '0 0 0 2px rgba(255, 176, 59, 0.14)' : 'none',
});

const platoGroupHeaderStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  color: '#fff',
  fontWeight: 800,
  fontSize: 12.5,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  padding: '0 2px',
};

const platoGroupTitleRowStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 8,
};

const platoStatusBadgeStyle = (isActive) => ({
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
  padding: '2px 8px',
  borderRadius: 999,
  fontSize: 10,
  fontWeight: 800,
  letterSpacing: '0.03em',
  textTransform: 'uppercase',
  background: isActive ? 'rgba(255, 176, 59, 0.2)' : 'rgba(80, 200, 130, 0.2)',
  color: isActive ? '#ffcf8a' : '#8ff0b8',
});

const platoGroupSubtotalStyle = {
  color: '#fff',
  fontWeight: 700,
};

const platoGroupItemsStyle = {
  display: 'grid',
  gap: 8,
};

const ungroupedGroupStyle = {
  display: 'grid',
  gap: 8,
  padding: 8,
  borderRadius: 14,
  border: '1px dashed rgba(255, 255, 255, 0.18)',
  background: 'rgba(255, 255, 255, 0.02)',
};

const ungroupedHeaderStyle = {
  color: '#c8bbbb',
  fontWeight: 800,
  fontSize: 12.5,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  padding: '0 2px',
};

const pesoUnitPriceHintStyle = {
  color: '#9a8686',
  fontSize: 11,
  marginTop: -4,
};

const pesoStepperRowStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 10,
};

const pesoInputStyle = {
  width: 90,
  textAlign: 'center',
  borderRadius: 12,
  border: '1px solid rgba(255,255,255,0.14)',
  background: 'rgba(12, 12, 12, 0.95)',
  color: '#fff',
  padding: '10px 8px',
  fontSize: 16,
  colorScheme: 'dark',
};

// --- Modal de selección de peso ---

const modalBackdropStyle = {
  position: 'fixed',
  inset: 0,
  zIndex: 20,
  background: 'rgba(0,0,0,0.7)',
  display: 'grid',
  placeItems: 'center',
  padding: 16,
};

const modalCardStyle = {
  position: 'relative',
  width: '100%',
  maxWidth: 420,
  maxHeight: '88vh',
  overflowY: 'auto',
  borderRadius: 20,
  border: '1px solid rgba(255,255,255,0.14)',
  background: 'linear-gradient(180deg, rgba(22, 10, 10, 0.98) 0%, rgba(10, 10, 10, 0.99) 100%)',
  boxShadow: '0 20px 50px rgba(0,0,0,0.5)',
};

const modalCloseButtonStyle = {
  position: 'absolute',
  top: 10,
  right: 10,
  zIndex: 2,
  width: 32,
  height: 32,
  borderRadius: '50%',
  border: 'none',
  background: 'rgba(0,0,0,0.55)',
  color: '#fff',
  fontSize: 20,
  lineHeight: 1,
  cursor: 'pointer',
  display: 'grid',
  placeItems: 'center',
};

const modalBodyStyle = {
  display: 'grid',
  gap: 10,
  padding: 16,
};

const modalTitleStyle = {
  color: '#fff',
  fontWeight: 700,
  fontSize: 20,
  lineHeight: 1.25,
};

const modalCategoryStyle = {
  color: '#f1b8b8',
  fontSize: 12,
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
};

const modalFooterStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 12,
  marginTop: 6,
  paddingTop: 12,
  borderTop: '1px solid rgba(255,255,255,0.1)',
};

const modalAddButtonStyle = {
  border: 'none',
  borderRadius: 999,
  padding: '11px 18px',
  background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
  minHeight: 44,
};

const opcionesElegidasWrapStyle = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 6,
};

const opcionElegidaChipStyle = {
  padding: '4px 9px',
  borderRadius: 999,
  border: '1px solid rgba(125, 200, 255, 0.35)',
  background: 'rgba(90, 170, 255, 0.08)',
  color: '#bfe0ff',
  fontSize: 12,
  fontWeight: 600,
};

const opcionButtonStyle = (isSelected, disabled = false) => ({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 10,
  width: '100%',
  boxSizing: 'border-box',
  textAlign: 'left',
  borderRadius: 12,
  border: isSelected ? '1px solid rgba(255, 132, 132, 0.7)' : '1px solid rgba(255, 255, 255, 0.14)',
  background: isSelected ? 'rgba(255, 90, 90, 0.16)' : 'rgba(255, 255, 255, 0.03)',
  color: disabled ? '#8a7a7a' : '#fff',
  padding: '10px 12px',
  fontSize: 14,
  fontWeight: isSelected ? 700 : 500,
  cursor: disabled ? 'not-allowed' : 'pointer',
  opacity: disabled ? 0.5 : 1,
});

const avisoAcompananteStyle = {
  display: 'grid',
  gap: 10,
  padding: '12px 14px',
  borderRadius: 14,
  border: '1px solid rgba(255, 190, 120, 0.35)',
  background: 'rgba(255, 170, 60, 0.1)',
  color: '#ffe1b8',
  fontSize: 13,
  marginTop: 6,
};

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

export default EditOrderPage;
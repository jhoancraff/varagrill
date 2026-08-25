import { useEffect, useMemo, useRef, useState } from 'react';
import BsAmount from './BsAmount';
import UnsavedChangesModal from './UnsavedChangesModal';
import useExchangeRate from '../hooks/useExchangeRate';
import useUnsavedChangesGuard from '../hooks/useUnsavedChangesGuard';
import { UNIT_OPTIONS, convertirCantidad } from '../utils/unitConversion';

const emptyForm = {
  id: null,
  nombre: '',
  descripcion: '',
  categoria_id: '',
  precio_venta: '',
  costo_estimado: '',
  tiempo_preparacion_min: '0',
  disponible: true,
  venta_por_peso: false,
  vinculo_tipo: '',
  vinculo_id: '',
};

const emptyIngredientDraft = {
  search: '',
  id: '',
  unidadBase: '',
  unidad: '',
  cantidad: '',
};

let opcionesUidSeq = 0;
function nextOpcionesUid(prefix) {
  opcionesUidSeq += 1;
  return `${prefix}-${opcionesUidSeq}`;
}

function crearGrupoOpcionVacio() {
  return {
    uid: nextOpcionesUid('grupo'),
    nombre: '',
    obligatorio: true,
    seleccion_multiple: false,
    opciones: [],
  };
}

function AnalystEditProductPage({ isMobile, isAdmin, productId, onBack, onProductsChanged }) {
  const tasaCambio = useExchangeRate();
  const ingredientPickerRef = useRef(null);
  const [categories, setCategories] = useState([]);
  const [recetas, setRecetas] = useState([]);
  const [subrecetas, setSubrecetas] = useState([]);
  const [ingredients, setIngredients] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [ingredientDraft, setIngredientDraft] = useState(emptyIngredientDraft);
  const [ingredientes, setIngredientes] = useState([]);
  const [gruposOpciones, setGruposOpciones] = useState([]);
  const [opcionDraftByGrupo, setOpcionDraftByGrupo] = useState({});
  const [showIngredientResults, setShowIngredientResults] = useState(false);
  const [currentImageUrl, setCurrentImageUrl] = useState('');
  const [imageFile, setImageFile] = useState(null);
  const [imagePreview, setImagePreview] = useState('');
  const [removeImageRequested, setRemoveImageRequested] = useState(false);
  const [confirmingImageRemoval, setConfirmingImageRemoval] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const fileInputRef = useRef(null);
  const { guard, isConfirmOpen, confirmLeave, cancelLeave, markClean } = useUnsavedChangesGuard({
    form, ingredientes, gruposOpciones, hasNewImage: Boolean(imageFile), removeImageRequested,
  });

  useEffect(() => {
    const handlePointerDown = (event) => {
      if (ingredientPickerRef.current && !ingredientPickerRef.current.contains(event.target)) {
        setShowIngredientResults(false);
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('touchstart', handlePointerDown);

    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('touchstart', handlePointerDown);
    };
  }, []);

  useEffect(() => {
    if (!isAdmin) {
      setLoading(false);
      return;
    }

    const loadProduct = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/admin/productos/', {
          credentials: 'include',
          cache: 'no-store',
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || 'No se pudo cargar el producto.');
        }

        const selectedProduct = (data.products || []).find((entry) => String(entry.id) === String(productId));
        if (!selectedProduct) {
          throw new Error('El producto seleccionado no existe.');
        }

        setCategories(Array.isArray(data.categories) ? data.categories : []);
        setRecetas(Array.isArray(data.recetas) ? data.recetas : []);
        setSubrecetas(Array.isArray(data.subrecetas) ? data.subrecetas : []);
        setIngredients(Array.isArray(data.ingredients) ? data.ingredients : []);
        const vinculoTipo = selectedProduct.receta_vinculada_id ? 'receta' : selectedProduct.subreceta_vinculada_id ? 'subreceta' : '';
        const loadedForm = {
          id: selectedProduct.id,
          nombre: selectedProduct.nombre || '',
          descripcion: selectedProduct.descripcion || '',
          categoria_id: selectedProduct.categoria_id ? String(selectedProduct.categoria_id) : '',
          precio_venta: selectedProduct.precio_venta || '',
          costo_estimado: selectedProduct.costo_estimado || '',
          tiempo_preparacion_min: String(selectedProduct.tiempo_preparacion_min ?? '0'),
          disponible: Boolean(selectedProduct.disponible),
          venta_por_peso: Boolean(selectedProduct.venta_por_peso),
          vinculo_tipo: vinculoTipo,
          vinculo_id: vinculoTipo === 'receta'
            ? String(selectedProduct.receta_vinculada_id)
            : vinculoTipo === 'subreceta'
              ? String(selectedProduct.subreceta_vinculada_id)
              : '',
        };
        const loadedIngredientes = (Array.isArray(selectedProduct.ingredientes) ? selectedProduct.ingredientes : [])
          .filter((item) => item.tipo === 'ingrediente')
          .map((item) => ({
            uid: `ingrediente-${item.referencia_id}`,
            referencia_id: item.referencia_id,
            nombre: item.nombre,
            unidadBase: item.unidad || 'unidad',
            cantidad: item.cantidad,
            unidad: item.unidad || 'unidad',
          }));
        const loadedGruposOpciones = (Array.isArray(selectedProduct.grupos_opciones) ? selectedProduct.grupos_opciones : []).map((grupo) => ({
          uid: nextOpcionesUid('grupo'),
          nombre: grupo.nombre || '',
          obligatorio: Boolean(grupo.obligatorio),
          seleccion_multiple: Boolean(grupo.seleccion_multiple),
          opciones: (Array.isArray(grupo.opciones) ? grupo.opciones : []).map((opcion) => ({
            uid: nextOpcionesUid('opcion'),
            preparacion_id: opcion.preparacion_id,
            nombre: opcion.preparacion_nombre,
            precio_adicional: opcion.precio_adicional || '0',
          })),
        }));
        setForm(loadedForm);
        setIngredientes(loadedIngredientes);
        setGruposOpciones(loadedGruposOpciones);
        markClean({
          form: loadedForm, ingredientes: loadedIngredientes, gruposOpciones: loadedGruposOpciones,
          hasNewImage: false, removeImageRequested: false,
        });
        setCurrentImageUrl(selectedProduct.imagen_url || '');
      } catch (error) {
        setMessage(error.message || 'No se pudo cargar el producto.');
      } finally {
        setLoading(false);
      }
    };

    loadProduct();
  }, [isAdmin, productId]);

  const handleChange = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const selectedVinculo = form.vinculo_id
    ? (form.vinculo_tipo === 'receta' ? recetas : subrecetas).find((item) => String(item.id) === String(form.vinculo_id))
    : null;

  const filteredIngredients = useMemo(() => {
    const query = ingredientDraft.search.trim().toLowerCase();
    if (!query) {
      return ingredients;
    }
    return ingredients.filter((item) => String(item.nombre || '').toLowerCase().includes(query));
  }, [ingredients, ingredientDraft.search]);

  const handleSelectIngredient = (item) => {
    const unidadBase = item.unidad_medida || 'unidad';
    setIngredientDraft((current) => ({
      ...current,
      id: String(item.id),
      search: item.nombre,
      unidadBase,
      unidad: unidadBase,
    }));
    setShowIngredientResults(false);
  };

  const handleAddIngrediente = () => {
    if (!ingredientDraft.id) {
      setMessage('Selecciona un ingrediente.');
      return;
    }
    if (!ingredientDraft.cantidad && !form.venta_por_peso) {
      setMessage('Define la cantidad que lleva el producto.');
      return;
    }

    const ingredient = ingredients.find((item) => String(item.id) === String(ingredientDraft.id));
    if (!ingredient) {
      setMessage('El ingrediente seleccionado ya no existe.');
      return;
    }

    if (ingredientes.some((item) => String(item.referencia_id) === String(ingredient.id))) {
      setMessage('Ese ingrediente ya está agregado a este producto.');
      return;
    }

    const usaProporcion1a1 = !ingredientDraft.cantidad && form.venta_por_peso;
    const unidadBase = ingredient.unidad_medida || 'unidad';

    setIngredientes((current) => ([
      ...current,
      {
        uid: `ingrediente-${ingredient.id}`,
        referencia_id: ingredient.id,
        nombre: ingredient.nombre,
        unidadBase,
        cantidad: usaProporcion1a1 ? '1' : ingredientDraft.cantidad,
        unidad: usaProporcion1a1 ? unidadBase : (ingredientDraft.unidad || unidadBase),
      },
    ]));
    setIngredientDraft(emptyIngredientDraft);
    setMessage('');
  };

  const handleRemoveIngrediente = (uid) => {
    setIngredientes((current) => current.filter((item) => item.uid !== uid));
  };

  const handleAddGrupoOpcion = () => {
    setGruposOpciones((current) => [...current, crearGrupoOpcionVacio()]);
  };

  const handleRemoveGrupoOpcion = (grupoUid) => {
    setGruposOpciones((current) => current.filter((grupo) => grupo.uid !== grupoUid));
  };

  const handleUpdateGrupoOpcion = (grupoUid, field, value) => {
    setGruposOpciones((current) => current.map((grupo) => (
      grupo.uid === grupoUid ? { ...grupo, [field]: value } : grupo
    )));
  };

  const handleAddOpcionAGrupo = (grupoUid) => {
    const draft = opcionDraftByGrupo[grupoUid] || { preparacion_id: '', precio_adicional: '0' };
    if (!draft.preparacion_id) {
      setMessage('Selecciona una subreceta para la opción.');
      return;
    }
    const preparacion = subrecetas.find((item) => String(item.id) === String(draft.preparacion_id));
    if (!preparacion) {
      setMessage('Esa subreceta ya no existe.');
      return;
    }
    setGruposOpciones((current) => current.map((grupo) => {
      if (grupo.uid !== grupoUid) {
        return grupo;
      }
      if (grupo.opciones.some((opcion) => String(opcion.preparacion_id) === String(preparacion.id))) {
        setMessage('Esa opción ya está agregada a este grupo.');
        return grupo;
      }
      return {
        ...grupo,
        opciones: [
          ...grupo.opciones,
          { uid: nextOpcionesUid('opcion'), preparacion_id: preparacion.id, nombre: preparacion.nombre, precio_adicional: draft.precio_adicional || '0' },
        ],
      };
    }));
    setOpcionDraftByGrupo((current) => ({ ...current, [grupoUid]: { preparacion_id: '', precio_adicional: '0' } }));
    setMessage('');
  };

  const handleRemoveOpcionDeGrupo = (grupoUid, opcionUid) => {
    setGruposOpciones((current) => current.map((grupo) => (
      grupo.uid === grupoUid ? { ...grupo, opciones: grupo.opciones.filter((opcion) => opcion.uid !== opcionUid) } : grupo
    )));
  };

  const handleImageChange = (event) => {
    const file = event.target.files && event.target.files[0] ? event.target.files[0] : null;
    setImageFile(file);
    setImagePreview(file ? URL.createObjectURL(file) : '');
    if (file) {
      setRemoveImageRequested(false);
      setConfirmingImageRemoval(false);
    }
  };

  const handleRequestRemoveImage = () => {
    setConfirmingImageRemoval(true);
  };

  const handleCancelRemoveImage = () => {
    setConfirmingImageRemoval(false);
  };

  const handleConfirmRemoveImage = () => {
    setRemoveImageRequested(true);
    setConfirmingImageRemoval(false);
    setImageFile(null);
    setImagePreview('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleUndoRemoveImage = () => {
    setRemoveImageRequested(false);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (!form.categoria_id) {
      setMessage('Debes seleccionar una categoría para el producto.');
      return;
    }

    setSaving(true);
    try {
      const formData = new FormData();
      formData.append('action', 'update');
      formData.append('id', form.id);
      formData.append('nombre', form.nombre);
      formData.append('descripcion', form.descripcion);
      formData.append('categoria_id', form.categoria_id);
      formData.append('precio_venta', form.precio_venta || '0');
      formData.append('costo_estimado', form.costo_estimado);
      formData.append('tiempo_preparacion_min', form.tiempo_preparacion_min || '0');
      formData.append('disponible', form.disponible ? 'true' : 'false');
      formData.append('venta_por_peso', form.venta_por_peso ? 'true' : 'false');
      formData.append('vinculo_tipo', form.vinculo_tipo);
      formData.append('vinculo_id', form.vinculo_id);
      formData.append('componentes', JSON.stringify(ingredientes.map((item) => ({
        tipo: 'ingrediente',
        referencia_id: item.referencia_id,
        cantidad: item.cantidad,
        unidad: item.unidad,
      }))));
      formData.append('grupos_opciones', JSON.stringify(gruposOpciones.map((grupo) => ({
        nombre: grupo.nombre,
        obligatorio: grupo.obligatorio,
        seleccion_multiple: grupo.seleccion_multiple,
        opciones: grupo.opciones.map((opcion) => ({
          preparacion_id: opcion.preparacion_id,
          precio_adicional: opcion.precio_adicional || '0',
        })),
      }))));
      if (imageFile) {
        formData.append('imagen', imageFile);
      } else if (removeImageRequested) {
        formData.append('eliminar_imagen', 'true');
      }

      const response = await fetch('/api/admin/productos/', {
        method: 'POST',
        credentials: 'include',
        body: formData,
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo actualizar el producto.');
      }

      setMessage(data.message || 'Producto actualizado correctamente.');
      setCurrentImageUrl(data.product ? data.product.imagen_url : currentImageUrl);
      setImageFile(null);
      setImagePreview('');
      setRemoveImageRequested(false);
      markClean({ form, ingredientes, gruposOpciones, hasNewImage: false, removeImageRequested: false });
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
      if (onProductsChanged) {
        onProductsChanged();
      }
    } catch (error) {
      setMessage(error.message || 'No se pudo actualizar el producto.');
    } finally {
      setSaving(false);
    }
  };

  if (!isAdmin) {
    return (
      <section style={containerStyle(isMobile)}>
        <div style={badgeStyle}>Editar producto</div>
        <h2 style={titleStyle(isMobile)}>Acceso restringido</h2>
        <div style={noticeStyle}>Solo el rol Administrador puede modificar productos.</div>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          Volver al reporte
        </button>
      </section>
    );
  }

  return (
    <section style={containerStyle(isMobile)}>
      <div style={badgeStyle}>Editar producto</div>
      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Actualización de producto</h2>
          <p style={subtitleStyle}>Modifica los datos del producto. Si no subes una imagen nueva, se conserva la actual.</p>
        </div>
      </div>

      {message ? <div style={noticeStyle}>{message}</div> : null}

      <form onSubmit={handleSubmit} style={panelStyle}>
        {loading ? <div style={emptyStateStyle}>Cargando producto...</div> : null}
        {!loading ? (
          <>
            <div style={formGridStyle(isMobile)}>
              <label style={fieldStyle}>
                <span style={labelStyle}>Nombre del producto</span>
                <input value={form.nombre} onChange={(event) => handleChange('nombre', event.target.value)} style={inputStyle} required />
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Categoría *</span>
                <select value={form.categoria_id} onChange={(event) => handleChange('categoria_id', event.target.value)} style={inputStyle} required>
                  <option value="">Selecciona una categoría</option>
                  {categories.map((category) => (
                    <option key={category.id} value={category.id}>{category.nombre}</option>
                  ))}
                </select>
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>
                  {form.venta_por_peso ? 'Precio por kilogramo' : 'Precio de venta'}
                  <BsAmount amountUsd={form.precio_venta} tasa={tasaCambio} />
                </span>
                <input type="number" min="0" step="0.01" value={form.precio_venta} onChange={(event) => handleChange('precio_venta', event.target.value)} style={inputStyle} />
                {form.venta_por_peso ? (
                  <span style={ventaPorPesoHintStyle}>El mesero indicará los gramos al pedir; el sistema calcula el subtotal y descuenta el inventario en base a ese peso.</span>
                ) : null}
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Costo estimado</span>
                <input type="number" min="0" step="0.01" value={form.costo_estimado} onChange={(event) => handleChange('costo_estimado', event.target.value)} style={inputStyle} />
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Tiempo de preparación (min)</span>
                <input type="number" min="0" step="1" value={form.tiempo_preparacion_min} onChange={(event) => handleChange('tiempo_preparacion_min', event.target.value)} style={inputStyle} />
              </label>
              <label style={toggleRowStyle}>
                <input type="checkbox" checked={form.disponible} onChange={(event) => handleChange('disponible', event.target.checked)} />
                <span>Producto disponible</span>
              </label>
              <label style={toggleRowStyle}>
                <input type="checkbox" checked={form.venta_por_peso} onChange={(event) => handleChange('venta_por_peso', event.target.checked)} />
                <span>Se vende por peso (precio por kilogramo)</span>
              </label>
            </div>

            <div style={linkCardStyle}>
              <div style={labelStyle}>Vincular con Receta o Subreceta (opcional)</div>
              <p style={linkHintStyle}>Así, cuando el mesero pida este producto, cocina verá también de qué está compuesto.</p>
              {ingredientes.length > 0 ? (
                <div style={noticeStyle}>Quita los ingredientes propios de abajo para poder vincular una receta o subreceta.</div>
              ) : (
                <>
                  <div style={formGridStyle(isMobile)}>
                    <label style={fieldStyle}>
                      <span style={labelStyle}>Tipo de vínculo</span>
                      <select
                        value={form.vinculo_tipo}
                        onChange={(event) => setForm((current) => ({ ...current, vinculo_tipo: event.target.value, vinculo_id: '' }))}
                        style={inputStyle}
                      >
                        <option value="">Ninguno</option>
                        <option value="receta">Receta</option>
                        <option value="subreceta">Subreceta</option>
                      </select>
                    </label>
                    {form.vinculo_tipo ? (
                      <label style={fieldStyle}>
                        <span style={labelStyle}>{form.vinculo_tipo === 'receta' ? 'Receta' : 'Subreceta'}</span>
                        <select value={form.vinculo_id} onChange={(event) => handleChange('vinculo_id', event.target.value)} style={inputStyle}>
                          <option value="">Selecciona...</option>
                          {(form.vinculo_tipo === 'receta' ? recetas : subrecetas).map((item) => (
                            <option key={item.id} value={item.id}>
                              {item.nombre} — costo unitario: ${Number(item.costo_unitario_calculado || 0).toFixed(2)}
                            </option>
                          ))}
                        </select>
                      </label>
                    ) : null}
                  </div>

                  {selectedVinculo ? (
                    <div style={costReferenceBoxStyle}>
                      <div>
                        <div style={costReferenceLabelStyle}>Costo unitario calculado de "{selectedVinculo.nombre}"</div>
                        <div style={costReferenceValueStyle}>${Number(selectedVinculo.costo_unitario_calculado || 0).toFixed(2)}</div>
                        <p style={costReferenceHintStyle}>
                          Es la suma del costo de los ingredientes/subrecetas de esta receta. Úsalo como referencia para definir el costo real del producto (empaque, mano de obra, etc.).
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleChange('costo_estimado', selectedVinculo.costo_unitario_calculado)}
                        style={useCostButtonStyle}
                      >
                        Usar este valor
                      </button>
                    </div>
                  ) : null}
                </>
              )}
            </div>

            <div style={linkCardStyle}>
              <style>
                {`.product-picker-option:hover { background: rgba(255, 90, 90, 0.16); }
                  .product-picker-option:focus-visible { outline: 1px solid rgba(255, 132, 132, 0.8); }
                `}
              </style>
              <div style={labelStyle}>Ingredientes que lleva este producto (opcional)</div>
              <p style={linkHintStyle}>
                Busca el ingrediente y define cuánto lleva el plato, en la unidad que te resulte más cómoda (ej. gramos).
                El sistema la convierte a la unidad del inventario del ingrediente al descontar stock cuando se venda.
                {form.venta_por_peso ? (
                  <> Como este producto se vende por peso, puedes dejar la cantidad vacía: se asume 1&nbsp;kg vendido = 1&nbsp;kg
                    descontado de ese ingrediente (ideal cuando el producto ES el ingrediente, ej. un corte de carne). El
                    mesero define el peso real al tomar el pedido y el descuento se ajusta solo a eso.</>
                ) : null}
              </p>

              {form.vinculo_tipo ? (
                <div style={noticeStyle}>Quita el vínculo de receta/subreceta de arriba para poder agregar ingredientes propios.</div>
              ) : (
                <>
                  <div style={composerRowStyle(isMobile)}>
                    <div ref={ingredientPickerRef} style={pickerWrapStyle}>
                      <input
                        value={ingredientDraft.search}
                        onChange={(event) => {
                          setIngredientDraft((current) => ({ ...current, search: event.target.value, id: '' }));
                          setShowIngredientResults(true);
                        }}
                        onFocus={() => setShowIngredientResults(true)}
                        placeholder="Buscar ingrediente"
                        style={inputStyle}
                      />
                      {showIngredientResults ? (
                        <div style={pickerListStyle}>
                          {filteredIngredients.length > 0 ? filteredIngredients.map((item) => (
                            <button
                              key={item.id}
                              type="button"
                              className="product-picker-option"
                              onMouseDown={(event) => event.preventDefault()}
                              onClick={() => handleSelectIngredient(item)}
                              style={pickerItemStyle}
                            >
                              <span style={pickerItemTitleStyle}>{item.nombre}</span>
                              <span style={pickerItemMetaStyle}>{item.unidad_medida || 'unidad'} · stock {item.stock_actual || '0'}</span>
                            </button>
                          )) : (
                            <div style={pickerEmptyStyle}>No hay ingredientes que coincidan.</div>
                          )}
                        </div>
                      ) : null}
                    </div>

                    <input
                      type="number"
                      min="0.001"
                      step="0.001"
                      value={ingredientDraft.cantidad}
                      onChange={(event) => setIngredientDraft((current) => ({ ...current, cantidad: event.target.value }))}
                      placeholder={form.venta_por_peso ? 'Cantidad (vacío = 1:1)' : 'Cantidad'}
                      style={inputStyle}
                    />

                    <select
                      value={ingredientDraft.unidad}
                      onChange={(event) => setIngredientDraft((current) => ({ ...current, unidad: event.target.value }))}
                      style={inputStyle}
                      disabled={!ingredientDraft.unidadBase || (form.venta_por_peso && !ingredientDraft.cantidad)}
                    >
                      {(UNIT_OPTIONS[ingredientDraft.unidadBase] || ['unidad']).map((unit) => (
                        <option key={unit} value={unit}>{unit}</option>
                      ))}
                    </select>

                    <button type="button" onClick={handleAddIngrediente} style={secondaryButtonStyle}>
                      Agregar ingrediente
                    </button>
                  </div>

                  {ingredientes.length > 0 ? (
                    <div style={{ display: 'grid', gap: 10 }}>
                      {ingredientes.map((item) => {
                        const convertido = item.unidad !== item.unidadBase
                          ? convertirCantidad(item.cantidad, item.unidad, item.unidadBase)
                          : null;
                        return (
                          <article key={item.uid} style={componentCardStyle}>
                            <div>
                              <div style={componentTitleStyle}>{item.nombre}</div>
                              <div style={componentMetaStyle}>
                                {item.cantidad} {item.unidad}
                                {convertido !== null ? ` (≈ ${convertido.toFixed(3)} ${item.unidadBase} de inventario)` : ''}
                              </div>
                            </div>
                            <button type="button" onClick={() => handleRemoveIngrediente(item.uid)} style={dangerButtonStyle}>
                              Quitar
                            </button>
                          </article>
                        );
                      })}
                    </div>
                  ) : null}
                </>
              )}
            </div>

            <div style={linkCardStyle}>
              <div style={labelStyle}>Opciones del pedido (opcional)</div>
              <p style={linkHintStyle}>
                Para platos con variantes que el mesero debe preguntar al pedir (ej. "Acompañante: Arepas o Casabe").
                Cada grupo puede ser obligatorio (elegir al menos una) y permitir una o varias opciones a la vez. Cada
                opción se apoya en una subreceta ya creada, para saber qué descontar de inventario.
              </p>

              {gruposOpciones.map((grupo) => {
                const draft = opcionDraftByGrupo[grupo.uid] || { preparacion_id: '', precio_adicional: '0' };
                return (
                  <div key={grupo.uid} style={grupoOpcionCardStyle}>
                    <div style={composerRowStyle(isMobile)}>
                      <input
                        placeholder='Nombre del grupo (ej. "Acompañante")'
                        value={grupo.nombre}
                        onChange={(event) => handleUpdateGrupoOpcion(grupo.uid, 'nombre', event.target.value)}
                        style={inputStyle}
                      />
                      <label style={toggleRowStyle}>
                        <input
                          type="checkbox"
                          checked={grupo.obligatorio}
                          onChange={(event) => handleUpdateGrupoOpcion(grupo.uid, 'obligatorio', event.target.checked)}
                        />
                        <span>Obligatorio</span>
                      </label>
                      <label style={toggleRowStyle}>
                        <input
                          type="checkbox"
                          checked={grupo.seleccion_multiple}
                          onChange={(event) => handleUpdateGrupoOpcion(grupo.uid, 'seleccion_multiple', event.target.checked)}
                        />
                        <span>Permite varias</span>
                      </label>
                      <button type="button" onClick={() => handleRemoveGrupoOpcion(grupo.uid)} style={dangerButtonStyle}>
                        Quitar grupo
                      </button>
                    </div>

                    {grupo.opciones.length > 0 ? (
                      <div style={{ display: 'grid', gap: 8 }}>
                        {grupo.opciones.map((opcion) => (
                          <div key={opcion.uid} style={componentCardStyle}>
                            <div>
                              <div style={componentTitleStyle}>{opcion.nombre}</div>
                              <div style={componentMetaStyle}>
                                {Number(opcion.precio_adicional || 0) > 0 ? `+ $${Number(opcion.precio_adicional).toFixed(2)}` : 'Sin costo adicional'}
                              </div>
                            </div>
                            <button type="button" onClick={() => handleRemoveOpcionDeGrupo(grupo.uid, opcion.uid)} style={dangerButtonStyle}>
                              Quitar
                            </button>
                          </div>
                        ))}
                      </div>
                    ) : null}

                    <div style={composerRowStyle(isMobile)}>
                      <select
                        value={draft.preparacion_id}
                        onChange={(event) => setOpcionDraftByGrupo((current) => ({ ...current, [grupo.uid]: { ...draft, preparacion_id: event.target.value } }))}
                        style={inputStyle}
                      >
                        <option value="">Selecciona una subreceta...</option>
                        {subrecetas.map((item) => (
                          <option key={item.id} value={item.id}>{item.nombre}</option>
                        ))}
                      </select>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        placeholder="Precio adicional"
                        value={draft.precio_adicional}
                        onChange={(event) => setOpcionDraftByGrupo((current) => ({ ...current, [grupo.uid]: { ...draft, precio_adicional: event.target.value } }))}
                        style={inputStyle}
                      />
                      <button type="button" onClick={() => handleAddOpcionAGrupo(grupo.uid)} style={secondaryButtonStyle}>
                        Agregar opción
                      </button>
                    </div>
                  </div>
                );
              })}

              <button type="button" onClick={handleAddGrupoOpcion} style={secondaryButtonStyle}>
                Agregar grupo de opciones
              </button>
            </div>

            <label style={fieldStyle}>
              <span style={labelStyle}>Descripción</span>
              <textarea rows={3} value={form.descripcion} onChange={(event) => handleChange('descripcion', event.target.value)} style={{ ...inputStyle, resize: 'vertical' }} />
            </label>

            <label style={fieldStyle}>
              <span style={labelStyle}>Reemplazar imagen (JPG, PNG, WEBP o GIF, máx. 5MB)</span>
              <input ref={fileInputRef} type="file" accept="image/jpeg,image/png,image/webp,image/gif" onChange={handleImageChange} style={inputStyle} />
            </label>

            <div style={previewRowStyle}>
              {currentImageUrl && !removeImageRequested ? (
                <div>
                  <div style={previewLabelStyle}>Imagen actual</div>
                  <img src={currentImageUrl} alt={form.nombre} style={previewImageStyle} />
                  {!confirmingImageRemoval ? (
                    <button type="button" onClick={handleRequestRemoveImage} style={removeImageButtonStyle}>
                      Eliminar imagen
                    </button>
                  ) : (
                    <div style={confirmRemoveBoxStyle}>
                      <span style={confirmRemoveTextStyle}>¿Seguro que deseas eliminar la imagen de este producto?</span>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        <button type="button" onClick={handleConfirmRemoveImage} style={dangerButtonStyle}>
                          Sí, eliminar imagen
                        </button>
                        <button type="button" onClick={handleCancelRemoveImage} style={secondaryButtonStyle}>
                          Cancelar
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ) : null}
              {currentImageUrl && removeImageRequested ? (
                <div style={confirmRemoveBoxStyle}>
                  <span style={confirmRemoveTextStyle}>La imagen se eliminará al guardar los cambios.</span>
                  <button type="button" onClick={handleUndoRemoveImage} style={secondaryButtonStyle}>
                    Deshacer
                  </button>
                </div>
              ) : null}
              {!currentImageUrl ? (
                <div style={previewLabelStyle}>Este producto aún no tiene imagen.</div>
              ) : null}
              {imagePreview ? (
                <div>
                  <div style={previewLabelStyle}>Imagen nueva</div>
                  <img src={imagePreview} alt="Vista previa" style={previewImageStyle} />
                </div>
              ) : null}
            </div>

            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <button type="submit" style={primaryButtonStyle} disabled={saving}>
                {saving ? 'Guardando...' : 'Guardar cambios'}
              </button>
              <button type="button" onClick={() => guard(onBack)} style={secondaryButtonStyle}>
                Volver al reporte
              </button>
            </div>
          </>
        ) : null}
      </form>

      <UnsavedChangesModal open={isConfirmOpen} onConfirm={confirmLeave} onCancel={cancelLeave} />
    </section>
  );
}

const containerStyle = (isMobile) => ({
  display: 'grid',
  gap: 18,
  padding: isMobile ? 6 : 10,
});

const composerRowStyle = (isMobile) => ({
  display: 'grid',
  gridTemplateColumns: isMobile ? '1fr' : 'minmax(220px, 2fr) minmax(100px, 0.6fr) minmax(80px, 0.5fr) auto',
  gap: 10,
  alignItems: 'center',
});

const pickerWrapStyle = {
  position: 'relative',
};

const pickerListStyle = {
  position: 'absolute',
  zIndex: 8,
  top: 'calc(100% + 6px)',
  left: 0,
  right: 0,
  maxHeight: 230,
  overflowY: 'auto',
  borderRadius: 14,
  border: '1px solid rgba(255, 132, 132, 0.4)',
  background: '#140d0d',
  boxShadow: '0 12px 24px rgba(0, 0, 0, 0.3)',
};

const pickerItemStyle = {
  width: '100%',
  textAlign: 'left',
  border: 'none',
  background: 'transparent',
  color: '#ffeaea',
  padding: '10px 12px',
  display: 'grid',
  gap: 3,
  cursor: 'pointer',
};

const pickerItemTitleStyle = {
  fontWeight: 700,
};

const pickerItemMetaStyle = {
  fontSize: 12,
  color: '#d8bcbc',
};

const pickerEmptyStyle = {
  padding: '10px 12px',
  color: '#d8bcbc',
  fontSize: 13,
};

const grupoOpcionCardStyle = {
  display: 'grid',
  gap: 10,
  padding: 12,
  borderRadius: 14,
  border: '1px solid rgba(255, 190, 120, 0.25)',
  background: 'rgba(255, 190, 120, 0.04)',
};

const componentCardStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 12,
  padding: '12px 14px',
  borderRadius: 14,
  border: '1px solid rgba(255, 255, 255, 0.08)',
  background: 'rgba(255, 255, 255, 0.03)',
};

const componentTitleStyle = {
  color: '#fff',
  fontWeight: 700,
};

const componentMetaStyle = {
  color: '#d2c3c3',
  fontSize: 13,
};

const dangerButtonStyle = {
  border: '1px solid rgba(255, 126, 126, 0.4)',
  borderRadius: 999,
  padding: '8px 14px',
  background: 'rgba(145, 33, 33, 0.25)',
  color: '#ffd3d3',
  fontWeight: 700,
  cursor: 'pointer',
};

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
  maxWidth: 720,
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

const emptyStateStyle = {
  minHeight: 80,
  display: 'grid',
  placeItems: 'center',
  borderRadius: 18,
  border: '1px dashed rgba(255, 255, 255, 0.12)',
  color: '#c8bbbb',
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
  background: 'rgba(255, 255, 255, 0.04)',
  padding: '11px 12px',
  color: '#fff',
  fontSize: 14,
};

const toggleRowStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 10,
  color: '#fff',
  fontWeight: 600,
  minHeight: 42,
};

const ventaPorPesoHintStyle = {
  color: '#c2adad',
  fontSize: 11.5,
  lineHeight: 1.4,
};

const linkCardStyle = {
  display: 'grid',
  gap: 8,
  padding: 14,
  borderRadius: 14,
  border: '1px solid rgba(255,255,255,0.08)',
  background: 'rgba(255,255,255,0.02)',
};

const linkHintStyle = {
  margin: 0,
  color: '#c2adad',
  fontSize: 12.5,
};

const costReferenceBoxStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 14,
  flexWrap: 'wrap',
  padding: '12px 14px',
  borderRadius: 14,
  border: '1px solid rgba(120, 220, 160, 0.35)',
  background: 'rgba(70, 200, 120, 0.08)',
};

const costReferenceLabelStyle = {
  color: '#bdf0cf',
  fontSize: 12,
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
};

const costReferenceValueStyle = {
  color: '#7dffa0',
  fontSize: 22,
  fontWeight: 800,
  marginTop: 2,
};

const costReferenceHintStyle = {
  margin: '4px 0 0',
  color: '#c2adad',
  fontSize: 12,
  maxWidth: 480,
};

const useCostButtonStyle = {
  border: '1px solid rgba(125, 255, 160, 0.4)',
  borderRadius: 999,
  padding: '9px 14px',
  background: 'rgba(125, 255, 160, 0.12)',
  color: '#bdf0cf',
  fontWeight: 700,
  cursor: 'pointer',
  whiteSpace: 'nowrap',
};

const previewRowStyle = {
  display: 'flex',
  gap: 20,
  flexWrap: 'wrap',
};

const removeImageButtonStyle = {
  marginTop: 8,
  display: 'block',
  border: '1px solid rgba(255, 126, 126, 0.4)',
  borderRadius: 999,
  padding: '7px 12px',
  background: 'rgba(145, 33, 33, 0.18)',
  color: '#ffd3d3',
  fontWeight: 700,
  fontSize: 12.5,
  cursor: 'pointer',
};

const confirmRemoveBoxStyle = {
  display: 'grid',
  gap: 10,
  padding: '12px 14px',
  borderRadius: 14,
  border: '1px solid rgba(255, 145, 145, 0.3)',
  background: 'rgba(255, 98, 98, 0.1)',
  maxWidth: 320,
};

const confirmRemoveTextStyle = {
  color: '#ffd8d8',
  fontSize: 13,
  lineHeight: 1.4,
};

const previewLabelStyle = {
  color: '#f0b4b4',
  fontSize: 12,
  fontWeight: 700,
  marginBottom: 6,
};

const previewImageStyle = {
  width: 140,
  height: 140,
  objectFit: 'cover',
  borderRadius: 16,
  border: '1px solid rgba(255, 255, 255, 0.14)',
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

export default AnalystEditProductPage;
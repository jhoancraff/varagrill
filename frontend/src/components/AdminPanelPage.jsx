import { useEffect, useMemo, useState } from 'react';

const initialInventory = [];

const initialRecipes = [];

const initialBeverages = [];

function AdminPanelPage({ isMobile, onBack }) {
  const [activeTab, setActiveTab] = useState('inventario');
  const [inventoryEntries, setInventoryEntries] = useState(initialInventory);
  const [inventoryForm, setInventoryForm] = useState({ nombre: '', categoria: 'Vegetales', cantidad: '', unidad: 'kg', proveedor: '' });
  const [recipes, setRecipes] = useState(initialRecipes);
  const [recipeForm, setRecipeForm] = useState({ nombre: '', ingredientes: '' });
  const [beverages, setBeverages] = useState(initialBeverages);
  const [beverageForm, setBeverageForm] = useState({ nombre: '', categoria: 'Jugos', precio: '' });
  const [editingInventoryId, setEditingInventoryId] = useState(null);
  const [editingRecipeId, setEditingRecipeId] = useState(null);
  const [editingBeverageId, setEditingBeverageId] = useState(null);
  const [currentView, setCurrentView] = useState('panel');
  const [statusMessage, setStatusMessage] = useState('');

  useEffect(() => {
    const loadCatalog = async () => {
      try {
        const response = await fetch('/api/admin/catalogo/', { credentials: 'include', cache: 'no-store' });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.message || 'No se pudo cargar el catálogo');
        }

        setInventoryEntries((data.inventory || []).map((item) => ({
          id: item.id,
          nombre: item.nombre,
          categoria: item.unidad_medida || 'Otros',
          cantidad: Number(item.stock_actual || 0),
          unidad: item.unidad_medida || 'unidad',
          proveedor: item.ultimo_proveedor || 'Sin proveedor',
        })));
        setRecipes((data.recipes || []).map((item) => ({
          id: item.id,
          nombre: item.nombre,
          ingredientes: `${item.rendimiento_cantidad || 0} ${item.rendimiento_unidad || 'unidad'}`,
        })));
        setBeverages((data.beverages || []).map((item) => ({
          id: item.id,
          nombre: item.nombre,
          categoria: item.categoria__nombre || 'Bebidas',
          precio: Number(item.precio_venta || 0),
        })));
      } catch (error) {
        setStatusMessage(error.message || 'No se pudo cargar el catálogo');
      }
    };

    loadCatalog();
  }, []);

  const summary = useMemo(() => ({
    items: inventoryEntries.length,
    recipes: recipes.length,
    beverages: beverages.length,
    lowStock: inventoryEntries.filter((item) => Number(item.cantidad) <= 6).length,
  }), [inventoryEntries, recipes, beverages]);

  const openIngredientReport = () => {
    setCurrentView('ingredientes');
    setActiveTab('inventario');
  };

  const openRecipeReport = () => {
    setCurrentView('recetas-listado');
    setActiveTab('recetas');
  };

  const backToPanel = () => {
    setCurrentView('panel');
  };

  const handleInventorySubmit = async (event) => {
    event.preventDefault();
    if (!inventoryForm.nombre.trim()) {
      return;
    }

    try {
      const response = await fetch('/api/admin/catalogo/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tipo: 'inventario',
          id: editingInventoryId || undefined,
          nombre: inventoryForm.nombre.trim(),
          categoria: inventoryForm.categoria,
          cantidad: inventoryForm.cantidad,
          unidad: inventoryForm.unidad.trim() || 'unidad',
          proveedor: inventoryForm.proveedor.trim() || 'Sin proveedor',
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.message || 'No se pudo guardar el inventario');
      }

      const nextItem = {
        id: data.item?.id || Date.now(),
        nombre: inventoryForm.nombre.trim(),
        categoria: inventoryForm.categoria,
        cantidad: Number(inventoryForm.cantidad || 0),
        unidad: inventoryForm.unidad.trim() || 'unidad',
        proveedor: inventoryForm.proveedor.trim() || 'Sin proveedor',
      };
      setInventoryEntries((current) => {
        if (editingInventoryId) {
          return current.map((entry) => (entry.id === editingInventoryId ? nextItem : entry));
        }
        return [nextItem, ...current];
      });
      setStatusMessage(data.message || 'Insumo guardado');
      setInventoryForm({ nombre: '', categoria: 'Vegetales', cantidad: '', unidad: 'kg', proveedor: '' });
      setEditingInventoryId(null);
      setActiveTab('inventario');
    } catch (error) {
      setStatusMessage(error.message || 'No se pudo guardar el inventario');
    }
  };

  const handleRecipeSubmit = async (event) => {
    event.preventDefault();
    if (!recipeForm.nombre.trim()) {
      return;
    }

    try {
      const response = await fetch('/api/admin/catalogo/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tipo: 'recetas',
          id: editingRecipeId || undefined,
          nombre: recipeForm.nombre.trim(),
          rendimiento_cantidad: '1',
          rendimiento_unidad: 'unidad',
          componentes: [
            { tipo: 'ingrediente', nombre: recipeForm.ingredientes.trim() || 'Ingrediente', cantidad: '1' },
          ],
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.message || 'No se pudo guardar la receta');
      }

      const nextRecipe = {
        id: data.item?.id || Date.now(),
        nombre: recipeForm.nombre.trim(),
        ingredientes: recipeForm.ingredientes.trim() || 'Ingredientes por definir',
      };
      setRecipes((current) => {
        if (editingRecipeId) {
          return current.map((entry) => (entry.id === editingRecipeId ? nextRecipe : entry));
        }
        return [nextRecipe, ...current];
      });
      setStatusMessage(data.message || 'Receta guardada');
      setRecipeForm({ nombre: '', ingredientes: '' });
      setEditingRecipeId(null);
      setActiveTab('recetas');
    } catch (error) {
      setStatusMessage(error.message || 'No se pudo guardar la receta');
    }
  };

  const handleDeleteInventory = async (id) => {
    const name = inventoryEntries.find((entry) => entry.id === id)?.nombre || 'este insumo';
    if (!window.confirm(`¿Deseas eliminar ${name}?`)) {
      return;
    }

    try {
      const response = await fetch('/api/admin/catalogo/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tipo: 'eliminar_inventario', id }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.message || 'No se pudo eliminar el insumo');
      }
      setInventoryEntries((current) => current.filter((entry) => entry.id !== id));
      setStatusMessage(data.message || 'Insumo eliminado');
    } catch (error) {
      setStatusMessage(error.message || 'No se pudo eliminar el insumo');
    }
  };

  const handleDeleteRecipe = async (id) => {
    const name = recipes.find((entry) => entry.id === id)?.nombre || 'esta receta';
    if (!window.confirm(`¿Deseas eliminar ${name}?`)) {
      return;
    }

    try {
      const response = await fetch('/api/admin/catalogo/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tipo: 'eliminar_receta', id }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.message || 'No se pudo eliminar la receta');
      }
      setRecipes((current) => current.filter((entry) => entry.id !== id));
      setStatusMessage(data.message || 'Receta eliminada');
    } catch (error) {
      setStatusMessage(error.message || 'No se pudo eliminar la receta');
    }
  };

  const handleDeleteBeverage = async (id) => {
    const name = beverages.find((entry) => entry.id === id)?.nombre || 'esta bebida';
    if (!window.confirm(`¿Deseas eliminar ${name}?`)) {
      return;
    }

    try {
      const response = await fetch('/api/admin/catalogo/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tipo: 'eliminar_bebida', id }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.message || 'No se pudo eliminar la bebida');
      }
      setBeverages((current) => current.filter((entry) => entry.id !== id));
      setStatusMessage(data.message || 'Bebida eliminada');
    } catch (error) {
      setStatusMessage(error.message || 'No se pudo eliminar la bebida');
    }
  };

  const handleBeverageSubmit = async (event) => {
    event.preventDefault();
    if (!beverageForm.nombre.trim()) {
      return;
    }

    try {
      const response = await fetch('/api/admin/catalogo/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tipo: 'bebidas',
          id: editingBeverageId || undefined,
          nombre: beverageForm.nombre.trim(),
          categoria: beverageForm.categoria,
          precio: beverageForm.precio,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.message || 'No se pudo guardar la bebida');
      }

      const nextBeverage = {
        id: data.item?.id || Date.now(),
        nombre: beverageForm.nombre.trim(),
        categoria: beverageForm.categoria,
        precio: Number(beverageForm.precio || 0),
      };
      setBeverages((current) => {
        if (editingBeverageId) {
          return current.map((entry) => (entry.id === editingBeverageId ? nextBeverage : entry));
        }
        return [nextBeverage, ...current];
      });
      setStatusMessage(data.message || 'Bebida guardada');
      setBeverageForm({ nombre: '', categoria: 'Jugos', precio: '' });
      setEditingBeverageId(null);
      setActiveTab('bebidas');
    } catch (error) {
      setStatusMessage(error.message || 'No se pudo guardar la bebida');
    }
  };

  if (currentView === 'ingredientes') {
    return (
      <section style={panelContainerStyle(isMobile)}>
        <div style={headerWrapStyle(isMobile)}>
          <div>
            <div style={eyebrowStyle}>Panel administrativo</div>
            <h2 style={titleStyle(isMobile)}>Ingredientes registrados</h2>
            <p style={subtitleStyle}>Revisa el inventario actual y administra cada ingrediente desde una vista dedicada.</p>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button type="button" onClick={backToPanel} style={backButtonStyle(isMobile)}>
              Volver al panel
            </button>
            <button type="button" onClick={onBack} style={backButtonStyle(isMobile)}>
              Volver al inicio
            </button>
          </div>
        </div>

        <div style={cardStyle}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <div style={sectionTitleStyle}>Inventario actual</div>
            <button type="button" onClick={() => { setCurrentView('panel'); setActiveTab('inventario'); }} style={secondaryButtonStyle}>
              + Nuevo ingreso
            </button>
          </div>
          <div style={{ display: 'grid', gap: 10 }}>
            {inventoryEntries.map((item) => (
              <div key={item.id} style={listItemStyle}>
                <div>
                  <div style={{ color: '#fff', fontWeight: 700 }}>{item.nombre}</div>
                  <div style={{ color: '#d0c1c1', fontSize: 12, marginTop: 4 }}>{item.categoria} · {item.cantidad} {item.unidad}</div>
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <div style={{ color: '#ffb4b4', fontSize: 12 }}>{item.proveedor}</div>
                  <button type="button" onClick={() => {
                    setEditingInventoryId(item.id);
                    setInventoryForm({
                      nombre: item.nombre,
                      categoria: item.categoria || 'Vegetales',
                      cantidad: String(item.cantidad || ''),
                      unidad: item.unidad || 'kg',
                      proveedor: item.proveedor || '',
                    });
                    setCurrentView('panel');
                    setActiveTab('inventario');
                  }} style={iconButtonStyle} title="Editar ingrediente">
                    ✏️
                  </button>
                  <button type="button" onClick={() => handleDeleteInventory(item.id)} style={iconButtonDangerStyle} title="Eliminar ingrediente">
                    🗑️
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
    );
  }

  if (currentView === 'recetas-listado') {
    return (
      <section style={panelContainerStyle(isMobile)}>
        <div style={headerWrapStyle(isMobile)}>
          <div>
            <div style={eyebrowStyle}>Panel administrativo</div>
            <h2 style={titleStyle(isMobile)}>Recetas registradas</h2>
            <p style={subtitleStyle}>Consulta tus recetas y gestiona edición o eliminación desde una vista separada.</p>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button type="button" onClick={backToPanel} style={backButtonStyle(isMobile)}>
              Volver al panel
            </button>
            <button type="button" onClick={onBack} style={backButtonStyle(isMobile)}>
              Volver al inicio
            </button>
          </div>
        </div>

        <div style={cardStyle}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <div style={sectionTitleStyle}>Recetas activas</div>
            <button type="button" onClick={() => { setCurrentView('panel'); setActiveTab('recetas'); }} style={secondaryButtonStyle}>
              + Nueva receta
            </button>
          </div>
          <div style={{ display: 'grid', gap: 10 }}>
            {recipes.map((recipe) => (
              <div key={recipe.id} style={listItemStyle}>
                <div>
                  <div style={{ color: '#fff', fontWeight: 700 }}>{recipe.nombre}</div>
                  <div style={{ color: '#d0c1c1', fontSize: 12, marginTop: 4 }}>{recipe.ingredientes}</div>
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <button type="button" onClick={() => {
                    setEditingRecipeId(recipe.id);
                    setRecipeForm({ nombre: recipe.nombre, ingredientes: recipe.ingredientes || '' });
                    setCurrentView('panel');
                    setActiveTab('recetas');
                  }} style={iconButtonStyle} title="Editar receta">
                    ✏️
                  </button>
                  <button type="button" onClick={() => handleDeleteRecipe(recipe.id)} style={iconButtonDangerStyle} title="Eliminar receta">
                    🗑️
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
    );
  }

  return (
    <section style={panelContainerStyle(isMobile)}>
      <div style={headerWrapStyle(isMobile)}>
        <div>
          <div style={eyebrowStyle}>Panel administrativo</div>
          <h2 style={titleStyle(isMobile)}>Control de mercancía y recetas</h2>
          <p style={subtitleStyle}>Gestiona entradas de inventario, recetas y bebidas desde un mismo espacio.</p>
        </div>
        <button type="button" onClick={onBack} style={backButtonStyle(isMobile)}>
          Volver al inicio
        </button>
      </div>

      {statusMessage ? (
        <div style={{ border: '1px solid rgba(255, 115, 115, 0.28)', borderRadius: 12, padding: '10px 12px', background: 'rgba(255, 82, 82, 0.12)', color: '#ffd3d3' }}>
          {statusMessage}
        </div>
      ) : null}

      <div style={summaryGridStyle(isMobile)}>
        <div style={summaryCardStyle}>
          <div style={summaryLabelStyle}>Insumos</div>
          <div style={summaryValueStyle}>{summary.items}</div>
        </div>
        <div style={summaryCardStyle}>
          <div style={summaryLabelStyle}>Recetas</div>
          <div style={summaryValueStyle}>{summary.recipes}</div>
        </div>
        <div style={summaryCardStyle}>
          <div style={summaryLabelStyle}>Bebidas</div>
          <div style={summaryValueStyle}>{summary.beverages}</div>
        </div>
        <div style={{ ...summaryCardStyle, borderColor: 'rgba(255, 173, 173, 0.28)' }}>
          <div style={summaryLabelStyle}>Stock bajo</div>
          <div style={{ ...summaryValueStyle, color: '#ffb0b0' }}>{summary.lowStock}</div>
        </div>
      </div>

      <div style={tabsWrapStyle}>
        {[
          { key: 'inventario', label: 'Ingreso de mercancía' },
          { key: 'recetas', label: 'Recetas' },
          { key: 'bebidas', label: 'Jugos y licores' },
          { key: 'resumen', label: 'Resumen' },
        ].map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActiveTab(tab.key)}
            style={tabButtonStyle(activeTab === tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'inventario' && (
        <div style={sectionGridStyle(isMobile)}>
          <form onSubmit={handleInventorySubmit} style={cardStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <div style={sectionTitleStyle}>Registrar ingreso de insumos</div>
              <button type="button" onClick={openIngredientReport} style={secondaryButtonStyle}>Ingredientes registrados</button>
            </div>
            <div style={{ display: 'grid', gap: 10 }}>
              <label style={fieldStyle}>
                <span style={labelStyle}>Nombre</span>
                <input value={inventoryForm.nombre} onChange={(event) => setInventoryForm((current) => ({ ...current, nombre: event.target.value }))} placeholder="Tomate, cebolla, pollo..." style={inputStyle} />
              </label>
              <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
                <label style={fieldStyle}>
                  <span style={labelStyle}>Categoría</span>
                  <select value={inventoryForm.categoria} onChange={(event) => setInventoryForm((current) => ({ ...current, categoria: event.target.value }))} style={selectStyle}>
                    <option value="Vegetales">Vegetales</option>
                    <option value="Proteínas">Proteínas</option>
                    <option value="Frutas">Frutas</option>
                    <option value="Lácteos">Lácteos</option>
                    <option value="Bebidas">Bebidas</option>
                    <option value="Otros">Otros</option>
                  </select>
                </label>
                <label style={fieldStyle}>
                  <span style={labelStyle}>Cantidad</span>
                  <input type="number" min="0" value={inventoryForm.cantidad} onChange={(event) => setInventoryForm((current) => ({ ...current, cantidad: event.target.value }))} placeholder="0" style={inputStyle} />
                </label>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
                <label style={fieldStyle}>
                  <span style={labelStyle}>Unidad</span>
                  <input value={inventoryForm.unidad} onChange={(event) => setInventoryForm((current) => ({ ...current, unidad: event.target.value }))} placeholder="kg, unidad, litro" style={inputStyle} />
                </label>
                <label style={fieldStyle}>
                  <span style={labelStyle}>Proveedor</span>
                  <input value={inventoryForm.proveedor} onChange={(event) => setInventoryForm((current) => ({ ...current, proveedor: event.target.value }))} placeholder="Nombre del proveedor" style={inputStyle} />
                </label>
              </div>
              <button type="submit" style={primaryButtonStyle}>Guardar ingreso</button>
            </div>
          </form>

        </div>
      )}

      {activeTab === 'recetas' && (
        <div style={sectionGridStyle(isMobile)}>
          <form onSubmit={handleRecipeSubmit} style={cardStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <div style={sectionTitleStyle}>Agregar nueva receta</div>
              <button type="button" onClick={openRecipeReport} style={secondaryButtonStyle}>Ver recetas</button>
            </div>
            <label style={fieldStyle}>
              <span style={labelStyle}>Nombre de la receta</span>
              <input value={recipeForm.nombre} onChange={(event) => setRecipeForm((current) => ({ ...current, nombre: event.target.value }))} placeholder="Ej. Arepa de perico" style={inputStyle} />
            </label>
            <label style={fieldStyle}>
              <span style={labelStyle}>Ingrediente principal</span>
              <input
                value={recipeForm.ingredientes}
                onChange={(event) => setRecipeForm((current) => ({ ...current, ingredientes: event.target.value }))}
                placeholder="Escribe tomate, cebolla, pollo..."
                style={inputStyle}
                autoComplete="off"
              />
            </label>
            <button type="submit" style={primaryButtonStyle}>Guardar receta</button>
          </form>
        </div>
      )}

      {activeTab === 'bebidas' && (
        <div style={sectionGridStyle(isMobile)}>
          <form onSubmit={handleBeverageSubmit} style={cardStyle}>
            <div style={sectionTitleStyle}>Registrar jugos o licores</div>
            <label style={fieldStyle}>
              <span style={labelStyle}>Nombre</span>
              <input value={beverageForm.nombre} onChange={(event) => setBeverageForm((current) => ({ ...current, nombre: event.target.value }))} placeholder="Jugo de guayaba, Cuba libre..." style={inputStyle} />
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
              <label style={fieldStyle}>
                <span style={labelStyle}>Categoría</span>
                <select value={beverageForm.categoria} onChange={(event) => setBeverageForm((current) => ({ ...current, categoria: event.target.value }))} style={selectStyle}>
                  <option value="Jugos">Jugos</option>
                  <option value="Licores">Licores</option>
                  <option value="Bebidas">Bebidas</option>
                </select>
              </label>
              <label style={fieldStyle}>
                <span style={labelStyle}>Precio</span>
                <input type="number" min="0" step="0.1" value={beverageForm.precio} onChange={(event) => setBeverageForm((current) => ({ ...current, precio: event.target.value }))} placeholder="0" style={inputStyle} />
              </label>
            </div>
            <button type="submit" style={primaryButtonStyle}>Guardar bebida</button>
          </form>
        </div>
      )}

      {activeTab === 'resumen' && (
        <div style={cardStyle}>
          <div style={sectionTitleStyle}>Resumen rápido</div>
          <div style={{ display: 'grid', gap: 10, color: '#e8d5d5' }}>
            <div style={listItemStyle}>
              <span>Insumos cargados hoy</span>
              <strong>{summary.items}</strong>
            </div>
            <div style={listItemStyle}>
              <span>Recetas disponibles</span>
              <strong>{summary.recipes}</strong>
            </div>
            <div style={listItemStyle}>
              <span>Opciones de bebidas</span>
              <strong>{summary.beverages}</strong>
            </div>
            <div style={listItemStyle}>
              <span>Productos con stock bajo</span>
              <strong>{summary.lowStock}</strong>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

const panelContainerStyle = (isMobile) => ({
  background: 'linear-gradient(180deg, rgba(18, 8, 8, 0.96) 0%, rgba(8, 8, 8, 0.98) 100%)',
  border: '1px solid rgba(255, 95, 95, 0.18)',
  borderRadius: 24,
  padding: isMobile ? 14 : 20,
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.05), 0 14px 30px rgba(0,0,0,0.32)',
  display: 'grid',
  gap: 14,
  width: '100%',
  boxSizing: 'border-box',
});

const headerWrapStyle = (isMobile) => ({
  display: 'flex',
  alignItems: 'flex-start',
  justifyContent: 'space-between',
  gap: 12,
  flexWrap: 'wrap',
  flexDirection: isMobile ? 'column' : 'row',
});

const eyebrowStyle = {
  color: '#f7a5a5',
  fontSize: 12,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
};

const titleStyle = (isMobile) => ({
  margin: '8px 0 0',
  color: '#fff',
  fontSize: isMobile ? 24 : 30,
  lineHeight: 1.15,
});

const subtitleStyle = {
  margin: '8px 0 0',
  color: '#c6c6c6',
  fontSize: 14,
};

const backButtonStyle = (isMobile) => ({
  border: '1px solid rgba(255, 115, 115, 0.34)',
  borderRadius: 999,
  padding: isMobile ? '10px 14px' : '9px 14px',
  background: 'rgba(255,255,255,0.03)',
  color: '#fff',
  fontWeight: 600,
  cursor: 'pointer',
  minHeight: isMobile ? 42 : 38,
});

const summaryGridStyle = (isMobile) => ({
  display: 'grid',
  gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, minmax(0, 1fr))',
  gap: 10,
});

const summaryCardStyle = {
  border: '1px solid rgba(255,255,255,0.12)',
  borderRadius: 16,
  background: 'rgba(255,255,255,0.04)',
  padding: 14,
};

const summaryLabelStyle = {
  color: '#f1b8b8',
  fontSize: 12,
  textTransform: 'uppercase',
  letterSpacing: '0.1em',
};

const summaryValueStyle = {
  color: '#fff',
  fontWeight: 800,
  fontSize: 24,
  marginTop: 8,
};

const tabsWrapStyle = {
  display: 'flex',
  gap: 8,
  overflowX: 'auto',
  paddingBottom: 2,
  WebkitOverflowScrolling: 'touch',
};

const tabButtonStyle = (active) => ({
  border: active ? '1px solid rgba(255, 109, 109, 0.62)' : '1px solid rgba(255,255,255,0.16)',
  borderRadius: 999,
  padding: '10px 14px',
  background: active ? 'rgba(191, 31, 31, 0.24)' : 'rgba(255,255,255,0.04)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
  whiteSpace: 'nowrap',
  flexShrink: 0,
});

const sectionGridStyle = (isMobile) => ({
  display: 'grid',
  gap: 14,
  gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 1fr))',
  alignItems: 'start',
});

const cardStyle = {
  border: '1px solid rgba(255,255,255,0.12)',
  borderRadius: 18,
  background: 'rgba(255,255,255,0.04)',
  padding: 16,
  display: 'grid',
  gap: 12,
  width: '100%',
  boxSizing: 'border-box',
};

const sectionTitleStyle = {
  color: '#fff',
  fontSize: 17,
  fontWeight: 700,
};

const fieldStyle = {
  display: 'grid',
  gap: 6,
};

const labelStyle = {
  color: '#f0b8b8',
  fontSize: 13,
  fontWeight: 700,
};

const inputStyle = {
  border: '1px solid rgba(255,255,255,0.14)',
  borderRadius: 12,
  padding: '10px 12px',
  background: 'rgba(14, 14, 14, 0.9)',
  color: '#fff',
  fontSize: 14,
  width: '100%',
  boxSizing: 'border-box',
  appearance: 'auto',
  colorScheme: 'dark',
};

const selectStyle = {
  ...inputStyle,
  backgroundColor: '#141414',
  color: '#fff',
  cursor: 'pointer',
  colorScheme: 'dark',
};

const primaryButtonStyle = {
  border: 'none',
  borderRadius: 999,
  padding: '10px 14px',
  background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
  width: '100%',
};

const secondaryButtonStyle = {
  border: '1px solid rgba(255,255,255,0.16)',
  borderRadius: 999,
  padding: '8px 12px',
  background: 'rgba(255,255,255,0.06)',
  color: '#fff',
  fontWeight: 600,
  cursor: 'pointer',
  flexShrink: 0,
};

const iconButtonStyle = {
  border: 'none',
  borderRadius: 999,
  width: 34,
  height: 34,
  background: 'rgba(255,255,255,0.08)',
  color: '#fff',
  cursor: 'pointer',
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
};

const iconButtonDangerStyle = {
  border: 'none',
  borderRadius: 999,
  width: 34,
  height: 34,
  background: 'rgba(255, 82, 82, 0.2)',
  color: '#ffd0d0',
  cursor: 'pointer',
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
};

const listItemStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 10,
  borderRadius: 12,
  padding: '10px 12px',
  background: 'rgba(255,255,255,0.04)',
  border: '1px solid rgba(255,255,255,0.08)',
  flexWrap: 'wrap',
};

export default AdminPanelPage;

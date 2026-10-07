import { useCallback, useEffect, useMemo, useState } from 'react';
import Toast from './Toast';
import UnsavedChangesModal from './UnsavedChangesModal';
import useToast from '../hooks/useToast';
import useUnsavedChangesGuard from '../hooks/useUnsavedChangesGuard';

function todayIso() {
  const now = new Date();
  const offset = now.getTimezoneOffset();
  const local = new Date(now.getTime() - offset * 60000);
  return local.toISOString().slice(0, 10);
}

const emptyForm = {
  categoria_id: '',
  descripcion: '',
  monto: '',
  monto_bs: '',
  fecha_gasto: todayIso(),
  proveedor_nombre: '',
  numero_comprobante: '',
  pagado: true,
  metodo_pago_id: '',
};

function AnalystGastosPage({ isMobile, onBack, onVerComprobante, onVerReporte }) {
  const [categorias, setCategorias] = useState([]);
  const [metodosPago, setMetodosPago] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const { toast, showSuccess, showError, hideToast } = useToast();
  const { guard, isConfirmOpen, confirmLeave, cancelLeave, markClean } = useUnsavedChangesGuard(form);

  const [showCategorias, setShowCategorias] = useState(false);
  const [nuevaCategoria, setNuevaCategoria] = useState('');
  const [savingCategoria, setSavingCategoria] = useState(false);

  const loadCategorias = useCallback(async () => {
    try {
      const response = await fetch('/api/admin/categorias-gasto/', { credentials: 'include', cache: 'no-store' });
      const data = await response.json();
      if (response.ok && data.ok) {
        setCategorias(Array.isArray(data.categorias) ? data.categorias : []);
      }
    } catch (error) {
      // La lista de categorias queda vacia si falla.
    }
  }, []);

  const loadMetodosPago = useCallback(async () => {
    try {
      const response = await fetch('/api/metodos-pago/', { credentials: 'include', cache: 'no-store' });
      const data = await response.json();
      if (response.ok && data.ok) {
        setMetodosPago(Array.isArray(data.metodos_pago) ? data.metodos_pago : []);
      }
    } catch (error) {
      // El selector queda vacio si falla.
    }
  }, []);

  useEffect(() => { loadCategorias(); loadMetodosPago(); }, [loadCategorias, loadMetodosPago]);

  const categoriasActivas = useMemo(() => categorias.filter((c) => c.activo), [categorias]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!form.categoria_id) {
      showError('Elige una categoria.'); return;
    }
    if (!form.descripcion.trim()) {
      showError('Escribe una descripcion del gasto.'); return;
    }
    const tieneMonto = form.monto !== '' && form.monto !== null;
    const tieneMontoBs = form.monto_bs !== '' && form.monto_bs !== null;
    if (tieneMonto && tieneMontoBs) {
      showError('Ingresa el monto solo en dólares o solo en bolívares, no en los dos.'); return;
    }
    if (!tieneMonto && !tieneMontoBs) {
      showError('Indica el monto del gasto.'); return;
    }
    if (tieneMonto && Number(form.monto) <= 0) {
      showError('Indica un monto valido.'); return;
    }
    if (tieneMontoBs && Number(form.monto_bs) <= 0) {
      showError('Indica un monto en bolívares válido.'); return;
    }
    const metodoPagoId = form.metodo_pago_id || (metodosPago[0] && metodosPago[0].id);
    if (form.pagado && !metodoPagoId) {
      showError('No hay metodos de pago activos configurados.'); return;
    }

    setSaving(true);
    try {
      const response = await fetch('/api/admin/gastos/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          categoria_id: form.categoria_id,
          descripcion: form.descripcion,
          monto: tieneMonto ? form.monto : undefined,
          monto_bs: tieneMontoBs ? form.monto_bs : undefined,
          fecha_gasto: form.fecha_gasto,
          proveedor_nombre: form.proveedor_nombre,
          numero_comprobante: form.numero_comprobante,
          pagado_de_una_vez: form.pagado,
          metodo_pago_id: form.pagado ? metodoPagoId : undefined,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo registrar el gasto.');
      }
      const comprobante = form.pagado && Array.isArray(data.gasto.abonos) && data.gasto.abonos.length > 0
        ? { gastoId: data.gasto.id, abonoId: data.gasto.abonos[0].id }
        : null;
      showSuccess(
        form.pagado ? 'Gasto registrado y pagado.' : 'Gasto registrado como pendiente.',
        comprobante && onVerComprobante ? {
          action: {
            label: 'Ver comprobante de pago',
            onClick: () => onVerComprobante('gasto', comprobante.gastoId, comprobante.abonoId),
          },
        } : undefined,
      );
      markClean({ ...emptyForm, fecha_gasto: form.fecha_gasto });
      setForm({ ...emptyForm, fecha_gasto: form.fecha_gasto });
    } catch (error) {
      showError(error.message || 'No se pudo registrar el gasto.');
    } finally {
      setSaving(false);
    }
  };

  const handleAgregarCategoria = async (event) => {
    event.preventDefault();
    if (!nuevaCategoria.trim()) return;
    setSavingCategoria(true);
    try {
      const response = await fetch('/api/admin/categorias-gasto/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'create', nombre: nuevaCategoria }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo crear la categoria.');
      }
      setNuevaCategoria('');
      loadCategorias();
    } catch (error) {
      showError(error.message || 'No se pudo crear la categoria.');
    } finally {
      setSavingCategoria(false);
    }
  };

  const handleToggleCategoria = async (categoria) => {
    try {
      const response = await fetch('/api/admin/categorias-gasto/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'toggle', id: categoria.id }),
      });
      const data = await response.json();
      if (response.ok && data.ok) {
        loadCategorias();
      }
    } catch (error) {
      // Sin feedback especifico, la lista simplemente no cambia.
    }
  };

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={() => guard(onBack)} style={backButtonStyle}>
        ← Volver a Contabilidad
      </button>

      <div style={headerRowStyle}>
        <h2 style={titleStyle(isMobile)}>Gastos operativos</h2>
        {onVerReporte ? (
          <button type="button" onClick={() => guard(onVerReporte)} style={primaryButtonStyle}>
            Ver reporte de gastos
          </button>
        ) : null}
      </div>

      <Toast toast={toast} onClose={hideToast} />
      <UnsavedChangesModal open={isConfirmOpen} onConfirm={confirmLeave} onCancel={cancelLeave} />

      <section style={panelStyle}>
        <div style={sectionTitleStyle}>Registrar gasto</div>
        <form onSubmit={handleSubmit} style={formGridStyle(isMobile)}>
          <label style={fieldStyle}>
            <span style={labelStyle}>Categoría</span>
            <select value={form.categoria_id} onChange={(e) => setForm((c) => ({ ...c, categoria_id: e.target.value }))} style={inputStyle} className="admin-dark-select">
              <option value="">Selecciona...</option>
              {categoriasActivas.map((cat) => (
                <option key={cat.id} value={cat.id}>{cat.nombre}</option>
              ))}
            </select>
          </label>

          <label style={{ ...fieldStyle, gridColumn: isMobile ? 'auto' : 'span 2' }}>
            <span style={labelStyle}>Descripción</span>
            <input value={form.descripcion} onChange={(e) => setForm((c) => ({ ...c, descripcion: e.target.value }))} style={inputStyle} placeholder="Ej: Factura de luz de agosto" />
          </label>

          <label style={fieldStyle}>
            <span style={labelStyle}>Monto ($)</span>
            <input
              type="number" min="0" step="0.01" value={form.monto}
              onChange={(e) => setForm((c) => ({ ...c, monto: e.target.value, monto_bs: e.target.value ? '' : c.monto_bs }))}
              style={inputStyle}
              placeholder="Deja vacío si lo vas a cargar en Bs"
            />
          </label>

          <label style={fieldStyle}>
            <span style={labelStyle}>Monto (Bs)</span>
            <input
              type="number" min="0" step="0.01" value={form.monto_bs}
              onChange={(e) => setForm((c) => ({ ...c, monto_bs: e.target.value, monto: e.target.value ? '' : c.monto }))}
              style={inputStyle}
              placeholder="Se convierte a $ con la tasa BCV de hoy"
            />
          </label>

          <label style={fieldStyle}>
            <span style={labelStyle}>Fecha del gasto</span>
            <input type="date" value={form.fecha_gasto} onChange={(e) => setForm((c) => ({ ...c, fecha_gasto: e.target.value }))} style={inputStyle} />
          </label>

          <label style={fieldStyle}>
            <span style={labelStyle}>Proveedor (opcional)</span>
            <input value={form.proveedor_nombre} onChange={(e) => setForm((c) => ({ ...c, proveedor_nombre: e.target.value }))} style={inputStyle} />
          </label>

          <label style={fieldStyle}>
            <span style={labelStyle}>N° de comprobante (opcional)</span>
            <input value={form.numero_comprobante} onChange={(e) => setForm((c) => ({ ...c, numero_comprobante: e.target.value }))} style={inputStyle} />
          </label>

          <div style={{ ...fieldStyle, gridColumn: isMobile ? 'auto' : 'span 2' }}>
            <span style={labelStyle}>Pago</span>
            <div style={toggleRowStyle}>
              <button type="button" onClick={() => setForm((c) => ({ ...c, pagado: true }))} style={toggleButtonStyle(form.pagado)}>Ya lo pagué</button>
              <button type="button" onClick={() => setForm((c) => ({ ...c, pagado: false }))} style={toggleButtonStyle(!form.pagado)}>Queda pendiente</button>
              {form.pagado ? (
                <select value={form.metodo_pago_id || (metodosPago[0] && metodosPago[0].id) || ''} onChange={(e) => setForm((c) => ({ ...c, metodo_pago_id: e.target.value }))} style={{ ...inputStyle, width: 'auto', flex: 1, minWidth: 140 }} className="admin-dark-select">
                  {metodosPago.map((m) => (
                    <option key={m.id} value={m.id}>{m.nombre}</option>
                  ))}
                </select>
              ) : null}
            </div>
          </div>

          <button type="submit" style={primaryButtonStyle} disabled={saving}>
            {saving ? 'Guardando...' : 'Registrar gasto'}
          </button>
        </form>
      </section>

      <section style={panelStyle}>
        <button type="button" onClick={() => setShowCategorias((c) => !c)} style={collapseButtonStyle}>
          {showCategorias ? '▾' : '▸'} Categorías de gasto ({categorias.length})
        </button>
        {showCategorias ? (
          <div style={{ display: 'grid', gap: 10 }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {categorias.map((cat) => (
                <button key={cat.id} type="button" onClick={() => handleToggleCategoria(cat)} style={categoriaChipStyle(cat.activo)}>
                  {cat.nombre} {cat.activo ? '' : '(inactiva)'}
                </button>
              ))}
            </div>
            <form onSubmit={handleAgregarCategoria} style={{ display: 'flex', gap: 8 }}>
              <input value={nuevaCategoria} onChange={(e) => setNuevaCategoria(e.target.value)} style={{ ...inputStyle, flex: 1 }} placeholder="Nueva categoría (ej: Publicidad)" />
              <button type="submit" style={secondaryButtonStyle} disabled={savingCategoria}>Agregar</button>
            </form>
          </div>
        ) : null}
      </section>
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 26 : 32 });
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const sectionTitleStyle = { color: '#fff', fontSize: 17, fontWeight: 700 };
const formGridStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(3, minmax(0, 1fr))', gap: 12, alignItems: 'end' });
const fieldStyle = { display: 'grid', gap: 6 };
const labelStyle = { color: '#f0b4b4', fontSize: 12.5, fontWeight: 700 };
const inputStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 10, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '9px 10px', color: '#fff', fontSize: 13 };
const toggleRowStyle = { display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' };
const toggleButtonStyle = (active) => ({
  border: active ? '1px solid rgba(80, 200, 130, 0.5)' : '1px solid rgba(255,255,255,0.14)',
  borderRadius: 999, padding: '9px 14px', background: active ? 'rgba(70, 200, 120, 0.16)' : 'rgba(255,255,255,0.04)',
  color: active ? '#9fe3b0' : '#fff', fontWeight: 700, cursor: 'pointer', fontSize: 13,
});

const collapseButtonStyle = { border: 'none', background: 'transparent', color: '#f0b4b4', fontWeight: 700, fontSize: 14, cursor: 'pointer', textAlign: 'left', padding: 0 };
const categoriaChipStyle = (activo) => ({
  border: activo ? '1px solid rgba(255,255,255,0.14)' : '1px solid rgba(255,145,145,0.3)',
  borderRadius: 999, padding: '6px 12px', background: activo ? 'rgba(255,255,255,0.04)' : 'rgba(255,98,98,0.1)',
  color: activo ? '#fff' : '#ffb0b0', fontSize: 12.5, cursor: 'pointer',
});
const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const secondaryButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '8px 14px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: 12 };
const headerRowStyle = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' };

export default AnalystGastosPage;

import { useCallback, useEffect, useMemo, useState } from 'react';
import Toast from './Toast';
import UnsavedChangesModal from './UnsavedChangesModal';
import useExchangeRate from '../hooks/useExchangeRate';
import useToast from '../hooks/useToast';
import useUnsavedChangesGuard from '../hooks/useUnsavedChangesGuard';
import { formatBs, formatBsRaw } from '../utils/currency';

function formatUsdBs(amount, tasa) {
  const usd = `$${Number(amount).toFixed(2)}`;
  const bs = formatBs(amount, tasa);
  return bs ? `${usd} (${bs})` : usd;
}

// A diferencia de formatUsdBs (una tasa para un monto), este toma un monto en USD
// ya sumado (p. ej. el total del período que devuelve el backend) junto con el Bs.
// ya acumulado registro por registro (ver bsTotalGeneral/bsTotalesPorCategoria) —
// evita el drift de convertir la suma global en USD con la tasa en vivo.
function formatUsdBsPrecomputed(usdAmount, bsAmount) {
  const usd = `$${Number(usdAmount).toFixed(2)}`;
  const bs = Number.isFinite(bsAmount) && bsAmount > 0 ? formatBsRaw(bsAmount) : '';
  return bs ? `${usd} (${bs})` : usd;
}

// Bs. de un solo gasto/abono, priorizando su propia tasa congelada al momento de
// registrarlo sobre la tasa en vivo — así reimprimir/reconsultar un registro viejo
// no cambia su equivalente en bolívares con el paso del tiempo.
function tasaDeRegistro(registro, tasaEnVivo) {
  return registro?.tasa_cambio_referencia ?? tasaEnVivo;
}

function todayIso() {
  const now = new Date();
  const offset = now.getTimezoneOffset();
  const local = new Date(now.getTime() - offset * 60000);
  return local.toISOString().slice(0, 10);
}

function firstDayOfMonthIso() {
  const today = todayIso();
  return `${today.slice(0, 7)}-01`;
}

const emptyForm = {
  categoria_id: '',
  descripcion: '',
  monto: '',
  fecha_gasto: todayIso(),
  proveedor_nombre: '',
  numero_comprobante: '',
  pagado: true,
  metodo_pago_id: '',
};

const ESTADO_LABELS = {
  pendiente: { label: 'Pendiente', color: '#ff9b9b', background: 'rgba(255, 145, 145, 0.16)' },
  abonada_parcial: { label: 'Abonado', color: '#ffcf7d', background: 'rgba(255, 200, 120, 0.16)' },
  pagado: { label: 'Pagado', color: '#9fe3b0', background: 'rgba(80, 200, 130, 0.18)' },
};

function AnalystGastosPage({ isMobile, onBack, onVerComprobante }) {
  const tasaCambio = useExchangeRate();
  const [categorias, setCategorias] = useState([]);
  const [metodosPago, setMetodosPago] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const { toast, showSuccess, showError, hideToast } = useToast();
  const { guard, isConfirmOpen, confirmLeave, cancelLeave, markClean } = useUnsavedChangesGuard(form);

  const [fechaDesde, setFechaDesde] = useState(firstDayOfMonthIso());
  const [fechaHasta, setFechaHasta] = useState(todayIso());
  const [filtroCategoriaId, setFiltroCategoriaId] = useState('');
  const [filtroEstado, setFiltroEstado] = useState('');
  const [gastos, setGastos] = useState([]);
  const [totalesPorCategoria, setTotalesPorCategoria] = useState([]);
  const [totalGeneral, setTotalGeneral] = useState('0');
  const [loadingGastos, setLoadingGastos] = useState(true);

  const [abonandoId, setAbonandoId] = useState(null);
  const [montoAbono, setMontoAbono] = useState('');
  const [metodoAbono, setMetodoAbono] = useState('');
  const [savingAbono, setSavingAbono] = useState(false);

  const [showCategorias, setShowCategorias] = useState(false);
  const [nuevaCategoria, setNuevaCategoria] = useState('');
  const [savingCategoria, setSavingCategoria] = useState(false);

  const [verAbonosId, setVerAbonosId] = useState(null);
  const [abonosDetalle, setAbonosDetalle] = useState([]);
  const [loadingAbonosDetalle, setLoadingAbonosDetalle] = useState(false);

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

  const loadGastos = useCallback(async () => {
    setLoadingGastos(true);
    try {
      const params = new URLSearchParams({ fecha_desde: fechaDesde, fecha_hasta: fechaHasta });
      if (filtroCategoriaId) params.set('categoria_id', filtroCategoriaId);
      if (filtroEstado) params.set('estado_pago', filtroEstado);
      const response = await fetch(`/api/admin/gastos/?${params.toString()}`, { credentials: 'include', cache: 'no-store' });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudieron cargar los gastos.');
      }
      setGastos(Array.isArray(data.gastos) ? data.gastos : []);
      setTotalesPorCategoria(Array.isArray(data.totales_por_categoria) ? data.totales_por_categoria : []);
      setTotalGeneral(data.total_general || '0');
    } catch (error) {
      showError(error.message || 'No se pudieron cargar los gastos.');
    } finally {
      setLoadingGastos(false);
    }
  }, [fechaDesde, fechaHasta, filtroCategoriaId, filtroEstado]);

  useEffect(() => { loadCategorias(); loadMetodosPago(); }, [loadCategorias, loadMetodosPago]);
  useEffect(() => { loadGastos(); }, [loadGastos]);

  const categoriasActivas = useMemo(() => categorias.filter((c) => c.activo), [categorias]);

  // Bs. del período: cada gasto se convierte con SU PROPIA tasa (congelada al
  // registrarlo, con fallback a la tasa en vivo si aún no tiene una), y luego se
  // suman los bolívares ya convertidos — en vez de sumar los montos en USD y
  // convertir esa suma con la tasa de hoy (lo que hacía que el total de un período
  // cerrado cambiara con el tiempo aunque los gastos no cambiaran).
  const bsTotalesPorCategoria = useMemo(() => {
    const totales = new Map();
    gastos.forEach((gasto) => {
      const tasa = Number(tasaDeRegistro(gasto, tasaCambio));
      if (!Number.isFinite(tasa) || tasa <= 0) return;
      const bs = Number(gasto.monto) * tasa;
      totales.set(gasto.categoria_id, (totales.get(gasto.categoria_id) || 0) + bs);
    });
    return totales;
  }, [gastos, tasaCambio]);

  const bsTotalGeneral = useMemo(() => (
    gastos.reduce((suma, gasto) => {
      const tasa = Number(tasaDeRegistro(gasto, tasaCambio));
      if (!Number.isFinite(tasa) || tasa <= 0) return suma;
      return suma + Number(gasto.monto) * tasa;
    }, 0)
  ), [gastos, tasaCambio]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!form.categoria_id) {
      showError('Elige una categoria.'); return;
    }
    if (!form.descripcion.trim()) {
      showError('Escribe una descripcion del gasto.'); return;
    }
    if (!form.monto || Number(form.monto) <= 0) {
      showError('Indica un monto valido.'); return;
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
          monto: form.monto,
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
      loadGastos();
    } catch (error) {
      showError(error.message || 'No se pudo registrar el gasto.');
    } finally {
      setSaving(false);
    }
  };

  const handleAbrirAbono = (gasto) => {
    setAbonandoId(gasto.id === abonandoId ? null : gasto.id);
    setMontoAbono('');
    setMetodoAbono('');
  };

  const handleRegistrarAbono = async (event, gastoId) => {
    event.preventDefault();
    const metodoPagoId = metodoAbono || (metodosPago[0] && metodosPago[0].id);
    if (!metodoPagoId) {
      showError('No hay metodos de pago activos configurados.'); return;
    }
    setSavingAbono(true);
    try {
      const response = await fetch(`/api/admin/gastos/${gastoId}/abonos/`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ monto: montoAbono, metodo_pago_id: metodoPagoId }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo registrar el abono.');
      }
      showSuccess(
        `Abono de $${data.abono.monto} registrado.`,
        onVerComprobante ? {
          action: {
            label: 'Ver comprobante de pago',
            onClick: () => onVerComprobante('gasto', gastoId, data.abono.id),
          },
        } : undefined,
      );
      setAbonandoId(null);
      loadGastos();
    } catch (error) {
      showError(error.message || 'No se pudo registrar el abono.');
    } finally {
      setSavingAbono(false);
    }
  };

  const handleVerAbonos = async (gasto) => {
    if (verAbonosId === gasto.id) {
      setVerAbonosId(null);
      return;
    }
    setVerAbonosId(gasto.id);
    setLoadingAbonosDetalle(true);
    try {
      const response = await fetch(`/api/admin/gastos/${gasto.id}/`, { credentials: 'include', cache: 'no-store' });
      const data = await response.json();
      if (response.ok && data.ok) {
        setAbonosDetalle(Array.isArray(data.gasto.abonos) ? data.gasto.abonos : []);
      }
    } catch (error) {
      setAbonosDetalle([]);
    } finally {
      setLoadingAbonosDetalle(false);
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

      <div>
        <h2 style={titleStyle(isMobile)}>Gastos operativos</h2>
        <p style={subtitleStyle}>
          Registra alquiler, servicios, nómina y demás gastos del negocio — separado del inventario. Marca si ya
          lo pagaste o si queda pendiente para abonarlo después.
        </p>
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
            <span style={labelStyle}>Monto</span>
            <input type="number" min="0" step="0.01" value={form.monto} onChange={(e) => setForm((c) => ({ ...c, monto: e.target.value }))} style={inputStyle} />
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

      <section style={panelStyle}>
        <div style={sectionTitleStyle}>Reporte de gastos</div>
        <div style={filtrosRowStyle(isMobile)}>
          <label style={fieldStyle}>
            <span style={labelStyle}>Desde</span>
            <input type="date" value={fechaDesde} onChange={(e) => setFechaDesde(e.target.value)} style={inputStyle} />
          </label>
          <label style={fieldStyle}>
            <span style={labelStyle}>Hasta</span>
            <input type="date" value={fechaHasta} onChange={(e) => setFechaHasta(e.target.value)} style={inputStyle} />
          </label>
          <label style={fieldStyle}>
            <span style={labelStyle}>Categoría</span>
            <select value={filtroCategoriaId} onChange={(e) => setFiltroCategoriaId(e.target.value)} style={inputStyle} className="admin-dark-select">
              <option value="">Todas</option>
              {categorias.map((cat) => (
                <option key={cat.id} value={cat.id}>{cat.nombre}</option>
              ))}
            </select>
          </label>
          <label style={fieldStyle}>
            <span style={labelStyle}>Estado</span>
            <select value={filtroEstado} onChange={(e) => setFiltroEstado(e.target.value)} style={inputStyle} className="admin-dark-select">
              <option value="">Todos</option>
              <option value="pendiente">Pendiente</option>
              <option value="abonada_parcial">Abonado parcial</option>
              <option value="pagado">Pagado</option>
            </select>
          </label>
        </div>

        {totalesPorCategoria.length > 0 ? (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {totalesPorCategoria.map((entry) => (
              <span key={entry.categoria_id} style={categoriaTotalChipStyle}>
                {entry.categoria_nombre}: {formatUsdBsPrecomputed(entry.total, bsTotalesPorCategoria.get(entry.categoria_id) || 0)}
              </span>
            ))}
          </div>
        ) : null}
        <div style={{ color: '#ffcf7d', fontWeight: 800 }}>Total del período: {formatUsdBsPrecomputed(totalGeneral, bsTotalGeneral)}</div>

        {loadingGastos ? <div style={emptyStyle}>Cargando gastos...</div> : null}
        {!loadingGastos && gastos.length === 0 ? <div style={emptyStyle}>No hay gastos para ese filtro.</div> : null}

        {!loadingGastos && gastos.length > 0 ? (
          <div style={tableWrapStyle}>
            <div style={tableStyle}>
              <div style={headStyle}>Fecha</div>
              <div style={headStyle}>Categoría</div>
              <div style={headStyle}>Descripción</div>
              <div style={headStyle}>Monto</div>
              <div style={headStyle}>Estado</div>
              <div style={headStyle}></div>

              {gastos.map((gasto) => {
                const badge = ESTADO_LABELS[gasto.estado_pago];
                return (
                  <>
                    <div key={`fecha-${gasto.id}`} style={cellStyle}>{gasto.fecha_gasto}</div>
                    <div key={`cat-${gasto.id}`} style={cellStyle}>{gasto.categoria_nombre}</div>
                    <div key={`desc-${gasto.id}`} style={cellPrimaryStyle}>
                      <div>{gasto.descripcion}</div>
                      {gasto.proveedor_nombre ? <div style={{ fontSize: 11, color: '#a89999' }}>{gasto.proveedor_nombre}</div> : null}
                    </div>
                    <div key={`monto-${gasto.id}`} style={cellStyle}>
                      {formatUsdBs(gasto.monto, tasaDeRegistro(gasto, tasaCambio))}
                      {gasto.estado_pago !== 'pagado' ? (
                        <div style={{ fontSize: 11, color: '#ffcf7d' }}>Saldo: {formatUsdBs(gasto.saldo_pendiente, tasaDeRegistro(gasto, tasaCambio))}</div>
                      ) : null}
                    </div>
                    <div key={`estado-${gasto.id}`} style={cellStyle}>
                      <span style={countBadgeStyle(badge)}>{badge?.label || gasto.estado_pago}</span>
                    </div>
                    <div key={`accion-${gasto.id}`} style={{ ...cellStyle, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      {gasto.estado_pago !== 'pagado' ? (
                        <button type="button" onClick={() => handleAbrirAbono(gasto)} style={secondaryButtonStyle}>
                          {abonandoId === gasto.id ? 'Cerrar' : 'Abonar'}
                        </button>
                      ) : null}
                      {gasto.estado_pago !== 'pendiente' ? (
                        <button type="button" onClick={() => handleVerAbonos(gasto)} style={secondaryButtonStyle}>
                          {verAbonosId === gasto.id ? 'Ocultar' : 'Ver abonos'}
                        </button>
                      ) : null}
                    </div>
                    {abonandoId === gasto.id ? (
                      <div key={`abono-${gasto.id}`} style={{ gridColumn: '1 / -1' }}>
                        <form onSubmit={(e) => handleRegistrarAbono(e, gasto.id)} style={abonoFormStyle(isMobile)}>
                          <input type="number" min="0.01" step="0.01" placeholder="Monto del abono" value={montoAbono} onChange={(e) => setMontoAbono(e.target.value)} style={inputStyle} required />
                          <select value={metodoAbono || (metodosPago[0] && metodosPago[0].id) || ''} onChange={(e) => setMetodoAbono(Number(e.target.value))} style={inputStyle} className="admin-dark-select">
                            {metodosPago.map((m) => (
                              <option key={m.id} value={m.id}>{m.nombre}</option>
                            ))}
                          </select>
                          <button type="submit" style={primaryButtonStyle} disabled={savingAbono}>
                            {savingAbono ? 'Registrando...' : 'Registrar abono'}
                          </button>
                        </form>
                      </div>
                    ) : null}
                    {verAbonosId === gasto.id ? (
                      <div key={`abonos-list-${gasto.id}`} style={{ gridColumn: '1 / -1', display: 'grid', gap: 6, padding: '6px 0' }}>
                        {loadingAbonosDetalle ? <div style={{ fontSize: 12, color: '#c8bbbb' }}>Cargando abonos...</div> : null}
                        {!loadingAbonosDetalle && abonosDetalle.map((abono) => (
                          <div key={abono.id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5, color: '#e8dede' }}>
                            <span>{abono.metodo_pago} — {new Date(abono.fecha_pago).toLocaleString('es-VE')}</span>
                            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              {formatUsdBs(abono.monto, tasaDeRegistro(abono, tasaCambio))}
                              {onVerComprobante ? (
                                <button type="button" onClick={() => onVerComprobante('gasto', gasto.id, abono.id)} style={miniPrintButtonStyle} title="Ver comprobante">🖨</button>
                              ) : null}
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </>
                );
              })}
            </div>
          </div>
        ) : null}
      </section>
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 26 : 32 });
const subtitleStyle = { margin: '8px 0 0', color: '#d2c3c3', lineHeight: 1.6, maxWidth: 760 };
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

const filtrosRowStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4, minmax(0,1fr))', gap: 10 });

const categoriaTotalChipStyle = { display: 'inline-flex', padding: '5px 12px', borderRadius: 999, fontSize: 12, fontWeight: 700, color: '#c8bbbb', background: 'rgba(255,255,255,0.06)' };

const emptyStyle = { minHeight: 60, display: 'grid', placeItems: 'center', borderRadius: 14, border: '1px dashed rgba(255,255,255,0.12)', color: '#c8bbbb' };
const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: '100px 140px minmax(180px,1.4fr) minmax(140px,1fr) 110px 170px', gap: '10px 12px', alignItems: 'center', minWidth: 900 };
const headStyle = { color: '#f0b4b4', fontSize: 11.5, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em', padding: '4px 2px', borderBottom: '1px solid rgba(255,255,255,0.1)' };
const cellStyle = { color: '#fff', fontSize: 13, padding: '6px 2px', borderBottom: '1px solid rgba(255,255,255,0.06)' };
const cellPrimaryStyle = { ...cellStyle, fontWeight: 700 };
const countBadgeStyle = (badge) => ({
  display: 'inline-flex', alignItems: 'center', padding: '3px 10px', borderRadius: 999,
  fontSize: 11, fontWeight: 800, letterSpacing: '0.02em', textTransform: 'uppercase',
  color: badge ? badge.color : '#fff', background: badge ? badge.background : 'rgba(255,255,255,0.08)',
});
const abonoFormStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr auto', gap: 8, padding: '10px 0' });

const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const secondaryButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '8px 14px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: 12 };

const miniPrintButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 8, padding: '2px 6px', background: 'rgba(255,255,255,0.04)', cursor: 'pointer', fontSize: 12, lineHeight: 1 };

export default AnalystGastosPage;

import { useMemo, useRef, useState } from 'react';

const ACCION_LABELS = {
  nuevo: { label: 'Nuevo', color: '#8ff0b8', background: 'rgba(80, 200, 130, 0.18)' },
  actualizar: { label: 'Actualizar', color: '#ffcf8a', background: 'rgba(255, 176, 59, 0.18)' },
  sin_cambios: { label: 'Sin cambios', color: '#c8bbbb', background: 'rgba(255, 255, 255, 0.08)' },
  ignorado: { label: 'Ignorado', color: '#c8bbbb', background: 'rgba(255, 255, 255, 0.06)' },
  error: { label: 'Error', color: '#ffb0b0', background: 'rgba(220, 38, 38, 0.2)' },
};

const SELECTABLE_ACCIONES = new Set(['nuevo', 'actualizar']);

const emptyLote = { proveedor_nombre: '', numero_factura_proveedor: '', fecha_factura: '' };

function AnalystIngredientsImportPage({ isMobile, onBack }) {
  const fileInputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [rows, setRows] = useState(null);
  const [lote, setLote] = useState(emptyLote);
  const [previewing, setPreviewing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState('success');
  const [summary, setSummary] = useState(null);

  const counts = useMemo(() => {
    if (!rows) {
      return null;
    }
    return rows.reduce((acc, row) => {
      acc[row.accion] = (acc[row.accion] || 0) + 1;
      return acc;
    }, {});
  }, [rows]);

  const selectedCount = useMemo(
    () => (rows || []).filter((row) => row.selected).length,
    [rows],
  );

  const handleFileChange = (event) => {
    const selected = event.target.files && event.target.files[0] ? event.target.files[0] : null;
    setFile(selected);
    setRows(null);
    setSummary(null);
    setMessage('');
  };

  const handlePreview = async () => {
    if (!file) {
      setMessageType('error');
      setMessage('Selecciona primero un archivo .xlsx.');
      return;
    }

    setPreviewing(true);
    setMessage('');
    try {
      const formData = new FormData();
      formData.append('action', 'preview');
      formData.append('archivo', file);

      const response = await fetch('/api/admin/catalogo/importar/', {
        method: 'POST',
        credentials: 'include',
        body: formData,
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo leer el archivo.');
      }

      setRows((data.filas || []).map((row) => ({
        ...row,
        precio_total: row.precio_total || '',
        selected: SELECTABLE_ACCIONES.has(row.accion),
      })));
      setSummary(null);
    } catch (error) {
      setMessageType('error');
      setMessage(error.message || 'No se pudo leer el archivo.');
    } finally {
      setPreviewing(false);
    }
  };

  const updateRow = (fila, changes) => {
    setRows((current) => current.map((row) => (row.fila === fila ? { ...row, ...changes } : row)));
  };

  const handleConfirm = async () => {
    const items = (rows || [])
      .filter((row) => row.selected)
      .map((row) => ({
        nombre: row.nombre, unidad: row.unidad, cantidad: row.cantidad, precio_total: row.precio_total,
      }));

    if (items.length === 0) {
      setMessageType('error');
      setMessage('Marca al menos una fila para importar.');
      return;
    }

    setConfirming(true);
    setMessage('');
    try {
      const response = await fetch('/api/admin/catalogo/importar/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'confirm',
          items,
          proveedor_nombre: lote.proveedor_nombre,
          numero_factura_proveedor: lote.numero_factura_proveedor,
          fecha_factura: lote.fecha_factura,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo completar la importación.');
      }

      setSummary(data);
      setMessageType('success');
      setMessage('Importación completada.');
    } catch (error) {
      setMessageType('error');
      setMessage(error.message || 'No se pudo completar la importación.');
    } finally {
      setConfirming(false);
    }
  };

  const handleReset = () => {
    setFile(null);
    setRows(null);
    setSummary(null);
    setMessage('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>
        ← Volver al reporte
      </button>

      <div>
        <h2 style={titleStyle(isMobile)}>Importar ingredientes desde Excel</h2>
        <p style={subtitleStyle}>
          Sube la ficha de conteo/pesaje, revisa qué se va a crear o actualizar, y confirma. Los ingredientes
          con la cantidad vacía o en 0 se ignoran automáticamente.
        </p>
      </div>

      {message ? <div style={noticeStyle(messageType)}>{message}</div> : null}

      <section style={panelStyle}>
        <div style={sectionTitleStyle}>Datos del lote (de dónde viene esta carga)</div>
        <div style={loteFormStyle(isMobile)}>
          <input
            value={lote.proveedor_nombre}
            onChange={(event) => setLote((current) => ({ ...current, proveedor_nombre: event.target.value }))}
            style={editInputStyle}
            placeholder="Proveedor"
          />
          <input
            value={lote.numero_factura_proveedor}
            onChange={(event) => setLote((current) => ({ ...current, numero_factura_proveedor: event.target.value }))}
            style={editInputStyle}
            placeholder="Número de factura del proveedor"
          />
          <input
            type="date"
            value={lote.fecha_factura}
            onChange={(event) => setLote((current) => ({ ...current, fecha_factura: event.target.value }))}
            style={editInputStyle}
          />
        </div>
        <p style={hintStyle}>
          Estos datos quedan guardados en un único lote de compra para todo el archivo, así después se puede
          rastrear de qué factura vino cada ingrediente cargado.
        </p>

        <div style={uploadRowStyle(isMobile)}>
          <a href="/plantilla_ingredientes.xlsx" download style={templateLinkStyle}>
            ⬇ Descargar plantilla (.xlsx)
          </a>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx"
            onChange={handleFileChange}
            style={fileInputStyle}
          />
          <button type="button" onClick={handlePreview} style={primaryButtonStyle} disabled={!file || previewing}>
            {previewing ? 'Leyendo archivo...' : 'Previsualizar'}
          </button>
          {rows ? (
            <button type="button" onClick={handleReset} style={secondaryButtonStyle}>
              Subir otro archivo
            </button>
          ) : null}
        </div>
        <p style={hintStyle}>
          La plantilla trae las columnas Ingrediente, Unidad (g, ml o unidad) y Cantidad. Puedes usar tus
          propios encabezados siempre que incluyan una columna "Ingrediente". Si además agregas una columna
          "Precio total" (lo pagado por esa cantidad de ese ingrediente), el sistema calcula solo el costo por
          unidad — igual que al registrar un ingreso individual.
        </p>
      </section>

      {rows && rows.length > 0 ? (
        <section style={panelStyle}>
          <div style={summaryRowStyle}>
            <div style={sectionTitleStyle}>Revisión antes de importar</div>
            <div style={countsRowStyle}>
              {Object.entries(counts || {}).map(([accion, count]) => (
                <span key={accion} style={countBadgeStyle(ACCION_LABELS[accion])}>
                  {count} {ACCION_LABELS[accion]?.label || accion}
                </span>
              ))}
            </div>
          </div>

          <div style={tableWrapStyle}>
            <div style={tableStyle}>
              <div style={headStyle}></div>
              <div style={headStyle}>Ingrediente</div>
              <div style={headStyle}>Unidad</div>
              <div style={headStyle}>Cantidad</div>
              <div style={headStyle}>Precio total</div>
              <div style={headStyle}>Estado</div>
              <div style={headStyle}>Detalle</div>

              {rows.map((row) => {
                const badge = ACCION_LABELS[row.accion] || ACCION_LABELS.error;
                const canSelect = SELECTABLE_ACCIONES.has(row.accion);
                return (
                  <>
                    <div key={`sel-${row.fila}`} style={cellStyle}>
                      <input
                        type="checkbox"
                        checked={row.selected}
                        disabled={!canSelect}
                        onChange={(event) => updateRow(row.fila, { selected: event.target.checked })}
                      />
                    </div>
                    <div key={`name-${row.fila}`} style={cellPrimaryStyle}>
                      <div style={{ fontWeight: 700 }}>{row.nombre}</div>
                      <div style={{ fontSize: 11, color: '#a89999' }}>Fila {row.fila}</div>
                    </div>
                    <div key={`unit-${row.fila}`} style={cellStyle}>
                      <input
                        value={row.unidad || ''}
                        onChange={(event) => updateRow(row.fila, { unidad: event.target.value })}
                        style={editInputStyle}
                        placeholder="g, ml, unidad"
                      />
                    </div>
                    <div key={`qty-${row.fila}`} style={cellStyle}>
                      <input
                        value={row.cantidad || ''}
                        onChange={(event) => updateRow(row.fila, { cantidad: event.target.value })}
                        style={editInputStyle}
                      />
                    </div>
                    <div key={`precio-${row.fila}`} style={cellStyle}>
                      <input
                        value={row.precio_total || ''}
                        onChange={(event) => updateRow(row.fila, { precio_total: event.target.value })}
                        style={editInputStyle}
                        placeholder="Opcional"
                      />
                    </div>
                    <div key={`state-${row.fila}`} style={cellStyle}>
                      <span style={countBadgeStyle(badge)}>{badge.label}</span>
                    </div>
                    <div key={`detail-${row.fila}`} style={{ ...cellStyle, fontSize: 12, color: '#c8bbbb' }}>
                      {row.ingrediente_id ? `Stock actual: ${row.stock_actual} ${row.unidad_actual}` : ''}
                      {row.mensaje ? <div>{row.mensaje}</div> : null}
                    </div>
                  </>
                );
              })}
            </div>
          </div>

          <div style={confirmRowStyle(isMobile)}>
            <div style={{ color: '#c8bbbb', fontSize: 13 }}>{selectedCount} fila(s) seleccionada(s) para importar</div>
            <button type="button" onClick={handleConfirm} style={primaryButtonStyle} disabled={confirming || selectedCount === 0}>
              {confirming ? 'Importando...' : 'Confirmar importación'}
            </button>
          </div>
        </section>
      ) : null}

      {summary ? (
        <section style={panelStyle}>
          <div style={sectionTitleStyle}>Resultado de la importación</div>
          <div style={countsRowStyle}>
            <span style={countBadgeStyle(ACCION_LABELS.nuevo)}>{summary.creados} creados</span>
            <span style={countBadgeStyle(ACCION_LABELS.actualizar)}>{summary.actualizados} actualizados</span>
            <span style={countBadgeStyle(ACCION_LABELS.ignorado)}>{summary.ignorados} ignorados</span>
            {summary.errores && summary.errores.length > 0 ? (
              <span style={countBadgeStyle(ACCION_LABELS.error)}>{summary.errores.length} con error</span>
            ) : null}
          </div>
          {summary.errores && summary.errores.length > 0 ? (
            <div style={{ display: 'grid', gap: 4 }}>
              {summary.errores.map((error, index) => (
                <div key={index} style={{ color: '#ffb0b0', fontSize: 13 }}>{error}</div>
              ))}
            </div>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}

const containerStyle = (isMobile) => ({ display: 'grid', gap: 16, padding: isMobile ? 6 : 10 });
const backButtonStyle = { display: 'inline-flex', alignItems: 'center', gap: 6, width: 'fit-content', border: 'none', borderRadius: 999, padding: '11px 18px', background: 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer', boxShadow: '0 8px 20px rgba(37, 99, 235, 0.35)' };
const titleStyle = (isMobile) => ({ margin: 0, color: '#fff', fontSize: isMobile ? 28 : 34 });
const subtitleStyle = { margin: '8px 0 0', color: '#d2c3c3', lineHeight: 1.6, maxWidth: 760 };
const panelStyle = { display: 'grid', gap: 14, padding: 18, borderRadius: 20, border: '1px solid rgba(255,255,255,0.1)', background: 'linear-gradient(180deg, rgba(20,10,10,0.95) 0%, rgba(8,8,8,0.98) 100%)' };
const sectionTitleStyle = { color: '#fff', fontSize: 17, fontWeight: 700 };

const uploadRowStyle = (isMobile) => ({ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10, flexDirection: isMobile ? 'column' : 'row' });
const templateLinkStyle = { color: '#bfe0ff', fontWeight: 700, textDecoration: 'none', border: '1px solid rgba(125, 200, 255, 0.4)', borderRadius: 999, padding: '9px 14px', background: 'rgba(90, 170, 255, 0.08)' };
const fileInputStyle = { color: '#fff', flex: 1, minWidth: 200 };
const hintStyle = { margin: 0, color: '#a89999', fontSize: 12.5 };

const summaryRowStyle = { display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 10 };
const countsRowStyle = { display: 'flex', flexWrap: 'wrap', gap: 8 };
const countBadgeStyle = (badge) => ({
  display: 'inline-flex', alignItems: 'center', padding: '3px 10px', borderRadius: 999,
  fontSize: 11.5, fontWeight: 800, letterSpacing: '0.02em', textTransform: 'uppercase',
  color: badge ? badge.color : '#fff', background: badge ? badge.background : 'rgba(255,255,255,0.08)',
});

const loteFormStyle = (isMobile) => ({ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1.4fr 1.4fr 1fr', gap: 10 });

const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: '34px minmax(160px, 1.4fr) 110px 100px 110px 110px minmax(160px, 1.4fr)', gap: '10px 12px', alignItems: 'center', minWidth: 820 };
const headStyle = { color: '#f0b4b4', fontSize: 11.5, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em', padding: '4px 2px', borderBottom: '1px solid rgba(255,255,255,0.1)' };
const cellStyle = { color: '#fff', fontSize: 13, padding: '6px 2px', borderBottom: '1px solid rgba(255,255,255,0.06)' };
const cellPrimaryStyle = { ...cellStyle };
const editInputStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 8, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '6px 8px', color: '#fff', fontSize: 13 };

const confirmRowStyle = (isMobile) => ({ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10, flexDirection: isMobile ? 'column' : 'row' });

const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const secondaryButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };

const noticeStyle = (type) => ({
  padding: '12px 14px', borderRadius: 16,
  border: type === 'error' ? '1px solid rgba(255, 145, 145, 0.22)' : '1px solid rgba(125, 255, 160, 0.3)',
  background: type === 'error' ? 'rgba(255, 98, 98, 0.12)' : 'rgba(70, 200, 120, 0.1)',
  color: type === 'error' ? '#ffd8d8' : '#bdf0cf',
});

export default AnalystIngredientsImportPage;
import { useMemo, useRef, useState } from 'react';

const ACCION_LABELS = {
  nuevo: { label: 'Nuevo', color: '#8ff0b8', background: 'rgba(80, 200, 130, 0.18)' },
  existente: { label: 'Ya existe', color: '#c8bbbb', background: 'rgba(255, 255, 255, 0.08)' },
  duplicado: { label: 'Repetido en el archivo', color: '#ffcf8a', background: 'rgba(255, 176, 59, 0.18)' },
};

const SELECTABLE_ACCIONES = new Set(['nuevo']);

function AnalystIngredientsBulkCreatePage({ isMobile, onBack }) {
  const fileInputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [rows, setRows] = useState(null);
  const [motivo, setMotivo] = useState('');
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

      const response = await fetch('/api/admin/catalogo/importar-simple/', {
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
    if (!motivo.trim()) {
      setMessageType('error');
      setMessage('Indica el motivo de esta carga (ej: "Inversión inicial - apertura de restaurante").');
      return;
    }

    const items = (rows || [])
      .filter((row) => row.selected)
      .map((row) => ({ nombre: row.nombre }));

    if (items.length === 0) {
      setMessageType('error');
      setMessage('Marca al menos una fila para crear.');
      return;
    }

    setConfirming(true);
    setMessage('');
    try {
      const response = await fetch('/api/admin/catalogo/importar-simple/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'confirm', items, motivo }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo completar la carga.');
      }

      setSummary(data);
      setMessageType('success');
      setMessage('Carga completada.');
    } catch (error) {
      setMessageType('error');
      setMessage(error.message || 'No se pudo completar la carga.');
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
        ← Volver
      </button>

      <div>
        <h2 style={titleStyle(isMobile)}>Cargar ingredientes desde Excel</h2>
        <p style={subtitleStyle}>
          Esta carga solo crea el ingrediente en el catálogo, con nombre únicamente — sin stock, sin costo y sin
          unidad todavía. Úsala para el montaje inicial del inventario antes de abrir el restaurante. Si el
          ingrediente ya existe, no se toca ni se duplica.
        </p>
      </div>

      {message ? <div style={noticeStyle(messageType)}>{message}</div> : null}

      <section style={panelStyle}>
        <div style={sectionTitleStyle}>Motivo de esta carga</div>
        <input
          value={motivo}
          onChange={(event) => setMotivo(event.target.value)}
          style={editInputStyle}
          placeholder='Ej: "Inversión inicial - apertura de restaurante"'
        />
        <p style={hintStyle}>
          Este motivo queda guardado como referencia para toda la carga, ya que no se trata de una compra real.
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
          Solo necesitas una columna "Ingrediente" con los nombres. Puedes usar la misma plantilla y dejar vacías
          las columnas de unidad, cantidad y precio — se ignoran en esta carga.
        </p>
      </section>

      {rows && rows.length > 0 ? (
        <section style={panelStyle}>
          <div style={summaryRowStyle}>
            <div style={sectionTitleStyle}>Revisión antes de crear</div>
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
              <div style={headStyle}>Estado</div>
              <div style={headStyle}>Detalle</div>

              {rows.map((row) => {
                const badge = ACCION_LABELS[row.accion];
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
                    <div key={`state-${row.fila}`} style={cellStyle}>
                      <span style={countBadgeStyle(badge)}>{badge?.label || row.accion}</span>
                    </div>
                    <div key={`detail-${row.fila}`} style={{ ...cellStyle, fontSize: 12, color: '#c8bbbb' }}>
                      {row.mensaje || ''}
                    </div>
                  </>
                );
              })}
            </div>
          </div>

          <div style={confirmRowStyle(isMobile)}>
            <div style={{ color: '#c8bbbb', fontSize: 13 }}>{selectedCount} fila(s) seleccionada(s) para crear</div>
            <button type="button" onClick={handleConfirm} style={primaryButtonStyle} disabled={confirming || selectedCount === 0}>
              {confirming ? 'Creando...' : 'Confirmar carga'}
            </button>
          </div>
        </section>
      ) : null}

      {summary ? (
        <section style={panelStyle}>
          <div style={sectionTitleStyle}>Resultado de la carga</div>
          <div style={countsRowStyle}>
            <span style={countBadgeStyle(ACCION_LABELS.nuevo)}>{summary.creados} creados</span>
            <span style={countBadgeStyle(ACCION_LABELS.existente)}>{summary.omitidos} omitidos (ya existían)</span>
          </div>
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

const tableWrapStyle = { overflowX: 'auto' };
const tableStyle = { display: 'grid', gridTemplateColumns: '34px minmax(200px, 1.4fr) 140px minmax(200px, 1.4fr)', gap: '10px 12px', alignItems: 'center', minWidth: 680 };
const headStyle = { color: '#f0b4b4', fontSize: 11.5, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em', padding: '4px 2px', borderBottom: '1px solid rgba(255,255,255,0.1)' };
const cellStyle = { color: '#fff', fontSize: 13, padding: '6px 2px', borderBottom: '1px solid rgba(255,255,255,0.06)' };
const cellPrimaryStyle = { ...cellStyle };
const editInputStyle = { width: '100%', boxSizing: 'border-box', borderRadius: 8, border: '1px solid rgba(255,255,255,0.14)', background: '#161010', padding: '8px 10px', color: '#fff', fontSize: 13 };

const confirmRowStyle = (isMobile) => ({ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10, flexDirection: isMobile ? 'column' : 'row' });

const primaryButtonStyle = { border: 'none', borderRadius: 999, padding: '10px 16px', background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)', color: '#fff', fontWeight: 700, cursor: 'pointer' };
const secondaryButtonStyle = { border: '1px solid rgba(255,255,255,0.14)', borderRadius: 999, padding: '10px 16px', background: 'rgba(255,255,255,0.04)', color: '#fff', fontWeight: 700, cursor: 'pointer' };

const noticeStyle = (type) => ({
  padding: '12px 14px', borderRadius: 16,
  border: type === 'error' ? '1px solid rgba(255, 145, 145, 0.22)' : '1px solid rgba(125, 255, 160, 0.3)',
  background: type === 'error' ? 'rgba(255, 98, 98, 0.12)' : 'rgba(70, 200, 120, 0.1)',
  color: type === 'error' ? '#ffd8d8' : '#bdf0cf',
});

export default AnalystIngredientsBulkCreatePage;

import { useEffect, useState } from 'react';

const emptyImpresoraCajaDraft = { ip: '', puerto: '515', cola: '', activo: false };

function AnalysPrintersPage({ isMobile, isAdmin, onBack }) {
  const [categorias, setCategorias] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState(null);
  const [message, setMessage] = useState('');

  const [impresoraCajaDraft, setImpresoraCajaDraft] = useState(emptyImpresoraCajaDraft);
  const [loadingCaja, setLoadingCaja] = useState(true);
  const [savingCaja, setSavingCaja] = useState(false);
  const [cajaMessage, setCajaMessage] = useState('');

  useEffect(() => {
    if (!isAdmin) {
      setLoading(false);
      return;
    }

    const loadCategorias = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/admin/categorias/', {
          credentials: 'include',
          cache: 'no-store',
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || 'No se pudieron cargar las categorías.');
        }
        const list = Array.isArray(data.categorias) ? data.categorias : [];
        setCategorias(list);
        const initialDrafts = {};
        list.forEach((categoria) => {
          initialDrafts[categoria.id] = {
            ip_impresora: categoria.ip_impresora || '',
            puerto_impresora: String(categoria.puerto_impresora || 9100),
            ip_impresora_secundaria: categoria.ip_impresora_secundaria || '',
            puerto_impresora_secundaria: String(categoria.puerto_impresora_secundaria || 9100),
            arma_plato_automatico: Boolean(categoria.arma_plato_automatico),
          };
        });
        setDrafts(initialDrafts);
      } catch (error) {
        setMessage(error.message || 'No se pudieron cargar las categorías.');
      } finally {
        setLoading(false);
      }
    };

    loadCategorias();
  }, [isAdmin]);

  useEffect(() => {
    if (!isAdmin) {
      setLoadingCaja(false);
      return;
    }

    const loadImpresoraCaja = async () => {
      setLoadingCaja(true);
      try {
        const response = await fetch('/api/admin/impresora-caja/', {
          credentials: 'include',
          cache: 'no-store',
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.message || 'No se pudo cargar la impresora de caja.');
        }
        const impresora = data.impresora_caja || {};
        setImpresoraCajaDraft({
          ip: impresora.ip || '',
          puerto: String(impresora.puerto || 515),
          cola: impresora.cola || '',
          activo: Boolean(impresora.activo),
        });
      } catch (error) {
        setCajaMessage(error.message || 'No se pudo cargar la impresora de caja.');
      } finally {
        setLoadingCaja(false);
      }
    };

    loadImpresoraCaja();
  }, [isAdmin]);

  const handleSaveImpresoraCaja = async (event) => {
    event.preventDefault();
    setSavingCaja(true);
    setCajaMessage('');
    try {
      const response = await fetch('/api/admin/impresora-caja/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ip: impresoraCajaDraft.ip.trim(),
          puerto: impresoraCajaDraft.puerto,
          cola: impresoraCajaDraft.cola.trim(),
          activo: impresoraCajaDraft.activo,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo guardar la impresora de caja.');
      }
      const impresora = data.impresora_caja || {};
      setImpresoraCajaDraft({
        ip: impresora.ip || '',
        puerto: String(impresora.puerto || 515),
        cola: impresora.cola || '',
        activo: Boolean(impresora.activo),
      });
      setCajaMessage(data.message || 'Impresora de caja guardada correctamente.');
    } catch (error) {
      setCajaMessage(error.message || 'No se pudo guardar la impresora de caja.');
    } finally {
      setSavingCaja(false);
    }
  };

  const updateDraft = (categoriaId, field, value) => {
    setDrafts((current) => ({
      ...current,
      [categoriaId]: { ...current[categoriaId], [field]: value },
    }));
  };

  const emptyDraft = {
    ip_impresora: '',
    puerto_impresora: '9100',
    ip_impresora_secundaria: '',
    puerto_impresora_secundaria: '9100',
    arma_plato_automatico: false,
  };

  const handleSave = async (categoria) => {
    const draft = drafts[categoria.id] || emptyDraft;
    setSavingId(categoria.id);
    setMessage('');
    try {
      const response = await fetch('/api/admin/categorias/', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'update',
          id: categoria.id,
          ip_impresora: draft.ip_impresora.trim(),
          puerto_impresora: draft.puerto_impresora,
          ip_impresora_secundaria: draft.ip_impresora_secundaria.trim(),
          puerto_impresora_secundaria: draft.puerto_impresora_secundaria,
          arma_plato_automatico: draft.arma_plato_automatico,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) {
        throw new Error(data.message || 'No se pudo guardar la impresora.');
      }
      setCategorias((current) => current.map((entry) => (entry.id === categoria.id ? data.categoria : entry)));
      setMessage(`Impresora de "${categoria.nombre}" guardada correctamente.`);
    } catch (error) {
      setMessage(error.message || 'No se pudo guardar la impresora.');
    } finally {
      setSavingId(null);
    }
  };

  if (!isAdmin) {
    return (
      <section style={containerStyle(isMobile)}>
        <div style={badgeStyle}>Impresoras</div>
        <h2 style={titleStyle(isMobile)}>Acceso restringido</h2>
        <div style={noticeStyle}>Solo el rol Administrador puede configurar las impresoras.</div>
        <button type="button" onClick={onBack} style={backButtonStyle}>
          ← Volver al panel del analista
        </button>
      </section>
    );
  }

  return (
    <section style={containerStyle(isMobile)}>
      <button type="button" onClick={onBack} style={backButtonStyle}>
        ← Volver al panel del analista
      </button>

      <div style={badgeStyle}>Impresoras</div>
      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Impresoras de cocina</h2>
          <p style={subtitleStyle}>
            Asigna la IP fija (y puerto, normalmente 9100) de la impresora térmica que debe imprimir la comanda de
            cada categoría. Las categorías sin IP asignada simplemente no imprimen nada. Opcionalmente, la
            impresora secundaria recibe además una copia reducida (solo cantidad/peso y nota, sin guarniciones ni
            adicionales) de la misma categoría — ej: Especialidad de la Casa imprimiendo el corte en cocina y,
            aparte, en la parrilla. "Arma plato automático" hace que, al mesero agregar un producto de esa
            categoría, el plato se arme y cierre solo, sin usar los botones "Armar plato"/"Terminar". Los cambios
            aplican al siguiente pedido que se registre.
          </p>
        </div>
      </div>

      {message ? <div style={noticeStyle}>{message}</div> : null}

      <section style={panelStyle}>
        {loading ? <div style={emptyStateStyle}>Cargando categorías...</div> : null}
        {!loading && categorias.length === 0 ? (
          <div style={emptyStateStyle}>No hay categorías registradas todavía.</div>
        ) : null}

        {!loading && categorias.length > 0 ? (
          <div style={tableWrapStyle}>
            <div style={tableStyle}>
              <div style={tableHeadStyle}>Categoría</div>
              <div style={tableHeadStyle}>IP de la impresora</div>
              <div style={tableHeadStyle}>Puerto</div>
              <div style={tableHeadStyle}>IP secundaria</div>
              <div style={tableHeadStyle}>Puerto secundario</div>
              <div style={tableHeadStyle}>Arma plato automático</div>
              <div style={tableHeadStyle}>Acciones</div>

              {categorias.map((categoria) => {
                const draft = drafts[categoria.id] || emptyDraft;
                return (
                  <>
                    <div key={`nombre-${categoria.id}`} style={tableCellPrimaryStyle}>
                      <div style={categoriaNameStyle}>{categoria.nombre}</div>
                    </div>
                    <div key={`ip-${categoria.id}`} style={tableCellStyle}>
                      <input
                        type="text"
                        placeholder="192.168.1.200"
                        value={draft.ip_impresora}
                        onChange={(event) => updateDraft(categoria.id, 'ip_impresora', event.target.value)}
                        style={inputStyle}
                      />
                    </div>
                    <div key={`puerto-${categoria.id}`} style={tableCellStyle}>
                      <input
                        type="number"
                        min="1"
                        max="65535"
                        value={draft.puerto_impresora}
                        onChange={(event) => updateDraft(categoria.id, 'puerto_impresora', event.target.value)}
                        style={{ ...inputStyle, width: 100 }}
                      />
                    </div>
                    <div key={`ip-sec-${categoria.id}`} style={tableCellStyle}>
                      <input
                        type="text"
                        placeholder="192.168.1.201"
                        value={draft.ip_impresora_secundaria}
                        onChange={(event) => updateDraft(categoria.id, 'ip_impresora_secundaria', event.target.value)}
                        style={inputStyle}
                      />
                    </div>
                    <div key={`puerto-sec-${categoria.id}`} style={tableCellStyle}>
                      <input
                        type="number"
                        min="1"
                        max="65535"
                        value={draft.puerto_impresora_secundaria}
                        onChange={(event) => updateDraft(categoria.id, 'puerto_impresora_secundaria', event.target.value)}
                        style={{ ...inputStyle, width: 100 }}
                      />
                    </div>
                    <div key={`auto-plato-${categoria.id}`} style={{ ...tableCellStyle, alignItems: 'center' }}>
                      <label style={autoPlatoCheckboxRowStyle}>
                        <input
                          type="checkbox"
                          checked={draft.arma_plato_automatico}
                          onChange={(event) => updateDraft(categoria.id, 'arma_plato_automatico', event.target.checked)}
                        />
                        <span>Sí</span>
                      </label>
                    </div>
                    <div key={`actions-${categoria.id}`} style={tableCellActionStyle}>
                      <button
                        type="button"
                        onClick={() => handleSave(categoria)}
                        style={primaryButtonStyle}
                        disabled={savingId === categoria.id}
                      >
                        {savingId === categoria.id ? 'Guardando...' : 'Guardar'}
                      </button>
                      {categoria.ip_impresora ? (
                        <span style={assignedPillStyle}>Imprime en {categoria.ip_impresora}:{categoria.puerto_impresora}</span>
                      ) : (
                        <span style={unassignedPillStyle}>Sin impresora</span>
                      )}
                      {categoria.ip_impresora_secundaria ? (
                        <span style={assignedPillStyle}>
                          + {categoria.ip_impresora_secundaria}:{categoria.puerto_impresora_secundaria}
                        </span>
                      ) : null}
                    </div>
                  </>
                );
              })}
            </div>
          </div>
        ) : null}
      </section>

      <div style={headerRowStyle(isMobile)}>
        <div>
          <h2 style={titleStyle(isMobile)}>Impresora de caja</h2>
          <p style={subtitleStyle}>
            El recibo con el detalle y el total del pedido para el cliente sale por esta impresora, distinta a las
            de cocina: es una impresora USB conectada a la PC de caja y compartida en red vía el "LPD Print Service"
            de Windows (puerto estándar 515), no ESC/POS directo por socket. Indica la IP de esa PC y el nombre
            exacto de la cola tal como quedó compartida.
          </p>
        </div>
      </div>

      {cajaMessage ? <div style={noticeStyle}>{cajaMessage}</div> : null}

      <section style={panelStyle}>
        {loadingCaja ? <div style={emptyStateStyle}>Cargando configuración...</div> : null}
        {!loadingCaja ? (
          <form onSubmit={handleSaveImpresoraCaja} style={cajaFormStyle(isMobile)}>
            <label style={cajaFieldStyle}>
              <span style={cajaLabelStyle}>IP de la PC de caja</span>
              <input
                type="text"
                placeholder="192.168.1.236"
                value={impresoraCajaDraft.ip}
                onChange={(event) => setImpresoraCajaDraft((current) => ({ ...current, ip: event.target.value }))}
                style={inputStyle}
              />
            </label>
            <label style={cajaFieldStyle}>
              <span style={cajaLabelStyle}>Puerto LPD</span>
              <input
                type="number"
                min="1"
                max="65535"
                value={impresoraCajaDraft.puerto}
                onChange={(event) => setImpresoraCajaDraft((current) => ({ ...current, puerto: event.target.value }))}
                style={inputStyle}
              />
            </label>
            <label style={cajaFieldStyle}>
              <span style={cajaLabelStyle}>Nombre de la cola compartida</span>
              <input
                type="text"
                placeholder="Impresora_Caja"
                value={impresoraCajaDraft.cola}
                onChange={(event) => setImpresoraCajaDraft((current) => ({ ...current, cola: event.target.value }))}
                style={inputStyle}
              />
            </label>
            <label style={cajaToggleRowStyle}>
              <input
                type="checkbox"
                checked={impresoraCajaDraft.activo}
                onChange={(event) => setImpresoraCajaDraft((current) => ({ ...current, activo: event.target.checked }))}
              />
              <span>Impresora activa (si está apagado, cobrar no intenta imprimir el recibo)</span>
            </label>
            <button type="submit" style={primaryButtonStyle} disabled={savingCaja}>
              {savingCaja ? 'Guardando...' : 'Guardar impresora de caja'}
            </button>
          </form>
        ) : null}
      </section>
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

const tableWrapStyle = {
  overflowX: 'auto',
};

const tableStyle = {
  display: 'grid',
  gridTemplateColumns:
    'minmax(150px, 0.8fr) minmax(160px, 1fr) minmax(90px, 0.5fr) minmax(160px, 1fr) minmax(90px, 0.5fr) minmax(130px, 0.6fr) minmax(260px, 1.2fr)',
  alignItems: 'stretch',
  border: '1px solid rgba(255, 255, 255, 0.08)',
  borderRadius: 18,
  overflow: 'hidden',
  minWidth: 1320,
};

const tableHeadStyle = {
  padding: '14px 16px',
  background: 'rgba(255, 255, 255, 0.06)',
  color: '#ffb0b0',
  fontSize: 12,
  fontWeight: 800,
  letterSpacing: '0.12em',
  textTransform: 'uppercase',
  borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
};

const tableCellStyle = {
  padding: '12px 16px',
  borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
  color: '#f2e6e6',
  display: 'grid',
  alignContent: 'center',
  gap: 4,
};

const tableCellPrimaryStyle = {
  ...tableCellStyle,
  background: 'rgba(255, 255, 255, 0.02)',
};

const tableCellActionStyle = {
  ...tableCellStyle,
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  flexWrap: 'wrap',
};

const autoPlatoCheckboxRowStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 8,
  color: '#f2e6e6',
  fontWeight: 600,
  fontSize: 13,
};

const categoriaNameStyle = {
  color: '#fff',
  fontWeight: 700,
  fontSize: 15,
};

const inputStyle = {
  width: '100%',
  boxSizing: 'border-box',
  borderRadius: 10,
  border: '1px solid rgba(255, 255, 255, 0.14)',
  background: 'rgba(255, 255, 255, 0.04)',
  padding: '9px 10px',
  color: '#fff',
  fontSize: 13,
};

const assignedPillStyle = {
  padding: '6px 10px',
  borderRadius: 999,
  background: 'rgba(94, 197, 135, 0.14)',
  border: '1px solid rgba(94, 197, 135, 0.22)',
  color: '#c8ffe0',
  fontSize: 11.5,
  fontWeight: 700,
};

const unassignedPillStyle = {
  padding: '6px 10px',
  borderRadius: 999,
  background: 'rgba(180, 180, 180, 0.14)',
  border: '1px solid rgba(180, 180, 180, 0.24)',
  color: '#e0e0e0',
  fontSize: 11.5,
  fontWeight: 700,
};

const cajaFormStyle = (isMobile) => ({
  display: 'grid',
  gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 1fr))',
  gap: 14,
  alignItems: 'end',
});

const cajaFieldStyle = {
  display: 'grid',
  gap: 6,
};

const cajaLabelStyle = {
  color: '#f0b4b4',
  fontSize: 13,
  fontWeight: 700,
};

const cajaToggleRowStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 10,
  color: '#fff',
  fontWeight: 600,
  gridColumn: '1 / -1',
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
  padding: '9px 14px',
  background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
  fontSize: 13,
};

const backButtonStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  justifySelf: 'flex-start',
  width: 'fit-content',
  border: 'none',
  background: 'transparent',
  color: '#ffb5b5',
  fontWeight: 700,
  cursor: 'pointer',
  padding: 0,
};

export default AnalysPrintersPage;
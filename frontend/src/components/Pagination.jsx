function Pagination({ page, pageCount, totalCount, pageSize, onPrev, onNext, isMobile }) {
  if (pageCount <= 1) {
    return null;
  }

  const from = totalCount === 0 ? 0 : page * pageSize + 1;
  const to = Math.min((page + 1) * pageSize, totalCount);

  return (
    <div style={wrapStyle(isMobile)}>
      <div style={labelStyle}>Mostrando {from}–{to} de {totalCount}</div>
      <div style={controlsStyle}>
        <button type="button" onClick={onPrev} disabled={page === 0} style={navButtonStyle(page === 0)}>
          ‹ Anterior
        </button>
        <span style={pageIndicatorStyle}>Página {page + 1} de {pageCount}</span>
        <button type="button" onClick={onNext} disabled={page >= pageCount - 1} style={navButtonStyle(page >= pageCount - 1)}>
          Siguiente ›
        </button>
      </div>
    </div>
  );
}

const wrapStyle = (isMobile) => ({
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: isMobile ? 'flex-start' : 'center',
  flexDirection: isMobile ? 'column' : 'row',
  gap: 10,
  paddingTop: 10,
  borderTop: '1px solid rgba(255, 255, 255, 0.08)',
});

const labelStyle = {
  color: '#c8bbbb',
  fontSize: 13,
};

const controlsStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
};

const pageIndicatorStyle = {
  color: '#fff',
  fontSize: 13,
  fontWeight: 700,
  minWidth: 92,
  textAlign: 'center',
};

const navButtonStyle = (disabled) => ({
  border: '1px solid rgba(255, 255, 255, 0.16)',
  borderRadius: 999,
  padding: '8px 14px',
  background: disabled ? 'rgba(255, 255, 255, 0.02)' : 'rgba(255, 255, 255, 0.06)',
  color: disabled ? '#7a6f6f' : '#fff',
  fontWeight: 700,
  fontSize: 13,
  cursor: disabled ? 'default' : 'pointer',
});

export default Pagination;
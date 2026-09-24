// design-tokens.js
// Tokens de diseño centralizados para todo el sistema Varagrill.
// Úsalos como valores de referencia, no como importaciones obligatorias
// (los componentes existentes usan inline styles, mantenemos ese patrón).

export const colors = {
  // Fondos
  bgBase:       '#050505',
  bgCard:       'rgba(10, 10, 10, 0.98)',
  bgCardAlt:    'rgba(20, 10, 10, 0.94)',
  bgSidebar:    'linear-gradient(180deg, rgba(22, 8, 8, 0.98) 0%, rgba(8, 8, 8, 0.98) 100%)',
  bgInput:      'rgba(255, 255, 255, 0.04)',

  // Acentos
  accentCrimson:    '#bf1f1f',
  accentCoral:      '#ff4d4d',
  accentCoralLight: '#ff7d7d',
  accentCoralMuted: '#ff8f8f',

  // Texto
  textPrimary:   '#f5f5f5',
  textSecondary: '#c8c8c8',
  textRose:      '#f1cfcf',
  textRoseMuted: '#d2c3c3',
  textRoseWeak:  '#e6bbbb',
  textRedLabel:  '#ff8f8f',

  // Bordes
  borderRed:       'rgba(255, 77, 77, 0.22)',
  borderRedStrong: 'rgba(255, 89, 89, 0.34)',
  borderWhite:     'rgba(255, 255, 255, 0.08)',
  borderWhiteMid:  'rgba(255, 255, 255, 0.14)',

  // Estados
  successBg:     'rgba(20, 60, 32, 0.96)',
  successBorder: 'rgba(125, 255, 160, 0.4)',
  successText:   '#c2f0d2',
  errorBg:       'rgba(70, 16, 16, 0.96)',
  errorBorder:   'rgba(255, 145, 145, 0.45)',
  errorText:     '#ffd8d8',
};

export const radii = {
  sm:   10,
  md:   14,
  lg:   20,
  xl:   24,
  xxl:  28,
  pill: 999,
};

export const shadows = {
  card:    '0 12px 32px rgba(0, 0, 0, 0.28)',
  cardLg:  '0 18px 50px rgba(0, 0, 0, 0.45)',
  glow:    '0 0 20px rgba(191, 31, 31, 0.35)',
  glowBtn: '0 4px 16px rgba(191, 31, 31, 0.45)',
  sidebar: '12px 0 26px rgba(0, 0, 0, 0.38)',
};

export const transitions = {
  fast:   '150ms ease',
  normal: '220ms ease',
  slow:   '320ms ease',
};

export const font = {
  family: "'Inter', system-ui, -apple-system, sans-serif",
};

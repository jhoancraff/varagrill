import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

// Tema de la aplicación: 'dark' (el de siempre) o 'light'. Se guarda en localStorage y se aplica como
// atributo data-theme en <html>; todos los colores salen de variables CSS --vg-* (ver index.css y
// theme-colors.css), así que cambiar el atributo cambia toda la interfaz sin tocar cada componente.
export const THEME_STORAGE_KEY = 'varagrill_theme';
const THEMES = ['dark', 'light'];
const META_THEME_COLOR = { dark: '#140606', light: '#f8f9fb' };

function readStoredTheme() {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return THEMES.includes(stored) ? stored : 'dark';
  } catch {
    // Navegación privada o almacenamiento bloqueado: se usa el tema oscuro.
    return 'dark';
  }
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) {
    meta.setAttribute('content', META_THEME_COLOR[theme]);
  }
}

const ThemeContext = createContext({ theme: 'dark', isDark: true, setTheme: () => {}, toggleTheme: () => {} });

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(readStoredTheme);

  useEffect(() => {
    applyTheme(theme);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      // Sin almacenamiento el tema vale solo para esta sesión.
    }
  }, [theme]);

  // Si el tema se cambia en otra pestaña, esta la sigue.
  useEffect(() => {
    const onStorage = (event) => {
      if (event.key === THEME_STORAGE_KEY && THEMES.includes(event.newValue)) {
        setThemeState(event.newValue);
      }
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const setTheme = useCallback((next) => {
    if (THEMES.includes(next)) {
      setThemeState(next);
    }
  }, []);
  const toggleTheme = useCallback(() => {
    setThemeState((current) => (current === 'dark' ? 'light' : 'dark'));
  }, []);

  const value = useMemo(
    () => ({ theme, isDark: theme === 'dark', setTheme, toggleTheme }),
    [theme, setTheme, toggleTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  return useContext(ThemeContext);
}

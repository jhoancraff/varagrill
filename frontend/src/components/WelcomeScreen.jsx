import { useCallback, useEffect, useState } from 'react';
import AdminPanelPage from './AdminPanelPage';
import AnalystBulkPromotionPage from './AnalystBulkPromotionPage';
import AnalystChefRecommendationsPage from './AnalystChefRecommendationsPage';
import AnalystEditUserPage from './AnalystEditUserPage';
import AnalystEditIngredientPage from './AnalystEditIngredientPage';
import AnalystEditRecipePage from './AnalystEditRecipePage';
import AnalystEditPreparationPage from './AnalystEditPreparationPage';
import AnalystIngredientsReportPage from './AnalystIngredientsReportPage';
import AnalystNewChefRecommendationPage from './AnalystNewChefRecommendationPage';
import AnalystNewIngredientPage from './AnalystNewIngredientPage';
import AnalystNewPreparationPage from './AnalystNewPreparationPage';
import AnalystNewPromotionPage from './AnalystNewPromotionPage';
import AnalystNewUserPage from './AnalystNewUserPage';
import AnalystNewRecipePage from './AnalystNewRecipePage';
import AnalystPreparationsReportPage from './AnalystPreparationsReportPage';
import AnalystPromotionsPage from './AnalystPromotionsPage';
import AnalystRecipesPage from './AnalystRecipesPage';
import AnalystUsersPage from './AnalystUsersPage';
import ChefRecommendationsPage from './ChefRecommendationsPage';
import KitchenOrdersPage from './KitchenOrdersPage';
import NewOrderPage from './NewOrderPage';
import PromotionsPage from './PromotionsPage';
import useKitchenSocket from '../hooks/useKitchenSocket';
import useKitchenAlerts from './useKitchenAlerts';

function WelcomeScreen({ name, role, isAdmin, onBack }) {
  const isCompactNavigationViewport = () => (
    window.matchMedia('(max-width: 1024px)').matches
    || window.matchMedia('(pointer: coarse)').matches
  );

  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isMobile, setIsMobile] = useState(() => window.matchMedia('(max-width: 768px)').matches);
  const [isSidebarOverlayMode, setIsSidebarOverlayMode] = useState(isCompactNavigationViewport);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const [activeView, setActiveView] = useState('home');
  const [mesas, setMesas] = useState([]);
  const [products, setProducts] = useState([]);
  const [loadingData, setLoadingData] = useState(true);
  const [pendingOrdersCount, setPendingOrdersCount] = useState(0);
  const [liveNotice, setLiveNotice] = useState('');
  const [lastKitchenEvent, setLastKitchenEvent] = useState(null);

  useEffect(() => {
    const handleEscapeClose = (event) => {
      if (event.key === 'Escape') {
        setIsSidebarOpen(false);
      }
    };

    window.addEventListener('keydown', handleEscapeClose);
    return () => window.removeEventListener('keydown', handleEscapeClose);
  }, []);

  useEffect(() => {
    const mediaQuery = window.matchMedia('(max-width: 768px)');

    const handleViewportChange = (event) => {
      setIsMobile(event.matches);
    };

    setIsMobile(mediaQuery.matches);
    mediaQuery.addEventListener('change', handleViewportChange);

    return () => {
      mediaQuery.removeEventListener('change', handleViewportChange);
    };
  }, []);

  useEffect(() => {
    const widthQuery = window.matchMedia('(max-width: 1024px)');
    const pointerQuery = window.matchMedia('(pointer: coarse)');

    const syncOverlayMode = () => {
      setIsSidebarOverlayMode(widthQuery.matches || pointerQuery.matches);
    };

    syncOverlayMode();
    widthQuery.addEventListener('change', syncOverlayMode);
    pointerQuery.addEventListener('change', syncOverlayMode);

    return () => {
      widthQuery.removeEventListener('change', syncOverlayMode);
      pointerQuery.removeEventListener('change', syncOverlayMode);
    };
  }, []);

  useEffect(() => {
    if (isSidebarOverlayMode) {
      setIsSidebarOpen(false);
      return;
    }

    setIsSidebarOpen(true);
  }, [isSidebarOverlayMode]);

  useEffect(() => {
    if (isSidebarOverlayMode) {
      setIsSidebarOpen(false);
    }
  }, [activeView, isSidebarOverlayMode]);

  const handleHomeClick = () => {
    setActiveView('home');
    if (isSidebarOverlayMode) {
      setIsSidebarOpen(false);
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleAnalystNavigation = (view) => {
    setActiveView(view);
    if (isSidebarOverlayMode) {
      setIsSidebarOpen(false);
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  useEffect(() => {
    const loadOrderData = async () => {
      try {
        const [mesasResponse, productsResponse] = await Promise.all([
          fetch('/api/mesas/', { credentials: 'include', cache: 'no-store' }),
          fetch('/api/productos/', { credentials: 'include', cache: 'no-store' }),
        ]);

        const mesasJson = mesasResponse.ok ? await mesasResponse.json() : [];
        const productsJson = productsResponse.ok ? await productsResponse.json() : [];

        setMesas(Array.isArray(mesasJson) ? mesasJson : []);
        setProducts(Array.isArray(productsJson) && productsJson.length > 0 ? productsJson : fallbackProducts);
      } catch (error) {
        setProducts(fallbackProducts);
        setMesas([]);
      } finally {
        setLoadingData(false);
      }
    };

    loadOrderData();
  }, []);

  useEffect(() => {
    let cancelled = false;

    const loadPendingOrders = async () => {
      try {
        const response = await fetch('/api/pedidos/cocina/?estado=activos&limit=1', {
          credentials: 'include',
          cache: 'no-store',
        });

        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.ok || cancelled) {
          return;
        }

        const count = Number(data.counts?.pendiente || 0);
        setPendingOrdersCount(Number.isFinite(count) ? count : 0);
      } catch (error) {
        // Keep the last known value when there is a temporary network error.
      }
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        loadPendingOrders();
      }
    };

    loadPendingOrders();
    const pollId = window.setInterval(loadPendingOrders, 12000);
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      cancelled = true;
      window.clearInterval(pollId);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, []);

  const normalizedRole = String(role || '').trim().toLowerCase();
  const isKitchenRole = normalizedRole === 'cocinero';

  useEffect(() => {
    if (!isAdmin && activeView.startsWith('admin')) {
      setActiveView('home');
    }
  }, [activeView, isAdmin]);

  const {
    alertPermission,
    alertsEnabled,
    audioUnlocked,
    alertDiagnostics,
    alertMessage,
    triggerKitchenAlert,
    runAlertDiagnostics,
    unlockAudioAndTest,
    requestAlertPermission,
  } = useKitchenAlerts();

  const handleKitchenSocketEvent = useCallback((message) => {
    if (!message?.event || !message.payload) {
      return;
    }

    if (message.event === 'NUEVA_COMANDAS' || message.event === 'PEDIDO_ACTUALIZADO') {
      triggerKitchenAlert(message);
      setLastKitchenEvent({ ...message, receivedAt: Date.now() });
    }

    if (message.event === 'NUEVA_COMANDAS') {
      const payload = message.payload;
      const mesaLabel = payload.mesa ? `Mesa ${payload.mesa}` : 'Sin mesa';
      setLiveNotice(`Alerta cocina: pedido #${payload.pedido_id} (${mesaLabel}) registrado por ${payload.actor}.`);
      setPendingOrdersCount((current) => current + 1);

      window.setTimeout(() => {
        setLiveNotice('');
      }, 8000);
    }
  }, [triggerKitchenAlert]);

  // Single, always-on socket connection for the whole dashboard, so alerts
  // (sound/notification/vibration) fire no matter which view is on screen,
  // instead of only inside the kitchen board.
  const { isConnected: isKitchenSocketConnected } = useKitchenSocket({
    socketPath: '/ws/pedidos/',
    onEvent: handleKitchenSocketEvent,
    enabled: isKitchenRole,
  });

  const sidebarWidth = isSidebarOverlayMode ? 'min(84vw, 320px)' : '300px';
  const desktopContentOffset = isSidebarOpen && !isSidebarOverlayMode ? '332px' : '0px';
  const displayName = name || 'Usuario';
  const todayLabel = new Intl.DateTimeFormat('es-ES', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).format(new Date());

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      background: 'radial-gradient(circle at top, #2f0b0b 0%, #120606 45%, #050505 100%)',
      padding: isMobile ? 16 : 24,
      boxSizing: 'border-box',
      position: 'relative',
      overflow: 'hidden',
      fontFamily: 'Arial, sans-serif',
    }}>
      <style>
        {`@keyframes pendingPulse {
            0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(255, 122, 122, 0.45); }
            70% { transform: scale(1.08); box-shadow: 0 0 0 10px rgba(255, 122, 122, 0); }
            100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(255, 122, 122, 0); }
          }`}
      </style>
      {liveNotice && (
        <div style={liveNoticeStyle}>
          {liveNotice}
        </div>
      )}
      {isSidebarOpen && isSidebarOverlayMode && (
        <button
          type="button"
          onClick={() => setIsSidebarOpen(false)}
          aria-label="Cerrar barra lateral"
          style={{
            position: 'fixed',
            inset: 0,
            border: 'none',
            background: 'rgba(0, 0, 0, 0.48)',
            zIndex: 19,
            cursor: 'pointer',
            padding: 0,
          }}
        />
      )}

      {!isSidebarOpen && (
        <button
          type="button"
          onClick={() => setIsSidebarOpen(true)}
          aria-label="Abrir barra lateral"
          style={{
            position: 'fixed',
            top: 16,
            left: 16,
            width: 42,
            height: 42,
            borderRadius: 12,
            border: '1px solid rgba(255, 110, 110, 0.45)',
            background: 'rgba(36, 13, 13, 0.96)',
            color: '#fff',
            display: 'grid',
            placeItems: 'center',
            cursor: 'pointer',
            zIndex: 30,
            boxShadow: '0 8px 20px rgba(0, 0, 0, 0.35)',
          }}
        >
          <span aria-hidden="true" style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M4 7h16" />
              <path d="M4 12h16" />
              <path d="M4 17h16" />
            </svg>
          </span>
        </button>
      )}

      <aside
        aria-label="Barra lateral"
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          height: '100vh',
          width: sidebarWidth,
          transform: isSidebarOpen ? 'translateX(0)' : 'translateX(-100%)',
          transition: 'transform 260ms ease',
          zIndex: 24,
          background: 'linear-gradient(180deg, rgba(22, 8, 8, 0.98) 0%, rgba(8, 8, 8, 0.98) 100%)',
          borderRight: '1px solid rgba(255, 89, 89, 0.34)',
          boxShadow: '12px 0 26px rgba(0, 0, 0, 0.38)',
          padding: '72px 12px 20px',
          boxSizing: 'border-box',
          overflowY: 'auto',
          overflowX: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}
      >
        <button
          type="button"
          onClick={() => setIsSidebarOpen(false)}
          aria-label="Cerrar barra lateral"
          style={{
            position: 'absolute',
            top: 16,
            right: 12,
            width: 38,
            height: 38,
            borderRadius: 10,
            border: '1px solid rgba(255, 110, 110, 0.35)',
            background: 'rgba(46, 14, 14, 0.88)',
            color: '#fff',
            display: 'grid',
            placeItems: 'center',
            cursor: 'pointer',
          }}
        >
          <span style={{ fontSize: 20, lineHeight: 1 }}>×</span>
        </button>

        <div style={{
          padding: '0 4px 12px',
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
        }}>
          <div style={{ fontSize: 12, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#ff8f8f', marginBottom: 8 }}>
            Panel
          </div>
          <div style={{ color: '#d1d1d1', fontSize: 14, lineHeight: 1.5 }}>
            Accesos directos para cocina, pedidos y servicio.
          </div>
        </div>

        <button
          type="button"
          onClick={handleHomeClick}
          style={sidebarButtonStyle(activeView === 'home')}
        >
          <span aria-hidden="true" style={sidebarIconWrapStyle}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 10.5L12 3l9 7.5" />
              <path d="M5 9.5V21h14V9.5" />
              <path d="M9.5 21v-6.5h5V21" />
            </svg>
          </span>
          <span>Inicio</span>
        </button>

        <button
          type="button"
          onClick={() => {
            setActiveView('orders');
            if (isSidebarOverlayMode) {
              setIsSidebarOpen(false);
            }
          }}
          style={sidebarButtonStyle(activeView === 'orders')}
        >
          <span aria-hidden="true" style={sidebarIconWrapStyle}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 11h6" />
              <path d="M9 15h6" />
              <path d="M5 3h14a2 2 0 0 1 2 2v14l-3-2-3 2-3-2-3 2-3-2V5a2 2 0 0 1 2-2Z" />
            </svg>
          </span>
          <span>Nuevo pedido</span>
        </button>

        <button
          type="button"
          onClick={() => {
            setActiveView('kitchen');
            if (isSidebarOverlayMode) {
              setIsSidebarOpen(false);
            }
          }}
          style={sidebarButtonStyle(activeView === 'kitchen')}
        >
          <span aria-hidden="true" style={sidebarIconWrapStyle}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M8 2h8" />
              <path d="M9 2v3" />
              <path d="M15 2v3" />
              <path d="M5 5h14" />
              <rect x="4" y="5" width="16" height="17" rx="2" />
              <path d="M8 10h8" />
              <path d="M8 14h8" />
              <path d="M8 18h5" />
            </svg>
          </span>
          <span style={{ flex: 1, textAlign: 'left' }}>Pedidos</span>
          <span style={pendingBadgeStyle(pendingOrdersCount > 0)}>{pendingOrdersCount}</span>
          
          
        </button>

        {isAdmin ? (
          <button
            type="button"
            onClick={() => {
              setActiveView('admin');
              if (isSidebarOverlayMode) {
                setIsSidebarOpen(false);
              }
            }}
            style={sidebarButtonStyle(activeView.startsWith('admin'))}
          >
            <span aria-hidden="true" style={sidebarIconWrapStyle}>
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.09A1.65 1.65 0 0 0 10 3.09V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.09a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" />
              </svg>
            </span>
            <span>Panel analista</span>
          </button>
        ) : null}

        <div style={{ flex: 1 }} />

        <div style={{
          borderRadius: 22,
          padding: 16,
          background: 'linear-gradient(180deg, rgba(191, 31, 31, 0.18) 0%, rgba(255, 255, 255, 0.03) 100%)',
          border: '1px solid rgba(255, 102, 102, 0.2)',
        }}>
          <button
            type="button"
            onClick={() => setIsUserMenuOpen((current) => !current)}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              marginBottom: isUserMenuOpen ? 14 : 0,
              background: 'transparent',
              border: 'none',
              padding: 0,
              color: 'inherit',
              cursor: 'pointer',
              textAlign: 'left',
            }}
          >
            <div style={{
              width: 44,
              height: 44,
              borderRadius: 14,
              background: 'linear-gradient(135deg, #ff5a5a 0%, #7f1414 100%)',
              display: 'grid',
              placeItems: 'center',
              color: '#fff',
              fontWeight: 700,
              fontSize: 16,
              flexShrink: 0,
            }}>
              {displayName.slice(0, 1).toUpperCase()}
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#ffaaaa', marginBottom: 4 }}>
                Usuario activo
              </div>
              <div style={{ fontSize: 17, fontWeight: 700, color: '#fff', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {displayName}
              </div>
              <div style={{ fontSize: 12, color: '#e6bbbb', marginTop: 3 }}>
                {todayLabel}
              </div>
            </div>
            <span aria-hidden="true" style={{ marginLeft: 'auto', opacity: 0.72, transform: isUserMenuOpen ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 180ms ease' }}>
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="m6 9 6 6 6-6" />
              </svg>
            </span>
          </button>

          {isUserMenuOpen && (
            <div style={{
              display: 'grid',
              gap: 10,
              paddingTop: 12,
              borderTop: '1px solid rgba(255, 255, 255, 0.08)',
            }}>
              <button
                type="button"
                style={userActionButtonStyle}
              >
                <span aria-hidden="true" style={userActionIconStyle}>
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="3" />
                    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.09A1.65 1.65 0 0 0 10 3.09V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.09a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" />
                  </svg>
                </span>
                <span style={{ flex: 1 }}>Configuración</span>
              </button>

              <button
                type="button"
                onClick={onBack}
                style={userActionButtonStyle}
              >
                <span aria-hidden="true" style={userActionIconStyle}>
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                    <path d="m16 17 5-5-5-5" />
                    <path d="M21 12H9" />
                  </svg>
                </span>
                <span style={{ flex: 1 }}>Cerrar sesión</span>
              </button>
            </div>
          )}
        </div>
      </aside>

      <div style={{
        width: '100%',
        maxWidth: 1180,
        marginLeft: desktopContentOffset,
        transition: 'margin-left 260ms ease',
        display: 'grid',
        gap: 18,
        alignContent: 'start',
        paddingTop: isMobile ? 64 : 0,
      }}>
        {activeView === 'home' ? (
          <>
            <div style={{
              display: 'flex',
              justifyContent: 'flex-end',
              alignItems: 'center',
              gap: 10,
              flexWrap: 'wrap',
            }}>
              <button
                type="button"
                onClick={() => setActiveView('kitchen')}
                style={kitchenButtonStyle}
              >
                <span aria-hidden="true" style={sidebarIconWrapStyle}>
                  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 4h18" />
                    <path d="M5 8h14" />
                    <path d="M8 12h8" />
                    <path d="M6 16h12" />
                    <path d="M9 20h6" />
                  </svg>
                </span>
                Ver cocina
              </button>

              <button
                type="button"
                onClick={() => setActiveView('orders')}
                style={newOrderButtonStyle}
              >
                <span aria-hidden="true" style={sidebarIconWrapStyle}>
                  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 5v14" />
                    <path d="M5 12h14" />
                  </svg>
                </span>
                Nuevo pedido
              </button>
            </div>

            <section style={{
              display: 'grid',
              gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, minmax(0, 1fr))',
              gap: 16,
            }}>
              {[
                {
                  view: 'promotions',
                  title: 'Promociones',
                  text: 'Consulta el catalogo de promociones vigentes para ofrecer al cliente.',
                  icon: (
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M20.59 13.41 12 22l-9-9V4a1 1 0 0 1 1-1h9l8.59 8.59a2 2 0 0 1 0 2.82Z" />
                      <path d="M7 7h.01" />
                    </svg>
                  ),
                },
                {
                  view: 'chef-recommendations',
                  title: 'Recomendación del chef',
                  text: 'Descubre los platos que el chef sugiere destacar durante el servicio de hoy.',
                  icon: (
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M17 21v-8a5 5 0 0 0-10 0v8" />
                      <path d="M4 21h16" />
                      <path d="M12 3a4 4 0 0 1 4 4c0 1.5-1 2-1 3H9c0-1-1-1.5-1-3a4 4 0 0 1 4-4Z" />
                    </svg>
                  ),
                },
              ].map((item) => (
                <button
                  key={item.view}
                  type="button"
                  onClick={() => setActiveView(item.view)}
                  style={featureCardButtonStyle}
                >
                  <div style={{ display: 'inline-grid', placeItems: 'center', width: 44, height: 44, borderRadius: 14, background: 'rgba(255, 88, 88, 0.12)', color: '#ff7d7d', marginBottom: 18 }}>
                    {item.icon}
                  </div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: '#fff', marginBottom: 10 }}>{item.title}</div>
                  <div style={{ color: '#c7c7c7', lineHeight: 1.6, fontSize: 14 }}>{item.text}</div>
                </button>
              ))}
            </section>
          </>
        ) : activeView === 'promotions' ? (
          <PromotionsPage
            isMobile={isMobile}
            onBack={() => setActiveView('home')}
          />
        ) : activeView === 'chef-recommendations' ? (
          <ChefRecommendationsPage
            isMobile={isMobile}
            onBack={() => setActiveView('home')}
          />
        ) : activeView === 'orders' ? (
          <NewOrderPage
            isMobile={isMobile}
            mesas={mesas}
            products={products}
            loadingData={loadingData}
            waiterName={displayName}
            onBack={() => setActiveView('home')}
          />
        ) : activeView === 'admin' ? (
          <AdminPanelPage
            isMobile={isMobile}
            onBack={() => setActiveView('home')}
            onNavigate={handleAnalystNavigation}
          />
        ) : activeView === 'admin-users' ? (
          <AnalystUsersPage
            isMobile={isMobile}
            isAdmin={isAdmin}
            onBack={() => setActiveView('admin')}
            onCreateNewUser={() => setActiveView('admin-users-new')}
            onEditUser={(userId) => setActiveView(`admin-users-edit:${userId}`)}
          />
        ) : activeView.startsWith('admin-users-edit:') ? (
          <AnalystEditUserPage
            isMobile={isMobile}
            isAdmin={isAdmin}
            userId={activeView.split(':')[1] || ''}
            onBack={() => setActiveView('admin-users')}
          />
        ) : activeView === 'admin-users-new' ? (
          <AnalystNewUserPage
            isMobile={isMobile}
            isAdmin={isAdmin}
            onBack={() => setActiveView('admin-users')}
          />
        ) : activeView === 'admin-ingredients' ? (
          <AnalystIngredientsReportPage
            isMobile={isMobile}
            onBack={() => setActiveView('admin')}
            onCreateNew={() => setActiveView('admin-ingredients-new')}
            onEdit={(ingredientId) => setActiveView(`admin-ingredients-edit:${ingredientId}`)}
          />
        ) : activeView.startsWith('admin-ingredients-edit:') ? (
          <AnalystEditIngredientPage
            isMobile={isMobile}
            ingredientId={activeView.split(':')[1] || ''}
            onBack={() => setActiveView('admin-ingredients')}
          />
        ) : activeView === 'admin-ingredients-new' ? (
          <AnalystNewIngredientPage
            isMobile={isMobile}
            onBack={() => setActiveView('admin-ingredients')}
          />
        ) : activeView === 'admin-preparations' ? (
          <AnalystPreparationsReportPage
            isMobile={isMobile}
            onBack={() => setActiveView('admin')}
            onCreateNew={() => setActiveView('admin-preparations-new')}
            onEdit={(preparationId) => setActiveView(`admin-preparations-edit:${preparationId}`)}
          />
        ) : activeView.startsWith('admin-preparations-edit:') ? (
          <AnalystEditPreparationPage
            isMobile={isMobile}
            preparationId={activeView.split(':')[1] || ''}
            onBack={() => setActiveView('admin-preparations')}
          />
        ) : activeView === 'admin-preparations-new' ? (
          <AnalystNewPreparationPage
            isMobile={isMobile}
            onBack={() => setActiveView('admin-preparations')}
          />
        ) : activeView === 'admin-recipes' ? (
          <AnalystRecipesPage
            isMobile={isMobile}
            isAdmin={isAdmin}
            onBack={() => setActiveView('admin')}
            onCreateNewRecipe={() => setActiveView('admin-recipes-new')}
            onEditRecipe={(recipeId) => setActiveView(`admin-recipes-edit:${recipeId}`)}
          />
        ) : activeView.startsWith('admin-recipes-edit:') ? (
          <AnalystEditRecipePage
            isMobile={isMobile}
            isAdmin={isAdmin}
            recipeId={activeView.split(':')[1] || ''}
            onBack={() => setActiveView('admin-recipes')}
          />
        ) : activeView === 'admin-recipes-new' ? (
          <AnalystNewRecipePage
            isMobile={isMobile}
            isAdmin={isAdmin}
            onBack={() => setActiveView('admin-recipes')}
          />
        ) : activeView === 'admin-promotions' ? (
          <AnalystPromotionsPage
            isMobile={isMobile}
            isAdmin={isAdmin}
            onBack={() => setActiveView('admin')}
            onSelectProduct={(productId) => setActiveView(`admin-promotions-new:${productId}`)}
            onSelectBulk={(productIds) => setActiveView(`admin-promotions-bulk:${productIds.join(',')}`)}
          />
        ) : activeView.startsWith('admin-promotions-new:') ? (
          <AnalystNewPromotionPage
            isMobile={isMobile}
            isAdmin={isAdmin}
            productId={activeView.split(':')[1] || ''}
            onBack={() => setActiveView('admin-promotions')}
          />
        ) : activeView.startsWith('admin-promotions-bulk:') ? (
          <AnalystBulkPromotionPage
            isMobile={isMobile}
            isAdmin={isAdmin}
            productIds={activeView.split(':')[1] || ''}
            onBack={() => setActiveView('admin-promotions')}
          />
        ) : activeView === 'admin-chef-recommendations' ? (
          <AnalystChefRecommendationsPage
            isMobile={isMobile}
            isAdmin={isAdmin}
            onBack={() => setActiveView('admin')}
            onCreateNew={() => setActiveView('admin-chef-recommendations-new')}
          />
        ) : activeView === 'admin-chef-recommendations-new' ? (
          <AnalystNewChefRecommendationPage
            isMobile={isMobile}
            isAdmin={isAdmin}
            onBack={() => setActiveView('admin-chef-recommendations')}
          />
        ) : (
          <KitchenOrdersPage
            isMobile={isMobile}
            onBack={() => setActiveView('home')}
            isSocketConnected={isKitchenSocketConnected}
            alertPermission={alertPermission}
            alertsEnabled={alertsEnabled}
            audioUnlocked={audioUnlocked}
            alertDiagnostics={alertDiagnostics}
            alertMessage={alertMessage}
            onUnlockAudio={unlockAudioAndTest}
            onRunDiagnostics={runAlertDiagnostics}
            onRequestPermission={requestAlertPermission}
            lastKitchenEvent={lastKitchenEvent}
          />
        )}
      </div>
    </div>
  );
}

const sidebarButtonStyle = (isPrimary) => ({
  width: '100%',
  border: 'none',
  borderRadius: 16,
  padding: '13px 12px',
  color: '#fff',
  background: isPrimary ? 'rgba(195, 35, 35, 0.26)' : 'rgba(255, 255, 255, 0.04)',
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  cursor: 'pointer',
  fontWeight: 700,
  letterSpacing: '0.03em',
  justifyContent: 'flex-start',
});

const sidebarIconWrapStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
};

const pendingBadgeStyle = (isActive) => ({
  minWidth: 28,
  height: 28,
  borderRadius: 999,
  display: 'inline-grid',
  placeItems: 'center',
  fontSize: 12,
  fontWeight: 800,
  color: '#fff',
  background: isActive ? '#ff9d9d' : 'rgba(255, 255, 255, 0.18)',
  border: isActive ? '1px solid rgba(255, 185, 185, 0.9)' : '1px solid rgba(255, 255, 255, 0.2)',
  animation: isActive ? 'pendingPulse 1.1s ease-in-out infinite' : 'none',
  boxSizing: 'border-box',
  flexShrink: 0,
});

const featureCardStyle = {
  background: 'linear-gradient(180deg, rgba(20, 10, 10, 0.94) 0%, rgba(10, 10, 10, 0.96) 100%)',
  border: '1px solid rgba(255, 255, 255, 0.08)',
  borderRadius: 24,
  padding: 22,
  boxShadow: '0 12px 32px rgba(0,0,0,0.24)',
};

const featureCardButtonStyle = {
  ...featureCardStyle,
  display: 'block',
  width: '100%',
  textAlign: 'left',
  cursor: 'pointer',
  color: 'inherit',
  font: 'inherit',
};

const userActionButtonStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  borderRadius: 16,
  padding: '13px 14px',
  background: 'rgba(255, 255, 255, 0.05)',
  border: '1px solid rgba(255, 255, 255, 0.08)',
  color: '#f5f5f5',
  fontWeight: 600,
  cursor: 'pointer',
  width: '100%',
};

const userActionIconStyle = {
  width: 34,
  height: 34,
  borderRadius: 11,
  display: 'grid',
  placeItems: 'center',
  background: 'rgba(255, 77, 77, 0.12)',
  color: '#ff7a7a',
};

const newOrderButtonStyle = {
  border: 'none',
  borderRadius: 999,
  padding: '11px 16px',
  background: 'linear-gradient(90deg, #bf1f1f 0%, #ff4d4d 100%)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 8,
};

const kitchenButtonStyle = {
  border: '1px solid rgba(255,255,255,0.2)',
  borderRadius: 999,
  padding: '11px 16px',
  background: 'rgba(255,255,255,0.03)',
  color: '#fff',
  fontWeight: 700,
  cursor: 'pointer',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 8,
};

const liveNoticeStyle = {
  position: 'fixed',
  top: 18,
  right: 18,
  zIndex: 50,
  maxWidth: 'min(92vw, 420px)',
  borderRadius: 14,
  border: '1px solid rgba(82, 206, 123, 0.45)',
  background: 'rgba(19, 77, 37, 0.92)',
  color: '#e9fff0',
  padding: '12px 14px',
  fontWeight: 700,
  boxShadow: '0 14px 30px rgba(0, 0, 0, 0.34)',
};

const fallbackProducts = [
  { id: 'f1', nombre: 'Arepa reina pepiada', precio_venta: 6.5, categoria_nombre: 'Arepas' },
  { id: 'f2', nombre: 'Arepa pelua', precio_venta: 6.8, categoria_nombre: 'Arepas' },
  { id: 'f3', nombre: 'Arepa domino', precio_venta: 5.9, categoria_nombre: 'Arepas' },
  { id: 'f4', nombre: 'Cachapa con queso de mano', precio_venta: 7.2, categoria_nombre: 'Cachapas' },
  { id: 'f5', nombre: 'Cachapa con pernil BBQ', precio_venta: 8.9, categoria_nombre: 'Cachapas' },
  { id: 'f6', nombre: 'Pabellon criollo', precio_venta: 11.5, categoria_nombre: 'Platos' },
  { id: 'f7', nombre: 'Bowl criollo de pollo', precio_venta: 9.75, categoria_nombre: 'Platos' },
  { id: 'f8', nombre: 'Yuca con salsa rosada y tocineta', precio_venta: 7.4, categoria_nombre: 'Platos' },
  { id: 'f9', nombre: 'Arepa desayuno perico', precio_venta: 6.1, categoria_nombre: 'Desayunos' },
  { id: 'f10', nombre: 'Arepa sifrina', precio_venta: 7.8, categoria_nombre: 'Arepas' },
  { id: 'f11', nombre: 'Jugo de naranja natural', precio_venta: 3.8, categoria_nombre: 'Jugos' },
  { id: 'f12', nombre: 'Jugo de parchita', precio_venta: 4.2, categoria_nombre: 'Jugos' },
  { id: 'f13', nombre: 'Jugo de guanabana', precio_venta: 4.4, categoria_nombre: 'Jugos' },
  { id: 'f14', nombre: 'Jugo tropical mixto', precio_venta: 4.9, categoria_nombre: 'Jugos' },
  { id: 'f15', nombre: 'Cuba libre', precio_venta: 7.2, categoria_nombre: 'Licores' },
  { id: 'f16', nombre: 'Mojito clasico', precio_venta: 8.1, categoria_nombre: 'Licores' },
  { id: 'f17', nombre: 'Gin tonic citrico', precio_venta: 8.5, categoria_nombre: 'Licores' },
  { id: 'f18', nombre: 'Vodka tropical', precio_venta: 8.8, categoria_nombre: 'Licores' },
  { id: 'f19', nombre: 'Sangria tropical', precio_venta: 9.2, categoria_nombre: 'Licores' },
];

export default WelcomeScreen;

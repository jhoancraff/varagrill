import { useEffect, useState } from 'react';
import AuthForm from './components/AuthForm';
import ScreenShell from './components/ScreenShell';
import SplashScreen from './components/SplashScreen';
import WelcomeScreen from './components/WelcomeScreen';

function App() {
  const [showSplash, setShowSplash] = useState(true);
  const [checkingSession, setCheckingSession] = useState(true);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [isInstalled, setIsInstalled] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [welcomeName, setWelcomeName] = useState('');
  const [welcomeRole, setWelcomeRole] = useState('');

  useEffect(() => {
    const installedStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone;
    setIsInstalled(installedStandalone);

    const splashTimer = window.setTimeout(() => setShowSplash(false), 1200);

    const handleBeforeInstallPrompt = (event) => {
      event.preventDefault();
      setDeferredPrompt(event);
    };

    const handleAppInstalled = () => {
      setDeferredPrompt(null);
      setIsInstalled(true);
      setMessage('La app ya quedó instalada en tu dispositivo.');
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
    window.addEventListener('appinstalled', handleAppInstalled);

    return () => {
      window.clearTimeout(splashTimer);
      window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
      window.removeEventListener('appinstalled', handleAppInstalled);
    };
  }, []);

  useEffect(() => {
    const restoreSession = async () => {
      try {
        const response = await fetch('/api/auth/status/', {
          method: 'GET',
          credentials: 'include',
          cache: 'no-store',
        });

        if (!response.ok) {
          setIsLoggedIn(false);
          setWelcomeName('');
          setWelcomeRole('');
          return;
        }

        const data = await response.json();
        if (!data.authenticated) {
          setIsLoggedIn(false);
          setWelcomeName('');
          setWelcomeRole('');
          return;
        }

        const formattedName = (data.user?.username || '')
          .trim()
          .toLowerCase()
          .replace(/^(.)/, (match) => match.toUpperCase());

        setWelcomeName(formattedName || 'Usuario');
        setWelcomeRole(data.user?.role || '');
        setIsLoggedIn(true);
      } catch (error) {
        setIsLoggedIn(false);
        setWelcomeName('');
        setWelcomeRole('');
      } finally {
        setCheckingSession(false);
      }
    };

    restoreSession();
  }, []);

  const handleInstall = async () => {
    if (deferredPrompt) {
      deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      if (outcome === 'accepted') {
        setMessage('Instalación aceptada. La app abrirá en pantalla completa.');
      } else {
        setMessage('La instalación fue cancelada.');
      }
      setDeferredPrompt(null);
      return;
    }

    if (isInstalled) {
      setMessage('La app ya está instalada en este dispositivo.');
      return;
    }

    setMessage('Abre el menú del navegador y elige “Agregar a pantalla de inicio” o “Instalar app”.');
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setMessage('');

    try {
      const response = await fetch('/api/auth/login/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({ username, password }),
      });

      const data = await response.json();
      if (!response.ok) {
        setMessage('Advertencia: ha introducido mal las credenciales.');
        setPassword('');
        return;
      }

      const formattedName = (data.user.username || username)
        .trim()
        .toLowerCase()
        .replace(/^(.)/, (match) => match.toUpperCase());

      setIsLoggedIn(true);
      setWelcomeName(formattedName);
      setWelcomeRole(data.user?.role || '');
      setMessage(`Acceso concedido, bienvenido ${formattedName}.`);
      setPassword('');
      setUsername('');
    } catch (error) {
      setMessage('Advertencia: ha introducido mal las credenciales.');
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/auth/logout/', {
        method: 'GET',
        credentials: 'include',
      });

      if (!response.ok) {
        setMessage('No se pudo cerrar la sesión. Intenta nuevamente.');
        return;
      }
    } catch (error) {
      setMessage('No se pudo cerrar la sesión. Intenta nuevamente.');
      return;
    } finally {
      setLoading(false);
    }

    setIsLoggedIn(false);
    setWelcomeName('');
    setWelcomeRole('');
    setMessage('Sesion cerrada.');
    setPassword('');
    setUsername('');
  };

  if (showSplash || checkingSession) {
    return <SplashScreen />;
  }

  if (isLoggedIn) {
    return <WelcomeScreen name={welcomeName} role={welcomeRole} onBack={handleLogout} />;
  }

  return (
    <ScreenShell>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '4px 0 18px',
        color: '#f3b4b4',
        fontSize: 13,
      }}>
        <div style={{ fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase' }}>Varagrill</div>
        <div style={{ opacity: 0.75 }}>● Online</div>
      </div>
      <div style={{ textAlign: 'center', marginBottom: 24 }}>
        <div style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 72,
          height: 72,
          borderRadius: 24,
          background: 'linear-gradient(135deg, #bf1f1f 0%, #7a0d0d 100%)',
          boxShadow: '0 8px 20px rgba(191, 31, 31, 0.25)',
          marginBottom: 12,
          overflow: 'hidden',
        }}>
          <img src="/assets/varagrill-logo.jpg" alt="Varagrill logo" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        </div>
        <div style={{ fontSize: 34, fontWeight: 700, color: '#ff4d4d' }}>Varagrill</div>
        <div style={{ color: '#c8c8c8', marginTop: 8, fontSize: 15 }}>Control de cocina y servicio</div>
      </div>

      <AuthForm
        username={username}
        password={password}
        loading={loading}
        onUsernameChange={(event) => setUsername(event.target.value)}
        onPasswordChange={(event) => setPassword(event.target.value)}
        onSubmit={handleSubmit}
        message={message}
        isInstalled={isInstalled}
        onInstall={handleInstall}
      />

      <div style={{ marginTop: 18, color: '#9a9a9a', fontSize: 13, textAlign: 'center' }}>
        Usa las credenciales del usuario creado en Django para entrar. Si la app está instalada, se abrirá directamente en esta pantalla.
      </div>
    </ScreenShell>
  );
}

export default App;

import { useCallback, useEffect, useRef, useState } from 'react';

const AUDIO_PREFERENCE_KEY = 'varagrill.kitchenAudioUnlocked';

function readStoredPreference() {
  if (typeof window === 'undefined') {
    return false;
  }
  try {
    return window.localStorage.getItem(AUDIO_PREFERENCE_KEY) === '1';
  } catch (storageError) {
    return false;
  }
}

function writeStoredPreference(value) {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.localStorage.setItem(AUDIO_PREFERENCE_KEY, value ? '1' : '0');
  } catch (storageError) {
    // Ignore storage failures (e.g. private browsing quota).
  }
}

function useKitchenAlerts() {
  const [alertPermission, setAlertPermission] = useState('default');
  const [alertsEnabled, setAlertsEnabled] = useState(true);
  const [audioUnlocked, setAudioUnlocked] = useState(() => readStoredPreference());
  const [alertDiagnostics, setAlertDiagnostics] = useState('Pulsa “Prueba completa” para ver si el teléfono puede sonar.');
  const [alertMessage, setAlertMessage] = useState(
    readStoredPreference()
      ? 'Sonido activado en este dispositivo.'
      : 'Toca en cualquier parte de la pantalla o presiona “Probar sonido” para activar el aviso.',
  );

  const audioContextRef = useRef(null);
  const audioReadyRef = useRef(false);
  const pendingAlertSoundRef = useRef(false);
  const lastAlertAtRef = useRef(0);

  const playAlertTone = useCallback((audioContext) => {
    if (!audioContext) {
      return;
    }

    const now = audioContext.currentTime;
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();

    oscillator.type = 'triangle';
    oscillator.frequency.setValueAtTime(880, now);
    oscillator.frequency.exponentialRampToValueAtTime(1280, now + 0.16);

    gainNode.gain.setValueAtTime(0.0001, now);
    gainNode.gain.exponentialRampToValueAtTime(0.24, now + 0.02);
    gainNode.gain.exponentialRampToValueAtTime(0.0001, now + 0.45);

    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);

    oscillator.start(now);
    oscillator.stop(now + 0.48);
  }, []);

  const ensureAudioContext = useCallback(() => {
    if (typeof window === 'undefined') {
      return null;
    }

    const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextCtor) {
      return null;
    }

    if (!audioContextRef.current) {
      audioContextRef.current = new AudioContextCtor();
    }

    return audioContextRef.current;
  }, []);

  const tryResumeAudioContext = useCallback(async () => {
    const audioContext = ensureAudioContext();
    if (!audioContext) {
      return false;
    }

    if (audioContext.state === 'suspended') {
      try {
        await audioContext.resume();
      } catch (resumeError) {
        // Browser refused to resume without a fresh user gesture; caller will retry later.
      }
    }

    audioReadyRef.current = audioContext.state === 'running';
    if (audioReadyRef.current && pendingAlertSoundRef.current) {
      pendingAlertSoundRef.current = false;
      // Reproducir el aviso pendiente en cuanto el navegador deje salir audio.
      playAlertTone(audioContext);
    }
    return audioReadyRef.current;
  }, [ensureAudioContext, playAlertTone]);

  useEffect(() => {
    if (typeof window !== 'undefined' && 'Notification' in window) {
      const permission = Notification.permission;
      setAlertPermission(permission);
      setAlertsEnabled(permission !== 'denied');
    }
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return undefined;
    }

    let done = false;
    const armOnFirstGesture = () => {
      if (done) {
        return;
      }
      done = true;
      tryResumeAudioContext();
      window.removeEventListener('pointerdown', armOnFirstGesture, true);
      window.removeEventListener('keydown', armOnFirstGesture, true);
      window.removeEventListener('touchend', armOnFirstGesture, true);
    };

    window.addEventListener('pointerdown', armOnFirstGesture, { once: true, capture: true });
    window.addEventListener('keydown', armOnFirstGesture, { once: true, capture: true });
    window.addEventListener('touchend', armOnFirstGesture, { once: true, capture: true });

    return () => {
      window.removeEventListener('pointerdown', armOnFirstGesture, true);
      window.removeEventListener('keydown', armOnFirstGesture, true);
      window.removeEventListener('touchend', armOnFirstGesture, true);
    };
  }, [tryResumeAudioContext]);

  const playKitchenAlertSound = useCallback(() => {
    // Sound only needs the AudioContext unlocked by a user gesture - it has
    // nothing to do with the browser's Notification permission, so it must
    // not be gated by `alertsEnabled` (that only reflects notification access).
    const audioContext = ensureAudioContext();
    if (!audioContext || !audioReadyRef.current) {
      pendingAlertSoundRef.current = true;
      void tryResumeAudioContext();
      return;
    }

    playAlertTone(audioContext);
  }, [ensureAudioContext, playAlertTone, tryResumeAudioContext]);

  const showKitchenNotification = useCallback((title, body, options = {}) => {
    if (typeof window === 'undefined' || !('Notification' in window)) {
      return;
    }

    if (alertPermission !== 'granted') {
      return;
    }

    if (!options.force && document.visibilityState === 'visible') {
      return;
    }

    new Notification(title, {
      body,
      icon: '/assets/varagrill-logo.jpg',
      tag: 'kitchen-order-alert',
      renotify: true,
    });
  }, [alertPermission]);

  const buildAlertDiagnostics = useCallback((audioReady, notificationPermission) => {
    const audioState = audioReady ? 'Audio listo' : (audioUnlocked ? 'Audio esperando un toque' : 'Audio bloqueado');
    const notificationState = typeof window === 'undefined' || !('Notification' in window)
      ? 'Notificaciones no soportadas'
      : notificationPermission === 'granted'
        ? 'Notificaciones activas'
        : notificationPermission === 'denied'
          ? 'Notificaciones bloqueadas'
          : 'Notificaciones sin permiso';
    const vibrationState = typeof navigator !== 'undefined' && 'vibrate' in navigator ? 'Vibración disponible' : 'Sin vibración';

    return `${audioState} · ${notificationState} · ${vibrationState}`;
  }, [audioUnlocked]);

  const triggerKitchenAlert = useCallback((title, body) => {
    const now = Date.now();
    if (now - lastAlertAtRef.current < 4000) {
      return;
    }

    lastAlertAtRef.current = now;
    playKitchenAlertSound();
    showKitchenNotification(title, body);

    if (typeof navigator !== 'undefined' && 'vibrate' in navigator) {
      navigator.vibrate([140, 60, 140]);
    }
  }, [playKitchenAlertSound, showKitchenNotification]);

  const runAlertDiagnostics = useCallback(async () => {
    const audioReady = await tryResumeAudioContext();
    const notificationSupported = typeof window !== 'undefined' && 'Notification' in window;
    let nextPermission = alertPermission;

    if (notificationSupported && Notification.permission === 'default') {
      nextPermission = await Notification.requestPermission();
      setAlertPermission(nextPermission);
      setAlertsEnabled(nextPermission !== 'denied');
    }

    if (audioReady) {
      playKitchenAlertSound();
    }

    if (typeof navigator !== 'undefined' && 'vibrate' in navigator) {
      navigator.vibrate([120, 60, 120]);
    }

    if (notificationSupported && nextPermission === 'granted') {
      showKitchenNotification('Alerta de prueba', 'Pedido #PRUEBA · Mesa Test', { force: true });
    }

    setAlertDiagnostics(buildAlertDiagnostics(audioReady, nextPermission));
    setAlertMessage(audioReady
      ? 'Prueba completa ejecutada. Revisa si el teléfono vibró, sonó o mostró una notificación.'
      : 'La prueba no pudo abrir el audio todavía. Toca otra parte de la pantalla y vuelve a intentar.');
  }, [alertPermission, buildAlertDiagnostics, playKitchenAlertSound, showKitchenNotification, tryResumeAudioContext]);

  const unlockAudioAndTest = useCallback(async () => {
    const audioReady = await tryResumeAudioContext();

    writeStoredPreference(true);
    setAudioUnlocked(true);
    setAlertMessage('Sonido desbloqueado. El aviso sonará cuando llegue una nueva orden.');
    if (audioReady) {
      playKitchenAlertSound();
    }

    if (typeof window !== 'undefined' && 'Notification' in window && Notification.permission === 'default') {
      const permission = await Notification.requestPermission();
      setAlertPermission(permission);
      setAlertsEnabled(permission !== 'denied');
      if (permission === 'granted') {
        setAlertMessage('Sonido desbloqueado y notificaciones activadas.');
      }
    }
  }, [playKitchenAlertSound, tryResumeAudioContext]);

  const requestAlertPermission = useCallback(async () => {
    if (typeof window === 'undefined' || !('Notification' in window)) {
      return;
    }

    const permission = await Notification.requestPermission();
    setAlertPermission(permission);
    setAlertsEnabled(permission !== 'denied');
    setAlertMessage(permission === 'granted' ? 'Notificaciones activadas.' : 'Las notificaciones están bloqueadas en este navegador.');
  }, []);

  return {
    alertPermission,
    alertsEnabled,
    audioUnlocked,
    alertDiagnostics,
    alertMessage,
    triggerKitchenAlert,
    runAlertDiagnostics,
    unlockAudioAndTest,
    requestAlertPermission,
  };
}

export default useKitchenAlerts;

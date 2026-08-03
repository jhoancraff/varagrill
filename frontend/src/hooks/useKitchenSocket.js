import { useEffect, useRef, useState } from 'react';

function resolveSocketUrl(pathOrUrl) {
  if (pathOrUrl.startsWith('ws://') || pathOrUrl.startsWith('wss://')) {
    return pathOrUrl;
  }

  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const normalizedPath = pathOrUrl.startsWith('/') ? pathOrUrl : `/${pathOrUrl}`;
  return `${protocol}://${window.location.host}${normalizedPath}`;
}

function useKitchenSocket({
  socketPath = '/ws/pedidos/',
  onEvent,
  reconnectMs = 3000,
  enabled = true,
}) {
  const [isConnected, setIsConnected] = useState(false);
  const onEventRef = useRef(onEvent);

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    let socket;
    let reconnectTimer = null;
    let disposed = false;

    const connect = () => {
      socket = new WebSocket(resolveSocketUrl(socketPath));

      socket.onopen = () => {
        setIsConnected(true);
      };

      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          const eventName = String(message?.event || message?.payload?.event || '').toUpperCase();

          if (onEventRef.current) {
            onEventRef.current({
              ...message,
              event: eventName,
            });
          }
        } catch (error) {
          // Ignore malformed messages and keep the socket alive.
        }
      };

      socket.onclose = () => {
        setIsConnected(false);

        if (!disposed) {
          reconnectTimer = window.setTimeout(connect, reconnectMs);
        }
      };

      socket.onerror = () => {
        setIsConnected(false);
      };
    };

    connect();

    return () => {
      disposed = true;
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.close();
      }
    };
  }, [enabled, reconnectMs, socketPath]);

  return { isConnected };
}

export default useKitchenSocket;

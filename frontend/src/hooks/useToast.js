import { useCallback, useEffect, useRef, useState } from 'react';

const DEFAULT_DURATION = 4500;

function useToast(duration = DEFAULT_DURATION) {
  const [toast, setToast] = useState(null);
  const timeoutRef = useRef(null);

  useEffect(() => () => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
  }, []);

  const hideToast = useCallback(() => {
    setToast(null);
  }, []);

  const showToast = useCallback((message, type = 'success', options = {}) => {
    if (!message) {
      return;
    }
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    setToast({ id: Date.now(), type, message, action: options.action || null });
    timeoutRef.current = setTimeout(() => setToast(null), duration);
  }, [duration]);

  const showSuccess = useCallback((message, options) => showToast(message, 'success', options), [showToast]);
  const showError = useCallback((message, options) => showToast(message, 'error', options), [showToast]);

  return { toast, showToast, showSuccess, showError, hideToast };
}

export default useToast;

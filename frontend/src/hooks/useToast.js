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

  const showToast = useCallback((message, type = 'success') => {
    if (!message) {
      return;
    }
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    setToast({ id: Date.now(), type, message });
    timeoutRef.current = setTimeout(() => setToast(null), duration);
  }, [duration]);

  const showSuccess = useCallback((message) => showToast(message, 'success'), [showToast]);
  const showError = useCallback((message) => showToast(message, 'error'), [showToast]);

  return { toast, showToast, showSuccess, showError, hideToast };
}

export default useToast;

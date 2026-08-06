import { useEffect, useState } from 'react';

const CLIENT_CACHE_MS = 5 * 60 * 1000;

let cachedRate = null;
let cachedAt = 0;
let inflightPromise = null;

function fetchTasaCambio() {
  const now = Date.now();
  if (cachedRate !== null && now - cachedAt < CLIENT_CACHE_MS) {
    return Promise.resolve(cachedRate);
  }
  if (inflightPromise) {
    return inflightPromise;
  }

  inflightPromise = fetch('/api/tasa-cambio/', { credentials: 'include', cache: 'no-store' })
    .then((response) => (response.ok ? response.json() : null))
    .then((data) => {
      if (data && data.ok) {
        cachedRate = Number(data.tasa);
        cachedAt = Date.now();
      }
      return cachedRate;
    })
    .catch(() => cachedRate)
    .finally(() => {
      inflightPromise = null;
    });

  return inflightPromise;
}

/** Tasa BCV (Bs. por USD) vigente, o null mientras carga / si no está disponible. */
export default function useExchangeRate() {
  const [tasa, setTasa] = useState(cachedRate);

  useEffect(() => {
    let active = true;
    fetchTasaCambio().then((value) => {
      if (active) {
        setTasa(value);
      }
    });
    return () => {
      active = false;
    };
  }, []);

  return tasa;
}
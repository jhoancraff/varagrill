# Varagrill frontend

## Requisitos
- Node.js y npm

## Instalar dependencias
```bash
cd frontend
npm install
```

## Ejecutar
```bash
npm run dev
```

La app se abrirá en http://localhost:3000.

## Variables de entorno
Define la URL base de tu API en `frontend/.env`:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Si no está definida, el frontend usa una URL local basada en el host actual.

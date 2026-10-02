# FourMind — Frontend (React)

Carpeta reservada para la interfaz. Aún no se inicializa el proyecto de React
(le toca a Lupita en su rama `feature/frontend-setup`).

## Para inicializarlo (con Vite, recomendado)

```bash
cd frontend
npm create vite@latest . -- --template react
npm install
npm run dev
```

## Conexión con el backend

La API vive en `http://127.0.0.1:8000/api/` durante desarrollo local.
Prueba rápida de conexión una vez inicializado el proyecto:

```js
fetch("http://127.0.0.1:8000/api/health/")
  .then(r => r.json())
  .then(console.log);
```

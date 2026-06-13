# DRIFT Frontend

React 18, TypeScript, Vite, Tailwind CSS, Leaflet, Zustand, and React Query.

The production image is built from the repository root because the build also
uses contract examples:

```powershell
docker compose build frontend
docker compose up -d frontend
```

For local Vite development with Node.js installed:

```powershell
cd frontend
npm ci
npm run dev
```

Environment variables:

```env
VITE_USE_MOCK=false
VITE_API_BASE_URL=http://localhost:8000
```

The GMS API key is intentionally not a frontend variable. Chat requests go to
the Django `/api/v1/chat/` endpoint so the key remains on the server.

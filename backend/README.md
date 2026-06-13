# DRIFT Backend

Django 5 and Django REST Framework provide synchronous prediction, briefing,
risk forecast, health, and GMS chat endpoints.

The backend is normally run through Docker Compose:

```powershell
docker compose up -d postgres redis backend
docker compose logs -f backend
```

Important boundaries:

- API payloads use models from `contracts/`.
- Runtime engine selection is isolated in `apps/sar/engine_interface.py`.
- Live marine API clients belong in `backend/integrations/`.
- Historical data providers belong in `engine/drift_engine/data_sources/`.
- GMS credentials are read from backend environment variables only.

Run backend and engine tests with:

```powershell
docker compose -f docker-compose.test.yml run --rm test
```

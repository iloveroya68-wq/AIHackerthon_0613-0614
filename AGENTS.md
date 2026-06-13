# DRIFT Agent Handoff

This file is the operational handoff for agents modifying or deploying this repository.

## Project Purpose

DRIFT is a maritime search-and-rescue decision-support demo.

```text
L1: current + wind + vessel leeway physics
L2: OpenDrift particle simulation and probability search zones
L3: LightGBM residual correction
L4: structured demo briefing plus GMS OpenAI-compatible incident chat
```

L3 currently uses a synthetic demo dataset. It proves the training, artifact loading, and
inference pipeline, but it must not be presented as validated real-world SAR accuracy.

## Demo Assets

The private repository includes the current demo assets so another environment can run the
same scenario after cloning with Git LFS enabled:

- `data/modeling_inputs/`: local CMEMS, KHOA, leeway, and land-mask bundle
- `.env`: demo-only runtime configuration; replace it before any public/production deployment
- `engine/artifacts/l3_correction.joblib`: generated LightGBM demo model
- `engine/artifacts/model_metadata.json`: generated model metadata

Large CMEMS files and the LightGBM binary are stored with Git LFS. Run `git lfs pull` after
cloning if they were not downloaded automatically.

Historical data coverage currently used by the demo:

- CMEMS time range: `2022-03-24` through `2024-03-24`
- Approximate area: latitude `34.0-34.8333`, longitude `125.0-126.4167`
- Known demo input: longitude `126.2`, latitude `34.5`, time `2023-09-23 12:00 KST`

## Main Runtime Flow

1. React sends `POST /api/v1/predictions/`.
2. Django selects `RealDriftEngine`.
3. Historical mode uses `HistoricalBundleProvider`; live mode injects the backend's
   `PublicMarineEnvironmentProvider` for KMA/KHOA HTTP calls.
4. L1 calculates the deterministic drift vector.
5. L2 runs OpenDrift particles.
6. The land mask filters particles and clips search zones.
7. L3 predicts east/north residual metres and corrects the L2 center.
8. The engine returns hourly centers and 60/80/95 percent search zones.

Relevant code:

- `backend/integrations/public_marine_data.py`
- `backend/apps/sar/engine_interface.py`
- `engine/drift_engine/engine.py`
- `engine/drift_engine/data_sources/`
- `engine/drift_engine/l1_physics.py`
- `engine/drift_engine/l2_monte_carlo.py`
- `engine/drift_engine/l3_correction.py`
- `frontend/src/map/LeafletMap.tsx`

## Data-Source Extension

Keep new data integrations behind the existing interfaces:

- Live API clients belong in `backend/integrations/` and implement `EnvironmentProvider`.
- Historical/file providers belong in `engine/drift_engine/data_sources/`.
- Vessel drift coefficient: extend or replace `LeewayCatalog`
- Coastline filtering: extend or replace `LandMask`
- Construct implementations in `data_sources/factory.py`

Do not couple new APIs directly into L1, L2, or L3.

## Demo Model

Generate the persistent synthetic LightGBM artifact:

```bash
docker compose -f docker-compose.test.yml run --rm demo-train
```

This creates a 2,000-record synthetic dataset and stores:

```text
engine/artifacts/l3_correction.joblib
engine/artifacts/model_metadata.json
```

Verify the complete CMEMS + KHOA + OpenDrift + LightGBM pipeline:

```bash
docker compose -f docker-compose.test.yml run --rm demo-smoke
```

Expected output includes:

```text
"l3_correction_applied": true
"similar_incidents_count": 2000
```

The current synthetic targets are east/north correction distances generated from wind and
current components plus injected noise. This is synthetic residual learning, not a model
trained from actual discovered-person coordinates.

## Tests

Run the main Docker test suite:

```bash
docker compose -f docker-compose.test.yml run --rm test
```

The latest verified result was `31 passed`.

Additional checks:

```bash
docker compose -f docker-compose.test.yml run --rm test-opendrift
docker compose -f docker-compose.test.yml run --rm train-smoke
```

## Local Demo

Required `.env` values:

```env
DRIFT_ENGINE=real
DRIFT_L2_ENGINE=opendrift
DRIFT_DATA_SOURCE=historical
DRIFT_DATA_ROOT=/data/modeling_inputs
DRIFT_DATA_HOST_PATH=./data/modeling_inputs
DRIFT_MODEL_PATH=/engine/artifacts/l3_correction.joblib
DRIFT_MODEL_METADATA_PATH=/engine/artifacts/model_metadata.json
ENGINE_L3_MIN_TRAINING_RECORDS=30
```

Start the synchronous demo services:

```bash
docker compose up -d postgres redis backend frontend
```

Open `http://localhost:5173`.

The default frontend input is set to the known historical demo coordinate and time. The map
draws larger zones first so hover labels resolve correctly as priority 3, then 2, then 1.

## EC2 Deployment

Recommended minimum for the current OpenDrift image is an Ubuntu EC2 instance with at least
4 GB RAM and enough disk space for Docker images and the local data bundle.

Prepare on the server:

1. Clone the repository.
2. Run `git lfs pull` to download the modeling data and model artifact.
3. Replace the committed demo `.env` with production credentials and settings.
4. Optionally run `demo-train` to regenerate the synthetic model.
5. Open security-group ports `22` and `80` only.

Production `.env` must include:

```env
DEBUG=False
DJANGO_ALLOWED_HOSTS=<EC2_PUBLIC_IP_OR_DOMAIN>
DJANGO_SECRET_KEY=<LONG_RANDOM_VALUE>
POSTGRES_PASSWORD=<STRONG_PASSWORD>
```

Deploy:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

The production override exposes nginx on port 80 and keeps Django, PostgreSQL, and Redis
internal. The current API is synchronous and does not include a Celery worker.

## Known Limitations

- L3 is synthetic and not operationally validated.
- Historical predictions must remain inside the bundled CMEMS time and coordinate range.
- L2 currently applies the current/wind sampled for the request as simulation forcing; it
  does not yet attach the full time-varying CMEMS grid as an OpenDrift reader.
- The structured L4 briefing endpoint remains a demo provider; interactive chat uses GMS.
- Some older repository text may display mojibake due to pre-existing encoding damage.

## Editing Safety

- The worktree may contain user/team changes. Never reset or restore unrelated files.
- Do not replace the committed demo `.env` with real credentials in Git history.
- Keep large data and model binaries under Git LFS tracking.
- Preserve the contract models in `contracts/` when changing backend/frontend payloads.

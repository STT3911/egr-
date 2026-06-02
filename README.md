# EGR Service

EGR Service is a FastAPI/PostgreSQL service with a React frontend for Belarus company dossiers and related public registries.

The project keeps application code, import logic, source snapshots, and operational scripts in separate places so deploys and repeated imports stay predictable.

## Repository Layout

```text
app/                 Backend application: API, DB models, services, tasks.
frontend/            React/Vite frontend.
migrations/          Alembic migrations.
scripts/             Operational scripts and compatibility entrypoints.
scripts/imports/     Import and snapshot commands.
scripts/legacy/      Old one-off scripts kept behind compatibility wrappers.
scripts/deploy/      Deployment/SSL helper scripts.
scripts/sql/         Manual and bootstrap SQL helpers.
docs/                Detailed documentation and historical notes.
data/imports/        Source snapshots and operator-provided import files.
reference_tables/    Reference-table bootstrap helpers.
tests/               Python tests.
nginx/               Nginx configs.
```

Root-level legacy files such as `Start.py`, `auto-import-data.py`, and `scripts/import_*.py` are compatibility wrappers. Prefer the organized paths under `scripts/` for new work.

## Main Data Sources

The profile endpoint can include linked records from:

- EGR company data;
- GRP taxpayer data;
- tax debt records;
- GIAS accredited customers and locked suppliers;
- MАРТ trade registry;
- license.gov.by licenses;
- park.by residents;
- EAEU SEZ residents;
- bankruptcy cases;
- scheduled inspection plans;
- BelTPP own-production certificates.

## Local Development

Install backend dependencies:

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

Install frontend dependencies:

```bash
npm --prefix frontend install
```

Run with Docker Compose:

```bash
docker compose up -d db redis
docker compose run --rm egr-api alembic upgrade head
docker compose up -d egr-api frontend
```

Build frontend:

```bash
npm --prefix frontend run build
```

## Deployment

Typical server deploy:

```bash
cd ~/egr
git pull
docker compose build egr-api frontend
docker compose up -d egr-api frontend
docker compose run --rm egr-api alembic upgrade head
```

If only migrations changed, running `alembic upgrade head` is enough after the backend image/code is updated.

## Imports and Snapshots

Keep raw import inputs and fetched snapshots under `data/imports/`. Prefer date-stamped filenames for repeatability.

### BelTPP Own-Production Certificates

Fetch all cci.by pages into JSON:

```bash
docker compose run --rm egr-api python scripts/imports/import_belltpp_own_certificates.py fetch \
  --delay 0.5 \
  --output /app/data/imports/belltpp_own_certificates/belltpp_own_certificates_$(date +%Y%m%d).json
```

Import a saved JSON snapshot:

```bash
docker compose run --rm egr-api python scripts/imports/import_belltpp_own_certificates.py import \
  /app/data/imports/belltpp_own_certificates/belltpp_own_certificates_YYYYMMDD.json
```

Fetch and import in one command:

```bash
docker compose run --rm egr-api python scripts/imports/import_belltpp_own_certificates.py sync \
  --delay 0.5 \
  --output /app/data/imports/belltpp_own_certificates/belltpp_own_certificates_$(date +%Y%m%d).json
```

### Scheduled Inspection Plans

Put Excel files under `data/imports/inspection_plan/`, then run:

```bash
docker compose run --rm egr-api python scripts/imports/import_inspection_plan.py \
  /app/data/imports/inspection_plan
```

### Trade Registry

```bash
docker compose run --rm egr-api python scripts/imports/import_trade_registry_csv.py \
  /app/data/imports/trade_registry/trade_registry.csv
```

## Checks

Backend syntax check:

```bash
python -m py_compile app/**/*.py scripts/**/*.py
```

Frontend build:

```bash
npm --prefix frontend run build
```

Service status:

```bash
docker compose ps
docker compose logs --tail=50 egr-api
docker compose logs --tail=50 frontend
```

## Notes

- Source snapshots in `data/imports/` are operational artifacts and are ignored by Git.
- Large local backups in `backups/` are not part of the app source tree.
- Historical root README content was moved to `docs/legacy-readme.md`.

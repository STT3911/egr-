# EGR Service

EGR Service is a FastAPI/PostgreSQL service with a React frontend for Belarus company dossiers and related public registries.

The project keeps application code, import logic, source snapshots, and operational scripts in separate places so deploys and repeated imports stay predictable.

## Repository Layout

```text
app/                 Backend application: API, DB models, services, tasks.
frontend/            React/Vite frontend.
migrations/          Alembic migrations.
scripts/             Operational scripts.
scripts/imports/     Import and snapshot commands.
scripts/legacy/      Old one-off scripts.
scripts/deploy/      Deployment/SSL helper scripts.
scripts/sql/         Manual and bootstrap SQL helpers.
docs/                Detailed documentation and historical notes.
data/imports/        Source snapshots and operator-provided import files.
reference_tables/    Reference-table bootstrap helpers.
tests/               Python tests.
nginx/               Nginx configs.
```

## Main Data Sources

The profile endpoint can include linked records from:

- EGR company data;
- GRP taxpayer data;
- tax debt records;
- GIAS accredited customers, locked suppliers, and public contracts;
- MАРТ trade registry;
- license.gov.by licenses;
- park.by residents;
- EAEU SEZ residents;
- bankruptcy cases;
- scheduled inspection plans;
- BelTPP own-production certificates.

Bankrot.gov.by release materials:

- [`docs/BANKROT.md`](docs/BANKROT.md) — collected datasets and API architecture;
- [`docs/BANKROT_RUNBOOK.md`](docs/BANKROT_RUNBOOK.md) — deployment, diagnostics, and recovery;
- [`docs/RELEASE_REPORT_2026-07-20.md`](docs/RELEASE_REPORT_2026-07-20.md) — release report and demo scenario;
### API access policy

- Company data and other read-only `GET` endpoints are available without `X-API-Key`.
- Administrative operations (`sync`, `reindex`, `parse`) require `X-API-Key`.
- `force_refresh=true` also requires `X-API-Key` because it updates stored data.

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

## Autonomous UNP Pipeline

The `egr-unp-pipeline` service continuously:

1. marks all known checksum-valid UNPs in `unp_scan_candidates`;
2. infers dense issuance islands in `unp_issuance_ranges`;
3. records each planned candidate before making an HTTP request;
4. requests every missing source independently from EGR and GRP;
5. records source statuses and attempts in the candidate registry;
6. persists and parses successful EGR and GRP responses.

Prepare and inspect the registry without starting external enumeration:

```bash
docker compose run --rm egr-api alembic upgrade head
docker compose run --rm egr-api \
  python /app/scripts/unp_enumerate.py --prepare-only
docker compose run --rm egr-api \
  python /app/scripts/unp_enumerate.py --registry-status
```

This preparation does not generate roughly 64 million empty rows. It stores
known UNPs, detects the actual dense issuance ranges, and creates pending
checksum-valid candidates for every latest regional frontier window. The
scanner also records any additional candidate before it is checked.

Build and start it once:

```bash
docker compose build egr-unp-pipeline
docker compose up -d egr-unp-pipeline
```

Inspect status and logs:

```bash
docker exec egr_unp_pipeline python -m app.workers.unp_pipeline --status
docker compose logs -f egr-unp-pipeline
```

Stop it gracefully:

```bash
docker compose stop -t 30 egr-unp-pipeline
```

The service resumes from `data/unp_enumerate_checkpoint.json`. Set
`UNP_PIPELINE_EMPTY_STOP=0` in `.env` only when a complete region-wide scan is
required together with `UNP_PIPELINE_SCAN_MODE=full`.

The default `frontier` mode scans only the latest narrow issuance window in
each region. Each pass is stored in `unp_range_scan_runs` with its cycle number,
source and scan boundaries, next sequence, first and last externally checked
UNP, counters and completion status. Confirmed misses and partial source hits
are stored in `unp_scan_candidates` and are not requested again until their
`next_check_at` deadline. The registry/range map is rebuilt on the separate
registry refresh interval; completed frontier cycles are separated by the
frontier interval.

```dotenv
UNP_PIPELINE_SCAN_MODE=frontier
UNP_PIPELINE_FRONTIER_LOOKAHEAD=50
UNP_PIPELINE_FRONTIER_BACKTRACK=50
UNP_PIPELINE_RANGE_GAP=50
UNP_PIPELINE_REGISTRY_REFRESH_INTERVAL_SECONDS=86400
UNP_PIPELINE_FRONTIER_INTERVAL_SECONDS=300
UNP_PIPELINE_NOT_FOUND_RECHECK_SECONDS=86400
UNP_PIPELINE_PARTIAL_RECHECK_SECONDS=86400
UNP_PIPELINE_ERROR_RECHECK_SECONDS=300
UNP_PIPELINE_CANDIDATE_BATCH=500
```

`UNP_PIPELINE_CANDIDATE_BATCH` controls only the local database-presence
lookup. External EGR/GRP requests still obey `UNP_PIPELINE_CONCURRENCY` and
`UNP_PIPELINE_DELAY`.
The expensive full `gov_organizations` rebuild is disabled in the continuous
pipeline by default. Run it manually during a maintenance window:

```bash
docker exec egr_api python -c \
  "from app.services.gov_organizations import rebuild; print(rebuild())"
```

To enable an automatic rebuild after new data, set
`UNP_PIPELINE_GOV_REBUILD_ENABLED=true`; the default interval is 86,400 seconds.

## Parser Telegram Alerts

Parser failures and retries are sent immediately. Routine `egr-unp-pipeline`
progress is sent twice per day through the same operational Telegram channel.

Configure `.env`:

```dotenv
ALERT_TELEGRAM_BOT_TOKEN=123456:telegram-bot-token
ALERT_TELEGRAM_CHAT_ID=-1001234567890
PARSER_ALERTS_ENABLED=true
PARSER_ALERTS_NOTIFY_START=false
PARSER_ALERTS_NOTIFY_SUCCESS=false
PARSER_ALERTS_PROGRESS_INTERVAL_SECONDS=43200
```

After changing these values, recreate the parser containers so they receive
the environment:

```bash
docker compose up -d --build --force-recreate \
  egr-celery-worker egr-celery-worker-heavy egr-celery-worker-bankrot \
  egr-celery-beat egr-unp-pipeline
```

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

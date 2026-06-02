# Scripts layout

Top-level scripts are kept as stable compatibility entrypoints for existing deploy commands.
New import and snapshot commands live in `scripts/imports/`.

## Import and snapshot commands

- `scripts/imports/import_belltpp_own_certificates.py`
  - `fetch`: save cci.by BelTPP own-production certificates to JSON.
  - `import`: import a saved JSON snapshot into PostgreSQL.
  - `sync`: fetch JSON and import it in one run.
- `scripts/imports/import_inspection_plan.py`
  - import scheduled inspection plan Excel files from a file or directory.
- `scripts/imports/import_trade_registry_csv.py`
  - import MART trade registry CSV.
- `scripts/imports/import_licenses.py`
  - import license.gov.by JSON snapshots.
- `scripts/imports/import_eaeu_sez_residents.py`
  - import EAEU SEZ resident snapshots.
- `scripts/imports/import_park_residents_catalog.py`
  - import park.by resident catalog snapshots.

Compatibility wrappers remain at `scripts/import_*.py`, so older commands keep working.

## Source fetchers

Fetcher-only scripts stay at the top level for now:

- `fetch_eaeu_sez_residents.py`
- `fetch_licenses.py`
- `fetch_park_residents_catalog.py`

## Checks and maintenance

- `check_*.py` and `check-*.sh` are operational checks.
- `run_*.py`, `run-*.sh`, `parse_*.py`, `load_*.py`, `fill_*.py`, and `reindex_*.py` are maintenance/manual operations.
- Old one-off scripts live in `scripts/legacy/`.
- Deployment helpers live in `scripts/deploy/`.
- SQL helpers live in `scripts/sql/`.
- Bootstrap and monitoring assets live in `scripts/init/` and `scripts/monitoring/`.

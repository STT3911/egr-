# Import Data Layout

`data/imports/` stores source snapshots and operator-provided import files. These files are operational artifacts and are intentionally ignored by Git.

Recommended layout:

```text
data/imports/
  belltpp_own_certificates/   JSON snapshots from cci.by BelTPP registry.
  inspection_plan/            Excel files for scheduled inspection plans.
  locked_suppliers/           GIAS locked supplier snapshots.
  trade_registry/             MART trade registry CSV files and reports.
  reports/                    generated import/check reports.
  manual/                     temporary/manual operator-provided files.
```

Use date-stamped snapshot names when the source can change:

```text
data/imports/belltpp_own_certificates/belltpp_own_certificates_20260602.json
```

When importing into Docker containers, host path `~/egr/data/imports/...` maps to `/app/data/imports/...`.

# Development and production workflow

The service has two environments and two long-lived branches:

- `develop` is deployed to `https://test.tendex.by`.
- `main` is deployed to `https://company.tenders.by`.

The environments use different API/frontend containers, PostgreSQL databases,
Redis instances, networks, and volumes. The lightweight dev stack deliberately
does not run Celery Beat, background synchronizers, Telegram, Grafana, or a
second Elasticsearch JVM. This prevents test code from triggering production
jobs and keeps the server within its memory limit.

## Make a change

Start from an up-to-date `develop` branch. A short-lived feature branch is
recommended when a change is larger than one small fix.

```bash
git switch develop
git pull --ff-only origin develop
git switch -c feature/<short-name>
```

Do not edit application source directly on a production server. Secrets and
environment-specific values belong in the server `.env` file and must not be
committed.

## Test a change

Run backend tests from the repository root:

```bash
python -m pytest -q
```

Run frontend checks from `frontend/`:

```bash
npm ci
npm run typecheck
npm test
npm run build
```

The same checks run in GitHub Actions for pushes and pull requests targeting
`develop` or `main`. After they pass, deploy `develop` from the dedicated
`~/egr-dev` worktree:

```bash
cd ~/egr-dev
./scripts/deploy-dev.sh
```

The file `~/egr-dev/.env.dev` is server-local and ignored by Git. Start from
`deploy/dev/.env.example`, replace both placeholder secrets, and never reuse the
production database volume.

## Promote to production

1. Merge the tested feature branch into `develop`.
2. Verify the `develop` CI run and the development environment.
3. Open and merge a pull request from `develop` into `main`.
4. Deploy the resulting `main` commit to production.

The production checkout must have no tracked local changes before deployment:

```bash
cd ~/egr
./scripts/deploy-prod.sh
```

Rebuild or restart any worker whose code or environment changed. After the
deployment, verify container health, the relevant API endpoint, and application
logs. Never use `git add .` on production; server-only exports and credentials
must remain outside commits.

## TLS certificates

The Nginx certificate must contain both public names. HTTP ACME challenges are
served from `acme-webroot/`, which is mounted read-only into Nginx. Issue or
expand the certificate with:

```bash
cd ~/egr
./scripts/issue-certificates.sh
```

Renew it from the server user's cron with `scripts/renew-certificates.sh`.
Certificate files are copied into the ignored `ssl/` directory and Nginx is
validated before it is reloaded.

## Emergency production fix

If a production-only emergency edit is unavoidable, reproduce it immediately
on a branch from `develop`, test it, and promote it through `main`. The server
must then be returned to the exact `origin/main` revision so the next deployment
is reproducible.

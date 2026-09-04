# Development and production workflow

The repository uses two long-lived branches:

- `develop` is the integration branch for development and testing.
- `main` is the production branch. Production servers deploy only this branch.

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
`develop` or `main`.

## Promote to production

1. Merge the tested feature branch into `develop`.
2. Verify the `develop` CI run and the development environment.
3. Open and merge a pull request from `develop` into `main`.
4. Deploy the resulting `main` commit to production.

The production checkout must have no tracked local changes before deployment:

```bash
cd ~/egr
git fetch origin
git switch main
git status --short
git pull --ff-only origin main
docker compose build egr-api frontend
docker compose run --rm egr-api alembic upgrade head
docker compose up -d egr-api frontend
```

Rebuild or restart any worker whose code or environment changed. After the
deployment, verify container health, the relevant API endpoint, and application
logs. Never use `git add .` on production; server-only exports and credentials
must remain outside commits.

## Emergency production fix

If a production-only emergency edit is unavoidable, reproduce it immediately
on a branch from `develop`, test it, and promote it through `main`. The server
must then be returned to the exact `origin/main` revision so the next deployment
is reproducible.

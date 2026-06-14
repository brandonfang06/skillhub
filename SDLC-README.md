# SkillHub SDLC README

> Full-Python branch: the Java `server/` backend has been removed. The active
> backend runtime, tests, schema migration, and container image live under
> `server-python/`.

This file captures the current development workflow for the post-cutover
SkillHub codebase.

## Active Runtime

- Backend: Python 3.12 + FastAPI in `server-python/`, listening on port `8080`.
- Frontend: React + TypeScript + Vite in `web/`, listening on port `3000`.
- Scanner: Python/FastAPI security scanner in `scanner/`, listening on port
  `8000`.
- Local dependencies: PostgreSQL, Redis, and MinIO through Docker Compose.

## Working Rules

1. Write or update tests with every backend behavior change.
2. Keep backend changes inside `server-python/` unless deployment, docs, or
   frontend contract files must move with the change.
3. Keep deployment env contracts documented under `deploy/k8s/` and matching
   release Compose files.
4. Persist milestone plans/results under `docs/` before treating architectural
   or cutover decisions as complete.
5. Do not reintroduce Java, Maven, Spring Boot images, or hybrid Java/Python
   runtime scripts.

## Local Development

```powershell
make dev-all
make dev-status
make dev-logs
make dev-all-down
```

Useful backend commands:

```powershell
make build-backend
make test-backend
make build-backend-app
make test-backend-app
```

`build-backend-app` and `test-backend-app` are compatibility aliases for the
Python backend targets.

## Direct Backend Commands

```powershell
cd server-python
uv sync --frozen
uv run python -m compileall app
uv run pytest tests -q
```

Run the backend directly when Compose is not needed:

```powershell
cd server-python
uv run uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

## Verification Before Commit

For backend or deployment changes, run the relevant subset first, then the
broader checks:

```powershell
cd server-python
uv run pytest tests -q
cd ..
docker build -t skillhub-server-python:local -f server-python\Dockerfile .
kubectl kustomize deploy\k8s\base
docker compose --env-file .env.release.example -f compose.release.yml config
git diff --check
```

For frontend changes:

```powershell
cd web
corepack pnpm install --frozen-lockfile
corepack pnpm typecheck
corepack pnpm build
```

For docs site changes:

```powershell
cd docs\skillhub
npm install
npm run build
```

## Security Checks

Dependency audit commands used by the full-Python cutover:

```powershell
cd server-python
uv export --frozen --no-dev --format requirements.txt --no-emit-project --output-file ..\.dev\security-scan\server-python-requirements.txt
uvx pip-audit -r ..\.dev\security-scan\server-python-requirements.txt

cd ..\web
corepack pnpm audit

cd ..\docs\skillhub
npm audit

cd ..\..\cli
bun audit
```

Scanner dependency audit should run inside the scanner container because it has
Linux-only dependencies such as `uvloop`.

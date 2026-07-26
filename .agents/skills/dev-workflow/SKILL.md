---
name: dev-workflow
description: Development workflow for the SkillHub Python backend, React frontend, scanner, staging validation, and pull requests.
license: Apache-2.0
---

# Development Workflow Skill

## Trigger

Use this skill for local setup, development, verification, staging, or pull
request preparation.

## Prerequisites

- Python 3.12 and `uv`
- Node.js, pnpm, and Bun for the CLI
- Docker with Docker Compose
- `curl`
- GitHub CLI when creating pull requests

## Local Development

```powershell
make dev-all
make dev-status
make dev-all-down
```

`make dev-all` starts PostgreSQL, Redis, MinIO, scanner, the FastAPI backend,
and the Vite frontend. Use `make dev-all-reset` only when a destructive local
data reset is intended.

Individual components:

```powershell
make dev
make dev-server
make dev-server-restart
make dev-web
make dev-logs
```

Access points:

- Web UI: `http://localhost:3000`
- Backend API: `http://localhost:8080`
- Backend health: `http://localhost:8080/api/v1/health`
- Backend metrics: `http://localhost:8080/api/v1/metrics/prometheus`
- Scanner health: `http://localhost:8000/health`

## Backend Commands

```powershell
cd server-python
uv sync --frozen
uv run python -m app.migrations upgrade
uv run pytest tests -q
uv run uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Use `make db-reset` to recreate the local database volume and apply the
Python-owned migration baseline.

## Verification

| Command | Scope |
| --- | --- |
| `make test-backend` | Full pytest backend suite |
| `make typecheck-web` | Frontend typecheck |
| `make lint-web` | Frontend lint |
| `make test-frontend` | Frontend unit tests |
| `make test-e2e-smoke-frontend` | Playwright smoke tests |
| `make test-cli` | CLI tests |
| `make staging` | Container build, frontend build, and smoke test |

For API changes, run `make generate-api` and commit the generated schema.

## Smoke Coverage

`scripts/smoke-test.sh` checks:

1. `/api/v1/health`
2. `/api/v1/metrics/prometheus`
3. session and CSRF behavior
4. local registration, login, password change, and logout
5. namespace and admin label workflows

Additional scripts cover namespace, governance, promotion, scanner publish,
and CLI workflows.

## Pull Requests

Before opening a pull request:

1. Run the checks proportional to the changed components.
2. Run `make staging` for backend, deployment, or broad workflow changes.
3. Regenerate OpenAPI types when the API contract changes.
4. Commit only intended files.

Use conventional commit subjects:

```text
<type>(<scope>): <description>
```

## Troubleshooting

| Issue | Action |
| --- | --- |
| Backend dependencies missing | Run `uv sync --frozen` in `server-python/` |
| Backend does not become ready | Check `.dev/python.log` and `/api/v1/health` |
| Port 8080 occupied | Identify the owning process before stopping it |
| Frontend dependencies missing | Run `make web-deps` |
| Scanner unavailable | Check Docker Compose status and scanner health |
| Staging backend build fails | Inspect `server-python/Dockerfile` and build output |

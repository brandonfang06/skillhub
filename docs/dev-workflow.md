# Development Workflow

This document describes the recommended workflow for developing SkillHub locally.

## Prerequisites

- Docker Desktop (for dependency services and staging)
- Python 3.12 and `uv` (for running the backend locally)
- Node.js 22 + pnpm (for running the frontend locally)
- `gh` CLI (for creating pull requests): https://cli.github.com/

## Stage 1: Local Development (fast iteration)

Use this stage for active development — writing code, fixing bugs, iterating quickly.

### Start the local stack

Start dependency containers:

```bash
docker compose up -d postgres redis minio skill-scanner
```

Start the Python backend with `uv`:

```bash
cd server-python
uv run uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload
```

Start the frontend:

```bash
cd web
pnpm dev
```

This starts:
- Dependency services (Postgres, Redis, MinIO) via Docker
- Backend (FastAPI) directly on your machine at http://localhost:8081
- Frontend (Vite) directly on your machine at http://localhost:3000

SkillHub now pins a shared Docker Compose project name for local development, so multiple git worktrees can reuse the same dependency containers instead of fighting over `5432`, `6379`, and `9000`.

### Local environment variables

Local development is zero-config by default. Run dependency containers from
`docker-compose.yml`, run the Python backend directly with `uv`, and run Vite
from `web/`.

To override local values, copy the template and edit the ignored file:

```bash
cp .env.local.example .env.local
```

When `.env.local` exists:

- `docker-compose.yml` receives it through `docker compose --env-file .env.local`
  for dependency settings such as PostgreSQL, Redis, MinIO, and scanner LLM
  variables.
- The Python backend receives it through `uv run uvicorn ... --env-file ../.env.local`.
- `.env.local` can override bootstrap admin, scanner upload mode, and scan
  consumer behavior.

Use `.env.local` for local-only changes such as Redis password testing,
MinIO/S3 adapter testing, Keycloak/OIDC client settings, and scanner LLM
credentials. Do not commit `.env.local`; commit only `.env.local.example`.

Environment source summary:

| Runtime | Env source | Notes |
| --- | --- | --- |
| Local backend | Optional `.env.local` via `uv run uvicorn ... --env-file ../.env.local` | FastAPI backend running on the host. |
| Local dependencies | Optional `.env.local` via `docker compose --env-file .env.local` | PostgreSQL, Redis, MinIO, and scanner containers from `docker-compose.yml`. |
| `make staging` | `docker-compose.yml` + `docker-compose.staging.yml` | Builds local backend image and frontend static files; does not use `.env.release`. |
| Release compose | `.env.release` + `compose.release.yml` | Container runtime path for manual deployment or release validation. |

### Backend restarts

**Frontend:** Vite HMR is enabled by default. Save a file and the browser updates instantly.

**Backend:** the local server runs the Python FastAPI app from `server-python/`.

After editing backend code, restart the backend explicitly:

```bash
cd server-python
uv run uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload
```

If you use `.env.local`, include `--env-file ../.env.local`. Stop the foreground
server and run the command again when you need a clean restart.

### Mock authentication

Two mock users are available in local mode (no password needed):

| User ID       | Role        | Header                           |
|---------------|-------------|----------------------------------|
| `local-user`  | Regular user | `X-Mock-User-Id: local-user`   |
| `local-admin` | Super admin  | `X-Mock-User-Id: local-admin`  |

Local development also creates a password-based bootstrap admin by default.
Use `BOOTSTRAP_ADMIN_USERNAME` / `BOOTSTRAP_ADMIN_PASSWORD` to log in through
the normal local account form. The default local fallback credentials are
`admin` / `ChangeMe!2026`.
To disable it for local source startup, set the environment variable
`BOOTSTRAP_ADMIN_ENABLED=false` before starting the backend.
For container or release environments, set the same value in `.env.release`
or the Compose environment.

### Useful commands

| Command                          | Description                      |
|----------------------------------|----------------------------------|
| `docker compose up -d postgres redis minio skill-scanner` | Start local dependency services |
| `cd server-python; uv run uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload` | Start backend locally |
| `docker compose down`            | Stop local dependency services   |
| `make dev-status`                | Check status of all services     |
| `make dev-logs`                  | Tail backend logs                |
| `SERVICE=frontend make dev-logs` | Tail frontend logs               |
| `docker compose down -v`         | Full reset of local dependency volumes |
| `make namespace-smoke`           | Run namespace workflow smoke test |
| `make db-reset`                  | Reset database only              |

### Claude + Codex parallel workflow

When two agents need to work in parallel, do not point both of them at the same checkout. Create isolated task worktrees instead:

```bash
make parallel-init TASK=legal-pages
```

That creates dedicated Claude, Codex, and integration worktrees as sibling directories. Keep `localhost:3000` reserved for the integration worktree only.

After the one-time setup, switch to the integration worktree for the daily merge + verification loop:

```bash
cd ../skillhub-integration-legal-pages
make parallel-up
```

Then verify the merged result at http://localhost:3000.

Because all worktrees share the same local dependency project, you only need one set of Postgres, Redis, and MinIO containers for all of them.

If you need to inspect or resolve merge conflicts before starting the app, you can still split the flow manually:

```bash
cd ../skillhub-integration-legal-pages
make parallel-sync
docker compose up -d postgres redis minio skill-scanner
```

See [13-parallel-workflow.md](./13-parallel-workflow.md) for the full workflow, responsibilities, merge rules, and recovery guidance.

## Stage 2: Staging Regression (pre-PR validation)

Use this stage when a feature or bugfix is complete and you want to verify it works correctly in a Docker environment before pushing.

### What staging does

`make staging` runs a **hybrid** Docker environment:
- **Backend**: built as a Docker image from your local source
- **Frontend**: built as static files (`pnpm build`) and served by Nginx
- **Dependencies**: same Postgres/Redis/MinIO as local dev

This is faster than building both images but still validates the containerized backend and the production Nginx serving path.

### Run staging

```bash
make staging
```

This will:
1. Build the backend Docker image
2. Build the frontend static files
3. Start all services
4. Run smoke tests against the API
5. Print pass/fail summary

If all tests pass, the environment stays running at:
- Web UI: http://localhost
- Backend API: http://localhost:8080

### Stop staging

```bash
make staging-down
```

### View staging logs

```bash
make staging-logs            # backend logs
SERVICE=web make staging-logs  # nginx logs
```

## Stage 3: Create Pull Request

After staging passes:

```bash
make pr
```

This will:
1. Check for uncommitted changes (prompts to commit if any)
2. Push your branch to origin
3. Create a pull request using `gh pr create --fill`

The PR title and body are auto-populated from your commit messages.

> **Note:** `make pr` requires an interactive terminal. Do not use it in CI.

## Full workflow summary

```
docker compose up -d postgres redis minio skill-scanner
cd server-python
uv run uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload
# ... write code, test in browser ...
make staging          # regression test in Docker
make staging-down     # stop staging
make pr               # push + create PR
```

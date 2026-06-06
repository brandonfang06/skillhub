# Hybrid Local E2E Plan

## Milestone

Add local orchestration so Java, Python, and TypeScript frontend services can run
together before Playwright E2E verification.

## Boundary

Allowed changes:

- `Makefile`
- `docs/backend-python-migration/**`
- `server-python/tests/**`

Forbidden changes:

- `server/**`

## Commands To Add

- `make dev-python`: run the Python FastAPI backend in the foreground on
  `http://localhost:8081`.
- `make dev-all-hybrid`: run dependencies, Java backend, Python backend, scanner,
  and Vite frontend together.
- `make test-e2e-smoke-hybrid`: start the hybrid dev stack and run Playwright
  smoke E2E.
- `make test-e2e-hybrid`: start the hybrid dev stack and run the full Playwright
  E2E suite.

## Verification

- `cd server-python; UV_CACHE_DIR=.uv-cache uv run pytest`
- `make dev-status`
- `git diff --name-only -- server` has no output.

Full E2E execution may require Docker, Java 21, browser dependencies, and local
ports `3000`, `8000`, `8080`, and `8081` to be free.


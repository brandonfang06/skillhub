# Python Backend Foundation Plan

## Milestone

Establish the backend migration governance documents, create the FastAPI
foundation in `server-python/`, and route `GET /api/v1/health` to Python during
local Vite development.

## API Boundary

| Method | Path | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/health` | Java on `localhost:8080` | Python on `localhost:8081` |
| * | `/api/**` except Python-owned paths | Java | Java |
| * | `/oauth2/**` | Java | Java |

## Files Allowed To Change

- `docs/backend-python-migration/**`
- `server-python/**`
- `web/vite.config.ts`
- `web/vite.config.test.ts`

## Files Forbidden To Change

- `server/**`

## Implementation Steps

1. Add governance docs and route registry.
2. Add `server-python/AGENTS.md` with the absolute Java boundary.
3. Add Python tests first for health envelope and request id propagation.
4. Add Vite config test first for route ownership and proxy ordering.
5. Implement minimal FastAPI app and health route.
6. Update Vite dev proxy so `/api/v1/health` routes to port `8081`.
7. Run Python and frontend verification.
8. Write result document.
9. Confirm `git diff --name-only` contains no `server/` paths.
10. Commit and push to `dev`.

## Acceptance Criteria

- `cd server-python; uv run pytest` passes.
- `cd web; pnpm exec vitest run vite.config.test.ts` passes.
- Python `GET /api/v1/health` returns `data.message = "UP"` in the SkillHub
  envelope.
- Python reuses incoming `X-Request-Id` and generates one when missing.
- Vite proxy routes `/api/v1/health` to `http://localhost:8081` before the
  fallback `/api` proxy.
- No file under `server/` changes.


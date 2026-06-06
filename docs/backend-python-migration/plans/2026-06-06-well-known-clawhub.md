# Well-Known ClawHub Discovery Migration Plan

Date: 2026-06-06

## Milestone

Migrate `GET /.well-known/clawhub.json` to FastAPI as the first formal Python-owned non-health
route.

This route is intentionally selected before database-backed APIs because it is easy to verify and
has no dependency on PostgreSQL, Redis, MinIO, session state, OAuth, CSRF, or RBAC.

## API Contract

Java reference:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/compat/WellKnownController.java`

Route:

| Method | Path | Response |
| --- | --- | --- |
| GET | `/.well-known/clawhub.json` | `{ "apiBase": "/api/v1" }` |

Important behavior:

- The response is plain JSON, not the SkillHub envelope.
- No auth is required.
- No request body is accepted.
- No Java files may be modified.

## Ownership Change

Before:

| Method | Path | Owner |
| --- | --- | --- |
| GET | `/.well-known/clawhub.json` | java |

After:

| Method | Path | Owner |
| --- | --- | --- |
| GET | `/.well-known/clawhub.json` | python |

## Allowed Changes

- `server-python/app/api/well_known.py`
- `server-python/app/main.py`
- `server-python/tests/test_well_known.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/results/2026-06-06-well-known-clawhub.md`

## Forbidden Changes

- Any file under `server/`
- Java backend config, tests, controller, service, or generated files
- Route ownership for any database-backed, auth, session, mutating, OAuth, or admin endpoint

## TDD Steps

1. Add `server-python/tests/test_well_known.py`.
   - Assert `GET /.well-known/clawhub.json` returns HTTP 200.
   - Assert JSON body is exactly `{ "apiBase": "/api/v1" }`.
   - Assert request id middleware still adds `X-Request-Id` response header.
   - Run the test and confirm it fails with 404 before implementation.

2. Add Vite proxy test coverage in `web/vite.config.test.ts`.
   - Assert `/.well-known/clawhub.json` targets `http://localhost:8081`.
   - Assert the route is independent from `/api` fallback ownership.
   - Run the test and confirm it fails before proxy implementation.

3. Implement `server-python/app/api/well_known.py`.
   - Add a FastAPI router for `GET /.well-known/clawhub.json`.
   - Return plain dict `{"apiBase": "/api/v1"}`.
   - Do not use `app.core.response.ok`.

4. Include the router in `server-python/app/main.py`.

5. Update Vite proxy.
   - Add `/.well-known/clawhub.json` pointing to `http://localhost:8081`.

6. Update route registry.
   - Add `GET /.well-known/clawhub.json` as Python-owned.

7. Verify:
   - `cd server-python; uv run pytest`
   - `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts`
   - `git diff --name-only -- server`
   - Optional local curl when servers are running:
     - `curl -i http://localhost:8081/.well-known/clawhub.json`
     - `curl -i http://localhost:3000/.well-known/clawhub.json`

8. Record result, commit, and push.

## Acceptance Criteria

- Python test proves the route contract.
- Vite proxy test proves local ownership points to Python.
- Route registry reflects ownership.
- No `server/` files changed.
- Result document is written before commit.

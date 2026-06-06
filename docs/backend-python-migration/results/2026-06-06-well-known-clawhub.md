# Well-Known ClawHub Discovery Migration Result

Date: 2026-06-06

## Summary

Migrated `GET /.well-known/clawhub.json` to the Python FastAPI backend as the first formal
Python-owned route after health.

This route was selected ahead of database-backed APIs because it is easy to verify and has no
PostgreSQL, Redis, MinIO, auth, session, CSRF, RBAC, or mutation dependency.

## Routes Changed

| Method | Path | Before | After |
| --- | --- | --- | --- |
| GET | `/.well-known/clawhub.json` | java | python |

## Contract

Response body:

```json
{
  "apiBase": "/api/v1"
}
```

This endpoint intentionally returns plain JSON rather than the SkillHub response envelope.

## Files Changed

- `server-python/app/api/well_known.py`
- `server-python/app/main.py`
- `server-python/tests/test_well_known.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/plans/2026-06-06-well-known-clawhub.md`
- `docs/backend-python-migration/results/2026-06-06-well-known-clawhub.md`

## Verification

- `cd server-python; uv run pytest tests\test_well_known.py -v`: passed, 1 test.
- `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts`: passed, 3 tests.
- `cd server-python; uv run pytest`: passed, 9 tests.
- `git diff --name-only -- server`: returned no paths.

## Risks

- This endpoint does not exercise database integration. The next database-backed milestone should
  still be treated as the first Python PostgreSQL read-model migration.

## Follow-up

- Keep `GET /api/v1/labels` and `GET /api/web/labels` as the next planned Python migration target
  when the team is ready to introduce PostgreSQL access in `server-python/`.

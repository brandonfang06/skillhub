# Public Labels API Migration Result

Date: 2026-06-07

## Summary

Migrated the public labels read API to the Python FastAPI backend.

This is the first PostgreSQL-backed Python route group. Java remains the source of truth for admin
label mutations and all other label/skill behavior not explicitly listed in the route registry.

## Routes Changed

| Method | Path | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/labels` | java | python |
| GET | `/api/web/labels` | java | python |

## Contract

The endpoint returns the standard SkillHub envelope:

```json
{
  "code": 0,
  "msg": "response.success.read",
  "data": [
    {
      "slug": "official",
      "type": "RECOMMENDED",
      "displayName": "Official"
    }
  ],
  "timestamp": "...",
  "requestId": "..."
}
```

Python behavior implemented:

- Reads visible labels from `label_definition`.
- Includes only `visible_in_filter = true`.
- Sorts by `sort_order ASC, id ASC`.
- Reads translations from `label_translation`.
- Matches Java display-name fallback:
  - normalized full locale
  - normalized language
  - `en`
  - slug

## Files Changed

- `server-python/pyproject.toml`
- `server-python/uv.lock`
- `server-python/app/api/labels.py`
- `server-python/app/core/config.py`
- `server-python/app/core/database.py`
- `server-python/app/main.py`
- `server-python/tests/test_labels.py`
- `server-python/tests/test_label_repository.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/results/2026-06-07-public-labels-api.md`

## Verification

- `cd server-python; uv run pytest tests\test_labels.py tests\test_label_repository.py -v`: passed, 6 tests.
- `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts`: passed, 4 tests.
- `cd server-python; uv run pytest`: passed, 15 tests.
- `git diff --name-only -- server`: returned no paths.

Pending local-stack verification:

- Java/Python direct contract comparison was not run in this session because the full Java +
  PostgreSQL local stack was not started.
- Frontend smoke E2E was not run in this session for the same reason.

Before using this route for broader frontend validation, run the hybrid stack and compare:

```bash
curl -s http://localhost:8080/api/v1/labels
curl -s http://localhost:8081/api/v1/labels
curl -s http://localhost:3000/api/v1/labels
curl -s http://localhost:3000/api/web/labels
```

## Risks

- This route introduces Python PostgreSQL access through `SKILLHUB_DATABASE_URL`. Windows/macOS can
  use the Docker Compose development PostgreSQL. Ubuntu developers should point this environment
  variable at the organization PostgreSQL endpoint.
- SQL uses PostgreSQL-specific array matching for translation lookup.
- Live Java/Python contract comparison still needs to be run against a populated database.

## Follow-up

- Run hybrid local E2E once Java, Python, Vite, and PostgreSQL are all available.
- Next planned API group: `GET /api/v1/skills/{namespace}/{slug}/labels` and
  `GET /api/web/skills/{namespace}/{slug}/labels`.

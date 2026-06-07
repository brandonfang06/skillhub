# Public Skill Search API Result

Date: 2026-06-07

## Summary

Migrated the anonymous public portal skill search route to FastAPI:

- `GET /api/web/skills`

The original draft sequence mentioned `GET /api/v1/skills`, but implementation inspection showed
that route is Java's ClawHub compatibility list/publish surface. It remains Java-owned.

## Routes Changed

| Method | Route | Before | After |
| --- | --- | --- | --- |
| GET | `/api/web/skills` | Java `localhost:8080` | Python `localhost:8081` |

Routes intentionally unchanged:

| Method | Route | Owner | Reason |
| --- | --- | --- | --- |
| GET | `/api/v1/skills` | Java | ClawHub compatibility list response, not portal search. |
| POST | `/api/v1/skills` | Java | ClawHub compatibility publish. |
| GET | `/api/v1/search` | Java | ClawHub compatibility search. |

## Implementation

- Added FastAPI route for `GET /api/web/skills`.
- Added Java-style query parsing for `q`, `namespace`, repeated `label`, `sort`, `page`, and
  `size`.
- Added public anonymous PostgreSQL search reader using `skill_search_document`, `skill`, and
  `namespace`.
- Added optional label filtering through `skill_label` and `label_definition`.
- Added Java-compatible `SkillSummaryResponse` mapping and lifecycle published projection.
- Added exact Vite proxy regex for `/api/web/skills` without taking over nested routes.
- Added `scripts/dev-hybrid.ps1 verify-search-smoke`.

## Verification

Commands run:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_skill_search.py tests/test_skill_search_repository.py tests/test_hybrid_makefile.py -v

cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts

$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-search-smoke
```

Live gate summary:

```json
{
  "allJavaMatchesPython": true,
  "allPythonMatchesProxyWeb": true,
  "v1SkillsRemainsJava": true,
  "cases": [
    "defaultNewest",
    "relevanceSingle",
    "namespaceFilter",
    "labelFilter",
    "downloadsSort",
    "ratingSort",
    "invalidPagination"
  ]
}
```

Representative live fixture results:

- `defaultNewest`: 3 matching fixture skills.
- `relevanceSingle`: 1 matching fixture skill.
- `labelFilter`: 2 matching fixture skills.
- `ratingSort`: `gamma`, `alpha`, `beta`.
- invalid `page=-1&size=0`: Java/Python both normalized to `page=0`, `size=20`.

The live gate also ran frontend Playwright smoke E2E: `6 passed`.

## Boundary Check

- `server/` remained read-only.
- No Java source, config, migration, generated DTO, or Java test file was changed.
- `web/src/api/generated/schema.d.ts` was not edited.

## Notes

- Vite proxy uses `^/api/web/skills(?:\\?.*)?$` so nested `/api/web/skills/...` routes keep their
  explicit existing ownership.
- `ratingAvg` numeric scale is normalized in contract comparison, matching the previous detail
  milestone behavior.
- The live gate confirmed `/api/v1/skills` still has the Java ClawHub list shape.

## Risks And Follow-Up

- This milestone covers anonymous public portal search only.
- Authenticated namespace-member search visibility remains deferred until the auth/session bridge is
  designed.
- Do not migrate `GET /api/v1/skills` without a separate ClawHub compatibility plan and a
  method-aware routing decision, because the same path also owns `POST /api/v1/skills`.
- A future low-risk candidate is `GET /api/v1/search` ClawHub compatibility search, which is a
  distinct route and can be planned separately.

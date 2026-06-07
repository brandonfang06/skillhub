# Public Skill Detail API Result

Date: 2026-06-07

## Summary

Migrated anonymous public skill detail reads to FastAPI while keeping Java as the read-only
reference backend during coexistence.

## Routes Changed

| Method | Route | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{namespace}/{slug}` | Java `localhost:8080` | Python `localhost:8081` |
| GET | `/api/web/skills/{namespace}/{slug}` | Java `localhost:8080` | Python `localhost:8081` |

Search/list, nested version routes, files, downloads, lifecycle mutations, social mutations, and
authenticated owner/admin preview behavior remain outside this milestone.

## Implementation

- Added FastAPI skill detail route aliases for `/api/v1` and `/api/web`.
- Added Java-compatible response mapping for anonymous public skill detail fields.
- Added PostgreSQL reader for active, non-hidden, public skills with `latest_version_id`.
- Added lifecycle projection for anonymous public viewers:
  - prefer `latest_version_id` when it points to a `PUBLISHED` version
  - otherwise fall back to newest `PUBLISHED` version by `published_at`, `created_at`, then `id`
- Added label projection using label translation fallback to English and then slug.
- Added Vite proxy ownership for only the exact two-segment detail routes.
- Added `scripts/dev-hybrid.ps1 verify-detail-smoke` as the Windows live contract gate.

## Verification

Commands run:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest tests/test_skill_detail.py tests/test_skill_detail_repository.py tests/test_hybrid_makefile.py -v

cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts

powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-detail-smoke
```

Live gate result:

```json
{
  "fixtureSlug": "codex-detail-fixture-20260607230000",
  "javaMatchesPython": true,
  "pythonMatchesProxyV1": true,
  "pythonMatchesProxyWeb": true,
  "publicDetail": {
    "id": 15,
    "slug": "codex-detail-fixture-20260607230000",
    "ownerDisplayName": "Codex Detail Owner",
    "labels": 1,
    "headlineVersion": "1.2.0",
    "publishedVersion": "1.2.0",
    "ownerPreviewVersion": null,
    "resolutionMode": "PUBLISHED"
  },
  "hidden": {
    "javaStatus": 400,
    "pythonStatus": 400,
    "matches": true
  },
  "noLatest": {
    "javaStatus": 400,
    "pythonStatus": 400,
    "matches": true
  },
  "archivedNamespace": {
    "javaStatus": 403,
    "pythonStatus": 403,
    "matches": true
  }
}
```

The live gate also ran frontend Playwright smoke E2E: `6 passed`.

## Boundary Check

- `server/` remained read-only.
- No Java source, config, migration, generated DTO, or Java test file was changed.
- `web/src/api/generated/schema.d.ts` was not edited.

## Notes From Implementation

- Java returns `ratingAvg` with BigDecimal scale while Python serializes it as a JSON number. The
  live comparison normalizes numeric scale for `ratingAvg` only.
- Archived namespace behavior is status-compared against Java and returns `403`.
- Hidden and no-latest-version fixtures are status-compared against Java and return `400`.

## Risks And Follow-Up

- This milestone covers anonymous public detail only.
- Authenticated owner/admin preview, namespace role checks, lifecycle permissions, and viewer state
  remain deferred until the auth/session bridge is explicitly designed.
- Public skill search (`GET /api/v1/skills`, `GET /api/web/skills`) is the next planned API group
  and needs its own milestone plan before implementation.

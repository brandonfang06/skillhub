# Public Skill Versions List API Migration Result

Date: 2026-06-07

Status: passed

## Scope

Routes migrated in this milestone:

| Method | Path | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{namespace}/{slug}/versions` | java | python |
| GET | `/api/web/skills/{namespace}/{slug}/versions` | java | python |

Routes intentionally not migrated:

- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}`
- `GET /api/web/skills/{namespace}/{slug}/versions/{version}`
- version compare routes
- version file metadata routes
- version file content routes
- version download routes
- authenticated manager-visible non-published versions

## Implementation Summary

- Added FastAPI aliases for the public skill versions list routes.
- Reused the Python `skills` API module and anonymous public skill lookup boundary.
- Returned Java-compatible `PageResponse<SkillVersionResponse>`:
  - `items`
  - `total`
  - `page`
  - `size`
- Mapped Java-compatible version fields:
  - `id`
  - `version`
  - `status`
  - `changelog`
  - `fileCount`
  - `totalSize`
  - `publishedAt`
  - `downloadAvailable`
- Matched Java anonymous published version order from
  `SkillVersionJpaRepository.findBySkillIdAndStatus()`: `created_at DESC`.
- Added exact Vite proxy ownership entries for `/versions` list only.
- Updated route ownership and migration sequence documentation.

## Files Changed

- `server-python/app/api/skills.py`
- `server-python/tests/test_skill_versions.py`
- `server-python/tests/test_skill_versions_repository.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-07-public-skill-versions-list-api.md`
- `docs/backend-python-migration/results/2026-06-07-public-skill-versions-list-api.md`

## Tests

Python:

```text
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest

39 passed, 1 warning
```

Vite proxy config:

```text
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts

1 passed, 7 tests passed
```

Frontend smoke E2E:

```text
cd web
.\node_modules\.bin\playwright.CMD test -c playwright.smoke.config.ts

6 passed (17.0s)
```

## Live Contract Verification

The live verification gate ran Java, Python, Vite, PostgreSQL, Redis, MinIO, and the scanner in the
same Windows PowerShell lifecycle.

Fixture inserted into local Docker PostgreSQL:

| Field | Value |
| --- | --- |
| namespace | `global` |
| skill slug | `codex-versions-fixture-20260607191000` |
| visibility | `PUBLIC` |
| skill status | `ACTIVE` |
| latest version | `1.2.0`, `PUBLISHED` |
| older version | `1.0.0`, `PUBLISHED` |
| draft version | `2.0.0-draft`, `DRAFT` |
| download readiness | `1.2.0=true`, `1.0.0=false` |

Stable fields compared:

- `code`
- `msg`
- `data.items`
- `data.total`
- `data.page`
- `data.size`

Ignored volatile fields:

- `timestamp`
- `requestId`

Comparison summary:

```json
{
  "fixtureSlug": "codex-versions-fixture-20260607191000",
  "scenarios": [
    {
      "name": "default-page",
      "javaMatchesPython": true,
      "pythonMatchesProxyV1": true,
      "pythonMatchesProxyWeb": true,
      "total": 2,
      "page": 0,
      "size": 20,
      "versions": ["1.2.0", "1.0.0"],
      "downloadAvailable": [true, false]
    },
    {
      "name": "page-0-size-1",
      "javaMatchesPython": true,
      "pythonMatchesProxyV1": true,
      "pythonMatchesProxyWeb": true,
      "total": 2,
      "page": 0,
      "size": 1,
      "versions": ["1.2.0"],
      "downloadAvailable": [true]
    },
    {
      "name": "page-1-size-1",
      "javaMatchesPython": true,
      "pythonMatchesProxyV1": true,
      "pythonMatchesProxyWeb": true,
      "total": 2,
      "page": 1,
      "size": 1,
      "versions": ["1.0.0"],
      "downloadAvailable": [false]
    }
  ],
  "e2eSmoke": "passed"
}
```

The `DRAFT` version was not returned to the anonymous public caller, matching Java.

## Boundary Check

Required Java boundary check:

```powershell
git diff --name-only -- server
```

Expected and observed output: empty.

## Cleanup Notes

During final cleanup, `dev-hybrid.ps1 down` emitted Windows sandbox `taskkill` warnings for
transient wrapper PIDs. Follow-up checks showed:

- no `LISTENING` entries on ports `3000`, `8080`, or `8081`
- only `TIME_WAIT` entries remained
- Docker dependency services were stopped explicitly with:
  `docker compose -p skillhub down --remove-orphans`

## Risks And Follow-Up

- This milestone intentionally supports anonymous public version listing only.
- Auth-specific manager-visible draft/pending/rejected/yanked/scanning versions remain Java-owned
  until the auth/session bridge is designed.
- Version detail remains Java-owned and should be the next small read-only milestone.
- Future live gates should extract the repeated fixture setup into a reusable verification helper.

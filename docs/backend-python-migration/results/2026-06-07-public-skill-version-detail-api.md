# Public Skill Version Detail API Migration Result

Date: 2026-06-07

Status: passed

## Scope

Routes migrated in this milestone:

| Method | Path | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{namespace}/{slug}/versions/{version}` | java | python |
| GET | `/api/web/skills/{namespace}/{slug}/versions/{version}` | java | python |

Routes intentionally not migrated:

- `DELETE /api/v1|web/skills/{namespace}/{slug}/versions/{version}`
- version compare routes
- version file metadata routes
- version file content routes
- version download routes
- authenticated owner/admin preview for non-published versions

## Implementation Summary

- Added FastAPI aliases for the public skill version detail routes.
- Reused the Python `skills` API module and anonymous public skill lookup boundary.
- Returned Java-compatible `SkillVersionDetailResponse` fields:
  - `id`
  - `version`
  - `status`
  - `changelog`
  - `fileCount`
  - `totalSize`
  - `publishedAt`
  - `parsedMetadataJson`
  - `manifestJson`
- Preserved `parsedMetadataJson` and `manifestJson` as JSON strings, matching Java.
- Required requested versions to be `PUBLISHED` for anonymous public callers.
- Added exact Vite proxy ownership entries for `/versions/{version}` only.
- Updated route ownership and migration sequence documentation.

## Files Changed

- `server-python/app/api/skills.py`
- `server-python/tests/test_skill_version_detail.py`
- `server-python/tests/test_skill_version_detail_repository.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-07-public-skill-version-detail-api.md`
- `docs/backend-python-migration/results/2026-06-07-public-skill-version-detail-api.md`

## Tests

Python:

```text
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest

44 passed, 1 warning
```

Vite proxy config:

```text
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts

1 passed, 8 tests passed
```

Frontend smoke E2E:

```text
cd web
.\node_modules\.bin\playwright.CMD test -c playwright.smoke.config.ts

6 passed (17.3s)
```

## Live Contract Verification

The live verification gate ran Java, Python, Vite, PostgreSQL, Redis, MinIO, and the scanner in the
same Windows PowerShell lifecycle.

Fixture inserted into local Docker PostgreSQL:

| Field | Value |
| --- | --- |
| namespace | `global` |
| skill slug | `codex-version-detail-fixture-20260607192500` |
| visibility | `PUBLIC` |
| skill status | `ACTIVE` |
| published version | `1.2.0`, `PUBLISHED` |
| draft version | `2.0.0-draft`, `DRAFT` |
| parsed metadata | `{"name":"detail-demo","version":"1.2.0"}` |
| manifest | `[{"path":"SKILL.md","sha256":"abc"}]` |

Stable fields compared:

- `code`
- `msg`
- `data`

Ignored volatile fields:

- `timestamp`
- `requestId`

Comparison summary:

```json
{
  "fixtureSlug": "codex-version-detail-fixture-20260607192500",
  "published": {
    "name": "published-version-detail",
    "javaMatchesPython": true,
    "pythonMatchesProxyV1": true,
    "pythonMatchesProxyWeb": true,
    "version": "1.2.0",
    "parsedMetadataJson": "{\"name\": \"detail-demo\", \"version\": \"1.2.0\"}",
    "manifestJson": "[{\"path\": \"SKILL.md\", \"sha256\": \"abc\"}]",
    "publishedAt": "2026-06-07T10:00:00Z"
  },
  "draft": {
    "name": "draft-version-rejected",
    "javaStatus": 400,
    "pythonStatus": 400,
    "proxyStatus": 400
  },
  "e2eSmoke": "passed"
}
```

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

- This milestone intentionally supports anonymous public version detail only.
- Auth-specific owner/admin preview for non-published versions remains Java-owned until the
  auth/session bridge is designed.
- File metadata routes remain Java-owned and are the next small read-only candidate.
- Exact Java error envelope for not-published versions is not implemented in Python yet; live gate
  confirmed status parity for the draft rejection.

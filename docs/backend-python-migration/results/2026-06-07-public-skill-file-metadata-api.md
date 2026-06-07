# Public Skill File Metadata API Migration Result

Date: 2026-06-07

Status: passed after review fixes

## Scope

Routes migrated in this milestone:

| Method | Path | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{namespace}/{slug}/versions/{version}/files` | java | python |
| GET | `/api/web/skills/{namespace}/{slug}/versions/{version}/files` | java | python |
| GET | `/api/v1/skills/{namespace}/{slug}/tags/{tagName}/files` | java | python |
| GET | `/api/web/skills/{namespace}/{slug}/tags/{tagName}/files` | java | python |

Routes intentionally not migrated:

- file content routes ending in `/file`
- download routes ending in `/download`
- version compare routes
- authenticated owner/admin preview behavior

## Review Fixes

Gemini's implementation was not accepted as-is. The review fixed:

- Vite version-detail regex incorrectly captured `/versions/compare`; the regex now excludes
  `compare`, and tests exercise real proxy matching.
- The file metadata result document was missing even though the migration sequence plan referenced it.
- `verify-files-smoke` originally depended on an old fixture slug; it now creates a repeatable
  PostgreSQL fixture.
- Java filters file metadata through `objectStorageService.exists(storage_key)`. The Windows live
  fixture now creates matching local storage objects under `.dev/java-storage` without writing
  runtime files under `server/`.
- SQL fixture setup now follows the current `skill` unique key:
  `(namespace_id, slug, owner_id)`.

## Implementation Summary

- Added FastAPI route aliases for public skill file metadata by version and tag.
- Added DB readers for anonymous public skill lookup, published version lookup, tag lookup, and
  file metadata mapping.
- Returned Java-compatible `SkillFileResponse` fields:
  - `id`
  - `filePath`
  - `fileSize`
  - `contentType`
  - `sha256`
- Added Vite proxy ownership only for `/files` metadata routes.
- Kept `/file`, `/download`, `/versions/compare`, `/api/**`, and `/oauth2/**` Java-owned.
- Added Windows hybrid verification action:
  `scripts\dev-hybrid.ps1 verify-files-smoke`.

## Tests

Python:

```text
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest

50 passed, 1 warning
```

Vite proxy config:

```text
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts

1 passed, 9 tests passed
```

Windows hybrid live gate:

```text
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-files-smoke

versionFiles.javaMatchesPython = true
tagStableFiles.javaMatchesPython = true
tagLatestFiles.javaMatchesPython = true
Playwright smoke: 6 passed
```

## Live Contract Verification

The live verification gate ran Java, Python, Vite, PostgreSQL, Redis, MinIO, and the scanner in one
Windows PowerShell lifecycle.

Fixture inserted into local Docker PostgreSQL:

| Field | Value |
| --- | --- |
| namespace | `global` |
| skill slug | `codex-files-fixture-20260607224000` |
| visibility | `PUBLIC` |
| skill status | `ACTIVE` |
| latest version | `1.2.0`, `PUBLISHED` |
| older version | `1.0.0`, `PUBLISHED` |
| tag | `stable -> 1.0.0` |
| Java storage base | `.dev/java-storage` |
| storage keys | `fixtures/files/...` matching DB `skill_file.storage_key` |

Compared routes:

- `/api/v1/skills/global/codex-files-fixture-20260607224000/versions/1.2.0/files`
- `/api/v1/skills/global/codex-files-fixture-20260607224000/tags/stable/files`
- `/api/v1/skills/global/codex-files-fixture-20260607224000/tags/latest/files`
- matching `/api/web/...` proxy aliases through Vite

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
  "versionFiles": {
    "javaMatchesPython": true,
    "pythonMatchesProxyV1": true,
    "pythonMatchesProxyWeb": true
  },
  "tagStableFiles": {
    "javaMatchesPython": true,
    "pythonMatchesProxyV1": true,
    "pythonMatchesProxyWeb": true
  },
  "tagLatestFiles": {
    "javaMatchesPython": true,
    "pythonMatchesProxyV1": true,
    "pythonMatchesProxyWeb": true
  }
}
```

## Boundary Check

Required Java boundary check:

```powershell
git diff --name-only -- server
```

Expected and observed output: empty.

## Risks And Follow-Up

- Java file metadata availability depends on object storage existence. Python currently reads DB
  metadata only. This is acceptable for the migrated public metadata route only because live
  fixtures include matching storage objects; future file/download milestones must design the full
  storage bridge.
- Authenticated owner/admin preview remains Java-owned until the auth/session bridge exists.
- `/file`, `/download`, and `/versions/compare` must stay Java-owned until separate milestones.

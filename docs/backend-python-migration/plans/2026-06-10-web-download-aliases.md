# Web Download Alias Migration Plan

## Summary

Move the frontend web download aliases to FastAPI. The v1 download implementation
is already Python-owned, so this milestone only adds `/api/web` route aliases and
proxy ownership for the same behavior.

## Route Ownership

Python-owned after this milestone:

- `GET /api/web/skills/{namespace}/{slug}/download`
- `GET /api/web/skills/{namespace}/{slug}/versions/{version}/download`
- `GET /api/web/skills/{namespace}/{slug}/tags/{tagName}/download`

Already Python-owned and unchanged:

- `GET /api/v1/skills/{namespace}/{slug}/download`
- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/download`
- `GET /api/v1/skills/{namespace}/{slug}/tags/{tagName}/download`
- `GET /api/v1/download`
- `GET /api/v1/download/{canonicalSlug}`

Out of scope:

- Auth/OAuth/API tokens.
- Notification SSE.
- Admin password reset.
- File-content web aliases, which do not have Java evidence in the current API.

## Java Contract Reference

Read-only references:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillController.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillDownloadService.java`

Expected behavior:

- Web aliases share the same `SkillController` request mapping as v1 aliases.
- Latest, explicit version, and tag downloads stream the same bundle/fallback zip.
- Download counters increment for published downloads.
- Anonymous pending-version downloads stay rejected.
- Missing bundle/no files keeps the existing Java error status.

## Implementation Scope

Allowed edits:

- `server-python/app/api/skills.py`
- `server-python/tests/test_skill_download.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/*`

Forbidden:

- Any file under `server/`.
- Database schema changes.
- Auth/token/session behavior.
- Refactoring the core download implementation beyond what the aliases require.

## Test Plan

- Add FastAPI route tests proving web aliases call the same readers and preserve
  `X-Mock-User-Id`.
- Update Vite proxy tests so the three web download aliases route to Python.
- Extend the Windows download live gate so Java direct, Python direct, and Vite
  proxy compare:
  - latest web alias;
  - explicit version web alias;
  - tag web alias;
  - missing/no-file rejection through a web alias;
  - published download counter deltas including web alias hits.

## Verification Commands

```powershell
cd server-python
$env:UV_CACHE_DIR='..\.uv-cache'
uv run pytest tests/test_skill_download.py tests/test_hybrid_makefile.py -q

cd ..\web
npx.cmd vitest run vite.config.test.ts

cd ..
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-download-smoke
git diff --name-only -- server
git diff --check
```

## Tasks

- [x] Add failing Python and Vite tests.
- [x] Add FastAPI web download aliases.
- [x] Move Vite proxy ownership for web download aliases.
- [x] Extend Windows download live gate coverage.
- [x] Update route registry and sequence plan.
- [x] Write result document.
- [x] Commit and push to `origin/dev`.

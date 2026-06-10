# Web Download Alias Migration Result

## Summary

Moved the frontend web download aliases to FastAPI by routing them through the
existing Python v1 download implementation.

Python-owned routes:

- `GET /api/web/skills/{namespace}/{slug}/download`
- `GET /api/web/skills/{namespace}/{slug}/versions/{version}/download`
- `GET /api/web/skills/{namespace}/{slug}/tags/{tagName}/download`

Already Python-owned and unchanged:

- `GET /api/v1/skills/{namespace}/{slug}/download`
- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/download`
- `GET /api/v1/skills/{namespace}/{slug}/tags/{tagName}/download`
- `GET /api/v1/download`
- `GET /api/v1/download/{canonicalSlug}`

## Behavior Preserved

- Latest, explicit version, and tag downloads stream the same content as Java.
- Java-compatible `Content-Type`, `Content-Disposition`, `Content-Length`, and
  body bytes are preserved.
- Fallback zip generation remains sorted and Java-compatible by content.
- Published downloads increment `skill.download_count` and
  `skill_version_stats.download_count`.
- Pending owner download and rejection behavior remain unchanged.

## Verification

Commands run:

```powershell
cd server-python
$env:UV_CACHE_DIR='..\.uv-cache'
uv run pytest tests/test_skill_download.py tests/test_hybrid_makefile.py -q

cd ..\web
npx.cmd vitest run vite.config.test.ts

cd ..
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-download-smoke
```

Results:

- Python tests: `30 passed`.
- Vite proxy tests: `34 passed`.
- Windows live gate: passed.
- Playwright smoke in live gate: `6 passed`.
- Live gate compared Java direct, Python direct, and Vite proxy for:
  - v1 latest/version/tag downloads;
  - web latest/version/tag downloads;
  - fallback zip download;
  - owner pending download;
  - missing bundle/no-file status;
  - anonymous pending status.
- Counter delta matched expectation after adding web aliases:
  - `skill.download_count`: `21`;
  - version `1.0.0`: `18`;
  - version `1.1.0`: `3`.

## Files Changed

- `server-python/app/api/skills.py`
- `server-python/tests/test_skill_download.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-10-web-download-aliases.md`

## Remaining Work

- Admin password reset remains Java-owned.
- Auth/OAuth/API-token surfaces remain Java-owned.
- Notification SSE remains Java-owned.
- Final proxy cleanup, Python route/module refactor, schema ownership, and Java
  decommission remain future milestones.

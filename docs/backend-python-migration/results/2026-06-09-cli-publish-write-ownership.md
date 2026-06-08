# CLI Publish Write Ownership Result

## Summary

Moved local Vite ownership for `POST /api/cli/v1/skills/{namespace}/publish` from Java to Python.

This completes the CLI publish write route ownership step after the Python publish foundations for
direct write, scanner handoff, same-version replacement, pending-review auto-withdraw, and storage
failure rollback evidence.

## Routes Changed

| Route | Before | After |
| --- | --- | --- |
| `POST /api/cli/v1/skills/{namespace}/publish` | Java through Vite `/api` fallback | Python direct proxy |

Unchanged:

- `POST /api/cli/v1/skills/{namespace}/publish/validate`: Python
- `POST /api/v1/skills`: Java
- `POST /api/v1/publish`: Java
- `POST /api/v1/skills/{namespace}/publish`: Java
- `POST /api/web/skills/{namespace}/publish`: Java

## Java Parity Checklist Outcome

- Java reference: `SkillPublishService` and CLI publish adapter behavior.
- API contract: covered for stable success response fields through Vite proxy.
- Authorization/session behavior: covered only for local mock-user bridge; OAuth/session/API-token
  remain Java-owned.
- Database transaction atomicity: covered by prior rollback milestone and reused here.
- Audit actor/timestamp fields: covered by prior side-effect and publish write milestones.
- Storage and replacement side effects: covered by Vite proxy repeated publish matrix.
- Scanner result boundary: scanner handoff is covered by Redis stream tests; scanner result
  consumption remains a separate scanner-processing milestone and does not block this route
  ownership move for pre-launch local development.

## Verification

Python targeted tests:

```powershell
cd server-python
$env:UV_CACHE_DIR='server-python\.uv-cache'
uv run pytest tests/test_hybrid_makefile.py tests/test_publish_http_validate.py -q
```

Result:

- `13 passed, 1 warning`

Vite proxy tests:

```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Result:

- `1 passed`
- `19 passed`

Windows live gate:

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
$env:COREPACK_HOME=(Join-Path (Get-Location) '.dev\corepack')
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-cli-publish-write-ownership-smoke
```

Result:

- First CLI publish through Vite proxy: `200`
- Same-version replacement through Vite proxy: `200`
- New-version publish through Vite proxy: `200`
- Same-version count after replacement: `1`
- Old replacement bundle deleted: `true`
- Replacement version before next publish: `PENDING_REVIEW`
- Replacement version after next publish: `UPLOADED`
- Replacement pending review task count: `1 -> 0`
- Next version status: `PENDING_REVIEW`
- Java-owned publish routes still match Java through Vite:
  - `POST /api/v1/skills`: `401`
  - `POST /api/v1/publish`: `401`
  - `POST /api/v1/skills/global/publish`: `401`
  - `POST /api/web/skills/global/publish`: `401`
- Playwright smoke: `6 passed`

The gate emitted taskkill warnings during teardown, but a follow-up port check found no listeners
on `3000`, `8080`, `8081`, or `8000`.

## Files Changed

- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `server-python/tests/test_hybrid_makefile.py`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-09-cli-publish-write-ownership.md`
- `docs/backend-python-migration/results/2026-06-09-cli-publish-write-ownership.md`

## Risks

- Portal/web publish routes remain Java-owned.
- Scanner result consumption is not implemented in this milestone.
- Local mock-user authorization remains the only Python-owned auth bridge for this route.

## Follow-Up

- Migrate portal publish write routes when frontend publishing becomes the next priority.
- Plan scanner result processing lifecycle if asynchronous scan completion should be Python-owned
  before portal publish.

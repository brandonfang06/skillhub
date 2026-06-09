# Portal Publish Write Ownership Result

## Summary

Moved portal publish write aliases from Java to Python:

- `POST /api/v1/skills/{namespace}/publish`
- `POST /api/web/skills/{namespace}/publish`

Both aliases now reuse the existing Python publish write service path. Root ClawHub publish and
legacy publish remain Java-owned.

## Routes Changed

| Route | Before | After |
| --- | --- | --- |
| `POST /api/v1/skills/{namespace}/publish` | Java | Python |
| `POST /api/web/skills/{namespace}/publish` | Java | Python |

Unchanged:

- `POST /api/cli/v1/skills/{namespace}/publish`: Python
- `POST /api/cli/v1/skills/{namespace}/publish/validate`: Python
- `POST /api/v1/skills`: Java
- `POST /api/v1/publish`: Java

## Java Parity Checklist Outcome

- Java reference: `SkillPublishService` and portal publish aliases.
- API contract: covered for stable success response envelope fields through Vite proxy.
- Authorization/session behavior: covered only for local mock-user bridge; OAuth/session/API-token
  remain Java-owned.
- Database transaction atomicity: reused from Python publish write path and prior rollback evidence.
- Audit actor/timestamp fields: reused from Python publish side-effect path.
- Storage and side effects: reused from Python publish service path.
- Scanner result boundary: unchanged; scanner handoff is covered, scanner result consumption
  remains a separate milestone.

## Verification

Python targeted tests:

```powershell
cd server-python
$env:UV_CACHE_DIR='server-python\.uv-cache'
uv run pytest tests/test_publish_http_validate.py tests/test_hybrid_makefile.py -q
```

Result:

- `14 passed, 1 warning`

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
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-portal-publish-write-ownership-smoke
```

Result:

- `POST /api/v1/skills/global/publish` through Vite: `200`
- `POST /api/web/skills/global/publish` through Vite: `200`
- v1 version status: `PENDING_REVIEW`
- web version status: `PENDING_REVIEW`
- v1 pending review task count: `1`
- web pending review task count: `1`
- root ClawHub publish remains Java-owned through Vite: Java `401`, proxy `401`
- legacy publish remains Java-owned through Vite: Java `401`, proxy `401`
- Playwright smoke: `6 passed`

The gate emitted taskkill warnings during teardown, but a follow-up port check found no listeners
on `3000`, `8080`, `8081`, or `8000`.

## Files Changed

- `server-python/app/api/publish.py`
- `server-python/tests/test_publish_http_validate.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-09-portal-publish-write-ownership.md`
- `docs/backend-python-migration/results/2026-06-09-portal-publish-write-ownership.md`

## Risks

- Root ClawHub publish and legacy publish remain Java-owned.
- Scanner result consumption is still not Python-owned.
- Local mock-user authorization remains the Python-owned auth bridge for publish routes.

## Follow-Up

- Migrate root ClawHub publish and legacy publish when write compatibility is the next priority.
- Plan scanner result processing lifecycle if asynchronous scan completion should be Python-owned
  before broader governance/lifecycle mutations.

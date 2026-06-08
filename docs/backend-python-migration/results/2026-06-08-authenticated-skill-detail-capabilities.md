# Authenticated Skill Detail Capabilities Result

Date: 2026-06-08

## Summary

Extended the Python-owned public skill detail routes with Java-compatible viewer capability flags
for local mock users:

- `GET /api/v1/skills/{namespace}/{slug}`
- `GET /api/web/skills/{namespace}/{slug}`

Anonymous public detail remains unchanged. The route now reads `X-Mock-User-Id`, namespace
membership, and promotion-request state to compute capability flags for public visible skills.

## Behavior Implemented

- Skill owner:
  - `canManageLifecycle: true`
  - `canReport: false`
- Namespace `OWNER` / `ADMIN`:
  - `canManageLifecycle: true`
- Non-global namespace promotion:
  - `canSubmitPromotion: true` only for eligible manager/owner public skills with a published
    version and no `PENDING` or `APPROVED` promotion request.
- Global namespace:
  - `canSubmitPromotion: false`
- Regular or anonymous public viewer:
  - remains non-manager and can report public skills.

## Deferred

- Private, hidden, archived, draft, pending review, rejected owner-preview, and owner-preview review
  comments remain deferred.
- Lifecycle, review, promotion, publish, upload, download, storage, OAuth, token, and CLI auth
  mutations remain Java-owned.
- `SUPER_ADMIN` is not treated as a portal skill-detail manager, matching Java behavior.

## Files Changed

- `server-python/app/api/skills.py`
- `server-python/tests/test_skill_detail.py`
- `server-python/tests/test_skill_detail_repository.py`
- `server-python/tests/test_clawhub_skill_detail.py`
- `server-python/tests/test_hybrid_makefile.py`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/plans/2026-06-08-authenticated-skill-detail-capabilities.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/windows-live-verification.md`

No files under `server/` were modified.

## Live Verification

Command:

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-auth-detail-smoke
```

Result:

- `allJavaMatchesPython: true`
- `allPythonMatchesProxyV1: true`
- `allPythonMatchesProxyWeb: true`
- Playwright smoke E2E: `6 passed`

Compared cases:

- anonymous global public skill
- owner global public skill
- owner team public skill
- namespace admin team public skill
- promotion-blocked team public skill

Artifact:

- `.dev/auth-detail-contract-result.json`

Cleanup check:

- Docker containers: none running.
- Ports `3000`, `8080`, and `8081`: no `LISTENING` entries; only `TIME_WAIT` entries remained.

## Unit And Static Verification

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest
```

Result:

- `109 passed, 1 warning`

```powershell
cd web
node_modules\.bin\vitest.CMD vite.config.test.ts --run
```

Result:

- `16 passed`

```powershell
cd web
node_modules\.bin\tsc.CMD --noEmit
```

Result:

- exit code `0`

## Risks

- This is still a local mock-user bridge, not complete production auth/session behavior.
- Python-owned detail still uses the public visibility boundary. Owner/admin access to non-public
  records requires a separate owner-preview/non-public visibility milestone.
- Promotion capability is read-only in this milestone; promotion submission remains Java-owned.

## Follow-Up

- Decide whether the next Group C milestone should add viewer-specific search/list behavior,
  owner-preview visibility, or broader session-cookie compatibility.
- Do not start publish/upload until auth and storage assumptions are explicitly planned.

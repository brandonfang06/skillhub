# Publish HTTP Validate Route Adapter Result

## Summary

Moved the CLI publish validate-only route to Python:

- `POST /api/cli/v1/skills/{namespace}/publish/validate`

No publish write route was moved in this milestone.

## Route Ownership

Changed:

- `POST /api/cli/v1/skills/{namespace}/publish/validate`: Java -> Python

Still Java-owned:

- `POST /api/v1/skills`
- `POST /api/v1/publish`
- `POST /api/v1/skills/{namespace}/publish`
- `POST /api/web/skills/{namespace}/publish`
- `POST /api/cli/v1/skills/{namespace}/publish`

## Implemented

- Added FastAPI multipart adapter for CLI publish validation.
- Added `python-multipart` dependency for FastAPI form parsing.
- Reused existing Python zip extraction, package validation, and dry-run model.
- Used the local `X-Mock-User-Id` auth bridge and platform roles for `SUPER_ADMIN` dry-run behavior.
- Added Vite proxy ownership for the validate-only route.
- Added Windows live gate `verify-publish-http-validate-smoke`.

## Java Parity Checklist Outcome

| Area | Outcome | Notes |
| --- | --- | --- |
| API contract | covered | Multipart `file` plus optional `visibility`; response data matches Java dry-run fields. |
| Auth/session | covered for local bridge | Missing `X-Mock-User-Id` returns `401`; OAuth/session remains Java-owned. |
| Authorization | covered by dry-run model | Namespace membership and platform role behavior use existing dry-run repository. |
| Database transaction atomicity | not applicable | Validate-only route does not write DB records. |
| Audit actor/timestamp fields | not applicable | No audit writes. |
| Storage and side effects | not applicable | Uploaded zip is read for validation only; no object storage write. |
| Live verification evidence | covered | Java/Python/proxy validate response fields matched; publish write routes remained Java-owned. |

## Tests

Passed:

```powershell
$env:UV_CACHE_DIR='.uv-cache'
Push-Location server-python
try {
  uv run pytest tests/test_publish_http_validate.py tests/test_publish_dry_run.py tests/test_publish_package.py tests/test_hybrid_makefile.py -q
} finally {
  Pop-Location
}
```

Result: `77 passed, 1 warning`.

Passed:

```powershell
$env:COREPACK_HOME=(Join-Path (Get-Location) '.dev\corepack')
Push-Location web
try {
  corepack pnpm test vite.config.test.ts --run
} finally {
  Pop-Location
}
```

Result: `19 passed`.

Passed:

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
$env:COREPACK_HOME=(Join-Path (Get-Location) '.dev\corepack')
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-http-validate-smoke
```

Result:

- Python route tests: `71 passed, 1 warning`.
- Java/Python/proxy validate route comparison passed:
  - status `200`
  - `code=0`
  - `valid=true`
  - `errors=[]`
  - `warnings=[]`
  - `resolvedSlug=codex-validate-skill`
  - `resolvedVersion=1.0.0`
- Publish write route ownership checks passed:
  - `POST /api/v1/skills`
  - `POST /api/v1/publish`
  - `POST /api/v1/skills/global/publish`
  - `POST /api/web/skills/global/publish`
  - `POST /api/cli/v1/skills/global/publish`
- Frontend smoke E2E: `6 passed`.

## Risks and Follow-Up

- Python response `msg` remains `response.success.read`, while Java localizes this to Chinese.
  Existing Python migrated routes use message-code style; live comparison intentionally compares
  stable contract fields and ignores localized message text.
- Publish write route migration still needs scanner behavior, storage failure cleanup, and route
  specific CLI or frontend E2E before ownership moves.

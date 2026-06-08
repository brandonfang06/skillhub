# Publish Storage Failure Cleanup Evidence Result

## Summary

Completed publish storage-failure cleanup evidence for direct Python CLI publish.

No route ownership changed.

- `POST /api/cli/v1/skills/{namespace}/publish` remains Java-owned through Vite/proxy.
- Direct Python backend on port `8081` now has regression and live evidence proving storage write
  failure does not commit dangling publish database rows.

## Routes Changed

None.

## Owner Before / After

| Route | Before | After |
| --- | --- | --- |
| `POST /api/cli/v1/skills/{namespace}/publish` through Vite | Java | Java |
| Direct Python `POST /api/cli/v1/skills/{namespace}/publish` | Python foundation only | Python foundation only |

## Behavior Verified

- Python publish orchestration keeps prepare, storage write, finalize, and side effects inside one
  SQLAlchemy transaction.
- If storage write raises after version allocation, the transaction exits with the exception.
- Finalize and side-effect writes are not executed.
- Live Postgres verification confirms no committed `skill`, `skill_version`, `skill_file`,
  `review_task`, or `security_audit` rows remain for the failed publish slug.

## Java Parity Checklist Outcome

- Java reference: `SkillPublishService`.
- API contract: route ownership unchanged; direct Python failure currently returns HTTP `500`.
- Authorization/session behavior: unchanged; local mock-user bridge remains the direct Python
  publish identity source.
- Database transaction atomicity: covered by unit test and Windows live gate.
- Audit actor/timestamp fields: not applicable because the failed transaction is rolled back.
- Storage and side effects: database side effects are rolled back; object-storage compensation for
  partially written files remains out of scope for this milestone.
- Live verification evidence: covered by Windows live gate.

## Verification

Narrow tests:

```powershell
cd server-python
$env:UV_CACHE_DIR='server-python\.uv-cache'
uv run pytest tests/test_publish_orchestration.py tests/test_publish_http_validate.py tests/test_hybrid_makefile.py -q
```

Result:

- `19 passed, 1 warning`

Windows live gate:

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
$env:COREPACK_HOME=(Join-Path (Get-Location) '.dev\corepack')
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-storage-failure-cleanup-smoke
```

Result:

- Python direct publish failure status: `500`
- Failed slug: `codex-storage-failure-20260609073617470`
- DB `skillCount`: `0`
- DB `versionCount`: `0`
- DB `fileCount`: `0`
- DB `reviewTaskCount`: `0`
- DB `securityAuditCount`: `0`
- Vite proxy ownership check: Java status `401`, proxy status `401`
- Playwright smoke: `6 passed`

The gate emitted taskkill warnings during teardown, but a follow-up port check found no listeners
on `3000`, `8080`, `8081`, or `8000`.

## Risks

- This milestone proves database rollback only. It does not introduce object-storage compensation
  for partially written files if a future storage backend can fail after writing some objects.
- Scanner result processing remains a later publish migration concern.
- Publish write ownership through Vite is still intentionally Java-owned.

## Follow-Up

- Define scanner result processing boundaries.
- Run a repeated publish Java/Python live matrix before moving
  `POST /api/cli/v1/skills/{namespace}/publish` ownership.

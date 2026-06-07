# Public Labels Live Verification Plan

Date: 2026-06-07

## Milestone

Verify the already-migrated public labels API against a live Java/Python/Vite/PostgreSQL hybrid
stack before starting the next API migration.

This milestone does not migrate a new API.

## API Group

| Method | Path | Owner |
| --- | --- | --- |
| GET | `/api/v1/labels` | python |
| GET | `/api/web/labels` | python |

## Gate Rule

Every future API migration must pass a live verification gate before the next API milestone starts.

Minimum gate:

- Java reference endpoint is reachable when applicable.
- Python-owned endpoint is reachable.
- Java/Python contract comparison is recorded when the route previously existed in Java.
- Vite proxy route returns the Python-owned response.
- Frontend smoke E2E passes, or the blocker is recorded before continuing.
- `git diff --name-only -- server` returns no paths.

## Allowed Changes

- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-07-public-labels-live-verification.md`
- `docs/backend-python-migration/results/2026-06-07-public-labels-live-verification.md`
- `docs/backend-python-migration/windows-live-verification.md`
- `scripts/dev-hybrid.ps1` only for Windows process-launch compatibility fixes.

## Forbidden Changes

- Any file under `server/`
- Runtime implementation changes
- Vite proxy route changes
- Python API behavior changes

## Verification Steps

1. Start the hybrid stack on Windows:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 up
```

2. Compare Java and Python direct responses:

```powershell
Invoke-RestMethod http://localhost:8080/api/v1/labels
Invoke-RestMethod http://localhost:8081/api/v1/labels
```

Comparison rule:

- Compare `code`, `msg`, and `data`.
- Ignore `timestamp` and `requestId`.

3. Verify Vite proxy ownership:

```powershell
Invoke-RestMethod http://localhost:3000/api/v1/labels
Invoke-RestMethod http://localhost:3000/api/web/labels
```

4. Run frontend smoke E2E:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 e2e-smoke
```

5. Confirm Java boundary:

```powershell
git diff --name-only -- server
```

## Acceptance Criteria

- Hybrid stack starts successfully.
- Java and Python direct `GET /api/v1/labels` responses match for `code`, `msg`, and `data`.
- Vite proxy routes `/api/v1/labels` and `/api/web/labels` to Python successfully.
- Frontend smoke E2E passes.
- Result document records command outputs and any follow-up.
- No `server/` files are changed.

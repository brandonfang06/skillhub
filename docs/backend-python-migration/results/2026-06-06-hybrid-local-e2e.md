# Hybrid Local E2E Result

## Routes Changed

No route ownership changed in this milestone.

## Files Changed

- Updated `Makefile` with hybrid dev and E2E targets.
- Added `scripts/dev-hybrid.ps1` for Windows PowerShell local orchestration.
- Added `server-python/tests/test_hybrid_makefile.py` to verify hybrid workflow
  wiring.
- Added `docs/backend-python-migration/hybrid-local-e2e.md`.
- Added this result file.

## Commands Added

PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 up
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 status
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 e2e-smoke
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 e2e
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 down
```

Makefile:

```bash
make dev-all-hybrid
make test-e2e-smoke-hybrid
make test-e2e-hybrid
make dev-all-down
```

## Tests Run

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest
```

Outcome: 6 tests passed, 1 warning from FastAPI/Starlette TestClient.

```powershell
$tokens=$null
$errors=$null
[System.Management.Automation.Language.Parser]::ParseFile('scripts/dev-hybrid.ps1',[ref]$tokens,[ref]$errors)
```

Outcome: PowerShell script parsed successfully.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 status
```

Outcome: command completed successfully. It reported Docker CLI unavailable in
this environment, then showed Java, Python, and Vite as stopped.

## Boundary Check

`git diff --name-only -- server` produced no output.

## Environment Findings

- PowerShell does not have `make` in PATH in this environment.
- `bash` resolves first to the WindowsApps/WSL shim and fails with a missing
  login session.
- Git `sh.exe` exists at `C:\Program Files\Git\bin\sh.exe`; the PowerShell
  script uses it to start the Java backend.
- Docker CLI is not available in PATH in this environment, so full hybrid
  startup and Playwright E2E could not be run here.

## Known Risks

- `scripts/dev-hybrid.ps1 up/e2e-smoke/e2e` require Docker Desktop, Java 21,
  Git for Windows, Node/Corepack, uv, and free ports `3000`, `8000`, `8080`,
  and `8081`.
- Playwright E2E can still fail if local seed data or browser dependencies are
  missing; this milestone only adds orchestration, not new seed fixtures.

## Follow-Up Work

- Run `scripts/dev-hybrid.ps1 e2e-smoke` on a local machine with Docker
  available.
- Add a smaller hybrid-specific Playwright spec if the existing smoke suite is
  too broad for quick migration checks.


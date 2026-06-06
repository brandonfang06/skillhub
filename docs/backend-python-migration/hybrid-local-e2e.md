# Hybrid Local E2E

Use this workflow when Java, Python, and the Vite frontend must run together.

## PowerShell Workflow

This is the recommended workflow on Windows.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 up
```

The command starts:

- dependency services through Docker Compose
- Java backend on `http://localhost:8080`
- Python backend on `http://localhost:8081`
- Vite frontend on `http://localhost:3000`
- scanner on `http://localhost:8000`

Check status:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 status
```

Run smoke E2E:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 e2e-smoke
```

Run full E2E:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 e2e
```

Stop everything:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 down
```

## Makefile Workflow

Use this when `make` is available in the shell.

```bash
make dev-all-hybrid
make test-e2e-smoke-hybrid
make test-e2e-hybrid
make dev-all-down
```

## Expected Health Checks

Direct Python:

```powershell
curl.exe -i http://localhost:8081/api/v1/health
```

Vite proxy to Python:

```powershell
curl.exe -i http://localhost:3000/api/v1/health
```

Both should return the SkillHub envelope with `data.message` set to `UP`.

## Logs

Logs are written under `.dev/`:

- `.dev/server.log`
- `.dev/python.log`
- `.dev/web.log`

For Makefile users:

```bash
SERVICE=backend make dev-logs
SERVICE=python make dev-logs
SERVICE=frontend make dev-logs
```


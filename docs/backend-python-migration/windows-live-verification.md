# Windows Live Verification Guide

Date: 2026-06-07

This guide is the Windows procedure for Java/Python/Vite coexistence verification during the
backend Python migration.

## Scope

Use this guide when verifying migrated Python-owned APIs against the live Java backend and the
Vite dev proxy on Windows.

Do not edit any file under `server/` during verification. Java is a read-only reference runtime.

## Prerequisites

- Docker Desktop engine is running.
- Git Bash is installed at `C:\Program Files\Git\bin\sh.exe`.
- Java 21 JDK is available.
- `uv` is available for `server-python/`.
- Node/corepack/pnpm are available for `web/`.

Recommended Java install:

```powershell
winget install --id EclipseAdoptium.Temurin.21.JDK -e --accept-package-agreements --accept-source-agreements
```

If Temurin is not installed but PyCharm 2025 is available, this JBR can be used for local
verification:

```powershell
$env:JAVA_HOME = "C:\Program Files\JetBrains\PyCharm 2025.2.1.1\jbr"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
java -version
javac -version
```

Expected major version: `21`.

## Start Hybrid Stack

Run from the repository root in a normal user PowerShell window. Do not use an elevated/admin
PowerShell for normal hybrid verification.

```powershell
$env:Path = "C:\Program Files\Docker\Docker\resources\bin;$env:Path"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 up
```

Expected services:

| Service | URL |
| --- | --- |
| Vite frontend | `http://localhost:3000` |
| Java backend | `http://localhost:8080` |
| Python backend | `http://localhost:8081` |
| Scanner | `http://localhost:8000` |

Logs are under `.dev/`:

- `.dev/server.log`
- `.dev/server.log.err`
- `.dev/python.log`
- `.dev/python.log.err`
- `.dev/web.log`
- `.dev/web.log.err`

## Health Checks

```powershell
Invoke-RestMethod http://localhost:8080/actuator/health
Invoke-RestMethod http://localhost:8081/api/v1/health
Invoke-RestMethod http://localhost:3000/api/v1/health
Invoke-RestMethod http://localhost:8000/health
```

## Public Labels Contract Check

Direct Java reference:

```powershell
$java = Invoke-RestMethod http://localhost:8080/api/v1/labels
```

Direct Python:

```powershell
$python = Invoke-RestMethod http://localhost:8081/api/v1/labels
```

Vite proxy to Python-owned routes:

```powershell
$proxyV1 = Invoke-RestMethod http://localhost:3000/api/v1/labels
$proxyWeb = Invoke-RestMethod http://localhost:3000/api/web/labels
```

Compare only stable contract fields:

```powershell
($java | Select-Object code,msg,data | ConvertTo-Json -Depth 20) -eq `
  ($python | Select-Object code,msg,data | ConvertTo-Json -Depth 20)

($python | Select-Object code,msg,data | ConvertTo-Json -Depth 20) -eq `
  ($proxyV1 | Select-Object code,msg,data | ConvertTo-Json -Depth 20)

($python | Select-Object code,msg,data | ConvertTo-Json -Depth 20) -eq `
  ($proxyWeb | Select-Object code,msg,data | ConvertTo-Json -Depth 20)
```

Ignore volatile fields such as `timestamp` and `requestId`.

## Smoke E2E

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 e2e-smoke
```

## Shutdown

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 down
```

## Agent/Codex Notes

Docker Desktop does not require an admin PowerShell for this project once the Windows user is in
the `docker-users` group and Docker Desktop is already running.

Verification commands should run as the normal Windows user:

```powershell
whoami
whoami /groups | Select-String docker-users
docker version
```

Expected:

- `whoami` is the normal interactive user.
- `docker-users` appears in the enabled groups.
- `docker version` shows both Client and Server.

Do not start Java/Python/Vite dev servers from an elevated PowerShell. Elevated processes can leave
ports `3000`, `8080`, and `8081` owned by an admin token, which a normal user shell cannot stop.
If that happened once during troubleshooting, close those elevated processes manually or reboot one
time. After that, use only normal PowerShell for:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 down
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 up
```

The Codex sandbox may not have permission to access the Docker Desktop named pipe or the user's
Docker config if it is not running as the interactive user. In that case, fix the user/session
context instead of switching to admin PowerShell for every verification.

Known sandbox symptoms:

- `permission denied while trying to connect to the docker API at npipe:////./pipe/docker_engine`
- `WARNING: Error loading config file: open C:\Users\USER\.docker\config.json: Access is denied`
- Maven dependency download failure such as `Permission denied: getsockopt`

For Maven dependency downloads, rerun the build with an approved external-network command. Do not
modify Java sources or resources.

## Troubleshooting From 2026-06-07

Observed failures:

1. Docker Desktop could not start until WSL/Docker Desktop distro state was reset.
2. `scripts/dev-hybrid.ps1` redirected stdout and stderr to the same file. Windows PowerShell
   rejects that with:
   `RedirectStandardOutput 與 RedirectStandardError 相同`.
3. Java backend failed with:
   `The JAVA_HOME environment variable is not defined correctly`.
4. The sandbox did not initially have Java 21 on PATH. PyCharm JBR 21 was present and usable.
5. Maven dependency download was blocked by sandbox networking until rerun with external-network
   permission.
6. Python labels returned 500 because the default Python DB password was `skillhub`, while Docker
   Compose and Java local config use `skillhub_dev`.
7. `dev-hybrid.ps1 down` removed pid files but left child Java/Python/Vite processes running on
   Windows. The script now uses process-tree and port fallback cleanup.

Root causes found during the failed verification session:

- Early attempts used an elevated/admin PowerShell to reach Docker Desktop. That created dev server
  processes that the normal user session could not later stop.
- Python's default database URL did not match `docker-compose.yml`.
- Windows process cleanup needed process-tree and port fallback handling.

Required next action:

- Ensure no admin-owned stale processes are listening on `3000`, `8080`, or `8081`.
- Run `scripts\dev-hybrid.ps1 up` from a normal user PowerShell after confirming Java 21 is
  installed or `JAVA_HOME` points to a valid JDK.
- Only after all four health checks pass, perform Java/Python/proxy contract comparison and smoke
  E2E.

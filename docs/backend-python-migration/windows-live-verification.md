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

Run from the repository root in a normal user PowerShell window:

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

The Codex sandbox may not have permission to access the Docker Desktop named pipe or the user's
Docker config. In that case, run Docker-dependent commands in the normal Windows user session and
write logs under `C:\tmp\`.

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

Root cause for the failed verification session:

- The hybrid stack was not fully started. Docker dependencies, Python, and Vite reached listening
  ports, but Java backend was not reliably started by the agent-controlled Windows sandbox before
  the verification attempt was stopped.

Required next action:

- Run `scripts\dev-hybrid.ps1 up` from a normal user PowerShell after confirming Java 21 is
  installed or `JAVA_HOME` points to a valid JDK.
- Only after all four health checks pass, perform Java/Python/proxy contract comparison and smoke
  E2E.

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
- Docker Desktop exposes the daemon on `tcp://localhost:2375` when running from the Codex sandbox.
- The Codex sandbox account can traverse `C:\Users\USER` when the workspace lives under OneDrive.

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
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
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

## One-Command Labels Verification Gate

For the migrated public labels API, prefer the one-command gate because it keeps Java, Python, Vite,
contract comparison, Playwright smoke E2E, and cleanup inside one PowerShell lifecycle:

```powershell
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-labels-smoke
```

Expected result:

```text
Java backend ready.
Python backend ready.
Scanner ready.
Vite frontend ready.
Vite proxy to Python health route ready.
javaMatchesPython: true
pythonMatchesProxyV1: true
pythonMatchesProxyWeb: true
6 passed
```

The command writes the latest labels comparison summary to:

```text
.dev/labels-contract-result.json
```

Playwright browser binaries are installed under:

```text
.dev/ms-playwright
```

The first run may need network access to download Chromium. After download, later runs reuse the
workspace-local browser binaries.

## One-Command Skill Detail Verification Gate

For the migrated public skill detail API, use the dedicated gate:

```powershell
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-detail-smoke
```

Expected result:

```text
javaMatchesPython: true
pythonMatchesProxyV1: true
pythonMatchesProxyWeb: true
hidden.matches: true
noLatest.matches: true
archivedNamespace.matches: true
6 passed
```

The command writes the latest detail comparison summary to:

```text
.dev/detail-contract-result.json
```

The detail comparison normalizes only the JSON numeric scale for `ratingAvg`; Java may preserve
BigDecimal scale such as `4.50`, while Python serializes the same JSON number as `4.5`.

## One-Command Portal Search Verification Gate

For the migrated public portal skill search API, use:

```powershell
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-search-smoke
```

Expected result:

```text
allJavaMatchesPython: true
allPythonMatchesProxyWeb: true
v1SkillsRemainsJava: true
6 passed
```

The command writes the latest search comparison summary to:

```text
.dev/search-contract-result.json
```

This gate intentionally verifies that `/api/v1/skills` still has the Java ClawHub list shape.

## One-Command ClawHub Search Verification Gate

For the migrated ClawHub compatibility search API, use:

```powershell
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-clawhub-search-smoke
```

Expected result:

```text
javaMatchesPython: true
pythonMatchesProxy: true
v1SkillsRemainsJava: true
plainShape: true
6 passed
```

The command writes the latest ClawHub search comparison summary to:

```text
.dev/clawhub-search-contract-result.json
```

## One-Command ClawHub Resolve Verification Gate

For the migrated ClawHub compatibility resolve API, use:

```powershell
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-clawhub-resolve-smoke
```

Expected result:

```text
query.javaMatchesPython: true
query.pythonMatchesProxy: true
path.javaMatchesPython: true
path.pythonMatchesProxy: true
plainShape: true
downloadRemainsJava: true
v1SkillDetailRemainsJava: true
6 passed
```

The command writes the latest ClawHub resolve comparison summary to:

```text
.dev/clawhub-resolve-contract-result.json
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

For this Windows setup, the stable no-admin sandbox path is:

1. Add the sandbox account to `docker-users`.
2. Enable Docker Desktop setting `Expose daemon on tcp://localhost:2375 without TLS`.
3. Set `DOCKER_HOST=tcp://127.0.0.1:2375` before Docker commands.
4. Set `DOCKER_CONFIG` to `.dev\docker-config` so the sandbox does not need
   `C:\Users\USER\.docker\config.json`.
5. Grant read/traverse permission to `CodexSandboxUsers` on `C:\Users\USER` when the workspace is
   under `C:\Users\USER\OneDrive\...`; Vite/esbuild traverses parent directories during startup.

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
8. Playwright failed because Chromium was missing under the default user profile path. The script
   now uses workspace-local `.dev/ms-playwright`.
9. `taskkill` can emit access-denied warnings for transient wrapper PIDs in the sandbox. Treat this
   as non-fatal when `netstat` shows no `LISTENING` entries and Docker Compose has no running
   containers.

Root causes found during the failed verification session:

- Early attempts used an elevated/admin PowerShell to reach Docker Desktop. That created dev server
  processes that the normal user session could not later stop.
- Python's default database URL did not match `docker-compose.yml`.
- Windows process cleanup needed process-tree and port fallback handling.

Verification status from 2026-06-07:

- `scripts\dev-hybrid.ps1 verify-labels-smoke` passed.
- Labels `code`, `msg`, and `data` matched between Java, Python, and both Vite proxy routes.
- Playwright smoke E2E passed: `6 passed`.
- Shutdown left no `LISTENING` ports on `3000`, `8080`, or `8081`; only `TIME_WAIT` remained.

## Lessons Learned & Future Testing Strategy (Timing & Tools)

1. **Spring Boot Boot-up Timing Delay**:
   - Spring Boot takes about 10-12 seconds to fully initialize Tomcat and database connections.
   - **Failed Experience**: Running `scripts/dev-hybrid.ps1 up` in the background and immediately executing `curl` resulted in `curl: (7) Failed to connect` because port 8080 was not yet open.
   - **Solution**: Always wait for `dev-hybrid.ps1 up` to complete health check wait loops synchronously, or manually verify `/actuator/health` returns `200 OK` before running API requests.

2. **PowerShell `curl` Alias Conflict**:
   - On Windows PowerShell, the command `curl` is aliased to `Invoke-WebRequest`.
   - **Failed Experience**: Running `curl -s -i --max-time 5 ...` threw a parameter binding exception: `MissingArgument,Microsoft.PowerShell.Commands.InvokeWebRequestCommand`.
   - **Solution**: Always use `curl.exe` explicitly when writing test requests, or use `Invoke-RestMethod` / `Invoke-WebRequest` natively in PowerShell.

3. **Future Testing Approach**:
   - Implement automated, single-command contract verification actions (e.g. `verify-files-smoke` in `dev-hybrid.ps1`) to boot the stack, perform comparisons, run E2E, and tear it down automatically. This eliminates manual timing issues and guarantees clean environments.

# Public Labels Live Verification Result

Date: 2026-06-07

Status: passed

## Scope

Routes under verification:

| Method | Path | Expected Owner |
| --- | --- | --- |
| GET | `/api/v1/labels` | python |
| GET | `/api/web/labels` | python |

This milestone did not migrate a new API.

## What Passed

- Docker Desktop engine was repaired and reached running state.
- Docker dependency services were started successfully:
  - PostgreSQL
  - Redis
  - MinIO
  - Scanner
- Python backend reached `0.0.0.0:8081`.
- Vite frontend reached `0.0.0.0:3000`.
- Maven package succeeded after external network permission allowed dependency downloads.
- Java application proved it can start in foreground with PyCharm JBR 21 and the local Docker
  PostgreSQL database.
- On 2026-06-07 follow-up, normal user Docker access was confirmed:
  - `whoami`: `desktop-jhkjedh\user`
  - `docker-users` group enabled
  - `docker version` returned both Client and Server
- Hybrid health checks passed while the stale elevated dev server processes were still running:
  - Java `http://localhost:8080/actuator/health`: `UP`
  - Python `http://localhost:8081/api/v1/health`: `code=0`
  - Vite proxy `http://localhost:3000/api/v1/health`: `code=0`
  - Scanner `http://localhost:8000/health`: `healthy`
- Python unit tests passed after fixing config:
  - `cd server-python; uv run pytest`
  - Result: `17 passed, 1 warning`
- Windows live verification passed with the repo script:

```powershell
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-labels-smoke
```

Result:

```text
Java backend ready.
Python backend ready.
Scanner ready.
Vite frontend ready.
Vite proxy to Python health route ready.
javaMatchesPython: true
pythonMatchesProxyV1: true
pythonMatchesProxyWeb: true
6 passed (19.0s)
```

The verified stable fields were `code`, `msg`, and `data`. Volatile `timestamp` and `requestId`
were intentionally ignored.

After shutdown, `docker compose -p skillhub ps` returned no running containers. `netstat` showed no
`LISTENING` entries for `3000`, `8080`, or `8081`; only short-lived `TIME_WAIT` sockets remained.

- General Windows smoke E2E action also passed after the workspace-local Playwright browser path
  was added:

```powershell
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 e2e-smoke
```

Result:

```text
6 passed (14.4s)
```

## What Failed And Was Fixed

Earlier verification attempts exposed these issues:

- The agent-controlled Windows sandbox could start Java/Python/Vite, but detached child processes
  were unreliable after the command ended. The script now provides `verify-labels-smoke` so the live
  stack, labels comparison, smoke E2E, and cleanup run in one PowerShell lifecycle.
- Direct Python labels initially returned HTTP 500 because the Python default database URL used
  password `skillhub`; Docker Compose and Java local config use `skillhub_dev`.
- Labels contract comparison initially failed because Python returned `msg:
  "response.success.read"` while Java returns localized `msg: "获取成功"`. Python labels now match
  the Java contract.
- Playwright initially failed because Chromium was not installed. The script now uses
  `.dev/ms-playwright` through `PLAYWRIGHT_BROWSERS_PATH` so browser binaries are workspace-local.
- `taskkill` stderr from Windows cleanup could terminate the script. Cleanup now warns and
  continues to port cleanup and Docker Compose shutdown.

## Evidence

Initial script failure:

```text
RedirectStandardOutput 與 RedirectStandardError 相同
```

Java environment failure:

```text
The JAVA_HOME environment variable is not defined correctly,
this environment variable is needed to run this program.
```

Sandbox Maven network failure:

```text
Could not transfer artifact org.springframework.boot:spring-boot-starter-parent:pom:3.2.3
Permission denied: getsockopt
```

Foreground Java proof:

```text
Tomcat started on port 8080 (http) with context path ''
Started SkillhubApplication
```

Python labels failure:

```text
asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "skillhub"
```

Initial labels contract mismatch:

```text
javaMatchesPython: false
pythonStatus.msg: response.success.read
```

Playwright browser failure:

```text
Executable doesn't exist at C:\Users\USER\AppData\Local\ms-playwright\...
Please run the following command to download new browsers:
npx playwright install
```

Stale elevated process cleanup failure from earlier troubleshooting:

```text
ERROR: The process with PID 30212 (child process of PID 1320) could not be terminated.
Reason: Access is denied.
ERROR: The process with PID 29472 (child process of PID 27880) could not be terminated.
Reason: Access is denied.
ERROR: The process with PID 8548 (child process of PID 19204) could not be terminated.
Reason: Access is denied.
```

## Changes Made For Verification

- `scripts/dev-hybrid.ps1`
  - Split stdout and stderr logs into separate files because Windows PowerShell cannot redirect
    both streams to the same file in `Start-Process`.
  - Added Java home detection for common Windows locations, including Temurin, Microsoft JDK,
    `C:\Program Files\Java`, and PyCharm JBR.
  - Fixed Python `UV_CACHE_DIR` PowerShell quoting.
  - Added process-tree cleanup and port fallback cleanup for `down` on Windows.
  - Added `verify-labels-smoke` to run health checks, labels contract comparison, Playwright smoke
    E2E, and cleanup in one command.
  - Added workspace-local Playwright browser management under `.dev/ms-playwright`.
  - Applied the same workspace-local Playwright browser setup to `e2e-smoke` and `e2e`.

- `server-python/app/core/config.py`
  - Changed the default local Docker database URL to use `skillhub_dev`.

- `server-python/app/api/labels.py`
  - Aligned the public labels success `msg` with Java's localized `response.success.read`
    resolution.

- `server-python/tests/test_config.py`
  - Added coverage for the default Docker-compatible database URL and env override behavior.

- `server-python/tests/test_labels.py`
  - Updated labels envelope coverage for the Java-compatible success message.

- `server-python/tests/test_hybrid_makefile.py`
  - Added coverage for Windows process cleanup support in `scripts/dev-hybrid.ps1`.
  - Added coverage for the live labels verification action and workspace-local Playwright browser
    path.

- `docs/backend-python-migration/windows-live-verification.md`
  - Added the Windows live verification procedure and troubleshooting notes.
  - Documented the no-admin Docker Desktop workflow.

## Boundary Check

No tracked source changes under `server/` are intended or allowed.

The Java build may create ignored build artifacts under `server/**/target/` during local runtime
verification. These must not be staged or committed.

Executed check before commit:

```powershell
git diff --name-only -- server
```

Expected and observed output: empty.

## Follow-Up

Future API migrations must run the live verification gate before moving to the next API.

For Windows public labels verification, use:

```powershell
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-labels-smoke
```

For the next API, keep the same gate shape:

- Java reference endpoint reachable when applicable.
- Python direct endpoint reachable.
- Vite proxy endpoint routes to Python for Python-owned paths.
- Stable `code`, `msg`, and `data` comparison passes unless the milestone plan explicitly narrows
  the comparison rule.
- Frontend smoke E2E passes.
- `git diff --name-only -- server` remains empty.

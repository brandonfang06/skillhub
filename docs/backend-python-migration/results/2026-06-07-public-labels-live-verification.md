# Public Labels Live Verification Result

Date: 2026-06-07

Status: blocked

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

## What Failed

The full live verification gate did not pass.

First failure:

Java backend was not reliably kept running as a detached process from the earlier
agent-controlled Windows sandbox before the verification session was stopped. Because Java was not
available on `localhost:8080` at the time of comparison, these required checks were not completed:

- Direct Java `GET /api/v1/labels`
- Direct Python-vs-Java stable contract comparison
- Vite proxy comparison for `/api/v1/labels`
- Vite proxy comparison for `/api/web/labels`
- Frontend smoke E2E

Follow-up failure:

After the hybrid stack became reachable, direct Python labels failed with HTTP 500. Root cause was
Python using a default database URL with password `skillhub`, while `docker-compose.yml` and Java
local config use `skillhub_dev`.

After fixing that config, the currently running Python process still used the stale DB engine. A
restart was required, but the old Java/Python/Vite processes had been started from an elevated
PowerShell during earlier troubleshooting and could not be terminated from the normal user session:

```text
ERROR: The process with PID 30212 could not be terminated.
Reason: Access is denied.
```

Because stale admin-owned processes still occupy `3000`, `8080`, and `8081`, contract comparison
and smoke E2E remain blocked until those processes are manually closed or the machine is rebooted
once.

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

Stale elevated process cleanup failure:

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

- `server-python/app/core/config.py`
  - Changed the default local Docker database URL to use `skillhub_dev`.

- `server-python/tests/test_config.py`
  - Added coverage for the default Docker-compatible database URL and env override behavior.

- `server-python/tests/test_hybrid_makefile.py`
  - Added coverage for Windows process cleanup support in `scripts/dev-hybrid.ps1`.

- `docs/backend-python-migration/windows-live-verification.md`
  - Added the Windows live verification procedure and troubleshooting notes.
  - Documented the no-admin Docker Desktop workflow.

## Boundary Check

No tracked source changes under `server/` are intended or allowed.

The Java build may create ignored build artifacts under `server/**/target/` during local runtime
verification. These must not be staged or committed.

Required check before any commit:

```powershell
git diff --name-only -- server
```

Expected output: empty.

## Follow-Up

Before starting the next API migration, complete the Windows live verification from a normal user
PowerShell session:

First ensure no stale elevated processes listen on `3000`, `8080`, or `8081`. If the process owner
is elevated/admin and normal `taskkill` returns `Access is denied`, close the elevated terminal or
reboot once. Future runs should not use admin PowerShell.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 up
```

Then run:

```powershell
Invoke-RestMethod http://localhost:8080/actuator/health
Invoke-RestMethod http://localhost:8081/api/v1/health
Invoke-RestMethod http://localhost:3000/api/v1/health
Invoke-RestMethod http://localhost:8000/health
```

Only after those health checks pass should the labels contract comparison and frontend smoke E2E
be rerun.

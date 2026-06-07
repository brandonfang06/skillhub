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

## What Failed

The full live verification gate did not pass.

Java backend was not reliably kept running as a detached process from the agent-controlled Windows
sandbox before the verification session was stopped. Because Java was not available on
`localhost:8080` at the time of comparison, these required checks were not completed:

- Direct Java `GET /api/v1/labels`
- Direct Python-vs-Java stable contract comparison
- Vite proxy comparison for `/api/v1/labels`
- Vite proxy comparison for `/api/web/labels`
- Frontend smoke E2E

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

## Changes Made For Verification

- `scripts/dev-hybrid.ps1`
  - Split stdout and stderr logs into separate files because Windows PowerShell cannot redirect
    both streams to the same file in `Start-Process`.
  - Added Java home detection for common Windows locations, including Temurin, Microsoft JDK,
    `C:\Program Files\Java`, and PyCharm JBR.
  - Fixed Python `UV_CACHE_DIR` PowerShell quoting.

- `docs/backend-python-migration/windows-live-verification.md`
  - Added the Windows live verification procedure and troubleshooting notes.

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

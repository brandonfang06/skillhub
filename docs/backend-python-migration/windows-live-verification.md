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

## One-Command ClawHub Skill Detail Verification Gate

For the migrated ClawHub compatibility skill detail API, use:

```powershell
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-clawhub-skill-smoke
```

Expected result:

```text
javaMatchesPython: true
pythonMatchesProxy: true
plainShape: true
v1SkillsListRemainsJava: true
downloadRemainsJava: true
deleteRemainsJava: true
undeleteRemainsJava: true
6 passed
```

The command writes the latest ClawHub skill detail comparison summary to:

```text
.dev/clawhub-skill-contract-result.json
```

This gate intentionally verifies the method boundary:

- `GET /api/v1/skills/{canonicalSlug}` reaches Python.
- `DELETE /api/v1/skills/{canonicalSlug}` still follows Java status behavior through Vite.
- `POST /api/v1/skills/{canonicalSlug}/undelete` still follows Java status behavior through Vite.
- `GET /api/v1/skills` is verified by the separate ClawHub skills list gate below.
- `GET /api/v1/download/{canonicalSlug}` remains the Java redirect route.

## One-Command ClawHub Skills List Verification Gate

For the migrated ClawHub compatibility skills list API, use:

```powershell
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-clawhub-list-smoke
```

Expected result:

```text
allJavaMatchesPython: true
allPythonMatchesProxy: true
plainShape: true
rootPostRemainsJava: true
deleteRemainsJava: true
downloadRemainsJava: true
6 passed
```

The command writes the latest ClawHub list comparison summary to:

```text
.dev/clawhub-list-contract-result.json
```

This gate verifies the Group A method boundary:

- `GET /api/v1/skills` reaches Python.
- `POST /api/v1/skills` still follows Java status behavior through Vite.
- `DELETE /api/v1/skills/{canonicalSlug}` still follows Java status behavior through Vite.
- `GET /api/v1/download/{canonicalSlug}` remains the Java redirect route.

## One-Command Auth Current User Verification Gate

For the migrated current-user bridge, use:

```powershell
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-auth-me-smoke
```

Expected result:

```text
allJavaMatchesPython: true
allPythonMatchesProxy: true
noHeaderMatches: true
authMethodsRemainsJava: true
6 passed
```

The command writes the latest auth comparison summary to:

```text
.dev/auth-me-contract-result.json
```

This gate verifies the Group C auth boundary:

- `GET /api/v1/auth/me` reaches Python through Vite.
- `X-Mock-User-Id: local-user` and `X-Mock-User-Id: local-admin` match Java direct behavior.
- Missing mock-user header returns `401` for Java, Python, and Vite.
- `GET /api/v1/auth/methods` still matches Java through Vite.
- OAuth, login, token, session bootstrap, and CLI auth routes remain Java-owned.

## One-Command Authenticated Skill Detail Verification Gate

For the migrated viewer-specific skill detail capability flags, use:

```powershell
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-auth-detail-smoke
```

Expected result:

```text
allJavaMatchesPython: true
allPythonMatchesProxyV1: true
allPythonMatchesProxyWeb: true
6 passed
```

The command writes the latest authenticated detail comparison summary to:

```text
.dev/auth-detail-contract-result.json
```

This gate verifies the Group C skill-detail boundary:

- anonymous public detail remains unchanged.
- owner requests via `X-Mock-User-Id: local-user` can manage their visible public skill and cannot
  report it.
- namespace `ADMIN` / `OWNER` requests can manage visible public team skills.
- non-global promotion capability is enabled only when Java enables it.
- pending promotion requests block `canSubmitPromotion`.
- owner preview and non-public visibility remain deferred.

## One-Command Owner Preview Skill Detail Verification Gate

For the migrated manager-only owner preview projection on public skill detail, use:

```powershell
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-owner-preview-detail-smoke
```

Expected result:

```text
allJavaMatchesPython: true
allPythonMatchesProxyV1: true
allPythonMatchesProxyWeb: true
anonymousHidesPreview: true
ownerSeesRejectedPreview: true
ownerSeesReviewComment: true
namespaceAdminSeesRejectedPreview: true
publishedHeadlineKept: true
6 passed
```

The command writes the latest owner preview detail comparison summary to:

```text
.dev/owner-preview-detail-contract-result.json
```

This gate verifies the Group C owner-preview boundary:

- anonymous public detail does not expose `ownerPreviewVersion`.
- owner requests via `X-Mock-User-Id: local-user` expose newer rejected owner preview and review
  comment.
- namespace `ADMIN` requests expose the same owner preview projection.
- published public skills keep `headlineVersion` / `publishedVersion` as the published version and
  keep `resolutionMode: PUBLISHED`.
- version detail, version list, file metadata, resolve, downloads, non-public visibility, and
  lifecycle mutations remain outside this gate.

## One-Command Owner Preview Version Verification Gate

For the migrated manager-only owner preview version list and version detail access, use:

```powershell
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-owner-preview-version-smoke
```

Expected result:

```text
allJavaMatchesPython: true
allPythonMatchesProxyV1: true
allPythonMatchesProxyWeb: true
anonymousListPublishedOnly: true
ownerListIncludesPreviewStates: true
anonymousPendingDetailStatusesMatch: true
6 passed
```

The command writes the latest owner preview version comparison summary to:

```text
.dev/owner-preview-version-contract-result.json
```

This gate verifies the Group C owner-preview version boundary:

- anonymous version list only returns `PUBLISHED`.
- owner and namespace `ADMIN` version lists include manager-visible lifecycle versions.
- owner and namespace `ADMIN` version detail can read `PENDING_REVIEW`.
- anonymous `PENDING_REVIEW` detail is rejected with the same HTTP status through Java, Python, and
  both Vite proxy aliases.
- file metadata, file bytes, downloads, non-public visibility, and lifecycle mutations remain
  outside this gate.

## One-Command Owner Preview File Metadata Verification Gate

For the migrated manager-only owner preview version file metadata access, use:

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-owner-preview-files-smoke
```

Expected result:

```text
allJavaMatchesPython: true
allPythonMatchesProxyV1: true
allPythonMatchesProxyWeb: true
anonymousPublishedFilesSorted: true
ownerPendingFilesSorted: true
anonymousPendingStatusesMatch: true
6 passed
```

The command writes the latest owner preview files comparison summary to:

```text
.dev/owner-preview-files-contract-result.json
```

This gate verifies the Group C owner-preview file metadata boundary:

- anonymous published version file metadata stays public.
- owner requests via `X-Mock-User-Id: local-user` can read `PENDING_REVIEW` version file metadata.
- namespace `ADMIN` requests can read the same `PENDING_REVIEW` version file metadata.
- anonymous `PENDING_REVIEW` file metadata is rejected with the same HTTP status through Java,
  Python, and both Vite proxy aliases.
- tag owner preview, file bytes, downloads, non-public visibility, and lifecycle mutations remain
  outside this gate.

## One-Command Owner Preview Tag File Metadata Verification Gate

For portal tag file metadata authenticated context forwarding and Java-compatible negative
owner-preview tag selector behavior, use:

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-owner-preview-tag-files-smoke
```

Expected result:

```text
allJavaMatchesPython: true
allPythonMatchesProxyV1: true
allPythonMatchesProxyWeb: true
publishedFilesSorted: true
allPendingStatusesMatch: true
allPendingRejected: true
6 passed
```

The command writes the latest owner preview tag files comparison summary to:

```text
.dev/owner-preview-tag-files-contract-result.json
```

This gate verifies the tag file metadata boundary:

- anonymous, owner, and namespace `ADMIN` callers can read published tag file metadata with
  matching Java/Python/Vite contracts.
- anonymous, owner, and namespace `ADMIN` callers are all rejected for `PENDING_REVIEW` tag file
  metadata, matching Java's published-only tag selector behavior.
- route handlers forward local mock-user context, but Python does not broaden Java semantics.
- file bytes, downloads, non-public visibility, and lifecycle mutations remain outside this gate.

## One-Command File Content Read Verification Gate

For portal single-file content read parity, use:

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-file-content-smoke
```

Expected result:

```text
allJavaMatchesPython: true
allPythonMatchesProxyV1: true
allStatusesMatch: true
allExpectedRejections: true
6 passed
```

The command writes the latest file content comparison summary to:

```text
.dev/file-content-contract-result.json
```

This gate verifies the file content read boundary:

- Java, Python, and Vite `/api/v1` match status, content type, byte length, and body bytes.
- anonymous callers can read published version and tag file content.
- owner and namespace `ADMIN` callers can read `PENDING_REVIEW` version file content.
- anonymous callers are rejected for `PENDING_REVIEW` version file content.
- owner and namespace `ADMIN` callers are still rejected for `PENDING_REVIEW` tag file content,
  matching Java's published-only tag selector behavior.
- download routes, counters, bundle objects, non-public visibility, and lifecycle mutations remain
  outside this gate.

## One-Command Owner Preview Resolve Verification Gate

For portal resolve authenticated parity and the Java-compatible negative owner-preview resolve
boundary, use:

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-owner-preview-resolve-smoke
```

Expected result:

```text
allJavaMatchesPython: true
allPythonMatchesProxyV1: true
allPythonMatchesProxyWeb: true
publishedVersionResolved: true
publishedDownloadUrlKept: true
anonymousPendingStatusesMatch: true
ownerPendingStatusesMatch: true
namespaceAdminPendingStatusesMatch: true
6 passed
```

The command writes the latest owner preview resolve comparison summary to:

```text
.dev/owner-preview-resolve-contract-result.json
```

This gate verifies the portal resolve boundary:

- anonymous, owner, and namespace `ADMIN` callers resolve published exact versions with matching
  Java/Python/Vite contracts.
- anonymous, owner, and namespace `ADMIN` callers are all rejected for exact `PENDING_REVIEW`
  resolve, matching Java's published-only `resolveVersion` behavior.
- download URLs stay metadata-only; download endpoints themselves remain Java-owned.
- ClawHub `/api/v1/resolve` routes, file bytes, downloads, non-public visibility, and lifecycle
  mutations remain outside this gate.

## One-Command Owner Preview Version Compare Verification Gate

For the migrated manager-only owner preview version compare route, use:

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-owner-preview-compare-smoke
```

Expected result:

```text
allJavaMatchesPython: true
allPythonMatchesProxyV1: true
allPythonMatchesProxyWeb: true
previewSummaryMatchesFixture: true
previewFilesSorted: true
anonymousPreviewStatusesMatch: true
sameVersionStatusesMatch: true
6 passed
```

The command writes the latest owner preview compare summary to:

```text
.dev/owner-preview-compare-contract-result.json
```

This gate verifies the version compare boundary:

- owner and namespace `ADMIN` callers can compare published-to-`PENDING_REVIEW` versions.
- anonymous published-to-`PENDING_REVIEW` compare is rejected with matching Java/Python/Vite status.
- same-version compare is rejected with matching Java/Python/Vite status.
- Python compare preserves Java text-diff behavior, including the trailing empty line produced by
  Java `split("\\R", -1)` when local storage files end with a newline.
- file bytes/download endpoints, ClawHub routes, non-public visibility, and lifecycle mutations
  remain outside this gate.

## Method-Colliding Route Verification

Some ClawHub compatibility routes use the same path with different HTTP methods. For these routes,
path-only Vite proxy entries are not allowed because they can accidentally proxy Java-owned
mutations to Python.

Required checks for method-colliding migrations:

- Verify the Python-owned method reaches Python.
- Verify Java-owned methods on the same path still reach Java.
- Add Vite config tests using `resolveMethodAwareProxyTarget`.
- Add live gate checks for both method groups before commit.

Method-aware infrastructure is available, but active rules should be enabled only inside the API
milestone that implements the matching Python route.

Active rule requiring live verification:

```text
GET /api/v1/skills/{canonicalSlug} -> Python
POST/DELETE /api/v1/skills/{canonicalSlug} -> Java fallback
GET /api/v1/skills -> Python
POST /api/v1/skills -> Java fallback
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

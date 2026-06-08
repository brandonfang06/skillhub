# File Content Read Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move portal single-file content read routes to Python as the first storage-read
foundation before migrating download routes.

**Architecture:** Add Python storage read helpers that load bytes from the same local storage
fixture path used by Java during Windows live verification. Version file content follows Java's
owner-preview access rules, while tag file content stays published-only because Java tag selectors
do not call owner-preview authorization. Download routes remain Java-owned until a separate
download milestone handles counters, bundle objects, and response headers.

**Tech Stack:** FastAPI on port `8081`, SQLAlchemy async PostgreSQL reads, local filesystem object
storage under `.dev/java-storage`, Vite proxy on port `3000`, Java Spring Boot on port `8080`,
PowerShell live contract gate, Playwright smoke.

---

## Scope

Routes in scope:

- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/file?path={filePath}`
- `GET /api/v1/skills/{namespace}/{slug}/tags/{tagName}/file?path={filePath}`

Behavior in scope:

- Stream/read exact stored file bytes from local object storage.
- Return Java-compatible `application/octet-stream` content type.
- Version file content:
  - published versions are readable by anonymous callers.
  - non-published owner-preview versions are readable by skill owner and namespace `OWNER` /
    `ADMIN` callers.
  - non-manager callers are rejected for non-published versions.
- Tag file content:
  - published tag targets are readable.
  - non-published tag targets remain rejected for anonymous, owner, and namespace admin callers.
- Missing file rows and missing storage objects map to Java-compatible `400` responses.
- Vite proxies only these GET file-content routes to Python.

Behavior intentionally out of scope:

- Do not migrate any `/download` route.
- Do not increment download counters.
- Do not implement object storage writes.
- Do not add MinIO/S3 direct integration yet; use a narrow local-storage abstraction first.
- Do not change file metadata, compare, resolve, publish, review, OAuth, token, session, or
  lifecycle mutation routes.
- Do not modify `server/`.

## Java Reference Findings

Java portal controller routes:

- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/file`
- `GET /api/v1/skills/{namespace}/{slug}/tags/{tagName}/file`

Both return:

```java
ResponseEntity.ok()
        .contentType(MediaType.APPLICATION_OCTET_STREAM)
        .body(new InputStreamResource(content));
```

Java version file content uses:

```java
SkillVersion skillVersion = findVersion(skill, version);
assertPreviewAccessible(skill, skillVersion, version, currentUserId, userNsRoles);
SkillFile file = findFile(skillVersion, filePath);
return readFileContent(file);
```

Java tag file content uses:

```java
SkillVersion skillVersion = resolveVersionEntity(skill, null, tagName, null);
SkillFile file = findFile(skillVersion, filePath);
return readFileContent(file);
```

The tag path remains published-only because `resolveVersionEntity(... tagName ...)` does not use
`assertPreviewAccessible(...)`.

Java `findFile(...)` only sees files that pass `availableFiles(...)`; `availableFiles(...)` filters
out rows whose `storage_key` does not exist. `readFileContent(...)` also maps storage read failures
to `error.skill.file.notFound`.

## Route Ownership

After implementation, update `docs/backend-python-migration/route-registry.md`:

| Method | Path | Owner | Notes |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{namespace}/{slug}/versions/{version}/file` | python | Single file content bytes with manager-only owner-preview access for non-published versions. |
| GET | `/api/v1/skills/{namespace}/{slug}/tags/{tagName}/file` | python | Single file content bytes for published tag targets only. Non-published tag targets remain rejected to match Java. |

No `/api/web/.../file` aliases exist in Java for this milestone.

## Files

Allowed changes:

- Modify `server-python/app/api/skills.py`.
- Create `server-python/tests/test_skill_file_content.py`.
- Modify `web/vite.config.ts`.
- Modify `web/vite.config.test.ts`.
- Modify `scripts/dev-hybrid.ps1`.
- Modify `server-python/tests/test_hybrid_makefile.py`.
- Update `docs/backend-python-migration/migration-sequence-plan.md`.
- Update `docs/backend-python-migration/route-registry.md`.
- Update `docs/backend-python-migration/windows-live-verification.md`.
- Write `docs/backend-python-migration/results/2026-06-08-file-content-read-foundation.md`.

Forbidden changes:

- Do not modify any file under `server/`.
- Do not manually edit `web/src/api/generated/schema.d.ts`.
- Do not add download routes to Python in this milestone.

## TDD Tasks

### Task 1. Route Contract

- [ ] Add failing tests in `server-python/tests/test_skill_file_content.py`:
  - version file content route returns raw bytes and `application/octet-stream`;
  - tag file content route returns raw bytes and `application/octet-stream`;
  - version route forwards `(namespace, slug, version, path, current_user_id)` to injected reader;
  - tag route forwards `(namespace, slug, tagName, path, current_user_id)` to injected reader;
  - blank `X-Mock-User-Id` forwards `None`;
  - injected `SkillResolveError` maps to status `400`.
- [ ] Run:
  - `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_skill_file_content.py -q`
- [ ] Expected before implementation: routes not found.
- [ ] Implement minimal FastAPI routes and injected reader hooks.
- [ ] Re-run focused tests and expect pass.

### Task 2. Local Storage Byte Reader

- [ ] Add failing unit tests for:
  - reading bytes from a storage key under a configured base path;
  - missing storage key raises `SkillResolveError("error.skill.file.notFound")`;
  - path traversal storage keys are rejected.
- [ ] Implement `read_local_storage_bytes(storage_base_path: str, storage_key: str) -> bytes`.
- [ ] Keep `read_local_storage_text(...)` behavior for compare, but let it reuse the byte reader if
  that keeps the code simple.
- [ ] Re-run focused tests.

### Task 3. Version File Content DB Reader

- [ ] Add tests around helper behavior where practical:
  - anonymous published file reads bytes;
  - owner pending file reads bytes;
  - anonymous pending file raises `error.skill.version.notPublished`;
  - missing file raises `error.skill.file.notFound`.
- [ ] Implement `read_skill_version_file_content(...)`:
  - active public skill lookup matching existing version metadata readers;
  - version lookup without published filter;
  - manager check using existing owner/namespace-role helpers;
  - file row lookup by exact `file_path`;
  - storage existence/read through `read_local_storage_bytes(...)`.
- [ ] Re-run focused tests.

### Task 4. Tag File Content DB Reader

- [ ] Add tests around helper behavior where practical:
  - published tag file reads bytes;
  - pending tag target raises the same Java-compatible error for owner/admin as anonymous;
  - missing tag raises `error.skill.tag.notFound`;
  - missing file raises `error.skill.file.notFound`.
- [ ] Implement `read_skill_tag_file_content(...)`:
  - active public skill lookup matching tag metadata reader;
  - `latest` maps to `latest_version_id`;
  - named tag resolves through `skill_tag`;
  - target version must be `PUBLISHED`;
  - file row lookup by exact `file_path`;
  - storage read through `read_local_storage_bytes(...)`.
- [ ] Re-run focused tests.

### Task 5. Proxy And Live Gate

- [ ] Add Vite proxy ownership for:
  - `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/file`
  - `GET /api/v1/skills/{namespace}/{slug}/tags/{tagName}/file`
- [ ] Update Vite proxy tests to prove file content routes go to Python while download routes still
  go to Java.
- [ ] Add `verify-file-content-smoke` to `scripts/dev-hybrid.ps1`.
- [ ] The gate must create deterministic DB rows and local storage objects:
  - public active skill owned by `local-user`;
  - namespace `ADMIN` role for `local-admin`;
  - published `1.0.0` with `stable` tag;
  - pending `1.1.0` with `preview` tag;
  - text file and binary-like byte fixture rows.
- [ ] Compare Java/Python/Vite contracts for:
  - anonymous published version file content;
  - owner pending version file content;
  - namespace admin pending version file content;
  - anonymous pending version file status;
  - anonymous published tag file content;
  - owner published tag file content;
  - owner pending tag file status;
  - namespace admin pending tag file status;
  - missing file status.
- [ ] The comparison must check:
  - HTTP status;
  - normalized `Content-Type`;
  - exact response body bytes or deterministic text;
  - Vite route ownership.
- [ ] Run Playwright smoke inside the gate.

### Task 6. Docs, Verification, Commit

- [ ] Update route registry, sequence plan, Windows guide, and result doc.
- [ ] Run:
  - `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest`
  - `cd web; .\node_modules\.bin\vitest.CMD vite.config.test.ts --run`
  - `cd web; .\node_modules\.bin\tsc.CMD --noEmit`
  - `$env:UV_CACHE_DIR='server-python\.uv-cache'; $env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config'); $env:DOCKER_HOST='tcp://127.0.0.1:2375'; powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-file-content-smoke`
  - `git diff --check`
  - `git diff --name-only -- server`
- [ ] Commit with:
  - `feat(skill): add file content read foundation`
- [ ] Push to `dev`.

## Acceptance Criteria

- Version file content route matches Java for published and owner-preview versions.
- Tag file content route remains published-only and matches Java for pending tag rejection.
- Python and Vite responses match Java status, content type, and body bytes for live fixtures.
- Download routes remain Java-owned.
- Python tests, Vite proxy tests, TypeScript typecheck, and Windows live gate pass.
- `git diff --name-only -- server` is empty.

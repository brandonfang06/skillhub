# Download Read Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move SkillHub download read routes to Python while preserving Java stream/redirect,
counter, bundle, and fallback behavior.

**Architecture:** Split the milestone into two behaviors inside one cohesive download read path:
ClawHub compatibility download routes return Java-compatible redirects to portal download routes,
while portal download routes stream zip bytes from local object storage or build a fallback zip from
stored file objects. Python updates the same download counters Java updates for published versions.
Java remains the read-only live contract reference.

**Tech Stack:** FastAPI on port `8081`, SQLAlchemy async PostgreSQL reads/writes with explicit SQL
as migration bridge code, local filesystem object storage under `.dev/java-storage`, Python
`zipfile` fallback bundle creation, Vite proxy on port `3000`, Java Spring Boot on port `8080`,
PowerShell live contract gate, Playwright smoke.

---

## Scope

Routes in scope:

- `GET /api/v1/download/{canonicalSlug}`
- `GET /api/v1/download?slug={slug}&version={version}`
- `GET /api/v1/skills/{namespace}/{slug}/download`
- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/download`
- `GET /api/v1/skills/{namespace}/{slug}/tags/{tagName}/download`

Behavior in scope:

- ClawHub download routes return `302` redirects with Java-compatible `Location` values.
- Portal download routes stream zip bytes when local bundle object exists.
- Portal download routes build a fallback zip from `skill_file` objects when bundle object is
  missing and at least one stored file exists.
- `Content-Disposition` matches Java: `attachment; filename="{sanitized-display-name}-{version}.zip"`.
- `Content-Type` comes from stored bundle metadata where practical; fallback zip returns
  `application/zip`.
- `Content-Length` matches streamed/fallback byte length.
- Published downloads increment:
  - `skill.download_count`;
  - `skill_version_stats.download_count` for `(skill_version_id, skill_id)`.
- Non-published download behavior follows Java:
  - `PUBLISHED` is downloadable by callers with skill access.
  - `UPLOADED` / `PENDING_REVIEW` are allowed only when Java allows the skill through visibility
    checks. For local public fixtures, owner/admin access must be verified against Java before
    broadening Python.
  - all other statuses return `error.skill.version.notDownloadable`.
- Tag download remains Java-compatible through tag selector semantics.
- Missing bundle and no stored file rows return `error.skill.bundle.notFound`.

Behavior intentionally out of scope:

- Do not migrate `/api/web/.../download` aliases unless Java/Vite evidence shows the frontend uses
  them in this milestone. Keep them Java-owned by default.
- Do not implement MinIO/S3 presigned redirects yet. Local Windows verification uses stream
  behavior because local object storage returns no presigned URL.
- Do not migrate review download routes.
- Do not migrate publish/upload, object storage writes, review, OAuth, token, session, or lifecycle
  mutations.
- Do not modify `server/`.

## Data Access Strategy

This milestone continues the current Python migration bridge: use SQLAlchemy async engine plus
explicit SQL (`sqlalchemy.text`) for database reads and counter updates. Do not introduce SQLAlchemy
ORM models in this milestone.

Rationale:

- Java remains the live contract reference and uses JPA/domain services internally, but Python needs
  exact response/counter parity first.
- Download behavior is read-path ownership with limited counter updates, so explicit SQL keeps the
  implementation narrow and easy to compare.
- ORM/domain modeling should be revisited before publish/upload/lifecycle mutations, where
  transaction boundaries, authorization, idempotency, and rollback behavior become central.

Implementation constraints:

- Keep SQL in repository/helper functions, not directly inside route handlers.
- Keep route handlers focused on request binding and response/stream construction.
- Cover SQL-dependent behavior with Python tests and the live Java/Python/Vite comparison gate.

## Java Reference Findings

Portal routes:

- `GET /api/v1/skills/{namespace}/{slug}/download`
- `GET /api/v1/skills/{namespace}/{slug}/versions/{version}/download`
- `GET /api/v1/skills/{namespace}/{slug}/tags/{tagName}/download`

Java portal response behavior:

```java
return ResponseEntity.ok()
        .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"" + result.filename() + "\"")
        .contentType(MediaType.parseMediaType(result.contentType()))
        .contentLength(result.contentLength())
        .body(new InputStreamResource(result.openContent()));
```

Java can return `302 Found` to a presigned URL only when storage returns a presigned URL and request
security rules allow redirect. The Windows local storage path does not use presigned URLs, so the
live gate should verify stream behavior.

Download service behavior:

- Bundle storage key is `packages/{skillId}/{versionId}/bundle.zip`.
- If bundle exists:
  - stream bundle object;
  - filename is `{sanitize(displayName || slug)}-{version}.zip`;
  - content type comes from object metadata.
- If bundle is missing:
  - build fallback zip from existing `skill_file.storage_key` objects sorted by `file_path`;
  - fallback content type is `application/zip`;
  - if no stored files exist, throw `error.skill.bundle.notFound`.
- Published version downloads increment skill and version stats counters.
- Review downloads use separate routes and do not increment public counters.

ClawHub compatibility behavior:

- `GET /api/v1/download/{canonicalSlug}` redirects to:
  - `/api/v1/skills/{namespace}/{slug}/download` for `version=latest`;
  - `/api/v1/skills/{namespace}/{slug}/versions/{version}/download` otherwise.
- `GET /api/v1/download?slug=...&version=...` performs query coordinate resolution before
  redirecting to the same portal download route shape.

## Route Ownership

After implementation, update `docs/backend-python-migration/route-registry.md`:

| Method | Path | Owner | Notes |
| --- | --- | --- | --- |
| GET | `/api/v1/download/{canonicalSlug}` | python | ClawHub compatibility redirect to portal download route. |
| GET | `/api/v1/download` | python | ClawHub query-style compatibility redirect. |
| GET | `/api/v1/skills/{namespace}/{slug}/download` | python | Latest published portal bundle download stream. |
| GET | `/api/v1/skills/{namespace}/{slug}/versions/{version}/download` | python | Explicit version portal bundle download stream with Java-compatible access and counters. |
| GET | `/api/v1/skills/{namespace}/{slug}/tags/{tagName}/download` | python | Tag-selected portal bundle download stream with Java-compatible access and counters. |

Vite proxy must route only these `GET` paths to Python and must keep Java-owned mutations and
unlisted `/api` routes untouched.

## Files

Allowed changes:

- Modify `server-python/app/api/skills.py`.
- Create `server-python/tests/test_skill_download.py`.
- Modify `web/vite.config.ts`.
- Modify `web/vite.config.test.ts`.
- Modify `scripts/dev-hybrid.ps1`.
- Modify `server-python/tests/test_hybrid_makefile.py`.
- Update `docs/backend-python-migration/migration-sequence-plan.md`.
- Update `docs/backend-python-migration/route-registry.md`.
- Update `docs/backend-python-migration/windows-live-verification.md`.
- Write `docs/backend-python-migration/results/2026-06-08-download-read-path.md`.

Forbidden changes:

- Do not modify any file under `server/`.
- Do not manually edit `web/src/api/generated/schema.d.ts`.
- Do not migrate review download routes.

## TDD Tasks

### Task 1. ClawHub Redirect Routes

- [ ] Add failing tests in `server-python/tests/test_skill_download.py`:
  - `GET /api/v1/download/{canonicalSlug}` with latest redirects to portal latest download.
  - `GET /api/v1/download/{canonicalSlug}?version=1.2.0` redirects to explicit version download.
  - `GET /api/v1/download?slug=demo&version=latest` redirects through query coordinate
    resolution.
  - query route forwards `X-Mock-User-Id` to the injected resolver.
- [ ] Run:
  - `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_skill_download.py -q`
- [ ] Expected before implementation: routes not found.
- [ ] Implement minimal redirect routes and injected resolver hooks.
- [ ] Re-run focused tests and expect pass.

### Task 2. Download Result Builder

- [ ] Add failing unit tests for:
  - filename sanitization;
  - direct bundle object result reads exact bytes, content type, content length, filename;
  - missing bundle fallback zip includes stored files sorted by path;
  - no bundle and no stored files raises `error.skill.bundle.notFound`.
- [ ] Implement helpers:
  - `sanitize_download_filename(value: str) -> str`;
  - `build_download_filename(display_name: str | None, slug: str, version: str) -> str`;
  - `read_bundle_or_build_fallback_zip(...)`.
- [ ] Re-run focused tests.

### Task 3. Portal Download DB Readers

- [ ] Add tests around pure access/counter helpers:
  - published download increments counters;
  - non-published download does not increment counters;
  - unsupported statuses raise `error.skill.version.notDownloadable`.
- [ ] Implement `read_skill_download_latest(...)`, `read_skill_download_version(...)`, and
  `read_skill_download_tag(...)`:
  - active public skill lookup matching existing readers;
  - latest uses `latest_version_id`;
  - explicit version resolves by version string;
  - tag resolves through `skill_tag`;
  - status/access checks match Java;
  - download content uses bundle or fallback zip;
  - published downloads update `skill.download_count` and upsert/increment
    `skill_version_stats.download_count`.
- [ ] Re-run focused tests.

### Task 4. Portal Download Routes

- [ ] Add failing route tests for:
  - latest portal download streams bytes;
  - explicit version portal download streams bytes;
  - tag portal download streams bytes;
  - `Content-Disposition`, `Content-Type`, and `Content-Length` are set;
  - injected `SkillResolveError` maps to its HTTP status.
- [ ] Implement FastAPI routes returning raw `Response` bytes.
- [ ] Re-run focused tests.

### Task 5. Proxy And Live Gate

- [ ] Add Vite proxy ownership for all route paths in scope.
- [ ] Update Vite proxy tests:
  - ClawHub download routes go to Python.
  - portal v1 download routes go to Python.
  - `/api/web/.../download` remains Java-owned unless explicitly migrated.
  - `POST /api/v1/skills` remains Java-owned.
- [ ] Add `verify-download-smoke` to `scripts/dev-hybrid.ps1`.
- [ ] The gate must create deterministic DB rows and storage objects:
  - public active skill owned by `local-user`;
  - published `1.0.0` with existing bundle object;
  - published `1.1.0` with no bundle but stored file rows for fallback zip;
  - pending `1.2.0` fixture if Java allows local owner download, otherwise record matching
    rejection;
  - stable tag pointing to a published version.
- [ ] Compare Java/Python/Vite for:
  - ClawHub path redirect latest and explicit version;
  - ClawHub query redirect latest and explicit version;
  - portal latest bundle stream;
  - portal explicit bundle stream;
  - portal tag bundle stream;
  - fallback zip stream shape;
  - missing bundle/no files status;
  - download counter increments after published download.
- [ ] The comparison must check:
  - HTTP status;
  - `Location` for redirects;
  - normalized `Content-Type`;
  - `Content-Disposition`;
  - byte length;
  - body bytes or zip entry names for fallback zip;
  - counter delta.
- [ ] Run Playwright smoke inside the gate.

### Task 6. Docs, Verification, Commit

- [ ] Update route registry, sequence plan, Windows guide, and result doc.
- [ ] Run:
  - `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest`
  - `cd web; .\node_modules\.bin\vitest.CMD vite.config.test.ts --run`
  - `cd web; .\node_modules\.bin\tsc.CMD --noEmit`
  - `$env:UV_CACHE_DIR='server-python\.uv-cache'; $env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config'); $env:DOCKER_HOST='tcp://127.0.0.1:2375'; powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-download-smoke`
  - `git diff --check`
  - `git diff --name-only -- server`
- [ ] Commit with:
  - `feat(skill): add download read path`
- [ ] Push to `dev`.

## Acceptance Criteria

- ClawHub download routes match Java redirect status and `Location`.
- Portal download routes match Java stream status, headers, and bytes for bundle objects.
- Fallback zip behavior matches Java enough to validate entry names and content bytes.
- Published downloads increment the same counters Java increments.
- Non-published and missing bundle cases match Java statuses.
- Download routes are Python-owned in Vite only for planned v1 paths.
- Python tests, Vite proxy tests, TypeScript typecheck, and Windows live gate pass.
- `git diff --name-only -- server` is empty.

# Publish Transaction Dry-Run Model Plan

Date: 2026-06-08

## Summary

This milestone builds the Python publish dry-run decision model. It does not migrate any publish
HTTP route and does not persist anything.

The goal is to mirror Java `SkillPublishService.validateOnly(...)` closely enough that a later
publish route milestone can reuse the same checks before adding DB writes, storage writes, scanner
triggering, review tasks, audit logs, or event publication.

## Route Ownership

No route ownership changes.

These routes stay Java-owned:

- `POST /api/v1/skills`
- `POST /api/v1/publish`
- `POST /api/v1/skills/{namespace}/publish`
- `POST /api/web/skills/{namespace}/publish`
- `POST /api/cli/v1/skills/{namespace}/publish/validate`
- `POST /api/cli/v1/skills/{namespace}/publish`

Vite must keep publish POST routes on Java. Public skill detail GET-only Python ownership must not
capture namespace publish POST paths.

## Java Reference

Read-only Java reference:

- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillPublishService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/validation/BasicPrePublishValidator.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/namespace/SlugValidator.java`

Java `validateOnly(...)` behavior to mirror:

1. Namespace must exist.
2. `FROZEN` and `ARCHIVED` namespace statuses produce errors.
3. Publisher must be a namespace member unless platform roles contain `SUPER_ADMIN`.
4. Package validation errors and warnings are collected.
5. Invalid package stops before metadata/conflict checks.
6. `SKILL.md` metadata resolves `slug` from `name`.
7. Missing `version` gets an auto-generated timestamp version.
8. Basic pre-publish credential scan warnings are collected.
9. Existing own archived skill produces an error.
10. Existing own `PUBLISHED` version with the same version produces an error.
11. Other owner's skill blocks only when it has at least one `PUBLISHED` version.
12. Warnings make dry-run `valid=false`, matching Java CLI dry-run behavior with
    `confirmWarnings=false`.

## Allowed Files

Create:

- `server-python/app/publish/dry_run.py`
- `server-python/tests/test_publish_dry_run.py`
- `docs/backend-python-migration/results/2026-06-08-publish-dry-run-model.md`

Modify:

- `scripts/dev-hybrid.ps1`
- `server-python/tests/test_hybrid_makefile.py`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/windows-live-verification.md`

Forbidden:

- No `server/` changes.
- No new publish route.
- No Vite publish ownership change.
- No DB writes.
- No object storage writes.
- No scanner trigger.
- No review task, audit log, or event creation.

## Implementation Shape

Add pure Python dry-run primitives:

- `PublishDryRunRepository`
  - `read_namespace_context(namespace_slug, publisher_id, platform_roles)`
  - `read_publish_conflicts(namespace_id, skill_slug, publisher_id, resolved_version)`
- `PublishDryRunInput`
  - `namespace_slug`
  - `entries`
  - `publisher_id`
  - `visibility`
  - `platform_roles`
  - optional `now`
- `PublishDryRunResult`
  - `valid`
  - `errors`
  - `warnings`
  - `resolved_slug`
  - `resolved_version`
- `validate_publish_dry_run(...)`

Keep SQL in the repository and dry-run orchestration in the service-level function.

## Tests First

Add `server-python/tests/test_publish_dry_run.py` before implementation.

Unit tests:

- valid package, active namespace, member publisher resolves slug/version and is valid.
- missing namespace returns `Namespace not found: <slug>`.
- frozen and archived namespaces produce Java-compatible errors.
- non-member publisher returns `Publisher is not a member of namespace: <slug>`.
- `SUPER_ADMIN` bypasses namespace membership.
- invalid package returns package errors and does not run conflict checks.
- missing version auto-generates timestamp version.
- warning-only package makes `valid=false`.
- basic secret scan warning mirrors Java wording.
- own archived skill returns `Cannot publish to archived skill: <slug>`.
- own published version returns `Version already published: <version>`.
- other owner's published skill returns name conflict.
- other owner's unpublished-only skill does not block.

Repository tests:

- read namespace status, membership, and platform-role context from rows.
- read own skill status, own version status, and other-owner published conflict rows.

## Windows Live Gate

Add `verify-publish-dry-run-smoke` to `scripts/dev-hybrid.ps1`.

The gate must:

- run `uv run pytest tests/test_publish_dry_run.py -q`;
- start hybrid stack;
- verify publish POST Java ownership through Vite for:
  - `POST /api/v1/skills`
  - `POST /api/v1/publish`
  - `POST /api/v1/skills/global/publish`
  - `POST /api/web/skills/global/publish`
- run Playwright smoke;
- write `.dev/publish-dry-run-contract-result.json`.

This gate does not call a Python publish HTTP route because no such route exists yet.

## Verification

Run before commit:

```powershell
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest
```

```powershell
cd web
.\node_modules\.bin\vitest.CMD vite.config.test.ts --run
.\node_modules\.bin\tsc.CMD --noEmit
```

```powershell
$env:UV_CACHE_DIR='server-python\.uv-cache'
$env:DOCKER_CONFIG=(Join-Path (Get-Location) '.dev\docker-config')
$env:DOCKER_HOST='tcp://127.0.0.1:2375'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-dry-run-smoke
```

```powershell
git diff --check
git diff --name-only -- server
```

## Result Requirements

Result doc must include:

- routes changed: none;
- owner before/after: publish POST remains Java;
- dry-run checks implemented;
- tests and live gate result;
- risks;
- follow-up milestone.

## Follow-Up

Next milestone after this should be local storage write transaction planning:

- create skill/version/file rows;
- write local storage files;
- build bundle zip;
- still no scanner trigger until scanner/review milestone.

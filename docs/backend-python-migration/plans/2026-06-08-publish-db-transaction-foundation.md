# Publish DB Transaction Foundation Plan

Date: 2026-06-08

## Summary

This milestone builds the Python DB transaction helper for publish/upload. It does not migrate any
publish HTTP route and does not trigger scanner, review tasks, audit logs, or events.

The helper will be callable by a later publish route milestone after route ownership is explicitly
planned. For now, it is covered by focused unit tests and a Windows live gate that still proves all
publish POST routes remain Java-owned through Vite.

## Route Ownership

No route ownership changes.

These routes stay Java-owned:

- `POST /api/v1/skills`
- `POST /api/v1/publish`
- `POST /api/v1/skills/{namespace}/publish`
- `POST /api/web/skills/{namespace}/publish`
- `POST /api/cli/v1/skills/{namespace}/publish/validate`
- `POST /api/cli/v1/skills/{namespace}/publish`

## Java Reference

Read-only Java reference:

- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillPublishService.java`
- `server/skillhub-app/src/main/resources/db/migration/V2__phase2_skill_tables.sql`
- `server/skillhub-app/src/main/resources/db/migration/V13__skill_owner_uniqueness.sql`
- `server/skillhub-app/src/main/resources/db/migration/V15__skill_version_download_state.sql`
- `server/skillhub-app/src/main/resources/db/migration/V32__add_requested_visibility_to_skill_version.sql`

DB behavior to mirror first:

- reuse existing `(namespace_id, slug, owner_id)` skill when present;
- create new skill when absent;
- reject archived own skill;
- create `skill_version`;
- set version status:
  - `PUBLISHED` when `auto_publish=true`;
  - `UPLOADED` when visibility is `PRIVATE`;
  - `PENDING_REVIEW` otherwise;
- set `published_at` for `PUBLISHED` and `UPLOADED`;
- store parsed metadata JSON and manifest JSON;
- insert `skill_file` rows from local storage metadata;
- update `skill_version.file_count`, `total_size`, `bundle_ready`, and `download_ready`;
- update skill display name, summary, and updated_by;
- update `skill.latest_version_id` and visibility only for `PUBLISHED` or `UPLOADED`, matching
  Java's auto-publish/private behavior.

## Allowed Files

Create:

- `server-python/app/publish/transaction.py`
- `server-python/tests/test_publish_transaction.py`
- `docs/backend-python-migration/results/2026-06-08-publish-db-transaction-foundation.md`

Modify:

- `scripts/dev-hybrid.ps1`
- `server-python/tests/test_hybrid_makefile.py`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/windows-live-verification.md`

Forbidden:

- No `server/` changes.
- No new publish route.
- No Vite publish ownership change.
- No scanner trigger.
- No review task creation.
- No audit log or event creation.
- No replacement cleanup or storage compensation in this milestone.

## Implementation Shape

Add `server-python/app/publish/transaction.py`:

- `PublishDbTransactionInput`
- `PublishDbTransactionResult`
- `determine_initial_version_status(...)`
- `build_parsed_metadata_json(...)`
- `build_manifest_json(...)`
- `create_publish_db_records(engine, request)`

The request consumes:

- resolved namespace id;
- resolved slug/version/name/description from dry-run;
- publisher id;
- visibility;
- platform role / auto-publish decision;
- package entries;
- storage write metadata from `write_local_package_objects(...)`.

SQL must stay inside this helper. No route handler changes.

## Tests First

Add `server-python/tests/test_publish_transaction.py` before implementation.

Tests:

- determines `PUBLISHED`, `UPLOADED`, and `PENDING_REVIEW` initial statuses.
- builds Java-compatible manifest JSON: `path`, `size`, `contentType`.
- inserts new skill, version, file rows, and version stats in one transaction.
- reuses an existing skill without inserting a duplicate skill.
- rejects existing archived skill before inserting a version.
- updates `latest_version_id` only for `PUBLISHED` and `UPLOADED`.
- leaves `latest_version_id` unchanged for `PENDING_REVIEW`.

Use fake async engine/connection tests for SQL ordering and parameters. Live DB mutation tests are
deferred until route ownership is planned.

## Windows Live Gate

Add `verify-publish-db-foundation-smoke` to `scripts/dev-hybrid.ps1`.

The gate must:

- run `uv run pytest tests/test_publish_transaction.py -q`;
- start hybrid stack;
- verify publish POST Java ownership through Vite for:
  - `POST /api/v1/skills`
  - `POST /api/v1/publish`
  - `POST /api/v1/skills/global/publish`
  - `POST /api/web/skills/global/publish`
- run Playwright smoke;
- write `.dev/publish-db-foundation-contract-result.json`.

No Python publish HTTP route is called because no route exists yet.

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
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-db-foundation-smoke
```

```powershell
git diff --check
git diff --name-only -- server
```

## Follow-Up

Next milestone should explicitly decide whether to migrate a private/internal publish route first or
continue with review/scanner/audit foundations before route ownership.

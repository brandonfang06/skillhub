# Download Analytics Event Tracking Result

Date: 2026-07-08

## Scope

- Added a Python-owned local schema migration layer for organization-specific tables.
- Added `local_skill_download_event` as a dedicated download analytics table.
- Kept existing public counters in `skill.download_count` and `skill_version_stats.download_count` unchanged.
- Recorded one download event after successful `PUBLISHED` skill downloads.
- Added backend query APIs for platform operators and skill-scoped managers.

## Local Schema Contract

- Upstream-followed Flyway files stay under `server-python/app/db/migration/V*__*.sql`.
- Organization-specific schema files live under `server-python/app/db/local_migration/`.
- Applied local migrations are tracked in `local_schema_migration`.
- Future upstream schema intake must preserve this local migration chain and explicitly review equivalent upstream features before merging or retiring local tables.

## API

- `GET /api/v1/admin/download-events`
  - Requires `SUPER_ADMIN`, `SKILL_ADMIN`, or `AUDITOR`.
  - Supports filters for namespace, slug, version, user, source, and time range.
- `GET /api/web/skills/{namespace}/{slug}/download-events`
  - Allows platform readers, skill owners, and namespace `OWNER`/`ADMIN`.
  - Supports filters for version, user, source, and time range.

## Operator Notes

- Authenticated downloads record `user_id`.
- Anonymous public downloads record `user_id = NULL`.
- The feature does not force login for public downloads.
- The event table is separate from `audit_log` to avoid turning audit logs into high-volume analytics.
- Preview downloads for `UPLOADED` or `PENDING_REVIEW` versions do not create analytics events.
- `request_id`, client IP, and user agent metadata are bounded before insert so untrusted headers cannot break successful downloads.
- `SKILLHUB_DOWNLOAD_ANALYTICS_RETENTION_MONTHS` controls rolling retention for `local_skill_download_event`; default is `12`, and `0` or a negative value disables automatic pruning.
- Retention pruning runs once when the backend starts and then once per day.
- `local_skill_download_event` has a global `(created_at DESC, id DESC)` index for operator event-list queries.

## Verification

Passed:

```powershell
cd server-python
uv run pytest tests/test_schema_migration_baseline.py -q
# 10 passed

uv run pytest tests/test_skill_download.py -q
# 33 passed, 1 warning

uv run pytest tests/test_publish_review_download_session_flow.py -q
# 1 passed, 1 warning

uv run pytest tests/test_download_analytics.py -q
# 6 passed, 1 warning

uv run pytest tests/test_route_policy_enforcement.py tests/test_route_registry.py -q
# 15 passed

uv run pytest tests/test_schema_migration_baseline.py tests/test_skill_download.py tests/test_publish_review_download_session_flow.py tests/test_download_analytics.py tests/test_route_policy_enforcement.py tests/test_route_registry.py -q
# 65 passed, 1 warning

uv run pytest tests -q
# 880 passed, 1 warning

cd ..
git diff --check
# passed; Windows CRLF conversion warnings only
```

Retention hardening follow-up:

```powershell
cd server-python
uv run pytest tests/test_schema_migration_baseline.py tests/test_config.py tests/test_download_analytics.py tests/test_deployment_cutover.py -q
# 55 passed, 1 warning

uv run pytest tests -q
# 886 passed, 1 warning

cd ..
kubectl kustomize deploy\k8s\base
# rendered successfully

docker compose --env-file .env.release.example -f compose.release.yml config
# rendered successfully

git diff --check
# passed; Windows CRLF conversion warnings only

docker build -t skillhub-server-python:verify -f server-python/Dockerfile .
# not completed: Docker Desktop Linux engine was not running on this workstation
```

OpenAPI generation note:

```powershell
cd web
corepack pnpm run generate-api
# failed: http://localhost:8080/v3/api-docs returned 404

corepack pnpm exec openapi-typescript http://localhost:8080/openapi.json -o src/api/generated/schema.d.ts
# generated successfully, but the resulting schema rewrote the existing file broadly because FastAPI operation IDs differ from the checked-in schema
```

`web/src/api/generated/schema.d.ts` was not committed in this milestone because the current checked-in script still targets `/v3/api-docs`, while the Python FastAPI app exposes `/openapi.json`. Regenerating from `/openapi.json` is a separate OpenAPI sync cleanup because it changes far more than the two new download analytics endpoints.

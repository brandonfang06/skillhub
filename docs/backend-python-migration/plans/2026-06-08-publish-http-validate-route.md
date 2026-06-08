# Publish HTTP Validate Route Adapter

## Summary

Move the CLI publish validate-only HTTP route to Python:

- `POST /api/cli/v1/skills/{namespace}/publish/validate`

This milestone intentionally does not move any publish route that writes DB rows, storage objects,
scanner tasks, audit logs, or lifecycle state. It is the HTTP adapter bridge between the completed
publish dry-run model and a real FastAPI multipart endpoint.

## Route Ownership

Before:

- `POST /api/cli/v1/skills/{namespace}/publish/validate` -> Java

After:

- `POST /api/cli/v1/skills/{namespace}/publish/validate` -> Python

Still Java-owned:

- `POST /api/v1/skills`
- `POST /api/v1/publish`
- `POST /api/v1/skills/{namespace}/publish`
- `POST /api/web/skills/{namespace}/publish`
- `POST /api/cli/v1/skills/{namespace}/publish`
- `/oauth2/**`

## Java Parity Checklist

Reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/cli/CliSkillController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/cli/CliSkillAppService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillPublishService.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/support/SkillPackageArchiveExtractor.java`

Checklist:

| Area | Status | Notes |
| --- | --- | --- |
| API contract | covered | Multipart `file` plus optional `visibility`, response data fields `valid`, `errors`, `warnings`, `resolvedSlug`, `resolvedVersion`. |
| Auth/session | covered for local bridge | Python uses existing local `X-Mock-User-Id`; missing user returns `401`. OAuth/session remains Java-owned. |
| Authorization | covered by dry-run repository | Namespace membership and `SUPER_ADMIN` bypass are handled by the existing dry-run model. |
| Database transaction atomicity | not applicable | Validate route is read-only and performs no publish write transaction. |
| Audit actor/timestamp fields | not applicable | Java validate-only route does not write audit rows. |
| Storage and side effects | not applicable | Reads uploaded zip bytes only; no object storage writes. |
| Live verification evidence | planned | Add Windows live gate to compare Java/Python/proxy stable response fields and prove write routes remain Java-owned. |

## Implementation Plan

1. Add focused FastAPI route tests for:
   - Missing `X-Mock-User-Id` returns `401`.
   - Invalid visibility returns `400`.
   - Valid multipart zip invokes dry-run validation and returns Java-compatible response data.
2. Add `app/api/publish.py` with the CLI validate endpoint.
3. Parse the uploaded zip using existing Python package extraction helpers.
4. Use `PublishDryRunRepository` and `validate_publish_dry_run(...)`.
5. Add Vite proxy ownership only for `POST /api/cli/v1/skills/{namespace}/publish/validate`.
6. Keep all mutating publish routes Java-owned.
7. Update route registry and sequence plan.
8. Add/update Windows live gate script for validate route ownership and contract comparison.

## Acceptance Criteria

- `cd server-python; uv run pytest tests/test_publish_http_validate.py tests/test_publish_dry_run.py tests/test_publish_package.py -q` passes.
- Vite proxy routes `POST /api/cli/v1/skills/{namespace}/publish/validate` to Python.
- Publish write routes still proxy to Java.
- Windows live gate passes for Java/Python/proxy validate-only comparison.
- `git diff --name-only -- server` is empty.

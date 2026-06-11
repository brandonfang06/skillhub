# Admin Route Bearer Policy Cutover Result

Date: 2026-06-12

## Summary

Already Python-owned `/api/v1/admin/**` route groups now share the same Java-compatible bearer
API-token route-policy behavior:

- Valid bearer API-token principals without `X-Mock-User-Id` receive `403` with
  `API token cannot access endpoint: <path>`.
- Invalid bearer tokens remain authentication failures with `401`.
- `X-Mock-User-Id` keeps local-development precedence over bearer credentials.

This milestone consolidates the earlier admin search and admin label route-policy handling into a
shared helper and applies it to the remaining migrated admin groups:

- Admin users and password-reset trigger.
- Admin skill hide/unhide/yank governance.
- Admin audit log reads.
- Admin skill report and profile review reads/mutations.
- Admin labels and admin search rebuild through the shared helper.

## Implementation Notes

- Added `app.api.admin_policy.reject_bearer_api_token_for_admin_route`.
- Kept Java `server/` source read-only.
- Did not remove the broad `/api/**` Java fallback because Vite proxy tests still intentionally
  preserve unmatched Java-owned paths and `/oauth2/**` ownership.

## Verification

Targeted tests run during implementation:

```text
uv run pytest tests/test_admin_bearer_policy.py -q
6 passed, 1 warning

uv run pytest tests/test_admin_label_definitions.py tests/test_admin_search_rebuild.py tests/test_admin_user_management.py tests/test_admin_skill_governance.py tests/test_admin_audit_logs.py tests/test_admin_review_reports.py tests/test_admin_review_report_mutations.py -q
38 passed, 1 warning
```

Additional verification after documentation updates:

```text
uv run pytest tests/test_admin_bearer_policy.py tests/test_route_registry.py -q
8 passed, 1 warning

npm.cmd run test -- vite.config.test.ts
Test Files  1 passed (1)
Tests       47 passed (47)
```

Hybrid live gate:

```text
http://localhost:8080 /api/v1/admin/users -> 403
http://localhost:8081 /api/v1/admin/users -> 403
http://localhost:3000 /api/v1/admin/users -> 403
python invalid bearer /api/v1/admin/users -> 401
python mock precedence /api/v1/admin/users -> 200

http://localhost:8080 POST /api/v1/admin/skills/10/hide -> 403
http://localhost:8081 POST /api/v1/admin/skills/10/hide -> 403
http://localhost:3000 POST /api/v1/admin/skills/10/hide -> 403
http://localhost:8080 GET /api/v1/admin/skill-reports -> 403
http://localhost:8081 GET /api/v1/admin/skill-reports -> 403
http://localhost:3000 GET /api/v1/admin/skill-reports -> 403
```

Final regression:

```text
uv run pytest tests/test_admin_bearer_policy.py tests/test_admin_label_definitions.py tests/test_admin_search_rebuild.py tests/test_admin_user_management.py tests/test_admin_skill_governance.py tests/test_admin_audit_logs.py tests/test_admin_review_reports.py tests/test_admin_review_report_mutations.py tests/test_route_registry.py -q
46 passed, 1 warning

npm.cmd run test -- vite.config.test.ts
Test Files  1 passed (1)
Tests       47 passed (47)

git diff --check
passed

git diff --name-only -- server
no output
```

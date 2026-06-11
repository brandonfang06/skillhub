# Admin Route Bearer Policy Cutover Implementation Plan

**Goal:** Apply Java-compatible bearer API-token unsupported policy to every already Python-owned
`/api/v1/admin/**` route group.

**Architecture:** Keep route ownership unchanged and introduce a small shared FastAPI admin policy
helper. Each admin route accepts `Authorization`, rejects valid bearer API-token principals without
`X-Mock-User-Id` as `403 API token cannot access endpoint: <path>`, preserves invalid bearer
`401`, and preserves mock-user precedence.

**Tech Stack:** FastAPI, pytest, Vite proxy tests, SkillHub hybrid stack.

## Scope

Routes covered in this milestone:

- Admin users: `GET/PUT/POST /api/v1/admin/users*`
- Admin skill governance: `POST /api/v1/admin/skills/*`
- Admin audit logs: `GET /api/v1/admin/audit-logs`
- Admin skill reports/profile reviews: `GET/POST /api/v1/admin/skill-reports*`,
  `GET/POST /api/v1/admin/profile-reviews*`
- Existing admin labels/search policy guards are consolidated onto the same helper.

Out of scope:

- `/oauth2/**`, Spring Session establishment, and CSRF behavior.
- Unmatched `/api/**` fallback cleanup.
- Java `server/` edits.

## Tasks

- [x] Add failing tests in `server-python/tests/test_admin_bearer_policy.py` for valid bearer
  unsupported behavior across the remaining admin route groups.
- [x] Add invalid bearer and mock-user precedence checks.
- [x] Create `server-python/app/api/admin_policy.py` with a shared
  `reject_bearer_api_token_for_admin_route` helper.
- [x] Wire the helper into `admin_users.py`, `admin_skills.py`, `admin_audit_logs.py`,
  `admin_review_reports.py`, `admin_labels.py`, and `admin_search.py`.
- [x] Update `route-registry.md`, `migration-sequence-plan.md`, and the result doc.
- [x] Verify with targeted pytest, Vite proxy tests, manual hybrid live gate, `git diff --check`,
  and `git diff --name-only -- server`.

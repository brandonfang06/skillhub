# User Profile API Migration Plan

## Summary

Move the current-user profile boundary to FastAPI:

- `GET /api/v1/user/profile`
- `PATCH /api/v1/user/profile`

This milestone is a behavior-parity step before final auth/session replacement and later Python
module refactoring. Java remains the reference implementation and `server/` stays read-only.

## Route Ownership

| Method | Route | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/user/profile` | java | python |
| PATCH | `/api/v1/user/profile` | java | python |

Deferred and still Java-owned:

- `/api/v1/account/merge/**`
- `/api/v1/device/**`
- `/api/v1/auth/logout`
- `/oauth2/**`
- bearer-token authentication filters, scope enforcement, CSRF/session persistence

## Java Parity Checklist

Reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/UserProfileController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/UpdateProfileRequest.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/UserProfileResponse.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/UpdateProfileResponse.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/config/ProfileFieldPolicyProperties.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/config/ProfileModerationProperties.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/user/UserProfileService.java`
- `server/skillhub-app/src/main/resources/db/migration/V27__profile_change_request.sql`

| Area | Status | Notes |
| --- | --- | --- |
| API contract | covered | Preserve Java envelope, GET profile shape, PATCH update status, and validation errors. |
| Authorization/session behavior | covered/deferred | Requires current mock user like migrated auth bridge. Refreshing Spring session after immediate apply is deferred with final session replacement. |
| Database transaction atomicity | covered | PATCH user update/change-request/audit side effects run in one SQLAlchemy transaction. |
| Audit actor/timestamp fields | covered | Immediate apply writes `PROFILE_UPDATE` audit with request id, client IP, user agent, and detail JSON. Pending review does not write audit, matching Java. |
| Storage/side effects | not applicable | No object storage usage. |
| Live verification evidence | pending | Windows live gate will compare Java/Python/proxy profile contract and DB state. |

## Behavior Requirements

- Missing or blank `X-Mock-User-Id` returns 401.
- Missing active user returns 401, matching Java `UnauthorizedException("error.auth.required")`.
- GET reads `user_account` and latest `PENDING` or `REJECTED` `profile_change_request`.
- GET overlays `displayName` and `avatarUrl` only when the latest relevant request status is
  `PENDING`.
- GET returns field policies in Java insertion order: `displayName`, then `email`.
- PATCH only accepts `displayName`, matching current Java DTO.
- PATCH trims `displayName` before applying.
- PATCH rejects empty body, too-short, too-long, and invalid characters.
- With default Java config, display name changes enter `PENDING_REVIEW` because human review is
  enabled and `displayName.requiresReview` is true.
- When human review is disabled, display name changes apply immediately, insert an `APPROVED`
  change request, and write `PROFILE_UPDATE` audit.

## Implementation Scope

Allowed files:

- `server-python/app/user_profile.py`
- `server-python/app/api/user_profile.py`
- `server-python/app/main.py`
- `server-python/tests/test_user_profile.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/**`

Forbidden:

- Any file under `server/`
- `web/src/api/generated/schema.d.ts`

## Verification

Red/green tests:

- `cd server-python; $env:UV_CACHE_DIR='..\.uv-cache'; uv run pytest tests/test_user_profile.py tests/test_hybrid_makefile.py -q`
- `cd web; npx.cmd vitest run vite.config.test.ts`

Live gate:

- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-user-profile-smoke`

Final checks:

- `git diff --name-only -- server`
- `git diff --check`

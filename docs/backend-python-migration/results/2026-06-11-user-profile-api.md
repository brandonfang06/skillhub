# User Profile API Migration Result

## Summary

Moved the current-user profile API boundary to FastAPI:

- `GET /api/v1/user/profile`
- `PATCH /api/v1/user/profile`

The route preserves Java behavior for profile read projection, display-name validation,
default human-review queueing, immediate-apply support, and profile change/audit side effects.
Spring Session refresh after immediate profile apply remains deferred to final session replacement.

## Routes Changed

| Method | Route | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/user/profile` | java | python |
| PATCH | `/api/v1/user/profile` | java | python |

Still Java-owned:

- `/api/v1/account/merge/**`
- `/api/v1/device/**`
- `/api/v1/auth/logout`
- `/oauth2/**`
- bearer-token authentication filters, scope enforcement, CSRF/session persistence

## Java Parity Checklist Outcome

| Area | Outcome |
| --- | --- |
| API contract | covered. GET and PATCH envelopes, status values, field policies, pending projection, and display-name validation are covered by tests and live comparison. |
| Authorization/session behavior | covered/deferred. The migrated route requires the same local mock-user bridge used by current Python auth routes. Spring Session refresh remains deferred. |
| Database transaction atomicity | covered. PATCH DB updates run inside one SQLAlchemy transaction. |
| Audit actor/timestamp fields | covered. Immediate-apply mode writes `PROFILE_UPDATE`; default pending-review mode intentionally writes no audit, matching Java. |
| Storage and side effects | not applicable. |
| Live verification evidence | covered. Windows live gate passed. |

## Verification

Commands run:

- `cd server-python; $env:UV_CACHE_DIR='..\.uv-cache'; uv run pytest tests/test_user_profile.py -q`
  - Result: `6 passed`
- `cd server-python; $env:UV_CACHE_DIR='..\.uv-cache'; uv run pytest tests/test_user_profile.py tests/test_hybrid_makefile.py -q`
  - Result: `12 passed`
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - Result: `40 passed`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-user-profile-smoke`
  - Result: Python tests `12 passed`, Vite proxy tests `40 passed`, Playwright smoke `6 passed`
  - Contract result file: `.dev/user-profile-contract-result.json`
  - Java/Python/proxy patch envelope match: `true`
  - Java/Python/proxy get envelope match: `true`
  - no-auth statuses: `[401, 401, 401]`
  - DB pending parity: `true`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 status`
  - Result: Java backend stopped, Python backend stopped, Vite frontend stopped, no compose services listed.

Live gate warning:

- The gate printed a transient warning while stopping a port-8080 process, but follow-up `status`
  confirmed all managed services were stopped.

## Risks And Follow-Up

- Final Spring Session refresh after immediate profile apply is deferred to final auth/session
  replacement.
- Machine moderation remains Java-compatible no-op approval for the open-source default. Custom
  SaaS moderation providers are outside this milestone.
- Account merge, device flow, logout, OAuth, bearer-token auth filters, and final proxy cleanup
  remain future milestones.

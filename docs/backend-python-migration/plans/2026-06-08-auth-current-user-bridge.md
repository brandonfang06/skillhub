# Auth Current User Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the first auth read endpoint, `GET /api/v1/auth/me`, to FastAPI so migrated
frontend workflows can resolve the current local development user from Python.

**Architecture:** Python will implement a narrow local-development current-user bridge based on
`X-Mock-User-Id`, matching Java local profile behavior for active users and platform roles. Java
remains the owner for login, OAuth, session bootstrap, API tokens, CLI auth, and all mutating auth
routes.

**Tech Stack:** FastAPI on port `8081`, SQLAlchemy async reads against PostgreSQL, Vite proxy on
port `3000`, Java Spring Boot on port `8080` as read-only reference.

---

## Route Ownership

| Method | Path | Before | After | Notes |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/auth/me` | java | python | Returns SkillHub envelope with current user data. |
| GET | `/api/v1/auth/methods` | java | java | Remains Java-owned. |
| GET | `/api/v1/auth/providers` | java | java | Remains Java-owned. |
| POST | `/api/v1/auth/session/bootstrap` | java | java | Remains Java-owned. |
| POST | `/api/v1/auth/direct/login` | java | java | Remains Java-owned. |
| * | `/api/v1/auth/local/**` | java | java | Remains Java-owned. |
| * | `/oauth2/**` | java | java | Remains Java-owned. |
| * | `/api/v1/tokens/**` | java | java | Remains Java-owned. |
| GET | `/api/v1/whoami` | java | java | ClawHub whoami remains separate from web auth. |
| GET | `/api/cli/v1/auth/whoami` | java | java | CLI auth remains Java-owned. |

## API Contract

`GET /api/v1/auth/me` uses the normal SkillHub `ApiResponse` envelope:

```json
{
  "code": 0,
  "msg": "获取成功",
  "data": {
    "userId": "local-user",
    "displayName": "Local User",
    "email": "local-user@example.com",
    "avatarUrl": "",
    "oauthProvider": "mock",
    "platformRoles": ["USER"]
  },
  "timestamp": "2026-06-08T00:00:00Z",
  "requestId": "..."
}
```

Behavior:

- If `X-Mock-User-Id` is present and maps to an active `user_account`, return that user.
- Read platform roles from `user_role_binding` joined to `role`.
- If the user has no platform role bindings, return `["USER"]`.
- Sort role codes for deterministic Java/Python comparison.
- Use empty string for null `email` and `avatar_url`, matching Java `AuthMeResponse`.
- Set `oauthProvider` to `"mock"` for this bridge.
- Return Java's localized read success message, `"获取成功"`, not the raw i18n key.
- If `X-Mock-User-Id` is missing, blank, unknown, or disabled, return HTTP `401`.

## Files

Allowed changes:

- Create `server-python/app/api/auth.py`.
- Create `server-python/tests/test_auth_me.py`.
- Create `server-python/tests/test_auth_me_repository.py`.
- Modify `server-python/app/main.py` to include the auth router.
- Modify `web/vite.config.ts` and `web/vite.config.test.ts` for route ownership.
- Modify `scripts/dev-hybrid.ps1` and `server-python/tests/test_hybrid_makefile.py` for live gate.
- Update `docs/backend-python-migration/route-registry.md`.
- Update `docs/backend-python-migration/migration-sequence-plan.md`.
- Write result file after verification.

Forbidden changes:

- Do not modify any file under `server/`.
- Do not manually edit `web/src/api/generated/schema.d.ts`.
- Do not migrate login, OAuth, token, session bootstrap, CLI auth, CSRF, or mutating auth behavior.

## TDD Tasks

### Task 1. Auth DTO And Repository Contract

- [ ] Write failing tests in `server-python/tests/test_auth_me_repository.py` for:
  - active user maps to `userId`, `displayName`, `email`, `avatarUrl`, `oauthProvider`, and sorted `platformRoles`;
  - missing role bindings return default `["USER"]`;
  - disabled or missing user returns `None`.
- [ ] Run `cd server-python; uv run pytest tests/test_auth_me_repository.py -q` and confirm it fails because `app.api.auth` does not exist.
- [ ] Implement `read_current_mock_user(engine, user_id)` and `build_auth_me_response(...)` in
  `server-python/app/api/auth.py`.
- [ ] Re-run the repository tests and confirm they pass.

### Task 2. FastAPI Route Contract

- [ ] Write failing tests in `server-python/tests/test_auth_me.py` for:
  - `GET /api/v1/auth/me` with `X-Mock-User-Id` returns a SkillHub envelope and request id;
  - missing `X-Mock-User-Id` returns `401`;
  - blank `X-Mock-User-Id` returns `401`.
- [ ] Run `cd server-python; uv run pytest tests/test_auth_me.py -q` and confirm it fails because the router is not registered.
- [ ] Include the auth router from `server-python/app/main.py`.
- [ ] Re-run the route tests and confirm they pass.

### Task 3. Vite Ownership

- [ ] Add a Vite proxy rule for `/api/v1/auth/me` to `http://localhost:8081` before `/api`.
- [ ] Add `web/vite.config.test.ts` assertions that:
  - `/api/v1/auth/me` resolves to Python;
  - `/api/v1/auth/methods` resolves to Java;
  - `/api/v1/auth/providers` resolves to Java;
  - `/oauth2/authorization/github` resolves to Java.
- [ ] Run `cd web; npx vitest vite.config.test.ts --run` and confirm it passes.

### Task 4. Live Verification Gate

- [ ] Add `verify-auth-me-smoke` to `scripts/dev-hybrid.ps1`.
- [ ] The gate must compare Java direct, Python direct, and Vite proxy for:
  - `X-Mock-User-Id: local-user`;
  - `X-Mock-User-Id: local-admin`;
  - no mock header status behavior.
- [ ] The gate must ignore volatile `timestamp` and `requestId`.
- [ ] The gate must confirm `/api/v1/auth/methods` still routes through Java from Vite.
- [ ] Update `server-python/tests/test_hybrid_makefile.py` so the script documents the new gate.
- [ ] Run the script test with `cd server-python; uv run pytest tests/test_hybrid_makefile.py -q`.

### Task 5. Docs, Verification, Commit

- [ ] Update `docs/backend-python-migration/route-registry.md`.
- [ ] Update `docs/backend-python-migration/migration-sequence-plan.md`.
- [ ] Write `docs/backend-python-migration/results/2026-06-08-auth-current-user-bridge.md`
  after verification.
- [ ] Run:
  - `cd server-python; uv run pytest`
  - `cd web; npx vitest vite.config.test.ts --run`
  - `cd web; npx tsc --noEmit`
  - `powershell -ExecutionPolicy Bypass -File scripts/dev-hybrid.ps1 verify-auth-me-smoke`
  - `git diff --check`
  - `git diff --name-only -- server`
- [ ] Commit and push to `dev`.

## Acceptance Criteria

- `GET /api/v1/auth/me` is Python-owned and Java/Python/Vite stable contracts match for local
  mock users.
- Missing or invalid local mock user returns `401`.
- Java remains owner for all other auth/OAuth/token/CLI auth routes listed above.
- Frontend `useAuth()` can call `/api/v1/auth/me` through Vite.
- No `server/` file is modified.
- Result documentation is completed before commit.

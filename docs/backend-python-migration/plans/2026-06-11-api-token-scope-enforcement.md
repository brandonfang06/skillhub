# API Token Scope Enforcement

## Summary

Move the Java API-token scope guard for the already Python-owned token management routes into
FastAPI. This milestone does not introduce global bearer-token authorization middleware. It only
enforces the existing Java policy for `/api/v1/tokens` and `/api/v1/tokens/**`.

## Route Ownership

| Method | Path | Before | After | Required bearer scope |
| --- | --- | --- | --- | --- |
| POST | `/api/v1/tokens` | python | python | `token:manage` |
| GET | `/api/v1/tokens` | python | python | `token:manage` |
| DELETE | `/api/v1/tokens/{id}` | python | python | `token:manage` |
| PUT | `/api/v1/tokens/{id}/expiration` | python | python | `token:manage` |

`X-Mock-User-Id` remains the development bridge and keeps precedence over `Authorization`.

## Java Parity Checklist

Reference files:

- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/policy/RouteSecurityPolicyRegistry.java`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/token/ApiTokenScopeService.java`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/token/ApiTokenScopeFilter.java`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/token/ApiTokenAuthenticationFilter.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/TokenController.java`

| Area | Classification | Notes |
| --- | --- | --- |
| API contract | covered | Token CRUD response bodies/statuses remain from the previous token management milestone. |
| Authorization/session behavior | covered | Valid bearer principals with `token:manage` are allowed; valid bearer principals without it are rejected with `403`; bad/missing bearer stays `401`. |
| Database transaction atomicity | not applicable | No token CRUD persistence changes beyond using the already migrated token service. |
| Audit actor/timestamp fields | not applicable | Java token management routes do not add a separate audit-log side effect for this scope guard. |
| Storage and side effects | not applicable | No storage side effects. |
| Live verification evidence | covered | Windows live gate compares Java/Python/proxy allow/deny status and route behavior. |

## Implementation Plan

1. Add route-level tests for bearer tokens with and without `token:manage`.
2. Reuse the current-principal bearer bridge in token routes.
3. Add a narrow `token:manage` guard for bearer `oauthProvider = api_token` principals.
4. Keep mock-user development auth behavior unchanged.
5. Add a Windows hybrid live gate for Java/Python/proxy scope parity.
6. Update the route registry, sequence plan, and result document.

## Tests

```powershell
cd server-python
uv run pytest tests/test_api_tokens.py tests/test_auth_bearer.py tests/test_hybrid_makefile.py -q
```

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-api-token-scope-smoke
```

## Boundaries

- Do not modify `server/`.
- Do not move any new route ownership.
- Do not add global bearer-token authorization middleware in this milestone.
- Do not change OAuth/session behavior.

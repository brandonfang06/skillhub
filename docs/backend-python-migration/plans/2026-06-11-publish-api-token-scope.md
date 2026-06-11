# Publish API Token Scope Enforcement

## Summary

Add Java-compatible API-token scope enforcement to already Python-owned publish routes. This
milestone does not move new route ownership and does not introduce full global bearer-token
middleware. It only applies the Java `skill:publish` route policy to publish endpoints that already
execute in FastAPI.

## Route Ownership

| Method | Path | Before | After | Required bearer scope |
| --- | --- | --- | --- | --- |
| POST | `/api/cli/v1/skills/{namespace}/publish/validate` | python | python | `skill:publish` |
| POST | `/api/cli/v1/skills/{namespace}/publish` | python | python | `skill:publish` |
| POST | `/api/v1/skills/{namespace}/publish` | python | python | `skill:publish` |
| POST | `/api/web/skills/{namespace}/publish` | python | python | `skill:publish` |
| POST | `/api/v1/skills` | python | python | `skill:publish` |
| POST | `/api/v1/publish` | python | python | `skill:publish` |

`X-Mock-User-Id` remains the local development bridge and keeps precedence over `Authorization`.

## Java Parity Checklist

Reference files:

- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/policy/RouteSecurityPolicyRegistry.java`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/token/ApiTokenScopeService.java`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/token/ApiTokenScopeFilter.java`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/token/ApiTokenAuthenticationFilter.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/compat/ClawHubCompatController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillPublishController.java`

| Area | Classification | Notes |
| --- | --- | --- |
| API contract | covered | Publish response bodies stay unchanged; this milestone only changes bearer auth boundary. |
| Authorization/session behavior | covered | Bearer `api_token` principals need `skill:publish`; missing scope returns `403`; bad bearer returns `401`; mock-user precedence remains. |
| Database transaction atomicity | not applicable | No publish persistence path changes. |
| Audit actor/timestamp fields | not applicable | Existing publish audit behavior is unchanged. |
| Storage and side effects | not applicable | Existing package/storage write behavior is unchanged. |
| Live verification evidence | covered | Windows live gate compares Java/Python/proxy bearer allow/deny status. |

## Implementation Plan

1. Add FastAPI route tests for bearer `skill:publish`, missing scope, bad bearer, and mock
   precedence.
2. Reuse the current-principal bearer bridge in publish routes.
3. Require `skill:publish` only for bearer `oauthProvider = api_token` principals.
4. Add Windows live gate coverage for publish-scope allow/deny parity.
5. Update route registry, migration sequence plan, and result document.

## Tests

```powershell
cd server-python
uv run pytest tests/test_publish_http_validate.py tests/test_auth_bearer.py tests/test_hybrid_makefile.py -q
```

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-publish-token-scope-smoke
```

## Boundaries

- Do not modify `server/`.
- Do not move new routes.
- Do not add global bearer-token middleware in this milestone.
- Do not change publish storage, transaction, scanner, or side-effect behavior.

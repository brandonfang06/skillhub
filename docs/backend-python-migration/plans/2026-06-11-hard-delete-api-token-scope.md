# Hard Delete API Token Scope Enforcement Plan

## Summary

Add Java-compatible bearer API-token `skill:delete` scope enforcement to already Python-owned
whole-skill hard-delete routes. This milestone does not move new route ownership and does not
change OAuth, Spring Session, CSRF, or CLI delete ownership.

## Route Ownership

| Method | Path | Before | After | Required bearer scope |
| --- | --- | --- | --- | --- |
| DELETE | `/api/v1/skills/id/{skillId}` | python | python | `skill:delete` |
| DELETE | `/api/v1/skills/{namespace}/{slug}` | python | python | `skill:delete` |
| DELETE | `/api/web/skills/id/{skillId}` | python | python | unsupported for API token |
| DELETE | `/api/web/skills/{namespace}/{slug}` | python | python | unsupported for API token |

`X-Mock-User-Id` remains the local development bridge and keeps precedence over `Authorization`.
`DELETE /api/cli/v1/skills/{namespace}/{slug}` remains Java-owned and out of scope. Java's
`RouteSecurityPolicyRegistry` defines `skill:delete` only for v1 hard-delete routes; web
hard-delete routes stay browser/mock-user authenticated and reject API-token principals as
unsupported.

## Java Parity Checklist

Reference files:

- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/policy/RouteSecurityPolicyRegistry.java`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/token/ApiTokenScopeService.java`
- `server/skillhub-auth/src/test/java/com/iflytek/skillhub/auth/policy/RouteSecurityPolicyRegistryTest.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SkillController.java`

| Area | Status | Notes |
| --- | --- | --- |
| API contract | covered | Existing hard-delete envelopes and route ownership remain unchanged. |
| Authorization/session behavior | covered | v1 bearer `api_token` principals need `skill:delete`; missing scope returns `403`; bad bearer returns `401`; web bearer hard-delete returns Java-compatible unsupported `403`; mock-user precedence remains. Existing v1 `SUPER_ADMIN` and web owner/super-admin checks remain. |
| Database transaction atomicity | not applicable | No hard-delete workflow transaction changes. |
| Audit actor/timestamp fields | covered | Bearer actor user id is passed to the existing hard-delete input just like mock-user actors. |
| Storage and side effects | not applicable | No storage deletion behavior changes. |
| Live verification evidence | pending | Windows live gate must compare Java/Python/proxy allow and deny behavior. |

## Implementation Steps

1. Add focused FastAPI tests for v1 bearer `skill:delete`, missing scope, unknown bearer, web
   bearer unsupported, and mock precedence on hard-delete routes.
2. Update the hard-delete route auth boundary to resolve either mock-user or bearer-token current
   user.
3. Require `skill:delete` only for bearer `oauthProvider = api_token` principals.
4. Add a Windows live gate action for hard-delete token-scope parity.
5. Update route registry, migration sequence plan, and result docs.

## Verification

```powershell
cd server-python
uv run pytest tests/test_skill_hard_delete.py tests/test_auth_bearer.py tests/test_hybrid_makefile.py -q
cd ..
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-hard-delete-token-scope-smoke
git diff --name-only -- server
git diff --check
```

## Boundaries

- Do not modify `server/`.
- Do not move CLI delete ownership.
- Do not add a new `skill:read` requirement; Java does not require it for current read routes.
- Do not change hard-delete DB/storage side effects.

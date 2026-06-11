# Bearer Token Current Principal Bridge Result

Date: 2026-06-11

## Routes Changed

No new route ownership moved. These existing Python-owned routes now accept bearer-token
authentication in addition to the local mock-user header:

| Method | Route | Owner |
|---|---|---|
| GET | `/api/v1/auth/me` | Python |
| GET | `/api/v1/whoami` | Python |
| GET | `/api/cli/v1/auth/whoami` | Python |

## Summary

Python current-principal reads now support `Authorization: Bearer sk_...` with Java-compatible
behavior:

- `X-Mock-User-Id` keeps precedence for local/hybrid test workflows.
- Bearer token is SHA-256 hashed before DB lookup.
- Token must be active: not revoked and not expired.
- Token user must be `ACTIVE`.
- Response projects `oauthProvider = api_token`.
- Platform roles are read from `user_role_binding` with default `USER` fallback.
- Successful bearer auth touches `api_token.last_used_at`.

This milestone intentionally does not enable global API-token scope enforcement for every Python
route. That remains a separate security-boundary milestone.

## Java Parity Checklist

| Area | Outcome |
|---|---|
| Java references | Covered: `ApiTokenAuthenticationFilter`, `ApiTokenService.validateToken`, `ApiTokenScopeFilter`, `RouteSecurityPolicyRegistry`, `AuthController`, `ClawHubCompatController`, `CliAuthController`. |
| API contract | Covered for `/api/v1/auth/me`, `/api/v1/whoami`, and `/api/cli/v1/auth/whoami`. |
| Authorization/session | Covered for bearer-token current-principal reads. OAuth callbacks and Spring Session cookies remain deferred. |
| Database effects | Covered: active token lookup, active-user lookup, role projection, and `last_used_at` update. |
| Scope enforcement | Deferred: current-principal routes are allowed by Java token policy; global endpoint scope enforcement is not part of this milestone. |
| Live verification | Passed with Java/Python/proxy stable response comparison and DB evidence. |

## Verification

- `cd server-python; uv run pytest tests/test_auth_bearer.py tests/test_auth_me.py tests/test_auth_whoami.py tests/test_hybrid_makefile.py -q`
  - Passed: 19 tests.
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 -Action verify-bearer-current-principal-smoke`
  - Passed.
  - Result artifact: `.dev/bearer-current-principal-contract-result.json`.
  - Checks: `authMeMatches`, `clawHubMatches`, `cliMatches`, `allEvidencePassed`, and `badTokenStatusesMatch` were all `true`.

## Files Changed

- `server-python/app/api/auth.py`
- `server-python/tests/test_auth_bearer.py`
- `server-python/tests/test_hybrid_makefile.py`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-11-bearer-token-current-principal.md`
- `docs/backend-python-migration/results/2026-06-11-bearer-token-current-principal.md`

## Follow-Up

- Decide whether to extend bearer-token principal resolution to all Python protected-route helpers
  or introduce middleware/dependency refactoring first.
- Implement Java-compatible global scope enforcement before treating bearer auth as complete for
  mutating APIs.
- OAuth callback/authorization and Spring Session cookie persistence remain deferred.

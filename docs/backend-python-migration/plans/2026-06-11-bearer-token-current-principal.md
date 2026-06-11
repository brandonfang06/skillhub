# Bearer Token Current Principal Bridge Plan

Date: 2026-06-11

## Scope

Add Python bearer-token authentication support for current-principal read routes that are already
Python-owned:

| Method | Route | Ownership change |
|---|---|---|
| GET | `/api/v1/auth/me` | none; remains Python |
| GET | `/api/v1/whoami` | none; remains Python |
| GET | `/api/cli/v1/auth/whoami` | none; remains Python |

The milestone widens the accepted authentication source from `X-Mock-User-Id` only to:

1. `X-Mock-User-Id` when present, preserving the existing local-dev bridge.
2. `Authorization: Bearer <raw-token>` when no mock user header is present.

Out of scope:

- OAuth callback/session establishment.
- Spring Session cookie persistence.
- Global bearer-token enforcement for every Python route.
- API token scope enforcement on arbitrary endpoints.
- Any `server/` edits.

## Java Parity Contract

Reference behavior:

- `ApiTokenAuthenticationFilter`
- `ApiTokenService.validateToken`
- `ApiTokenScopeFilter`
- `RouteSecurityPolicyRegistry`

Parity expectations for this milestone:

- Only paths under `/api/v1/`, `/api/web/`, or `/api/cli/` consider bearer tokens in Java.
- Header must start with `Bearer `.
- Raw token is SHA-256 hashed and looked up by `api_token.token_hash`.
- Token must be active: not revoked and not expired.
- Token user must exist and be `ACTIVE`.
- `last_used_at` is touched after successful authentication.
- The principal has provider `api_token`, default `USER` role fallback, explicit platform roles, and token scopes.
- Current-principal response shape matches the existing Python route contracts.

## Python Design

- Add a small bearer-token resolver in `server-python/app/api/auth.py`.
- Keep `X-Mock-User-Id` precedence so existing local tests and Windows gates remain stable.
- Reuse existing `sha256_token` from `app.auth.tokens`.
- Read `api_token`, `user_account`, and platform roles with explicit SQL.
- Touch `api_token.last_used_at` in the same successful-auth transaction.
- Do not add global middleware yet; this milestone only changes the current-principal routes and shared helper.

## Tests

Add/update Python tests for:

- Valid bearer token returns the same `auth/me`, ClawHub whoami, and CLI whoami shapes as mock auth.
- Bearer token updates `last_used_at`.
- Revoked, expired, unknown, malformed, and disabled-user tokens return `401`.
- `X-Mock-User-Id` takes precedence over bearer token.

Add/update Windows live gate:

- Seed Java/Python/proxy users and tokens.
- Compare stable Java/Python/proxy responses for the three current-principal routes using bearer auth.
- Verify `last_used_at` changed for each token.
- Verify malformed/unknown bearer tokens return the same unauthorized status.

## Files Allowed To Change

- `server-python/app/api/auth.py`
- `server-python/tests/test_auth_bearer.py`
- `server-python/tests/test_hybrid_makefile.py`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/**`

Forbidden: any file under `server/`.

## Exit Criteria

- `cd server-python; uv run pytest tests/test_auth_bearer.py tests/test_auth_me.py tests/test_auth_whoami.py tests/test_hybrid_makefile.py -q` passes.
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 -Action verify-bearer-current-principal-smoke` passes.
- `git diff --name-only -- server` is empty.
- Result document is written.
- Commit and push to `dev`.

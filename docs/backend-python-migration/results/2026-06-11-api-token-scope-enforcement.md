# API Token Scope Enforcement Result

## Summary

Added Java-compatible bearer API-token scope enforcement for the already Python-owned token
management routes:

- `POST /api/v1/tokens`
- `GET /api/v1/tokens`
- `DELETE /api/v1/tokens/{id}`
- `PUT /api/v1/tokens/{id}/expiration`

Bearer principals with `oauthProvider = api_token` must include `token:manage`. Missing or bad
bearer tokens still return `401`, and the development `X-Mock-User-Id` bridge keeps precedence.

## Route Ownership

No new route ownership moved. `/api/v1/tokens*` was already Python-owned; this milestone tightens
its bearer authorization behavior to match Java route policy.

## Java Parity Checklist Outcome

| Area | Outcome | Notes |
| --- | --- | --- |
| API contract | passed | Existing token CRUD envelopes/statuses retained. |
| Authorization/session behavior | passed | `token:manage` bearer can access; bearer without scope is `403`; unknown bearer is `401`; mock-user precedence is unchanged. |
| Database transaction atomicity | not applicable | No persistence semantics changed. |
| Audit actor/timestamp fields | not applicable | No audit side effect is owned by this guard. |
| Storage and side effects | not applicable | No storage side effects. |
| Live verification evidence | passed | Windows live gate compared Java/Python/proxy allow and deny behavior. |

## Tests

Passed:

```powershell
cd server-python
uv run pytest tests/test_api_tokens.py tests/test_auth_bearer.py tests/test_hybrid_makefile.py -q
```

Passed:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-api-token-scope-smoke
```

Live gate evidence:

- Java/Python/proxy `GET /api/v1/tokens` with bearer `token:manage` returned matching stable list
  envelopes.
- Java/Python/proxy `POST /api/v1/tokens` with bearer `token:manage` returned matching stable create
  envelopes.
- Java/Python/proxy bearer tokens without `token:manage` returned `403` for list and create.
- Java/Python/proxy unknown bearer tokens returned `401`.
- Successful and denied bearer attempts both touched `last_used_at`, matching Java filter behavior.
- Frontend smoke E2E passed after the contract comparison.

## Risks And Follow-Up

- Broader Java `RouteSecurityPolicyRegistry` parity remains deferred. This milestone only covers
  `/api/v1/tokens` and `/api/v1/tokens/**`.
- OAuth/session cookie behavior remains deferred to final auth/session replacement work.

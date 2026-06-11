# Publish API Token Scope Enforcement Result

## Summary

Added Java-compatible bearer API-token `skill:publish` scope enforcement for already Python-owned
publish routes:

- `POST /api/cli/v1/skills/{namespace}/publish/validate`
- `POST /api/cli/v1/skills/{namespace}/publish`
- `POST /api/v1/skills/{namespace}/publish`
- `POST /api/web/skills/{namespace}/publish`
- `POST /api/v1/skills`
- `POST /api/v1/publish`

No new route ownership moved. The milestone only tightens the bearer authorization boundary.

## Route Ownership

All listed routes were already Python-owned before this milestone and remain Python-owned.

## Java Parity Checklist Outcome

| Area | Outcome | Notes |
| --- | --- | --- |
| API contract | passed | Existing publish envelopes/plain ClawHub responses are unchanged. |
| Authorization/session behavior | passed | Bearer `api_token` principals require `skill:publish`; missing scope is `403`; unknown bearer is `401`; mock-user precedence is unchanged. |
| Database transaction atomicity | not applicable | Publish persistence behavior is unchanged. |
| Audit actor/timestamp fields | not applicable | Existing publish audit behavior is unchanged. |
| Storage and side effects | not applicable | Existing publish storage/write behavior is unchanged. |
| Live verification evidence | passed | Windows live gate compared Java/Python/proxy bearer allow/deny behavior. |

## Tests

Passed:

```powershell
cd server-python
uv run pytest tests/test_publish_http_validate.py tests/test_auth_bearer.py tests/test_hybrid_makefile.py -q
```

Passed:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-publish-token-scope-smoke
```

Live gate evidence:

- Java/Python/proxy `POST /api/cli/v1/skills/global/publish/validate` with bearer
  `skill:publish` returned matching stable success contracts.
- Java/Python/proxy bearer tokens without `skill:publish` returned `403` for:
  - `POST /api/cli/v1/skills/{namespace}/publish/validate`
  - `POST /api/cli/v1/skills/{namespace}/publish`
  - `POST /api/v1/skills/{namespace}/publish`
  - `POST /api/web/skills/{namespace}/publish`
  - `POST /api/v1/publish`
  - `POST /api/v1/skills`
- Java/Python/proxy unknown bearer tokens returned `401`.
- Successful and denied bearer attempts both touched `last_used_at`, matching Java filter ordering.
- Frontend smoke E2E passed after the contract comparison.

## Risks And Follow-Up

- This milestone covers only Java publish-route `skill:publish` policy. Broader Java
  `RouteSecurityPolicyRegistry` parity for other API token routes remains deferred.
- OAuth callback/session cookie establishment remains deferred to final auth/session replacement.

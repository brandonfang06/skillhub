# Hard Delete API Token Scope Enforcement Result

## Summary

Added Java-compatible bearer API-token policy behavior for already Python-owned whole-skill
hard-delete routes.

No new route ownership moved.

## Routes Changed

| Method | Path | Owner before | Owner after | Behavior |
| --- | --- | --- | --- | --- |
| DELETE | `/api/v1/skills/id/{skillId}` | python | python | Bearer `api_token` requires `skill:delete`; mock-user precedence unchanged. |
| DELETE | `/api/v1/skills/{namespace}/{slug}` | python | python | Bearer `api_token` requires `skill:delete`; mock-user precedence unchanged. |
| DELETE | `/api/web/skills/id/{skillId}` | python | python | Bearer `api_token` is rejected as Java-compatible unsupported `403`; mock-user auth unchanged. |
| DELETE | `/api/web/skills/{namespace}/{slug}` | python | python | Bearer `api_token` is rejected as Java-compatible unsupported `403`; mock-user auth unchanged. |

`DELETE /api/cli/v1/skills/{namespace}/{slug}` remains Java-owned.

## Java Parity Checklist

| Area | Outcome | Notes |
| --- | --- | --- |
| API contract | passed | Existing hard-delete response envelopes and side-effect behavior are unchanged. |
| Authorization/session behavior | passed | v1 bearer `skill:delete` is allowed; v1 bearer missing scope is `403`; unknown bearer is `401`; web bearer hard-delete is unsupported `403`; `X-Mock-User-Id` precedence remains. |
| Database transaction atomicity | not applicable | No hard-delete workflow transaction changes. |
| Audit actor/timestamp fields | passed | Bearer actor user id flows through the existing hard-delete input and audit path. |
| Storage and side effects | not applicable | No storage deletion behavior changes. |
| Live verification evidence | passed | Windows live gate wrote `.dev/hard-delete-token-scope-contract-result.json` with all checks true. |

## Tests

```powershell
cd server-python
uv run pytest tests/test_skill_hard_delete.py tests/test_auth_bearer.py tests/test_hybrid_makefile.py -q
```

Result: `16 passed, 1 warning`.

Windows live gate:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-hard-delete-token-scope-smoke
```

Result:

- Python pytest: `16 passed, 1 warning`.
- Vite proxy tests: `46 passed`.
- Java/Python/proxy hard-delete bearer `skill:delete` delete envelopes matched.
- Java/Python/proxy v1 bearer without `skill:delete` returned `403`.
- Java/Python/proxy unknown bearer returned `401`.
- Java/Python/proxy web hard-delete bearer access returned unsupported `403`.
- DB evidence passed for deleted skill/version/file rows, `DELETE_SKILL_HARD` audit, and
  `last_used_at` touches for both allowed and denied bearer tokens.
- Frontend smoke E2E: `6 passed`.
- Post-gate status confirmed Java backend, Python backend, and Vite frontend stopped.

## Risks And Follow-Up

- Java route policy does not allow bearer API tokens on web hard-delete routes, even with
  `skill:delete`. Python intentionally preserves that unsupported `403` instead of broadening web
  API-token access.
- Remaining auth/session work still includes OAuth/session replacement, any remaining route-policy
  scope enforcement, active SSE fanout, and final proxy cleanup.

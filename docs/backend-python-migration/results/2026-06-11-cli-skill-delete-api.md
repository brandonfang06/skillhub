# CLI Skill Delete API Result

## Summary

Moved `DELETE /api/cli/v1/skills/{namespace}/{slug}` from Java to Python.

The Python route reuses the existing whole-skill hard-delete workflow and adapts the result to
Java's CLI delete response shape:

```json
{
  "ok": true,
  "scope": "remote",
  "action": "delete",
  "namespace": "team",
  "slug": "demo"
}
```

## Routes Changed

| Method | Path | Owner before | Owner after | Behavior |
| --- | --- | --- | --- | --- |
| DELETE | `/api/cli/v1/skills/{namespace}/{slug}` | java | python | Authenticated CLI whole-skill hard delete. Bearer API tokens require `skill:delete`; mock-user precedence remains. |

## Java Parity Checklist

| Area | Outcome | Notes |
| --- | --- | --- |
| API contract | passed | Route test covers Java `ApiResponse` envelope, `删除成功` message, request id propagation, and CLI response data. |
| Authorization/session behavior | passed | Missing auth remains `401`; bearer `skill:delete` succeeds; bearer without scope is `403`; bad bearer is `401`; mock user takes precedence over bearer. |
| Database transaction atomicity | passed via reused workflow | The CLI adapter delegates to the existing `hard_delete_skill` transaction path. |
| Audit actor/timestamp fields | passed via reused workflow | The adapter passes actor user id, request id, client IP, and user agent through `SkillHardDeleteInput`. |
| Storage and side effects | passed via reused workflow | Existing hard-delete tests cover related-row cleanup, audit insert, local storage deletion, and storage compensation path. |
| Live verification evidence | passed | `verify-cli-skill-delete-smoke` now compares Java, direct Python, and Vite proxy contracts and writes `.dev/cli-skill-delete-contract-result.json`. The first live run found the Java DTO field names were `ok/scope/action`; Python and tests were corrected before the passing run. |

## Tests

Red checks run before implementation:

```powershell
cd server-python
uv run pytest tests/test_skill_hard_delete.py::test_cli_skill_delete_route_returns_java_cli_envelope tests/test_skill_hard_delete.py::test_cli_skill_delete_route_enforces_bearer_delete_scope -q
```

Result before implementation: `2 failed`; both failures were expected `404` for missing Python route.

Passed after implementation:

```powershell
cd server-python
uv run pytest tests/test_skill_hard_delete.py -q
```

Result: `7 passed, 1 warning`.

Proxy red check before adding the Vite method-aware rule:

```powershell
cd web
npm.cmd run test -- vite.config.test.ts
```

Result before proxy change: `1 failed | 45 passed`; `DELETE /api/cli/v1/skills/global/agent-helper` resolved to `undefined` instead of Python.

Passed after proxy change:

```powershell
cd web
npm.cmd run test -- vite.config.test.ts
```

Result: `46 passed`.

Final targeted verification:

```powershell
cd server-python
uv run pytest tests/test_skill_hard_delete.py tests/test_auth_bearer.py tests/test_hybrid_makefile.py -q
```

Result: `18 passed, 1 warning`.

```powershell
cd web
npm.cmd run test -- vite.config.test.ts
```

Result: `46 passed`.

```powershell
git diff --name-only -- server
```

Result: no output.

```powershell
git diff --check
```

Result: no whitespace errors. Git emitted only Windows line-ending warnings for touched text files.

## Review Pass

Local review compared the Python adapter against the Java reference route and
`RouteSecurityPolicyRegistry`:

- Java requires authenticated access for `DELETE /api/cli/v1/skills/*/*`; Python now requires
  current mock user or bearer principal.
- Java requires `skill:delete` for API-token principals on the CLI delete route; Python now enforces
  the same missing-scope `403` and bad-bearer `401` behavior.
- Java delegates CLI delete to whole-skill hard-delete without explicit owner fallback; Python uses
  `route_scope = "cli"`, no `owner_id`, and does not use the web owner fallback.
- Java returns `ApiResponse<CliDeleteResponse>`; Python adapts hard-delete output to
  `{ ok, scope, action, namespace, slug }`.
- Vite now routes the DELETE method for `/api/cli/v1/skills/{namespace}/{slug}` to Python while
  keeping `/api/**` fallback and `/oauth2/**` Java-owned.

## Files Changed

- `server-python/app/api/lifecycle.py`
- `server-python/tests/test_skill_hard_delete.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `docs/backend-python-migration/plans/2026-06-11-cli-skill-delete-api.md`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/results/2026-06-11-cli-skill-delete-api.md`
- `docs/backend-python-migration/plans/2026-06-11-cli-skill-delete-live-smoke.md`
- `docs/backend-python-migration/results/2026-06-11-cli-skill-delete-live-smoke.md`

## Known Risks

- OAuth and Spring Session establishment remain Java-owned/deferred.
- Active SSE notification fanout and final proxy cleanup remain deferred.

## Follow-Up Work

- Continue with remaining auth/session/global route-policy cleanup or final proxy cleanup based on
  route ownership priority.

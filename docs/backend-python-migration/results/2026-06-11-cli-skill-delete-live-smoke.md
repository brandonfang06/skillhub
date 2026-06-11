# CLI Skill Delete Live Smoke Result

## Summary

Added `scripts/dev-hybrid.ps1 -Action verify-cli-skill-delete-smoke`.

The smoke target starts the hybrid Java/Python/Vite stack, compares Java, direct Python, and Vite
proxy behavior for `DELETE /api/cli/v1/skills/{namespace}/{slug}`, checks destructive side effects,
and writes `.dev/cli-skill-delete-contract-result.json`.

## Review Finding From Live Gate

The first live run failed the API contract comparison:

- Java returned CLI data fields `{ ok, scope, action, namespace, slug }`.
- Python initially returned `{ deleted, target, operation, namespace, slug }`.
- Side-effect evidence still passed for all three channels.
- Bearer scope checks still passed for all three channels.

Fix applied:

- Updated Python CLI response mapping to Java's actual `CliDeleteResponse` DTO shape.
- Updated route tests and migration docs to use `ok/scope/action`.
- Updated the live smoke comparison fields to `data.ok`, `data.scope`, and `data.action`.

## Live Smoke Coverage

| Check | Result | Evidence |
| --- | --- | --- |
| Java/Python/proxy delete envelope | passed | Stable `code`, `msg`, `data.ok`, `data.scope`, `data.action`, namespace, and slug match after normalization. |
| DB side effects | passed | `skill`, `skill_version`, `skill_file`, `skill_search_document`, and `security_audit` rows are removed for each fixture. |
| Audit side effect | passed | `DELETE_SKILL_HARD` audit row exists for each deleted fixture. |
| Storage side effect | passed | Fixture local storage files are removed for each deleted fixture. |
| Bearer delete scope | passed | Bearer token with `skill:delete` succeeds for Java, direct Python, and proxy. |
| Missing bearer scope | passed | Bearer token with only `skill:read` returns `403` for Java, direct Python, and proxy. |
| Unknown bearer token | passed | Unknown bearer token returns `401` for Java, direct Python, and proxy. |
| Playwright smoke | passed | Hybrid frontend smoke suite passed after the contract check. |

## Tests

Red guard before script implementation:

```powershell
cd server-python
uv run pytest tests/test_hybrid_makefile.py -q
```

Result before implementation: `1 failed, 5 passed`; missing `verify-cli-skill-delete-smoke`.

Red contract correction after the first live smoke found the Java DTO mismatch:

```powershell
cd server-python
uv run pytest tests/test_skill_hard_delete.py::test_cli_skill_delete_route_returns_java_cli_envelope tests/test_skill_hard_delete.py::test_cli_skill_delete_route_enforces_bearer_delete_scope -q
```

Result before mapper correction: `2 failed`; Python still returned `deleted/target/operation`.

Passed after correction:

```powershell
cd server-python
uv run pytest tests/test_skill_hard_delete.py::test_cli_skill_delete_route_returns_java_cli_envelope tests/test_skill_hard_delete.py::test_cli_skill_delete_route_enforces_bearer_delete_scope -q
```

Result: `2 passed, 1 warning`.

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
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 -Action verify-cli-skill-delete-smoke
```

Result: passed. The target also ran `18 passed, 1 warning`, `46 passed`, the
Java/Python/proxy contract comparison, and `6 passed` Playwright smoke tests.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 -Action status
```

Result: Java backend, Python backend, and Vite frontend all stopped; Docker compose had no running
project services.

## Files Changed

- `scripts/dev-hybrid.ps1`
- `server-python/app/api/lifecycle.py`
- `server-python/tests/test_skill_hard_delete.py`
- `server-python/tests/test_hybrid_makefile.py`
- `docs/backend-python-migration/plans/2026-06-11-cli-skill-delete-live-smoke.md`
- `docs/backend-python-migration/results/2026-06-11-cli-skill-delete-api.md`
- `docs/backend-python-migration/results/2026-06-11-cli-skill-delete-live-smoke.md`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`

## Review Pass

- Java source under `server/` was only read for parity; no Java files were modified.
- The live fixtures use timestamped slugs, so repeated runs do not depend on stale deleted rows.
- The mock-user path deletes as `local-user`, matching the authenticated CLI route's non-owner-specific
  delete delegation.
- The bearer path verifies both success and Java-compatible auth failures before deleting with the
  valid token.
- The contract comparison normalizes only volatile namespace/slug values and compares the real CLI
  DTO field names.

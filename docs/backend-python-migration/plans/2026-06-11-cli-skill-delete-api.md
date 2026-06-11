# CLI Skill Delete API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `DELETE /api/cli/v1/skills/{namespace}/{slug}` from Java to Python while preserving Java hard-delete side effects, CLI response shape, and API-token scope behavior.

**Architecture:** Reuse the existing Python whole-skill hard-delete workflow instead of creating a second deletion path. Add a CLI route adapter that authenticates like Java's CLI route policy, calls the existing hard-delete helper with CLI scope, and transforms the hard-delete result into Java's `CliDeleteResponse` shape.

**Tech Stack:** FastAPI, SQLAlchemy async engine, pytest, Vite method-aware dev proxy, Java Spring Boot as read-only parity reference.

---

## Scope

Migrate only:

- `DELETE /api/cli/v1/skills/{namespace}/{slug}`

Do not migrate or change:

- `POST /api/v1/skills/{canonicalSlug}/undelete`
- `/oauth2/**`
- Spring Session cookie establishment
- Broad global route-policy refactors
- Java files under `server/`

## Java Reference Files

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/cli/CliSkillController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/cli/CliSkillAppService.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/SkillDeleteAppService.java`
- `server/skillhub-auth/src/main/java/com/iflytek/skillhub/auth/policy/RouteSecurityPolicyRegistry.java`

Java behavior to preserve:

- Route requires an authenticated principal.
- Bearer API token principals require `skill:delete`.
- The route delegates to whole-skill hard-delete with no explicit `ownerId`.
- Missing or ambiguous namespace/slug returns a successful envelope with `deleted = false`.
- Success response is `ApiResponse<CliDeleteResponse>` with message `删除成功`.
- CLI response data contains `deleted`, `target = "remote"`, `operation = "delete"`, `namespace`, and `slug`.

## Java Parity Checklist

| Area | Planned outcome | Evidence |
| --- | --- | --- |
| API contract | covered | Add route tests for envelope message, request id, and CLI data shape. |
| Authorization/session behavior | covered | Add tests for missing auth, bearer `skill:delete`, missing scope, and mock-user precedence. |
| Database transaction atomicity | covered by reused workflow | Reuse existing `hard_delete_skill` transaction and storage cleanup path. |
| Audit actor/timestamp fields | covered by reused workflow | CLI adapter passes actor user, request id, client IP, and user agent to `SkillHardDeleteInput`. |
| Storage and side effects | covered by reused workflow | Existing hard-delete tests cover storage deletion and compensation behavior. |
| Live verification evidence | planned | Run the CLI delete contract smoke if available; otherwise record targeted pytest and proxy-test evidence plus blocker. |

## Files

- Modify: `server-python/app/api/lifecycle.py`
  - Add CLI delete route adapter and response-shape conversion.
  - Allow `route_scope="cli"` to use bearer API tokens with `skill:delete`.
- Modify: `server-python/app/lifecycle/hard_delete.py`
  - Treat CLI hard-delete like Java `deleteSkill(...)`: authenticated principal allowed, no SUPER_ADMIN route-level requirement, no portal owner fallback.
- Modify: `server-python/tests/test_skill_hard_delete.py`
  - Add CLI route tests for envelope, response data, and bearer scope.
- Modify: `web/vite.config.ts`
  - Route `DELETE /api/cli/v1/skills/{namespace}/{slug}` to Python.
- Modify: `web/vite.config.test.ts`
  - Change the proxy ownership assertions from Java to Python for CLI delete.
- Modify: `docs/backend-python-migration/route-registry.md`
  - Change the route owner from `java` to `python`.
- Modify: `docs/backend-python-migration/migration-sequence-plan.md`
  - Add the completed ownership entry and update remaining deferred summary.
- Create: `docs/backend-python-migration/results/2026-06-11-cli-skill-delete-api.md`
  - Record implementation, tests, and any live-gate result/blocker.

## Tasks

### Task 1: Route Test First

- [ ] Add a failing route test in `server-python/tests/test_skill_hard_delete.py` that calls `DELETE /api/cli/v1/skills/team/demo` with `X-Mock-User-Id`.
- [ ] Assert status `200`, Java success message `删除成功`, request id propagation, and data:

```python
{
    "deleted": True,
    "target": "remote",
    "operation": "delete",
    "namespace": "team",
    "slug": "demo",
}
```

- [ ] Assert the captured `SkillHardDeleteInput` has `route_scope == "cli"`, no `owner_id`, and the mock actor user id.
- [ ] Run:

```powershell
cd server-python
uv run pytest tests/test_skill_hard_delete.py::test_cli_skill_delete_route_returns_java_cli_envelope -q
```

Expected: fail because the route does not exist or returns the old Java/proxy boundary behavior in Python tests.

### Task 2: Bearer Scope Test First

- [ ] Add a failing route test for CLI delete bearer behavior.
- [ ] Assert bearer token with `skill:delete` succeeds.
- [ ] Assert bearer token without `skill:delete` returns `403` and does not call the hard-delete writer.
- [ ] Assert unknown bearer token returns `401`.
- [ ] Assert `X-Mock-User-Id` still takes precedence over an insufficient bearer token.
- [ ] Run:

```powershell
cd server-python
uv run pytest tests/test_skill_hard_delete.py::test_cli_skill_delete_route_enforces_bearer_delete_scope -q
```

Expected: fail because CLI route/scope handling is not implemented yet.

### Task 3: Implement Minimal Python Route

- [ ] In `server-python/app/api/lifecycle.py`, add `route_scope="cli"` support in `_read_hard_delete_user` for API-token principals with `skill:delete`.
- [ ] Add a helper that converts hard-delete workflow data into CLI response data:

```python
{
    "deleted": bool(data.get("deleted")),
    "target": "remote",
    "operation": "delete",
    "namespace": data.get("namespace"),
    "slug": data.get("slug"),
}
```

- [ ] Add `@router.delete("/api/cli/v1/skills/{namespace}/{slug}")` that calls `hard_delete_skill_route_data(..., route_scope="cli", owner_id=None, ...)`.
- [ ] In `server-python/app/lifecycle/hard_delete.py`, ensure only `route_scope == "v1"` requires `SUPER_ADMIN` and only `route_scope == "web"` uses actor-owner fallback for ambiguous namespace/slug candidates.
- [ ] Run both new tests and the existing hard-delete tests:

```powershell
cd server-python
uv run pytest tests/test_skill_hard_delete.py -q
```

Expected: pass.

### Task 4: Move Proxy And Registry Ownership

- [ ] In `web/vite.config.ts`, add a method-aware rule for:

```text
DELETE /api/cli/v1/skills/{namespace}/{slug}
```

- [ ] In `web/vite.config.test.ts`, update CLI read/download test expectations so delete now resolves to Python.
- [ ] In `docs/backend-python-migration/route-registry.md`, change the CLI delete route owner to `python`.
- [ ] Run:

```powershell
cd web
npm run test -- vite.config.test.ts
```

Expected: pass.

### Task 5: Result And Sequence Documentation

- [ ] Add a completed ownership row to `docs/backend-python-migration/migration-sequence-plan.md`.
- [ ] Update the remaining Java-owned/deferred summary to remove the CLI delete route from the explicit destructive-route gap.
- [ ] Create `docs/backend-python-migration/results/2026-06-11-cli-skill-delete-api.md`.
- [ ] Record exact tests run, route owner before/after, Java parity checklist outcome, known risks, and follow-up work.
- [ ] Confirm Java reference remains untouched:

```powershell
git diff --name-only -- server
```

Expected: no output.

### Task 6: Final Targeted Verification

- [ ] Run:

```powershell
cd server-python
uv run pytest tests/test_skill_hard_delete.py tests/test_auth_bearer.py tests/test_hybrid_makefile.py -q
```

- [ ] Run:

```powershell
cd web
npm run test -- vite.config.test.ts
```

- [ ] If a CLI delete live smoke target exists in `server-python/scripts/dev-hybrid.ps1`, run it and record the exact result. If not, record that live gate is deferred because no CLI delete smoke target exists yet.

Expected: targeted Python and proxy tests pass, and result doc records live-gate evidence or blocker.

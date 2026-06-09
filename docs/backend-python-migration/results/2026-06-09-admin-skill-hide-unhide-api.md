# Admin Skill Hide Unhide API Migration Result

## Summary

Moved platform-admin skill hide/unhide ownership to Python:

- `POST /api/v1/admin/skills/{skillId}/hide`
- `POST /api/v1/admin/skills/{skillId}/unhide`

Admin version yank remains Java-owned:

- `POST /api/v1/admin/skills/versions/{versionId}/yank`

## Implementation Notes

- Added a focused Python admin-governance module for skill hidden-overlay mutations.
- Added FastAPI routes that resolve the local mock user, require `SUPER_ADMIN`, and return the
  Java-compatible update-success envelope.
- Hide sets `hidden=true`, `hidden_by`, `hidden_at`, `updated_by`, and `updated_at` without
  changing `skill.status`.
- Unhide clears `hidden`, `hidden_by`, and `hidden_at`, updates `updated_by`/`updated_at`, and
  preserves `skill.status`.
- Each mutation updates the skill row and writes the audit row in one DB transaction.
- Hide writes `HIDE_SKILL` audit with optional `{"reason":...}` detail.
- Unhide writes `UNHIDE_SKILL` audit with null detail.
- Vite method-aware proxy routes only hide/unhide admin skill POST routes to Python. Yank remains
  on the Java fallback.

## Java Parity Checklist Outcome

| Area | Outcome |
| --- | --- |
| API contract | Covered: hide accepts optional reason body; unhide accepts no required body; both return `AdminSkillMutationResponse` data in the update-success envelope. |
| Authorization/session | Covered for local bridge: missing user is 401, `SKILL_ADMIN` is 403, and `SUPER_ADMIN` can mutate. |
| Database transaction atomicity | Covered: skill hidden overlay and audit insert occur in one SQLAlchemy transaction. |
| Audit actor/timestamp fields | Covered: actor, target type/id, optional request metadata, detail JSON, and timestamp match the Java action shape. |
| Storage and side effects | Not applicable: no object storage mutation. |
| Vite proxy boundary | Covered: hide/unhide are Python-owned; yank remains Java-owned/fallback. |
| Live verification evidence | Covered: Windows live gate compared Java/Python/Vite response parity, DB state, audit rows, role rejection, unauth rejection, and yank fallback boundary. |

## Verification

Red checks:

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_admin_skill_governance.py -q`
  initially failed because `app.admin` did not exist.
- `cd web; npx.cmd vitest run vite.config.test.ts` initially failed because hide/unhide proxy
  ownership was still undefined.

Narrow checks after implementation:

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_admin_skill_governance.py tests/test_hybrid_makefile.py -q`
  - Result: 11 passed, 1 warning.
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - Result: 23 passed.

Windows live gate:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-admin-skill-hide-unhide-smoke
```

Result:

- Python/live-gate pytest suite: 11 passed, 1 warning.
- Vite proxy test: 23 passed.
- Contract checks:
  - `hideResponsesMatch: true`
  - `unhideResponsesMatch: true`
  - `hideDbState: true`
  - `unhideDbState: true`
  - `hideAudit: true`
  - `unhideAudit: true`
  - `skillAdminRejected: true`
  - `unauthenticatedRejected: true`
  - `yankStillJavaOwned: true`
- Stable status: Java/Python/Vite hide returned `HIDE` with `ACTIVE`; Java/Python/Vite unhide
  returned `UNHIDE` with `ACTIVE`.
- Playwright smoke: 6 passed.

The live gate emitted process-cleanup warnings for elevated local services after completion. The
contract checks had already completed successfully.

## Risks And Follow-Up

- Admin version yank is still Java-owned and should be migrated as a separate milestone because it
  mutates version lifecycle state and latest-version recalculation rather than only toggling the
  skill hidden overlay.
- This milestone does not move broader admin/report/label/search/user-management routes.

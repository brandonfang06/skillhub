# Admin Version Yank API Migration Result

## Summary

Moved admin version yank ownership to Python:

- `POST /api/v1/admin/skills/versions/{versionId}/yank`

The previously migrated admin skill hide/unhide routes remain Python-owned.

## Implementation Notes

- Extended the Python admin-governance module with version yank workflow.
- Added a FastAPI route that resolves the local mock user and requires `SKILL_ADMIN` or
  `SUPER_ADMIN`.
- Yank only accepts `PUBLISHED` versions.
- The target version is updated to `YANKED`, `yanked_at`, `yanked_by`, `yank_reason`, and
  `download_ready=false`.
- If the yanked version was the skill latest version, Python recalculates `skill.latest_version_id`
  from remaining `PUBLISHED` versions using Java-compatible ordering by `published_at`, then
  `created_at`, then `id`.
- The route writes `YANK_SKILL_VERSION` audit on target type `SKILL_VERSION` with optional reason
  detail.
- Vite method-aware proxy now routes only the admin version yank POST route to Python.

## Java Parity Checklist Outcome

| Area | Outcome |
| --- | --- |
| API contract | Covered: optional reason body and `AdminSkillMutationResponse` data in the update-success envelope. |
| Authorization/session | Covered for local bridge: missing user is 401, unrelated platform role is 403, and `SKILL_ADMIN` can yank. |
| Database transaction atomicity | Covered: version mutation, latest pointer recalculation, skill update, and audit insert happen in one SQLAlchemy transaction. |
| Version state parity | Covered: only `PUBLISHED` can be yanked; target status becomes `YANKED`, yanked fields are set, and download readiness is disabled. |
| Latest pointer parity | Covered: latest pointer moves to the newest remaining published version when the yanked version was current latest. |
| Audit actor/timestamp fields | Covered: action, target type/id, actor, optional request metadata, detail JSON, and timestamp are persisted. |
| Event parity | Deferred: Java publishes `SkillVersionYankedEvent`; Python has no event bus equivalent yet. This remains a broader migration follow-up. |
| Vite proxy boundary | Covered: admin version yank is Python-owned. |
| Live verification evidence | Covered: Windows live gate compared Java/Python/Vite response parity, DB state, latest pointer, audit rows, role rejection, unauth rejection, missing-version rejection, and Playwright smoke. |

## Verification

Red checks:

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_admin_skill_governance.py -q`
  initially failed because `yank_skill_version_as_admin` did not exist.
- `cd web; npx.cmd vitest run vite.config.test.ts`
  initially failed because admin version yank proxy ownership was still undefined.

Narrow checks after implementation:

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_admin_skill_governance.py tests/test_hybrid_makefile.py -q`
  - Result: 16 passed, 1 warning.
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - Result: 23 passed.
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "[void][scriptblock]::Create((Get-Content -Raw -LiteralPath 'scripts\dev-hybrid.ps1')); 'syntax-ok'"`
  - Result: `syntax-ok`.

Windows live gate:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-admin-version-yank-smoke
```

Result:

- Python/live-gate pytest suite: 16 passed, 1 warning.
- Vite proxy test: 23 passed.
- Contract checks:
  - `responsesMatch: true`
  - `javaDbState: true`
  - `pythonDbState: true`
  - `proxyDbState: true`
  - `javaAudit: true`
  - `pythonAudit: true`
  - `proxyAudit: true`
  - `userAdminRejected: true`
  - `unauthenticatedRejected: true`
  - `missingVersionRejected: true`
- Stable status: Java/Python/Vite all returned `YANK` with `YANKED`.
- Playwright smoke: 6 passed.

The first live-gate run failed at `responsesMatch` because the verifier compared concrete
`versionId` values across three independent fixtures. The DB, audit, and authorization checks were
already true. The verifier was corrected to compare `versionIdPresent` for yank response shape, then
the live gate passed.

The live gate emitted process-cleanup warnings for elevated local services after completion. The
contract checks and Playwright smoke had already completed successfully.

## Risks And Follow-Up

- Java publishes `SkillVersionYankedEvent`; Python currently records DB/audit parity but does not
  emit an equivalent domain event. Event bus parity should be addressed when the broader Python
  notification/event bridge is designed.
- This milestone does not move other admin management APIs.

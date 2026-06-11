# CLI Skill Delete Live Smoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated Java/Python/proxy live verification target for `DELETE /api/cli/v1/skills/{namespace}/{slug}`.

**Architecture:** Reuse the existing hybrid stack, hard-delete fixture, DB evidence helper, and API-token fixture patterns from `scripts/dev-hybrid.ps1`. The new smoke target should compare Java, direct Python, and Vite proxy behavior for CLI delete and write a JSON evidence file under `.dev/`.

**Tech Stack:** PowerShell hybrid verification script, pytest guard tests, Vite proxy tests, Java and FastAPI reference runtimes.

---

## Scope

Add verification for:

- `scripts/dev-hybrid.ps1 -Action verify-cli-skill-delete-smoke`

Do not change:

- Java source under `server/`
- Python route behavior already migrated in `2026-06-11-cli-skill-delete-api.md`
- OAuth/session behavior

## Java Parity Checklist

| Area | Planned outcome | Evidence |
| --- | --- | --- |
| API contract | covered | Compare stable `code`, `msg`, `data.ok`, `data.scope`, `data.action`, and namespace/slug presence across Java/Python/proxy. |
| Authorization/session behavior | covered | Verify `X-Mock-User-Id` delete and bearer `skill:delete` success; verify bearer without scope returns `403`; verify unknown bearer returns `401`. |
| Database transaction atomicity | covered | Reuse existing hard-delete DB evidence helper to check skill/version/file/search/security cleanup and audit insertion. |
| Audit actor/timestamp fields | covered | Evidence checks `DELETE_SKILL_HARD` audit exists for deleted fixture. |
| Storage and side effects | covered | Reuse storage file fixture and storage-missing evidence checks. |
| Live verification evidence | covered | New action writes `.dev/cli-skill-delete-contract-result.json`. |

## Files

- Modify: `scripts/dev-hybrid.ps1`
  - Add ValidateSet action `verify-cli-skill-delete-smoke`.
  - Add Python/proxy test wrapper for `test_skill_hard_delete.py`, `test_auth_bearer.py`, `test_hybrid_makefile.py`, and `vite.config.test.ts`.
  - Add Java/Python/proxy CLI delete contract comparison.
  - Add switch branch for the new action.
- Modify: `server-python/tests/test_hybrid_makefile.py`
  - Assert the new action, function, and result file are documented in the script.
- Create: `docs/backend-python-migration/results/2026-06-11-cli-skill-delete-live-smoke.md`
  - Record tests and live gate result.
- Update: `docs/backend-python-migration/results/2026-06-11-cli-skill-delete-api.md`
  - Replace the live-gate deferred risk with the new smoke result once it passes.

## Tasks

### Task 1: Failing Script Guard Test

- [x] Add assertions to `server-python/tests/test_hybrid_makefile.py` for:
  - `verify-cli-skill-delete-smoke`
  - `Invoke-HybridCliSkillDeleteSmokeVerification`
  - `Invoke-CliSkillDeleteContractComparison`
  - `cli-skill-delete-contract-result.json`
- [x] Run:

```powershell
cd server-python
uv run pytest tests/test_hybrid_makefile.py -q
```

Result: failed as expected because the new action/functions/result file did not exist.

### Task 2: Implement Script Wiring

- [x] Add `verify-cli-skill-delete-smoke` to the script ValidateSet.
- [x] Add `Invoke-CliSkillDeleteTests` to run:

```powershell
uv run pytest tests/test_skill_hard_delete.py tests/test_auth_bearer.py tests/test_hybrid_makefile.py -q
npx.cmd vitest run vite.config.test.ts
```

- [x] Add a switch branch for `verify-cli-skill-delete-smoke`.
- [x] Run `uv run pytest tests/test_hybrid_makefile.py -q`.

Result: passed.

### Task 3: Implement Contract Comparison

- [x] Add `ConvertTo-StableCliSkillDeleteJson` for CLI response comparison.
- [x] Add `Invoke-CliSkillDeleteContractComparison`.
- [x] Use `Ensure-SkillHardDeleteFixture` for java/python/proxy fixture slugs.
- [x] DELETE `/api/cli/v1/skills/codex-hard-delete-team/{slug}` with `X-Mock-User-Id: local-user`.
- [x] Verify DB/storage/audit evidence with `Get-SkillHardDeleteDbEvidence`.
- [x] Add a bearer scope sub-check using `Ensure-HardDeleteTokenScopeFixture` and DELETE through the CLI path.
- [x] Write `.dev/cli-skill-delete-contract-result.json`.
- [x] Throw if stable contracts differ or evidence fails.

### Task 4: Run Verification

- [x] Run:

```powershell
cd server-python
uv run pytest tests/test_skill_hard_delete.py tests/test_auth_bearer.py tests/test_hybrid_makefile.py -q
```

- [x] Run:

```powershell
cd web
npm.cmd run test -- vite.config.test.ts
```

- [x] Run if the local hybrid dependencies are available:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 -Action verify-cli-skill-delete-smoke
```

### Task 5: Result And Review

- [x] Write `docs/backend-python-migration/results/2026-06-11-cli-skill-delete-live-smoke.md`.
- [x] Update `docs/backend-python-migration/results/2026-06-11-cli-skill-delete-api.md` to reference the passed live gate.
- [x] Run `git diff --name-only -- server` and confirm no Java files changed.
- [x] Run `git diff --check`.
- [x] Review the script diff for destructive-fixture isolation and Java/Python/proxy parity.

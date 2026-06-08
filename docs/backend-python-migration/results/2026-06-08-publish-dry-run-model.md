# Publish Transaction Dry-Run Model Result

Date: 2026-06-08

## Summary

Completed the Python publish transaction dry-run model without migrating any publish route.

Python now mirrors Java `SkillPublishService.validateOnly(...)` preflight decisions for:

- namespace existence;
- namespace `FROZEN` / `ARCHIVED` errors;
- namespace membership with `SUPER_ADMIN` bypass;
- package validation errors and warnings;
- `SKILL.md` metadata parsing;
- slug generation from metadata `name`;
- auto timestamp version when metadata `version` is missing;
- basic pre-publish credential warnings;
- own archived skill conflicts;
- own already-published version conflicts;
- other-owner published name conflicts.

Warnings make dry-run `valid=false`, matching Java CLI dry-run behavior when
`confirmWarnings=false`.

## Route Ownership

No route ownership moved to Python in this milestone.

| Method | Path | Before | After |
| --- | --- | --- | --- |
| POST | `/api/v1/skills` | java | java |
| POST | `/api/v1/publish` | java | java |
| POST | `/api/v1/skills/{namespace}/publish` | java | java |
| POST | `/api/web/skills/{namespace}/publish` | java | java |
| POST | `/api/cli/v1/skills/{namespace}/publish/validate` | java | java |
| POST | `/api/cli/v1/skills/{namespace}/publish` | java | java |

## Files Changed

- `server-python/app/publish/dry_run.py`
- `server-python/tests/test_publish_dry_run.py`
- `server-python/tests/test_hybrid_makefile.py`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/plans/2026-06-08-publish-dry-run-model.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/windows-live-verification.md`

## Verification

Focused checks completed during implementation:

- `cd server-python; uv run pytest tests/test_publish_dry_run.py -q`
  - `18 passed`
- `cd server-python; uv run pytest tests/test_publish_dry_run.py tests/test_hybrid_makefile.py -q`
  - `24 passed`

Final checks completed:

- `cd server-python; uv run pytest`
  - `197 passed, 1 warning`
- `cd web; .\node_modules\.bin\vitest.CMD vite.config.test.ts --run`
  - `18 passed`
- `cd web; .\node_modules\.bin\tsc.CMD --noEmit`
  - passed
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-dry-run-smoke`
  - dry-run tests: `18 passed`
  - publish ownership: all Java/Vite status comparisons matched
  - Playwright smoke: `6 passed`
  - `.dev/publish-dry-run-contract-result.json` written
- Port cleanup check after live gate:
  - no `LISTENING` entries on `3000`, `8080`, or `8081`; only `TIME_WAIT` entries remained.

- `git diff --check`
  - passed; Windows line-ending warnings only.
- `git diff --name-only -- server`
  - printed nothing.

## Risks

- The dry-run model is not yet exposed via HTTP and is not wired into publish POST handling.
- It performs read-only DB checks but no transaction, storage write, scanner trigger, review task,
  audit log, or event behavior.
- Java's full publish flow has replacement cleanup and pending-review withdrawal behavior that this
  dry-run model intentionally does not execute.

## Follow-Up

Next milestone should plan the local storage write transaction:

- create skill/version/file rows;
- write local storage files;
- build bundle zip;
- verify no scanner trigger yet;
- keep publish POST route ownership decision explicit before enabling any route.

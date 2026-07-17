# Orphan Skill Cleanup Implementation Plan

## Goal

Make abnormal skill records diagnosable and removable by `SUPER_ADMIN`, prevent resource-less
published projections from appearing in search, and explain namespace deletion blockers.

## Milestones

- [x] Published search resource boundary
  - Add failing SQL assertions for search, rebuild, and upsert.
  - Require a file row for the current published version and rerun focused tests.
- [x] `SUPER_ADMIN` skill read override
  - Add access and route tests across archived, namespace-only, and unpublished states.
  - Preserve ordinary lifecycle permissions and expose a separate override flag.
- [x] Resource diagnostics
  - Test authorization, missing metadata/objects, probe cap, and storage errors.
  - Add the admin route, typed client/hook, cleanup UI, and translations.
- [x] Namespace blockers and cleanup
  - Centralize dependency counts and test owner/platform-admin deletion rules.
  - Expose blocker details and render a disabled, explained delete command.
- [x] Reviewer pass and full verification
  - Review role boundaries, transaction races, object-probe behavior, and upstream impact.
  - Run full backend/frontend tests, typecheck, lint, build, and diff checks.

## Results

- Search, rebuild, and upsert now require a database file row for the latest published version.
- Session/mock `SUPER_ADMIN` can inspect active, archived, hidden, private, and unpublished skill
  projections without receiving ordinary lifecycle permission.
- Resource diagnostics distinguish missing database rows, blank storage keys, missing objects,
  bounded partial checks, and unverified storage failures.
- Namespace responses expose exact dependency blockers; list queries batch blocker counts, while
  delete mutations recheck blockers in their transaction.
- Reviewer fixes added all-version missing-file detection, accurate probe counters, archived-skill
  platform reads, removal of the namespace dependency N+1 query, manual-only object-store
  diagnostics, and cleanup-only namespace actions for platform admins who are not members.

Verification on 2026-07-17:

- `uv run --frozen pytest tests -q`: 932 passed, 1 third-party deprecation warning.
- `vitest run`: 194 files passed, 678 tests passed.
- `pnpm run typecheck`: passed.
- `pnpm run lint`: passed with zero warnings.
- `pnpm run build`: passed; existing runtime-config and chunk-size warnings remain.
- Locale JSON UTF-8 parse: passed.
- `git diff --check`: passed.

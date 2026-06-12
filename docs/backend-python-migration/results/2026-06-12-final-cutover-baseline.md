# Final Cutover Baseline Result

Date: 2026-06-12

## Summary

Milestone 114 created a machine-checked baseline for the final Python cutover.

- Route registry has no Java-owned rows.
- Vite config has no Java `8080` proxy target.
- Remaining deferred categories are explicit in the migration sequence and final cutover plan.
- Milestones 115-120 are now the ordered remaining work.

## Deferred Categories Locked By Tests

- OAuth provider redirect/callback/session establishment.
- Global bearer route-policy enforcement.
- Active notification SSE fanout.
- Post-publish lifecycle/governance semantic audit.
- Python schema migration ownership.

## TDD Evidence

Red run:

- `uv run pytest tests/test_final_cutover_baseline.py -q`
- Result: expected failure because the result document did not exist and the migration sequence did not yet list the final deferred category markers.

Green run:

- Result: `uv run pytest tests/test_final_cutover_baseline.py tests/test_route_registry.py -q` passed.

## Verification

Result: `uv run pytest tests/test_final_cutover_baseline.py tests/test_route_registry.py -q` passed.

Additional checks:

- `npm.cmd run test -- vite.config.test.ts`
- `rg -n "target:\s*'http://localhost:8080'|toBe\('http://localhost:8080'\)" web\vite.config.ts web\vite.config.test.ts`
- `git diff --check`
- `git diff --name-only -- server`

## Files Changed

- `server-python/tests/test_final_cutover_baseline.py`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-12-final-python-cutover.md`
- `docs/backend-python-migration/results/2026-06-12-final-cutover-baseline.md`

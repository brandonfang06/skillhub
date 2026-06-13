# Post-Cutover Hardening Regression Result

Date: 2026-06-13

Milestone: Post Python Cutover Hardening Milestone 8

## Scope

This milestone re-ran the full local regression suite after the post-cutover
maintainability hardening milestones and recorded the launch-readiness baseline.
No production behavior or API contract was intentionally changed in this
milestone.

## Baseline

- Branch: `codex/post-cutover-hardening-m1`
- Starting state: clean working tree, aligned with
  `origin/codex/post-cutover-hardening-m1`.
- Last completed milestone before this run:
  `d196e2a0 docs(backend): add upstream sync workflow`.

## Verification

| Command | Result |
| --- | --- |
| `cd server-python; uv run pytest tests -q` | Passed: `727 passed, 1 warning in 74.01s`. Warning was the existing Starlette/httpx `TestClient` deprecation from FastAPI test support. |
| `cd web; corepack pnpm run typecheck` | Passed. |
| `cd web; corepack pnpm run lint` | Passed. |
| `cd web; corepack pnpm run test` | Passed: `180 passed` test files, `630 passed` tests in `14.07s`. |
| `powershell -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 down` | Passed; stopped the existing local hybrid stack. |
| `powershell -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 e2e` | First attempt failed during Java reference backend startup because the existing `skillhub_postgres_data` volume contained a non-empty `public` schema without Flyway history. This was local state, not a code regression. |
| `powershell -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 down; docker compose -p skillhub down -v --remove-orphans` | Passed; removed the stale `skillhub` compose volumes to restore a clean local database. |
| `powershell -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 e2e` | Passed after clean volume reset: local stack became ready and Playwright reported `146 passed`, `2 skipped` in `5.6m`. |
| `git fetch upstream --prune` | Passed. |
| `powershell -ExecutionPolicy Bypass -File scripts\check-upstream-backend-drift.ps1 -BaseRef upstream/main -HeadRef HEAD` | Passed; no immediate Java backend contract or schema drift category item was reported. |
| `git diff --check` | Passed; no whitespace errors. |

## Upstream Drift Snapshot

Command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check-upstream-backend-drift.ps1 -BaseRef upstream/main -HeadRef HEAD
```

Summary:

- `java-backend-contract-or-behavior`: 0
- `database-migration-or-schema`: 0
- `frontend-or-api-client-expectation`: 12
- `python-backend-runtime`: 247
- `docs-config-or-ci`: 287
- `scanner-cli-or-other-runtime`: 4

Interpretation: there is no currently detected upstream Java backend contract or
Flyway schema category change that must be ported before this hardening batch is
closed. The remaining report is dominated by local Python cutover, web proxy,
documentation, and maintenance work.

## E2E Environment Note

The first E2E attempt proved that `scripts\dev-hybrid.ps1 down` stops containers
but intentionally preserves Docker volumes. When the local `skillhub_postgres_data`
volume contains a Python-created schema without Java Flyway history, the Java
reference backend cannot start and reports:

```text
Found non-empty schema(s) "public" but no schema history table.
```

For a true clean local regression baseline, reset the `skillhub` compose volumes
before rerunning full E2E:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 down
docker compose -p skillhub down -v --remove-orphans
powershell -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 e2e
```

This is local verification state management, not an application behavior change.

## Launch Readiness Assessment

- Python backend unit coverage is green across the current test suite.
- Web typecheck, lint, and unit tests are green.
- Full local hybrid Playwright E2E is green against a clean database and Python
  API proxy path.
- Upstream drift check does not show a Java backend contract or schema item that
  must be ported immediately.
- No generated files or test report artifacts were left in the working tree.

## Residual Risk

- The upstream drift report is path-classified. Future upstream pulls still need
  human review before deciding whether a change is `port-to-python-now`,
  `accept-non-backend`, `defer-with-reason`, or `reject`.
- Full E2E currently depends on a clean local compose database when Java Flyway
  is used as reference startup evidence. Reusing a stale local volume can fail
  before tests begin.
- The existing FastAPI test support emits a Starlette/httpx deprecation warning;
  it does not fail current tests but should be tracked separately if dependency
  upgrades are planned.

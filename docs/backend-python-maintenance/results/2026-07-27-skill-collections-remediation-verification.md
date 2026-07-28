# Skill Collections Remediation Verification

Date: 2026-07-28

Plan:
`docs/backend-python-maintenance/plans/2026-07-27-skill-collections-code-review-remediation.md`

## Verdict

All code-review remediation blockers in Tasks 1-9 are resolved in the local
worktree. The current Python-only backend, Web application, CLI, scanner
contracts, release manifests, and deployment renders pass their local gates.
The branch is a local merge candidate, subject to the normal review and CI
process.

Production rollout remains **blocked**. No real internal GitLab request, Nexus
publication/read-back, Kubernetes deployment, or multi-pod production
startup was authorized or executed. Collection and GitLab import flags remain
default-off.

The pre-existing cross-process CLI inventory lost-update limitation remains
explicitly pinned by a passing regression test. It is an accepted non-goal of
this remediation, not silently treated as fixed.

No commit, stage, push, package publication, deployment, or PR was performed.

## Final-review findings repaired

Two additional issues were found by the final real-case review:

1. `SKILLHUB_GITLAB_ARCHIVE_MAX_BYTES` defaulted to 100 MiB in Python while
   Compose, K8s, and operator documentation declared 50 MiB. A RED config test
   reproduced the mismatch. Python now uses the shared 50 MiB default and
   rejects zero or negative overrides by falling back to that safe value.
2. The existing subscription E2E accepted the optimistic `Subscribed` label
   and navigated before the PUT completed. The failed run contained no PUT in
   the backend log. The E2E now waits for successful PUT/DELETE responses and
   uses exact button names. Focused real-API rerun: `2 passed`.

Neither repair changes the production subscription workflow or an existing
Skill lifecycle contract.

## Focused remediation gates

Tasks 1-9 retain their RED/GREEN and real-case evidence in the adjacent task
result documents. Their final focused results were:

| Task | Final focused evidence |
| --- | --- |
| 1 migration safety | 17 backend tests; fresh and existing PostgreSQL concurrent upgrades |
| 2 lifecycle references | 102 backend tests; real hard/version deletes, degraded history, and lock races |
| 3 Web principal policy | 46 auth tests and 113 adjacent core tests |
| 4 immutable member IDs | 176 backend tests and 38 focused Web tests |
| 5 atomic ingest claim | 18 repository/service/publish tests, 35 schema/API tests, and 115 related transaction tests |
| 6 runtime config | 14 deployment tests and two actual Web container renders |
| 7 CLI coordinate | 11 Web unit tests, 1 E2E, and 27 CLI parser/help tests |
| 8 Nexus release contract | 6 workflow tests and a no-publish npm pack rehearsal |
| 9 resource bounds | 108 backend tests, 17 CLI tests, and a 500-file/50-MiB availability probe |

After every task was present, the current-state backend remediation union was
rerun:

```powershell
cd server-python
.\.venv\Scripts\python.exe -m pytest `
  tests\test_schema_migration_baseline.py `
  tests\test_collection_schema.py `
  tests\test_repository_import_schema.py `
  tests\test_collection_read.py `
  tests\test_collection_resolve.py `
  tests\test_skill_hard_delete.py `
  tests\test_collection_access.py `
  tests\test_repository_import_api.py `
  tests\test_collection_mutations.py `
  tests\test_collection_transactions.py `
  tests\test_skill_versions.py `
  tests\test_repository_import_repository.py `
  tests\test_repository_import_service.py `
  tests\test_repository_import_publish_integration.py `
  tests\test_deployment_cutover.py `
  tests\test_config.py `
  tests\test_repository_import_archive.py -q
```

Result: `220 passed, 2 warnings in 30.64s`.

The warnings are the existing Starlette/httpx deprecation and the intentional
duplicate-ZIP-entry security fixture.

The current-state full Web and CLI suites below subsume the focused Web,
collection command, install transaction, and release workflow tests.

## Full repository gates

| Area | Command | Result |
| --- | --- | --- |
| Backend dependencies | `uv sync --frozen` with workspace-local cache | 43 packages checked |
| Backend | `uv run pytest tests -q` | 1107 passed, 2 warnings in 215.40s |
| SQL placement | `uv run python scripts/sql_inventory.py` | exit 0; no new ownership violation |
| Web types | `corepack pnpm run typecheck` | exit 0 |
| Web lint | `corepack pnpm run lint` | exit 0, zero warnings |
| Web unit/component | `.\node_modules\.bin\vitest.cmd run --maxWorkers=4` | 207 files, 747 tests passed |
| Web build | `corepack pnpm run build` | exit 0; 2404 modules transformed |
| Web real API E2E | `.\node_modules\.bin\playwright.cmd test --project=chromium --workers=1 --reporter=line` | 154 passed, 2 skipped in 7.6 minutes |
| CLI lint/types | `bun run lint`; `bun run typecheck` | both exit 0 |
| CLI | `bun test` | 413 passed, 6 skipped, 0 failed; 1138 assertions |
| CLI artifact | `bun run build`; `node dist/index.js version` | 179 modules; `SkillHub CLI 0.1.9` |
| Backend image | `docker build -t skillhub-server-python:verify -f server-python/Dockerfile .` | exit 0; image manifest `2ef9445a61756a1995e9a8c89eb53563b47cca12b767f8031fccb643a0e65f1f` |
| K8s render | `kubectl kustomize deploy\k8s\base` | exit 0 |
| Compose render | `docker compose --env-file .env.release.example -f compose.release.yml config --quiet` | exit 0 |
| Diff hygiene | `git diff --check` | exit 0 |

The two Playwright skips are an intentional browser-new-tab limitation and a
data-dependent admin-list precondition. The six CLI skips are Windows symlink
cases. The Vite runtime-config URL and large-chunk notices are existing build
warnings, not build failures. Compose printed a sandbox-only warning that the
user Docker config was unreadable; rendering still exited 0.

## Real-case core matrix

| Area | Evidence | Result |
| --- | --- | --- |
| Startup | Task 1 ran two fresh-database replicas and two existing-database replicas against real PostgreSQL. This final run again launched two existing-database upgrades concurrently. | Both final processes exited 0 with `skillhub_flyway_v43_baseline`; Task 1 recorded one row per migration and transactional rollback. |
| Flags | Backend was started with collection/import defaults off. `GET /api/v1/health`, collection list, and import preview were requested. | Health `200`; both new routes `404`. Existing real-API Web suite remained green. |
| Auth | Session owner, MEMBER, invalid bearer, and read-only API-token cases are covered by the Task 3 route-policy gate. | Owner success; MEMBER `403`; invalid token `401`; API-token mutation `403`, all before side effects. |
| Skill lifecycle | Full backend lifecycle suite plus real Web publish/review flows; Task 2 used real PostgreSQL for hard delete, version delete, and replacement cleanup. | Existing publish/archive/restore/delete paths remain green; collection/import references null safely with no FK `500`. Scanner failure is automated, not an external scanner-failure rehearsal. |
| Collection | Exact Skill/version IDs, duplicate owner slug handling, draft replacement, publish, resolve, copied CLI command, preflight, and rollback are covered by backend, Web, and CLI suites. | Selected immutable IDs are preserved and one collection install writes one inventory snapshot. |
| Degraded snapshot | Task 2 hard-deleted a published member using real PostgreSQL. | Historical namespace/slug/version remained readable under the original visibility policy; resolve returned controlled `409 error.collection.resolve.degraded`. |
| GitLab import | Task 5 used real PostgreSQL and two simultaneous local ASGI ingest requests; preview/discovery, scan failure, publish, audit, and collection seeding use mocked GitLab/archive inputs. | One claim/publisher won; competitor `409`; terminal ownership and audit remained atomic. No real GitLab TLS/token/group check was made. |
| Web runtime | Task 6 built and ran the Web image once with defaults and once with enabled/Nexus values. | No literal placeholders; default flags were false; supplied values were exact. |
| CLI | The copied `@namespace/collection` command reached the registry boundary; full ordinary single-Skill install regression also passed. | Collection coordinate parsed without usage exit 5; existing single-Skill install behavior remained green. |
| Nexus | Workflow contract tests and `npm.cmd pack --dry-run --json` passed. Hosted/group digest checks are wired to fail closed on a same-version byte mismatch. | Local contract passed. Real Nexus connectivity, credentials, caching, and read-back remain external gates. |
| Rollback | All four product flags remain default-off; local backend health and full prior core smoke passed with the additive tables present. | Core remains available while collection/import routes are hidden; additive data is not destructively removed. |

## Static diff review

The complete diff and required searches were reviewed after the final fixes:

- collection/import references to core `skill` and `skill_version` use
  `ON DELETE SET NULL`; existing analytics references retain their unrelated
  `ON DELETE CASCADE` policy;
- both new mutating API modules resolve the current principal and reject
  read-only API tokens before side effects;
- collection membership is resolved by exact Skill and Skill-version IDs,
  with slug/version retained only as immutable snapshots;
- repository ingest claim, candidate updates, and terminal transition are
  conditional on `INGESTING` plus the same `ingest_operation_id`;
- every Web runtime collection/GitLab/CLI variable appears in the template,
  default/export logic, explicit `envsubst` allowlist, Compose, and K8s wiring;
- the CLI publish job has no npmjs or legacy registry fallback, uses a
  runner-temporary npm config, cleans it with `if: always()`, and compares
  hosted/group tarballs with the build SHA-256;
- no Java, Maven, Spring Boot, or hybrid runtime was added.

## External gates and rollout conditions

Before enabling production flags:

1. Run the release workflow on the approved
   `[self-hosted, linux, skillhub-nexus]` runner with real hosted/group URLs
   and verify exact-byte read-back.
2. Validate real internal GitLab CA trust, token scope, allowed-group policy,
   archive limits, and failure/audit behavior without exposing the token.
3. Render the organization overlay and deploy to a non-production K8s
   environment; verify two real backend pods, migrations, scanner/storage,
   metrics, logs, and rollback with flags off.
4. Decide whether the known cross-process CLI inventory lost-update risk is
   acceptable for the initial audience or must be fixed before broad rollout.
5. Enable backend and Web flags in stages; GitLab import only after
   collections is healthy.

Local merge blockers are resolved. Production rollout remains blocked until
the first three external gates are completed and the CLI concurrency risk is
explicitly accepted or repaired.

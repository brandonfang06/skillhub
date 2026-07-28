# Skill Collections Milestone 0 Safety Gate Result

Date: 2026-07-26

Source commit: `b54a135a674a75202cd30bbc6a5c53510840580c`

Milestone status: complete

## Scope

Milestone 0 is configuration-only. It establishes default-off backend and web
feature flags, optional immutable CLI distribution metadata, Kubernetes wiring,
and durable architecture assertions before collection implementation begins.

This milestone excludes collection/import tables, collection/import routes,
GitLab clients or credentials, CLI collection commands, collection UI or
navigation, background work, and changes to existing publish, search, detail,
download, review, namespace, or ClawHub behavior.

## Pre-existing Worktree State

`git status --short` produced no entries before implementation:

```text
(clean; no output)
```

The original `dev` worktree has separate pre-existing untracked files. Milestone
0 is isolated in
`C:\Users\USER\projects\skillhub\.worktrees\skill-collections-m0` and does not
modify those entries.

## Pre-feature SQL Inventory

Command: `cd server-python; uv run python scripts/sql_inventory.py`

```text
category,text_calls,path
repository-query,54,app/skills/read_repository.py
service-domain,24,app/auth/account_merge.py
service-domain,22,app/lifecycle/skill.py
service-domain,20,app/lifecycle/hard_delete.py
repository-query,19,app/admin/review_report_repository.py
service-domain,18,app/promotion/workflow.py
repository-query,16,app/governance/workbench_repository.py
service-domain,16,app/review/approval.py
api-route,14,app/api/labels.py
service-domain,13,app/admin/labels.py
service-domain,13,app/auth/local.py
service-domain,13,app/review/query.py
service-domain,12,app/namespace/members.py
migration-bootstrap,11,app/bootstrap.py
repository-query,11,app/admin/user_repository.py
service-domain,9,app/auth/oauth.py
service-domain,9,app/auth/tokens.py
service-domain,9,app/namespace/mutations.py
service-domain,8,app/publish/replacement.py
service-domain,8,app/user_profile.py
service-domain,7,app/admin/skill.py
service-domain,7,app/builtin_skills.py
service-domain,7,app/download_analytics/repository.py
service-domain,7,app/notifications/service.py
repository-query,6,app/reports/report_repository.py
service-domain,6,app/admin/search.py
service-domain,6,app/auth/context.py
service-domain,6,app/auth/password_reset.py
service-domain,6,app/publish/transaction.py
service-domain,6,app/social/subscription.py
service-domain,5,app/publish/dry_run.py
service-domain,5,app/security_audit.py
service-domain,5,app/social/clawhub_star.py
service-domain,5,app/social/rating.py
service-domain,5,app/social/star.py
service-domain,4,app/namespace/read.py
service-domain,4,app/promotion/query.py
service-domain,4,app/publish/scanner_result.py
service-domain,3,app/admin/resource_diagnostics.py
service-domain,3,app/publish/auto_withdraw.py
service-domain,3,app/publish/side_effects.py
service-domain,3,app/review/notifications.py
repository-query,2,app/admin/audit_repository.py
service-domain,2,app/notifications/preferences.py
service-domain,2,app/publish/scan_worker.py
service-domain,2,app/social/lists.py
api-route,1,app/api/device_auth.py
service-domain,1,app/namespace/dependencies.py
service-domain,1,app/social/owned.py

summary
api-route,15
migration-bootstrap,11
repository-query,108
service-domain,309
```

The allowlisted route SQL remains limited to `app/api/labels.py` and
`app/api/device_auth.py`.

## Configuration Defaults

| Setting | Verified default | Evidence |
| --- | --- | --- |
| Backend collections | `false` | `test_collection_features_default_to_disabled` and `test_collection_features_default_off_without_environment` |
| Backend GitLab import | `false` | Both settings tests also verify that import cannot enable while collections are disabled |
| Web collections | `false` | Runtime-config unit test and rendered K8s ConfigMap |
| Web GitLab import | `false` | Runtime-config dependency test and rendered K8s ConfigMap |
| CLI/Nexus registry, package, version | empty | Runtime-config incomplete-value test and rendered K8s ConfigMap |

Backend flags are authoritative for behavior. Web flags control presentation
only. The frontend exposes CLI distribution metadata only when registry,
package, and version are all non-empty; no Nexus token or other credential is
placed in runtime config.

## Verification

| Gate | Literal command | Result | Exit code |
| --- | --- | --- | --- |
| SQL inventory before and after | `cd server-python; uv run python scripts/sql_inventory.py` | Unchanged summary: api-route 15, migration-bootstrap 11, repository-query 108, service-domain 309 | 0 |
| Targeted core regression baseline | `cd server-python; uv run pytest tests/test_publish_review_download_session_flow.py tests/test_skill_detail.py tests/test_skill_download.py tests/test_clawhub_resolve.py tests/test_namespace_profile_lifecycle.py tests/test_route_registry.py tests/test_post_cutover_architecture.py tests/test_schema_migration_baseline.py -q` | 67 passed, 1 pre-existing Starlette deprecation warning | 0 |
| Backend settings | `cd server-python; uv run pytest tests/test_config.py -q` | 30 passed | 0 |
| Web runtime config | `cd web; .\node_modules\.bin\vitest.cmd run src/api/client.test.ts` | 28 passed | 0 |
| Deployment assertions | `cd server-python; uv run pytest tests/test_deployment_cutover.py -q` | 11 passed | 0 |
| Architecture isolation | `cd server-python; uv run pytest tests/test_collection_feature_isolation.py tests/test_post_cutover_architecture.py tests/test_python_runtime_cutover.py tests/test_schema_migration_baseline.py -q` | 27 passed | 0 |
| Complete backend | `cd server-python; uv run pytest tests -q` | 940 passed, 1 pre-existing Starlette deprecation warning | 0 |
| Frontend typecheck | `cd web; corepack pnpm run typecheck` | Passed | 0 |
| Frontend lint | `cd web; corepack pnpm run lint` | Passed with zero warnings | 0 |
| Complete frontend tests | `cd web; corepack pnpm run test` | 194 files and 691 tests passed | 0 |
| Frontend build | `cd web; corepack pnpm run build` | Production build completed; existing runtime-config and chunk-size warnings remain | 0 |
| CLI lint | `cd cli; bun run lint` | Passed | 0 |
| CLI typecheck | `cd cli; bun run typecheck` | Passed | 0 |
| Complete CLI tests | `cd cli; bun test` | 346 passed, 6 Windows symlink tests skipped, 0 failed | 0 |
| CLI build | `cd cli; bun run build` | Node-target bundle created | 0 |
| CLI artifact version | `cd cli; node dist/index.js version` | `SkillHub CLI 0.1.9` | 0 |
| Python backend image | `docker build -t skillhub-server-python:verify -f server-python/Dockerfile .` | Local image built successfully | 0 |
| K8s render | `kubectl kustomize deploy\k8s\base` | Rendered only scanner, Python backend, web, services, and ingress; collection/import defaults are false and CLI metadata is empty | 0 |
| Release Compose render | `docker compose --env-file .env.release.example -f compose.release.yml config --quiet` | Valid | 0 |
| Route boundary | `Get-ChildItem server-python\app\api | Where-Object Name -match 'collection|repository_import'` | No files | 0 |
| Schema boundary | `Get-ChildItem server-python\app\db\migration,server-python\app\db\local_migration | Where-Object Name -match 'collection|repository_import'` | No files | 0 |
| Whitespace and patch hygiene | `git diff --check` | Clean; only Git's existing LF-to-CRLF worktree notices were printed | 0 |

The pre-feature and post-change regression gates cover publish and scan/review
flow, skill detail, download, namespace lifecycle, ClawHub resolution, route
registry, and schema baseline behavior. No collection/import schema, route,
network client, CLI command, UI, navigation, or background worker was added.

## Environment Recovery Note

The system pnpm was `11.9.0`, while `web/package.json` pins `pnpm@10.33.0`.
Frontend install and gates therefore used `corepack pnpm` so the existing
lockfile and overrides remained unchanged.

The first sandboxed CLI dependency install was denied access to Bun's user
cache after creating empty package directories. That incomplete dependency tree
caused the first CLI gate attempt to report missing `eslint`, `tsc`, `fflate`,
and `semver`, followed by 114 failed tests and 11 import errors. Reinstalling
with the frozen lockfile, a fresh temporary cache, and the copyfile backend
restored the dependencies:

```powershell
bun install --frozen-lockfile --force --no-cache `
  --cache-dir C:\tmp\skillhub-m0-bun-cache-20260726 `
  --backend=copyfile
```

The complete CLI gate was then rerun from scratch and produced the successful
results recorded above. No source or lockfile change was made by this recovery.

## Authorization

No commit, push, pull request, package publication, or deployment has been
performed.

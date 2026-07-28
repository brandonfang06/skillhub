# Skill Collections Milestone 1 Backend Result

Date: 2026-07-27

Source commit: `b54a135a674a75202cd30bbc6a5c53510840580c`

Upstream comparison commit: `ac46ad53913e413e451710a3563590b62d183927`

Milestone status: complete; stopped before Milestone 2

Implementation plan:
`docs/superpowers/plans/2026-07-27-skill-collections-m1-backend.md`

## Outcome

Milestone 1 adds the default-off, Python-owned collection schema and FastAPI
contract needed by a future CLI `install-collection` command. A collection is a
first-class, namespace-scoped resource. Each published collection version is an
immutable ordered snapshot of exact published skill versions.

The implementation does not add a CLI command, collection UI, GitLab import,
background jobs, Java code, Maven, Spring Boot, or a hybrid runtime. The
collection and GitLab-import feature flags remain disabled by default.

## Upstream And Local Baseline

The implementation worktree remained on
`b54a135a674a75202cd30bbc6a5c53510840580c`. The fetched official
`upstream/main` reference was
`ac46ad53913e413e451710a3563590b62d183927`.

The pre-implementation upstream drift classification completed successfully:

| Area | Changed paths |
| --- | ---: |
| Java backend | 791 |
| Database migration/schema | 0 |
| Frontend/API | 114 |
| Python backend | 342 |
| Docs/config/CI | 356 |
| Scanner/CLI | 69 |

There was no upstream database migration/schema overlap with the new local
collection schema. Existing upstream migration files under
`server-python/app/db/migration/` were not modified.

## Delivered Contract

### Schema

The Python-owned local migration
`server-python/app/db/local_migration/20260726_01__local_collections.sql`
creates:

- `local_collection`
- `local_collection_version`
- `local_collection_version_member`

The schema enforces one collection slug per namespace, one draft per
collection, one semantic version per collection, ordered non-duplicate
members, exact `skill_id` plus `skill_version_id` references, and a foreign-key
protected latest-published-version pointer. Collection states are `ACTIVE` and
`ARCHIVED`; version states are `DRAFT`, `PUBLISHED`, and `YANKED`.

### Ownership And Access

Namespace `OWNER` and `ADMIN` members can curate collections in that namespace.
Platform `SKILL_ADMIN` and `SUPER_ADMIN` roles retain global curation access.
Reads apply the existing skill visibility rules to every member. A public
resolve never bypasses a private member's access boundary.

All mutating workflows require an authenticated curator, use a transaction,
write the audit record in that transaction, and lock the namespace,
collection, draft, or latest published version as appropriate. Create and
publish require `Idempotency-Key`; draft replacement requires `If-Match`.

### API

The FastAPI router adds nine default-off endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/web/namespaces/{namespace}/collections` | List visible collections |
| `GET` | `/api/web/collections/{namespace}/{collection}` | Read collection detail |
| `GET` | `/api/cli/v1/collections/{namespace}/{collection}/resolve` | Resolve one immutable install snapshot |
| `POST` | `/api/web/namespaces/{namespace}/collections` | Create a collection |
| `POST` | `/api/web/collections/{namespace}/{collection}/draft` | Create a draft |
| `PUT` | `/api/web/collections/{namespace}/{collection}/draft` | Replace the draft atomically |
| `DELETE` | `/api/web/collections/{namespace}/{collection}/draft` | Delete the draft |
| `POST` | `/api/web/collections/{namespace}/{collection}/publish` | Publish a semantic collection version |
| `PUT` | `/api/web/collections/{namespace}/{collection}/status` | Archive or restore a collection |

When collections are disabled, the router returns `404` before authentication
or request-body validation. This preserves the pre-feature external surface.

Publishing validates that every member still belongs to the same namespace,
that `skill_version.skill_id` matches the snapshotted skill, and that the
version is published, downloadable, not yanked, and attached to an active,
visible skill. Published collection versions must increase according to
SemVer 2.0 precedence.

Resolve returns the exact ordered member versions, their deterministic file
fingerprints, and exact version download URLs. It does not fall back to a
skill's latest version. If any snapshotted member is no longer installable or
readable, the whole resolve returns `409 error.collection.degraded`.

## OpenAPI And Frontend Compatibility

The TypeScript declarations were regenerated from a live Python FastAPI
OpenAPI document with the repository-pinned `openapi-typescript` generator.
The generated file changed broadly because its previous baseline still
described legacy Java-era schemas.

Nine frontend-only legacy aliases that are still consumed by existing UI code
but are not emitted by the Python OpenAPI document were retained as local
compatibility interfaces in `web/src/api/types.ts`. The token path parameter
type was aligned from `id` to the Python contract's `token_id`; the actual HTTP
URL and runtime behavior did not change. Typecheck, tests, lint, and production
build all pass with the Python OpenAPI document as the generated source of
truth.

## PostgreSQL End-To-End Evidence

A temporary PostgreSQL 16 database was migrated with
`python -m app.migrations upgrade`. Migration status returned
`skillhub_flyway_v43_baseline`, the three collection tables and one-draft index
were present, and a second upgrade completed without applying the migration
again.

An isolated owner, team namespace, skill, exact published skill version, and
skill file were seeded. Against a live FastAPI process, create, create-draft,
replace-draft, publish, identical publish replay, and resolve all succeeded.
Resolve returned collection `1.0.0`, the exact skill version `4.1.0`, and
fingerprint
`sha256:e4f39b530109f15e939234d3fa6b49431dfc542daecb3952a7b9c09b6596297a`.
After the referenced skill version was yanked, the same resolve returned
`409 error.collection.degraded`.

The first real resolve exposed an asyncpg `AmbiguousParameterError` for an
untyped nullable `:version` parameter. A focused regression test was added
first, then the query was fixed with `CAST(:version AS varchar)` in each null
check and comparison. The targeted test, live PostgreSQL flow, and complete
backend suite were rerun successfully.

The temporary PostgreSQL container was removed after verification.

## Architecture Inventory

`python scripts/sql_inventory.py` produced:

| Category | M0 baseline | M1 result | Delta |
| --- | ---: | ---: | ---: |
| API route | 15 | 15 | 0 |
| Migration bootstrap | 11 | 11 | 0 |
| Repository query | 108 | 137 | +29 |
| Service domain | 309 | 309 | 0 |

All 29 new query calls are in
`app/collections/read_repository.py` or
`app/collections/mutation_repository.py`. Collection route, contract, access,
and service modules contain no SQL. Existing
`server-python/app/api/skills.py` and
`server-python/app/skills/read_repository.py` were not changed.

## Verification

| Gate | Literal command | Result | Exit code |
| --- | --- | --- | ---: |
| Targeted M1 and core backend regressions | `cd server-python; .venv\Scripts\python.exe -m pytest tests/test_publish_transaction.py tests/test_publish_http_validate.py tests/test_skill_resolve_repository.py tests/test_skill_resolve_routes.py tests/test_cli_skills.py tests/test_skill_download.py tests/test_namespace_member_read.py tests/test_namespace_member_mutations.py tests/test_namespace_profile_lifecycle.py tests/test_route_registry.py tests/test_post_cutover_architecture.py tests/test_route_policy.py tests/test_schema_migration_baseline.py tests/test_collection_schema.py tests/test_collection_access.py tests/test_collection_read.py tests/test_collection_mutations.py tests/test_collection_resolve.py tests/test_collection_transactions.py tests/test_collection_feature_isolation.py -q` | 198 passed; one pre-existing Starlette deprecation warning | 0 |
| Complete backend | `cd server-python; .venv\Scripts\python.exe -m pytest tests -q` | 1006 passed; one pre-existing Starlette deprecation warning | 0 |
| Frontend typecheck | `cd web; corepack pnpm run typecheck` | Passed | 0 |
| Complete frontend tests | `cd web; corepack pnpm run test` | 194 files and 691 tests passed | 0 |
| Frontend lint | `cd web; corepack pnpm run lint` | Passed | 0 |
| Frontend build | `cd web; corepack pnpm run build` | Production build completed; existing runtime-config URL and chunk-size warnings remain | 0 |
| Complete CLI tests | `cd cli; bun test` | 346 passed, 6 Windows symlink tests skipped, 0 failed | 0 |
| CLI lint | `cd cli; bun run lint` | Passed | 0 |
| CLI typecheck | `cd cli; bun run typecheck` | Passed | 0 |
| CLI build | `cd cli; bun run build` | Passed; package remains `0.1.9` | 0 |
| Python backend image | `docker build --tag skillhub-server-python:m1-verify --file server-python/Dockerfile .` | Local image built; manifest digest `sha256:5e1e5295a8060277ceae6f20f90db9c43dbdd09cf3f29a47356ba9c6930a7754` | 0 |
| K8s render | `kubectl kustomize deploy\k8s\base` | Valid; collection and GitLab-import defaults remain `false` | 0 |
| Release Compose render | `docker compose --env-file .env.release.example -f compose.release.yml config --quiet` | Valid | 0 |
| Patch hygiene | `git diff --check` | Clean; only Git LF-to-CRLF worktree notices | 0 |

## Milestone 2 Stop Condition

The backend resolve contract is now represented in generated TypeScript types
and protected by route, repository, transaction, real PostgreSQL, and
regression tests. This is the review gate before Milestone 2 may implement the
custom CLI distribution pipeline and `install-collection` command.

Milestone 2 has not started. No collection CLI command, Nexus publication,
frontend install button, or UI maintenance surface was added.

## Authorization

No files were staged. No commit, push, pull request, deployment, CLI package
publication, or Nexus write has been performed.

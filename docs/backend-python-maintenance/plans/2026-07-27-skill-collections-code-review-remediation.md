# Skill Collections Code Review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the merge-blocking core-function, security, data-integrity,
deployment, and supply-chain risks found in the M0-M5 Skill Collections review
without widening the approved first-class collection design.

**Architecture:** Keep collections and GitLab import behind default-off feature
flags, but make their additive schema safe for the existing Skill lifecycle and
multi-replica startup. Preserve the Python publish/scanner pipeline, use
immutable database identifiers for collection membership, make repository
ingest claim-based and idempotent, and repair the Web/CLI/Nexus contracts before
any rollout. Complete one task and its targeted real-case verification before
starting the next task.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, asyncpg, PostgreSQL,
React/TypeScript/Vite, Bun/TypeScript CLI, GitHub Actions, Nexus npm, Docker,
and Kubernetes.

---

## Status and execution boundary

- Review date: 2026-07-27.
- Worktree: `C:\Users\USER\projects\skillhub\.worktrees\skill-collections-m0`.
- Branch: `codex/skill-collections-m0`.
- Reviewed baseline commit: `b54a135a674a75202cd30bbc6a5c53510840580c`.
- M0-M5 changes are uncommitted and have not been authorized for deployment.
- The `20260726_01` and `20260726_02` local migrations are therefore
  unreleased. Repair their definitions directly instead of preserving a known
  broken schema for compatibility.
- If preflight evidence shows that either migration has reached a shared
  database, stop Task 2 and write an additive compatibility migration instead
  of editing an applied migration.
- Do not contact real GitLab or Nexus, deploy, enable flags, commit, push, or
  open a PR without explicit authorization.
- Do not reintroduce Java, Maven, Spring Boot, or a hybrid runtime.

## Review findings covered

| ID | Priority | Finding | Task |
| --- | --- | --- | --- |
| R1 | P1 | Local migration execution and tracking are not atomic or serialized | 1 |
| R2 | P1 | Collection/import foreign keys block core Skill/version deletion | 2 |
| R3 | P1 | New `/api/web` mutations accept API tokens without the established policy | 3 |
| R4 | P1 | Slug/version collection input is ambiguous across Skill owners | 4 |
| R5 | P1 | Repository candidate ingest has no atomic claim or result ownership | 5 |
| R6 | P1 | Web entrypoint does not substitute the five new runtime variables | 6 |
| R7 | P1 | Web generates a collection coordinate without the CLI-required `@` | 7 |
| R8 | P1 | Nexus verification checks version text, not the remote artifact bytes | 8 |
| R9 | P2 | Repository archives and collection installs lack operation-level isolation | 9 |

## Fixed remediation decisions

1. Published collection history remains visible after a backing Skill is hard
   deleted, but exact resolution returns a controlled `409` because the bundle
   no longer exists. A database FK must never turn the existing hard-delete
   route into an unhandled `500`.
2. Repository import provenance keeps source, target coordinate, commit, and
   audit evidence after a target Skill/version is deleted. Its nullable target
   IDs use `ON DELETE SET NULL`.
3. Collection and repository-import endpoints remain Web/session endpoints.
   API-token principals receive the same route-specific `403` used by existing
   `/api/web` lifecycle endpoints. No new token scopes are introduced here.
4. Draft members are selected by `skillId` and `skillVersionId`; display
   slug/version fields are server-derived and never trusted as identity.
5. A repository import is claimed exactly once from `PREVIEW_READY` to
   `INGESTING`. A competing request receives `409`; candidate results are
   written only by the operation that owns the claim.
6. Existing single-Skill CLI behavior and the Python publish/scanner/review
   pipeline remain unchanged.

## File map

### Backend and schema

- `server-python/app/migrations.py` — serialize and atomically record local
  migrations.
- `server-python/app/db/local_migration/20260726_01__local_collections.sql` —
  retain collection snapshot data without restricting Skill lifecycle.
- `server-python/app/db/local_migration/20260726_02__local_repository_imports.sql`
  — retain import provenance with nullable target references.
- `server-python/app/api/collections.py` and
  `server-python/app/api/repository_imports.py` — apply the Web API-token
  rejection policy.
- `server-python/app/collections/contracts.py`,
  `mutation_repository.py`, `read_repository.py`, and `service.py` — immutable
  member identity and degraded snapshot handling.
- `server-python/app/repository_imports/repository.py`, `service.py`,
  `archive.py`, and `gitlab_client.py` — ingest claims and bounded/offloaded
  archive processing.
- `server-python/app/core/config.py` — operation-level GitLab import limits.

### Web, CLI, release, and deployment

- `web/docker-entrypoint.d/30-runtime-config.sh` — substitute every runtime
  variable used by the template.
- `web/src/features/collection/collection-install-command.tsx` — generate the
  canonical `@namespace/collection` coordinate.
- `web/src/pages/dashboard/collection-maintenance.tsx` and collection feature
  types — send immutable member IDs.
- `cli/src/services/install-transaction.ts` and
  `collection-install-service.ts` — stage one downloaded archive at a time and
  cap manifest members.
- `.github/workflows/release-cli.yml` — internal runner, temporary npm config,
  and byte-for-byte remote package verification.
- `.env.release.example`, `compose.release.yml`, `deploy/k8s/**`,
  `server-python/ENVIRONMENT_VARIABLES.md`, and
  `deploy/k8s/skill-collections-operations.zh.md` — document and wire new
  operation limits.

### Verification

- Extend the existing focused tests under `server-python/tests/`,
  `web/src/**`, `web/e2e/`, and `cli/test/`.
- Record the final evidence in
  `docs/backend-python-maintenance/results/2026-07-27-skill-collections-remediation-verification.md`.

## Task 1: Serialize migration operations and atomically record local migrations

**Files:**

- Modify: `server-python/app/migrations.py`
- Modify: `server-python/tests/test_schema_migration_baseline.py`

- [x] **Step 1: Add failing operation-lock and rollback regression tests**

  Extend `FakeConnection` with an async transaction context manager and record
  events in execution order. Cover a fresh `upgrade_database` and a direct
  `apply_local_schema_migrations` call. The fresh upgrade must acquire the lock
  before the first bundled baseline statement, rather than waiting until the
  local extensions:

  ```python
  def test_fresh_upgrade_locks_before_bundled_baseline_sql() -> None:
      connection = FakeConnection()

      asyncio.run(migrations.upgrade_database(connection, flyway_dir=FLYWAY_DIR))

      assert connection.events[0] == "transaction:enter"
      assert "pg_advisory_xact_lock" in connection.executed[0]
      assert next(
          index
          for index, sql in enumerate(connection.executed)
          if "CREATE TABLE user_account" in sql
      ) > 0
      assert any("INSERT INTO local_schema_migration" in sql for sql in connection.executed)
      assert connection.events[-1] == "transaction:exit"
  ```

  Add a direct-local-migration test asserting the same lock/transaction
  boundary, and a rollback test whose fake raises immediately after a local
  migration SQL file succeeds but its tracking `INSERT` fails. Assert that
  `transaction:rollback` is recorded, the DDL and tracking write were both
  attempted, and neither is committed. Extend the existing stamp test to
  assert that stamp remains a compatibility/baseline-only operation and does
  not begin applying local feature migrations.

  Assert the operation requests `READ COMMITTED` explicitly instead of
  inheriting a database/role default. Add a two-file bundled migration fixture
  in which the first file uses `SET LOCAL lock_timeout` and assert the previous
  timeout is restored before the second file executes. Also assert stamp enters
  the operation transaction while read-only status does not.

- [x] **Step 2: Run the new tests and confirm the current runner fails**

  ```powershell
  cd server-python
  uv run pytest tests/test_schema_migration_baseline.py -q
  ```

  Expected result: the new assertions fail because fresh baseline and local
  migrations currently run without a shared operation-level lock/transaction.

- [x] **Step 3: Lock the complete upgrade/stamp operation and keep local SQL plus its record atomic**

  Add a stable signed 64-bit lock key and a shared transaction context:

  ```python
  LOCAL_MIGRATION_LOCK_KEY = 0x534B494C4C485542

  @asynccontextmanager
  async def migration_operation(connection: DatabaseConnection):
      async with connection.transaction(isolation="read_committed"):
          await connection.execute(
              "SELECT pg_advisory_xact_lock($1)",
              LOCAL_MIGRATION_LOCK_KEY,
          )
          yield
  ```

  Extract the current local migration loop to a private unlocked helper.
  `upgrade_database` and `stamp_existing_database` enter `migration_operation`
  before checking or applying bundled baseline SQL. Upgrade calls the private
  local helper inside that same transaction; stamp preserves its existing
  compatibility/baseline-only behavior and must not apply local feature
  migrations. The public
  `apply_local_schema_migrations` entrypoint also enters
  `migration_operation`, so direct callers remain safe without nesting when it
  is invoked from upgrade.

  Preserve the previous per-file behavior of transaction-local settings.
  Snapshot `SHOW lock_timeout` before executing each bundled Flyway file and
  restore it with parameterized
  `SELECT set_config('lock_timeout', $1, true)` before the next file. Do not
  modify the historical V42 SQL file.

  Update the connection protocol and fake transaction object without adding an
  ORM, a second migration framework, or a lock around read-only `status`.

- [x] **Step 4: Verify success, rollback, and repeat execution**

  ```powershell
  uv run pytest tests/test_schema_migration_baseline.py -q
  ```

  Expected result: the success, injected rollback, and repeat-execution tests
  pass. Do not run the still-unrepaired `20260726` schema against a persistent
  development or shared database at this step.

- [x] **Step 5: Stop on a real multi-process failure**

  Create an isolated disposable PostgreSQL database that is used only for this
  task:

  ```powershell
  docker run --name skillhub-migration-verify `
    -e POSTGRES_USER=skillhub `
    -e POSTGRES_PASSWORD=skillhub `
    -e POSTGRES_DB=skillhub_migration_verify `
    -p 55432:5432 `
    -d postgres:16-alpine
  $env:SKILLHUB_DATABASE_URL='postgresql+asyncpg://skillhub:skillhub@127.0.0.1:55432/skillhub_migration_verify'
  ```

  Wait until `docker exec skillhub-migration-verify pg_isready` reports
  accepting connections. Set the disposable database default to
  `REPEATABLE READ` so the explicit operation isolation is exercised:

  ```powershell
  docker exec skillhub-migration-verify psql `
    -U skillhub `
    -d postgres `
    -c "ALTER DATABASE skillhub_migration_verify SET default_transaction_isolation TO 'repeatable read';"
  ```

  Then launch two
  `python -m app.migrations upgrade` processes at the same time. Both must exit
  `0`, and this query must return one row per identifier:

  ```powershell
  $repo = 'C:\Users\USER\projects\skillhub\.worktrees\skill-collections-m0'
  $databaseUrl = $env:SKILLHUB_DATABASE_URL
  $jobs = 1..2 | ForEach-Object {
    Start-Job -ArgumentList $repo, $databaseUrl -ScriptBlock {
      param($repoPath, $url)
      Set-Location (Join-Path $repoPath 'server-python')
      $env:SKILLHUB_DATABASE_URL = $url
      $output = & uv run python -m app.migrations upgrade 2>&1
      [pscustomobject]@{
        ExitCode = $LASTEXITCODE
        Output = ($output -join "`n")
      }
    }
  }
  $results = $jobs | Wait-Job | Receive-Job
  $results | Format-List
  ```

  ```sql
  SELECT identifier, COUNT(*)
  FROM local_schema_migration
  GROUP BY identifier
  HAVING COUNT(*) <> 1;
  ```

  Execute the query with:

  ```powershell
  docker exec skillhub-migration-verify psql `
    -U skillhub `
    -d skillhub_migration_verify `
    -c 'SELECT identifier, COUNT(*) FROM local_schema_migration GROUP BY identifier HAVING COUNT(*) <> 1;'
  ```

  Expected result: both `ExitCode` values are `0` and the query returns zero
  rows. Do not continue to Task 2 if either process
  fails, blocks indefinitely, or reports duplicate DDL.

  Before removing the container, run a real rollback probe through
  `apply_local_schema_migrations`: use a temporary migration whose DDL creates
  `rollback_probe` and whose identifier is 65 characters, forcing the
  `VARCHAR(64)` tracking insert to fail. The call must raise, and
  `SELECT to_regclass('rollback_probe')` must return `NULL`.

  Remove only the explicitly named disposable container after recording the
  result:

  ```powershell
  docker rm -f skillhub-migration-verify
  Remove-Item Env:SKILLHUB_DATABASE_URL
  ```

## Task 2: Preserve core Skill lifecycle while retaining collection/import evidence

**Files:**

- Modify: `server-python/app/db/local_migration/20260726_01__local_collections.sql`
- Modify: `server-python/app/db/local_migration/20260726_02__local_repository_imports.sql`
- Modify: `server-python/app/collections/contracts.py`
- Modify: `server-python/app/collections/mutation_repository.py`
- Modify: `server-python/app/collections/read_repository.py`
- Modify: `server-python/app/collections/service.py`
- Modify: `server-python/tests/test_collection_schema.py`
- Modify: `server-python/tests/test_repository_import_schema.py`
- Modify: `server-python/tests/test_collection_read.py`
- Modify: `server-python/tests/test_collection_resolve.py`
- Create: `server-python/tests/test_collection_repository_snapshots.py`
- Modify: `server-python/tests/test_skill_hard_delete.py`
- Modify: `web/src/pages/collection-detail.tsx`
- Modify: `web/src/pages/collection-detail.test.tsx`
- Modify: `web/src/i18n/locales/en.json`
- Modify: `web/src/i18n/locales/zh-TW.json`
- Modify: `web/src/i18n/locales/zh.json`
- Regenerate: `web/src/api/generated/schema.d.ts`

- [x] **Step 1: Add failing schema-policy tests**

  Assert the collection member table has a surrogate member ID, nullable target
  FKs with `ON DELETE SET NULL`, and immutable display snapshots. Assert the
  import candidate target FKs also use `ON DELETE SET NULL`.

  ```python
  assert "id BIGSERIAL PRIMARY KEY" in collection_sql
  assert "skill_slug_snapshot VARCHAR(128) NOT NULL" in collection_sql
  assert "skill_version_snapshot VARCHAR(64) NOT NULL" in collection_sql
  assert "REFERENCES skill(id) ON DELETE SET NULL" in collection_sql
  assert "REFERENCES skill_version(id) ON DELETE SET NULL" in collection_sql
  assert import_sql.count("ON DELETE SET NULL") >= 2
  ```

- [x] **Step 2: Add failing lifecycle scenarios**

  Cover all three deletion paths:

  1. hard-delete a Skill referenced by a published collection;
  2. delete a draft/rejected/scan-failed version referenced by an import;
  3. replace an upload version created by repository import.

  The expected outcome is successful lifecycle deletion. Collection detail
  retains `skillSlug` and `version` from its snapshots; collection resolve
  returns `409 error.collection.resolve.degraded`; import detail retains
  source/target/commit evidence with nullable IDs.

- [x] **Step 3: Replace restrictive collection member identity with retained snapshots**

  Because the migration is unreleased, define the table in its final form:

  ```sql
  CREATE TABLE IF NOT EXISTS local_collection_version_member (
      id BIGSERIAL PRIMARY KEY,
      collection_version_id BIGINT NOT NULL
          REFERENCES local_collection_version(id) ON DELETE CASCADE,
      skill_id BIGINT REFERENCES skill(id) ON DELETE SET NULL,
      skill_version_id BIGINT REFERENCES skill_version(id) ON DELETE SET NULL,
      skill_slug_snapshot VARCHAR(128) NOT NULL,
      skill_version_snapshot VARCHAR(64) NOT NULL,
      skill_owner_id_snapshot VARCHAR(128) NOT NULL,
      skill_visibility_snapshot VARCHAR(32) NOT NULL,
      position INTEGER NOT NULL CHECK (position >= 0),
      note VARCHAR(500),
      UNIQUE (collection_version_id, skill_version_id),
      UNIQUE (collection_version_id, position)
  );
  ```

  Change repository reads to `LEFT JOIN` the live Skill/version and use the
  snapshot fields for historical display. Make response IDs nullable:

  ```python
  class CollectionMemberResponse(CollectionContract):
      skill_id: int | None = None
      skill_version_id: int | None = None
      namespace: str
      skill_slug: str
      version: str
      position: int
      note: str | None = None
  ```

  Resolve must explicitly detect either missing live ID before computing files
  or download URLs and raise a controlled degraded `409`.

  Retain canonical owner and visibility snapshots as well as the coordinate so
  a deleted `NAMESPACE_ONLY` or `PRIVATE` member does not become anonymously
  visible. A surviving partial Skill reference continues to use its live
  access/lifecycle fields. Capture `OLD.owner_id` and `OLD.visibility` in a
  local `BEFORE DELETE ON skill` trigger immediately before the target FK is
  nulled, so a Skill that changed visibility after collection publication
  retains its final live access boundary instead of a stale earlier snapshot.

  Serialize member replacement against target deletion with
  `FOR KEY SHARE OF s, sv`. Lock draft member rows during publish validation
  with `FOR UPDATE OF member`, so a concurrent FK `SET NULL` either completes
  before validation and is rejected or waits until the valid publish
  transaction commits.

  Keep the trigger and FK actions out of full-table scans by defining leading,
  partial indexes for `local_collection_version_member(skill_id)`,
  `local_repository_import_candidate(skill_id)`, and
  `local_repository_import_candidate(skill_version_id)`. The existing
  collection `(skill_version_id, skill_id)` index remains the leading index for
  its version FK.

  In `collection-detail.tsx`, use the live version ID when present and the
  immutable snapshot coordinate when it is absent:

  ```tsx
  key={
    member.skillVersionId
      ?? `${member.skillSlug}@${member.version}:${member.position}`
  }
  ```

- [x] **Step 4: Make import provenance nullable without deleting evidence**

  Use:

  ```sql
  skill_id BIGINT REFERENCES skill(id) ON DELETE SET NULL,
  skill_version_id BIGINT REFERENCES skill_version(id) ON DELETE SET NULL,
  ```

  Keep `source_path`, `target_slug`, `target_version`, visibility, commit SHA,
  archive digest, warnings, and error code unchanged.

- [x] **Step 5: Regenerate API types after contract nullability changes**

  Start the FastAPI app and regenerate
  `web/src/api/generated/schema.d.ts` through the repository's existing OpenAPI
  generation path. Do not edit the generated file manually.

- [x] **Step 6: Verify lifecycle behavior with real PostgreSQL**

  ```powershell
  cd server-python
  uv run pytest tests/test_collection_schema.py tests/test_repository_import_schema.py tests/test_collection_read.py tests/test_collection_resolve.py tests/test_skill_hard_delete.py -q
  uv run python scripts/sql_inventory.py
  ```

  Then use the local API/database to publish one Skill, add it to a collection,
  hard-delete it, and inspect both collection detail and resolve. The delete
  must remain successful, detail must retain its coordinate, and resolve must
  return controlled `409`, never `500`. Also change a referenced public Skill
  to `NAMESPACE_ONLY` and `PRIVATE` before deletion and prove anonymous reads
  remain hidden after deletion. Run PostgreSQL `EXPLAIN` for the trigger/FK
  update predicates and confirm each uses its intended leading index.

## Task 3: Enforce the existing Web principal policy on new mutation routes

**Files:**

- Modify: `server-python/app/api/collections.py`
- Modify: `server-python/app/api/repository_imports.py`
- Modify: `server-python/tests/test_collection_access.py`
- Modify: `server-python/tests/test_repository_import_api.py`

- [x] **Step 1: Add bearer-policy regression tests**

  Configure `auth_bearer_reader` to return:

  ```python
  {
      "userId": "namespace-owner",
      "oauthProvider": "api_token",
      "tokenScopes": ["skill:read"],
      "platformRoles": ["USER"],
  }
  ```

  Assert every collection mutation, repository preview, ingest, seed, and
  update-check endpoint returns:

  ```python
  assert response.status_code == 403
  assert response.json()["detail"] == (
      f"API token cannot access endpoint: {response.request.url.path}"
  )
  ```

  Also retain session/mock success, invalid bearer `401`, MEMBER `403`, and
  disabled-flag `404` cases.

- [x] **Step 2: Confirm current routes accept the read-only token**

  ```powershell
  cd server-python
  uv run pytest tests/test_collection_access.py tests/test_repository_import_api.py -q
  ```

  Expected result: the new token-policy cases fail before the service call.

- [x] **Step 3: Apply one route-consistent resolver in both API modules**

  Import `reject_api_token_principal_for_route` and use:

  ```python
  async def _current_web_user(
      request: Request,
      mock_user_id: str | None,
      authorization: str | None,
  ) -> dict[str, object]:
      user = dict(
          await resolve_current_user_or_401(
              request,
              mock_user_id,
              authorization,
          )
      )
      reject_api_token_principal_for_route(user, request.url.path)
      return user
  ```

  Route every new `/api/web/collections` and `/api/web/repository-imports`
  handler through this helper before namespace authorization or service work.

- [x] **Step 4: Verify no publish or collection mutation occurs after rejection**

  ```powershell
  uv run pytest tests/test_collection_access.py tests/test_repository_import_api.py tests/test_publish_http_validate.py tests/test_skill_hard_delete.py -q
  ```

  Assert mocked writers/publishers were not called for rejected API tokens.

## Task 4: Use immutable IDs for collection membership

**Files:**

- Modify: `server-python/app/collections/contracts.py`
- Modify: `server-python/app/collections/mutation_repository.py`
- Modify: `server-python/app/collections/service.py`
- Modify: `server-python/app/api/repository_imports.py`
- Modify: `server-python/app/api/skills.py`
- Modify: `server-python/app/skills/read_repository.py`
- Modify: `server-python/tests/test_collection_mutations.py`
- Modify: `server-python/tests/test_collection_transactions.py`
- Modify: `server-python/tests/test_collection_repository_snapshots.py`
- Modify: `server-python/tests/test_repository_import_publish_integration.py`
- Modify: `server-python/tests/test_skill_versions.py`
- Modify: `web/src/pages/dashboard/collection-maintenance.tsx`
- Modify: `web/src/pages/dashboard/collection-maintenance.test.tsx`
- Modify: `web/src/features/collection/collection-member-editor.tsx`
- Modify: `web/src/features/collection/collection-member-editor.test.tsx`
- Modify: `web/src/features/collection/collection-version-diff.tsx`
- Modify: `web/src/features/collection/collection-version-diff.test.tsx`
- Modify: `web/src/features/skill/use-skill-versions.ts`
- Modify: `web/src/shared/hooks/use-skill-queries.ts`
- Modify: `web/src/i18n/locales/en.json`
- Modify: `web/src/i18n/locales/zh-TW.json`
- Modify: `web/src/i18n/locales/zh.json`
- Modify: `web/src/features/repository-import/**`
- Regenerate: `web/src/api/generated/schema.d.ts`

- [x] **Step 1: Add the duplicate-owner regression first**

  Model two Skills with the same namespace, slug, and version but different
  owner/IDs. Submit the second Skill's IDs and assert the stored member uses
  exactly those IDs, regardless of insertion order.

  ```python
  payload = CollectionDraftReplaceRequest.model_validate(
      {
          "displayName": "Superpowers",
          "summary": "Curated skills",
          "members": [
              {
                  "skillId": 202,
                  "skillVersionId": 902,
                  "position": 0,
              }
          ],
      }
  )
  ```

  Add negative cases for mismatched Skill/version IDs and a Skill outside the
  collection namespace; both return `400 error.collection.member.notFound`.

- [x] **Step 2: Replace client-provided coordinates with immutable IDs**

  Define:

  ```python
  class CollectionMemberInput(CollectionContract):
      skill_id: int
      skill_version_id: int
      position: int
      note: str | None = None
  ```

  Resolve the pair with:

  ```sql
  WHERE s.id = :skill_id
    AND sv.id = :skill_version_id
    AND sv.skill_id = s.id
    AND s.namespace_id = :namespace_id
  ```

  Continue validating ACTIVE/not-hidden Skill, PUBLISHED/download-ready
  version, and no yank. Populate snapshot slug/version only from the returned
  database row.

- [x] **Step 3: Update GitLab draft seeding**

  Pass the exact `skill_id` and `skill_version_id` returned by the existing
  publisher into `CollectionDraftReplaceRequest`. Do not translate the result
  back to slug/version and then re-resolve it.

- [x] **Step 4: Update the maintenance UI**

  Use `skillId` and `versionId` as option values and React keys. Display
  `namespace/slug@version` only as a label. The draft request must contain:

  ```ts
  {
    skillId: selected.skillId,
    skillVersionId: selected.versionId,
    position,
    note,
  }
  ```

- [x] **Step 5: Regenerate types and verify backend/UI contracts**

  ```powershell
  cd server-python
  uv run pytest tests/test_collection_mutations.py tests/test_collection_transactions.py tests/test_repository_import_publish_integration.py -q
  cd ..\web
  pnpm run typecheck
  pnpm exec vitest run src/pages/dashboard/collection-maintenance.test.tsx
  ```

  Expected result: no path accepts a member based only on slug/version.

## Task 5: Add atomic repository-ingest claims and owned result transitions

**Files:**

- Modify: `server-python/app/repository_imports/repository.py`
- Modify: `server-python/app/repository_imports/service.py`
- Modify: `server-python/app/repository_imports/contracts.py`
- Modify: `server-python/app/api/repository_imports.py`
- Modify: `server-python/app/db/local_migration/20260726_02__local_repository_imports.sql`
- Modify: `server-python/tests/test_repository_import_repository.py`
- Modify: `server-python/tests/test_repository_import_schema.py`
- Modify: `server-python/tests/test_repository_import_service.py`
- Modify: `server-python/tests/test_repository_import_publish_integration.py`

- [x] **Step 1: Add concurrent-ingest failure tests**

  Add a repository test proving only one operation can transition:

  ```sql
  UPDATE local_repository_import
  SET state = 'INGESTING', updated_at = CURRENT_TIMESTAMP
  WHERE id = :import_id AND state = 'PREVIEW_READY'
  RETURNING id
  ```

  Add a service test with two concurrent ingest calls. The first pauses after
  claim; the second must receive
  `409 error.repositoryImport.ingest.inProgress`, and the publisher must be
  called only once.

- [x] **Step 2: Add an operation identifier**

  Add an unreleased-schema column:

  ```sql
  ingest_operation_id VARCHAR(64)
  ```

  Generate a UUID hex value at the service boundary. `claim_ingest` sets
  `INGESTING` and the operation ID only when the import is
  `PREVIEW_READY`. Candidate selection and result statements include:

  ```sql
  AND EXISTS (
      SELECT 1
      FROM local_repository_import parent
      WHERE parent.id = local_repository_import_candidate.import_id
        AND parent.state = 'INGESTING'
        AND parent.ingest_operation_id = :operation_id
  )
  ```

  Check `RETURNING id`; zero rows is a conflict, never silent success.

- [x] **Step 3: Make terminal transitions owner-conditional**

  Complete with:

  ```sql
  UPDATE local_repository_import
  SET state = :state,
      error_code = :error_code,
      ingest_operation_id = NULL,
      updated_at = CURRENT_TIMESTAMP
  WHERE id = :import_id
    AND state = 'INGESTING'
    AND ingest_operation_id = :operation_id
  RETURNING id
  ```

  Preserve `COMPLETED` versus `PARTIAL`; unexpected operation ownership loss
  raises a conflict and does not overwrite another result.

- [x] **Step 4: Verify retry semantics**

  Define these exact outcomes:

  - competing request during `INGESTING` -> `409`;
  - completed import -> `409`, no republish;
  - failed candidate within an owned ingest -> import becomes `PARTIAL`;
  - process failure before a terminal transition leaves `INGESTING` for
    operator reconciliation, never automatic republish.

  Do not add an automatic retry, timeout reaper, or background worker in this
  remediation.

- [x] **Step 5: Run repository, service, and publish-pipeline tests**

  ```powershell
  cd server-python
  uv run pytest tests/test_repository_import_repository.py tests/test_repository_import_service.py tests/test_repository_import_publish_integration.py -q
  ```

  Then issue two simultaneous ingest requests against the local API. Exactly
  one request may enter publish/scanner; the other must return controlled
  `409`.

## Task 6: Make Web runtime configuration substitution complete

**Files:**

- Modify: `web/Dockerfile`
- Modify: `web/docker-entrypoint.d/30-runtime-config.sh`
- Modify: `server-python/tests/test_deployment_cutover.py`
- Verify: `web/runtime-config.js.template`

- [x] **Step 1: Add a template-to-entrypoint completeness test**

  Parse `${NAME}` references from `runtime-config.js.template` and assert every
  reference is both defaulted and present in the explicit `envsubst` argument.
  The test must fail with this exact missing set before implementation:

  ```python
  {
      "SKILLHUB_WEB_COLLECTIONS_ENABLED",
      "SKILLHUB_WEB_GITLAB_IMPORT_ENABLED",
      "SKILLHUB_WEB_CLI_NPM_REGISTRY",
      "SKILLHUB_WEB_CLI_PACKAGE",
      "SKILLHUB_WEB_CLI_VERSION",
  }
  ```

- [x] **Step 2: Default and substitute all five variables**

  Add:

  ```sh
  : "${SKILLHUB_WEB_COLLECTIONS_ENABLED:=false}"
  : "${SKILLHUB_WEB_GITLAB_IMPORT_ENABLED:=false}"
  : "${SKILLHUB_WEB_CLI_NPM_REGISTRY:=}"
  : "${SKILLHUB_WEB_CLI_PACKAGE:=}"
  : "${SKILLHUB_WEB_CLI_VERSION:=}"
  ```

  Include the same five names in the existing explicit `envsubst` allowlist.

- [x] **Step 3: Verify default-off and enabled container output**

  ```powershell
  cd server-python
  uv run pytest tests/test_deployment_cutover.py -q
  cd ..\web
  docker build -t skillhub-web:collections-runtime-verify .
  ```

  Run the image once with no new env and once with known enabled/Nexus values.
  Copy or inspect `/usr/share/nginx/html/runtime-config.js`. It must contain no
  literal `${`, default flags must be `"false"`, and enabled values must match
  the supplied environment exactly.

## Task 7: Align the Web install command with the CLI parser

**Files:**

- Modify: `web/src/features/collection/collection-install-command.tsx`
- Modify: `web/src/features/collection/collection-install-command.test.tsx`
- Modify: `web/e2e/collection-install-command.spec.ts`
- Verify: `cli/src/shared/collection-name-parser.ts`

- [x] **Step 1: Change the tests to the canonical coordinate**

  Expected command fragment:

  ```text
  collection install @opensource/superpowers
  ```

  Retain exact CLI version, Nexus `--registry`, SkillHub `--registry`,
  collection `--version`, and `--scope user`.

- [x] **Step 2: Confirm the corrected test fails**

  ```powershell
  cd web
  pnpm exec vitest run src/features/collection/collection-install-command.test.tsx
  ```

- [x] **Step 3: Add the missing `@` in one place**

  ```ts
  `@${input.namespace}/${input.collection}`,
  ```

  Do not loosen the CLI parser to accept the ambiguous non-canonical form.

- [x] **Step 4: Execute the copied command contract**

  ```powershell
  cd web
  pnpm exec vitest run src/features/collection/collection-install-command.test.tsx
  pnpm exec playwright test e2e/collection-install-command.spec.ts --project=chromium --workers=1
  cd ..\cli
  bun run build
  node dist/index.js collection install @opensource/superpowers --registry https://skills.example.com --scope user --json
  ```

  A fake/unreachable registry may fail after parsing, but it must not return
  `collection must use @namespace/collection` or usage exit code `5`.

## Task 8: Make the Nexus CLI release byte-verifiable and credential-safe

**Files:**

- Modify: `.github/workflows/release-cli.yml`
- Modify: `cli/test/unit/scripts/release-workflow.test.ts`
- Modify: `cli/RELEASE.md`
- Modify: `deploy/k8s/skill-collections-operations.zh.md`

- [x] **Step 1: Add failing workflow contract assertions**

  Assert the publish job:

  - uses the approved self-hosted internal-Nexus runner labels;
  - has no public npm registry fallback;
  - writes credentials only to `NPM_CONFIG_USERCONFIG` under `$RUNNER_TEMP`;
  - cleans that file with `if: always()`;
  - downloads the exact package from hosted and install registries;
  - compares both SHA-256 values with
    `needs.build-and-test.outputs.package_sha256`.

- [x] **Step 2: Separate public build from internal publish connectivity**

  Keep build/test on `ubuntu-latest`. Run only `publish-npm` on:

  ```yaml
  runs-on: [self-hosted, linux, skillhub-nexus]
  ```

  Require non-empty `NPM_PUBLISH_REGISTRY` and `NPM_INSTALL_REGISTRY` repository
  variables in the publish job. Do not default either value to
  `https://registry.npmjs.org`.

- [x] **Step 3: Use an ephemeral npm configuration**

  Set:

  ```yaml
  env:
    NPM_CONFIG_USERCONFIG: ${{ runner.temp }}/skillhub-cli-release.npmrc
  ```

  Write tokens only to that path and add:

  ```yaml
  - name: Remove npm credentials
    if: always()
    run: rm -f "$NPM_CONFIG_USERCONFIG"
  ```

- [x] **Step 4: Verify existing and newly published artifacts by bytes**

  For both hosted and install/group registries:

  ```bash
  PACK_JSON=$(npm pack "${PACKAGE_NAME}@${VERSION}" \
    --registry "$VERIFY_REGISTRY" \
    --pack-destination "$RUNNER_TEMP/registry-verify" \
    --json)
  REMOTE_TARBALL=$(node -e \
    "const p=JSON.parse(process.argv[1]); process.stdout.write(p[0].filename)" \
    "$PACK_JSON")
  REMOTE_SHA256=$(sha256sum \
    "$RUNNER_TEMP/registry-verify/$REMOTE_TARBALL" | cut -d ' ' -f 1)
  test "$REMOTE_SHA256" = "$EXPECTED_SHA256"
  ```

  If the hosted version already exists with different bytes, fail the release;
  never skip and report success.

- [x] **Step 5: Run local workflow tests and no-publish rehearsal**

  ```powershell
  cd cli
  bun test test/unit/scripts/release-workflow.test.ts
  bun run build
  npm pack --dry-run
  ```

  Real Nexus publication remains an external authorization gate. Document the
  required runner labels, repository variables, secret, hosted/group split,
  digest evidence, and credential cleanup.

## Task 9: Bound and isolate archive-heavy operations

**Files:**

- Modify: `server-python/app/core/config.py`
- Modify: `server-python/app/repository_imports/archive.py`
- Modify: `server-python/app/repository_imports/service.py`
- Modify: `server-python/app/api/repository_imports.py`
- Modify: `server-python/app/collections/contracts.py`
- Modify: `server-python/tests/test_config.py`
- Modify: `server-python/tests/test_repository_import_archive.py`
- Modify: `server-python/tests/test_repository_import_service.py`
- Modify: `cli/src/services/collection-install-service.ts`
- Modify: `cli/src/services/install-transaction.ts`
- Modify: `cli/test/unit/services/collection-install-service.test.ts`
- Modify: `cli/test/unit/services/install-transaction.test.ts`
- Modify: `.env.release.example`
- Modify: `compose.release.yml`
- Modify: `deploy/k8s/base/configmap.yaml`
- Modify: `deploy/k8s/plain/backend/config.yaml`
- Modify: `server-python/ENVIRONMENT_VARIABLES.md`
- Modify: `deploy/k8s/environment-variables.zh.md`
- Modify: `deploy/k8s/skill-collections-operations.zh.md`

- [x] **Step 1: Add operation-limit tests before implementation**

  Pin these safe defaults:

  ```text
  SKILLHUB_GITLAB_ARCHIVE_MAX_FILES=500
  SKILLHUB_GITLAB_ARCHIVE_MAX_SINGLE_FILE_BYTES=5242880
  SKILLHUB_GITLAB_ARCHIVE_MAX_EXPANDED_BYTES=52428800
  SKILLHUB_GITLAB_IMPORT_MAX_CANDIDATES=100
  ```

  Add config override/boundary tests, candidate-count rejection, collection
  draft/member-count rejection using a shared code constant of `100`, and CLI
  manifest member-count rejection using the same fixed contract maximum.

- [x] **Step 2: Offload ZIP parsing from the event loop**

  Build `RepositoryArchiveLimits` from settings and call:

  ```python
  files = await asyncio.to_thread(
      read_repository_archive,
      archive,
      archive_limits,
  )
  ```

  Apply this in preview, ingest verification, and update-check paths. Keep the
  archive hash check before parsing and retain all traversal/symlink/duplicate
  protections.

- [x] **Step 3: Reject oversized discovery results before persistence or publish**

  After discovery and before `create_preview`:

  ```python
  if len(candidates) > context.import_max_candidates:
      raise RepositoryImportServiceError(
          "error.repositoryImport.candidate.tooMany",
          status_code=413,
      )
  ```

  Add `Field(max_length=100)` to collection draft members and retain the same
  maximum in CLI manifest validation, so backend and client fail consistently.

- [x] **Step 4: Stage collection archives one package at a time**

  Refactor `installPackages` so it does not retain an array of every member's
  `ArrayBuffer`. For each package plan: load once, validate the version, extract
  to all prepared targets for that package, then release the archive reference
  before loading the next package. Preserve the existing all-filesystem and
  inventory rollback boundary.

  Add an event-order test:

  ```ts
  expect(events).toEqual([
    'load:alpha',
    'extract:alpha',
    'load:beta',
    'extract:beta',
    'inventory:write',
  ])
  ```

- [x] **Step 5: Wire and document every new backend limit**

  Keep defaults conservative in config, Compose, K8s base/plain manifests, and
  both operator references. These are backend limits; never expose them or the
  GitLab token in Web runtime config.

- [x] **Step 6: Verify availability-oriented scenarios**

  ```powershell
  cd server-python
  uv run pytest tests/test_config.py tests/test_repository_import_archive.py tests/test_repository_import_service.py -q
  cd ..\cli
  bun test test/unit/services/collection-install-service.test.ts test/unit/services/install-transaction.test.ts
  ```

  During a maximum-allowed local archive preview, repeatedly call an existing
  lightweight endpoint such as `/api/health`. It must remain responsive; an
  over-limit archive or collection must fail with `413` before publish or
  filesystem mutation.

## Task 10: Full core-function regression and rollout decision

**Files:**

- Create:
  `docs/backend-python-maintenance/results/2026-07-27-skill-collections-remediation-verification.md`
- Verify only: all M0-M5 implementation and deployment files

- [x] **Step 1: Run focused remediation gates**

  Run every focused command from Tasks 1-9 again after all changes are present.
  Record exact commands, pass counts, skipped tests, and any environmental
  limitation in the result document.

- [x] **Step 2: Run full repository gates**

  ```powershell
  cd server-python
  uv sync --frozen
  uv run pytest tests -q
  uv run python scripts/sql_inventory.py
  cd ..\web
  pnpm run typecheck
  pnpm run lint
  pnpm exec vitest run
  pnpm run build
  pnpm exec playwright test --project=chromium --workers=1
  cd ..\cli
  bun run lint
  bun run typecheck
  bun test
  bun run build
  node dist/index.js version
  cd ..
  docker build -t skillhub-server-python:verify -f server-python/Dockerfile .
  kubectl kustomize deploy\k8s\base
  docker compose --env-file .env.release.example -f compose.release.yml config --quiet
  git diff --check
  ```

- [x] **Step 3: Execute the real-case core matrix**

  Record an evidence row for each case:

  | Area | Required scenario | Expected result |
  | --- | --- | --- |
  | Startup | two backend replicas migrate one database | both start; one row per migration |
  | Flags | all collection/import flags off | existing routes/UI work; new routes return 404 |
  | Auth | session owner, MEMBER, invalid token, read-only API token | success, 403, 401, 403 respectively |
  | Skill lifecycle | publish, scan, archive, restore, version delete, hard delete | unchanged; no FK 500 |
  | Collection | exact IDs, duplicate-owner slug, publish, resolve, install | selected IDs preserved; one atomic install |
  | Degraded snapshot | delete a published member Skill | detail retained; resolve controlled 409 |
  | GitLab import | preview, double ingest, scan failure, seed collection | one claim; pipeline/audit preserved |
  | Web runtime | default and enabled container config | no literal placeholders; flags behave correctly |
  | CLI | copied UI command and ordinary single-Skill install | both parse; existing install remains unchanged |
  | Nexus | dry-run plus mocked same-version/different-bytes package | byte mismatch fails closed |
  | Rollback | turn flags off and run prior core smoke | core remains available; additive data retained |

- [x] **Step 4: Review the complete diff, not only tests**

  Re-run static searches for:

  ```powershell
  rg -n "REFERENCES skill\\(id\\)|REFERENCES skill_version\\(id\\)" server-python/app/db/local_migration
  rg -n "resolve_current_user_or_401" server-python/app/api/collections.py server-python/app/api/repository_imports.py
  rg -n "skill_slug.*version|ORDER BY s.id.*LIMIT 1" server-python/app/collections
  rg -n "INGESTING|ingest_operation_id" server-python/app/repository_imports
  rg -n "SKILLHUB_WEB_(COLLECTIONS|GITLAB|CLI)" web/runtime-config.js.template web/docker-entrypoint.d/30-runtime-config.sh
  rg -n "registry.npmjs.org|~/.npmrc|package_sha256|npm pack" .github/workflows/release-cli.yml
  ```

  Every remaining match must agree with the fixed remediation decisions.

- [x] **Step 5: Write the merge verdict**

  The result document must distinguish:

  - verified locally;
  - external GitLab/Nexus/K8s gates not executed;
  - known pre-existing cross-process CLI inventory lost-update limitation;
  - merge blockers resolved or still open;
  - whether rollout remains blocked.

  Do not mark the remediation complete merely because the automated suites
  pass.

## Explicit non-goals

- No collection owner role; namespace OWNER/ADMIN remains the curator boundary.
- No automatic Skill or collection version bump.
- No GitLab webhook, schedule, background import, auto-approval, or
  auto-publication.
- No public GitHub/arbitrary-host repository import.
- No nested, cross-namespace, or label-dynamic collections.
- No collection uninstall/update command in this remediation.
- No replacement of the existing scanner, review, audit, publish, storage, or
  single-Skill install pipeline.
- No fix for the pre-existing cross-process CLI inventory lost-update issue;
  keep it documented as a rollout limitation.
- No real Nexus publication, GitLab access, deployment, flag enablement,
  commit, push, or PR without separate authorization.

## Per-task stop rule

After each task:

1. Run its focused automated tests.
2. Execute the listed real-case check.
3. Inspect the focused diff for adjacent core changes.
4. Update this plan's checkbox state and the result evidence.
5. Stop and report before beginning the next task if any existing core path
   regresses.

If commits are later authorized, make one narrow commit per completed task with
an imperative subject under 72 characters. Do not combine unrelated
remediations into one commit.

## Paste-ready execution prompt

```text
Execute
docs/backend-python-maintenance/plans/2026-07-27-skill-collections-code-review-remediation.md
in C:\Users\USER\projects\skillhub\.worktrees\skill-collections-m0.

Read AGENTS.md, server-python/AGENTS.md, the M0-M5 plan/result documents, and
the full remediation plan first. Treat SkillHub as a full-Python backend
project. Use TDD and execute exactly one remediation task at a time. After each
task, run its focused automated tests, execute its real-case check, inspect the
focused diff for effects on existing core functions, update the plan/result
evidence, and stop on any regression before proceeding.

Start with Task 1 only: serialize and atomically record local migrations. Do
not start Task 2 until Task 1's automated and real PostgreSQL concurrency
checks pass. Preserve all fixed remediation decisions and explicit non-goals.
Do not contact real GitLab or Nexus, deploy, enable flags, commit, push, or
open a PR without new explicit authorization.
```

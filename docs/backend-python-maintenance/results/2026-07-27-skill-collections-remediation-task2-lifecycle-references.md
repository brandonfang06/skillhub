# Skill Collections Remediation Task 2 Result

Date: 2026-07-27

Task: Preserve the existing Skill lifecycle while retaining collection and
repository-import evidence.

## Scope and boundary

This task changes only the unreleased local collection/import schema, the
collection read/write contract, generated Web API types, and their focused
tests. It does not implement Task 3 or any later remediation task. It does not
change the existing Skill hard-delete, version-delete, publish replacement, or
scanner implementations.

The two local migrations had not reached a shared database. The only prior
application was to a named disposable Task 1 verification database, which had
already been removed. The original local migration definitions were therefore
edited directly instead of adding a compatibility migration.

## Result

- Collection members now use a surrogate member ID.
- Collection member Skill/version references are nullable and use
  `ON DELETE SET NULL`.
- Immutable Skill slug and version snapshots remain after target deletion.
- Immutable owner and visibility snapshots retain the original member access
  boundary after target deletion.
- A local `BEFORE DELETE ON skill` trigger refreshes those access snapshots
  from the final live Skill row before PostgreSQL nulls the target references.
- Repository-import candidate target references use `ON DELETE SET NULL`;
  source path, target coordinate, commit, archive digest, upstream URL,
  warnings, and error evidence remain in place.
- Draft creation clones snapshots. Draft replacement stores the canonical
  database-resolved slug/version, not caller-provided display text.
- Collection reads retain historical members through `LEFT JOIN`s and expose
  nullable IDs.
- A fully deleted target remains visible as published collection history.
  Anonymous, namespace-member, and private-owner access still follows the
  retained `PUBLIC`, `NAMESPACE_ONLY`, or `PRIVATE` policy. When only the
  version reference is missing, the surviving Skill's current visibility,
  status, and hidden policy applies; partial references do not bypass live
  access rules.
- Draft publish preserves and rejects rows whose live target is missing.
- Draft member resolution locks the referenced Skill/version keys, while
  publish locks the member rows it validates. Concurrent core deletion is
  serialized instead of becoming an FK `500` or a stale publish.
- Leading partial indexes cover the collection delete trigger and all new
  collection/import referencing-FK actions, avoiding evidence-table scans
  inside existing hard-delete/version-delete transactions.
- Resolve rejects empty, missing, or inaccessible pinned members with
  `409 error.collection.resolve.degraded` before reading `skill_file` or
  constructing a fingerprint/download URL.
- The Web collection detail uses the live version ID as its React key when
  available and a stable snapshot-coordinate fallback when it is not.
- Degraded Web detail renders a fully deleted coordinate as historical text
  and suppresses the install command that would deterministically return
  `409`.
- Generated OpenAPI types now require `skillId` and `skillVersionId` fields
  whose values are `number | null`.

## TDD evidence

The first Task 2 focused run failed as intended:

```text
11 failed, 36 passed
```

After the initial implementation:

```text
48 passed, 1 existing Starlette deprecation warning
```

Independent spec review found a partial-reference access-policy gap. The new
RED cases reproduced it:

```text
4 failed, 8 passed, 1 existing warning
```

After separating fully deleted history from partial-reference policy:

```powershell
cd server-python
.venv\Scripts\python.exe -m pytest tests/test_collection_read.py tests/test_collection_resolve.py -q
```

```text
24 passed, 1 existing Starlette deprecation warning
```

The quality-review RED run for access snapshots and lock clauses produced:

```text
7 failed, 33 passed, 1 existing warning
```

After adding access snapshots and row locks:

```text
52 passed, 1 existing Starlette deprecation warning
```

The degraded Web behavior was also written RED first:

```text
2 failed, 2 passed
```

After suppressing invalid links/install:

```text
2 test files passed, 5 tests passed
```

The delete-time access refresh was added after a final review exposed a stale
snapshot case. Its schema test failed RED first:

```text
1 failed
```

After adding the `BEFORE DELETE` trigger:

```text
5 passed
```

The final quality review then identified missing leading indexes on the
trigger/FK lookup columns. Exact schema-policy tests failed RED:

```text
2 failed, 6 passed
```

After adding the three partial indexes:

```text
8 passed
```

## Real PostgreSQL lifecycle evidence

A fresh named `postgres:16-alpine` container was exposed only on
`127.0.0.1:55434`. The full bundled and local migration chain was applied:

```powershell
$env:SKILLHUB_DATABASE_URL = `
  'postgresql+asyncpg://skillhub:<redacted>@127.0.0.1:55434/skillhub'
.venv\Scripts\python.exe -m app.migrations upgrade
```

Migration result:

```text
skillhub_flyway_v43_baseline
```

The verification then used the real SQLAlchemy engine and the existing
application functions `hard_delete_skill`, `delete_skill_version`,
`find_replaceable_version`, `cleanup_replaceable_version`, `get_collection`,
and `resolve_collection`.

| Scenario | Observed result |
| --- | --- |
| Hard-delete a Skill referenced by a published collection and import candidate | Delete returned `deleted: true`; both collection and import Skill/version IDs became `NULL` |
| Read the published collection after hard delete | Historical namespace, slug `hard-delete-member`, and version `1.0.0` remained; both response IDs were `null` |
| Resolve the deleted pinned member | `409 error.collection.resolve.degraded`; never an FK error or `500` |
| Delete an import-created `SCAN_FAILED` version while another published version remains | Existing version-delete path succeeded; candidate `skill_id` remained and `skill_version_id` became `NULL` |
| Clean up an import-created `UPLOADED` version for publish replacement | Existing replacement cleanup succeeded; candidate `skill_id` remained and `skill_version_id` became `NULL` |
| Inspect import evidence after all three deletes | Source path, target slug/version, 40-character commit SHA, 64-character archive digest, and upstream URL all remained unchanged |

The hard-delete historical member evidence was:

```json
{
  "skillId": null,
  "skillVersionId": null,
  "namespace": "task2-team",
  "skillSlug": "hard-delete-member",
  "version": "1.0.0",
  "position": 0,
  "note": null
}
```

The resolve evidence was:

```json
{
  "status": 409,
  "detail": "error.collection.resolve.degraded"
}
```

The exact disposable container and its anonymous data volume were removed
after verification. Docker inspection confirmed that neither remained.

## Real PostgreSQL concurrency evidence

A second fresh PostgreSQL 16 database applied the final migration shape,
including owner/visibility snapshots. Two independent SQLAlchemy connections
then exercised the real collection repository and core hard-delete path.

| Race | Lock order and observed result |
| --- | --- |
| Resolve member reference, then concurrent hard delete | `FOR KEY SHARE OF s, sv` held the target rows; hard delete waited `0.353s`; member insert committed; delete then succeeded and nulled both references |
| Validate/publish a draft, then concurrent hard delete | `FOR UPDATE OF member` held the validated member row; hard delete waited `0.357s`; publish committed as `PUBLISHED 1.0.0`; delete then succeeded and nulled both references |

Both resulting historical rows retained:

```json
{
  "skillOwnerIdSnapshot": "owner-task2-lock",
  "skillVisibilitySnapshot": "NAMESPACE_ONLY"
}
```

An anonymous read of the deleted `NAMESPACE_ONLY` collection returned
`error.collection.notFound`; the namespace owner still received the historical
member with nullable IDs. This proves deletion history does not widen the
original visibility boundary.

The exact second disposable container and anonymous volume were also removed
and confirmed absent.

## Final access-boundary PostgreSQL evidence

A third fresh PostgreSQL 16 database applied the final migration shape. Two
published collection members were initially snapshotted as `PUBLIC`; their
live Skills were then changed to `NAMESPACE_ONLY` and `PRIVATE` respectively
before the existing `hard_delete_skill` path ran.

The delete-time trigger retained the final live policy:

```text
access-namespace-collection|NULL|NULL|owner-task2-access|NAMESPACE_ONLY
access-private-collection|NULL|NULL|owner-task2-access|PRIVATE
```

Application-level reads after deletion produced:

```json
{
  "namespaceAnonymous": {"status": "error.collection.notFound"},
  "namespaceMember": {"status": "visible", "skillId": null},
  "privateAnonymous": {"status": "error.collection.notFound"},
  "privateOwner": {"status": "visible", "skillId": null}
}
```

This verifies that post-publication visibility changes cannot be widened by
hard deletion. The exact third disposable container and anonymous volume were
removed and confirmed absent.

## Lifecycle-index PostgreSQL evidence

A fourth fresh PostgreSQL 16 database applied the complete migration chain.
With sequential scans disabled to verify indexability, real PostgreSQL
`EXPLAIN` plans selected:

| Lifecycle predicate | Observed plan |
| --- | --- |
| Collection trigger/FK `WHERE skill_id = 42` | `Index Scan using idx_local_collection_member_skill_id` |
| Import Skill FK `WHERE skill_id = 42` | `Index Scan using idx_local_repository_import_candidate_skill_id` |
| Import version FK `WHERE skill_version_id = 84` | `Index Scan using idx_local_repository_import_candidate_skill_version_id` |

The exact fourth disposable container and anonymous volume were removed and
confirmed absent.

## Core-function review

The implementation does not add collection/import cleanup calls to the core
Skill lifecycle. PostgreSQL performs only the intended reference nulling while
the existing lifecycle transaction order and audit/storage behavior remain
unchanged.

The following real cases were considered in addition to automated tests:

- full Skill hard delete;
- deletion of a non-published version while the Skill survives;
- retry replacement of an uploaded version;
- anonymous browse of fully deleted published history;
- anonymous/member/owner browse of deleted `PUBLIC`, `NAMESPACE_ONLY`, and
  `PRIVATE` history;
- anonymous browse of a partial reference whose surviving Skill is public;
- rejection when the surviving Skill is private, archived, or hidden;
- resolve before any file/fingerprint work;
- preservation of GitLab/import provenance after target deletion.
- concurrent hard delete during member insertion and collection publish.
- a Skill changing from public to namespace/private before hard deletion;
- indexability of trigger and FK nulling predicates at evidence-table scale.

## Final verification and review disposition

Final backend focused gate:

```text
102 passed, 2 warnings in 8.40s
```

Final complete backend regression:

```text
1060 passed, 2 warnings in 179.42s
```

The warnings are the existing Starlette `TestClient` deprecation and the
intentional duplicate ZIP-name fixture warning.

Final Web checks used the already-installed project binaries because the
ambient pnpm 11 wrapper does not match the repository's declared pnpm 10.33
and attempted a non-interactive modules reinstall:

```text
vitest: 2 files passed, 5 tests passed
tsc --noEmit: exit 0
focused eslint: exit 0
```

`scripts/sql_inventory.py` and `git diff --check` both exited `0`. The
independent specification review passed after the partial-reference policy
repair. The independent quality review passed after the delete-time access
refresh and lifecycle-index repairs; no Important or Critical Task 2 finding
remains.

No commit, stage, push, deployment, feature enablement, or real GitLab/Nexus
operation was performed.

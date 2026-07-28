# Skill Collections Remediation Task 1: Migration Safety

## Result

Task 1 is complete. Python schema upgrade and stamp operations now acquire one
PostgreSQL transaction-scoped advisory lock using explicit `READ COMMITTED`.
Bundled baseline SQL, baseline stamping, local migration SQL, and each local
tracking insert execute within the protected upgrade transaction. Direct local
migration callers use the same boundary.

Existing command semantics remain intact:

- `upgrade` applies bundled compatibility/baseline SQL and local migrations;
- `stamp` remains compatibility-and-baseline-only and does not apply local
  feature migrations;
- read-only `status` does not acquire the migration transaction or advisory
  lock.

No Task 2 code, schema definition, route, Web, CLI, scanner, or deployment
behavior was changed.

## Files changed

- `server-python/app/migrations.py`
- `server-python/tests/test_schema_migration_baseline.py`
- `docs/backend-python-maintenance/plans/2026-07-27-skill-collections-code-review-remediation.md`
- `docs/backend-python-maintenance/results/2026-07-27-skill-collections-remediation-task1-migration-safety.md`

## TDD evidence

Initial focused baseline before Task 1:

```text
12 passed in 0.17s
```

First RED cycle:

```text
3 failed, 12 passed
```

The failures proved that fresh upgrade started with `to_regclass`, direct local
application started with DDL, and an injected failure had no transaction
rollback event.

First GREEN cycle:

```text
15 passed
```

Core-semantics review then found that stamp had accidentally started applying
local migrations. The added regression produced:

```text
1 failed, 14 passed
```

Removing only the extra local-migration call restored:

```text
15 passed
```

Code-quality review found two production cases hidden by default local
configuration:

1. an inherited `REPEATABLE READ` or `SERIALIZABLE` transaction could retain a
   pre-lock snapshot and miss migration rows committed by the first replica;
2. V42's `SET LOCAL lock_timeout = '30s'` could leak into later migration files
   after moving all files into one operation transaction.

The isolation regression produced:

```text
2 failed, 14 passed
```

The per-file `lock_timeout` restoration regression produced:

```text
1 failed, 16 passed
```

The final focused verification was:

```powershell
server-python\.venv\Scripts\python.exe -m pytest `
  tests/test_schema_migration_baseline.py -q
```

```text
17 passed
```

The rollback unit test now injects failure on the tracking `INSERT` after the
test DDL has executed. It verifies the DDL and tracking write were attempted,
the transaction rolled back, and neither appears in the fake committed set.

## Independent review

The specification reviewer confirmed:

- explicit `READ COMMITTED` and advisory lock;
- local migration SQL and tracking write share one operation transaction;
- public direct-local application is protected without nesting inside upgrade;
- stamp remains locked but baseline-only;
- status remains unlocked;
- no Task 2 scope entered the diff.

The code-quality reviewer reported no remaining Critical or Important issues
after the isolation, lock-timeout, rollback, and stamp fixes. The final minor
test-name mismatch was corrected before full verification.

## Real PostgreSQL evidence

An isolated `postgres:16-alpine` container named
`skillhub-migration-verify` used database
`skillhub_migration_verify` on host port `55432`. The database default was
deliberately changed to:

```text
repeatable read
```

This ensured the test exercised the explicit operation isolation rather than
passing only because of PostgreSQL's normal default.

Two simultaneous fresh-database commands both returned:

```text
ExitCode: 0
Output: skillhub_flyway_v43_baseline
```

Afterward:

```text
duplicate local migration identifiers: 0 rows
local migration count: 3
alembic version: skillhub_flyway_v43_baseline
user_account.system_account type: boolean
```

A third sequential upgrade returned exit code `0`. Two simultaneous upgrades
against the now-existing database also both returned exit code `0`, proving the
tracking-row read does not reuse a stale pre-lock snapshot.

The real rollback probe used a temporary local migration that successfully
created `rollback_probe`, followed by a 65-character identifier that exceeded
`local_schema_migration.identifier VARCHAR(64)`. The tracking insert failed and
the post-rollback query returned:

```text
rollback_probe table: NULL
tracking record: NULL
```

The final database check still returned exactly three unique local migration
records and no `rollback_probe` table.

The disposable container and its anonymous PostgreSQL data volume were removed
after verification. They contained only this Task 1 test database and are not
recoverable.

## Full backend regression

```powershell
server-python\.venv\Scripts\python.exe -m pytest tests -q
```

```text
1045 passed, 2 warnings in 95.21s
```

The warnings were the existing Starlette/httpx deprecation warning and the
intentional duplicate ZIP-entry warning in the repository archive test.

```powershell
server-python\.venv\Scripts\python.exe scripts\sql_inventory.py
```

The command exited `0`; no new SQL ownership/category violation was reported.

The transaction-incompatible SQL scan found no bundled or local use of
`CREATE INDEX CONCURRENTLY`, `VACUUM`, `CREATE DATABASE`,
`ALTER TYPE ... ADD VALUE`, explicit `BEGIN`, or explicit `COMMIT`.

## Core-function impact assessment

- Fresh database startup: serialized and atomic across replicas.
- Existing database startup: serialized; local tracking rows are observed after
  lock acquisition.
- V42 compatibility: its 30-second local lock timeout is restored before V43
  and local extensions.
- Stamp: existing baseline-only semantics preserved.
- Status: existing read-only/no-lock semantics preserved.
- Schema: Task 1 adds no tables, columns, constraints, or data migration.
- Application APIs, authentication, Skill lifecycle, publish/scanner, Web,
  CLI, and deployment manifests: untouched by Task 1.

Task 2 must not start unless this result and the Task 1 focused diff remain
unchanged.

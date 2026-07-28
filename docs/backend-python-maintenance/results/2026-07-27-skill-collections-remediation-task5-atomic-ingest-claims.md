# Skill Collections Remediation Task 5 Result

Date: 2026-07-27

Task: Add atomic repository-ingest claims and owned result transitions.

## Scope and boundary

This task changes only the GitLab repository-import ingest state machine,
repository SQL, its unreleased local schema, and focused API/service tests.
Authorization remains before the claim. Selection syntax, duplicate candidate
IDs, and candidate existence are validated before the claim so client errors
do not strand an import.

The general Skill publish transaction, scanner, collection, CLI, Web,
deployment, and existing repository-preview/update-check contracts remain
unchanged. No automatic retry, timeout reaper, background worker, or operator
recovery endpoint was added. Task 6 Web runtime substitution was not started.

## Result

- `local_repository_import.ingest_operation_id` stores a UUID hex operation
  ID while an ingest owns the import.
- `claim_ingest` performs one conditional PostgreSQL update:

  ```sql
  UPDATE local_repository_import
  SET state = 'INGESTING',
      ingest_operation_id = :operation_id
  WHERE id = :import_id
    AND state = 'PREVIEW_READY'
  RETURNING id
  ```

- Exactly one concurrent request can claim a `PREVIEW_READY` import. A
  competing request receives
  `409 error.repositoryImport.ingest.inProgress` and cannot enter the
  publisher.
- A successful claim and its
  `REPOSITORY_IMPORT_INGEST_STARTED` audit are in the same transaction. The
  audit records the actual ingest actor and request metadata, not only the
  earlier preview creator. Audit failure rolls back the claim.
- Candidate selection and result writes require the parent import to remain
  `INGESTING` with the same operation ID. A zero-row `RETURNING` result becomes
  `409 error.repositoryImport.ingest.ownershipLost`.
- `COMPLETED` and `PARTIAL` terminal writes require the same operation
  ownership and clear the operation ID in the same transaction as the
  terminal audit.
- Only the explicit `RepositoryImportCandidatePublishError`, currently emitted
  for deterministic package-validation failure before publishing, becomes a
  candidate `FAILED` result and an import `PARTIAL`.
- Unknown publisher exceptions are not classified as candidate failures. This
  includes the dangerous case where Skill publishing committed and a later
  notification failed. Such errors propagate while the import stays
  `INGESTING`, the candidate stays `SELECTED`, and the operation ID remains for
  operator reconciliation.
- Archive changes or other unexpected failures after the claim likewise leave
  the import `INGESTING`.
- A terminal `COMPLETED` or `PARTIAL` import rejects later ingest attempts with
  `409 error.repositoryImport.ingest.notAvailable`; it never republishes.

## TDD evidence

The initial RED suite proved the previous implementation had no schema column,
atomic claim, or operation-owned transitions, and allowed terminal retries:

```text
7 failed, 11 passed in 1.11s
```

The first implementation reached:

```text
19 passed in 1.57s
```

Independent review then reproduced two safety gaps:

- the successful claim had no audit for the actual ingest actor;
- a broad `except Exception` misclassified programming, infrastructure, and
  post-commit notification failures as candidate failures and terminalized
  them as `PARTIAL`.

New RED tests first failed because the typed candidate failure did not exist
and the claim accepted no audit context. After the narrow fix:

```text
Repository/service/publish focused: 18 passed
Repository-import schema/API focused: 35 passed, 1 warning
Related repository-import/publish/collection transactions: 115 passed,
2 warnings
```

The warnings are the existing Starlette `TestClient` deprecation and the
intentional duplicate ZIP-name fixture.

## Real PostgreSQL and concurrent API evidence

A disposable PostgreSQL 16 database applied the complete bundled and local
migration chain. Two simultaneous local ASGI requests targeted the same
preview while the first request paused at the publish boundary:

```json
{
  "firstStatus": 200,
  "firstState": "PARTIAL",
  "competingStatus": 409,
  "competingDetail": "error.repositoryImport.ingest.inProgress",
  "publishCalls": 1,
  "databaseState": "PARTIAL",
  "operationIdAfterTerminal": null
}
```

The database contained exactly one start audit and one terminal ingest audit,
both for the actual ingest actor. A later terminal retry returned
`409 error.repositoryImport.ingest.notAvailable` without another publish.

A second import simulated a publisher exception after an external publish had
already committed:

```json
{
  "firstStatus": 400,
  "firstDetail": "error.repositoryImport.failed",
  "retryStatus": 409,
  "retryDetail": "error.repositoryImport.ingest.inProgress",
  "publishCalls": 1,
  "databaseState": "INGESTING",
  "candidateState": "SELECTED",
  "operationIdRetained": true,
  "audits": ["REPOSITORY_IMPORT_INGEST_STARTED"]
}
```

This proves the uncertain result is not overwritten as `FAILED/PARTIAL` and is
not automatically republished. The exact disposable container and its
anonymous volume were removed after verification.

## Core-regression verification

The SQL inventory check passed with repository SQL remaining in the repository
module. The final complete Python backend result is recorded after the last
review fix:

```text
1097 passed, 2 warnings in 100.00s
```

Task 5 did not change frontend, CLI, deployment, or generated OpenAPI response
shapes, so their already-green Task 4 full gates were not rerun for this
backend-only state-machine change.

## Review disposition

The first independent specification review found one P1 issue: a broad
publisher exception handler incorrectly terminalized unknown failures. The
first independent code-quality review found the same post-commit orphan risk
and the missing claim audit.

The implementation now uses a narrow explicit candidate-failure type and an
audit-atomic claim. Both independent reviewers returned `PASS` after
reinspection and fresh focused test runs. They found no remaining auth, Skill
publish, scanner, collection, or other core-function regression.

No commit, stage, push, deployment, feature enablement, or real GitLab/Nexus
operation was performed.

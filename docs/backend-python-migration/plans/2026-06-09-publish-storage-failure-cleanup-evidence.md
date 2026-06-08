# Publish Storage Failure Cleanup Evidence Plan

## Summary

Prove the Python publish write path does not leave dangling database rows when local storage write
fails after the publish prepare step has allocated a skill/version id.

This milestone addresses the transaction parity risk raised during review. The current Python
orchestration executes prepare, storage write, finalize, and side effects inside one
`engine.begin()` transaction. Therefore the intended cleanup mechanism is transaction rollback, not
a separate best-effort delete pass.

## Route Ownership

No route ownership changes.

- `POST /api/cli/v1/skills/{namespace}/publish` remains Java-owned through Vite/proxy.
- Direct Python backend on port `8081` gains stronger regression evidence for storage failure
  rollback.
- Route registry remains unchanged.

## Scope

Allowed:

- `server-python/app/publish/`
- publish orchestration tests
- Windows hybrid verification script
- `docs/backend-python-migration/`

Forbidden:

- Any changes under `server/`.
- Vite proxy ownership changes.
- Portal publish write route ownership.
- Scanner result processing.
- Object storage compensation behavior beyond database rollback evidence.

## Java Parity Checklist

Reference:

- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillPublishService.java`

Required behavior:

- If storage write fails during publish, no committed dangling `skill_version` row remains.
- No `skill_file`, pending `review_task`, or `security_audit` rows remain for the failed version.
- Vite/proxy publish write route remains Java-owned until route ownership is explicitly moved.

Current Python approach:

- Keep prepare, storage write, finalize, and side effects in the same SQLAlchemy transaction.
- Let transaction rollback handle database cleanup when storage write raises.
- Add tests and live verification to prevent future refactors from splitting this path without an
  explicit cleanup design.

## Implementation Plan

1. Add an orchestration test that injects a storage writer failure after version allocation and
   asserts finalize/side effects are not reached.
2. Add a Windows live gate action that starts hybrid services with an invalid Python storage base,
   calls direct Python CLI publish, and verifies no skill/version/review/audit/file rows remain.
3. Keep proxy ownership check proving Vite publish write still reaches Java.
4. Record the result and update `migration-sequence-plan.md`.

## Acceptance Criteria

- `uv run pytest tests/test_publish_orchestration.py tests/test_publish_http_validate.py tests/test_hybrid_makefile.py -q` passes.
- Windows live gate `verify-publish-storage-failure-cleanup-smoke` passes.
- `git diff --name-only -- server` is empty.
- Result document records tests, live evidence, risks, and follow-up.

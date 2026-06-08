# Publish Pending Review Auto-Withdraw Foundation Plan

## Summary

Add Java-compatible pending-review auto-withdraw behavior to Python publish orchestration.

Java behavior before creating a new version for an existing skill:

- Find existing `PENDING_REVIEW` versions for the same skill.
- Delete their pending `review_task` rows.
- Move those versions back to `UPLOADED`.

This milestone wires that behavior into direct Python CLI publish. It does not move route
ownership.

## Route Ownership

No route ownership changes.

- `POST /api/cli/v1/skills/{namespace}/publish` remains Java-owned through Vite/proxy.
- Direct Python backend on port `8081` gains pending-review auto-withdraw behavior.
- Route registry remains unchanged.

## Scope

Allowed:

- `server-python/app/publish/`
- `server-python/app/api/publish.py`
- publish tests and hybrid gate updates
- `docs/backend-python-migration/`

Forbidden:

- Any changes under `server/`.
- Vite proxy ownership changes.
- Scanner result/consumer processing.
- Portal publish write route ownership.

## Java Parity Checklist

Reference:

- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillPublishService.java`

Required behavior:

- Auto-withdraw runs for the same skill before same-version replacement and new version insert.
- Only `PENDING_REVIEW` versions are moved to `UPLOADED`.
- Pending review task rows for those versions are deleted.
- Published versions are untouched.

## Implementation Plan

1. Add failing helper/orchestration test for auto-withdraw SQL sequencing.
2. Implement focused helper for auto-withdraw by skill id.
3. Wire orchestration to run after existing skill is identified and before replacement/new version.
4. Add Windows live gate proving direct Python publish withdraws an existing pending review version.
5. Keep route ownership unchanged.

## Acceptance Criteria

- `uv run pytest tests/test_publish_auto_withdraw.py tests/test_publish_orchestration.py tests/test_publish_http_validate.py tests/test_hybrid_makefile.py -q` passes.
- Windows live gate passes for direct Python pending-review auto-withdraw.
- `git diff --name-only -- server` is empty.
- Result document records tests, live evidence, risks, and follow-up.

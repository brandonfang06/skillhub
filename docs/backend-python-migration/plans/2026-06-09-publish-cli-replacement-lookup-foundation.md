# Publish CLI Replacement Lookup Foundation Plan

## Summary

Add route-level replacement lookup for the direct Python CLI publish write route without moving
route ownership.

Java behavior:

- Existing same-skill same-version `PUBLISHED` blocks publishing.
- Existing same-skill same-version non-published version is replaceable.
- Replacement cleanup removes pending review task, file rows, soft-deletes security audit rows,
  deletes the old version row, and deletes old storage after commit.

Existing Python already has the replacement cleanup and orchestration foundation. This milestone
wires direct CLI publish to find the replaceable version before creating the replacement.

## Route Ownership

No route ownership changes.

- `POST /api/cli/v1/skills/{namespace}/publish` remains Java-owned through Vite/proxy.
- Direct Python backend on port `8081` gains replacement lookup behavior.
- Route registry remains unchanged.

## Scope

Allowed:

- `server-python/app/publish/replacement.py`
- `server-python/app/api/publish.py`
- publish tests and hybrid gate updates
- `docs/backend-python-migration/`

Forbidden:

- Any changes under `server/`.
- Vite proxy ownership changes.
- Pending-review auto-withdraw.
- Full scanner result/consumer processing.

## Java Parity Checklist

Reference:

- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillPublishService.java`

Required behavior:

- Find existing skill by `namespace_id`, `slug`, and `owner_id`.
- Find existing version by `skill_id` and `version`.
- If existing version is `PUBLISHED`, reject through existing dry-run conflict path.
- If existing version is not `PUBLISHED`, pass it into replacement cleanup.
- Include `latest_version_id` and current `publisher_id` so cleanup updates audit fields.

## Implementation Plan

1. Add failing route test proving a replacement reader result is attached to `PublishWriteInput`.
2. Add failing replacement repository test for SQL shape and `ReplaceableVersion` mapping.
3. Implement lookup helper/repository.
4. Wire direct CLI publish route to use injected replacement reader or DB lookup.
5. Add Windows live gate for direct repeat publish replacement through Python.
6. Keep route ownership unchanged.

## Acceptance Criteria

- `uv run pytest tests/test_publish_replacement.py tests/test_publish_http_validate.py tests/test_publish_orchestration.py tests/test_hybrid_makefile.py -q` passes.
- Windows live gate passes for direct Python repeat publish replacement.
- `git diff --name-only -- server` is empty.
- Result document records tests, live evidence, risks, and follow-up.

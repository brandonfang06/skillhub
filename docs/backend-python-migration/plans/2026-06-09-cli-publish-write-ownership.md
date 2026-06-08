# CLI Publish Write Ownership Plan

## Summary

Move Vite/local route ownership for `POST /api/cli/v1/skills/{namespace}/publish` from Java to
Python after the completed publish foundations:

- direct Python CLI publish write
- scanner handoff
- same-version replacement lookup
- pending-review auto-withdraw
- storage-failure database rollback evidence

Because the project is pre-launch, this milestone intentionally moves the CLI publish write route
once the cohesive Python vertical slice has live evidence.

## Route Ownership

Change:

- `POST /api/cli/v1/skills/{namespace}/publish`: `java` -> `python`

Unchanged:

- `POST /api/cli/v1/skills/{namespace}/publish/validate`: `python`
- `POST /api/v1/skills`: `java`
- `POST /api/v1/publish`: `java`
- `POST /api/v1/skills/{namespace}/publish`: `java`
- `POST /api/web/skills/{namespace}/publish`: `java`
- `/oauth2/**`: `java`

## Scope

Allowed:

- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `server-python/tests/test_hybrid_makefile.py`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- milestone plan/result docs

Forbidden:

- Any changes under `server/`.
- Portal/web publish route ownership.
- OAuth/session/API-token migration.
- Scanner result consumer implementation.

## Java Parity Checklist

Reference:

- `SkillPublishService`
- CLI publish controller/adapter references under Java app/auth modules.

Covered by previous milestones:

- package extraction and validation parity
- dry-run validation model
- local storage write keys and bundle shape
- DB write transaction and rollback behavior
- review task/security audit/scan task side effects
- same-version replacement
- pending-review auto-withdraw

This milestone adds:

- Vite proxy ownership for CLI publish write.
- Repeated publish live matrix through the Vite proxy.
- Explicit scanner result boundary documentation.

Scanner result boundary:

- Scanner handoff is covered by Python Redis stream publication.
- Scanner result consumption, retry/reclaim, and final `security_audit` verdict updates remain a
  separate scanner-processing milestone. They do not block moving CLI publish write ownership for
  pre-launch local development because the current Java/Python comparison already treats scanner
  handoff as asynchronous.

## Implementation Plan

1. Add `POST /api/cli/v1/skills/{namespace}/publish` Vite proxy route to Python.
2. Update proxy tests so CLI publish write maps to `8081` while portal/root publish routes remain
   `8080`.
3. Update route registry and migration sequence plan.
4. Add a Windows live gate that publishes through the Vite proxy and verifies:
   - first publish succeeds through proxy
   - same-version replacement through proxy leaves one version
   - new-version publish through proxy auto-withdraws the earlier pending review version
   - Java-owned portal/root publish routes still match Java status
   - Playwright smoke passes
5. Record result and commit/push.

## Acceptance Criteria

- `cd web; corepack pnpm vitest run vite.config.test.ts` passes.
- `cd server-python; uv run pytest tests/test_hybrid_makefile.py tests/test_publish_http_validate.py -q` passes.
- Windows live gate `verify-cli-publish-write-ownership-smoke` passes.
- `git diff --name-only -- server` is empty.

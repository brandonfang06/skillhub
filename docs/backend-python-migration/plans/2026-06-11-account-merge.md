# Account Merge API Migration Plan

Date: 2026-06-11

## Scope

Migrate the account merge workflow from Java to Python for the local mock-user development boundary:

| Method | Route | New owner |
|---|---|---|
| POST | `/api/v1/account/merge/initiate` | Python |
| POST | `/api/v1/account/merge/verify` | Python |
| POST | `/api/v1/account/merge/confirm` | Python |

Out of scope: OAuth redirect/login, OAuth device flow, Spring Session establishment, bearer-token authentication filters, token-scope enforcement, and any `server/` edits.

## Java Parity Contract

Reference behavior is `AccountMergeController` plus `AccountMergeService`:

- All three routes require an authenticated primary user. During migration, Python keeps the existing `X-Mock-User-Id` bridge and returns `error.auth.required` for missing/unknown users.
- `initiate` resolves the secondary user from either:
  - local username, case-insensitive after trim; or
  - identity binding identifier in `{provider}:{subject}` format.
- `initiate` rejects:
  - blank identifier with `error.auth.merge.identifierRequired`;
  - malformed provider identifier with `error.auth.merge.identifierInvalid`;
  - missing secondary user with `error.auth.merge.secondaryNotFound`;
  - inactive primary with `error.auth.merge.primaryNotActive`;
  - same primary/secondary user with `error.auth.merge.sameAccount`;
  - inactive secondary with `error.auth.merge.secondaryNotActive`;
  - existing pending request for the secondary user with `error.auth.merge.pendingExists`;
  - primary and secondary both having local credentials with `error.auth.merge.localCredentialConflict`.
- `initiate` creates a pending `account_merge_request`, stores a BCrypt-compatible verification token hash, returns the raw token, and sets expiration to now + 30 minutes.
- `verify` requires a pending request owned by the primary user, a non-expired token, and a token hash match. It updates status to `VERIFIED`.
- `confirm` requires a verified request owned by the primary user, re-validates active primary/secondary users, then atomically:
  - moves secondary `identity_binding` rows to the primary user;
  - moves secondary `api_token` rows to the primary user and rewrites `subject_id` when `subject_type = 'USER'`;
  - merges platform roles without duplicates and deletes secondary role bindings;
  - merges namespace memberships, keeping the higher role when primary and secondary share a namespace;
  - moves secondary local credential only when the primary has none;
  - fills primary email from secondary only when primary email is blank;
  - marks secondary user `MERGED` with `merged_to_user_id = primary`;
  - marks the merge request `COMPLETED`, sets `completed_at`, and clears `verification_token`.

## Data Access Strategy

Use `sqlalchemy.text` and native SQL, consistent with the current Python migration data-access policy. Keep all account merge DB writes inside one SQLAlchemy transaction per route handler. Avoid SQLAlchemy ORM models during the migration phase.

## Files Allowed To Change

- `server-python/app/auth/account_merge.py`
- `server-python/app/api/account_merge.py`
- `server-python/app/main.py`
- `server-python/tests/test_account_merge.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/**`

Forbidden: any file under `server/`.

## Verification Plan

1. Python unit tests:
   - route envelopes for initiate/verify/confirm;
   - local username and provider-subject resolution;
   - pending/conflict/error behavior;
   - confirm side effects for bindings, tokens, roles, namespace memberships, credentials, primary email, secondary status, and request completion.
2. Vite proxy tests:
   - the three account merge POST routes route to `localhost:8081`;
   - unrelated OAuth routes remain Java-owned.
3. Windows live gate:
   - seed isolated Java and Python fixtures;
   - compare Java and Python initiate/verify/confirm envelopes after normalizing volatile id/token/timestamps;
   - verify proxy routes to Python;
   - assert DB side effects after confirm.
4. Safety checks:
   - `git diff --name-only -- server` must be empty;
   - `git diff --check` must pass.

## Milestone Exit Criteria

- `cd server-python; uv run pytest tests/test_account_merge.py tests/test_hybrid_makefile.py -q` passes.
- `cd web; npm run test -- vite.config.test.ts --run` passes.
- `./scripts/dev-hybrid.ps1 -Action verify-account-merge-smoke` passes.
- `route-registry.md`, this plan, `migration-sequence-plan.md`, and a result document are updated.
- Commit and push to `dev`.

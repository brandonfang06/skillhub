# Account Merge API Migration Result

Date: 2026-06-11

## Routes Changed

| Method | Route | Owner before | Owner after |
|---|---|---|---|
| POST | `/api/v1/account/merge/initiate` | Java | Python |
| POST | `/api/v1/account/merge/verify` | Java | Python |
| POST | `/api/v1/account/merge/confirm` | Java | Python |

## Implementation Summary

- Added Python account merge service logic using `sqlalchemy.text` native SQL.
- Added FastAPI routes for initiate, verify, and confirm.
- Kept each route in a single SQLAlchemy transaction.
- Preserved Java secondary resolution rules for local username and `{provider}:{subject}` identity identifiers.
- Preserved Java error keys/statuses for pending requests, invalid identifiers, inactive users, same-account merge, invalid/expired token, and local credential conflicts.
- Preserved BCrypt-compatible verification token storage and verification.
- Preserved confirm side effects:
  - move `identity_binding`;
  - move `api_token` and rewrite `subject_id` for `USER` tokens;
  - merge platform roles without duplicates;
  - merge namespace memberships and keep the higher role;
  - move secondary local credential when primary has none;
  - fill primary email from secondary when primary email is blank;
  - mark secondary user `MERGED`;
  - complete the merge request and clear `verification_token`.
- Added method-aware Vite proxy ownership for only the three account merge `POST` routes.

## Verification

Passed:

- `cd server-python; uv run pytest tests/test_account_merge.py tests/test_hybrid_makefile.py -q`
  - `12 passed`
- `cd web; npm run test -- vite.config.test.ts --run`
  - `45 passed`
- `./scripts/dev-hybrid.ps1 -Action verify-account-merge-smoke`
  - Python/unit gate: `12 passed`
  - Vite proxy gate: `45 passed`
  - Java/Python/proxy live comparison:
    - `initiateMatches = true`
    - `verifyMatches = true`
    - `confirmMatches = true`
    - `allEvidencePassed = true`
  - Playwright smoke: `6 passed`
- `git diff --name-only -- server`
  - no output
- `git diff --check`
  - no whitespace errors

## Live Gate Notes

- The live gate compares stable `code` and `data` fields while excluding `msg` because Java live responses apply i18n translation and the Python migration layer currently returns message keys, matching the existing migration convention.
- DB evidence verifies secondary merge status, primary email fill, identity binding movement, API token movement, local credential movement, role merge, namespace membership promotion/move, and merge request completion.
- During live gate development, fixture SQL caught three environment/parity details:
  - PL/pgSQL variable names must avoid table column ambiguity.
  - Use `jsonb_build_array(...)` rather than JSON string literals inside the PowerShell -> psql path.
  - `USER` is a fallback platform role and may not exist as a row in `role`; fixture role merge must use an actual role such as `AUDITOR`.

## Risks And Follow-Up

- OAuth account merge entrypoints/callbacks remain Java-owned.
- Spring Session establishment, device flow, bearer-token authentication filters, token-scope enforcement, and final proxy cleanup remain deferred.
- Python response `msg` localization remains a known migration-layer convention until the final localization strategy is decided.

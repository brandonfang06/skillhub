# Test Fixture Cleanup Result

Date: 2026-06-12

Milestone: Post Python Cutover Hardening Milestone 6

## Scope

This milestone reduced duplicated fake database and row-builder code in large Python backend tests. It did not change production runtime behavior.

## Changes

- Added `server-python/tests/support/fake_db.py` with shared:
  - `FakeResult`
  - `FakeTransaction`
  - `FakeEngine`
  - `normalized_sql`
- Added `server-python/tests/support/builders.py` with shared row/auth builders:
  - `auth_user`
  - `bearer_user`
  - `user_row`
  - `namespace_row`
  - `namespace_member_row`
  - `skill_row`
  - `skill_version_row`
  - `review_task_row`
  - `promotion_request_row`
  - `token_row`
- Added `server-python/tests/test_support_fake_db.py` to cover the shared support helpers directly.
- Converted the specified large tests one at a time:
  - `test_api_tokens.py`
  - `test_namespace_member_mutation.py`
  - `test_promotion_write.py`
  - `test_skill_hard_delete.py`
  - `test_account_merge.py`
  - `test_publish_http_validate.py`
- Kept each test file's fake connection state machine local to the test file; only generic result/engine and row/auth builders moved to shared support.

## Line Counts

| File | Before | After | Delta |
| --- | ---: | ---: | ---: |
| `server-python/tests/test_publish_http_validate.py` | 838 | 832 | -6 |
| `server-python/tests/test_skill_hard_delete.py` | 479 | 439 | -40 |
| `server-python/tests/test_account_merge.py` | 463 | 423 | -40 |
| `server-python/tests/test_namespace_member_mutation.py` | 450 | 367 | -83 |
| `server-python/tests/test_promotion_write.py` | 437 | 399 | -38 |
| `server-python/tests/test_api_tokens.py` | 409 | 316 | -93 |

Total across converted files: 3076 lines before, 2776 lines after, net -300 lines.

## Verification

- `cd server-python; uv run pytest tests/test_support_fake_db.py -q`
  - Result: `4 passed`
- `cd server-python; uv run pytest tests/test_api_tokens.py -q`
  - Result: `8 passed, 1 warning`
- `cd server-python; uv run pytest tests/test_namespace_member_mutation.py -q`
  - Result: `9 passed, 1 warning`
- `cd server-python; uv run pytest tests/test_promotion_write.py -q`
  - Result: `11 passed, 1 warning`
- `cd server-python; uv run pytest tests/test_skill_hard_delete.py -q`
  - Result: `7 passed, 1 warning`
- `cd server-python; uv run pytest tests/test_account_merge.py -q`
  - Result: `6 passed, 1 warning`
- `cd server-python; uv run pytest tests/test_publish_http_validate.py -q`
  - Result: `14 passed, 1 warning`
- `cd server-python; uv run pytest tests/test_support_fake_db.py tests/test_publish_http_validate.py tests/test_skill_hard_delete.py tests/test_account_merge.py tests/test_namespace_member_mutation.py tests/test_promotion_write.py tests/test_api_tokens.py -q`
  - Result: `59 passed, 1 warning`
- `cd server-python; uv run pytest tests -q`
  - Result: `727 passed, 1 warning`
- `git diff --check`
  - Result: no whitespace errors; PowerShell reported only CRLF working-copy warnings.

## Residual Risk

- Fake connection SQL branch logic remains local to each test file. That is intentional: those branches encode file-specific workflow expectations and should not become a generic test framework yet.
- Additional tests outside the converted list still define local fake result helpers. Future cleanup should convert them opportunistically when those files are already being touched.

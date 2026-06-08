# Publish CLI Write Direct Route Foundation

## Summary

Add a direct Python implementation for:

- `POST /api/cli/v1/skills/{namespace}/publish`

This milestone does not move Vite proxy ownership. The route remains Java-owned from the frontend
and CLI-through-proxy perspective until replacement, pending-review withdrawal, scanner behavior,
and repeated publish parity have full live coverage.

## Route Ownership

Before:

- `POST /api/cli/v1/skills/{namespace}/publish` -> Java

After:

- Direct Python backend has an implementation on port `8081`.
- Vite proxy still sends `POST /api/cli/v1/skills/{namespace}/publish` to Java on port `8080`.
- Route registry remains Java-owned.

## Java Parity Checklist

Reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/cli/CliSkillController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/cli/CliSkillAppService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/service/SkillPublishService.java`

Checklist:

| Area | Status | Notes |
| --- | --- | --- |
| API contract | covered for direct route foundation | Multipart `file` plus optional `visibility`; response data fields `namespace`, `slug`, `version`, `visibility`. |
| Auth/session | covered for local bridge | Uses `X-Mock-User-Id` local bridge. OAuth/session remains Java-owned. |
| Authorization | covered by dry-run preflight | Namespace membership and `SUPER_ADMIN` bypass use existing dry-run repository. |
| Database transaction atomicity | covered for new-version happy path | Uses `execute_publish_write(...)`; storage write failure still aborts finalize. |
| Audit actor/timestamp fields | covered by existing side-effect helper for compat audit where requested; CLI direct route does not set compat audit fields. |
| Storage and side effects | partially covered | Local storage, DB rows, review task/security audit foundations are used. Scanner HTTP calls remain deferred. |
| Live verification evidence | planned | Direct Python publish writes a unique fixture; proxy write route remains Java-owned. |

## Known Deferred Parity Before Ownership Move

- Auto-withdraw existing pending review versions before creating a new version.
- Same-version replacement lookup and cleanup from the HTTP route.
- Scanner enabled behavior and scanner HTTP handoff.
- Repeated publish/live replacement matrix against Java.

These gaps block route ownership but do not block a direct Python foundation route.

## Implementation Plan

1. Add route tests for missing auth, invalid preflight, and successful injected write.
2. Add `validate_cli_publish` shared helpers where possible.
3. Build `PublishWriteInput` from dry-run result and package metadata.
4. Execute `execute_publish_write(...)` for direct Python backend calls.
5. Add Windows live gate for direct Python CLI publish write plus proxy Java ownership check.
6. Keep route registry owner as Java.

## Acceptance Criteria

- `uv run pytest tests/test_publish_http_validate.py tests/test_publish_orchestration.py -q` passes.
- Windows live gate passes for direct Python publish write.
- Vite proxy still routes `POST /api/cli/v1/skills/{namespace}/publish` to Java.
- `git diff --name-only -- server` is empty.

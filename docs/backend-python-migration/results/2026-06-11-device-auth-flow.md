# Device Auth Flow Migration Result

Date: 2026-06-11

## Routes Changed

| Method | Route | Before | After |
|---|---|---|---|
| POST | `/api/v1/auth/device/code` | Java | Python |
| POST | `/api/v1/device/authorize` | Java | Python |
| POST | `/api/v1/auth/device/token` | Java | Python |

## Summary

The CLI/browser device authorization flow is now Python-owned. The migrated flow preserves:

- Java-compatible code response shape: `deviceCode`, `userCode`, `verificationUri`, `expiresIn = 900`, `interval = 5`.
- Redis key names and TTL semantics: `device:code:{deviceCode}`, `device:usercode:{userCode}`, and `device:claim:{deviceCode}`.
- Authorization state transitions for `PENDING`, `AUTHORIZED`, same-user idempotency, different-user rejection, and `USED`.
- One-time token redemption with `CLI Device Flow` API token rotation and `skill:read` / `skill:publish` scopes.
- Hash-only token storage.
- `DEVICE_AUTHORIZE` audit log with `{"userCode":"..."}` detail.

## Java Parity Checklist

| Area | Outcome |
|---|---|
| Java references | Covered: `DeviceAuthController`, `DeviceAuthWebController`, `DeviceAuthService`, `ApiTokenService`. |
| API contract | Covered for code, authorize, pending token, success token, and used-code error envelopes. |
| Authorization/session | Covered for local mock-user bridge on authorize. OAuth/session cookie persistence remains out of scope. |
| Database effects | Covered for API token rotation and audit-log insertion. |
| Redis effects | Covered for code/user-code/claim keys and TTL behavior. Python stores JSON values; Java/Python do not need cross-read compatibility because route ownership is per path. |
| Live verification | Passed with Python direct and Vite proxy full-flow parity. Java direct code shape matches, but Java direct token polling has a pre-existing runtime defect documented below. |

## Live Gate Finding

Windows live verification found that Java direct `POST /api/v1/auth/device/token` currently returns `500` during pending polling with:

`java.util.LinkedHashMap cannot be cast to com.iflytek.skillhub.auth.device.DeviceCodeData`

Because `server/` is read-only, this milestone does not modify Java. The gate records this as a Java reference runtime defect and still requires:

- Java direct `/code` stable response shape matches Python/proxy.
- Python direct full device flow passes.
- Vite proxy full device flow passes and reaches Python-owned routes.
- Python/proxy pending, authorize, success, and used-code contracts match.
- DB evidence passes for token rotation, scopes, hash-only storage, and `DEVICE_AUTHORIZE` audit.

## Verification

- `cd server-python; uv run pytest tests/test_device_auth.py tests/test_hybrid_makefile.py -q`
  - Passed: 12 tests.
- `cd web; npm run test -- vite.config.test.ts --run`
  - Passed: 46 tests.
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 -Action verify-device-auth-smoke`
  - Passed.
  - Result artifact: `.dev/device-auth-contract-result.json`.
  - Checks: `codeMatches`, `pendingMatches`, `authorizeMatches`, `successMatches`, `usedStatusMatches`, and `allEvidencePassed` were `true`.
  - Recorded: `javaFullFlowAvailable = false`, `javaLiveTokenPollClassCastDefectObserved = true`.

## Files Changed

- `server-python/app/auth/device.py`
- `server-python/app/api/device_auth.py`
- `server-python/app/main.py`
- `server-python/tests/test_device_auth.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-11-device-auth-flow.md`
- `docs/backend-python-migration/results/2026-06-11-device-auth-flow.md`

## Follow-Up

- Spring Session cookie persistence remains deferred to final auth/session replacement.
- OAuth callback/authorization routes remain Java-owned.
- Bearer-token request authentication filters and scope enforcement remain deferred.
- If Java device token polling is fixed later, update `verify-device-auth-smoke` to restore full Java/Python/proxy flow comparison.

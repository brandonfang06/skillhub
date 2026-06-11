# Device Auth Flow Migration Plan

Date: 2026-06-11

## Scope

Migrate the CLI/browser device authorization flow to Python:

| Method | Route | New owner |
|---|---|---|
| POST | `/api/v1/auth/device/code` | Python |
| POST | `/api/v1/device/authorize` | Python |
| POST | `/api/v1/auth/device/token` | Python |

Out of scope: OAuth callback/session login, Spring Session cookie persistence, bearer-token request authentication filters, token-scope enforcement, and any `server/` edits.

## Java Parity Contract

Reference behavior is `DeviceAuthController`, `DeviceAuthWebController`, and `DeviceAuthService`:

- `POST /api/v1/auth/device/code`
  - Anonymous route.
  - Generates a random device code and an 8-character user code formatted `XXXX-XXXX`.
  - Stores pending state with TTL 15 minutes under:
    - `device:code:{deviceCode}`
    - `device:usercode:{userCode}`
  - Returns `{ deviceCode, userCode, verificationUri, expiresIn: 900, interval: 5 }`.
- `POST /api/v1/device/authorize`
  - Requires an authenticated current user. During migration, Python uses the existing `X-Mock-User-Id` bridge.
  - Looks up `device:usercode:{userCode}`.
  - Missing user code returns `error.deviceAuth.userCode.invalid`.
  - Missing device data returns `error.deviceAuth.deviceCode.expired`.
  - `PENDING` transitions to `AUTHORIZED` and stores the authorizing `userId`.
  - `AUTHORIZED` by the same user is idempotent.
  - `AUTHORIZED` by a different user returns `error.deviceAuth.deviceCode.alreadyAuthorized`.
  - `USED` returns `error.deviceAuth.deviceCode.used`.
  - Writes `DEVICE_AUTHORIZE` audit with `{"userCode":"..."}` detail.
  - Returns `{ message: "Device authorized successfully" }`.
- `POST /api/v1/auth/device/token`
  - Anonymous polling route.
  - Missing device data returns `error.deviceAuth.deviceCode.invalid`.
  - `PENDING` returns `{ accessToken: null, tokenType: null, error: "authorization_pending" }`.
  - `AUTHORIZED` redeems exactly once:
    - claims `device:claim:{deviceCode}` with TTL 1 minute;
    - rotates an API token named `CLI Device Flow`;
    - scopes are `["skill:read","skill:publish"]`;
    - returns `{ accessToken, tokenType: "Bearer", error: null }`;
    - marks device data `USED` with TTL 1 minute;
    - deletes `device:usercode:{userCode}`;
  - `USED` returns `error.deviceAuth.deviceCode.used`.

## Python Design

- Use a small native RESP Redis client, reusing the existing `redis://` parser/RESP helpers already present for scanner handoff.
- Store Python device data as JSON under the same key names. Java/Python do not need to read each other's serialized value during coexistence because route ownership is per request path, and live comparisons run isolated full flows.
- Reuse Python API token storage behavior from the migrated token service, but ensure the returned field is Java-compatible `accessToken`.
- Keep token issuance and device state redemption ordered so DB token creation and Redis `USED` update match Java semantics as closely as possible.

## Files Allowed To Change

- `server-python/app/auth/device.py`
- `server-python/app/api/device_auth.py`
- `server-python/app/main.py`
- `server-python/tests/test_device_auth.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/**`

Forbidden: any file under `server/`.

## Verification Plan

1. Python unit tests:
   - code generation shape and Redis keys/TTLs;
   - pending token polling;
   - authorize transition and same-user idempotency;
   - different-user already-authorized error;
   - redeem creates/rotates CLI token and marks device code used;
   - route envelopes and auth requirement.
2. Vite proxy tests:
   - the three device routes route to `localhost:8081`;
   - OAuth routes remain Java-owned.
3. Windows live gate:
   - run Java/Python/proxy full device flows on isolated codes;
   - compare stable code/token/authorize envelopes after normalizing volatile device/user/access tokens and excluding localized `msg`;
   - verify DB API-token side effects for `CLI Device Flow`;
   - verify second token poll returns used-code behavior.
   - if Java direct token polling hits the current `LinkedHashMap` to `DeviceCodeData`
     `ClassCastException`, record it as a Java runtime reference defect, keep Java `/code`
     shape comparison, and require Python direct plus Vite proxy full-flow parity.
4. Safety checks:
   - `git diff --name-only -- server` must be empty;
   - `git diff --check` must pass.

## Milestone Exit Criteria

- `cd server-python; uv run pytest tests/test_device_auth.py tests/test_hybrid_makefile.py -q` passes.
- `cd web; npm run test -- vite.config.test.ts --run` passes.
- `./scripts/dev-hybrid.ps1 -Action verify-device-auth-smoke` passes.
- `route-registry.md`, this plan, `migration-sequence-plan.md`, and a result document are updated.
- Commit and push to `dev`.

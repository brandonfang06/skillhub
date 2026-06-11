# ClawHub Star Compatibility API Migration Result

Date: 2026-06-11

## Routes Changed

Moved to Python:

- `POST /api/v1/stars/{canonicalSlug}`
- `DELETE /api/v1/stars/{canonicalSlug}`

Still Java-owned:

- `DELETE /api/v1/skills/{canonicalSlug}`
- `POST /api/v1/skills/{canonicalSlug}/undelete`
- unlisted `/api/**`
- `/oauth2/**`

## Implementation

- Added Python ClawHub star service with Java-compatible canonical slug parsing.
- Added visible skill lookup before mutation.
- Preserved plain ClawHub JSON response bodies:
  - `{ ok, starred, alreadyStarred }`
  - `{ ok, unstarred, alreadyUnstarred }`
- Kept star/unstar idempotent and refreshed `skill.star_count` synchronously.
- Added FastAPI route ownership for only the ClawHub compatibility star/unstar paths.
- Added Vite method-aware proxy rules for only `POST`/`DELETE /api/v1/stars/{canonicalSlug}`.
- Added `verify-clawhub-star-smoke` Windows live gate.

## Verification

Passed:

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_clawhub_star.py tests/test_hybrid_makefile.py -q`
  - `10 passed`
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - `42 passed`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-clawhub-star-smoke`
  - Python tests inside gate: `15 passed`
  - Vite proxy tests inside gate: `42 passed`
  - Java/Python/proxy contract checks:
    - `unauthenticatedPostRejected = true`
    - `firstStarResponsesMatch = true`
    - `secondStarResponsesMatch = true`
    - `starDbState = true`
    - `firstUnstarResponsesMatch = true`
    - `secondUnstarResponsesMatch = true`
    - `unstarDbState = true`
  - Playwright smoke: `6 passed`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 status`
  - Java backend stopped
  - Python backend stopped
  - Vite frontend stopped

## Java Parity Checklist Outcome

| Area | Outcome |
| --- | --- |
| API contract | Passed. Plain JSON bodies match Java for first/repeated star and unstar. |
| Authorization / visibility | Passed for authenticated requirement and visible skill lookup in unit tests; live gate covers public visible skills. |
| Database atomicity | Passed. Mutation and counter refresh occur in one Python transaction. |
| Audit / storage | Not applicable. Java ClawHub star/unstar has no audit or storage side effects. |
| Proxy ownership | Passed. Vite routes only `POST`/`DELETE /api/v1/stars/{canonicalSlug}` to Python and leaves skill delete/undelete Java-owned. |

## Risks / Follow-Up

- Private and namespace-only ClawHub star access is covered by Python unit tests, but the live gate currently uses public fixtures only.
- Final proxy cleanup remains deferred until remaining Java-owned auth/session/device/account routes are handled or explicitly decommissioned.

# Skill Hard Delete Migration Result

## Summary

Moved whole-skill hard-delete routes to Python:

- `DELETE /api/v1/skills/id/{skillId}`
- `DELETE /api/v1/skills/{namespace}/{slug}`
- `DELETE /api/web/skills/id/{skillId}`
- `DELETE /api/web/skills/{namespace}/{slug}`

Kept Java-owned:

- `DELETE /api/v1/skills/{canonicalSlug}`
- `POST /api/v1/skills/{canonicalSlug}/undelete`

## Implementation

- Added `server-python/app/lifecycle/hard_delete.py`.
- Added lifecycle route adapters in `server-python/app/api/lifecycle.py`.
- Added Vite method-aware proxy rules for the four whole-skill hard-delete routes.
- Added `verify-skill-hard-delete-smoke` to `scripts/dev-hybrid.ps1`.
- Updated route registry and migration sequence plan.

## Java Parity Checklist Outcome

- API contract: covered. Java/Python/proxy stable delete envelopes match after normalizing
  volatile fields and per-fixture ids/slugs.
- Authorization/session behavior: covered for local `X-Mock-User-Id`; v1 requires
  `SUPER_ADMIN`; web allows owner or `SUPER_ADMIN`. Spring Session and bearer-token filters
  remain deferred by the global migration plan.
- Database transaction atomicity: covered for DB mutations in one transaction.
- Audit actor/timestamp fields: covered. Python records `DELETE_SKILL_HARD` with
  `namespaceId` and `slug`.
- Storage and side effects: covered for local storage deletion and compensation path.
- Live verification evidence: passed on Windows.

## Verification

- `cd server-python; uv run pytest tests/test_skill_hard_delete.py tests/test_skill_lifecycle_delete_version.py tests/test_hybrid_makefile.py -q`
  - Result: `16 passed`
- `cd web; npm run test -- vite.config.test.ts`
  - Result: `45 passed`
- `./scripts/dev-hybrid.ps1 -Action verify-skill-hard-delete-smoke`
  - Result: passed
  - Python/unit portion: `16 passed`
  - Vite proxy tests: `45 passed`
  - Playwright smoke: `6 passed`
  - Live contract result: `stableMatches=true`, `allDeleteSideEffectsObserved=true`,
    `webOwnerDeleteWorked=true`, `clawHubPlaceholdersRemainJavaOwned=true`
- `./scripts/dev-hybrid.ps1 -Action status`
  - Java backend: stopped
  - Python backend: stopped
  - Vite frontend: stopped

## Live Findings

- The hard-delete fixture initially used `security_audit.scanner_type = 'skill-scanner'`.
  Java JPA expects enum names when reading `SecurityAudit`, so the fixture was corrected to
  `SKILL_SCANNER`.
- The Windows live gate still printed the existing port-stop warning at teardown, but exited
  successfully and a follow-up status check showed the managed Java/Python/Vite services stopped.

## Risks And Follow-Up

- Python uses explicit SQL bridge code for parity. Refactor into repositories/ORM remains part
  of the later post-migration cleanup plan.
- ClawHub delete/undelete placeholders remain Java-owned and should be handled only if the product
  decides to keep or replace those compatibility endpoints.
- Final auth/session/bearer-token replacement remains deferred.

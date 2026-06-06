# SDLC Environment README Result

Date: 2026-06-06

## Summary

Documented the team SDLC rules for the Java/FastAPI coexistence migration and corrected the
cross-platform local development guidance:

- Windows and macOS continue to use Docker-managed dependency services for local hybrid E2E.
- Ubuntu uses organization-managed PostgreSQL, Redis, and MinIO instead of Docker-managed
  dependency services.
- Ubuntu developers manually adjust
  `server/skillhub-app/src/main/resources/application-local.yml` in their local workspace, but this
  file remains outside agent-owned changes and should not be committed unless explicitly approved.
- Added root `SDLC-README.md` in Chinese for team onboarding.

## Routes Changed

None.

## Ownership Before

- `/api/v1/health`: Python backend on `localhost:8081`
- Other `/api` and `/oauth2`: Java backend on `localhost:8080`

## Ownership After

No route ownership changes.

## Files Changed

- `SDLC-README.md`
- `docs/backend-python-migration/hybrid-local-e2e.md`
- `docs/backend-python-migration/plans/2026-06-06-sdlc-environment-readme.md`
- `docs/backend-python-migration/results/2026-06-06-sdlc-environment-readme.md`
- `server-python/tests/test_hybrid_makefile.py`

## Verification

- `cd server-python; uv run pytest`: passed, 8 tests.
- `cd web; .\node_modules\.bin\vitest.CMD run vite.config.test.ts`: passed, 2 tests.
- `git diff --name-only -- server`: returned no paths.

## Risks

- Ubuntu developers must keep their local `application-local.yml` changes out of commits unless the
  project owner explicitly approves a server configuration change.
- The Ubuntu workflow depends on organization network access and reachable PostgreSQL, Redis, and
  MinIO endpoints.

## Follow-up

- If Ubuntu developers need repeatable startup automation later, add a non-Docker Linux helper that
  starts Java, Python, and Vite only, while leaving dependency services external.

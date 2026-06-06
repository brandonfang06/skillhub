# SDLC Environment README Plan

Date: 2026-06-06

## Milestone

Document the team SDLC rules for the hybrid Java/FastAPI migration and correct the local
environment guidance for Windows, macOS, and Ubuntu.

This is a governance/documentation milestone. It does not migrate a business API.

## Scope

Allowed changes:

- `docs/backend-python-migration/hybrid-local-e2e.md`
- `docs/backend-python-migration/plans/2026-06-06-sdlc-environment-readme.md`
- `docs/backend-python-migration/results/2026-06-06-sdlc-environment-readme.md`
- `SDLC-README.md`
- `server-python/tests/test_hybrid_makefile.py`

Forbidden changes:

- Any file under `server/`
- Java backend configuration commits, including `server/skillhub-app/src/main/resources/application-local.yml`
- Business API ownership changes
- Vite proxy route ownership changes

## Required Rules to Capture

- Windows and macOS local development can use Docker for dependency services because those
  environments are outside the organization network.
- Ubuntu local development must not use Docker for PostgreSQL, Redis, or MinIO dependency
  services.
- Ubuntu developers manually adjust
  `server/skillhub-app/src/main/resources/application-local.yml` in their local workspace to point
  Java to organization-managed PostgreSQL, Redis, and MinIO.
- The Ubuntu Java config adjustment is local environment setup, not part of agent changes, and must
  not be committed unless explicitly approved by the project owner.
- `server/` remains read-only for migration work.

## Tests

- Add pytest assertions that the hybrid E2E document describes the Ubuntu organization-service
  workflow.
- Add pytest assertions that root `SDLC-README.md` exists and documents the Chinese team rules.

## Acceptance Criteria

- `cd server-python; uv run pytest` passes.
- Vite proxy regression test still passes.
- `git diff --name-only -- server` returns no paths.
- Result document records the final environment ownership and verification.

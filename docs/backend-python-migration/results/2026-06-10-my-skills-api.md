# My Skills API Migration Result

**Date:** 2026-06-10

## Summary

Moved current-user owned skill list routes to FastAPI and Vite method-aware proxy.

## Routes Changed

Python-owned:

- `GET /api/v1/me/skills`
- `GET /api/web/me/skills`

Java-owned:

- Non-GET `/api/v1/me/skills` and `/api/web/me/skills`
- Other `/me/**` routes not already registered as Python-owned

## Behavior Notes

- Defaults remain Java-compatible: `page=0`, `size=10`.
- Supports `filter`, `q`, and `namespace`.
- Invalid/blank filter falls back to `ALL`.
- Preserved Java's two-path behavior:
  - no filter/q/namespace uses direct owner pagination and includes hidden/archived owned skills,
  - filter path applies lifecycle filtering and excludes hidden/archived for `ALL`.
- `HIDDEN` filter only returns hidden skills for `SUPER_ADMIN`.
- Owner summary lifecycle fields include `headlineVersion`, `publishedVersion`,
  `ownerPreviewVersion`, and `resolutionMode`.
- Promotion eligibility mirrors the Java summary guard for team namespace, active skill, published
  version, and no pending/approved promotion request.

## Verification

- `cd server-python; $env:UV_CACHE_DIR='.uv-cache'; uv run pytest tests/test_my_skills.py tests/test_my_social_lists.py tests/test_hybrid_makefile.py -q`
  - `13 passed`
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - `28 passed`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-my-skills-smoke`
  - Python/hybrid tests passed.
  - Vite proxy tests passed.
  - Java/Python/Vite default owned-skill stable JSON matched.
  - Java/Python/Vite keyword/namespace filter stable JSON matched.
  - Java/Python/Vite `HIDDEN` SUPER_ADMIN filter stable JSON matched.
  - Anonymous proxy access returned `401`.
  - POST boundary stayed Java-owned through fallback.
  - Playwright smoke passed: `6 passed`.
- `git diff --name-only -- server`
  - no paths.

## Risks / Follow-Up

- This milestone does not migrate any owned-skill mutation routes.
- The live gate depends on Docker Desktop for local dependencies; if Docker Desktop is stopped, run
  or start Docker Desktop before executing `verify-my-skills-smoke`.

# Publish Upload Foundation Result

Date: 2026-06-08

## Summary

Completed the Python publish package foundation without migrating any publish route.

Python now has deterministic helpers for:

- package entry modeling and content type detection;
- Java-compatible zip extraction limits;
- path normalization and OS metadata filtering;
- single-root stripping and single nested `SKILL.md` promotion;
- `SKILL.md` YAML frontmatter parsing;
- package validation errors and warnings for required metadata, duplicate paths, extensions, and
  content signatures.

All publish POST routes remain Java-owned.

## Route Ownership

No route ownership moved to Python in this milestone.

| Method | Path | Before | After |
| --- | --- | --- | --- |
| POST | `/api/v1/skills` | java | java |
| POST | `/api/v1/publish` | java | java |
| POST | `/api/v1/skills/{namespace}/publish` | java | java |
| POST | `/api/web/skills/{namespace}/publish` | java | java |
| POST | `/api/cli/v1/skills/{namespace}/publish/validate` | java | java |
| POST | `/api/cli/v1/skills/{namespace}/publish` | java | java |

## Proxy Boundary

The Vite proxy had a real method-collision risk: two-segment skill detail paths and namespace
publish paths have the same route shape.

This milestone changed public skill detail proxy ownership to method-aware GET-only rules:

- `GET /api/v1/skills/{namespace}/{slug}` -> Python
- `GET /api/web/skills/{namespace}/{slug}` -> Python
- `POST /api/v1/skills/{namespace}/publish` -> Java fallback
- `POST /api/web/skills/{namespace}/publish` -> Java fallback

This is an ownership safety fix, not a publish migration.

## Files Changed

- `server-python/app/publish/__init__.py`
- `server-python/app/publish/package.py`
- `server-python/tests/test_publish_package.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/windows-live-verification.md`

## Verification

Focused checks completed during implementation:

- `cd server-python; uv run pytest tests/test_publish_package.py -q`
  - `21 passed`
- `cd web; .\node_modules\.bin\vitest.CMD vite.config.test.ts --run`
  - `18 passed`
- `cd server-python; uv run pytest tests/test_publish_package.py tests/test_hybrid_makefile.py -q`
  - `27 passed`

Final checks completed:

- `cd server-python; uv run pytest`
  - `179 passed, 1 warning`
- `cd web; .\node_modules\.bin\vitest.CMD vite.config.test.ts --run`
  - `18 passed`
- `cd web; .\node_modules\.bin\tsc.CMD --noEmit`
  - passed
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-publish-foundation-smoke`
  - package tests: `21 passed`
  - publish ownership: all Java/Vite status comparisons matched
  - Playwright smoke: `6 passed`
  - `.dev/publish-foundation-contract-result.json` written
- Port cleanup check after live gate:
  - no `LISTENING` entries on `3000`, `8080`, or `8081`; only `TIME_WAIT` entries remained.
- `git diff --check`
  - passed; Windows line-ending warnings only.
- `git diff --name-only -- server`
  - printed nothing.

## Risks

- The package helper mirrors deterministic Java extraction/validation rules, but it is not yet wired
  into an HTTP publish route.
- Auth, namespace writability, DB writes, object storage writes, scanner trigger, audit/event
  behavior, and transaction compensation remain Java-owned.
- CLI publish response contracts are documented as Java-owned but not yet mapped into Python.

## Follow-Up

Next publish migration milestone should be a dry-run transaction model:

- namespace lookup;
- local mock-user / role checks;
- slug and version conflict checks;
- package validation reuse;
- no DB writes, storage writes, or scanner trigger yet.

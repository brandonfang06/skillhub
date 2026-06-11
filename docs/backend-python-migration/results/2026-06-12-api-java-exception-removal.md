# API Java Exception Removal Result

Date: 2026-06-12

## Summary

The local Vite dev proxy no longer contains Java targets for `/api/**`. All API paths now reach
Python through either route-specific Python proxy rules or the broad `/api` Python fallback.

`/oauth2/**` remains the only Java-owned proxy family.

## Implementation Notes

- Removed the remaining `http://localhost:8080` method-aware proxy rules for API paths.
- Added a Vite regression test that rejects any `/api` proxy target to Java while preserving OAuth
  on Java.
- Updated migration registry docs to mark unsupported or method-mismatched API paths as Python
  fallback behavior instead of Java sidecar behavior.
- Kept Java `server/` source read-only.

## Verification

TDD red check:

```text
npm.cmd run test -- vite.config.test.ts
Test Files  1 failed (1)
Tests       8 failed | 40 passed (48)
```

Green check after proxy changes:

```text
npm.cmd run test -- vite.config.test.ts
Test Files  1 passed (1)
Tests       48 passed (48)

uv run pytest tests/test_route_registry.py -q
2 passed
```

Hybrid live gate:

```text
health python=200 vite=200
post-canonical-skill python=405 vite=405
get-clawhub-star-holdout python=405 vite=405
post-me-skills-holdout python=405 vite=405
post-admin-audit-holdout python=405 vite=405
post-tag-holdout python=405 vite=405
oauth java=302 vite=302
```

Hybrid shutdown:

```text
Java backend:   stopped
Python backend: stopped
Vite frontend:  stopped
Get-NetTCPConnection -LocalPort 3000,8000,8080,8081
no output
```

Final regression:

```text
npm.cmd run test -- vite.config.test.ts
Test Files  1 passed (1)
Tests       48 passed (48)

uv run pytest tests/test_route_registry.py -q
2 passed

git diff --check
passed

git diff --name-only -- server
no output
```

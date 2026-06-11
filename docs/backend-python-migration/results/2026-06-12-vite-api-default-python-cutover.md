# Vite API Default Python Cutover Result

Date: 2026-06-12

## Summary

The local Vite dev proxy now sends unmatched `/api/**` traffic to Python by default after explicit
Java-owned exceptions. `/oauth2/**` remains Java-owned.

This closes the broad Java API fallback that previously made final route ownership ambiguous during
hybrid development.

## Explicit Java Exceptions

The Vite method-aware proxy keeps these holdouts on Java:

- `POST /api/v1/skills/{canonicalSlug}`
- `POST /api/v1/skills/{namespace}/{slug}`
- `POST /api/web/skills/{namespace}/{slug}`
- `GET /api/v1/skills/{skillId}/versions/{versionId}`
- `GET /api/v1/stars/{canonicalSlug}`
- `POST /api/v1/me/skills`
- `POST /api/v1/admin/audit-logs`
- `POST /api/v1/skills/{namespace}/{slug}/tags/{tagName}`
- `POST /api/web/skills/{namespace}/{slug}/tags/{tagName}`

## Verification

TDD red check:

```text
npm.cmd run test -- vite.config.test.ts
Test Files  1 failed (1)
Tests       4 failed | 43 passed (47)
```

Green check after proxy changes:

```text
npm.cmd run test -- vite.config.test.ts
Test Files  1 passed (1)
Tests       47 passed (47)

uv run pytest tests/test_route_registry.py -q
2 passed
```

Hybrid live gate:

```text
vite health -> 200
python unmatched -> 404
vite unmatched -> 404
java oauth -> 302
vite oauth -> 302
java holdout POST admin audit logs -> 401
vite holdout POST admin audit logs -> 401
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
Tests       47 passed (47)

uv run pytest tests/test_route_registry.py -q
2 passed

git diff --check
passed

git diff --name-only -- server
no output
```

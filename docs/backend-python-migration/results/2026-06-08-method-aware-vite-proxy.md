# Method-Aware Vite Proxy Result

Date: 2026-06-08

## Summary

Added method-aware Vite proxy infrastructure for future API migrations where a Python-owned GET
route shares the same path with Java-owned mutating methods.

No backend business API was migrated in this milestone.

## Routes Changed

No active backend route ownership changed.

Verified inactive-by-default method-aware capability:

| Method | Route | Target |
| --- | --- | --- |
| GET | `/api/v1/skills/{canonicalSlug}` | Python `localhost:8081` when a future milestone enables a rule. |
| POST / DELETE | `/api/v1/skills/{canonicalSlug}` | Java fallback `localhost:8080` because no method-aware rule matches. |

The active rule list is intentionally empty. The next API milestone must add the FastAPI route,
enable the method-aware GET rule, and add a live contract gate before this path is considered
migrated.

## Implementation

- Added empty `METHOD_AWARE_PROXY_RULES`.
- Added `resolveMethodAwareProxyTarget`.
- Added `skillhub-method-aware-proxy` Vite plugin.
- Plugin runs before Vite's path-based proxy middleware.
- Matching methods proxy to the configured target.
- Non-matching methods fall through to existing Java `/api` fallback.
- Added Vitest coverage for GET vs POST/DELETE routing on the same path.

## Verification

Commands run:

```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Observed result:

```text
Test Files  1 passed (1)
Tests       14 passed (14)
```

## Boundary Check

- `server/` remained read-only.
- `server-python/app/api/**` was not changed for this infrastructure milestone.
- No generated frontend API type was edited.

## Risks And Follow-Up

- The next `GET /api/v1/skills/{canonicalSlug}` milestone must add live verification proving:
  - GET reaches Python.
  - DELETE on the same path still reaches Java.
  - `/api/v1/skills` root remains Java-owned.
- This infrastructure is intentionally scoped to Vite local dev coexistence. Production routing
  still needs separate deployment design when Python owns production traffic.

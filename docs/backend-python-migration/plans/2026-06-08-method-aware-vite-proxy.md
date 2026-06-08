# Method-Aware Vite Proxy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add method-aware Vite dev proxy support so future migrations can route GET-only paths to
Python without taking over Java-owned POST/DELETE routes on the same path.

**Architecture:** Keep existing path-based `server.proxy` entries for routes without method
collisions. Add a small Vite plugin that runs before Vite's built-in proxy middleware, checks
method-aware rules, and proxies only matching methods to the configured target. Non-matching
methods fall through to the existing `/api` Java fallback.

**Tech Stack:** Vite, TypeScript, Node `http` / `https`, Vitest, Windows hybrid verification.

---

## Milestone Announcement

This milestone does not migrate a backend API. It adds infrastructure required before migrating
ClawHub routes that have method collisions.

First route family that needs this:

| Method | Path | Future Owner | Collision |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{canonicalSlug}` | python | Same path as Java-owned DELETE. |
| DELETE | `/api/v1/skills/{canonicalSlug}` | java | Must not be proxied to Python. |

## Allowed Files

- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `docs/backend-python-migration/plans/2026-06-08-method-aware-vite-proxy.md`
- `docs/backend-python-migration/windows-live-verification.md`
- `docs/backend-python-migration/results/2026-06-08-method-aware-vite-proxy.md`

## Forbidden Files

- Any path under `server/`
- `server-python/app/api/**`
- `web/src/api/generated/schema.d.ts`
- Any business API route ownership change

## Tasks

- [x] **Step 1: Write failing resolver tests**

Update `web/vite.config.test.ts` to import `resolveMethodAwareProxyTarget` and verify:

- `GET /api/v1/skills/demo` resolves to `http://localhost:8081` when a GET-only rule exists.
- `DELETE /api/v1/skills/demo` returns `undefined` for the method-aware resolver.
- `POST /api/v1/skills/demo` returns `undefined`.
- nested `/api/v1/skills/global/demo` does not match the one-segment rule.

- [x] **Step 2: Run resolver tests and confirm RED**

```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Expected: FAIL because method-aware helpers do not exist.

- [x] **Step 3: Implement method-aware proxy helpers**

Add to `web/vite.config.ts`:

- `MethodAwareProxyRule` type.
- `METHOD_AWARE_PROXY_RULES` constant.
- `resolveMethodAwareProxyTarget(method, pathname, rules)`.

Keep active `METHOD_AWARE_PROXY_RULES` empty in this milestone. Tests should pass explicit fixture
rules into `resolveMethodAwareProxyTarget` to verify behavior without changing active route
ownership.

- [x] **Step 4: Implement Vite middleware plugin**

Add a Vite plugin that:

- Runs before built-in proxy middleware.
- Uses `resolveMethodAwareProxyTarget`.
- Proxies matching requests to Python.
- Lets non-matching methods fall through to existing path-based proxy.

- [x] **Step 5: Run Vite tests**

```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
```

Expected: PASS.

- [x] **Step 6: Add Windows verification note**

Update `docs/backend-python-migration/windows-live-verification.md` with the rule:

- For method-colliding routes, verify GET and mutating methods separately.
- GET may route to Python; POST/DELETE must still route to Java.

- [x] **Step 7: Final verification**

```powershell
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts
cd ..
git diff --check
git diff --name-only -- server
```

- [x] **Step 8: Write result document**

Create `docs/backend-python-migration/results/2026-06-08-method-aware-vite-proxy.md`.

- [x] **Step 9: Commit and push**

Commit and push after verification and result document are complete.

## Acceptance Criteria

- Method-aware resolver can distinguish GET from DELETE/POST on the same path.
- Non-matching methods fall through to Java `/api` fallback.
- No business backend API is migrated in this milestone.
- `web` Vite proxy tests pass.
- `git diff --name-only -- server` is empty.

# Explicit Java Proxy Exceptions Result

## Summary

Made the remaining Java-owned proxy exceptions explicit in the migration registry.

This milestone intentionally did not change runtime proxy behavior. It records that final proxy
cleanup is still blocked by Java-owned compatibility/fallback paths rather than treating `/api/**`
as an anonymous catch-all with unknown contents.

## Routes Documented

| Method | Path | Owner | Reason |
| --- | --- | --- | --- |
| DELETE | `/api/v1/skills/{canonicalSlug}` | java | ClawHub placeholder delete remains distinct from Python-owned two-segment namespace/slug hard delete. |
| POST | `/api/v1/skills/{canonicalSlug}/undelete` | java | ClawHub placeholder undelete remains Java-owned until a dedicated compatibility decision moves or removes it. |
| * | `/api/**` unmatched paths | java | Default owner for unregistered or intentionally unmigrated API paths until final cutover. |
| * | `/oauth2/**` | java | OAuth remains Java-owned. |

## Tests

Red guard before registry update:

```powershell
cd server-python
uv run pytest tests/test_route_registry.py -q
```

Result before docs update: `2 failed`; route registry and migration sequence did not yet include
the explicit Java exception rows/milestone.

Passed after docs update:

```powershell
cd server-python
uv run pytest tests/test_route_registry.py -q
```

Result: `2 passed`.

Proxy behavior regression check:

```powershell
cd web
npm.cmd run test -- vite.config.test.ts
```

Result: `46 passed`.

Guard regression check:

```powershell
cd server-python
uv run pytest tests/test_hybrid_makefile.py tests/test_route_registry.py -q
```

Result: `8 passed`.

## Review Pass

- Java source under `server/` was read-only; no Java files were modified.
- Existing Vite tests still prove ClawHub one-segment delete and undelete route to Java.
- The registry now distinguishes one-segment ClawHub delete from two-segment namespace/slug hard
  delete, avoiding a future proxy cleanup mistake.
- Final proxy cleanup should not remove the Java `/api` fallback until ClawHub delete/undelete and
  other unmatched paths are either migrated, intentionally preserved, or removed from compatibility.

## Files Changed

- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-11-explicit-java-proxy-exceptions.md`
- `docs/backend-python-migration/results/2026-06-11-explicit-java-proxy-exceptions.md`
- `server-python/tests/test_route_registry.py`

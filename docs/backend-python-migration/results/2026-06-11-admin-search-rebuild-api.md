# Admin Search Rebuild API Migration Result

## Summary

Moved `POST /api/v1/admin/search/rebuild` to Python.

The route requires `SUPER_ADMIN`, rebuilds `skill_search_document` rows for ACTIVE skills, and
writes Java-compatible `REBUILD_SEARCH_INDEX` audit metadata.

## Java Parity Checklist Outcome

- API contract: covered. Java, direct Python, and Vite proxy return `200`, `code = 0`,
  localized `msg = 更新成功`, and `data = null`.
- Authorization/session behavior: covered. Python requires local mock current user and
  `SUPER_ADMIN`.
- Database transaction atomicity: covered. Rebuild upserts and audit insert run in one transaction.
- Audit actor/timestamp fields: covered. Python writes `REBUILD_SEARCH_INDEX`, target type
  `SEARCH_INDEX`, null target id, request id, client IP, user agent, and `{"scope":"ALL"}` detail.
- Storage and side effects: not applicable.
- Live verification evidence: covered.

## Tests

- Red: `uv run pytest tests/test_admin_search_rebuild.py tests/test_route_registry.py -q`
  failed because `app.admin.search` did not exist.
- Red: `npm.cmd run test -- vite.config.test.ts` failed because
  `POST /api/v1/admin/search/rebuild` did not route to Python.
- Green: `uv run pytest tests/test_admin_search_rebuild.py tests/test_route_registry.py -q`
  passed with `5 passed, 1 warning`.
- Green: `npm.cmd run test -- vite.config.test.ts` passed with `47 passed`.

## Live Verification

Hybrid stack:

- Java backend: `http://localhost:8080`
- Python backend: `http://localhost:8081`
- Vite proxy: `http://localhost:3000`

Final HTTP comparison:

| Target | Status | Stable body fields |
| --- | --- | --- |
| Java direct | 200 | `code=0`, `msg=更新成功`, `data=null`, request id echoed |
| Python direct | 200 | `code=0`, `msg=更新成功`, `data=null`, request id echoed |
| Vite proxy | 200 | `code=0`, `msg=更新成功`, `data=null`, request id echoed |

DB side-effect evidence:

- `skill_search_document` count after rebuild: `318`.
- Recent `audit_log` rows include `REBUILD_SEARCH_INDEX` with actor `local-admin`, target type
  `SEARCH_INDEX`, null target id, request ids from Java and Vite proxy calls, and detail
  `{"scope": "ALL"}`.

## Debug Notes

Live verification caught two Python-only issues before final pass:

- `sv.parsed_metadata_json::text` inside SQLAlchemy `text()` can be parsed as a bind marker. The
  query now uses `CAST(sv.parsed_metadata_json AS text)`.
- `skill_search_document.updated_at` and `audit_log.created_at` are PostgreSQL `TIMESTAMP` columns,
  matching Java `LocalDateTime`. Python now binds naive UTC datetimes instead of timezone-aware
  values.
- Java localizes `response.success.updated` to `更新成功`; Python now returns the localized message
  for this route.

## Files Changed

- `server-python/app/admin/search.py`
- `server-python/app/api/admin_search.py`
- `server-python/app/main.py`
- `server-python/tests/test_admin_search_rebuild.py`
- `server-python/tests/test_route_registry.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-11-admin-search-rebuild-api.md`

No files under `server/` were modified for this milestone.

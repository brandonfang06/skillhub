# Admin Label Definition API Migration Plan

## Summary

Move admin label definition management from Java to Python:

- `GET /api/v1/admin/labels`
- `POST /api/v1/admin/labels`
- `PUT /api/v1/admin/labels/{slug}`
- `DELETE /api/v1/admin/labels/{slug}`
- `PUT /api/v1/admin/labels/sort-order`

This milestone does not move skill label attach/detach routes under
`/api/v1/skills/{namespace}/{slug}/labels/{labelSlug}`. Those require skill ownership, namespace
role checks, and search sync behavior and should be handled separately.

## Java Contract

Reference files, read-only:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/admin/AdminLabelController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/service/LabelAdminAppService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/label/LabelDefinitionService.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/label/LabelSlugValidator.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/label/LabelPermissionChecker.java`
- `server/skillhub-app/src/main/resources/db/migration/V34__skill_label_system.sql`

Behavior to preserve:

- All routes require `SUPER_ADMIN`.
- List returns labels ordered by `sort_order ASC, id ASC`.
- Create normalizes slug by trimming and lowercasing, validates slug pattern/double hyphen/length,
  rejects duplicate slug, requires at least one translation, normalizes translation locale and
  display name, and writes `LABEL_CREATE` audit.
- Update finds by normalized slug, replaces translations, updates type/visibility/sort order, and
  writes `LABEL_UPDATE` audit.
- Delete finds by normalized slug, deletes the label definition and translations by FK cascade, and
  writes `LABEL_DELETE` audit.
- Sort order update rejects empty items, resolves each slug, updates sort order, returns updated
  labels, and writes `LABEL_SORT_ORDER_UPDATE` audit with `{"count":N}`.

## Route Ownership

| Method | Route | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/admin/labels` | java | python |
| POST | `/api/v1/admin/labels` | java | python |
| PUT | `/api/v1/admin/labels/{slug}` | java | python |
| DELETE | `/api/v1/admin/labels/{slug}` | java | python |
| PUT | `/api/v1/admin/labels/sort-order` | java | python |

Remain Java-owned:

- Skill label attach/detach
- Admin user management
- Auth/OAuth/token routes
- Notification SSE

## Implementation Scope

Allowed edits:

- `server-python/app/admin/`
- `server-python/app/api/`
- `server-python/tests/`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/*`

Forbidden:

- Any file under `server/`
- Generated frontend OpenAPI files
- Skill label attach/detach ownership changes

## Java Parity Checklist

| Area | Status | Notes |
| --- | --- | --- |
| API contract | covered | Preserve response fields and Java envelope messages. |
| Authorization/session | covered | Local mock user must have `SUPER_ADMIN` platform role. |
| Database transaction atomicity | covered | Create/update/delete/sort each run in one SQLAlchemy transaction. |
| Audit actor/timestamp fields | covered | Writes Java-compatible `audit_log` rows for admin label actions. |
| Storage/side effects | not applicable | No object storage side effects. |
| Search side effects | deferred | Java schedules search rebuild for affected skills on update/delete. Route ownership can move with this recorded as deferred because the project is pre-launch and live gate verifies DB/audit contract; skill-label attach/detach remains Java-owned. |
| Live verification | covered | Java/Python/Vite compare covers create/update/delete/sort, permissions, and audit evidence. |

## Tests

- Python service tests:
  - create normalizes slug/translation and writes audit
  - duplicate slug and non-super-admin rejected
  - update replaces translations and writes audit
  - delete deletes definition and writes audit
  - sort-order updates multiple labels and writes count audit
- FastAPI route tests:
  - admin envelope and 401/403 behavior
- Vite proxy tests:
  - admin label definition routes go to Python
  - skill label attach/detach remains Java fallback
- Windows live gate:
  - `verify-admin-label-definition-smoke`

## Verification Commands

- `cd server-python; $env:UV_CACHE_DIR='..\\.uv-cache'; uv run pytest tests/test_admin_label_definitions.py tests/test_hybrid_makefile.py -q`
- `cd web; npx.cmd vitest run vite.config.test.ts`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\dev-hybrid.ps1 verify-admin-label-definition-smoke`
- `git diff --name-only -- server`
- `git diff --check`

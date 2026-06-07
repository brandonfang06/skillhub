# Skill Labels List API Migration Result

Date: 2026-06-07

Status: passed

## Scope

Routes migrated in this milestone:

| Method | Path | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{namespace}/{slug}/labels` | java | python |
| GET | `/api/web/skills/{namespace}/{slug}/labels` | java | python |

Routes intentionally not migrated:

- `PUT /api/v1/skills/{namespace}/{slug}/labels/{labelSlug}`
- `PUT /api/web/skills/{namespace}/{slug}/labels/{labelSlug}`
- `DELETE /api/v1/skills/{namespace}/{slug}/labels/{labelSlug}`
- `DELETE /api/web/skills/{namespace}/{slug}/labels/{labelSlug}`
- Admin label APIs

## Implementation Summary

- Added FastAPI aliases for the skill labels list routes.
- Reused the existing Python label localization helper.
- Added `build_skill_label_response()` with Java-compatible sorting: `type ASC`, then `slug ASC`.
- Added anonymous public PostgreSQL lookup for public, non-hidden skills with a latest version.
- Added precise Vite regex proxy entries for the two labels routes only.
- Updated route ownership documentation.

Auth-specific Java behavior remains deferred until the auth/session bridge is designed:

- owner preview
- namespace-only access
- private access
- hidden preview for owner/admin
- SUPER_ADMIN bypass

## Files Changed

- `server-python/app/api/labels.py`
- `server-python/tests/test_labels.py`
- `server-python/tests/test_label_repository.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-07-skill-labels-list-api.md`
- `docs/backend-python-migration/results/2026-06-07-skill-labels-list-api.md`

## Tests

Python:

```text
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest

20 passed, 1 warning
```

Vite proxy config:

```text
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts

1 passed, 5 tests passed
```

Frontend smoke E2E:

```text
.\node_modules\.bin\playwright.CMD test -c playwright.smoke.config.ts

6 passed (19.8s)
```

## Live Contract Verification

The local Docker PostgreSQL bootstrap data did not include a public skill with labels, so the live
gate inserted a local-only fixture into Docker PostgreSQL:

| Field | Value |
| --- | --- |
| namespace | `global` |
| skill slug | `codex-label-fixture-20260607181400` |
| label slug | `codex-fixture-label-20260607181400` |
| visibility | `PUBLIC` |
| latest version | `1.0.0`, `PUBLISHED` |
| zh display name | `Codex Fixture Zh` |

Stable fields compared:

- `code`
- `msg`
- `data`

Ignored volatile fields:

- `timestamp`
- `requestId`

Comparison result:

```json
{
  "javaMatchesPython": true,
  "pythonMatchesProxyV1": true,
  "pythonMatchesProxyWeb": true,
  "data": [
    {
      "slug": "codex-fixture-label-20260607181400",
      "type": "RECOMMENDED",
      "displayName": "Codex Fixture Zh"
    }
  ]
}
```

## Boundary Check

Required Java boundary check:

```powershell
git diff --name-only -- server
```

Expected and observed output: empty.

## Cleanup Notes

During live verification, `dev-hybrid.ps1 down` emitted Windows sandbox warnings for transient
process cleanup, but Java/Python/Vite listeners were gone afterward. Docker dependency services
were then stopped explicitly with:

```powershell
docker compose -p skillhub down --remove-orphans
```

Follow-up checks showed no remaining Java/Python/Vite listeners on `3000`, `8080`, or `8081`.

## Risks And Follow-Up

- This milestone intentionally supports anonymous public skill labels only.
- Auth-specific behavior must not be migrated until the Python auth/session bridge exists.
- Future skill read milestones should add reusable fixture setup for live contract comparison
  instead of ad hoc SQL insertion.
- Next planned API group: public skill resolve routes.

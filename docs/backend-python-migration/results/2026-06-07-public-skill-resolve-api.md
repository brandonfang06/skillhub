# Public Skill Resolve API Migration Result

Date: 2026-06-07

Status: passed

## Scope

Routes migrated in this milestone:

| Method | Path | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{namespace}/{slug}/resolve` | java | python |
| GET | `/api/web/skills/{namespace}/{slug}/resolve` | java | python |

Routes intentionally not migrated:

- `/download` routes
- file streaming or file content routes
- download counters
- object storage access
- rate-limit behavior
- authenticated owner preview, private/namespace-only visibility, hidden preview, and SUPER_ADMIN
  bypass

## Implementation Summary

- Added `server-python/app/api/skills.py` with resolve route aliases.
- Added Java-compatible `ResolveVersionResponse` fields:
  - `skillId`
  - `namespace`
  - `slug`
  - `version`
  - `versionId`
  - `fingerprint`
  - `matched`
  - `downloadUrl`
- Implemented anonymous public PostgreSQL lookup for active, public, non-hidden skills with a latest
  published version.
- Implemented Java-compatible selector behavior for:
  - no selector
  - `tag=latest`
  - exact `version`
  - custom `tag`
  - matching `hash`
  - non-matching `hash`
  - `version` + `tag` conflict
- Added exact Vite proxy ownership entries for resolve only.
- Updated route ownership and migration sequence documentation.

## Files Changed

- `server-python/app/api/skills.py`
- `server-python/app/main.py`
- `server-python/tests/test_skill_resolve.py`
- `server-python/tests/test_skill_resolve_repository.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `docs/backend-python-migration/route-registry.md`
- `docs/backend-python-migration/migration-sequence-plan.md`
- `docs/backend-python-migration/plans/2026-06-07-public-skill-resolve-api.md`
- `docs/backend-python-migration/results/2026-06-07-public-skill-resolve-api.md`

## Tests

Python:

```text
cd server-python
$env:UV_CACHE_DIR='.uv-cache'
uv run pytest

31 passed, 1 warning
```

Vite proxy config:

```text
cd web
.\node_modules\.bin\vitest.CMD run vite.config.test.ts

1 passed, 6 tests passed
```

Frontend smoke E2E:

```text
cd web
.\node_modules\.bin\playwright.CMD test -c playwright.smoke.config.ts

6 passed (19.5s)
```

## Live Contract Verification

The live verification gate ran Java, Python, Vite, PostgreSQL, Redis, MinIO, and the scanner in the
same Windows PowerShell lifecycle because background dev processes are cleaned up when a Codex tool
call exits.

Fixture inserted into local Docker PostgreSQL:

| Field | Value |
| --- | --- |
| namespace | `global` |
| skill slug | `codex-resolve-fixture-20260607190000` |
| visibility | `PUBLIC` |
| skill status | `ACTIVE` |
| latest version | `1.2.0`, `PUBLISHED` |
| older version | `1.0.0`, `PUBLISHED` |
| tag | `stable -> 1.0.0` |
| files | one `SKILL.md` per version for fingerprint comparison |

Stable fields compared:

- `code`
- `msg`
- `data.skillId`
- `data.namespace`
- `data.slug`
- `data.version`
- `data.versionId`
- `data.fingerprint`
- `data.matched`
- `data.downloadUrl`

Ignored volatile fields:

- `timestamp`
- `requestId`

Comparison summary:

```json
{
  "fixtureSlug": "codex-resolve-fixture-20260607190000",
  "scenarios": [
    {
      "name": "latest-default",
      "javaMatchesPython": true,
      "pythonMatchesProxyV1": true,
      "pythonMatchesProxyWeb": true,
      "version": "1.2.0",
      "matched": null
    },
    {
      "name": "tag-latest",
      "javaMatchesPython": true,
      "pythonMatchesProxyV1": true,
      "pythonMatchesProxyWeb": true,
      "version": "1.2.0",
      "matched": null
    },
    {
      "name": "version-1.0.0",
      "javaMatchesPython": true,
      "pythonMatchesProxyV1": true,
      "pythonMatchesProxyWeb": true,
      "version": "1.0.0",
      "matched": null
    },
    {
      "name": "tag-stable",
      "javaMatchesPython": true,
      "pythonMatchesProxyV1": true,
      "pythonMatchesProxyWeb": true,
      "version": "1.0.0",
      "matched": null
    },
    {
      "name": "hash-match-stable",
      "javaMatchesPython": true,
      "pythonMatchesProxyV1": true,
      "pythonMatchesProxyWeb": true,
      "version": "1.0.0",
      "matched": true
    },
    {
      "name": "hash-miss-latest",
      "javaMatchesPython": true,
      "pythonMatchesProxyV1": true,
      "pythonMatchesProxyWeb": true,
      "version": "1.2.0",
      "matched": false
    }
  ],
  "conflict": {
    "name": "version-tag-conflict",
    "javaStatus": 400,
    "pythonStatus": 400,
    "proxyStatus": 400
  },
  "e2eSmoke": "passed"
}
```

## Boundary Check

Required Java boundary check:

```powershell
git diff --name-only -- server
```

Expected and observed output: empty.

## Cleanup Notes

The first fixture attempt used a CTE-style SQL insert and failed the live gate because
`latest_version_id` was not written, so Java correctly returned `error.skill.notFound`. The final
fixture used a PL/pgSQL variable block and verified:

```text
skill_id = 5
latest_version_id = 8
latest_version = 1.2.0
```

During final cleanup, `dev-hybrid.ps1 down` emitted Windows sandbox `taskkill` warnings for
transient wrapper PIDs. Follow-up checks showed:

- no `LISTENING` entries on ports `3000`, `8080`, or `8081`
- only `TIME_WAIT` entries remained
- `docker compose -p skillhub ps` showed no running services after explicit
  `docker compose -p skillhub down --remove-orphans`

## Risks And Follow-Up

- This milestone intentionally supports anonymous public resolve behavior only.
- Auth-specific behavior must not be migrated until the Python auth/session bridge exists.
- `downloadUrl` is returned for contract compatibility, but download execution remains Java-owned.
- Python currently returns FastAPI's default error body for bad requests; live verification confirms
  status parity for the selector conflict. If future frontend code depends on Java's exact error
  envelope for this route, add a Python exception envelope milestone before migrating UI error
  handling.
- Future live gates should reuse a fixture helper instead of embedding SQL in the verification
  command.

# Skill Report Submit Migration Result

## Summary

Moved user-facing skill report submission to FastAPI:

- `POST /api/v1/skills/{namespace}/{slug}/reports`
- `POST /api/web/skills/{namespace}/{slug}/reports`

This completes the report submission side of the governance/report workflow after admin report
list and resolve/dismiss routes had already moved to Python.

## Route Ownership

Before:

- `POST /api/v1/skills/{namespace}/{slug}/reports` -> Java
- `POST /api/web/skills/{namespace}/{slug}/reports` -> Java

After:

- `POST /api/v1/skills/{namespace}/{slug}/reports` -> Python
- `POST /api/web/skills/{namespace}/{slug}/reports` -> Python

## Java Parity

Preserved behavior:

- Requires current user auth.
- Strips leading `@` from namespace during skill lookup.
- Uses Java `Preference.PUBLISHED` semantics: published visible skill first, caller-owned fallback.
- Rejects blank reason, self-report, duplicate pending report, and unavailable hidden/inactive skill.
- Trims `reason` and normalizes blank/missing `details` to `null`.
- Inserts pending `skill_report`.
- Writes `REPORT_SKILL` audit with `{"reportId": <id>}` detail JSON.
- Writes `REPORT_SUBMITTED` notifications to platform `SKILL_ADMIN` and `SUPER_ADMIN` recipients,
  respecting enabled in-app report notification preferences.
- Returns Java-compatible create envelope with `{ reportId, status }`.

Live gate caught and fixed two implementation/gate issues:

- Python initially referenced nonexistent `skill.deleted_at`; Java does not use that column for
  this resolution path, so the query was corrected.
- Notification comparison was changed to compare stable contract fields instead of fixture-specific
  skill names.

## Verification

Commands run:

```powershell
cd server-python
$env:UV_CACHE_DIR='..\.uv-cache'
uv run pytest tests/test_skill_report_submit.py tests/test_hybrid_makefile.py -q

cd ..\web
npx.cmd vitest run vite.config.test.ts

cd ..
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\dev-hybrid.ps1 verify-skill-report-submit-smoke
```

Results:

- Python route/service/hybrid-script tests: `9 passed, 1 warning`.
- Vite proxy tests: `38 passed`.
- Windows live gate: passed.
- Playwright smoke inside live gate: `6 passed`.

Live gate artifact:

- `.dev/skill-report-submit-contract-result.json`

## Risks And Follow-Up

- Notification recipient count depends on current platform role bindings, so the live gate compares
  count and stable notification fields rather than exact recipient ids.
- OAuth/session/bearer-token authentication filters remain Java-owned.
- Remaining governance/report cleanup should focus on any routes still hidden behind the default
  `/api/**` Java fallback.

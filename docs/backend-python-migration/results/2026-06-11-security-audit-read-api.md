# Security Audit Read API Result

Date: 2026-06-11

## Summary

Migrated the authenticated security audit read boundary to Python:

- `GET /api/v1/skills/{skillId}/versions/{versionId}/security-audit`

The Vite dev proxy now routes numeric skill/version audit reads to Python on
`localhost:8081`. Other `/api` fallback traffic remains Java-owned on
`localhost:8080`.

## Routes Changed

| Method | Route | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{skillId}/versions/{versionId}/security-audit` | java | python |

## Behavior Verified

- Requires current user auth; missing `X-Mock-User-Id` returns `401`.
- Version missing or version/skill mismatch raises Java-compatible
  `error.skill.version.notFound`.
- Skill missing raises Java-compatible `error.skill.notFound`.
- Visibility follows the Java `SecurityAuditController` access contract:
  platform admins, namespace owners/admins, owners, public skills, namespace-only
  members, and private managers are handled by the same effective rules.
- No audit rows returns `200` with `data: []`.
- No `scannerType` returns the latest active audit per scanner type ordered by
  scanner type.
- `scannerType=skill-scanner` returns only the latest active skill-scanner audit.
- Scanner type values are converted between Java API values and DB enum values:
  `skill-scanner` <-> `SKILL_SCANNER`, `custom` <-> `CUSTOM`.
- Malformed or blank findings payloads normalize to `[]`, matching Java's tolerant
  DTO mapping behavior.

## Tests And Checks

Passed:

- `cd server-python; $env:UV_CACHE_DIR='..\.uv-cache'; uv run pytest tests/test_security_audit.py tests/test_hybrid_makefile.py -q`
  - `10 passed`
- `cd web; npx.cmd vitest run vite.config.test.ts`
  - `1 passed`, `41 passed`
- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-security-audit-read-smoke`
  - Python pytest: `10 passed`
  - Vite proxy tests: `41 passed`
  - Java/Python/proxy contract checks:
    - `allAuditsEnvelopeMatches: true`
    - `scannerFilterEnvelopeMatches: true`
    - `missingAuditEnvelopeMatches: true`
    - `latestSkillScannerSelected: true`
    - `customScannerIncluded: true`
    - `scannerFilterExcludesCustom: true`
    - `noAuthRejected: true`
  - Playwright smoke: `6 passed`

## Live Gate Notes

The first live-gate attempts caught fixture issues, not API behavior issues:

- Windows shell quoting broke a JSONB fixture with embedded double quotes. The live
  fixture now uses `[]::jsonb`; detailed findings parsing remains covered by
  `tests/test_security_audit.py`.
- The current schema uses `skill(namespace_id, slug, owner_id)` uniqueness, so the
  fixture was updated away from the older `(namespace_id, slug)` assumption.
- PL/pgSQL fixture variables were renamed to avoid ambiguity with table column
  names.

The final live gate passed after those fixture fixes.

## Risks And Follow-Up

- The final auth/session replacement is still deferred; this route uses the
  current local mock-user bridge during migration.
- Invalid `scannerType` currently returns `400` from Python for explicit bad values.
  The migrated valid-value behavior is verified; broader invalid enum parity can be
  revisited during final contract hardening if needed.
- During local teardown, the script can warn about an elevated existing process on
  port `8080`. The milestone contract still passed, and dependency containers were
  removed after the run.

## Boundary Check

No `server/` files were modified.

# Security Audit Read API Migration Plan

## Summary

Move the skill-version security audit read route to FastAPI:

- `GET /api/v1/skills/{skillId}/versions/{versionId}/security-audit`

This is a read-only frontend route used by the security audit UI. It is a good next migration
slice because it depends on a narrow DB table and already has Java controller tests to mirror.

## Route Ownership

| Method | Route | Before | After |
| --- | --- | --- | --- |
| GET | `/api/v1/skills/{skillId}/versions/{versionId}/security-audit` | java | python |

Still Java-owned/deferred:

- scanner task enqueue/worker mutations beyond already-migrated publish scanner foundations
- scanner result write APIs and background processing beyond existing Python scan daemon
- security audit admin mutation/deletion beyond existing lifecycle soft-delete helpers
- final proxy cleanup

## Java Parity Checklist

Reference files:

- `server/skillhub-app/src/main/java/com/iflytek/skillhub/controller/portal/SecurityAuditController.java`
- `server/skillhub-app/src/main/java/com/iflytek/skillhub/dto/SecurityAuditResponse.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/security/SecurityAudit.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/security/ScannerType.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/security/SecurityFinding.java`
- `server/skillhub-infra/src/main/java/com/iflytek/skillhub/infra/jpa/SecurityAuditJpaRepository.java`
- `server/skillhub-domain/src/main/java/com/iflytek/skillhub/domain/skill/VisibilityChecker.java`
- `server/skillhub-app/src/main/resources/db/migration/V35__security_audit.sql`
- `server/skillhub-app/src/main/resources/db/migration/V36__security_audit_timestamptz.sql`

| Area | Status | Notes |
| --- | --- | --- |
| API contract | covered | Preserve Java envelope, response fields, scanner type value mapping, findings deserialization fallback, and latest-per-scanner behavior. |
| Authorization/session behavior | covered | Requires current user. Allows `SUPER_ADMIN`/`SKILL_ADMIN`, namespace `OWNER`/`ADMIN`, or normal `VisibilityChecker` read access. |
| Database transaction atomicity | not applicable | Read-only route. |
| Audit actor/timestamp fields | not applicable | No audit log writes. |
| Storage and side effects | not applicable | No object storage or scanner side effects. |
| Live verification evidence | pending | Windows live gate will compare Java/Python/proxy contract. |

## Behavior Requirements

- Missing auth returns 401.
- Missing version or skill/version mismatch returns 400 with Java-compatible bad request behavior.
- Forbidden viewer returns 403.
- Missing audit returns `200` with empty `data`, not `404`.
- Without `scannerType`, return the latest active audit per scanner type, ordered by scanner type.
- With `scannerType=skill-scanner`, return only the latest active audit for that scanner type.
- Soft-deleted audits are excluded.
- `scanner_type` DB enum names map to Java API values: `SKILL_SCANNER -> skill-scanner`, `CUSTOM -> custom`.
- Blank or malformed `findings` deserializes to an empty list.

## Implementation Scope

Allowed files:

- `server-python/app/security_audit.py`
- `server-python/app/api/security_audit.py`
- `server-python/app/main.py`
- `server-python/tests/test_security_audit.py`
- `server-python/tests/test_hybrid_makefile.py`
- `web/vite.config.ts`
- `web/vite.config.test.ts`
- `scripts/dev-hybrid.ps1`
- `docs/backend-python-migration/**`

Forbidden:

- Any file under `server/`
- `web/src/api/generated/schema.d.ts`

## Verification

Red/green tests:

- `cd server-python; $env:UV_CACHE_DIR='..\.uv-cache'; uv run pytest tests/test_security_audit.py tests/test_hybrid_makefile.py -q`
- `cd web; npx.cmd vitest run vite.config.test.ts`

Live gate:

- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 verify-security-audit-read-smoke`

Final checks:

- `git diff --name-only -- server`
- `git diff --check`

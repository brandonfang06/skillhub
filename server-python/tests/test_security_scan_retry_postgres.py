from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.security_scan_retry import SecurityScanRetryInput, retry_security_scan


TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")


@pytest.mark.skipif(TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL")
@pytest.mark.anyio
async def test_parallel_retry_creates_one_new_attempt_and_one_outbox_intent() -> None:
    engine = create_async_engine(str(TEST_DATABASE_URL), pool_size=2, max_overflow=0)
    suffix = uuid4().hex[:10]
    owner = f"retry-owner-{suffix}"
    namespace_id: int | None = None
    skill_id: int | None = None
    version_id: int | None = None
    now = datetime(2026, 9, 6, 1, 0, tzinfo=UTC)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("INSERT INTO user_account (id, display_name) VALUES (:owner, 'Owner')"), {"owner": owner})
            namespace_id = int((await connection.execute(text("INSERT INTO namespace (slug, display_name, type, status, created_by) VALUES (:slug, :slug, 'TEAM', 'ACTIVE', :owner) RETURNING id"), {"slug": f"retry-{suffix}", "owner": owner})).scalar_one())
            skill_id = int((await connection.execute(text("INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by) VALUES (:namespace_id, 'demo', 'Demo', 'summary', :owner, 'PUBLIC', 'ACTIVE', :owner, :owner) RETURNING id"), {"namespace_id": namespace_id, "owner": owner})).scalar_one())
            version_id = int((await connection.execute(text("INSERT INTO skill_version (skill_id, version, status, created_by, bundle_ready, download_ready) VALUES (:skill_id, '1.0.0', 'SCAN_FAILED', :owner, TRUE, FALSE) RETURNING id"), {"skill_id": skill_id, "owner": owner})).scalar_one())
            old_audit_id = int((await connection.execute(text("INSERT INTO security_audit (skill_version_id, scanner_type, verdict, is_safe, findings_count, findings, task_id, failure_reason, created_at) VALUES (:version_id, 'SKILL_SCANNER', 'ERROR', FALSE, 0, '[]', :task_id, 'provider timeout', :now) RETURNING id"), {"version_id": version_id, "task_id": f"old-{suffix}", "now": now})).scalar_one())
            await connection.execute(text("INSERT INTO local_security_scan_execution (security_audit_id, scan_status, failure_code) VALUES (:audit_id, 'FAILED', 'SCANNER_UNAVAILABLE')"), {"audit_id": old_audit_id})

        request = SecurityScanRetryInput(skill_id=skill_id, version_id=version_id, user_id=owner, platform_roles=set(), scanner_enabled=True, bundle_exists=lambda _key: True, now=now)
        first, second = await asyncio.gather(retry_security_scan(engine, request), retry_security_scan(engine, request))

        assert first["taskId"] == second["taskId"]
        assert first["status"] == "SCANNING"
        async with engine.connect() as connection:
            audits = int((await connection.execute(text("SELECT COUNT(*) FROM security_audit WHERE skill_version_id = :version_id"), {"version_id": version_id})).scalar_one())
            outboxes = int((await connection.execute(text("SELECT COUNT(*) FROM scan_task_outbox WHERE version_id = :version_id"), {"version_id": version_id})).scalar_one())
            retries = int((await connection.execute(text("SELECT COUNT(*) FROM audit_log WHERE action = 'RETRY_SECURITY_SCAN' AND target_id = :version_id"), {"version_id": version_id})).scalar_one())
        assert audits == 2
        assert outboxes == 1
        assert retries == 1
    finally:
        if version_id is not None:
            async with engine.begin() as connection:
                await connection.execute(text("DELETE FROM audit_log WHERE actor_user_id = :owner"), {"owner": owner})
                await connection.execute(text("DELETE FROM scan_task_outbox WHERE version_id = :version_id"), {"version_id": version_id})
                await connection.execute(text("DELETE FROM security_audit WHERE skill_version_id = :version_id"), {"version_id": version_id})
                await connection.execute(text("DELETE FROM skill_version WHERE id = :version_id"), {"version_id": version_id})
                await connection.execute(text("DELETE FROM skill WHERE id = :skill_id"), {"skill_id": skill_id})
                await connection.execute(text("DELETE FROM namespace WHERE id = :namespace_id"), {"namespace_id": namespace_id})
                await connection.execute(text("DELETE FROM user_account WHERE id = :owner"), {"owner": owner})
        await engine.dispose()

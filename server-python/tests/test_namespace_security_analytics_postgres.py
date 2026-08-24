from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.namespace_analytics.security_repository import (
    list_namespace_security_analytics,
    list_namespace_security_skills,
)

TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")

VERSION_STATUSES = [
    "DRAFT",
    "SCANNING",
    "SCAN_FAILED",
    "UPLOADED",
    "PENDING_REVIEW",
    "PUBLISHED",
    "REJECTED",
    "YANKED",
]


class _BorrowedConnectionContext:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    async def __aenter__(self) -> Any:
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


class _BoundEngine:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def connect(self) -> _BorrowedConnectionContext:
        return _BorrowedConnectionContext(self.connection)


async def _insert_audit(
    connection: Any,
    *,
    version_id: int,
    scanner_type: str,
    severity: str | None,
    created_at: datetime,
    findings_count: int = 1,
    deleted: bool = False,
) -> None:
    findings = []
    if severity is not None:
        findings = [
            {
                "ruleId": f"RULE-{severity}",
                "severity": severity,
                "category": "test",
                "title": f"{severity} finding",
                "message": "detected by PostgreSQL integration fixture",
                "filePath": "SKILL.md",
                "lineNumber": 1,
            }
        ]
    await connection.execute(
        text(
            """
            INSERT INTO security_audit (
                skill_version_id,
                scan_id,
                scanner_type,
                verdict,
                is_safe,
                max_severity,
                findings_count,
                findings,
                scanned_at,
                created_at,
                deleted_at
            ) VALUES (
                :version_id,
                :scan_id,
                :scanner_type,
                'DANGEROUS',
                FALSE,
                :severity,
                :findings_count,
                CAST(:findings AS jsonb),
                :created_at,
                :created_at,
                :deleted_at
            )
            """
        ),
        {
            "version_id": version_id,
            "scan_id": f"scan-{uuid4().hex}",
            "scanner_type": scanner_type,
            "severity": severity,
            "findings_count": findings_count,
            "findings": json.dumps(findings),
            "created_at": created_at,
            "deleted_at": created_at if deleted else None,
        },
    )


@pytest.mark.skipif(TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL")
@pytest.mark.anyio
async def test_namespace_security_analytics_includes_every_retained_lifecycle_on_postgres() -> None:
    engine = create_async_engine(TEST_DATABASE_URL)
    suffix = uuid4().hex[:12]
    owner_id = f"security-owner-{suffix}"
    now = datetime(2026, 8, 24, 8, 0, tzinfo=UTC)
    connection = await engine.connect()
    transaction = await connection.begin()
    try:
        await connection.execute(
            text(
                """
                INSERT INTO user_account (id, display_name, email, status)
                VALUES (:owner_id, 'Security Owner', :email, 'ACTIVE')
                """
            ),
            {"owner_id": owner_id, "email": f"{owner_id}@example.test"},
        )
        archived_namespace_id = int(
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO namespace (slug, display_name, type, status, created_by)
                        VALUES (:slug, 'Private Lab', 'TEAM', 'ARCHIVED', :owner_id)
                        RETURNING id
                        """
                    ),
                    {"slug": f"private-lab-{suffix}", "owner_id": owner_id},
                )
            ).scalar_one()
        )
        active_namespace_id = int(
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO namespace (slug, display_name, type, status, created_by)
                        VALUES (:slug, 'Public Lab', 'TEAM', 'ACTIVE', :owner_id)
                        RETURNING id
                        """
                    ),
                    {"slug": f"public-lab-{suffix}", "owner_id": owner_id},
                )
            ).scalar_one()
        )
        private_skill_id = int(
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO skill (
                            namespace_id, slug, display_name, owner_id, visibility,
                            status, hidden, created_by
                        ) VALUES (
                            :namespace_id, 'private-draft', 'Private Draft', :owner_id,
                            'PRIVATE', 'ARCHIVED', TRUE, :owner_id
                        ) RETURNING id
                        """
                    ),
                    {"namespace_id": archived_namespace_id, "owner_id": owner_id},
                )
            ).scalar_one()
        )
        public_skill_id = int(
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO skill (
                            namespace_id, slug, display_name, owner_id, visibility,
                            status, hidden, created_by
                        ) VALUES (
                            :namespace_id, 'public-risk', 'Public Risk', :owner_id,
                            'PUBLIC', 'ACTIVE', FALSE, :owner_id
                        ) RETURNING id
                        """
                    ),
                    {"namespace_id": active_namespace_id, "owner_id": owner_id},
                )
            ).scalar_one()
        )
        severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "CRITICAL", "HIGH", "MEDIUM"]
        private_version_ids: list[int] = []
        for index, (status, severity) in enumerate(zip(VERSION_STATUSES, severities, strict=True)):
            version_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO skill_version (skill_id, version, status, created_by)
                            VALUES (:skill_id, :version, :status, :owner_id)
                            RETURNING id
                            """
                        ),
                        {
                            "skill_id": private_skill_id,
                            "version": f"fixture-{index}",
                            "status": status,
                            "owner_id": owner_id,
                        },
                    )
                ).scalar_one()
            )
            private_version_ids.append(version_id)
            await _insert_audit(
                connection,
                version_id=version_id,
                scanner_type="SKILL_SCANNER",
                severity=severity,
                created_at=now + timedelta(minutes=index),
            )

        await _insert_audit(
            connection,
            version_id=private_version_ids[0],
            scanner_type="SKILL_SCANNER",
            severity="HIGH",
            findings_count=4,
            created_at=now - timedelta(days=1),
        )
        await _insert_audit(
            connection,
            version_id=private_version_ids[0],
            scanner_type="CUSTOM",
            severity="HIGH",
            created_at=now + timedelta(hours=1),
        )

        public_version_id = int(
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO skill_version (skill_id, version, status, created_by)
                        VALUES (:skill_id, 'rejected-1', 'REJECTED', :owner_id)
                        RETURNING id
                        """
                    ),
                    {"skill_id": public_skill_id, "owner_id": owner_id},
                )
            ).scalar_one()
        )
        await _insert_audit(
            connection,
            version_id=public_version_id,
            scanner_type="SKILL_SCANNER",
            severity=None,
            created_at=now + timedelta(hours=2),
        )
        await _insert_audit(
            connection,
            version_id=public_version_id,
            scanner_type="CUSTOM",
            severity="CRITICAL",
            findings_count=5,
            created_at=now + timedelta(hours=3),
            deleted=True,
        )

        bound_engine = _BoundEngine(connection)
        aggregate = await list_namespace_security_analytics(
            bound_engine,
            query=suffix,
            severity="ALL",
            namespace_type="ALL",
            namespace_status="ALL",
            skill_status="ALL",
            visibility="ALL",
            hidden="ALL",
            version_status="ALL",
            scanner_type=None,
            sort="risk",
            direction="desc",
            page=0,
            size=20,
        )

        assert aggregate["summary"] == {
            "affectedNamespaceCount": 2,
            "affectedSkillCount": 2,
            "affectedVersionCount": 9,
            "findingCount": 10,
            "severityCounts": {
                "critical": 2,
                "high": 3,
                "medium": 2,
                "low": 1,
                "info": 1,
                "unclassified": 1,
            },
        }
        assert [item["status"] for item in aggregate["items"]] == ["ARCHIVED", "ACTIVE"]

        skills = await list_namespace_security_skills(
            bound_engine,
            namespace_id=archived_namespace_id,
            query=None,
            severity="ALL",
            skill_status="ALL",
            visibility="ALL",
            hidden="ALL",
            version_status="ALL",
            scanner_type=None,
            sort="risk",
            direction="desc",
            page=0,
            size=20,
        )

        assert skills["total"] == 1
        private_skill = skills["items"][0]
        assert private_skill["visibility"] == "PRIVATE"
        assert private_skill["status"] == "ARCHIVED"
        assert private_skill["hidden"] is True
        assert private_skill["affectedVersionCount"] == 8
        assert private_skill["findingCount"] == 9
        assert {version["status"] for version in private_skill["versions"]} == set(VERSION_STATUSES)
        assert private_skill["versions"][0]["scannerTypes"] == ["custom", "skill-scanner"]

        private_only = await list_namespace_security_analytics(
            bound_engine,
            query=suffix,
            severity="CRITICAL",
            namespace_type="TEAM",
            namespace_status="ARCHIVED",
            skill_status="ARCHIVED",
            visibility="PRIVATE",
            hidden="HIDDEN",
            version_status="ALL",
            scanner_type="skill-scanner",
            sort="risk",
            direction="desc",
            page=0,
            size=20,
        )
        assert private_only["summary"]["affectedNamespaceCount"] == 1
        assert private_only["summary"]["affectedVersionCount"] == 2
        assert private_only["summary"]["findingCount"] == 2
    finally:
        await transaction.rollback()
        await connection.close()
        await engine.dispose()

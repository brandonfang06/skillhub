from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.security_audit import SecurityAuditReadError, list_security_audits


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self.rows

    def one_or_none(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, scalar: Any = None) -> None:
        self.rows = rows or []
        self.scalar = scalar

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)

    def scalar_one_or_none(self) -> Any:
        return self.scalar


class FakeContext:
    def __init__(self, connection: "FakeSecurityAuditConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeSecurityAuditConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeSecurityAuditConnection") -> None:
        self.connection = connection

    def connect(self) -> FakeContext:
        return FakeContext(self.connection)


class FakeSecurityAuditConnection:
    def __init__(self) -> None:
        self.versions = {
            42: {"id": 42, "skill_id": 8},
            43: {"id": 43, "skill_id": 9},
        }
        self.skills = {
            8: {
                "id": 8,
                "owner_id": "owner-1",
                "namespace_id": 5,
                "visibility": "PRIVATE",
                "latest_version_id": None,
                "hidden": False,
            }
        }
        self.namespace_roles = {("team-admin", 5): "ADMIN"}
        self.audits = [
            {
                "id": 7,
                "skill_version_id": 42,
                "scan_id": "scan-old",
                "scanner_type": "SKILL_SCANNER",
                "verdict": "SUSPICIOUS",
                "is_safe": False,
                "max_severity": "MEDIUM",
                "findings_count": 0,
                "findings": [],
                "scan_duration_seconds": None,
                "scanned_at": None,
                "created_at": datetime(2026, 6, 11, 8, 0, tzinfo=UTC),
                "deleted_at": None,
            },
            {
                "id": 8,
                "skill_version_id": 42,
                "scan_id": "scan-latest",
                "scanner_type": "SKILL_SCANNER",
                "verdict": "DANGEROUS",
                "is_safe": False,
                "max_severity": "HIGH",
                "findings_count": 1,
                "findings": [
                    {
                        "ruleId": "STATIC-001",
                        "severity": "HIGH",
                        "category": "code-execution",
                        "title": "Dynamic execution",
                        "message": "avoid eval",
                        "filePath": "src/main.py",
                        "lineNumber": 12,
                        "codeSnippet": "eval(user_input)",
                    }
                ],
                "scan_duration_seconds": 1.25,
                "scanned_at": datetime(2026, 6, 11, 8, 1, tzinfo=UTC),
                "created_at": datetime(2026, 6, 11, 8, 2, tzinfo=UTC),
                "deleted_at": None,
            },
            {
                "id": 9,
                "skill_version_id": 42,
                "scan_id": "custom-latest",
                "scanner_type": "CUSTOM",
                "verdict": "SAFE",
                "is_safe": True,
                "max_severity": "LOW",
                "findings_count": 0,
                "findings": "",
                "scan_duration_seconds": 0.5,
                "scanned_at": datetime(2026, 6, 11, 8, 3, tzinfo=UTC),
                "created_at": datetime(2026, 6, 11, 8, 4, tzinfo=UTC),
                "deleted_at": None,
            },
        ]
        self.statements: list[str] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        bound = params or {}
        normalized = " ".join(sql.split())
        self.statements.append(normalized)
        if "FROM skill_version" in normalized:
            row = self.versions.get(int(bound["version_id"]))
            return FakeResult([row.copy()] if row else [])
        if "FROM skill s" in normalized:
            row = self.skills.get(int(bound["skill_id"]))
            return FakeResult([row.copy()] if row else [])
        if "FROM namespace_member" in normalized:
            return FakeResult(scalar=self.namespace_roles.get((bound["user_id"], int(bound["namespace_id"]))))
        if "FROM security_audit" in normalized and "scanner_type = :scanner_type" in normalized:
            rows = self._latest_for_scanner(int(bound["version_id"]), str(bound["scanner_type"]))
            return FakeResult(rows)
        if "FROM security_audit" in normalized:
            return FakeResult(self._latest_per_scanner(int(bound["version_id"])))
        raise AssertionError(f"unexpected SQL: {sql}")

    def _active_audits(self, version_id: int) -> list[dict[str, Any]]:
        return [
            audit.copy()
            for audit in self.audits
            if audit["skill_version_id"] == version_id and audit["deleted_at"] is None
        ]

    def _latest_for_scanner(self, version_id: int, scanner_type: str) -> list[dict[str, Any]]:
        rows = [audit for audit in self._active_audits(version_id) if audit["scanner_type"] == scanner_type]
        rows.sort(key=lambda audit: audit["created_at"], reverse=True)
        return rows[:1]

    def _latest_per_scanner(self, version_id: int) -> list[dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for audit in self._active_audits(version_id):
            current = latest.get(audit["scanner_type"])
            if current is None or audit["created_at"] > current["created_at"]:
                latest[audit["scanner_type"]] = audit
        return [latest[key] for key in sorted(latest)]


@pytest.mark.anyio
async def test_list_security_audits_returns_latest_active_per_scanner_with_java_shape() -> None:
    result = await list_security_audits(
        FakeEngine(FakeSecurityAuditConnection()),
        skill_id=8,
        version_id=42,
        scanner_type=None,
        current_user_id="owner-1",
        platform_roles=["USER"],
    )

    assert [item["id"] for item in result] == [9, 8]
    assert result[1]["scannerType"] == "skill-scanner"
    assert result[1]["verdict"] == "DANGEROUS"
    assert result[1]["findings"][0]["ruleId"] == "STATIC-001"
    assert result[1]["scannedAt"] == "2026-06-11T08:01:00Z"
    assert result[0]["scannerType"] == "custom"
    assert result[0]["findings"] == []


@pytest.mark.anyio
async def test_list_security_audits_filters_by_scanner_type_value() -> None:
    result = await list_security_audits(
        FakeEngine(FakeSecurityAuditConnection()),
        skill_id=8,
        version_id=42,
        scanner_type="skill-scanner",
        current_user_id="owner-1",
        platform_roles=["USER"],
    )

    assert len(result) == 1
    assert result[0]["id"] == 8


@pytest.mark.anyio
async def test_list_security_audits_enforces_version_skill_and_visibility_rules() -> None:
    engine = FakeEngine(FakeSecurityAuditConnection())

    with pytest.raises(SecurityAuditReadError, match="error.skill.version.notFound") as mismatch:
        await list_security_audits(
            engine,
            skill_id=8,
            version_id=43,
            scanner_type=None,
            current_user_id="owner-1",
            platform_roles=["USER"],
        )
    assert mismatch.value.status_code == 400

    with pytest.raises(SecurityAuditReadError, match="error.forbidden") as forbidden:
        await list_security_audits(
            engine,
            skill_id=8,
            version_id=42,
            scanner_type=None,
            current_user_id="viewer-1",
            platform_roles=["USER"],
        )
    assert forbidden.value.status_code == 403

    assert await list_security_audits(
        engine,
        skill_id=8,
        version_id=42,
        scanner_type=None,
        current_user_id="team-admin",
        platform_roles=["USER"],
    )


def test_security_audit_route_uses_java_envelope_and_auth_boundary() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["SKILL_ADMIN"] if user_id == "skill-admin" else ["USER"],
    }
    app.state.security_audit_reader = lambda skill_id, version_id, scanner_type, user: [
        {
            "id": 7,
            "scanId": "scan-123",
            "scannerType": scanner_type or "skill-scanner",
            "verdict": "SAFE",
            "isSafe": True,
            "maxSeverity": None,
            "findingsCount": 0,
            "findings": [],
            "scanDurationSeconds": None,
            "scannedAt": None,
            "createdAt": "2026-06-11T08:00:00Z",
        }
    ]

    client = TestClient(app)

    assert client.get("/api/v1/skills/8/versions/42/security-audit").status_code == 401
    response = client.get(
        "/api/v1/skills/8/versions/42/security-audit?scannerType=skill-scanner",
        headers={"X-Mock-User-Id": "skill-admin", "X-Request-Id": "security-audit"},
    )

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "security_audit.found"
    assert response.json()["requestId"] == "security-audit"
    assert response.json()["data"][0]["scannerType"] == "skill-scanner"

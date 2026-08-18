from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.admin.audit_logs import AdminAuditLogError, list_admin_audit_logs
from app.main import create_app


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class FakeResult:
    def __init__(
        self, rows: list[dict[str, Any]] | None = None, scalar: int | None = None
    ) -> None:
        self.rows = rows or []
        self.scalar = scalar

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)

    def scalar_one(self) -> int:
        if self.scalar is not None:
            return self.scalar
        return int(self.rows[0]["count"])


class FakeTransaction:
    def __init__(self, connection: FakeAuditConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeAuditConnection:
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: FakeAuditConnection) -> None:
        self.connection = connection

    def connect(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class FakeAuditConnection:
    def __init__(self) -> None:
        self.rows = [
            {
                "id": 2,
                "action": "REVIEW_APPROVE",
                "actor_user_id": "auditor-target",
                "actor_service_principal_id": None,
                "display_name": "Audit Target",
                "service_display_name": None,
                "detail_json": None,
                "target_type": "REVIEW",
                "target_id": 42,
                "request_id": "req-2",
                "client_ip": "127.0.0.2",
                "created_at": datetime(2026, 6, 10, 8, 2, tzinfo=UTC),
            },
            {
                "id": 1,
                "action": "HIDE_SKILL",
                "actor_user_id": "auditor-target",
                "actor_service_principal_id": None,
                "display_name": "Audit Target",
                "service_display_name": None,
                "detail_json": '{"reason":"policy"}',
                "target_type": "SKILL",
                "target_id": 9,
                "request_id": "req-1",
                "client_ip": "127.0.0.1",
                "created_at": datetime(2026, 6, 10, 8, 1, tzinfo=UTC),
            },
        ]
        self.params: list[dict[str, Any]] = []

    async def execute(
        self, statement: object, params: dict[str, Any] | None = None
    ) -> FakeResult:
        sql = str(statement)
        bound = params or {}
        self.params.append(bound)
        rows = self._filtered(bound)
        if "COUNT(*)" in sql:
            return FakeResult(scalar=len(rows))
        if "FROM audit_log" in sql:
            offset = int(bound.get("offset", 0))
            limit = int(bound.get("limit", len(rows)))
            return FakeResult(rows=rows[offset : offset + limit])
        raise AssertionError(f"unexpected SQL: {sql}")

    def _filtered(self, bound: dict[str, Any]) -> list[dict[str, Any]]:
        rows = list(self.rows)
        if bound.get("user_id"):
            rows = [row for row in rows if row["actor_user_id"] == bound["user_id"]]
        if bound.get("action"):
            rows = [row for row in rows if row["action"] == bound["action"]]
        if bound.get("request_id"):
            rows = [row for row in rows if row["request_id"] == bound["request_id"]]
        if bound.get("ip_address"):
            rows = [row for row in rows if row["client_ip"] == bound["ip_address"]]
        if bound.get("resource_type"):
            rows = [row for row in rows if row["target_type"] == bound["resource_type"]]
        if bound.get("resource_id"):
            rows = [
                row for row in rows if str(row["target_id"]) == bound["resource_id"]
            ]
        return sorted(
            [row.copy() for row in rows],
            key=lambda row: row["created_at"],
            reverse=True,
        )


@pytest.mark.anyio
async def test_admin_audit_log_filters_and_projects_java_fields() -> None:
    connection = FakeAuditConnection()

    response = await list_admin_audit_logs(
        FakeEngine(connection),
        page=0,
        size=20,
        user_id=" auditor-target ",
        action=None,
        request_id=None,
        ip_address=None,
        resource_type=None,
        resource_id=None,
        start_time="2026-06-10T08:00:00Z",
        end_time="2026-06-10T08:03:00Z",
        platform_roles=["AUDITOR"],
    )

    assert response["total"] == 2
    assert response["items"][0] == {
        "id": 2,
        "action": "REVIEW_APPROVE",
        "userId": "auditor-target",
        "username": "Audit Target",
        "actorType": "USER",
        "actorId": "auditor-target",
        "actorName": "Audit Target",
        "details": "REVIEW:42",
        "ipAddress": "127.0.0.2",
        "requestId": "req-2",
        "resourceType": "REVIEW",
        "resourceId": "42",
        "timestamp": "2026-06-10T08:02:00Z",
    }
    assert response["items"][1]["details"] == '{"reason":"policy"}'
    assert response["page"] == 0
    assert response["size"] == 20
    assert isinstance(connection.params[0]["start_time"], datetime)
    assert isinstance(connection.params[0]["end_time"], datetime)
    assert connection.params[0]["start_time"].tzinfo is not None


@pytest.mark.anyio
async def test_admin_audit_log_projects_service_actor() -> None:
    connection = FakeAuditConnection()
    connection.rows = [
        {
            "id": 3,
            "action": "SOURCE_IMPORT_SKILL_VERSION",
            "actor_user_id": None,
            "actor_service_principal_id": "svc_importer",
            "display_name": None,
            "service_display_name": "GitLab OSS Importer",
            "detail_json": {},
            "target_type": "SKILL_VERSION",
            "target_id": 8,
            "request_id": "req-3",
            "client_ip": "127.0.0.3",
            "created_at": datetime(2026, 8, 18, 8, 1, tzinfo=UTC),
        }
    ]
    response = await list_admin_audit_logs(
        FakeEngine(connection),
        page=0,
        size=20,
        user_id=None,
        action=None,
        request_id=None,
        ip_address=None,
        resource_type=None,
        resource_id=None,
        start_time=None,
        end_time=None,
        platform_roles=["SUPER_ADMIN"],
    )
    item = response["items"][0]
    assert item["userId"] is None
    assert item["username"] is None
    assert item["actorType"] == "SERVICE"
    assert item["actorId"] == "svc_importer"
    assert item["actorName"] == "GitLab OSS Importer"


@pytest.mark.anyio
async def test_admin_audit_log_requires_auditor_or_super_admin() -> None:
    with pytest.raises(
        AdminAuditLogError, match="error.admin.auditLog.readDenied"
    ) as denied:
        await list_admin_audit_logs(
            FakeEngine(FakeAuditConnection()),
            page=0,
            size=20,
            user_id=None,
            action=None,
            request_id=None,
            ip_address=None,
            resource_type=None,
            resource_id=None,
            start_time=None,
            end_time=None,
            platform_roles=["USER"],
        )

    assert denied.value.status_code == 403


def test_admin_audit_log_route_uses_read_envelope_and_roles() -> None:
    app = create_app()
    captured_payloads: list[dict[str, Any]] = []
    app.state.auth_me_reader = lambda user_id: {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["AUDITOR"] if user_id == "auditor" else ["USER"],
    }

    def read_audit_logs(
        payload: dict[str, Any], user: dict[str, Any]
    ) -> dict[str, Any]:
        captured_payloads.append(payload)
        return {
            "items": [{"id": 1}],
            "total": 1,
            "page": payload["page"],
            "size": payload["size"],
        }

    app.state.admin_audit_log_reader = read_audit_logs
    client = TestClient(app)

    assert client.get("/api/v1/admin/audit-logs").status_code == 401
    assert (
        client.get(
            "/api/v1/admin/audit-logs", headers={"X-Mock-User-Id": "user"}
        ).status_code
        == 403
    )

    response = client.get(
        "/api/v1/admin/audit-logs?page=1&size=5&startTime=2026-06-10T08:00:00Z&endTime=2026-06-10T08:03:00Z",
        headers={"X-Mock-User-Id": "auditor"},
    )
    assert response.status_code == 200
    assert response.json()["msg"] == "\u83b7\u53d6\u6210\u529f"
    assert response.json()["data"] == {
        "items": [{"id": 1}],
        "total": 1,
        "page": 1,
        "size": 5,
    }
    assert isinstance(captured_payloads[-1]["startTime"], datetime)
    assert isinstance(captured_payloads[-1]["endTime"], datetime)

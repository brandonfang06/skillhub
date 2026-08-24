from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.namespace_analytics import security_repository
from scripts.export_namespace_analytics_openapi import build_openapi_schema


class _FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def one(self) -> dict[str, Any]:
        assert len(self.rows) == 1
        return self.rows[0]

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def mappings(self) -> _FakeMappings:
        return _FakeMappings(self.rows)


class _FakeConnection:
    def __init__(self) -> None:
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any]) -> _FakeResult:
        sql = str(statement)
        self.params.append(params)
        if "namespace-security-summary" in sql:
            return _FakeResult(
                [
                    {
                        "namespace_count": 1,
                        "skill_count": 2,
                        "version_count": 3,
                        "finding_count": 7,
                        "critical_count": 1,
                        "high_count": 2,
                        "medium_count": 1,
                        "low_count": 1,
                        "info_count": 1,
                        "unclassified_count": 1,
                    }
                ]
            )
        if "namespace-security-items" in sql:
            return _FakeResult(
                [
                    {
                        "namespace_id": 9,
                        "slug": "private-lab",
                        "display_name": "Private Lab",
                        "type": "TEAM",
                        "status": "ARCHIVED",
                        "skill_count": 2,
                        "version_count": 3,
                        "finding_count": 7,
                        "critical_count": 1,
                        "high_count": 2,
                        "medium_count": 1,
                        "low_count": 1,
                        "info_count": 1,
                        "unclassified_count": 1,
                        "latest_scan_at": datetime(2026, 8, 24, 8, 0, tzinfo=UTC),
                    }
                ]
            )
        if "namespace-security-skill-total" in sql:
            return _FakeResult([{"skill_count": 1}])
        if "namespace-security-skill-items" in sql:
            return _FakeResult(
                [
                    {
                        "skill_id": 44,
                        "slug": "private-draft",
                        "display_name": "Private Draft",
                        "owner_id": "owner-1",
                        "owner_display_name": "Owner One",
                        "visibility": "PRIVATE",
                        "status": "ARCHIVED",
                        "hidden": True,
                        "version_count": 1,
                        "finding_count": 2,
                        "critical_count": 0,
                        "high_count": 2,
                        "medium_count": 0,
                        "low_count": 0,
                        "info_count": 0,
                        "unclassified_count": 0,
                        "latest_scan_at": datetime(2026, 8, 24, 9, 0, tzinfo=UTC),
                    }
                ]
            )
        if "namespace-security-version-items" in sql:
            return _FakeResult(
                [
                    {
                        "skill_id": 44,
                        "version_id": 55,
                        "version": "draft-1",
                        "status": "UPLOADED",
                        "finding_count": 2,
                        "critical_count": 0,
                        "high_count": 2,
                        "medium_count": 0,
                        "low_count": 0,
                        "info_count": 0,
                        "unclassified_count": 0,
                        "latest_scan_at": datetime(2026, 8, 24, 9, 0, tzinfo=UTC),
                        "scanner_types": ["CUSTOM", "SKILL_SCANNER"],
                    }
                ]
            )
        raise AssertionError(f"Unexpected SQL: {sql}")


class _FakeConnectionContext:
    def __init__(self, connection: _FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _FakeConnection:
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


class _FakeEngine:
    def __init__(self, connection: _FakeConnection) -> None:
        self.connection = connection

    def connect(self) -> _FakeConnectionContext:
        return _FakeConnectionContext(self.connection)


def _auth_user(user_id: str, roles: list[str]) -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": roles,
    }


def test_namespace_security_analytics_route_returns_affected_inventory() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: _auth_user(user_id, ["SUPER_ADMIN"])
    app.state.namespace_security_analytics_reader = lambda **_kwargs: {
        "summary": {
            "affectedNamespaceCount": 1,
            "affectedSkillCount": 2,
            "affectedVersionCount": 3,
            "findingCount": 7,
            "severityCounts": {
                "critical": 1,
                "high": 2,
                "medium": 1,
                "low": 1,
                "info": 1,
                "unclassified": 1,
            },
        },
        "items": [
            {
                "namespaceId": 9,
                "slug": "private-lab",
                "displayName": "Private Lab",
                "type": "TEAM",
                "status": "ARCHIVED",
                "affectedSkillCount": 2,
                "affectedVersionCount": 3,
                "findingCount": 7,
                "severityCounts": {
                    "critical": 1,
                    "high": 2,
                    "medium": 1,
                    "low": 1,
                    "info": 1,
                    "unclassified": 1,
                },
                "maxSeverity": "CRITICAL",
                "latestScanAt": "2026-08-24T08:00:00Z",
            }
        ],
        "page": 0,
        "size": 20,
        "total": 1,
    }
    client = TestClient(app)

    response = client.get(
        "/api/v1/admin/namespace-analytics/security",
        headers={
            "X-Mock-User-Id": "platform-admin",
            "X-Request-Id": "namespace-security-test",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["requestId"] == "namespace-security-test"
    assert body["data"]["summary"]["affectedNamespaceCount"] == 1
    assert body["data"]["summary"]["severityCounts"]["critical"] == 1
    assert body["data"]["items"][0]["status"] == "ARCHIVED"


def test_namespace_security_skills_route_returns_private_version_provenance() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: _auth_user(user_id, ["SUPER_ADMIN"])
    app.state.namespace_security_skills_reader = lambda **_kwargs: {
        "items": [
            {
                "skillId": 44,
                "slug": "private-draft",
                "displayName": "Private Draft",
                "ownerId": "owner-1",
                "ownerDisplayName": "Owner One",
                "visibility": "PRIVATE",
                "status": "ARCHIVED",
                "hidden": True,
                "affectedVersionCount": 1,
                "findingCount": 2,
                "severityCounts": {
                    "critical": 0,
                    "high": 2,
                    "medium": 0,
                    "low": 0,
                    "info": 0,
                    "unclassified": 0,
                },
                "maxSeverity": "HIGH",
                "latestScanAt": "2026-08-24T09:00:00Z",
                "versions": [
                    {
                        "versionId": 55,
                        "version": "draft-1",
                        "status": "UPLOADED",
                        "findingCount": 2,
                        "severityCounts": {
                            "critical": 0,
                            "high": 2,
                            "medium": 0,
                            "low": 0,
                            "info": 0,
                            "unclassified": 0,
                        },
                        "maxSeverity": "HIGH",
                        "latestScanAt": "2026-08-24T09:00:00Z",
                        "scannerTypes": ["skill-scanner"],
                    }
                ],
            }
        ],
        "page": 0,
        "size": 20,
        "total": 1,
    }
    client = TestClient(app)

    response = client.get(
        "/api/v1/admin/namespace-analytics/security/namespaces/9/skills",
        headers={"X-Mock-User-Id": "platform-admin"},
    )

    assert response.status_code == 200
    item = response.json()["data"]["items"][0]
    assert item["visibility"] == "PRIVATE"
    assert item["hidden"] is True
    assert item["versions"][0]["status"] == "UPLOADED"
    assert item["versions"][0]["scannerTypes"] == ["skill-scanner"]


def test_namespace_security_skills_route_rejects_nonpositive_namespace_id() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: _auth_user(user_id, ["SUPER_ADMIN"])
    app.state.namespace_security_skills_reader = lambda **_kwargs: {
        "items": [],
        "page": 0,
        "size": 20,
        "total": 0,
    }
    client = TestClient(app)

    response = client.get(
        "/api/v1/admin/namespace-analytics/security/namespaces/0/skills",
        headers={"X-Mock-User-Id": "platform-admin"},
    )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_namespace_security_analytics_projects_filters_and_severity_totals() -> None:
    connection = _FakeConnection()

    result = await security_repository.list_namespace_security_analytics(
        _FakeEngine(connection),
        query=" private ",
        severity="HIGH",
        namespace_type="ALL",
        namespace_status="ARCHIVED",
        skill_status="ARCHIVED",
        visibility="PRIVATE",
        hidden="HIDDEN",
        version_status="UPLOADED",
        scanner_type="skill-scanner",
        sort="risk",
        direction="desc",
        page=0,
        size=20,
    )

    assert result["summary"] == {
        "affectedNamespaceCount": 1,
        "affectedSkillCount": 2,
        "affectedVersionCount": 3,
        "findingCount": 7,
        "severityCounts": {
            "critical": 1,
            "high": 2,
            "medium": 1,
            "low": 1,
            "info": 1,
            "unclassified": 1,
        },
    }
    assert result["items"][0]["maxSeverity"] == "CRITICAL"
    assert result["items"][0]["latestScanAt"] == datetime(2026, 8, 24, 8, 0, tzinfo=UTC)
    assert connection.params[0]["query"] == "%private%"
    assert connection.params[0]["severity"] == "HIGH"
    assert connection.params[0]["namespace_status"] == "ARCHIVED"
    assert connection.params[0]["skill_status"] == "ARCHIVED"
    assert connection.params[0]["visibility"] == "PRIVATE"
    assert connection.params[0]["hidden"] is True
    assert connection.params[0]["version_status"] == "UPLOADED"
    assert connection.params[0]["scanner_type"] == "SKILL_SCANNER"


@pytest.mark.anyio
async def test_namespace_security_skills_projects_affected_versions() -> None:
    connection = _FakeConnection()

    result = await security_repository.list_namespace_security_skills(
        _FakeEngine(connection),
        namespace_id=9,
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

    assert result == {
        "items": [
            {
                "skillId": 44,
                "slug": "private-draft",
                "displayName": "Private Draft",
                "ownerId": "owner-1",
                "ownerDisplayName": "Owner One",
                "visibility": "PRIVATE",
                "status": "ARCHIVED",
                "hidden": True,
                "affectedVersionCount": 1,
                "findingCount": 2,
                "severityCounts": {
                    "critical": 0,
                    "high": 2,
                    "medium": 0,
                    "low": 0,
                    "info": 0,
                    "unclassified": 0,
                },
                "maxSeverity": "HIGH",
                "latestScanAt": datetime(2026, 8, 24, 9, 0, tzinfo=UTC),
                "versions": [
                    {
                        "versionId": 55,
                        "version": "draft-1",
                        "status": "UPLOADED",
                        "findingCount": 2,
                        "severityCounts": {
                            "critical": 0,
                            "high": 2,
                            "medium": 0,
                            "low": 0,
                            "info": 0,
                            "unclassified": 0,
                        },
                        "maxSeverity": "HIGH",
                        "latestScanAt": datetime(2026, 8, 24, 9, 0, tzinfo=UTC),
                        "scannerTypes": ["custom", "skill-scanner"],
                    }
                ],
            }
        ],
        "page": 0,
        "size": 20,
        "total": 1,
    }
    assert connection.params[0]["namespace_id"] == 9
    assert connection.params[1]["limit"] == 20
    assert connection.params[2]["skill_ids"] == [44]


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/admin/namespace-analytics/security",
        "/api/v1/admin/namespace-analytics/security/namespaces/9/skills",
    ],
)
def test_namespace_security_routes_require_authentication(path: str) -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get(path)

    assert response.status_code == 401
    assert response.json()["detail"] == "error.auth.required"


@pytest.mark.parametrize("roles", [["USER"], ["SKILL_ADMIN"], ["AUDITOR"]])
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/admin/namespace-analytics/security",
        "/api/v1/admin/namespace-analytics/security/namespaces/9/skills",
    ],
)
def test_namespace_security_routes_require_super_admin(path: str, roles: list[str]) -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: _auth_user(user_id, roles)
    client = TestClient(app)

    response = client.get(path, headers={"X-Mock-User-Id": "not-super-admin"})

    assert response.status_code == 403
    assert response.json()["detail"] == "error.admin.superAdminRequired"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/admin/namespace-analytics/security",
        "/api/v1/admin/namespace-analytics/security/namespaces/9/skills",
    ],
)
def test_namespace_security_routes_reject_bearer_api_tokens(path: str) -> None:
    app = create_app()
    app.state.auth_bearer_reader = lambda token: {
        **_auth_user("token-admin", ["SUPER_ADMIN"]),
        "oauthProvider": "api_token",
    }
    client = TestClient(app)

    response = client.get(path, headers={"Authorization": "Bearer valid"})

    assert response.status_code == 403
    assert response.json()["msg"] == "error.apiToken.endpoint.unsupported"
    assert response.json()["data"]["args"] == [path]


def test_namespace_security_openapi_exposes_both_typed_routes() -> None:
    schema = build_openapi_schema()

    assert "/api/v1/admin/namespace-analytics/security" in schema["paths"]
    assert (
        "/api/v1/admin/namespace-analytics/security/namespaces/{namespace_id}/skills"
        in schema["paths"]
    )
    assert "NamespaceSecurityAnalyticsEnvelope" in schema["components"]["schemas"]
    assert "NamespaceSecuritySkillsEnvelope" in schema["components"]["schemas"]

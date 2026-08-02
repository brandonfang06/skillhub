from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.admin.search import rebuild_search_index, upsert_skill_search_document
from app.main import create_app


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self.rows

    def one_or_none(self) -> dict[str, Any] | None:
        if not self.rows:
            return None
        if len(self.rows) != 1:
            raise AssertionError(f"expected at most one row, got {len(self.rows)}")
        return self.rows[0]


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)


class FakeTransaction:
    def __init__(self, connection: "FakeSearchConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeSearchConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeSearchConnection") -> None:
        self.connection = connection

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class FakeSearchConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.documents: dict[int, dict[str, Any]] = {}
        self.audit_rows: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        bound = params or {}
        self.statements.append(sql)
        self.params.append(bound)
        if "FROM skill s" in sql and "WHERE s.id = :skill_id" in sql:
            return FakeResult(
                [
                    {
                        "skill_id": int(bound["skill_id"]),
                        "namespace_id": 7,
                        "namespace_slug": "global",
                        "owner_id": "owner-a",
                        "slug": "agent-helper",
                        "display_name": "Agent Helper",
                        "summary": "Helps agents",
                        "visibility": "PUBLIC",
                        "status": "ACTIVE",
                        "parsed_metadata_json": None,
                    }
                ]
            )
        if "FROM skill s" in sql and "LEFT JOIN namespace" in sql:
            return FakeResult(
                [
                    {
                        "skill_id": 10,
                        "namespace_id": 7,
                        "namespace_slug": "global",
                        "owner_id": "owner-a",
                        "slug": "agent-helper",
                        "display_name": "Agent Helper",
                        "summary": "Helps agents",
                        "visibility": "PUBLIC",
                        "status": "ACTIVE",
                        "parsed_metadata_json": json.dumps(
                            {
                                "frontmatter": {
                                    "keywords": ["ops", "agent"],
                                    "x-category": "Developer Tools",
                                    "name": "Ignored reserved name",
                                }
                            }
                        ),
                    },
                    {
                        "skill_id": 11,
                        "namespace_id": 7,
                        "namespace_slug": "global",
                        "owner_id": "owner-b",
                        "slug": "hidden-skill",
                        "display_name": "Hidden Skill",
                        "summary": "Should not be selected",
                        "visibility": "PUBLIC",
                        "status": "HIDDEN",
                        "parsed_metadata_json": None,
                    },
                ]
            )
        if "FROM skill_label" in sql:
            return FakeResult([{"skill_id": 10, "display_name": "Featured"}])
        if "INSERT INTO skill_search_document" in sql:
            self.documents[int(bound["skill_id"])] = bound.copy()
            return FakeResult()
        if "INSERT INTO audit_log" in sql:
            self.audit_rows.append(bound.copy())
            return FakeResult()
        raise AssertionError(f"unexpected SQL: {sql}")


def auth_user(user_id: str = "admin", roles: list[str] | None = None) -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": roles or ["SUPER_ADMIN"],
    }


def bearer_user(user_id: str = "token-admin", roles: list[str] | None = None) -> dict[str, object]:
    data = auth_user(user_id, roles or ["SUPER_ADMIN"])
    data["oauthProvider"] = "api_token"
    data["tokenScopes"] = ["skill:read", "token:manage", "skill:publish", "skill:delete"]
    return data


def test_admin_search_rebuild_route_requires_super_admin() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user(user_id, ["USER"])
    app.state.admin_search_rebuild_writer = lambda *_args, **_kwargs: None

    client = TestClient(app)

    assert client.post("/api/v1/admin/search/rebuild").status_code == 401
    forbidden = client.post("/api/v1/admin/search/rebuild", headers={"X-Mock-User-Id": "user"})
    assert forbidden.status_code == 403


def test_admin_search_rebuild_rejects_api_token_principals_as_unsupported() -> None:
    app = create_app()
    app.state.auth_bearer_reader = lambda raw_token: bearer_user() if raw_token == "sk_valid" else None
    app.state.auth_me_reader = lambda user_id: auth_user(user_id, ["SUPER_ADMIN"])
    app.state.admin_search_rebuild_writer = lambda *_args, **_kwargs: None

    client = TestClient(app)

    unsupported = client.post("/api/v1/admin/search/rebuild", headers={"Authorization": "Bearer sk_valid"})
    assert unsupported.status_code == 403
    payload = unsupported.json()
    assert payload["msg"] == "error.apiToken.endpoint.unsupported"
    assert payload["data"]["args"] == ["/api/v1/admin/search/rebuild"]
    assert payload["requestId"] == unsupported.headers["X-Request-Id"]

    invalid = client.post("/api/v1/admin/search/rebuild", headers={"Authorization": "Bearer sk_missing"})
    assert invalid.status_code == 401
    assert invalid.json()["detail"] == "error.auth.required"

    mock_precedence = client.post(
        "/api/v1/admin/search/rebuild",
        headers={"X-Mock-User-Id": "admin", "Authorization": "Bearer sk_valid"},
    )
    assert mock_precedence.status_code == 200


def test_admin_search_rebuild_route_returns_java_success_envelope_and_calls_writer() -> None:
    seen: list[dict[str, Any]] = []
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user(user_id, ["SUPER_ADMIN"])

    def writer(user: dict[str, Any], context: dict[str, str | None]) -> None:
        seen.append({"user": user, "context": context})

    app.state.admin_search_rebuild_writer = writer

    client = TestClient(app)
    response = client.post(
        "/api/v1/admin/search/rebuild",
        headers={"X-Mock-User-Id": " admin ", "X-Request-Id": "req-search", "User-Agent": "pytest"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["msg"] == "\u66f4\u65b0\u6210\u529f"
    assert body["data"] is None
    assert seen[0]["user"]["userId"] == "admin"
    assert seen[0]["context"]["request_id"] == "req-search"
    assert seen[0]["context"]["user_agent"] == "pytest"


@pytest.mark.anyio
async def test_rebuild_search_index_indexes_active_skills_and_writes_audit() -> None:
    connection = FakeSearchConnection()

    rebuilt = await rebuild_search_index(
        FakeEngine(connection),
        actor_user_id="admin",
        platform_roles=["SUPER_ADMIN"],
        request_id="req-rebuild",
        client_ip="127.0.0.1",
        user_agent="pytest",
    )

    assert rebuilt == {"rebuilt": 1}
    assert set(connection.documents) == {10}
    document = connection.documents[10]
    active_skill_query = next(statement for statement in connection.statements if "FROM skill s" in statement)
    assert "JOIN LATERAL" in active_skill_query
    assert "sv.skill_id = s.id" in active_skill_query
    assert "sv.status = 'PUBLISHED'" in active_skill_query
    normalized_active_query = " ".join(active_skill_query.split())
    assert "EXISTS (" in normalized_active_query
    assert "SELECT 1 FROM skill_file sf WHERE sf.version_id = sv.id" in normalized_active_query
    assert "CASE WHEN sv.id = s.latest_version_id THEN 0 ELSE 1 END" in " ".join(active_skill_query.split())
    assert any("CAST(sv.parsed_metadata_json AS text)" in statement for statement in connection.statements)
    assert all("parsed_metadata_json::text" not in statement for statement in connection.statements)
    assert document["namespace_slug"] == "global"
    assert document["owner_id"] == "owner-a"
    assert document["title"] == "Agent Helper"
    assert document["summary"] == "Helps agents"
    assert "ops" in document["keywords"]
    assert "agent" in document["keywords"]
    assert "Featured" in document["keywords"]
    assert "x-category" in document["search_text"]
    assert "Developer Tools" in document["search_text"]
    assert document["visibility"] == "PUBLIC"
    assert document["status"] == "ACTIVE"
    assert isinstance(document["updated_at"], datetime)
    assert document["updated_at"].tzinfo is None
    assert isinstance(document["semantic_vector"], str)
    assert len(document["semantic_vector"].split(",")) == 64
    assert connection.audit_rows[-1]["actor_user_id"] == "admin"
    assert connection.audit_rows[-1]["action"] == "REBUILD_SEARCH_INDEX"
    assert connection.audit_rows[-1]["target_type"] == "SEARCH_INDEX"
    assert connection.audit_rows[-1]["target_id"] is None
    assert connection.audit_rows[-1]["request_id"] == "req-rebuild"
    assert connection.audit_rows[-1]["client_ip"] == "127.0.0.1"
    assert connection.audit_rows[-1]["user_agent"] == "pytest"
    assert connection.audit_rows[-1]["detail_json"] == '{"scope":"ALL"}'
    assert isinstance(connection.audit_rows[-1]["created_at"], datetime)
    assert connection.audit_rows[-1]["created_at"].tzinfo is None


@pytest.mark.anyio
async def test_upsert_search_document_uses_published_fallback_with_files() -> None:
    connection = FakeSearchConnection()

    await upsert_skill_search_document(connection, 10)

    source_query = next(
        statement
        for statement in connection.statements
        if "FROM skill s" in statement and "WHERE s.id = :skill_id" in statement
    )
    assert "JOIN LATERAL" in source_query
    assert "sv.skill_id = s.id" in source_query
    normalized_source_query = " ".join(source_query.split())
    assert "EXISTS (" in normalized_source_query
    assert "SELECT 1 FROM skill_file sf WHERE sf.version_id = sv.id" in normalized_source_query
    assert "JOIN skill_version sv ON sv.id = s.latest_version_id" not in source_query

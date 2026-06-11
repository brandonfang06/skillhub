from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.lifecycle.hard_delete import SkillHardDeleteInput, SkillHardDeleteError, hard_delete_skill
from app.main import create_app


class FakeResult:
    def __init__(self, row: dict[str, Any] | None = None, rows: list[dict[str, Any]] | None = None, rowcount: int = 1):
        self.row = row
        self.rows = rows or []
        self.rowcount = rowcount

    def mappings(self) -> "FakeResult":
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        return self.row

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class FakeHardDeleteConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.skill_rows = [
            {
                "skill_id": 10,
                "namespace_id": 1,
                "namespace_slug": "team",
                "skill_slug": "demo",
                "owner_id": "owner-1",
                "latest_version_id": 102,
            }
        ]
        self.version_rows = [{"version_id": 101}, {"version_id": 102}]
        self.file_rows = [
            {"version_id": 101, "storage_key": "skills/10/101/SKILL.md"},
            {"version_id": 102, "storage_key": "skills/10/102/SKILL.md"},
        ]

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        bound = params or {}
        self.statements.append(sql)
        self.params.append(bound)

        if "FROM skill s" in sql and "JOIN namespace n" in sql and "WHERE s.id = :skill_id" in sql:
            skill_id = bound["skill_id"]
            return FakeResult(row=next((row for row in self.skill_rows if row["skill_id"] == skill_id), None))
        if "FROM skill s" in sql and "JOIN namespace n" in sql and "WHERE n.slug = :namespace_slug" in sql:
            matches = [
                row
                for row in self.skill_rows
                if row["namespace_slug"] == bound["namespace_slug"] and row["skill_slug"] == bound["skill_slug"]
            ]
            return FakeResult(rows=matches)
        if "FROM skill_version" in sql and "WHERE skill_id = :skill_id" in sql:
            return FakeResult(rows=self.version_rows)
        if "FROM skill_file" in sql and "WHERE version_id = ANY" in sql:
            return FakeResult(rows=self.file_rows)
        if "DELETE FROM skill" in sql:
            return FakeResult(rowcount=1)
        return FakeResult()


class FakeBegin:
    def __init__(self, connection: FakeHardDeleteConnection):
        self.connection = connection

    async def __aenter__(self) -> FakeHardDeleteConnection:
        return self.connection

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: FakeHardDeleteConnection):
        self.connection = connection

    def begin(self) -> FakeBegin:
        return FakeBegin(self.connection)


def normalized(sql: str) -> str:
    return " ".join(sql.split())


def test_hard_delete_skill_deletes_java_artifacts_and_storage(tmp_path: Path) -> None:
    connection = FakeHardDeleteConnection()
    for key in ["skills/10/101/SKILL.md", "skills/10/102/SKILL.md", "packages/10/101/bundle.zip", "packages/10/102/bundle.zip"]:
        path = tmp_path / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture", encoding="utf-8")

    result = asyncio.run(
        hard_delete_skill(
            FakeEngine(connection),
            SkillHardDeleteInput(
                route_scope="web",
                skill_id=10,
                namespace=None,
                slug=None,
                owner_id=None,
                actor_user_id="owner-1",
                actor_platform_roles=["USER"],
                storage_base_path=str(tmp_path),
                request_id="req-hard-delete",
                client_ip="127.0.0.1",
                user_agent="pytest",
                now=datetime(2026, 6, 11, tzinfo=UTC),
            ),
        )
    )

    assert result == {"skillId": 10, "namespace": "team", "slug": "demo", "deleted": True}
    assert not (tmp_path / "skills/10/101/SKILL.md").exists()
    assert not (tmp_path / "packages/10/102/bundle.zip").exists()
    ordered = [normalized(sql) for sql in connection.statements]
    assert any("DELETE FROM skill_search_document WHERE skill_id = :skill_id" in sql for sql in ordered)
    assert any("UPDATE skill SET latest_version_id = NULL" in sql and "updated_by = :actor_user_id" in sql for sql in ordered)
    assert any("DELETE FROM review_task WHERE skill_version_id = ANY" in sql for sql in ordered)
    assert any("DELETE FROM promotion_request WHERE source_skill_id = :skill_id OR target_skill_id = :skill_id" in sql for sql in ordered)
    assert any("DELETE FROM security_audit WHERE skill_version_id = :version_id" in sql for sql in ordered)
    assert any("DELETE FROM skill_version WHERE skill_id = :skill_id" in sql for sql in ordered)
    assert any("DELETE FROM skill WHERE id = :skill_id" in sql for sql in ordered)
    audit_params = next(params for sql, params in zip(ordered, connection.params, strict=False) if "INSERT INTO audit_log" in sql)
    assert audit_params["action"] == "DELETE_SKILL_HARD"
    assert audit_params["actor_user_id"] == "owner-1"
    assert audit_params["target_id"] == 10


def test_slug_delete_is_idempotent_when_target_missing_or_ambiguous(tmp_path: Path) -> None:
    missing = FakeHardDeleteConnection()
    missing.skill_rows = []
    missing_result = asyncio.run(
        hard_delete_skill(
            FakeEngine(missing),
            SkillHardDeleteInput(
                route_scope="v1",
                skill_id=None,
                namespace="@team",
                slug="missing",
                owner_id=None,
                actor_user_id="admin",
                actor_platform_roles=["SUPER_ADMIN"],
                storage_base_path=str(tmp_path),
            ),
        )
    )
    assert missing_result == {"skillId": None, "namespace": "team", "slug": "missing", "deleted": False}

    ambiguous = FakeHardDeleteConnection()
    ambiguous.skill_rows.append({**ambiguous.skill_rows[0], "skill_id": 11, "owner_id": "admin"})
    ambiguous_result = asyncio.run(
        hard_delete_skill(
            FakeEngine(ambiguous),
            SkillHardDeleteInput(
                route_scope="v1",
                skill_id=None,
                namespace="team",
                slug="demo",
                owner_id=None,
                actor_user_id="admin",
                actor_platform_roles=["SUPER_ADMIN"],
                storage_base_path=str(tmp_path),
            ),
        )
    )
    assert ambiguous_result == {"skillId": None, "namespace": "team", "slug": "demo", "deleted": False}

    web_ambiguous = FakeHardDeleteConnection()
    web_ambiguous.skill_rows.append({**web_ambiguous.skill_rows[0], "skill_id": 11, "owner_id": "owner-2"})
    web_result = asyncio.run(
        hard_delete_skill(
            FakeEngine(web_ambiguous),
            SkillHardDeleteInput(
                route_scope="web",
                skill_id=None,
                namespace="team",
                slug="demo",
                owner_id=None,
                actor_user_id="owner-1",
                actor_platform_roles=["USER"],
                storage_base_path=str(tmp_path),
            ),
        )
    )
    assert web_result == {"skillId": 10, "namespace": "team", "slug": "demo", "deleted": True}


def test_hard_delete_authorization_matches_java_portal_and_v1(tmp_path: Path) -> None:
    with pytest.raises(SkillHardDeleteError, match="error.admin.superAdminRequired"):
        asyncio.run(
            hard_delete_skill(
                FakeEngine(FakeHardDeleteConnection()),
                SkillHardDeleteInput(
                    route_scope="v1",
                    skill_id=None,
                    namespace="team",
                    slug="demo",
                    owner_id=None,
                    actor_user_id="owner-1",
                    actor_platform_roles=["USER"],
                    storage_base_path=str(tmp_path),
                ),
            )
        )

    with pytest.raises(SkillHardDeleteError, match="error.forbidden"):
        asyncio.run(
            hard_delete_skill(
                FakeEngine(FakeHardDeleteConnection()),
                SkillHardDeleteInput(
                    route_scope="web",
                    skill_id=None,
                    namespace="team",
                    slug="demo",
                    owner_id=None,
                    actor_user_id="other-user",
                    actor_platform_roles=["USER"],
                    storage_base_path=str(tmp_path),
                ),
            )
        )


def test_skill_hard_delete_routes_return_java_envelopes(tmp_path: Path) -> None:
    app = create_app()

    def auth_user(user_id: str) -> dict[str, object]:
        return {
            "userId": user_id,
            "displayName": user_id,
            "email": f"{user_id}@example.com",
            "avatarUrl": "",
            "platformRoles": ["SUPER_ADMIN"] if user_id == "admin" else ["USER"],
        }

    seen: list[SkillHardDeleteInput] = []

    async def writer(delete_input: SkillHardDeleteInput) -> dict[str, Any]:
        seen.append(delete_input)
        return {
            "skillId": delete_input.skill_id or 10,
            "namespace": delete_input.namespace or "team",
            "slug": delete_input.slug or "demo",
            "deleted": True,
        }

    app.state.auth_me_reader = auth_user
    app.state.skill_hard_delete_writer = writer
    app.state.storage_base_path = str(tmp_path)
    client = TestClient(app)

    v1 = client.delete("/api/v1/skills/team/demo?ownerId=owner-1", headers={"X-Mock-User-Id": "admin", "X-Request-Id": "hard-delete-v1"})
    assert v1.status_code == 200
    assert v1.json()["msg"] == "\u5220\u9664\u6210\u529f"
    assert v1.json()["requestId"] == "hard-delete-v1"
    assert v1.json()["data"] == {"skillId": 10, "namespace": "team", "slug": "demo", "deleted": True}
    assert seen[-1].route_scope == "v1"
    assert seen[-1].owner_id == "owner-1"

    web = client.delete("/api/web/skills/id/10", headers={"X-Mock-User-Id": "owner"})
    assert web.status_code == 200
    assert web.json()["msg"] == "\u5220\u9664\u6210\u529f"
    assert seen[-1].route_scope == "web"
    assert seen[-1].skill_id == 10

    assert client.delete("/api/v1/skills/team/demo", headers={"X-Mock-User-Id": "owner"}).status_code == 403
    assert client.delete("/api/web/skills/team/demo").status_code == 401


def test_skill_hard_delete_routes_enforce_bearer_delete_scope(tmp_path: Path) -> None:
    app = create_app()
    seen: list[SkillHardDeleteInput] = []

    def bearer_user(raw_token: str) -> dict[str, object] | None:
        if raw_token == "delete-token":
            return {
                "userId": "admin",
                "displayName": "Admin",
                "email": "admin@example.com",
                "avatarUrl": "",
                "oauthProvider": "api_token",
                "platformRoles": ["SUPER_ADMIN"],
                "tokenScopes": ["skill:delete"],
            }
        if raw_token == "read-token":
            return {
                "userId": "admin",
                "displayName": "Admin",
                "email": "admin@example.com",
                "avatarUrl": "",
                "oauthProvider": "api_token",
                "platformRoles": ["SUPER_ADMIN"],
                "tokenScopes": ["skill:read"],
            }
        return None

    def mock_user(user_id: str) -> dict[str, object]:
        return {
            "userId": user_id,
            "displayName": user_id,
            "email": f"{user_id}@example.com",
            "avatarUrl": "",
            "platformRoles": ["SUPER_ADMIN"],
        }

    async def writer(delete_input: SkillHardDeleteInput) -> dict[str, Any]:
        seen.append(delete_input)
        return {
            "skillId": delete_input.skill_id or 10,
            "namespace": delete_input.namespace or "team",
            "slug": delete_input.slug or "demo",
            "deleted": True,
        }

    app.state.auth_bearer_reader = bearer_user
    app.state.auth_me_reader = mock_user
    app.state.skill_hard_delete_writer = writer
    app.state.storage_base_path = str(tmp_path)
    client = TestClient(app)

    allowed = client.delete("/api/v1/skills/team/demo", headers={"Authorization": "Bearer delete-token"})
    assert allowed.status_code == 200
    assert seen[-1].actor_user_id == "admin"

    missing_scope = client.delete("/api/v1/skills/team/demo", headers={"Authorization": "Bearer read-token"})
    assert missing_scope.status_code == 403
    assert missing_scope.json()["detail"] == "Missing API token scope: skill:delete"
    assert len(seen) == 1

    unknown = client.delete("/api/v1/skills/team/demo", headers={"Authorization": "Bearer bad-token"})
    assert unknown.status_code == 401

    web_unsupported = client.delete("/api/web/skills/team/demo", headers={"Authorization": "Bearer delete-token"})
    assert web_unsupported.status_code == 403
    assert web_unsupported.json()["detail"] == "API token cannot access endpoint: /api/web/skills/team/demo"

    mock_precedence = client.delete(
        "/api/v1/skills/team/demo",
        headers={"X-Mock-User-Id": "mock-admin", "Authorization": "Bearer read-token"},
    )
    assert mock_precedence.status_code == 200
    assert seen[-1].actor_user_id == "mock-admin"


def test_cli_skill_delete_route_returns_java_cli_envelope(tmp_path: Path) -> None:
    app = create_app()

    def auth_user(user_id: str) -> dict[str, object]:
        return {
            "userId": user_id,
            "displayName": user_id,
            "email": f"{user_id}@example.com",
            "avatarUrl": "",
            "platformRoles": ["USER"],
        }

    seen: list[SkillHardDeleteInput] = []

    async def writer(delete_input: SkillHardDeleteInput) -> dict[str, Any]:
        seen.append(delete_input)
        return {
            "skillId": 10,
            "namespace": delete_input.namespace or "team",
            "slug": delete_input.slug or "demo",
            "deleted": True,
        }

    app.state.auth_me_reader = auth_user
    app.state.skill_hard_delete_writer = writer
    app.state.storage_base_path = str(tmp_path)
    client = TestClient(app)

    response = client.delete(
        "/api/cli/v1/skills/team/demo",
        headers={"X-Mock-User-Id": "owner-1", "X-Request-Id": "cli-delete"},
    )

    assert response.status_code == 200
    assert response.json()["msg"] == "\u5220\u9664\u6210\u529f"
    assert response.json()["requestId"] == "cli-delete"
    assert response.json()["data"] == {
        "ok": True,
        "scope": "remote",
        "action": "delete",
        "namespace": "team",
        "slug": "demo",
    }
    assert seen[-1].route_scope == "cli"
    assert seen[-1].namespace == "team"
    assert seen[-1].slug == "demo"
    assert seen[-1].owner_id is None
    assert seen[-1].actor_user_id == "owner-1"


def test_cli_skill_delete_route_enforces_bearer_delete_scope(tmp_path: Path) -> None:
    app = create_app()
    seen: list[SkillHardDeleteInput] = []

    def bearer_user(raw_token: str) -> dict[str, object] | None:
        if raw_token == "delete-token":
            return {
                "userId": "token-owner",
                "displayName": "Token Owner",
                "email": "token-owner@example.com",
                "avatarUrl": "",
                "oauthProvider": "api_token",
                "platformRoles": ["USER"],
                "tokenScopes": ["skill:delete"],
            }
        if raw_token == "read-token":
            return {
                "userId": "token-owner",
                "displayName": "Token Owner",
                "email": "token-owner@example.com",
                "avatarUrl": "",
                "oauthProvider": "api_token",
                "platformRoles": ["USER"],
                "tokenScopes": ["skill:read"],
            }
        return None

    def mock_user(user_id: str) -> dict[str, object]:
        return {
            "userId": user_id,
            "displayName": user_id,
            "email": f"{user_id}@example.com",
            "avatarUrl": "",
            "platformRoles": ["USER"],
        }

    async def writer(delete_input: SkillHardDeleteInput) -> dict[str, Any]:
        seen.append(delete_input)
        return {
            "skillId": 10,
            "namespace": delete_input.namespace or "team",
            "slug": delete_input.slug or "demo",
            "deleted": True,
        }

    app.state.auth_bearer_reader = bearer_user
    app.state.auth_me_reader = mock_user
    app.state.skill_hard_delete_writer = writer
    app.state.storage_base_path = str(tmp_path)
    client = TestClient(app)

    allowed = client.delete("/api/cli/v1/skills/team/demo", headers={"Authorization": "Bearer delete-token"})
    assert allowed.status_code == 200
    assert allowed.json()["data"]["scope"] == "remote"
    assert allowed.json()["data"]["action"] == "delete"
    assert seen[-1].actor_user_id == "token-owner"

    missing_scope = client.delete("/api/cli/v1/skills/team/demo", headers={"Authorization": "Bearer read-token"})
    assert missing_scope.status_code == 403
    assert missing_scope.json()["detail"] == "Missing API token scope: skill:delete"
    assert len(seen) == 1

    unknown = client.delete("/api/cli/v1/skills/team/demo", headers={"Authorization": "Bearer bad-token"})
    assert unknown.status_code == 401

    mock_precedence = client.delete(
        "/api/cli/v1/skills/team/demo",
        headers={"X-Mock-User-Id": "mock-owner", "Authorization": "Bearer read-token"},
    )
    assert mock_precedence.status_code == 200
    assert seen[-1].actor_user_id == "mock-owner"

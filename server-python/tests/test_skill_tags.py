import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import skills
from app.main import create_app


class _FakeMappings:
    def __init__(self, value: object) -> None:
        self.value = value

    def one_or_none(self) -> object:
        return self.value

    def one(self) -> object:
        return self.value

    def all(self) -> object:
        return self.value


class _FakeResult:
    def __init__(self, value: object = None) -> None:
        self.value = value

    def mappings(self) -> _FakeMappings:
        return _FakeMappings(self.value)

    def scalar_one_or_none(self) -> object:
        return self.value


class _FakeConnectionContext:
    def __init__(self, connection: object) -> None:
        self.connection = connection

    async def __aenter__(self) -> object:
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class _FakeEngine:
    def __init__(self, connection: object) -> None:
        self.connection = connection

    def connect(self) -> _FakeConnectionContext:
        return _FakeConnectionContext(self.connection)

    def begin(self) -> _FakeConnectionContext:
        return _FakeConnectionContext(self.connection)


def tag_response(tag_name: str = "stable", version_id: int = 101) -> dict[str, object]:
    return {
        "id": 10,
        "tagName": tag_name,
        "versionId": version_id,
        "createdAt": "2026-06-11T00:00:00Z",
    }


def test_skill_tag_routes_use_java_envelopes_and_forward_inputs() -> None:
    app = create_app()
    seen: list[tuple[str, ...]] = []

    app.state.skill_tags_reader = lambda namespace, slug, current_user_id: seen.append(
        ("list", namespace, slug, current_user_id or "")
    ) or [tag_response()]
    app.state.skill_tag_writer = lambda namespace, slug, tag_name, target_version, user_id: seen.append(
        ("put", namespace, slug, tag_name, target_version, user_id)
    ) or tag_response(tag_name, 102)
    app.state.skill_tag_delete_writer = lambda namespace, slug, tag_name, user_id: seen.append(
        ("delete", namespace, slug, tag_name, user_id)
    ) or {"message": "Tag deleted"}

    client = TestClient(app)

    listed = client.get(
        "/api/v1/skills/team/demo/tags",
        headers={"X-Mock-User-Id": " owner-1 ", "X-Request-Id": "tag-list"},
    )
    moved = client.put(
        "/api/web/skills/team/demo/tags/stable",
        json={"tagName": "stable", "targetVersion": "1.1.0"},
        headers={"X-Mock-User-Id": "owner-1"},
    )
    deleted = client.delete(
        "/api/v1/skills/team/demo/tags/stable",
        headers={"X-Mock-User-Id": "owner-1"},
    )

    assert listed.status_code == 200
    assert listed.headers["X-Request-Id"] == "tag-list"
    assert listed.json()["msg"] == "\u83b7\u53d6\u6210\u529f"
    assert listed.json()["data"] == [tag_response()]
    assert moved.status_code == 200
    assert moved.json()["msg"] == "\u66f4\u65b0\u6210\u529f"
    assert moved.json()["data"]["versionId"] == 102
    assert deleted.status_code == 200
    assert deleted.json()["msg"] == "\u5220\u9664\u6210\u529f"
    assert deleted.json()["data"] == {"message": "Tag deleted"}
    assert seen == [
        ("list", "team", "demo", "owner-1"),
        ("put", "team", "demo", "stable", "1.1.0", "owner-1"),
        ("delete", "team", "demo", "stable", "owner-1"),
    ]


def test_skill_tag_write_routes_require_auth() -> None:
    client = TestClient(create_app())

    assert client.put("/api/v1/skills/team/demo/tags/stable", json={"tagName": "stable", "targetVersion": "1.1.0"}).status_code == 401
    assert client.delete("/api/web/skills/team/demo/tags/stable").status_code == 401


class _TagListConnection:
    async def execute(self, statement: object, params: dict[str, object] | None = None) -> _FakeResult:
        sql = str(statement)
        if "FROM skill s" in sql:
            assert "s.visibility = 'PUBLIC'" not in sql
            assert "CAST(:current_user_id AS varchar)" in sql
            assert "s.owner_id" in sql
            assert params and params["current_user_id"] == "owner-1"
            return _FakeResult(
                {
                    "id": 11,
                    "owner_id": "owner-1",
                    "namespace_id": 7,
                    "visibility": "PRIVATE",
                    "latest_version_id": 101,
                }
            )
        if "FROM namespace_member" in sql:
            return _FakeResult("OWNER")
        if "FROM skill_tag" in sql:
            return _FakeResult(
                [
                    {
                        "id": 20,
                        "tag_name": "stable",
                        "version_id": 100,
                        "created_at": datetime(2026, 6, 10, tzinfo=UTC),
                    }
                ]
            )
        raise AssertionError(f"unexpected SQL: {sql}")


def test_list_skill_tags_appends_latest_and_uses_visibility_access() -> None:
    result = asyncio.run(skills.list_skill_tags(_FakeEngine(_TagListConnection()), "team", "demo", "owner-1"))

    assert result == [
        {
            "id": 20,
            "tagName": "stable",
            "versionId": 100,
            "createdAt": "2026-06-10T00:00:00Z",
        },
        {
            "id": None,
            "tagName": "latest",
            "versionId": 101,
            "createdAt": None,
        },
    ]


class _TagWriteConnection:
    def __init__(self, *, role: str | None = "OWNER", existing_tag: dict[str, Any] | None = None, version_status: str = "PUBLISHED") -> None:
        self.role = role
        self.existing_tag = existing_tag
        self.version_status = version_status
        self.inserted: dict[str, Any] | None = None
        self.updated: dict[str, Any] | None = None
        self.deleted = False

    async def execute(self, statement: object, params: dict[str, object] | None = None) -> _FakeResult:
        sql = str(statement)
        values = params or {}
        if "FROM namespace n" in sql:
            return _FakeResult({"id": 7, "status": "ACTIVE"})
        if "SELECT role" in sql and "FROM namespace_member" in sql:
            return _FakeResult(self.role)
        if "FROM skill s" in sql:
            assert "s.owner_id = :current_user_id" in sql
            assert values["current_user_id"] == "owner-1"
            return _FakeResult(
                {
                    "id": 11,
                    "owner_id": "owner-1",
                    "namespace_id": 7,
                    "visibility": "PUBLIC",
                    "latest_version_id": 101,
                }
            )
        if "FROM skill_version" in sql:
            return _FakeResult({"id": 102, "status": self.version_status})
        if "SELECT id, skill_id, tag_name" in sql and "FROM skill_tag" in sql:
            return _FakeResult(self.existing_tag)
        if "UPDATE skill_tag" in sql:
            self.updated = dict(values)
            return _FakeResult(
                {
                    "id": self.existing_tag["id"] if self.existing_tag else 20,
                    "tag_name": values["tag_name"],
                    "version_id": values["version_id"],
                    "created_at": datetime(2026, 6, 9, tzinfo=UTC),
                }
            )
        if "INSERT INTO skill_tag" in sql:
            self.inserted = dict(values)
            return _FakeResult(
                {
                    "id": 21,
                    "tag_name": values["tag_name"],
                    "version_id": values["version_id"],
                    "created_at": datetime(2026, 6, 11, tzinfo=UTC),
                }
            )
        if "DELETE FROM skill_tag" in sql:
            self.deleted = True
            return _FakeResult(None)
        raise AssertionError(f"unexpected SQL: {sql}")


def test_create_or_move_skill_tag_matches_java_rules() -> None:
    connection = _TagWriteConnection()

    created = asyncio.run(
        skills.create_or_move_skill_tag(_FakeEngine(connection), "team", "demo", "stable", "1.1.0", "owner-1")
    )

    assert created["tagName"] == "stable"
    assert created["versionId"] == 102
    assert connection.inserted == {"skill_id": 11, "tag_name": "stable", "version_id": 102, "created_by": "owner-1"}

    moved_connection = _TagWriteConnection(
        existing_tag={"id": 20, "skill_id": 11, "tag_name": "stable", "version_id": 101}
    )
    moved = asyncio.run(
        skills.create_or_move_skill_tag(_FakeEngine(moved_connection), "team", "demo", "stable", "1.1.0", "owner-1")
    )

    assert moved["id"] == 20
    assert moved_connection.updated == {"skill_id": 11, "tag_name": "stable", "version_id": 102}


def test_create_or_move_skill_tag_rejects_reserved_forbidden_and_unpublished() -> None:
    with pytest.raises(skills.SkillResolveError, match="error.skill.tag.latest.reserved"):
        asyncio.run(skills.create_or_move_skill_tag(_FakeEngine(_TagWriteConnection()), "team", "demo", "latest", "1.0.0", "owner-1"))

    with pytest.raises(skills.SkillResolveError, match="error.namespace.admin.required"):
        asyncio.run(
            skills.create_or_move_skill_tag(
                _FakeEngine(_TagWriteConnection(role="MEMBER")), "team", "demo", "stable", "1.0.0", "member-1"
            )
        )

    with pytest.raises(skills.SkillResolveError, match="error.skill.tag.targetVersion.notPublished"):
        asyncio.run(
            skills.create_or_move_skill_tag(
                _FakeEngine(_TagWriteConnection(version_status="UPLOADED")), "team", "demo", "stable", "1.0.0", "owner-1"
            )
        )


def test_delete_skill_tag_matches_java_rules() -> None:
    connection = _TagWriteConnection(existing_tag={"id": 20, "skill_id": 11, "tag_name": "stable", "version_id": 101})

    result = asyncio.run(skills.delete_skill_tag(_FakeEngine(connection), "team", "demo", "stable", "owner-1"))

    assert result == {"message": "Tag deleted"}
    assert connection.deleted is True

    with pytest.raises(skills.SkillResolveError, match="error.skill.tag.latest.delete"):
        asyncio.run(skills.delete_skill_tag(_FakeEngine(_TagWriteConnection()), "team", "demo", "LATEST", "owner-1"))

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.social.star import SkillStarError, SkillStarInput, check_skill_star, star_skill, unstar_skill


class FakeScalarResult:
    def __init__(self, value: Any = None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> Any:
        return self.value


class FakeTransaction:
    def __init__(self, connection: "FakeStarConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeStarConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeConnect:
    def __init__(self, connection: "FakeStarConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeStarConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeStarConnection") -> None:
        self.connection = connection

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)

    def connect(self) -> FakeConnect:
        return FakeConnect(self.connection)


class FakeStarConnection:
    def __init__(self, *, skill_exists: bool = True, already_starred: bool = False) -> None:
        self.skill_exists = skill_exists
        self.starred = already_starred
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeScalarResult:
        sql = str(statement)
        values = params or {}
        self.statements.append(sql)
        self.params.append(values)

        if "SELECT 1" in sql and "FROM skill_star" in sql:
            return FakeScalarResult(1 if self.starred else None)
        if "SELECT 1" in sql and "FROM skill" in sql:
            return FakeScalarResult(1 if self.skill_exists else None)
        if "INSERT INTO skill_star" in sql:
            self.starred = True
            return FakeScalarResult()
        if "DELETE FROM skill_star" in sql:
            self.starred = False
            return FakeScalarResult()
        if "UPDATE skill" in sql and "star_count" in sql:
            return FakeScalarResult()
        raise AssertionError(f"unexpected SQL: {sql}")


def normalized(sql: str) -> str:
    return " ".join(sql.split())


def star_input(**overrides: Any) -> SkillStarInput:
    data: dict[str, Any] = {
        "skill_id": 10,
        "user_id": "user-1",
        "now": datetime(2026, 6, 10, 9, 30, tzinfo=UTC),
    }
    data.update(overrides)
    return SkillStarInput(**data)


@pytest.mark.anyio
async def test_star_skill_creates_relationship_and_refreshes_count_idempotently() -> None:
    connection = FakeStarConnection()

    await star_skill(FakeEngine(connection), star_input())
    await star_skill(FakeEngine(connection), star_input())

    insert_count = sum(1 for sql in connection.statements if "INSERT INTO skill_star" in normalized(sql))
    refresh_count = sum(1 for sql in connection.statements if "UPDATE skill" in sql and "star_count" in sql)
    assert insert_count == 1
    assert refresh_count == 1
    insert_params = next(params for sql, params in zip(connection.statements, connection.params, strict=True) if "INSERT INTO skill_star" in normalized(sql))
    assert insert_params["skill_id"] == 10
    assert insert_params["user_id"] == "user-1"
    assert insert_params["created_at"] == datetime(2026, 6, 10, 9, 30, tzinfo=UTC)


@pytest.mark.anyio
async def test_unstar_skill_deletes_relationship_and_refreshes_count_idempotently() -> None:
    connection = FakeStarConnection(already_starred=True)

    await unstar_skill(FakeEngine(connection), star_input())
    await unstar_skill(FakeEngine(connection), star_input())

    delete_count = sum(1 for sql in connection.statements if "DELETE FROM skill_star" in normalized(sql))
    refresh_count = sum(1 for sql in connection.statements if "UPDATE skill" in sql and "star_count" in sql)
    assert delete_count == 1
    assert refresh_count == 1


@pytest.mark.anyio
async def test_check_skill_star_returns_false_for_anonymous_and_validates_authenticated_skill() -> None:
    anonymous_connection = FakeStarConnection(skill_exists=False, already_starred=True)
    assert await check_skill_star(FakeEngine(anonymous_connection), 10, None) is False
    assert not anonymous_connection.statements

    authenticated_connection = FakeStarConnection(already_starred=True)
    assert await check_skill_star(FakeEngine(authenticated_connection), 10, "user-1") is True


@pytest.mark.anyio
async def test_skill_star_raises_not_found_before_mutation() -> None:
    connection = FakeStarConnection(skill_exists=False)

    with pytest.raises(SkillStarError, match="skill.not_found") as exc_info:
        await star_skill(FakeEngine(connection), star_input())

    assert exc_info.value.status_code == 404
    assert not any("INSERT INTO skill_star" in sql for sql in connection.statements)


def auth_user(user_id: str = "user-1") -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": "User",
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["USER"],
    }


def test_skill_star_routes_use_java_envelopes_and_auth_boundaries() -> None:
    app = create_app()
    seen: list[SkillStarInput] = []
    starred = {"value": False}
    app.state.auth_me_reader = lambda user_id: auth_user(user_id)

    async def star_writer(star_input_value: SkillStarInput) -> None:
        seen.append(star_input_value)
        starred["value"] = True

    async def unstar_writer(star_input_value: SkillStarInput) -> None:
        seen.append(star_input_value)
        starred["value"] = False

    async def reader(skill_id: int, user_id: str | None) -> bool:
        return bool(starred["value"] and user_id == "user-1" and skill_id == 10)

    app.state.skill_star_writer = star_writer
    app.state.skill_unstar_writer = unstar_writer
    app.state.skill_star_reader = reader
    client = TestClient(app)

    assert client.get("/api/v1/skills/10/star").status_code == 401
    missing_user = client.put("/api/v1/skills/10/star", headers={"X-Request-Id": "star-missing-user"})
    assert missing_user.status_code == 401

    star_response = client.put(
        "/api/v1/skills/10/star",
        headers={"X-Mock-User-Id": "user-1", "X-Request-Id": "star-test"},
    )
    check_response = client.get("/api/web/skills/10/star", headers={"X-Mock-User-Id": "user-1"})
    unstar_response = client.delete("/api/web/skills/10/star", headers={"X-Mock-User-Id": "user-1"})

    assert star_response.status_code == 200
    assert star_response.json()["msg"] == "\u66f4\u65b0\u6210\u529f"
    assert star_response.json()["data"] is None
    assert star_response.json()["requestId"] == "star-test"
    assert check_response.status_code == 200
    assert check_response.json()["msg"] == "\u83b7\u53d6\u6210\u529f"
    assert check_response.json()["data"] is True
    assert unstar_response.status_code == 200
    assert unstar_response.json()["msg"] == "\u66f4\u65b0\u6210\u529f"
    assert unstar_response.json()["data"] is None
    assert [entry.skill_id for entry in seen] == [10, 10]
    assert [entry.user_id for entry in seen] == ["user-1", "user-1"]

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.social.rating import (
    SkillRatingError,
    SkillRatingInput,
    check_skill_rating,
    rate_skill,
)


class FakeScalarResult:
    def __init__(self, value: Any = None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> Any:
        return self.value


class FakeTransaction:
    def __init__(self, connection: "FakeRatingConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeRatingConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeConnect:
    def __init__(self, connection: "FakeRatingConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeRatingConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeRatingConnection") -> None:
        self.connection = connection

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)

    def connect(self) -> FakeConnect:
        return FakeConnect(self.connection)


class FakeRatingConnection:
    def __init__(self, *, skill_exists: bool = True, existing_score: int | None = None) -> None:
        self.skill_exists = skill_exists
        self.score = existing_score
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeScalarResult:
        sql = str(statement)
        values = params or {}
        self.statements.append(sql)
        self.params.append(values)

        if "SELECT 1" in sql and "FROM skill" in sql:
            return FakeScalarResult(1 if self.skill_exists else None)
        if "SELECT score" in sql and "FROM skill_rating" in sql:
            return FakeScalarResult(self.score)
        if "INSERT INTO skill_rating" in sql:
            self.score = int(values["score"])
            return FakeScalarResult()
        if "UPDATE skill_rating" in sql:
            self.score = int(values["score"])
            return FakeScalarResult()
        if "UPDATE skill" in sql and "rating_avg" in sql:
            return FakeScalarResult()
        raise AssertionError(f"unexpected SQL: {sql}")


def normalized(sql: str) -> str:
    return " ".join(sql.split())


def rating_input(**overrides: Any) -> SkillRatingInput:
    data: dict[str, Any] = {
        "skill_id": 10,
        "user_id": "user-1",
        "score": 4,
        "now": datetime(2026, 6, 10, 11, 30, tzinfo=UTC),
    }
    data.update(overrides)
    return SkillRatingInput(**data)


@pytest.mark.anyio
async def test_rate_skill_creates_then_updates_rating_and_refreshes_aggregates() -> None:
    connection = FakeRatingConnection()

    await rate_skill(FakeEngine(connection), rating_input(score=4))
    await rate_skill(FakeEngine(connection), rating_input(score=2))

    insert_count = sum(1 for sql in connection.statements if "INSERT INTO skill_rating" in normalized(sql))
    update_count = sum(1 for sql in connection.statements if "UPDATE skill_rating" in normalized(sql))
    aggregate_count = sum(1 for sql in connection.statements if "UPDATE skill" in sql and "rating_avg" in sql)
    assert insert_count == 1
    assert update_count == 1
    assert aggregate_count == 2
    insert_params = next(
        params
        for sql, params in zip(connection.statements, connection.params, strict=True)
        if "INSERT INTO skill_rating" in normalized(sql)
    )
    assert insert_params["score"] == 4
    assert insert_params["created_at"] == datetime(2026, 6, 10, 11, 30, tzinfo=UTC)
    update_params = next(
        params
        for sql, params in zip(connection.statements, connection.params, strict=True)
        if "UPDATE skill_rating" in normalized(sql)
    )
    assert update_params["score"] == 2
    assert update_params["updated_at"] == datetime(2026, 6, 10, 11, 30, tzinfo=UTC)


@pytest.mark.anyio
async def test_rate_skill_rejects_invalid_score_after_skill_validation() -> None:
    connection = FakeRatingConnection()

    with pytest.raises(SkillRatingError, match="error.rating.score.invalid") as exc_info:
        await rate_skill(FakeEngine(connection), rating_input(score=6))

    assert exc_info.value.status_code == 400
    assert any("FROM skill" in sql for sql in connection.statements)
    assert not any("INSERT INTO skill_rating" in sql or "UPDATE skill_rating" in sql for sql in connection.statements)


@pytest.mark.anyio
async def test_check_skill_rating_requires_authenticated_user_for_skill_validation() -> None:
    anonymous_connection = FakeRatingConnection(skill_exists=False, existing_score=5)
    assert await check_skill_rating(FakeEngine(anonymous_connection), 10, None) == {"score": 0, "rated": False}
    assert not anonymous_connection.statements

    authenticated_connection = FakeRatingConnection(existing_score=3)
    assert await check_skill_rating(FakeEngine(authenticated_connection), 10, "user-1") == {"score": 3, "rated": True}

    unrated_connection = FakeRatingConnection(existing_score=None)
    assert await check_skill_rating(FakeEngine(unrated_connection), 10, "user-1") == {"score": 0, "rated": False}


@pytest.mark.anyio
async def test_skill_rating_raises_not_found_before_score_validation() -> None:
    connection = FakeRatingConnection(skill_exists=False)

    with pytest.raises(SkillRatingError, match="skill.not_found") as exc_info:
        await rate_skill(FakeEngine(connection), rating_input(score=9))

    assert exc_info.value.status_code == 404
    assert not any("INSERT INTO skill_rating" in sql or "UPDATE skill_rating" in sql for sql in connection.statements)


def auth_user(user_id: str = "user-1") -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": "User",
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["USER"],
    }


def test_skill_rating_routes_use_java_envelopes_and_auth_boundaries() -> None:
    app = create_app()
    seen: list[SkillRatingInput] = []
    current_score = {"value": 0}
    app.state.auth_me_reader = lambda user_id: auth_user(user_id)

    async def rating_writer(rating_input_value: SkillRatingInput) -> None:
        if rating_input_value.score < 1 or rating_input_value.score > 5:
            raise SkillRatingError("error.rating.score.invalid", status_code=400)
        seen.append(rating_input_value)
        current_score["value"] = rating_input_value.score

    async def reader(skill_id: int, user_id: str | None) -> dict[str, object]:
        if user_id != "user-1" or skill_id != 10 or current_score["value"] == 0:
            return {"score": 0, "rated": False}
        return {"score": current_score["value"], "rated": True}

    app.state.skill_rating_writer = rating_writer
    app.state.skill_rating_reader = reader
    client = TestClient(app)

    assert client.get("/api/v1/skills/10/rating").status_code == 401
    missing_user = client.put("/api/v1/skills/10/rating", json={"score": 4})
    invalid_score = client.put("/api/v1/skills/10/rating", headers={"X-Mock-User-Id": "user-1"}, json={"score": 0})

    rate_response = client.put(
        "/api/v1/skills/10/rating",
        headers={"X-Mock-User-Id": "user-1", "X-Request-Id": "rating-test"},
        json={"score": 4},
    )
    check_response = client.get("/api/web/skills/10/rating", headers={"X-Mock-User-Id": "user-1"})

    assert missing_user.status_code == 401
    assert invalid_score.status_code == 400
    assert rate_response.status_code == 200
    assert rate_response.json()["msg"] == "\u66f4\u65b0\u6210\u529f"
    assert rate_response.json()["data"] is None
    assert rate_response.json()["requestId"] == "rating-test"
    assert check_response.status_code == 200
    assert check_response.json()["msg"] == "\u83b7\u53d6\u6210\u529f"
    assert check_response.json()["data"] == {"score": 4, "rated": True}
    assert seen[0].skill_id == 10
    assert seen[0].user_id == "user-1"
    assert seen[0].score == 4

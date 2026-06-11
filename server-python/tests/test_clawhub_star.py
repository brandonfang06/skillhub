from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.social.clawhub_star import (
    ClawHubStarError,
    clawhub_star_skill,
    clawhub_unstar_skill,
    from_clawhub_canonical_slug,
)


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

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
    def __init__(self, connection: "FakeClawHubStarConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeClawHubStarConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeClawHubStarConnection") -> None:
        self.connection = connection

    def begin(self) -> FakeContext:
        return FakeContext(self.connection)


class FakeClawHubStarConnection:
    def __init__(self) -> None:
        self.skills = {
            ("global", "agent-helper"): {
                "id": 10,
                "owner_id": "owner-1",
                "namespace_id": 5,
                "visibility": "PUBLIC",
                "latest_version_id": 100,
            },
            ("team-ai", "private-helper"): {
                "id": 11,
                "owner_id": "owner-1",
                "namespace_id": 6,
                "visibility": "PRIVATE",
                "latest_version_id": 101,
            },
        }
        self.namespace_roles = {("member-1", 6): "MEMBER", ("owner-1", 6): "OWNER"}
        self.stars: set[tuple[int, str]] = set()
        self.star_counts: dict[int, int] = {10: 0, 11: 0}
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = " ".join(str(statement).split())
        values = params or {}
        self.params.append(values)

        if "FROM skill s" in sql and "JOIN namespace n" in sql:
            row = self.skills.get((str(values["namespace_slug"]), str(values["skill_slug"])))
            return FakeResult(rows=[row] if row is not None else [])
        if "FROM namespace_member" in sql:
            role = self.namespace_roles.get((str(values["user_id"]), int(values["namespace_id"])))
            return FakeResult(scalar=role)
        if "FROM skill_star" in sql and "SELECT 1" in sql:
            return FakeResult(scalar=1 if (int(values["skill_id"]), str(values["user_id"])) in self.stars else None)
        if "INSERT INTO skill_star" in sql:
            self.stars.add((int(values["skill_id"]), str(values["user_id"])))
            return FakeResult()
        if "DELETE FROM skill_star" in sql:
            self.stars.discard((int(values["skill_id"]), str(values["user_id"])))
            return FakeResult()
        if "UPDATE skill SET star_count" in sql:
            skill_id = int(values["skill_id"])
            self.star_counts[skill_id] = sum(1 for star_skill_id, _ in self.stars if star_skill_id == skill_id)
            return FakeResult()

        raise AssertionError(f"unexpected SQL: {sql}")


def test_from_clawhub_canonical_slug_matches_java_mapper() -> None:
    assert from_clawhub_canonical_slug("agent-helper") == ("global", "agent-helper")
    assert from_clawhub_canonical_slug("team-ai--agent-helper") == ("team-ai", "agent-helper")
    assert from_clawhub_canonical_slug("--agent-helper") == ("global", "--agent-helper")


@pytest.mark.anyio
async def test_clawhub_star_and_unstar_are_idempotent_plain_responses() -> None:
    connection = FakeClawHubStarConnection()
    engine = FakeEngine(connection)
    now = datetime(2026, 6, 11, 12, 0, tzinfo=UTC)

    first_star = await clawhub_star_skill(engine, "agent-helper", "user-1", now=now)
    second_star = await clawhub_star_skill(engine, "agent-helper", "user-1", now=now)
    first_unstar = await clawhub_unstar_skill(engine, "agent-helper", "user-1")
    second_unstar = await clawhub_unstar_skill(engine, "agent-helper", "user-1")

    assert first_star == {"ok": True, "starred": True, "alreadyStarred": False}
    assert second_star == {"ok": True, "starred": True, "alreadyStarred": True}
    assert first_unstar == {"ok": True, "unstarred": True, "alreadyUnstarred": False}
    assert second_unstar == {"ok": True, "unstarred": True, "alreadyUnstarred": True}
    assert connection.star_counts[10] == 0
    insert_params = next(params for params in connection.params if params.get("created_at") == now)
    assert insert_params["skill_id"] == 10
    assert insert_params["user_id"] == "user-1"


@pytest.mark.anyio
async def test_clawhub_star_uses_visibility_for_private_skills() -> None:
    connection = FakeClawHubStarConnection()

    with pytest.raises(ClawHubStarError, match="error.skill.notFound") as exc_info:
        await clawhub_star_skill(FakeEngine(connection), "team-ai--private-helper", "member-1")

    assert exc_info.value.status_code == 404
    owner_response = await clawhub_star_skill(FakeEngine(connection), "team-ai--private-helper", "owner-1")
    assert owner_response == {"ok": True, "starred": True, "alreadyStarred": False}


def auth_user(user_id: str = "user-1") -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": "User",
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["USER"],
    }


def test_clawhub_star_routes_require_auth_and_return_plain_json() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user(user_id)

    async def star_writer(engine: object, canonical_slug: str, user_id: str) -> dict[str, object]:
        assert engine is app.state.db_engine
        assert canonical_slug == "agent-helper"
        assert user_id == "user-1"
        return {"ok": True, "starred": True, "alreadyStarred": False}

    async def unstar_writer(engine: object, canonical_slug: str, user_id: str) -> dict[str, object]:
        assert engine is app.state.db_engine
        assert canonical_slug == "team-ai--agent-helper"
        assert user_id == "user-1"
        return {"ok": True, "unstarred": True, "alreadyUnstarred": True}

    app.state.clawhub_star_writer = star_writer
    app.state.clawhub_unstar_writer = unstar_writer
    app.state.db_engine = object()
    client = TestClient(app)

    assert client.post("/api/v1/stars/agent-helper").status_code == 401

    star_response = client.post("/api/v1/stars/agent-helper", headers={"X-Mock-User-Id": "user-1"})
    unstar_response = client.delete("/api/v1/stars/team-ai--agent-helper", headers={"X-Mock-User-Id": "user-1"})

    assert star_response.status_code == 200
    assert star_response.json() == {"ok": True, "starred": True, "alreadyStarred": False}
    assert "code" not in star_response.json()
    assert unstar_response.status_code == 200
    assert unstar_response.json() == {"ok": True, "unstarred": True, "alreadyUnstarred": True}

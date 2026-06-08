import asyncio
from typing import Any

from app.api.auth import build_auth_me_response, read_current_mock_user


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> "FakeResult":
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class FakeConnection:
    def __init__(self, user_rows: list[dict[str, Any]], role_rows: list[dict[str, Any]]) -> None:
        self.user_rows = user_rows
        self.role_rows = role_rows
        self.executed_params: list[dict[str, Any]] = []

    async def __aenter__(self) -> "FakeConnection":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    async def execute(self, query: object, params: dict[str, Any]) -> FakeResult:
        self.executed_params.append(params)
        if len(self.executed_params) == 1:
            return FakeResult(self.user_rows)
        return FakeResult(self.role_rows)


class FakeEngine:
    def __init__(self, user_rows: list[dict[str, Any]], role_rows: list[dict[str, Any]]) -> None:
        self.connection = FakeConnection(user_rows, role_rows)

    def connect(self) -> FakeConnection:
        return self.connection


def test_build_auth_me_response_matches_java_dto_defaults_and_sorted_roles() -> None:
    data = build_auth_me_response(
        {
            "id": "local-admin",
            "display_name": "Local Admin",
            "email": None,
            "avatar_url": None,
        },
        ["SKILL_ADMIN", "SUPER_ADMIN"],
    )

    assert data == {
        "userId": "local-admin",
        "displayName": "Local Admin",
        "email": "",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": ["SKILL_ADMIN", "SUPER_ADMIN"],
    }


def test_build_auth_me_response_uses_default_user_role_when_bindings_empty() -> None:
    data = build_auth_me_response(
        {
            "id": "local-user",
            "display_name": "Local User",
            "email": "local-user@example.com",
            "avatar_url": "",
        },
        [],
    )

    assert data["platformRoles"] == ["USER"]


def test_read_current_mock_user_reads_active_user_and_roles() -> None:
    engine = FakeEngine(
        user_rows=[
            {
                "id": "local-admin",
                "display_name": "Local Admin",
                "email": "admin@example.com",
                "avatar_url": "https://example.com/admin.png",
            }
        ],
        role_rows=[{"code": "SUPER_ADMIN"}, {"code": "AUDITOR"}],
    )

    data = asyncio.run(read_current_mock_user(engine, "local-admin"))

    assert data == {
        "userId": "local-admin",
        "displayName": "Local Admin",
        "email": "admin@example.com",
        "avatarUrl": "https://example.com/admin.png",
        "oauthProvider": "mock",
        "platformRoles": ["AUDITOR", "SUPER_ADMIN"],
    }
    assert engine.connection.executed_params == [{"user_id": "local-admin"}, {"user_id": "local-admin"}]


def test_read_current_mock_user_returns_none_for_missing_or_disabled_user() -> None:
    engine = FakeEngine(user_rows=[], role_rows=[])

    data = asyncio.run(read_current_mock_user(engine, "missing-user"))

    assert data is None
    assert engine.connection.executed_params == [{"user_id": "missing-user"}]

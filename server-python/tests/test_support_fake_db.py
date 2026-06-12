from __future__ import annotations

import asyncio

from tests.support.builders import auth_user, namespace_member_row, token_row
from tests.support.fake_db import FakeEngine, FakeResult, normalized_sql


def test_fake_result_supports_common_sqlalchemy_result_methods() -> None:
    result = FakeResult(row={"count": "3", "id": 10})

    assert result.mappings() is result
    assert result.one_or_none() == {"count": "3", "id": 10}
    assert result.all() == [{"count": "3", "id": 10}]
    assert result.scalar_one() == 3


def test_fake_engine_begin_and_connect_yield_same_connection() -> None:
    connection = object()
    engine = FakeEngine(connection)

    async def run() -> None:
        async with engine.begin() as begin_connection:
            assert begin_connection is connection
        async with engine.connect() as connect_connection:
            assert connect_connection is connection

    asyncio.run(run())


def test_builders_return_overridable_rows() -> None:
    assert auth_user("admin", platform_roles=["SUPER_ADMIN"])["platformRoles"] == ["SUPER_ADMIN"]
    assert namespace_member_row(user_id="owner", role="OWNER")["role"] == "OWNER"
    assert token_row(7, "user-7", "Deploy", "sk_deplo", "hash", ["skill:publish"])["scope_json"] == [
        "skill:publish"
    ]


def test_normalized_sql_collapses_whitespace() -> None:
    assert normalized_sql("SELECT  *\nFROM   api_token") == "SELECT * FROM api_token"

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import replace

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.session import RedisSessionStore
from app.core.config import get_settings
from app.core.redis import create_redis_client
from app.main import create_app

TEST_REDIS_URL = os.getenv("SKILLHUB_TEST_REDIS_URL")
pytestmark = pytest.mark.skipif(
    not TEST_REDIS_URL,
    reason="SKILLHUB_TEST_REDIS_URL is required for real Redis integration tests",
)


def _principal(user_id: str) -> dict[str, object]:
    return {
        "userId": user_id,
        "username": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "local",
        "platformRoles": ["USER"],
    }


def _runtime_client():
    settings = replace(
        get_settings(),
        redis_mode="single",
        redis_url=TEST_REDIS_URL or "redis://127.0.0.1:6379/15",
    )
    return create_redis_client(settings)


def test_runtime_redis_client_rotates_session_atomically() -> None:
    async def scenario() -> None:
        client = _runtime_client()
        prefix = f"test:session:{uuid.uuid4()}:"
        store = RedisSessionStore(client, ttl_seconds=60, key_prefix=prefix)
        session_ids: list[str] = []
        try:
            old_session_id = await store.create(_principal("old-user"))
            session_ids.append(old_session_id)

            new_session_id = await store.rotate(_principal("new-user"), [old_session_id])
            session_ids.append(new_session_id)

            assert await store.get(old_session_id) is None
            assert await store.get(new_session_id) == _principal("new-user")
        finally:
            if session_ids:
                await client.execute_command("DEL", *(f"{prefix}{value}" for value in session_ids))
            await client.aclose()

    asyncio.run(scenario())


def test_runtime_redis_client_deletes_multiple_sessions() -> None:
    async def scenario() -> None:
        client = _runtime_client()
        prefix = f"test:session:{uuid.uuid4()}:"
        store = RedisSessionStore(client, ttl_seconds=60, key_prefix=prefix)
        session_ids: list[str] = []
        try:
            session_ids.extend(
                [
                    await store.create(_principal("first-user")),
                    await store.create(_principal("second-user")),
                ]
            )

            await store.delete_many(session_ids)

            assert await store.get(session_ids[0]) is None
            assert await store.get(session_ids[1]) is None
        finally:
            if session_ids:
                await client.execute_command("DEL", *(f"{prefix}{value}" for value in session_ids))
            await client.aclose()

    asyncio.run(scenario())


def test_direct_login_rotation_and_logout_use_runtime_redis_client() -> None:
    async def scenario() -> None:
        redis_client = _runtime_client()
        app = create_app()
        app.state.redis_client = redis_client
        app.state.auth_direct_enabled = True
        app.state.local_auth_login = lambda payload: _principal("session-user")
        session_ids: list[str] = []
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://testserver",
            ) as http_client:
                first_login = await http_client.post(
                    "/api/v1/auth/direct/login",
                    json={"provider": "local", "username": "session-user", "password": "Abcd123!"},
                )
                assert first_login.status_code == 200
                session_ids.append(http_client.cookies["SESSION"])

                second_login = await http_client.post(
                    "/api/v1/auth/direct/login",
                    json={"provider": "local", "username": "session-user", "password": "Abcd123!"},
                )
                assert second_login.status_code == 200
                session_ids.append(http_client.cookies["SESSION"])
                assert session_ids[1] != session_ids[0]

                auth_me = await http_client.get("/api/v1/auth/me")
                assert auth_me.status_code == 200
                assert auth_me.json()["data"]["userId"] == "session-user"

                logout = await http_client.post("/api/v1/auth/logout")
                assert logout.status_code == 204

            store = RedisSessionStore(redis_client)
            assert await store.get(session_ids[0]) is None
            assert await store.get(session_ids[1]) is None
        finally:
            if session_ids:
                await redis_client.execute_command(
                    "DEL",
                    *(f"skillhub:session:{value}" for value in session_ids),
                )
            await redis_client.aclose()

    asyncio.run(scenario())

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from typing import Any

from fastapi import Request, Response

from app.core.config import first_env, parse_bool
from app.core.public_url import public_base_path

SESSION_COOKIE_NAME = "SESSION"
SESSION_TTL_SECONDS = 8 * 60 * 60


@dataclass
class InMemorySessionStore:
    sessions: dict[str, dict[str, object]] = field(default_factory=dict)

    async def create(self, principal: dict[str, object]) -> str:
        session_id = secrets.token_urlsafe(32)
        self.sessions[session_id] = dict(principal)
        return session_id

    async def get(self, session_id: str) -> dict[str, object] | None:
        principal = self.sessions.get(session_id)
        return dict(principal) if principal is not None else None

    async def delete(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)


class RedisSessionStore:
    def __init__(
        self,
        redis_client: Any,
        *,
        ttl_seconds: int = SESSION_TTL_SECONDS,
        key_prefix: str = "skillhub:session:",
    ) -> None:
        self.redis_client = redis_client
        self.ttl_seconds = ttl_seconds
        self.key_prefix = key_prefix

    def _key(self, session_id: str) -> str:
        return f"{self.key_prefix}{session_id}"

    async def create(self, principal: dict[str, object]) -> str:
        session_id = secrets.token_urlsafe(32)
        await self.redis_client.setex(self._key(session_id), self.ttl_seconds, json.dumps(principal))
        return session_id

    async def get(self, session_id: str) -> dict[str, object] | None:
        value = await self.redis_client.get(self._key(session_id))
        if value is None:
            return None
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        parsed = json.loads(str(value))
        return dict(parsed) if isinstance(parsed, dict) else None

    async def delete(self, session_id: str) -> None:
        await self.redis_client.delete(self._key(session_id))


def _session_store(request: Request) -> Any:
    store = getattr(request.app.state, "auth_session_store", None)
    if store is None:
        redis_client = getattr(request.app.state, "redis_client", None)
        store = RedisSessionStore(redis_client) if redis_client is not None else InMemorySessionStore()
        request.app.state.auth_session_store = store
    return store


def _cookie_secure() -> bool:
    return parse_bool(first_env("SKILLHUB_SESSION_COOKIE_SECURE", "SESSION_COOKIE_SECURE"))


def _cookie_path() -> str:
    return public_base_path() or "/"


def _session_ids(request: Request) -> list[str]:
    session_ids: list[str] = []
    for cookie_header in request.headers.getlist("cookie"):
        for cookie_pair in cookie_header.split(";"):
            name, separator, value = cookie_pair.strip().partition("=")
            session_id = value.strip().strip('"')
            if (
                separator
                and name == SESSION_COOKIE_NAME
                and session_id
                and session_id not in session_ids
            ):
                session_ids.append(session_id)
    return session_ids


async def establish_session(
    request: Request, response: Response, principal: dict[str, object]
) -> None:
    store = _session_store(request)
    session_id = await store.create(principal)
    for existing_session_id in _session_ids(request):
        await store.delete(existing_session_id)
    cookie_path = _cookie_path()
    if cookie_path != "/":
        response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_id,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        path=cookie_path,
    )


async def read_session_principal(request: Request) -> dict[str, object] | None:
    store = _session_store(request)
    for session_id in _session_ids(request):
        principal = await store.get(session_id)
        if principal is not None:
            return principal
    return None


async def clear_session(request: Request, response: Response) -> None:
    store = _session_store(request)
    for session_id in _session_ids(request):
        await store.delete(session_id)
    cookie_path = _cookie_path()
    response.delete_cookie(SESSION_COOKIE_NAME, path=cookie_path)
    if cookie_path != "/":
        response.delete_cookie(SESSION_COOKIE_NAME, path="/")

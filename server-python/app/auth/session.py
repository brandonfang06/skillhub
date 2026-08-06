from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, Request, Response

from app.core.config import first_env, parse_bool
from app.core.public_url import public_base_path

SESSION_COOKIE_NAME = "SESSION"
SESSION_TTL_SECONDS = 8 * 60 * 60
MAX_SESSION_LOOKUP_CANDIDATES = 2
MAX_SESSION_MUTATION_CANDIDATES = 3
MAX_SESSION_ID_LENGTH = 128


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

    async def rotate(
        self,
        principal: dict[str, object],
        existing_session_ids: list[str],
    ) -> str:
        session_id = secrets.token_urlsafe(32)
        for existing_session_id in existing_session_ids:
            self.sessions.pop(existing_session_id, None)
        self.sessions[session_id] = dict(principal)
        return session_id

    async def delete_many(self, session_ids: list[str]) -> None:
        for session_id in session_ids:
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

    async def rotate(
        self,
        principal: dict[str, object],
        existing_session_ids: list[str],
    ) -> str:
        session_id = secrets.token_urlsafe(32)
        pipeline = self.redis_client.pipeline(transaction=True)
        pipeline.setex(
            self._key(session_id),
            self.ttl_seconds,
            json.dumps(principal),
        )
        if existing_session_ids:
            pipeline.delete(*(self._key(value) for value in existing_session_ids))
        await pipeline.execute()
        return session_id

    async def delete_many(self, session_ids: list[str]) -> None:
        if session_ids:
            await self.redis_client.delete(*(self._key(value) for value in session_ids))


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


def _session_cookie_candidates(request: Request) -> tuple[list[str], int, bool]:
    candidates: list[str] = []
    raw_candidate_count = 0
    for cookie_header in request.headers.getlist("cookie"):
        for cookie_pair in cookie_header.split(";"):
            name, separator, value = cookie_pair.strip().partition("=")
            session_id = value.strip().strip('"')
            if not separator or name != SESSION_COOKIE_NAME or not session_id:
                continue
            raw_candidate_count += 1
            if raw_candidate_count > MAX_SESSION_MUTATION_CANDIDATES:
                return candidates, raw_candidate_count, True
            if (
                session_id not in candidates
                and len(candidates) < MAX_SESSION_MUTATION_CANDIDATES
            ):
                candidates.append(session_id)
    return candidates, raw_candidate_count, False


def validate_session_cookie_candidates(request: Request) -> tuple[list[str], int]:
    candidates, raw_candidate_count, overflow = _session_cookie_candidates(request)
    if overflow:
        raise HTTPException(status_code=400, detail="error.auth.session.cookieOverflow")
    return candidates, raw_candidate_count


def _store_session_ids(candidates: list[str]) -> list[str]:
    return [value for value in candidates if len(value) <= MAX_SESSION_ID_LENGTH]


async def _owns_legacy_root_session(
    store: Any,
    candidates: list[str],
    raw_candidate_count: int,
    cookie_path: str,
) -> bool:
    if (
        cookie_path == "/"
        or raw_candidate_count != MAX_SESSION_LOOKUP_CANDIDATES
        or len(candidates) != MAX_SESSION_LOOKUP_CANDIDATES
    ):
        return False
    root_candidate = candidates[-1]
    if len(root_candidate) > MAX_SESSION_ID_LENGTH:
        return False
    return await store.get(root_candidate) is not None


async def establish_session(
    request: Request, response: Response, principal: dict[str, object]
) -> None:
    candidates, raw_candidate_count = validate_session_cookie_candidates(request)
    store = _session_store(request)
    existing_session_ids = _store_session_ids(candidates)
    cookie_path = _cookie_path()
    expire_root_cookie = await _owns_legacy_root_session(
        store,
        candidates,
        raw_candidate_count,
        cookie_path,
    )
    session_id = await store.rotate(principal, existing_session_ids)
    if expire_root_cookie:
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
    candidates, _, _ = _session_cookie_candidates(request)
    for session_id in _store_session_ids(candidates[:MAX_SESSION_LOOKUP_CANDIDATES]):
        principal = await store.get(session_id)
        if principal is not None:
            return principal
    return None


async def clear_session(request: Request, response: Response) -> None:
    candidates, raw_candidate_count = validate_session_cookie_candidates(request)
    store = _session_store(request)
    session_ids = _store_session_ids(candidates)
    cookie_path = _cookie_path()
    expire_root_cookie = await _owns_legacy_root_session(
        store,
        candidates,
        raw_candidate_count,
        cookie_path,
    )
    await store.delete_many(session_ids)
    response.delete_cookie(SESSION_COOKIE_NAME, path=cookie_path)
    if expire_root_cookie:
        response.delete_cookie(SESSION_COOKIE_NAME, path="/")

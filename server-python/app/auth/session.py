from __future__ import annotations

from dataclasses import dataclass, field
import os
import secrets
from typing import Any

from fastapi import Request, Response

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


def _session_store(request: Request) -> Any:
    store = getattr(request.app.state, "auth_session_store", None)
    if store is None:
        store = InMemorySessionStore()
        request.app.state.auth_session_store = store
    return store


def _cookie_secure() -> bool:
    value = os.getenv("SKILLHUB_SESSION_COOKIE_SECURE")
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}


async def establish_session(request: Request, response: Response, principal: dict[str, object]) -> None:
    session_id = await _session_store(request).create(principal)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_id,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        path="/",
    )


async def read_session_principal(request: Request) -> dict[str, object] | None:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id is None or session_id.strip() == "":
        return None
    return await _session_store(request).get(session_id)


async def clear_session(request: Request, response: Response) -> None:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id is not None and session_id.strip() != "":
        await _session_store(request).delete(session_id)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")

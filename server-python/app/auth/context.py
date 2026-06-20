from __future__ import annotations

from collections.abc import Awaitable
from datetime import UTC, datetime
from inspect import isawaitable
import json
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import text

from app.auth.session import read_session_principal
from app.auth.tokens import sha256_token

DEFAULT_USER_ROLE = "USER"


def normalize_platform_roles(role_codes: list[str]) -> list[str]:
    normalized = sorted({role for role in role_codes if role})
    return normalized if normalized else [DEFAULT_USER_ROLE]


def build_unit_mock_user_response(user_id: str) -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": user_id,
        "email": "",
        "avatarUrl": "",
        "oauthProvider": "mock",
        "platformRoles": [DEFAULT_USER_ROLE],
    }


def build_auth_me_response(user_row: dict[str, Any], role_codes: list[str]) -> dict[str, object]:
    return {
        "userId": str(user_row["id"]),
        "displayName": str(user_row["display_name"]),
        "email": user_row["email"] or "",
        "avatarUrl": user_row["avatar_url"] or "",
        "oauthProvider": str(user_row.get("oauth_provider") or "mock"),
        "platformRoles": normalize_platform_roles(role_codes),
    }


async def resolve_reader_result(
    result: dict[str, object] | None | Awaitable[dict[str, object] | None],
) -> dict[str, object] | None:
    if isawaitable(result):
        return await result
    return result


async def read_current_mock_user(engine: Any, user_id: str) -> dict[str, object] | None:
    async with engine.connect() as connection:
        user_row = (
            await connection.execute(
                text(
                    """
                    SELECT id, display_name, email, avatar_url
                    FROM user_account
                    WHERE id = :user_id
                      AND status = 'ACTIVE'
                    LIMIT 1
                    """
                ),
                {"user_id": user_id},
            )
        ).mappings().one_or_none()

        if user_row is None:
            return None

        role_rows = (
            await connection.execute(
                text(
                    """
                    SELECT r.code
                    FROM user_role_binding urb
                    JOIN role r ON r.id = urb.role_id
                    WHERE urb.user_id = :user_id
                    ORDER BY r.code ASC
                    """
                ),
                {"user_id": user_id},
            )
        ).mappings().all()

    return build_auth_me_response(dict(user_row), [str(row["code"]) for row in role_rows])


def _decode_scope_json(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []


async def read_current_bearer_user(engine: Any, raw_token: str) -> dict[str, object] | None:
    now = datetime.now(UTC)
    async with engine.begin() as connection:
        row = (
            await connection.execute(
                text(
                    """
                    SELECT
                        t.id AS token_id,
                        t.scope_json,
                        u.id,
                        u.display_name,
                        u.email,
                        u.avatar_url
                    FROM api_token t
                    JOIN user_account u ON u.id = t.user_id
                    WHERE t.token_hash = :token_hash
                      AND t.revoked_at IS NULL
                      AND (t.expires_at IS NULL OR t.expires_at > :now)
                      AND u.status = 'ACTIVE'
                    LIMIT 1
                    """
                ),
                {"token_hash": sha256_token(raw_token), "now": now},
            )
        ).mappings().one_or_none()
        if row is None:
            return None

        role_rows = (
            await connection.execute(
                text(
                    """
                    SELECT r.code
                    FROM user_role_binding urb
                    JOIN role r ON r.id = urb.role_id
                    WHERE urb.user_id = :user_id
                    ORDER BY r.code ASC
                    """
                ),
                {"user_id": row["id"]},
            )
        ).mappings().all()
        await connection.execute(
            text("UPDATE api_token SET last_used_at = :last_used_at WHERE id = :token_id"),
            {"last_used_at": now, "token_id": int(row["token_id"])},
        )

    data = dict(row)
    data["oauth_provider"] = "api_token"
    response = build_auth_me_response(data, [str(role["code"]) for role in role_rows])
    response["tokenScopes"] = _decode_scope_json(row.get("scope_json"))
    return response


async def read_mock_user_or_401(request: Request, mock_user_id: str | None) -> dict[str, object]:
    if mock_user_id is None or mock_user_id.strip() == "":
        raise HTTPException(status_code=401, detail="error.auth.required")

    user_id = mock_user_id.strip()
    reader = getattr(request.app.state, "auth_me_reader", None)
    if reader is not None:
        data = await resolve_reader_result(reader(user_id))
    elif not hasattr(request.app.state, "db_engine") or not hasattr(request.app.state.db_engine, "connect"):
        data = build_unit_mock_user_response(user_id)
    else:
        data = await read_current_mock_user(request.app.state.db_engine, user_id)

    if data is None:
        raise HTTPException(status_code=401, detail="error.auth.required")
    return data


def bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    parts = authorization.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token if token else None


def has_bearer_authorization(authorization: str | None) -> bool:
    if authorization is None or authorization.strip() == "":
        return False
    parts = authorization.strip().split(None, 1)
    return bool(parts) and parts[0].lower() == "bearer"


async def resolve_current_user_or_401(
    request: Request,
    mock_user_id: str | None,
    authorization: str | None,
) -> dict[str, object]:
    if mock_user_id is not None and mock_user_id.strip() != "":
        return await read_mock_user_or_401(request, mock_user_id)

    token = bearer_token(authorization)
    if has_bearer_authorization(authorization):
        if token is None:
            raise HTTPException(status_code=401, detail="error.auth.required")
        reader = getattr(request.app.state, "auth_bearer_reader", None)
        if reader is not None:
            data = await resolve_reader_result(reader(token))
        else:
            data = await read_current_bearer_user(request.app.state.db_engine, token)

        if data is None:
            raise HTTPException(status_code=401, detail="error.auth.required")
        return data

    session_principal = await read_session_principal(request)
    if session_principal is not None:
        return session_principal

    raise HTTPException(status_code=401, detail="error.auth.required")

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import text

from app.core.response import ok

router = APIRouter()

DEFAULT_USER_ROLE = "USER"


def normalize_platform_roles(role_codes: list[str]) -> list[str]:
    normalized = sorted({role for role in role_codes if role})
    return normalized if normalized else [DEFAULT_USER_ROLE]


def build_auth_me_response(user_row: dict[str, Any], role_codes: list[str]) -> dict[str, object]:
    return {
        "userId": str(user_row["id"]),
        "displayName": str(user_row["display_name"]),
        "email": user_row["email"] or "",
        "avatarUrl": user_row["avatar_url"] or "",
        "oauthProvider": "mock",
        "platformRoles": normalize_platform_roles(role_codes),
    }


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


async def _resolve_reader_result(
    result: dict[str, object] | None | Awaitable[dict[str, object] | None],
) -> dict[str, object] | None:
    if isawaitable(result):
        return await result
    return result


@router.get("/api/v1/auth/me")
async def get_current_user(
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    if mock_user_id is None or mock_user_id.strip() == "":
        raise HTTPException(status_code=401, detail="error.auth.required")

    user_id = mock_user_id.strip()
    reader = getattr(request.app.state, "auth_me_reader", None)
    if reader is not None:
        data = await _resolve_reader_result(reader(user_id))
    else:
        data = await read_current_mock_user(request.app.state.db_engine, user_id)

    if data is None:
        raise HTTPException(status_code=401, detail="error.auth.required")

    return ok("\u83b7\u53d6\u6210\u529f", data, request)

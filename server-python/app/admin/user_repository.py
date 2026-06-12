from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
import secrets
from typing import Any

import bcrypt
from sqlalchemy import bindparam, text

from app.api.skills import to_java_instant


ADMIN_ROLES = {"USER_ADMIN", "SUPER_ADMIN"}
MANAGEABLE_STATUSES = {"ACTIVE", "DISABLED"}
USER_STATUSES = {"ACTIVE", "DISABLED", "PENDING"}
PASSWORD_RESET_CODE_DIGITS = 6
PASSWORD_RESET_EXPIRY = timedelta(minutes=10)


class AdminUserError(Exception):
    def __init__(self, detail: str, *, status_code: int = 400) -> None:
        super().__init__(detail)
        self.status_code = status_code


def require_user_admin(platform_roles: list[str]) -> None:
    if {str(role) for role in platform_roles}.isdisjoint(ADMIN_ROLES):
        raise AdminUserError("error.admin.userAdminRequired", status_code=403)


def _normalize_status(status: str | None) -> str:
    if status is None or status.strip() == "":
        raise AdminUserError("error.admin.user.status.invalid", status_code=400)
    normalized = status.strip().upper()
    if normalized not in USER_STATUSES:
        raise AdminUserError("error.admin.user.status.invalid", status_code=400)
    return normalized


def _normalize_manageable_status(status: str | None) -> str:
    normalized = _normalize_status(status)
    if normalized not in MANAGEABLE_STATUSES:
        raise AdminUserError("error.admin.user.status.unsupported", status_code=400)
    return normalized


def _normalize_role(role: str | None) -> str:
    if role is None or role.strip() == "":
        raise AdminUserError("error.admin.user.role.invalid", status_code=400)
    return role.strip().upper()


def _page_size(size: int) -> int:
    return max(1, min(int(size), 200))


def _page_number(page: int) -> int:
    return max(0, int(page))


def generate_password_reset_code() -> str:
    return f"{secrets.randbelow(10 ** PASSWORD_RESET_CODE_DIGITS):0{PASSWORD_RESET_CODE_DIGITS}d}"


def bcrypt_reset_code(code: str) -> str:
    return bcrypt.hashpw(code.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _admin_user_list_filters(search: str | None, status: str | None) -> tuple[str, dict[str, Any]]:
    filters: list[str] = []
    params: dict[str, Any] = {}
    if status is not None and status.strip():
        filters.append("status = :status")
        params["status"] = _normalize_status(status)
    if search is not None and search.strip():
        filters.append(
            """
            (
                LOWER(id) LIKE :search
                OR LOWER(display_name) LIKE :search
                OR LOWER(email) LIKE :search
            )
            """
        )
        params["search"] = f"%{search.strip().lower()}%"
    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    return where_clause, params


async def _read_user(connection: Any, user_id: str) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT id, display_name, email, status, created_at
                FROM user_account
                WHERE id = :user_id
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise AdminUserError("error.admin.user.notFound", status_code=404)
    return dict(row)


async def _roles_by_user_id(connection: Any, user_ids: list[str]) -> dict[str, list[str]]:
    if not user_ids:
        return {}
    query = text(
        """
        SELECT urb.user_id, r.code
        FROM user_role_binding urb
        JOIN role r ON r.id = urb.role_id
        WHERE urb.user_id IN :user_ids
        ORDER BY urb.user_id ASC, r.code ASC
        """
    ).bindparams(bindparam("user_ids", expanding=True))
    rows = (await connection.execute(query, {"user_ids": user_ids})).mappings().all()
    roles: dict[str, list[str]] = {user_id: [] for user_id in user_ids}
    for row in rows:
        roles.setdefault(str(row["user_id"]), []).append(str(row["code"]))
    return {user_id: sorted(values) if values else ["USER"] for user_id, values in roles.items()}


def _user_response(row: dict[str, Any], roles: list[str]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "username": str(row["display_name"]),
        "email": row["email"] or "",
        "status": str(row["status"]),
        "platformRoles": sorted(roles) if roles else ["USER"],
        "createdAt": to_java_instant(row["created_at"]),
    }


async def list_admin_users(
    engine: Any,
    *,
    search: str | None,
    status: str | None,
    page: int,
    size: int,
    platform_roles: list[str],
) -> dict[str, Any]:
    require_user_admin(platform_roles)
    normalized_page = _page_number(page)
    normalized_size = _page_size(size)
    where_clause, filter_params = _admin_user_list_filters(search, status)
    params = {
        **filter_params,
        "limit": normalized_size,
        "offset": normalized_page * normalized_size,
    }
    async with engine.connect() as connection:
        total = (
            await connection.execute(
                text(
                    f"""
                    SELECT COUNT(*) AS count
                    FROM user_account
                    {where_clause}
                    """
                ),
                params,
            )
        ).scalar_one()
        rows = (
            await connection.execute(
                text(
                    f"""
                    SELECT id, display_name, email, status, created_at
                    FROM user_account
                    {where_clause}
                    ORDER BY created_at DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            )
        ).mappings().all()
        users = [dict(row) for row in rows]
        roles = await _roles_by_user_id(connection, [str(row["id"]) for row in users])
    return {
        "items": [_user_response(row, roles.get(str(row["id"]), ["USER"])) for row in users],
        "total": int(total),
        "page": normalized_page,
        "size": normalized_size,
    }


async def update_admin_user_role(
    engine: Any,
    *,
    user_id: str,
    role: str,
    actor_platform_roles: list[str],
) -> dict[str, Any]:
    require_user_admin(actor_platform_roles)
    normalized_role = _normalize_role(role)
    if normalized_role == "SUPER_ADMIN" and "SUPER_ADMIN" not in {str(role) for role in actor_platform_roles}:
        raise AdminUserError("error.admin.user.role.superAdmin.assignDenied", status_code=403)
    async with engine.begin() as connection:
        user = await _read_user(connection, user_id)
        await connection.execute(text("DELETE FROM user_role_binding WHERE user_id = :user_id"), {"user_id": user_id})
        if normalized_role != "USER":
            role_row = (
                await connection.execute(
                    text("SELECT id, code FROM role WHERE code = :role_code LIMIT 1"),
                    {"role_code": normalized_role},
                )
            ).mappings().one_or_none()
            if role_row is None:
                raise AdminUserError("error.admin.user.role.invalid", status_code=400)
            await connection.execute(
                text("INSERT INTO user_role_binding (user_id, role_id) VALUES (:user_id, :role_id)"),
                {"user_id": user_id, "role_id": int(role_row["id"])},
            )
    return {"userId": str(user["id"]), "role": normalized_role, "status": str(user["status"])}


async def update_admin_user_status(engine: Any, *, user_id: str, status: str) -> dict[str, Any]:
    normalized_status = _normalize_manageable_status(status)
    async with engine.begin() as connection:
        user = await _read_user(connection, user_id)
        await connection.execute(
            text("UPDATE user_account SET status = :status, updated_at = CURRENT_TIMESTAMP WHERE id = :user_id"),
            {"user_id": user_id, "status": normalized_status},
        )
    return {"userId": str(user["id"]), "role": None, "status": normalized_status}


async def _has_local_credential(connection: Any, user_id: str) -> bool:
    row = (
        await connection.execute(
            text(
                """
                SELECT user_id
                FROM local_credential
                WHERE user_id = :user_id
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().one_or_none()
    return row is not None


def _is_password_reset_eligible(user: dict[str, Any], has_credential: bool) -> bool:
    return str(user["status"]) == "ACTIVE" and str(user.get("email") or "").strip() != "" and has_credential


async def trigger_admin_password_reset(
    engine: Any,
    *,
    user_id: str,
    admin_user_id: str,
    actor_platform_roles: list[str],
    code_generator: Callable[[], str] = generate_password_reset_code,
    code_hasher: Callable[[str], str] = bcrypt_reset_code,
    sender: Callable[[str, str, bool], None] | None = None,
) -> None:
    require_user_admin(actor_platform_roles)
    async with engine.begin() as connection:
        user = await _read_user(connection, user_id)
        has_credential = await _has_local_credential(connection, user_id)
        if not _is_password_reset_eligible(user, has_credential):
            raise AdminUserError("error.auth.password.reset.not.eligible", status_code=400)

        now = datetime.now(UTC)
        code = code_generator()
        code_hash = code_hasher(code)
        await connection.execute(
            text(
                """
                UPDATE password_reset_request
                SET consumed_at = :consumed_at
                WHERE user_id = :user_id
                  AND consumed_at IS NULL
                  AND expires_at > :consumed_at
                """
            ),
            {"user_id": user_id, "consumed_at": now},
        )
        await connection.execute(
            text(
                """
                INSERT INTO password_reset_request (
                    user_id,
                    email,
                    code_hash,
                    expires_at,
                    requested_by_admin,
                    requested_by_user_id
                )
                VALUES (
                    :user_id,
                    :email,
                    :code_hash,
                    :expires_at,
                    :requested_by_admin,
                    :requested_by_user_id
                )
                """
            ),
            {
                "user_id": user_id,
                "email": str(user["email"]),
                "code_hash": code_hash,
                "expires_at": now + PASSWORD_RESET_EXPIRY,
                "requested_by_admin": True,
                "requested_by_user_id": admin_user_id,
            },
        )
        if sender is not None:
            try:
                sender(str(user["email"]), code, True)
            except Exception as exc:  # pragma: no cover - exercised through route-level behavior when configured.
                raise AdminUserError("error.auth.password.reset.email.failed", status_code=500) from exc
    return None

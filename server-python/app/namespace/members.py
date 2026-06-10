from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.api.skills import to_java_instant


class NamespaceMemberReadError(Exception):
    def __init__(self, detail: str, *, status_code: int = 400) -> None:
        super().__init__(detail)
        self.status_code = status_code


def _member_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "namespaceId": int(row["namespace_id"]),
        "userId": row["user_id"],
        "displayName": row["display_name"],
        "email": row["email"],
        "role": str(row["role"]),
        "createdAt": to_java_instant(row["created_at"]),
        "updatedAt": to_java_instant(row["updated_at"]),
    }


def _candidate_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "userId": row["id"],
        "displayName": row["display_name"],
        "email": row["email"],
        "status": str(row["status"]),
    }


async def _read_namespace(connection: Any, slug: str) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT n.id, n.slug, n.status, n.type
                FROM namespace n
                WHERE n.slug = :slug
                LIMIT 1
                """
            ),
            {"slug": slug},
        )
    ).mappings().one_or_none()
    if row is None:
        raise NamespaceMemberReadError("error.namespace.slug.notFound", status_code=400)
    return dict(row)


async def _read_member_role(connection: Any, namespace_id: int, user_id: str) -> str | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT role
                FROM namespace_member
                WHERE namespace_id = :namespace_id
                  AND user_id = :user_id
                LIMIT 1
                """
            ),
            {"namespace_id": namespace_id, "user_id": user_id},
        )
    ).mappings().one_or_none()
    return str(row["role"]) if row is not None else None


async def _require_member(connection: Any, namespace_id: int, user_id: str) -> str:
    role = await _read_member_role(connection, namespace_id, user_id)
    if role is None:
        raise NamespaceMemberReadError("error.namespace.membership.required", status_code=403)
    return role


def _assert_member_mutation_allowed(namespace: dict[str, Any]) -> None:
    if str(namespace["type"]) == "GLOBAL":
        raise NamespaceMemberReadError("error.namespace.system.immutable", status_code=400)
    if str(namespace["status"]) != "ACTIVE":
        raise NamespaceMemberReadError("error.namespace.readonly", status_code=400)


def _validate_role(role: str) -> None:
    if role not in {"OWNER", "ADMIN", "MEMBER"}:
        raise NamespaceMemberReadError("error.namespace.member.role.invalid", status_code=400)


async def _require_admin_or_owner(connection: Any, namespace_id: int, user_id: str) -> str:
    role = await _require_member(connection, namespace_id, user_id)
    if role not in {"OWNER", "ADMIN"}:
        raise NamespaceMemberReadError("error.namespace.admin.required", status_code=403)
    return role


async def _read_member_response(connection: Any, namespace_id: int, user_id: str) -> dict[str, Any] | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT nm.id, nm.namespace_id, nm.user_id, ua.display_name, ua.email,
                       nm.role, nm.created_at, nm.updated_at
                FROM namespace_member nm
                LEFT JOIN user_account ua ON ua.id = nm.user_id
                WHERE nm.namespace_id = :namespace_id
                  AND nm.user_id = :user_id
                LIMIT 1
                """
            ),
            {"namespace_id": namespace_id, "user_id": user_id},
        )
    ).mappings().one_or_none()
    return _member_response(dict(row)) if row is not None else None


async def list_namespace_members(engine: Any, *, slug: str, user_id: str, page: int, size: int) -> dict[str, Any]:
    async with engine.connect() as connection:
        namespace = await _read_namespace(connection, slug)
        namespace_id = int(namespace["id"])
        await _require_member(connection, namespace_id, user_id)
        total = (
            await connection.execute(
                text(
                    """
                    SELECT COUNT(*) AS count
                    FROM namespace_member
                    WHERE namespace_id = :namespace_id
                    """
                ),
                {"namespace_id": namespace_id},
            )
        ).scalar_one()
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT nm.id, nm.namespace_id, nm.user_id, ua.display_name, ua.email,
                           nm.role, nm.created_at, nm.updated_at
                    FROM namespace_member nm
                    LEFT JOIN user_account ua ON ua.id = nm.user_id
                    WHERE nm.namespace_id = :namespace_id
                    ORDER BY nm.id ASC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {"namespace_id": namespace_id, "limit": size, "offset": page * size},
            )
        ).mappings().all()
    return {
        "items": [_member_response(dict(row)) for row in rows],
        "total": int(total),
        "page": page,
        "size": size,
    }


async def add_namespace_member(
    engine: Any,
    *,
    slug: str,
    member_user_id: str,
    role: str,
    operator_user_id: str,
) -> dict[str, Any]:
    async with engine.begin() as connection:
        namespace = await _read_namespace(connection, slug)
        namespace_id = int(namespace["id"])
        _assert_member_mutation_allowed(namespace)
        await _require_admin_or_owner(connection, namespace_id, operator_user_id)
        if role == "OWNER":
            raise NamespaceMemberReadError("error.namespace.member.owner.assignDirect", status_code=400)
        if await _read_member_role(connection, namespace_id, member_user_id) is not None:
            raise NamespaceMemberReadError("error.namespace.member.alreadyExists", status_code=400)
        await connection.execute(
            text(
                """
                INSERT INTO namespace_member (namespace_id, user_id, role)
                VALUES (:namespace_id, :user_id, :role)
                """
            ),
            {"namespace_id": namespace_id, "user_id": member_user_id, "role": role},
        )
        response = await _read_member_response(connection, namespace_id, member_user_id)
        if response is None:
            raise NamespaceMemberReadError("error.namespace.member.notFound", status_code=400)
        return response


async def remove_namespace_member(
    engine: Any,
    *,
    slug: str,
    member_user_id: str,
    operator_user_id: str,
) -> dict[str, str]:
    async with engine.begin() as connection:
        namespace = await _read_namespace(connection, slug)
        namespace_id = int(namespace["id"])
        _assert_member_mutation_allowed(namespace)
        await _require_admin_or_owner(connection, namespace_id, operator_user_id)
        role = await _read_member_role(connection, namespace_id, member_user_id)
        if role is None:
            raise NamespaceMemberReadError("error.namespace.member.notFound", status_code=400)
        if role == "OWNER":
            raise NamespaceMemberReadError("error.namespace.member.owner.remove", status_code=400)
        await connection.execute(
            text(
                """
                DELETE FROM namespace_member
                WHERE namespace_id = :namespace_id
                  AND user_id = :user_id
                """
            ),
            {"namespace_id": namespace_id, "user_id": member_user_id},
        )
    return {"message": "Member removed successfully"}


async def update_namespace_member_role(
    engine: Any,
    *,
    slug: str,
    member_user_id: str,
    role: str,
    operator_user_id: str,
) -> dict[str, Any]:
    async with engine.begin() as connection:
        namespace = await _read_namespace(connection, slug)
        namespace_id = int(namespace["id"])
        _assert_member_mutation_allowed(namespace)
        await _require_admin_or_owner(connection, namespace_id, operator_user_id)
        if role == "OWNER":
            raise NamespaceMemberReadError("error.namespace.member.owner.setDirect", status_code=400)
        if await _read_member_role(connection, namespace_id, member_user_id) is None:
            raise NamespaceMemberReadError("error.namespace.member.notFound", status_code=400)
        await connection.execute(
            text(
                """
                UPDATE namespace_member
                SET role = :role,
                    updated_at = CURRENT_TIMESTAMP
                WHERE namespace_id = :namespace_id
                  AND user_id = :user_id
                """
            ),
            {"namespace_id": namespace_id, "user_id": member_user_id, "role": role},
        )
        response = await _read_member_response(connection, namespace_id, member_user_id)
        if response is None:
            raise NamespaceMemberReadError("error.namespace.member.notFound", status_code=400)
        return response


def _map_batch_error(exc: Exception) -> str:
    message = str(exc)
    if "alreadyExists" in message:
        return "ALREADY_MEMBER"
    if "owner.assignDirect" in message:
        return "INVALID_ROLE"
    if "notFound" in message or "not found" in message:
        return "USER_NOT_FOUND"
    if "immutable" in message or "readonly" in message:
        return "NAMESPACE_READONLY"
    return "UNKNOWN_ERROR"


async def batch_add_namespace_members(
    engine: Any,
    *,
    slug: str,
    members: list[dict[str, Any]],
    operator_user_id: str,
) -> dict[str, Any]:
    async with engine.begin() as connection:
        await _read_namespace(connection, slug)

    results: list[dict[str, Any]] = []
    success_count = 0
    failure_count = 0
    for item in members:
        user_id = str(item["userId"])
        role = str(item["role"])
        try:
            await add_namespace_member(
                engine,
                slug=slug,
                member_user_id=user_id,
                role=role,
                operator_user_id=operator_user_id,
            )
            results.append({"userId": user_id, "role": role, "success": True, "error": None})
            success_count += 1
        except Exception as exc:
            results.append({"userId": user_id, "role": role, "success": False, "error": _map_batch_error(exc)})
            failure_count += 1
    return {
        "totalCount": len(members),
        "successCount": success_count,
        "failureCount": failure_count,
        "results": results,
    }


def _normalize_search(search: str) -> str | None:
    keyword = search.strip()
    if not keyword:
        return None
    if len(keyword) < 2:
        raise NamespaceMemberReadError("error.namespace.member.search.tooShort", status_code=400)
    return keyword


def _normalize_size(size: int) -> int:
    if size <= 0:
        return 10
    return min(size, 20)


async def search_namespace_member_candidates(
    engine: Any,
    *,
    slug: str,
    search: str,
    user_id: str,
    size: int,
) -> list[dict[str, Any]]:
    async with engine.connect() as connection:
        namespace = await _read_namespace(connection, slug)
        namespace_id = int(namespace["id"])
        if str(namespace["type"]) == "GLOBAL":
            raise NamespaceMemberReadError("error.namespace.system.immutable", status_code=400)
        role = await _require_member(connection, namespace_id, user_id)
        if role not in {"OWNER", "ADMIN"}:
            raise NamespaceMemberReadError("error.namespace.admin.required", status_code=403)
        if str(namespace["status"]) != "ACTIVE":
            raise NamespaceMemberReadError("error.namespace.readonly", status_code=400)

        keyword = _normalize_search(search)
        if keyword is None:
            return []
        limit = _normalize_size(size)

        existing_rows = (
            await connection.execute(
                text(
                    """
                    SELECT user_id
                    FROM namespace_member
                    WHERE namespace_id = :namespace_id
                    ORDER BY id ASC
                    LIMIT 500
                    """
                ),
                {"namespace_id": namespace_id},
            )
        ).mappings().all()
        existing_member_ids = {str(row["user_id"]) for row in existing_rows}

        rows = (
            await connection.execute(
                text(
                    """
                    SELECT id, display_name, email, status
                    FROM user_account
                    WHERE status = 'ACTIVE'
                      AND (
                        lower(display_name) LIKE lower(:keyword)
                        OR lower(coalesce(email, '')) LIKE lower(:keyword)
                        OR lower(id) LIKE lower(:keyword)
                      )
                    ORDER BY id ASC
                    LIMIT :limit
                    """
                ),
                {"keyword": f"%{keyword}%", "limit": limit},
            )
        ).mappings().all()
    return [_candidate_response(dict(row)) for row in rows if str(row["id"]) not in existing_member_ids]

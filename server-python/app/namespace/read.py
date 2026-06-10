from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.api.skills import to_java_instant


class NamespaceReadError(Exception):
    def __init__(self, detail: str, *, status_code: int = 400) -> None:
        super().__init__(detail)
        self.status_code = status_code


def _page(page: int, size: int, items: list[dict[str, Any]]) -> dict[str, Any]:
    start = min(page * size, len(items))
    end = min(start + size, len(items))
    return {"items": items[start:end], "total": len(items), "page": page, "size": size}


def _namespace_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "slug": str(row["slug"]),
        "displayName": row["display_name"],
        "status": str(row["status"]),
        "description": row["description"],
        "type": str(row["type"]),
        "avatarUrl": row["avatar_url"],
        "createdBy": row["created_by"],
        "createdAt": to_java_instant(row["created_at"]),
        "updatedAt": to_java_instant(row["updated_at"]),
    }


def _is_immutable(row: dict[str, Any]) -> bool:
    return str(row["type"]) == "GLOBAL"


def _is_team(row: dict[str, Any]) -> bool:
    return str(row["type"]) == "TEAM"


def _can_freeze(row: dict[str, Any], role: str | None) -> bool:
    return _is_team(row) and str(row["status"]) == "ACTIVE" and role in {"OWNER", "ADMIN"}


def _can_unfreeze(row: dict[str, Any], role: str | None) -> bool:
    return _is_team(row) and str(row["status"]) == "FROZEN" and role in {"OWNER", "ADMIN"}


def _can_archive(row: dict[str, Any], role: str | None) -> bool:
    return _is_team(row) and str(row["status"]) != "ARCHIVED" and role == "OWNER"


def _can_restore(row: dict[str, Any], role: str | None) -> bool:
    return _is_team(row) and str(row["status"]) == "ARCHIVED" and role == "OWNER"


def _can_delete_policy(row: dict[str, Any], role: str | None) -> bool:
    return _is_team(row) and role == "OWNER"


async def _read_roles(connection: Any, user_id: str) -> dict[int, str]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT namespace_id, role
                FROM namespace_member
                WHERE user_id = :user_id
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().all()
    return {int(row["namespace_id"]): str(row["role"]) for row in rows}


async def _read_namespaces_by_ids(connection: Any, namespace_ids: list[int]) -> list[dict[str, Any]]:
    if not namespace_ids:
        return []
    rows = (
        await connection.execute(
            text(
                """
                SELECT id, slug, display_name, status, description, type, avatar_url,
                       created_by, created_at, updated_at
                FROM namespace
                WHERE id = ANY(:namespace_ids)
                """
            ),
            {"namespace_ids": namespace_ids},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def _read_namespace_by_slug(connection: Any, slug: str) -> dict[str, Any] | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT n.id, n.slug, n.display_name, n.status, n.description, n.type,
                       n.avatar_url, n.created_by, n.created_at, n.updated_at
                FROM namespace n
                WHERE n.slug = :slug
                LIMIT 1
                """
            ),
            {"slug": slug},
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


async def _has_dependencies(connection: Any, namespace_id: int) -> bool:
    row = (
        await connection.execute(
            text(
                """
                SELECT
                    EXISTS (SELECT 1 FROM skill WHERE namespace_id = :namespace_id) AS has_skill,
                    EXISTS (SELECT 1 FROM review_task WHERE namespace_id = :namespace_id) AS has_review,
                    EXISTS (SELECT 1 FROM promotion_request WHERE target_namespace_id = :namespace_id) AS has_promotion
                """
            ),
            {"namespace_id": namespace_id},
        )
    ).mappings().one_or_none()
    if row is None:
        return False
    return bool(row["has_skill"]) or bool(row["has_review"]) or bool(row["has_promotion"])


async def list_namespaces(engine: Any, *, user_id: str, page: int, size: int) -> dict[str, Any]:
    async with engine.connect() as connection:
        roles = await _read_roles(connection, user_id)
        rows = await _read_namespaces_by_ids(connection, list(roles))

    items = [
        _namespace_response(row)
        for row in sorted(rows, key=lambda item: str(item["slug"]))
        if str(row["status"]) == "ACTIVE"
    ]
    return _page(page, size, items)


async def list_my_namespaces(engine: Any, *, user_id: str) -> list[dict[str, Any]]:
    async with engine.connect() as connection:
        roles = await _read_roles(connection, user_id)
        rows = await _read_namespaces_by_ids(connection, list(roles))
        items: list[dict[str, Any]] = []
        for row in sorted(rows, key=lambda item: str(item["slug"])):
            role = roles.get(int(row["id"]))
            response = _namespace_response(row)
            can_delete = _can_delete_policy(row, role) and not await _has_dependencies(connection, int(row["id"]))
            response.update(
                {
                    "currentUserRole": role,
                    "immutable": _is_immutable(row),
                    "canFreeze": _can_freeze(row, role),
                    "canUnfreeze": _can_unfreeze(row, role),
                    "canArchive": _can_archive(row, role),
                    "canRestore": _can_restore(row, role),
                    "canDelete": can_delete,
                }
            )
            items.append(response)
    return items


async def get_namespace(engine: Any, *, slug: str, user_id: str) -> dict[str, Any]:
    async with engine.connect() as connection:
        roles = await _read_roles(connection, user_id)
        row = await _read_namespace_by_slug(connection, slug)

    if row is None:
        raise NamespaceReadError("error.namespace.slug.notFound", status_code=400)

    namespace_id = int(row["id"])
    if str(row["status"]) == "ARCHIVED" and namespace_id not in roles:
        raise NamespaceReadError("error.namespace.slug.notFound", status_code=400)
    if namespace_id not in roles:
        raise NamespaceReadError("error.namespace.membership.required", status_code=403)
    return _namespace_response(row)

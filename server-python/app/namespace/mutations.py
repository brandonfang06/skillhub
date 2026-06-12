from __future__ import annotations

import json
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.auth.policy import is_namespace_manager, is_namespace_owner, namespace_role_allows
from app.namespace.read import _namespace_response


class NamespaceMutationError(Exception):
    def __init__(self, detail: str, *, status_code: int = 400) -> None:
        super().__init__(detail)
        self.status_code = status_code


RESERVED_SLUGS = {"admin", "api", "dashboard", "search", "auth", "me", "global", "system", "static", "assets", "health"}
UPPERCASE_PATTERN = re.compile(r"[A-Z]")


def _validate_slug(slug: str | None) -> str:
    if slug is None or slug.strip() == "":
        raise NamespaceMutationError("error.slug.blank", status_code=400)
    value = slug
    if len(value) < 2 or len(value) > 64:
        raise NamespaceMutationError("error.slug.length", status_code=400)
    if UPPERCASE_PATTERN.search(value):
        raise NamespaceMutationError("error.slug.pattern", status_code=400)
    if value.startswith("-") or value.endswith("-") or "--" in value:
        if "--" in value:
            raise NamespaceMutationError("error.slug.doubleHyphen", status_code=400)
        raise NamespaceMutationError("error.slug.pattern", status_code=400)
    for char in value:
        category = unicodedata.category(char)
        if char == "-" or category[0] in {"L", "N"} or category == "So":
            continue
        raise NamespaceMutationError("error.slug.pattern", status_code=400)
    if value in RESERVED_SLUGS:
        raise NamespaceMutationError("error.slug.reserved", status_code=400)
    return value


async def _read_namespace_by_slug(connection: Any, slug: str) -> dict[str, Any]:
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
    if row is None:
        raise NamespaceMutationError("error.namespace.slug.notFound", status_code=400)
    return dict(row)


async def _read_namespace_optional(connection: Any, slug: str) -> dict[str, Any] | None:
    try:
        return await _read_namespace_by_slug(connection, slug)
    except NamespaceMutationError:
        return None


async def _read_member_role(connection: Any, namespace_id: int, user_id: str) -> str:
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
    if row is None:
        raise NamespaceMutationError("error.namespace.membership.required", status_code=403)
    return str(row["role"])


def _assert_not_immutable(namespace: dict[str, Any]) -> None:
    if str(namespace["type"]) == "GLOBAL":
        raise NamespaceMutationError("error.namespace.system.immutable", status_code=400)


def _assert_writable(namespace: dict[str, Any]) -> None:
    if str(namespace["type"]) != "TEAM" or str(namespace["status"]) != "ACTIVE":
        raise NamespaceMutationError("error.namespace.readonly", status_code=400)


async def _require_admin_or_owner(connection: Any, namespace_id: int, user_id: str) -> str:
    role = await _read_member_role(connection, namespace_id, user_id)
    if not is_namespace_manager(role):
        raise NamespaceMutationError("error.namespace.admin.required", status_code=403)
    return role


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


async def _insert_audit(
    connection: Any,
    *,
    actor_user_id: str,
    action: str,
    namespace_id: int,
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
    reason: str | None,
) -> None:
    detail_json = None if reason is None or reason.strip() == "" else json.dumps({"reason": reason}, ensure_ascii=False, separators=(",", ":"))
    await connection.execute(
        text(
            """
            INSERT INTO audit_log (
                actor_user_id, action, target_type, target_id, request_id,
                client_ip, user_agent, detail_json, created_at
            )
            VALUES (
                :actor_user_id, :action, 'NAMESPACE', :target_id, :request_id,
                :client_ip, :user_agent, :detail_json, :created_at
            )
            """
        ),
        {
            "actor_user_id": actor_user_id,
            "action": action,
            "target_id": namespace_id,
            "request_id": request_id,
            "client_ip": client_ip,
            "user_agent": user_agent,
            "detail_json": detail_json,
            "created_at": datetime.now(UTC),
        },
    )


async def create_namespace(
    engine: Any,
    *,
    slug: str,
    display_name: str,
    description: str | None,
    actor_user_id: str,
    platform_roles: list[str],
) -> dict[str, Any]:
    if not ({"SKILL_ADMIN", "SUPER_ADMIN"} & set(platform_roles)):
        raise NamespaceMutationError("error.namespace.create.platformAdminRequired", status_code=403)
    normalized_slug = _validate_slug(slug)
    async with engine.begin() as connection:
        if await _read_namespace_optional(connection, normalized_slug) is not None:
            raise NamespaceMutationError("error.namespace.slug.exists", status_code=400)
        row = (
            await connection.execute(
                text(
                    """
                    INSERT INTO namespace (
                        slug, display_name, status, description, type, avatar_url,
                        created_by, created_at, updated_at
                    )
                    VALUES (
                        :slug, :display_name, 'ACTIVE', :description, 'TEAM', '',
                        :created_by, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    RETURNING id, slug, display_name, status, description, type, avatar_url,
                              created_by, created_at, updated_at
                    """
                ),
                {
                    "slug": normalized_slug,
                    "display_name": display_name,
                    "description": description,
                    "created_by": actor_user_id,
                },
            )
        ).mappings().one_or_none()
        if row is None:
            row = await _read_namespace_by_slug(connection, normalized_slug)
        namespace = dict(row)
        await connection.execute(
            text(
                """
                INSERT INTO namespace_member (namespace_id, user_id, role)
                VALUES (:namespace_id, :user_id, 'OWNER')
                """
            ),
            {"namespace_id": int(namespace["id"]), "user_id": actor_user_id, "role": "OWNER"},
        )
    return _namespace_response(namespace)


async def update_namespace(
    engine: Any,
    *,
    slug: str,
    display_name: str | None,
    description: str | None,
    actor_user_id: str,
) -> dict[str, Any]:
    async with engine.begin() as connection:
        namespace = await _read_namespace_by_slug(connection, slug)
        namespace_id = int(namespace["id"])
        _assert_not_immutable(namespace)
        await _require_admin_or_owner(connection, namespace_id, actor_user_id)
        _assert_writable(namespace)
        updates = {
            "namespace_id": namespace_id,
            "display_name": display_name if display_name is not None else namespace["display_name"],
            "description": description if description is not None else namespace["description"],
        }
        row = (
            await connection.execute(
                text(
                    """
                    UPDATE namespace
                    SET display_name = :display_name,
                        description = :description,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :namespace_id
                    RETURNING id, slug, display_name, status, description, type, avatar_url,
                              created_by, created_at, updated_at
                    """
                ),
                updates,
            )
        ).mappings().one_or_none()
        namespace = dict(row) if row is not None else await _read_namespace_by_slug(connection, slug)
    return _namespace_response(namespace)


async def delete_namespace(engine: Any, *, slug: str, actor_user_id: str) -> dict[str, str]:
    async with engine.begin() as connection:
        namespace = await _read_namespace_by_slug(connection, slug)
        namespace_id = int(namespace["id"])
        _assert_not_immutable(namespace)
        role = await _read_member_role(connection, namespace_id, actor_user_id)
        if not is_namespace_owner(role):
            raise NamespaceMutationError("error.namespace.owner.required", status_code=403)
        if await _has_dependencies(connection, namespace_id):
            raise NamespaceMutationError("error.namespace.delete.hasDependencies", status_code=400)
        await connection.execute(text("DELETE FROM namespace_member WHERE namespace_id = :namespace_id"), {"namespace_id": namespace_id})
        await connection.execute(text("DELETE FROM namespace WHERE id = :namespace_id"), {"namespace_id": namespace_id})
    return {"message": "Namespace deleted successfully"}


async def _transition_namespace(
    engine: Any,
    *,
    slug: str,
    actor_user_id: str,
    reason: str | None,
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
    source_status: str,
    target_status: str,
    allowed_roles: set[str],
    action: str,
    reject_if_archived: bool = False,
) -> dict[str, Any]:
    async with engine.begin() as connection:
        namespace = await _read_namespace_by_slug(connection, slug)
        namespace_id = int(namespace["id"])
        _assert_not_immutable(namespace)
        role = await _read_member_role(connection, namespace_id, actor_user_id)
        current_status = str(namespace["status"])
        if reject_if_archived:
            if current_status == "ARCHIVED":
                raise NamespaceMutationError("error.namespace.state.transition.invalid", status_code=400)
        elif current_status != source_status:
            raise NamespaceMutationError("error.namespace.state.transition.invalid", status_code=400)
        if not namespace_role_allows(role, allowed_roles):
            raise NamespaceMutationError("error.namespace.lifecycle.forbidden", status_code=403)
        row = (
            await connection.execute(
                text(
                    """
                    UPDATE namespace
                    SET status = :status,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :namespace_id
                    RETURNING id, slug, display_name, status, description, type, avatar_url,
                              created_by, created_at, updated_at
                    """
                ),
                {"namespace_id": namespace_id, "status": target_status},
            )
        ).mappings().one_or_none()
        updated = dict(row) if row is not None else await _read_namespace_by_slug(connection, slug)
        await _insert_audit(
            connection,
            actor_user_id=actor_user_id,
            action=action,
            namespace_id=namespace_id,
            request_id=request_id,
            client_ip=client_ip,
            user_agent=user_agent,
            reason=reason,
        )
    return _namespace_response(updated)


async def freeze_namespace(engine: Any, *, slug: str, actor_user_id: str, reason: str | None, request_id: str | None, client_ip: str | None, user_agent: str | None) -> dict[str, Any]:
    return await _transition_namespace(engine, slug=slug, actor_user_id=actor_user_id, reason=reason, request_id=request_id, client_ip=client_ip, user_agent=user_agent, source_status="ACTIVE", target_status="FROZEN", allowed_roles={"OWNER", "ADMIN"}, action="FREEZE_NAMESPACE")


async def unfreeze_namespace(engine: Any, *, slug: str, actor_user_id: str, request_id: str | None, client_ip: str | None, user_agent: str | None) -> dict[str, Any]:
    return await _transition_namespace(engine, slug=slug, actor_user_id=actor_user_id, reason=None, request_id=request_id, client_ip=client_ip, user_agent=user_agent, source_status="FROZEN", target_status="ACTIVE", allowed_roles={"OWNER", "ADMIN"}, action="UNFREEZE_NAMESPACE")


async def archive_namespace(engine: Any, *, slug: str, actor_user_id: str, reason: str | None, request_id: str | None, client_ip: str | None, user_agent: str | None) -> dict[str, Any]:
    return await _transition_namespace(engine, slug=slug, actor_user_id=actor_user_id, reason=reason, request_id=request_id, client_ip=client_ip, user_agent=user_agent, source_status="ACTIVE", target_status="ARCHIVED", allowed_roles={"OWNER"}, action="ARCHIVE_NAMESPACE", reject_if_archived=True)


async def restore_namespace(engine: Any, *, slug: str, actor_user_id: str, request_id: str | None, client_ip: str | None, user_agent: str | None) -> dict[str, Any]:
    return await _transition_namespace(engine, slug=slug, actor_user_id=actor_user_id, reason=None, request_id=request_id, client_ip=client_ip, user_agent=user_agent, source_status="ARCHIVED", target_status="ACTIVE", allowed_roles={"OWNER"}, action="RESTORE_NAMESPACE")

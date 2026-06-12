from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.audit.writer import write_audit_log
from app.db.unit_of_work import transaction_connection

from app.publish.replacement import (
    StorageDeleteCompensationInput,
    bundle_storage_key,
    delete_local_storage_objects_or_record_compensation,
)


@dataclass(frozen=True)
class SkillHardDeleteInput:
    route_scope: str
    skill_id: int | None
    namespace: str | None
    slug: str | None
    owner_id: str | None
    actor_user_id: str
    actor_platform_roles: list[str]
    storage_base_path: str
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    now: datetime | None = None


class SkillHardDeleteError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _now(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        return current.replace(tzinfo=UTC)
    return current.astimezone(UTC)


def _clean_namespace(namespace: str) -> str:
    return namespace[1:] if namespace.startswith("@") else namespace


def _roles(request: SkillHardDeleteInput) -> set[str]:
    return {str(role) for role in request.actor_platform_roles}


def _require_v1_super_admin(request: SkillHardDeleteInput) -> None:
    if request.route_scope == "v1" and "SUPER_ADMIN" not in _roles(request):
        raise SkillHardDeleteError("error.admin.superAdminRequired", status_code=403)


def _assert_web_can_delete(request: SkillHardDeleteInput, skill: dict[str, Any]) -> None:
    if request.route_scope != "web":
        return
    if "SUPER_ADMIN" in _roles(request):
        return
    if str(skill["owner_id"]) == request.actor_user_id:
        return
    raise SkillHardDeleteError("error.forbidden", status_code=403)


async def _read_skill_by_id(connection: Any, skill_id: int) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT s.id AS skill_id,
                       s.namespace_id,
                       n.slug AS namespace_slug,
                       s.slug AS skill_slug,
                       s.owner_id,
                       s.latest_version_id
                FROM skill s
                JOIN namespace n ON n.id = s.namespace_id
                WHERE s.id = :skill_id
                LIMIT 1
                """
            ),
            {"skill_id": skill_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise SkillHardDeleteError("error.skill.notFound", status_code=404)
    return dict(row)


async def _read_skill_by_slug(
    connection: Any,
    namespace: str,
    slug: str,
    owner_id: str | None,
    fallback_owner_id: str | None,
) -> dict[str, Any] | None:
    rows = (
        await connection.execute(
            text(
                """
                SELECT s.id AS skill_id,
                       s.namespace_id,
                       n.slug AS namespace_slug,
                       s.slug AS skill_slug,
                       s.owner_id,
                       s.latest_version_id
                FROM skill s
                JOIN namespace n ON n.id = s.namespace_id
                WHERE n.slug = :namespace_slug
                  AND s.slug = :skill_slug
                ORDER BY s.id ASC
                """
            ),
            {"namespace_slug": _clean_namespace(namespace), "skill_slug": slug},
        )
    ).mappings().all()
    candidates = [dict(row) for row in rows]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    if owner_id is not None and owner_id.strip():
        return next((row for row in candidates if str(row["owner_id"]) == owner_id), None)
    if fallback_owner_id is not None and fallback_owner_id.strip():
        return next((row for row in candidates if str(row["owner_id"]) == fallback_owner_id), None)
    return None


async def _read_version_ids(connection: Any, skill_id: int) -> list[int]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT id AS version_id
                FROM skill_version
                WHERE skill_id = :skill_id
                ORDER BY id ASC
                """
            ),
            {"skill_id": skill_id},
        )
    ).mappings().all()
    return [int(row["version_id"]) for row in rows]


async def _read_storage_keys(connection: Any, skill_id: int, version_ids: list[int]) -> list[str]:
    if not version_ids:
        return []
    rows = (
        await connection.execute(
            text(
                """
                SELECT version_id, storage_key
                FROM skill_file
                WHERE version_id = ANY(:version_ids)
                ORDER BY id ASC
                """
            ),
            {"version_ids": version_ids},
        )
    ).mappings().all()
    keys = [
        str(row["storage_key"])
        for row in rows
        if row.get("storage_key") is not None and str(row["storage_key"]).strip()
    ]
    keys.extend(bundle_storage_key(skill_id, version_id) for version_id in version_ids)
    return keys


async def _delete_related_rows(connection: Any, request: SkillHardDeleteInput, skill: dict[str, Any], version_ids: list[int]) -> None:
    skill_id = int(skill["skill_id"])
    timestamp = _now(request.now)
    await connection.execute(text("DELETE FROM skill_search_document WHERE skill_id = :skill_id"), {"skill_id": skill_id})
    await connection.execute(
        text(
            """
            UPDATE skill
            SET latest_version_id = NULL,
                updated_by = :actor_user_id,
                updated_at = :updated_at
            WHERE id = :skill_id
            """
        ),
        {"skill_id": skill_id, "actor_user_id": request.actor_user_id, "updated_at": timestamp},
    )

    if version_ids:
        await connection.execute(
            text("DELETE FROM review_task WHERE skill_version_id = ANY(:version_ids)"),
            {"version_ids": version_ids},
        )
        await connection.execute(
            text("DELETE FROM promotion_request WHERE source_version_id = ANY(:version_ids)"),
            {"version_ids": version_ids},
        )

    await connection.execute(
        text("DELETE FROM promotion_request WHERE source_skill_id = :skill_id OR target_skill_id = :skill_id"),
        {"skill_id": skill_id},
    )
    await connection.execute(text("DELETE FROM skill_tag WHERE skill_id = :skill_id"), {"skill_id": skill_id})
    await connection.execute(text("DELETE FROM skill_star WHERE skill_id = :skill_id"), {"skill_id": skill_id})
    await connection.execute(text("DELETE FROM skill_rating WHERE skill_id = :skill_id"), {"skill_id": skill_id})
    await connection.execute(text("DELETE FROM skill_report WHERE skill_id = :skill_id"), {"skill_id": skill_id})
    await connection.execute(text("DELETE FROM skill_version_stats WHERE skill_id = :skill_id"), {"skill_id": skill_id})
    await connection.execute(text("DELETE FROM skill_subscription WHERE skill_id = :skill_id"), {"skill_id": skill_id})
    await connection.execute(text("DELETE FROM skill_label WHERE skill_id = :skill_id"), {"skill_id": skill_id})

    for version_id in version_ids:
        await connection.execute(text("DELETE FROM security_audit WHERE skill_version_id = :version_id"), {"version_id": version_id})
        await connection.execute(text("DELETE FROM skill_file WHERE version_id = :version_id"), {"version_id": version_id})
    await connection.execute(text("DELETE FROM skill_version WHERE skill_id = :skill_id"), {"skill_id": skill_id})
    await connection.execute(text("DELETE FROM skill WHERE id = :skill_id"), {"skill_id": skill_id})
    await write_audit_log(
        connection,
        actor_user_id=request.actor_user_id,
        action="DELETE_SKILL_HARD",
        target_type="SKILL",
        target_id=skill_id,
        request_id=request.request_id,
        client_ip=request.client_ip,
        user_agent=request.user_agent,
        detail={},
        detail_json=json.dumps(
            {"namespaceId": int(skill["namespace_id"]), "slug": str(skill["skill_slug"])},
            separators=(",", ":"),
        ),
        created_at=timestamp,
    )


async def hard_delete_skill(engine: Any, request: SkillHardDeleteInput) -> dict[str, Any]:
    _require_v1_super_admin(request)
    storage_keys: list[str] = []
    target: dict[str, Any] | None = None
    async with transaction_connection(engine) as connection:
        if request.skill_id is not None:
            target = await _read_skill_by_id(connection, request.skill_id)
        else:
            namespace = request.namespace or ""
            slug = request.slug or ""
            fallback_owner_id = request.actor_user_id if request.route_scope == "web" else None
            target = await _read_skill_by_slug(connection, namespace, slug, request.owner_id, fallback_owner_id)
            if target is None:
                return {"skillId": None, "namespace": _clean_namespace(namespace), "slug": slug, "deleted": False}

        _assert_web_can_delete(request, target)
        version_ids = await _read_version_ids(connection, int(target["skill_id"]))
        storage_keys = await _read_storage_keys(connection, int(target["skill_id"]), version_ids)
        await _delete_related_rows(connection, request, target, version_ids)

    if storage_keys:
        async with transaction_connection(engine) as connection:
            await delete_local_storage_objects_or_record_compensation(
                connection,
                request.storage_base_path,
                StorageDeleteCompensationInput(
                    skill_id=int(target["skill_id"]),
                    namespace=str(target["namespace_slug"]),
                    slug=str(target["skill_slug"]),
                    storage_keys=storage_keys,
                    last_error=None,
                    now=request.now,
                ),
            )

    return {
        "skillId": int(target["skill_id"]),
        "namespace": str(target["namespace_slug"]),
        "slug": str(target["skill_slug"]),
        "deleted": True,
    }

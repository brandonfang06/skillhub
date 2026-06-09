from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text


LIFECYCLE_NAMESPACE_ROLES = {"OWNER", "ADMIN"}


@dataclass(frozen=True)
class SkillArchiveInput:
    namespace: str
    slug: str
    user_id: str
    reason: str | None = None
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    now: datetime | None = None


class SkillLifecycleError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _now(value: datetime | None) -> datetime:
    return value or datetime.now(UTC)


def _clean_namespace(namespace: str) -> str:
    return namespace[1:] if namespace.startswith("@") else namespace


def _reason_detail(reason: str | None) -> str | None:
    if reason is None or reason.strip() == "":
        return None
    return json.dumps({"reason": reason}, separators=(",", ":"))


async def _read_skill_context(connection: Any, namespace: str, slug: str) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT s.id AS skill_id,
                       s.namespace_id,
                       s.slug AS skill_slug,
                       s.owner_id,
                       s.status,
                       n.slug AS namespace_slug,
                       n.status AS namespace_status
                FROM namespace n
                JOIN skill s ON s.namespace_id = n.id
                WHERE n.slug = :namespace_slug
                  AND s.slug = :skill_slug
                LIMIT 1
                """
            ),
            {"namespace_slug": _clean_namespace(namespace), "skill_slug": slug},
        )
    ).mappings().one_or_none()
    if row is None:
        raise SkillLifecycleError("error.skill.notFound", status_code=404)
    return dict(row)


async def _read_namespace_role(connection: Any, namespace_id: int, user_id: str) -> str | None:
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


def _assert_can_manage(skill: dict[str, Any], user_id: str, namespace_role: str | None) -> None:
    if str(skill["owner_id"]) == user_id:
        return
    if namespace_role in LIFECYCLE_NAMESPACE_ROLES:
        return
    raise SkillLifecycleError("error.skill.lifecycle.noPermission", status_code=403)


async def _write_audit(
    connection: Any,
    *,
    actor_user_id: str,
    action: str,
    skill_id: int,
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
    detail_json: str | None,
    created_at: datetime,
) -> None:
    await connection.execute(
        text(
            """
            INSERT INTO audit_log (
                actor_user_id, action, target_type, target_id, request_id,
                client_ip, user_agent, detail_json, created_at
            )
            VALUES (
                :actor_user_id, :action, :target_type, :target_id, :request_id,
                :client_ip, :user_agent, :detail_json, :created_at
            )
            """
        ),
        {
            "actor_user_id": actor_user_id,
            "action": action,
            "target_type": "SKILL",
            "target_id": skill_id,
            "request_id": request_id,
            "client_ip": client_ip,
            "user_agent": user_agent,
            "detail_json": detail_json,
            "created_at": created_at,
        },
    )


async def _mutate_archive_status(
    engine: Any,
    request: SkillArchiveInput,
    *,
    status: str,
    action: str,
    audit_action: str,
    detail_json: str | None,
) -> dict[str, Any]:
    timestamp = _now(request.now)
    async with engine.begin() as connection:
        skill = await _read_skill_context(connection, request.namespace, request.slug)
        namespace_role = await _read_namespace_role(connection, int(skill["namespace_id"]), request.user_id)
        _assert_can_manage(skill, request.user_id, namespace_role)
        await connection.execute(
            text(
                """
                UPDATE skill
                SET status = :status,
                    updated_by = :updated_by,
                    updated_at = :updated_at
                WHERE id = :skill_id
                """
            ),
            {
                "status": status,
                "updated_by": request.user_id,
                "updated_at": timestamp,
                "skill_id": int(skill["skill_id"]),
            },
        )
        await _write_audit(
            connection,
            actor_user_id=request.user_id,
            action=audit_action,
            skill_id=int(skill["skill_id"]),
            request_id=request.request_id,
            client_ip=request.client_ip,
            user_agent=request.user_agent,
            detail_json=detail_json,
            created_at=timestamp,
        )
    return {"skillId": int(skill["skill_id"]), "versionId": None, "action": action, "status": status}


async def archive_skill(engine: Any, request: SkillArchiveInput) -> dict[str, Any]:
    return await _mutate_archive_status(
        engine,
        request,
        status="ARCHIVED",
        action="ARCHIVE",
        audit_action="ARCHIVE_SKILL",
        detail_json=_reason_detail(request.reason),
    )


async def unarchive_skill(engine: Any, request: SkillArchiveInput) -> dict[str, Any]:
    return await _mutate_archive_status(
        engine,
        request,
        status="ACTIVE",
        action="UNARCHIVE",
        audit_action="UNARCHIVE_SKILL",
        detail_json=None,
    )

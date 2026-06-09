from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text


@dataclass(frozen=True)
class AdminSkillGovernanceInput:
    skill_id: int
    actor_user_id: str
    reason: str | None = None
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    now: datetime | None = None


class AdminSkillGovernanceError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _now(value: datetime | None) -> datetime:
    return value or datetime.now(UTC)


def _reason_detail(reason: str | None) -> str | None:
    if reason is None or reason.strip() == "":
        return None
    return json.dumps({"reason": reason}, separators=(",", ":"))


async def _read_skill(connection: Any, skill_id: int) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT id AS skill_id,
                       status
                FROM skill
                WHERE id = :skill_id
                LIMIT 1
                """
            ),
            {"skill_id": skill_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise AdminSkillGovernanceError("error.skill.notFound", status_code=404)
    return dict(row)


async def _write_audit(
    connection: Any,
    *,
    actor_user_id: str,
    action: str,
    target_id: int,
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
            "target_id": target_id,
            "request_id": request_id,
            "client_ip": client_ip,
            "user_agent": user_agent,
            "detail_json": detail_json,
            "created_at": created_at,
        },
    )


async def _mutate_hidden_overlay(
    engine: Any,
    request: AdminSkillGovernanceInput,
    *,
    hidden: bool,
    hidden_by: str | None,
    hidden_at: datetime | None,
    action: str,
    audit_action: str,
    detail_json: str | None,
) -> dict[str, Any]:
    timestamp = hidden_at if hidden_at is not None else _now(request.now)
    async with engine.begin() as connection:
        skill = await _read_skill(connection, request.skill_id)
        await connection.execute(
            text(
                """
                UPDATE skill
                SET hidden = :hidden,
                    hidden_by = :hidden_by,
                    hidden_at = :hidden_at,
                    updated_by = :updated_by,
                    updated_at = :updated_at
                WHERE id = :skill_id
                """
            ),
            {
                "hidden": hidden,
                "hidden_by": hidden_by,
                "hidden_at": hidden_at,
                "updated_by": request.actor_user_id,
                "updated_at": timestamp,
                "skill_id": request.skill_id,
            },
        )
        await _write_audit(
            connection,
            actor_user_id=request.actor_user_id,
            action=audit_action,
            target_id=request.skill_id,
            request_id=request.request_id,
            client_ip=request.client_ip,
            user_agent=request.user_agent,
            detail_json=detail_json,
            created_at=timestamp,
        )

    return {"skillId": request.skill_id, "versionId": None, "action": action, "status": str(skill["status"])}


async def hide_skill_as_admin(engine: Any, request: AdminSkillGovernanceInput) -> dict[str, Any]:
    timestamp = _now(request.now)
    return await _mutate_hidden_overlay(
        engine,
        request,
        hidden=True,
        hidden_by=request.actor_user_id,
        hidden_at=timestamp,
        action="HIDE",
        audit_action="HIDE_SKILL",
        detail_json=_reason_detail(request.reason),
    )


async def unhide_skill_as_admin(engine: Any, request: AdminSkillGovernanceInput) -> dict[str, Any]:
    return await _mutate_hidden_overlay(
        engine,
        request,
        hidden=False,
        hidden_by=None,
        hidden_at=None,
        action="UNHIDE",
        audit_action="UNHIDE_SKILL",
        detail_json=None,
    )

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text


class SkillReportSubmitError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _now(value: datetime | None) -> datetime:
    return value or datetime.now(UTC)


def _normalize_required(value: str | None, error_key: str) -> str:
    if value is None or value.strip() == "":
        raise SkillReportSubmitError(error_key, status_code=400)
    return value.strip()


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _clean_namespace_slug(namespace_slug: str) -> str:
    return namespace_slug[1:] if namespace_slug.startswith("@") else namespace_slug


def _display_name(row: dict[str, Any]) -> str:
    value = row.get("display_name")
    if value is not None and str(value).strip() != "":
        return str(value)
    return str(row["slug"])


async def _read_reportable_skill(
    connection: Any,
    *,
    namespace_slug: str,
    skill_slug: str,
    reporter_id: str,
) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT s.id,
                       s.namespace_id,
                       s.slug,
                       s.display_name,
                       s.owner_id,
                       s.status,
                       s.hidden,
                       n.slug AS namespace_slug
                FROM namespace n
                JOIN skill s ON s.namespace_id = n.id
                WHERE n.slug = :namespace_slug
                  AND s.slug = :skill_slug
                  AND (
                    (s.latest_version_id IS NOT NULL AND s.hidden = FALSE)
                    OR s.owner_id = :reporter_id
                  )
                ORDER BY
                  CASE WHEN s.latest_version_id IS NOT NULL AND s.hidden = FALSE THEN 0 ELSE 1 END,
                  s.updated_at DESC,
                  s.id DESC
                LIMIT 1
                """
            ),
            {
                "namespace_slug": _clean_namespace_slug(namespace_slug),
                "skill_slug": skill_slug,
                "reporter_id": reporter_id,
            },
        )
    ).mappings().one_or_none()
    if row is None:
        raise SkillReportSubmitError("error.skill.notFound", status_code=404)
    return dict(row)


async def _has_pending_report(connection: Any, *, skill_id: int, reporter_id: str) -> bool:
    count = (
        await connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM skill_report
                WHERE skill_id = :skill_id
                  AND reporter_id = :reporter_id
                  AND status = 'PENDING'
                """
            ),
            {"skill_id": skill_id, "reporter_id": reporter_id},
        )
    ).scalar_one()
    return int(count or 0) > 0


async def _insert_skill_report(
    connection: Any,
    *,
    skill_id: int,
    namespace_id: int,
    reporter_id: str,
    reason: str,
    details: str | None,
    created_at: datetime,
) -> int:
    return int(
        (
            await connection.execute(
                text(
                    """
                    INSERT INTO skill_report (
                        skill_id, namespace_id, reporter_id, reason, details, status, created_at
                    )
                    VALUES (
                        :skill_id, :namespace_id, :reporter_id, :reason, :details, 'PENDING', :created_at
                    )
                    RETURNING id
                    """
                ),
                {
                    "skill_id": skill_id,
                    "namespace_id": namespace_id,
                    "reporter_id": reporter_id,
                    "reason": reason,
                    "details": details,
                    "created_at": created_at,
                },
            )
        ).scalar_one()
    )


async def _write_audit(
    connection: Any,
    *,
    actor_user_id: str,
    target_id: int,
    report_id: int,
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
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
            "action": "REPORT_SKILL",
            "target_type": "SKILL",
            "target_id": target_id,
            "request_id": request_id,
            "client_ip": client_ip,
            "user_agent": user_agent,
            "detail_json": json.dumps({"reportId": report_id}, separators=(",", ":")),
            "created_at": created_at,
        },
    )


async def _read_platform_skill_admins(connection: Any) -> list[str]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT DISTINCT urb.user_id
                FROM user_role_binding urb
                JOIN role r ON r.id = urb.role_id
                LEFT JOIN notification_preference np
                  ON np.user_id = urb.user_id
                 AND np.category = 'REPORT'
                 AND np.channel = 'IN_APP'
                WHERE r.code IN ('SKILL_ADMIN', 'SUPER_ADMIN')
                  AND COALESCE(np.enabled, TRUE) = TRUE
                ORDER BY urb.user_id
                """
            )
        )
    ).mappings().all()
    return [str(row["user_id"]) for row in rows]


async def _write_report_submitted_notifications(
    connection: Any,
    *,
    recipients: list[str],
    skill: dict[str, Any],
    report_id: int,
    reporter_id: str,
    created_at: datetime,
) -> None:
    title = f"Skill reported: {_display_name(skill)}"
    body_json = json.dumps(
        {
            "skillId": int(skill["id"]),
            "skillName": _display_name(skill),
            "slug": str(skill["slug"]),
            "namespace": str(skill["namespace_slug"]),
            "reportId": report_id,
            "reporterId": reporter_id,
        },
        separators=(",", ":"),
    )
    for recipient_id in dict.fromkeys(recipients):
        await connection.execute(
            text(
                """
                INSERT INTO notification (
                    recipient_id, category, event_type, title, body_json,
                    entity_type, entity_id, status, created_at
                )
                VALUES (
                    :recipient_id, :category, :event_type, :title, :body_json,
                    :entity_type, :entity_id, :status, :created_at
                )
                """
            ),
            {
                "recipient_id": recipient_id,
                "category": "REPORT",
                "event_type": "REPORT_SUBMITTED",
                "title": title,
                "body_json": body_json,
                "entity_type": "REPORT",
                "entity_id": report_id,
                "status": "UNREAD",
                "created_at": created_at,
            },
        )


async def submit_skill_report(
    engine: Any,
    *,
    namespace_slug: str,
    skill_slug: str,
    reporter_id: str,
    reason: str | None,
    details: str | None,
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    normalized_reason = _normalize_required(reason, "error.skill.report.reason.required")
    normalized_details = _normalize_optional(details)
    timestamp = _now(now)
    async with engine.begin() as connection:
        skill = await _read_reportable_skill(
            connection,
            namespace_slug=namespace_slug,
            skill_slug=skill_slug,
            reporter_id=reporter_id,
        )
        if str(skill["status"]) != "ACTIVE" or bool(skill["hidden"]):
            raise SkillReportSubmitError("error.skill.report.unavailable", status_code=400)
        if str(skill["owner_id"]) == reporter_id:
            raise SkillReportSubmitError("error.skill.report.self", status_code=400)
        if await _has_pending_report(connection, skill_id=int(skill["id"]), reporter_id=reporter_id):
            raise SkillReportSubmitError("error.skill.report.duplicate", status_code=400)

        report_id = await _insert_skill_report(
            connection,
            skill_id=int(skill["id"]),
            namespace_id=int(skill["namespace_id"]),
            reporter_id=reporter_id,
            reason=normalized_reason,
            details=normalized_details,
            created_at=timestamp,
        )
        await _write_audit(
            connection,
            actor_user_id=reporter_id,
            target_id=int(skill["id"]),
            report_id=report_id,
            request_id=request_id,
            client_ip=client_ip,
            user_agent=user_agent,
            created_at=timestamp,
        )
        await _write_report_submitted_notifications(
            connection,
            recipients=await _read_platform_skill_admins(connection),
            skill=skill,
            report_id=report_id,
            reporter_id=reporter_id,
            created_at=timestamp,
        )

    return {"reportId": report_id, "status": "PENDING"}

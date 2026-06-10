from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any

from sqlalchemy import bindparam, text


PLATFORM_GOVERNANCE_ROLES = {"SKILL_ADMIN", "SUPER_ADMIN"}
ACTIVITY_READ_ROLES = {"SKILL_ADMIN", "SUPER_ADMIN", "AUDITOR"}
NAMESPACE_GOVERNANCE_ROLES = {"OWNER", "ADMIN"}
INBOX_TYPES = {"REVIEW", "PROMOTION", "REPORT"}
ACTIVITY_ACTIONS = {
    "REVIEW_SUBMIT",
    "REVIEW_APPROVE",
    "REVIEW_REJECT",
    "REVIEW_WITHDRAW",
    "PROMOTION_SUBMIT",
    "PROMOTION_APPROVE",
    "PROMOTION_REJECT",
    "REPORT_SKILL",
    "RESOLVE_SKILL_REPORT",
    "DISMISS_SKILL_REPORT",
    "HIDE_SKILL",
    "ARCHIVE_SKILL",
    "UNHIDE_SKILL",
    "UNARCHIVE_SKILL",
}


class GovernanceWorkbenchError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _java_instant(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        instant = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return instant.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return str(value).replace("+00:00", "Z")


def _normalize_page(page: int) -> int:
    return max(0, int(page))


def _normalize_size(size: int) -> int:
    return int(size) if int(size) > 0 else 20


def _normalize_inbox_type(type_filter: str | None) -> str | None:
    if type_filter is None or type_filter.strip() == "":
        return None
    normalized = type_filter.strip().upper()
    if normalized not in INBOX_TYPES:
        raise GovernanceWorkbenchError("error.governance.inbox.type.invalid", status_code=400)
    return normalized


async def _read_platform_roles(connection: Any, user_id: str) -> set[str]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT r.code
                FROM user_role_binding urb
                JOIN role r ON r.id = urb.role_id
                WHERE urb.user_id = :user_id
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().all()
    return {str(row["code"]) for row in rows}


async def _read_namespace_roles(connection: Any, user_id: str) -> list[dict[str, Any]]:
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
    return [dict(row) for row in rows]


def _managed_namespace_ids(namespace_roles: list[dict[str, Any]]) -> list[int]:
    return [
        int(row["namespace_id"])
        for row in namespace_roles
        if str(row["role"]) in NAMESPACE_GOVERNANCE_ROLES
    ]


def _has_platform_governance_role(platform_roles: set[str]) -> bool:
    return bool(platform_roles & PLATFORM_GOVERNANCE_ROLES)


def _can_read_activity(platform_roles: set[str]) -> bool:
    return bool(platform_roles & ACTIVITY_READ_ROLES)


async def _count_pending_reviews(connection: Any, *, platform_roles: set[str], managed_namespace_ids: list[int]) -> int:
    if _has_platform_governance_role(platform_roles):
        return int(
            (
                await connection.execute(
                    text("SELECT COUNT(*) FROM review_task WHERE status = 'PENDING'")
                )
            ).scalar_one()
        )
    if not managed_namespace_ids:
        return 0
    query = text(
        """
        SELECT COUNT(*)
        FROM review_task
        WHERE status = 'PENDING'
          AND namespace_id IN :namespace_ids
        """
    ).bindparams(bindparam("namespace_ids", expanding=True))
    return int((await connection.execute(query, {"namespace_ids": managed_namespace_ids})).scalar_one())


async def _count_pending_promotions(connection: Any) -> int:
    return int(
        (
            await connection.execute(
                text("SELECT COUNT(*) FROM promotion_request WHERE status = 'PENDING'")
            )
        ).scalar_one()
    )


async def _count_pending_reports(connection: Any) -> int:
    return int(
        (
            await connection.execute(
                text("SELECT COUNT(*) FROM skill_report WHERE status = 'PENDING'")
            )
        ).scalar_one()
    )


async def _count_unread_governance_notifications(connection: Any, user_id: str) -> int:
    return int(
        (
            await connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM user_notification
                    WHERE user_id = :user_id
                      AND status = 'UNREAD'
                    """
                ),
                {"user_id": user_id},
            )
        ).scalar_one()
    )


async def get_governance_summary(engine: Any, *, user_id: str) -> dict[str, int]:
    async with engine.connect() as connection:
        platform_roles = await _read_platform_roles(connection, user_id)
        namespace_roles = await _read_namespace_roles(connection, user_id)
        managed_ids = _managed_namespace_ids(namespace_roles)
        can_platform = _has_platform_governance_role(platform_roles)
        return {
            "pendingReviews": await _count_pending_reviews(
                connection,
                platform_roles=platform_roles,
                managed_namespace_ids=managed_ids,
            ),
            "pendingPromotions": await _count_pending_promotions(connection) if can_platform else 0,
            "pendingReports": await _count_pending_reports(connection) if can_platform else 0,
            "unreadNotifications": await _count_unread_governance_notifications(connection, user_id),
        }


def _inbox_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": str(row["type"]),
        "id": int(row["id"]),
        "title": row.get("title"),
        "subtitle": row.get("subtitle"),
        "timestamp": _java_instant(row.get("timestamp")),
        "namespace": row.get("namespace"),
        "skillSlug": row.get("skill_slug"),
    }


async def _read_review_inbox_rows(connection: Any, *, platform_roles: set[str], managed_namespace_ids: list[int], limit: int) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": limit}
    namespace_filter = ""
    query_text = """
        /* review_inbox */
        SELECT 'REVIEW' AS type,
               rt.id,
               COALESCE(ns.slug || '/' || s.slug || '@' || sv.version, 'Unknown target') AS title,
               'Pending review' AS subtitle,
               rt.submitted_at AS timestamp,
               ns.slug AS namespace,
               s.slug AS skill_slug
        FROM review_task rt
        LEFT JOIN skill_version sv ON sv.id = rt.skill_version_id
        LEFT JOIN skill s ON s.id = sv.skill_id
        LEFT JOIN namespace ns ON ns.id = s.namespace_id
        WHERE rt.status = 'PENDING'
        {namespace_filter}
        ORDER BY rt.submitted_at DESC, rt.id DESC
        LIMIT :limit
    """
    if not _has_platform_governance_role(platform_roles):
        if not managed_namespace_ids:
            return []
        namespace_filter = "AND rt.namespace_id IN :namespace_ids"
        params["namespace_ids"] = managed_namespace_ids
    query = text(query_text.format(namespace_filter=namespace_filter))
    if "namespace_ids" in params:
        query = query.bindparams(bindparam("namespace_ids", expanding=True))
    return [dict(row) for row in (await connection.execute(query, params)).mappings().all()]


async def _read_promotion_inbox_rows(connection: Any, *, limit: int) -> list[dict[str, Any]]:
    rows = (
        await connection.execute(
            text(
                """
                /* promotion_inbox */
                SELECT 'PROMOTION' AS type,
                       pr.id,
                       COALESCE(source_ns.slug || '/' || source_skill.slug || '@' || source_version.version, 'Unknown target') AS title,
                       CASE
                         WHEN target_ns.slug IS NOT NULL THEN 'Promote to @' || target_ns.slug
                         ELSE 'Pending promotion'
                       END AS subtitle,
                       pr.submitted_at AS timestamp,
                       source_ns.slug AS namespace,
                       source_skill.slug AS skill_slug
                FROM promotion_request pr
                LEFT JOIN skill source_skill ON source_skill.id = pr.source_skill_id
                LEFT JOIN skill_version source_version ON source_version.id = pr.source_version_id
                LEFT JOIN namespace source_ns ON source_ns.id = source_skill.namespace_id
                LEFT JOIN namespace target_ns ON target_ns.id = pr.target_namespace_id
                WHERE pr.status = 'PENDING'
                ORDER BY pr.submitted_at DESC, pr.id DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def _read_report_inbox_rows(connection: Any, *, limit: int) -> list[dict[str, Any]]:
    rows = (
        await connection.execute(
            text(
                """
                /* report_inbox */
                SELECT 'REPORT' AS type,
                       sr.id,
                       COALESCE(ns.slug || '/' || s.slug, 'Unknown target') AS title,
                       sr.reason AS subtitle,
                       sr.created_at AS timestamp,
                       ns.slug AS namespace,
                       s.slug AS skill_slug
                FROM skill_report sr
                LEFT JOIN skill s ON s.id = sr.skill_id
                LEFT JOIN namespace ns ON ns.id = sr.namespace_id
                WHERE sr.status = 'PENDING'
                ORDER BY sr.created_at DESC, sr.id DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def list_governance_inbox(
    engine: Any,
    *,
    user_id: str,
    type_filter: str | None,
    page: int,
    size: int,
) -> dict[str, Any]:
    normalized_type = _normalize_inbox_type(type_filter)
    normalized_page = _normalize_page(page)
    normalized_size = _normalize_size(size)
    fetch_size = max((normalized_page + 1) * normalized_size, normalized_size)
    async with engine.connect() as connection:
        platform_roles = await _read_platform_roles(connection, user_id)
        namespace_roles = await _read_namespace_roles(connection, user_id)
        managed_ids = _managed_namespace_ids(namespace_roles)
        can_platform = _has_platform_governance_role(platform_roles)
        rows: list[dict[str, Any]] = []
        total = 0
        if normalized_type in (None, "REVIEW"):
            total += await _count_pending_reviews(
                connection,
                platform_roles=platform_roles,
                managed_namespace_ids=managed_ids,
            )
            rows.extend(
                await _read_review_inbox_rows(
                    connection,
                    platform_roles=platform_roles,
                    managed_namespace_ids=managed_ids,
                    limit=fetch_size,
                )
            )
        if can_platform and normalized_type in (None, "PROMOTION"):
            total += await _count_pending_promotions(connection)
            rows.extend(await _read_promotion_inbox_rows(connection, limit=fetch_size))
        if can_platform and normalized_type in (None, "REPORT"):
            total += await _count_pending_reports(connection)
            rows.extend(await _read_report_inbox_rows(connection, limit=fetch_size))
    rows.sort(key=lambda row: (_java_instant(row.get("timestamp")) is not None, _java_instant(row.get("timestamp")) or ""), reverse=True)
    start = normalized_page * normalized_size
    end = start + normalized_size
    return {
        "items": [_inbox_item(row) for row in rows[start:end]],
        "total": total,
        "page": normalized_page,
        "size": normalized_size,
    }


def _detail_string(detail_json: Any, target_type: Any, target_id: Any) -> str | None:
    if detail_json is not None:
        if isinstance(detail_json, (dict, list)):
            return json.dumps(detail_json, ensure_ascii=False, separators=(",", ":"))
        text_value = str(detail_json)
        if text_value.strip() != "":
            return text_value
    if target_type is None and target_id is None:
        return None
    return f"{target_type}:{target_id}"


def _activity_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "action": str(row["action"]),
        "actorUserId": row.get("actor_user_id"),
        "actorDisplayName": row.get("display_name"),
        "targetType": row.get("target_type"),
        "targetId": str(row["target_id"]) if row.get("target_id") is not None else None,
        "details": _detail_string(row.get("detail_json"), row.get("target_type"), row.get("target_id")),
        "timestamp": _java_instant(row.get("created_at")),
    }


async def list_governance_activity(engine: Any, *, user_id: str, page: int, size: int) -> dict[str, Any]:
    normalized_page = _normalize_page(page)
    normalized_size = _normalize_size(size)
    async with engine.connect() as connection:
        platform_roles = await _read_platform_roles(connection, user_id)
        if not _can_read_activity(platform_roles):
            return {"items": [], "total": 0, "page": normalized_page, "size": normalized_size}
        params = {
            "actions": sorted(ACTIVITY_ACTIONS),
            "limit": normalized_size,
            "offset": normalized_page * normalized_size,
        }
        count_query = text(
            """
            SELECT COUNT(*)
            FROM audit_log al
            WHERE al.action IN :actions
            """
        ).bindparams(bindparam("actions", expanding=True))
        total = int((await connection.execute(count_query, params)).scalar_one())
        query = text(
            """
            SELECT al.id,
                   al.action,
                   al.actor_user_id,
                   ua.display_name,
                   al.detail_json,
                   al.target_type,
                   al.target_id,
                   al.created_at
            FROM audit_log al
            LEFT JOIN user_account ua ON ua.id = al.actor_user_id
            WHERE al.action IN :actions
            ORDER BY al.created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ).bindparams(bindparam("actions", expanding=True))
        rows = (await connection.execute(query, params)).mappings().all()
    return {
        "items": [_activity_item(dict(row)) for row in rows],
        "total": total,
        "page": normalized_page,
        "size": normalized_size,
    }


def _governance_notification_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "category": str(row["category"]),
        "entityType": str(row["entity_type"]),
        "entityId": int(row["entity_id"]) if row.get("entity_id") is not None else None,
        "title": str(row["title"]),
        "bodyJson": row.get("body_json"),
        "status": str(row["status"]),
        "createdAt": _java_instant(row.get("created_at")),
        "readAt": _java_instant(row.get("read_at")),
    }


async def list_governance_notifications(engine: Any, *, user_id: str, page: int, size: int) -> dict[str, Any]:
    normalized_page = _normalize_page(page)
    normalized_size = _normalize_size(size)
    params = {"user_id": user_id, "limit": normalized_size, "offset": normalized_page * normalized_size}
    async with engine.connect() as connection:
        total = int(
            (
                await connection.execute(
                    text("SELECT COUNT(*) FROM user_notification WHERE user_id = :user_id"),
                    params,
                )
            ).scalar_one()
        )
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT id, category, entity_type, entity_id, title, body_json, status, created_at, read_at
                    FROM user_notification
                    WHERE user_id = :user_id
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            )
        ).mappings().all()
    return {
        "items": [_governance_notification_item(dict(row)) for row in rows],
        "total": total,
        "page": normalized_page,
        "size": normalized_size,
    }


async def mark_governance_notification_read(engine: Any, *, notification_id: int, user_id: str) -> dict[str, Any]:
    async with engine.begin() as connection:
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT id, user_id, category, entity_type, entity_id, title, body_json, status, created_at, read_at
                    FROM user_notification
                    WHERE id = :notification_id
                    """
                ),
                {"notification_id": notification_id},
            )
        ).mappings().all()
        if not rows:
            raise GovernanceWorkbenchError("error.notification.notFound", status_code=404)
        row = dict(rows[0])
        if str(row["user_id"]) != user_id:
            raise GovernanceWorkbenchError("error.notification.noPermission", status_code=403)
        read_at = datetime.now(UTC)
        updated_rows = (
            await connection.execute(
                text(
                    """
                    UPDATE user_notification
                    SET status = 'READ',
                        read_at = :read_at
                    WHERE id = :notification_id
                      AND user_id = :user_id
                    RETURNING id, category, entity_type, entity_id, title, body_json, status, created_at, read_at
                    """
                ),
                {"notification_id": notification_id, "user_id": user_id, "read_at": read_at},
            )
        ).mappings().all()
        if not updated_rows:
            raise GovernanceWorkbenchError("error.notification.noPermission", status_code=403)
    return _governance_notification_item(dict(updated_rows[0]))

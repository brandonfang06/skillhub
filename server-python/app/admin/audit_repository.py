from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any

from sqlalchemy import text


AUDIT_READ_ROLES = {"AUDITOR", "SUPER_ADMIN"}


class AdminAuditLogError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def require_audit_reader(platform_roles: list[str]) -> None:
    if {str(role) for role in platform_roles}.isdisjoint(AUDIT_READ_ROLES):
        raise AdminAuditLogError("error.admin.auditLog.readDenied", status_code=403)


def _java_instant(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        instant = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return instant.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return str(value).replace("+00:00", "Z")


def _normalize_page(page: int) -> int:
    return int(page)


def _offset_page(page: int) -> int:
    return max(0, int(page))


def _normalize_size(size: int) -> int:
    return int(size)


def _parse_instant(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    text_value = value.strip()
    if text_value == "":
        return None
    parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _trim(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    return value.strip()


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


def _audit_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "action": str(row["action"]),
        "userId": row.get("actor_user_id"),
        "username": row.get("display_name"),
        "details": _detail_string(row.get("detail_json"), row.get("target_type"), row.get("target_id")),
        "ipAddress": row.get("client_ip"),
        "requestId": row.get("request_id"),
        "resourceType": row.get("target_type"),
        "resourceId": str(row["target_id"]) if row.get("target_id") is not None else None,
        "timestamp": _java_instant(row.get("created_at")),
    }


def _where_clause(
    *,
    user_id: str | None,
    action: str | None,
    request_id: str | None,
    ip_address: str | None,
    resource_type: str | None,
    resource_id: str | None,
    start_time: datetime | str | None,
    end_time: datetime | str | None,
) -> tuple[str, dict[str, Any]]:
    filters = ["1 = 1"]
    params: dict[str, Any] = {}
    if (value := _trim(user_id)) is not None:
        filters.append("al.actor_user_id = :user_id")
        params["user_id"] = value
    if (value := _trim(action)) is not None:
        filters.append("al.action = :action")
        params["action"] = value
    if (value := _trim(request_id)) is not None:
        filters.append("al.request_id = :request_id")
        params["request_id"] = value
    if (value := _trim(ip_address)) is not None:
        filters.append("al.client_ip = :ip_address")
        params["ip_address"] = value
    if (value := _trim(resource_type)) is not None:
        filters.append("al.target_type = :resource_type")
        params["resource_type"] = value
    if (value := _trim(resource_id)) is not None:
        filters.append("CAST(al.target_id AS TEXT) = :resource_id")
        params["resource_id"] = value
    if (value := _parse_instant(start_time)) is not None:
        filters.append("al.created_at >= CAST(:start_time AS timestamptz)")
        params["start_time"] = value
    if (value := _parse_instant(end_time)) is not None:
        filters.append("al.created_at <= CAST(:end_time AS timestamptz)")
        params["end_time"] = value
    return " WHERE " + " AND ".join(filters), params


async def list_admin_audit_logs(
    engine: Any,
    *,
    page: int,
    size: int,
    user_id: str | None,
    action: str | None,
    request_id: str | None,
    ip_address: str | None,
    resource_type: str | None,
    resource_id: str | None,
    start_time: datetime | str | None,
    end_time: datetime | str | None,
    platform_roles: list[str],
) -> dict[str, Any]:
    require_audit_reader(platform_roles)
    normalized_page = _normalize_page(page)
    normalized_size = _normalize_size(size)
    where_clause, filter_params = _where_clause(
        user_id=user_id,
        action=action,
        request_id=request_id,
        ip_address=ip_address,
        resource_type=resource_type,
        resource_id=resource_id,
        start_time=start_time,
        end_time=end_time,
    )
    params = {
        **filter_params,
        "limit": normalized_size,
        "offset": _offset_page(normalized_page) * normalized_size,
    }
    async with engine.connect() as connection:
        total = int(
            (
                await connection.execute(
                    text(f"SELECT COUNT(*) FROM audit_log al{where_clause}"),
                    params,
                )
            ).scalar_one()
        )
        rows = (
            await connection.execute(
                text(
                    f"""
                    SELECT al.id,
                           al.action,
                           al.actor_user_id,
                           ua.display_name,
                           al.detail_json,
                           al.target_type,
                           al.target_id,
                           al.request_id,
                           al.client_ip,
                           al.created_at
                    FROM audit_log al
                    LEFT JOIN user_account ua ON ua.id = al.actor_user_id
                    {where_clause}
                    ORDER BY al.created_at DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            )
        ).mappings().all()
    return {
        "items": [_audit_item(dict(row)) for row in rows],
        "total": total,
        "page": normalized_page,
        "size": normalized_size,
    }

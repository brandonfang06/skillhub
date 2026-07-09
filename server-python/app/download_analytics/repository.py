from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import text

DownloadSource = Literal["api", "web", "cli"]
DOWNLOAD_EVENT_READ_ROLES = {"AUDITOR", "SKILL_ADMIN", "SUPER_ADMIN"}
NAMESPACE_ANALYTICS_ROLES = {"OWNER", "ADMIN"}
REQUEST_ID_MAX_LENGTH = 64
CLIENT_IP_MAX_LENGTH = 64
USER_AGENT_MAX_LENGTH = 512


@dataclass(frozen=True)
class DownloadEventContext:
    user_id: str | None
    source: DownloadSource
    request_id: str | None
    client_ip: str | None
    user_agent: str | None


class DownloadAnalyticsError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def require_platform_download_event_reader(platform_roles: list[str]) -> None:
    if {str(role) for role in platform_roles}.isdisjoint(DOWNLOAD_EVENT_READ_ROLES):
        raise DownloadAnalyticsError("error.downloadAnalytics.readDenied", status_code=403)


def _has_platform_download_event_role(platform_roles: list[str]) -> bool:
    return not {str(role) for role in platform_roles}.isdisjoint(DOWNLOAD_EVENT_READ_ROLES)


def _trim(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    return value.strip()


def _bounded_text(value: str | None, max_length: int) -> str | None:
    normalized = _trim(value)
    if normalized is None:
        return None
    return normalized[:max_length]


def _normalize_source(value: str | None) -> str | None:
    normalized = _trim(value)
    if normalized is None:
        return None
    lowered = normalized.lower()
    if lowered not in {"api", "web", "cli"}:
        raise DownloadAnalyticsError("error.downloadAnalytics.invalidSource", status_code=400)
    return lowered


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


def _java_instant(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        instant = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return instant.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return str(value).replace("+00:00", "Z")


async def prune_expired_download_events(connection: Any, *, retention_months: int) -> int:
    if retention_months <= 0:
        return 0
    result = await connection.execute(
        text(
            """
            DELETE FROM local_skill_download_event
            WHERE created_at < CURRENT_TIMESTAMP - (CAST(:retention_months AS integer) * INTERVAL '1 month')
            """
        ),
        {"retention_months": retention_months},
    )
    rowcount = getattr(result, "rowcount", 0)
    return max(int(rowcount or 0), 0)


def _download_event_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "skillId": int(row["skill_id"]),
        "skillVersionId": int(row["skill_version_id"]),
        "namespace": str(row["namespace_slug"]),
        "slug": str(row["skill_slug"]),
        "version": str(row["version"]),
        "source": str(row["source"]),
        "userId": row.get("user_id"),
        "username": row.get("display_name"),
        "requestId": row.get("request_id"),
        "ipAddress": row.get("client_ip"),
        "userAgent": row.get("user_agent"),
        "createdAt": _java_instant(row.get("created_at")),
    }


def _where_clause(
    *,
    namespace: str | None,
    slug: str | None,
    version: str | None,
    user_id: str | None,
    source: str | None,
    start_time: datetime | str | None,
    end_time: datetime | str | None,
) -> tuple[str, dict[str, Any]]:
    filters = ["1 = 1"]
    params: dict[str, Any] = {}
    if (value := _trim(namespace)) is not None:
        filters.append("de.namespace_slug = :namespace")
        params["namespace"] = value
    if (value := _trim(slug)) is not None:
        filters.append("de.skill_slug = :slug")
        params["slug"] = value
    if (value := _trim(version)) is not None:
        filters.append("de.version = :version")
        params["version"] = value
    if (value := _trim(user_id)) is not None:
        filters.append("de.user_id = :user_id")
        params["user_id"] = value
    if (value := _normalize_source(source)) is not None:
        filters.append("de.source = :source")
        params["source"] = value
    if (value := _parse_instant(start_time)) is not None:
        filters.append("de.created_at >= CAST(:start_time AS timestamptz)")
        params["start_time"] = value
    if (value := _parse_instant(end_time)) is not None:
        filters.append("de.created_at <= CAST(:end_time AS timestamptz)")
        params["end_time"] = value
    return " WHERE " + " AND ".join(filters), params


async def _list_download_events(
    connection: Any,
    *,
    page: int,
    size: int,
    namespace: str | None,
    slug: str | None,
    version: str | None,
    user_id: str | None,
    source: str | None,
    start_time: datetime | str | None,
    end_time: datetime | str | None,
) -> dict[str, Any]:
    normalized_page = max(0, int(page))
    normalized_size = max(1, min(int(size), 100))
    where_clause, filter_params = _where_clause(
        namespace=namespace,
        slug=slug,
        version=version,
        user_id=user_id,
        source=source,
        start_time=start_time,
        end_time=end_time,
    )
    params = {
        **filter_params,
        "limit": normalized_size,
        "offset": normalized_page * normalized_size,
    }
    total = int(
        (
            await connection.execute(
                text(f"SELECT COUNT(*) FROM local_skill_download_event de{where_clause}"),
                params,
            )
        ).scalar_one()
    )
    rows = (
        await connection.execute(
            text(
                f"""
                SELECT de.id,
                       de.skill_id,
                       de.skill_version_id,
                       de.namespace_slug,
                       de.skill_slug,
                       de.version,
                       de.source,
                       de.user_id,
                       ua.display_name,
                       de.request_id,
                       de.client_ip,
                       de.user_agent,
                       de.created_at
                FROM local_skill_download_event de
                LEFT JOIN user_account ua ON ua.id = de.user_id
                {where_clause}
                ORDER BY de.created_at DESC, de.id DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).mappings().all()
    return {
        "items": [_download_event_item(dict(row)) for row in rows],
        "total": total,
        "page": normalized_page,
        "size": normalized_size,
    }


async def list_admin_download_events(
    engine: Any,
    *,
    page: int,
    size: int,
    namespace: str | None,
    slug: str | None,
    version: str | None,
    user_id: str | None,
    source: str | None,
    start_time: datetime | str | None,
    end_time: datetime | str | None,
    platform_roles: list[str],
) -> dict[str, Any]:
    require_platform_download_event_reader(platform_roles)
    async with engine.connect() as connection:
        return await _list_download_events(
            connection,
            page=page,
            size=size,
            namespace=namespace,
            slug=slug,
            version=version,
            user_id=user_id,
            source=source,
            start_time=start_time,
            end_time=end_time,
        )


async def _read_skill_for_analytics(connection: Any, namespace: str, slug: str) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT s.id, s.owner_id, s.namespace_id
                FROM skill s
                JOIN namespace n ON n.id = s.namespace_id
                WHERE n.slug = :namespace
                  AND n.status = 'ACTIVE'
                  AND s.slug = :slug
                  AND s.status = 'ACTIVE'
                  AND s.hidden = false
                ORDER BY s.id ASC
                LIMIT 1
                """
            ),
            {"namespace": namespace, "slug": slug},
        )
    ).mappings().one_or_none()
    if row is None:
        raise DownloadAnalyticsError("error.skill.notFound", status_code=404)
    return dict(row)


async def _read_namespace_role(connection: Any, namespace_id: int, user_id: str) -> str | None:
    return (
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
    ).scalar_one_or_none()


async def list_skill_download_events(
    engine: Any,
    *,
    namespace: str,
    slug: str,
    page: int,
    size: int,
    version: str | None,
    user_id: str | None,
    source: str | None,
    start_time: datetime | str | None,
    end_time: datetime | str | None,
    actor_user_id: str,
    platform_roles: list[str],
) -> dict[str, Any]:
    normalized_namespace = _trim(namespace)
    normalized_slug = _trim(slug)
    if normalized_namespace is None or normalized_slug is None:
        raise DownloadAnalyticsError("error.skill.notFound", status_code=404)
    async with engine.connect() as connection:
        skill = await _read_skill_for_analytics(connection, normalized_namespace, normalized_slug)
        if not _has_platform_download_event_role(platform_roles) and str(skill["owner_id"]) != actor_user_id:
            namespace_role = await _read_namespace_role(connection, int(skill["namespace_id"]), actor_user_id)
            if str(namespace_role or "").upper() not in NAMESPACE_ANALYTICS_ROLES:
                raise DownloadAnalyticsError("error.downloadAnalytics.readDenied", status_code=403)
        return await _list_download_events(
            connection,
            page=page,
            size=size,
            namespace=normalized_namespace,
            slug=normalized_slug,
            version=version,
            user_id=user_id,
            source=source,
            start_time=start_time,
            end_time=end_time,
        )


async def record_skill_download_event(
    connection: Any,
    *,
    skill_id: int,
    skill_version_id: int,
    namespace: str,
    slug: str,
    version: str,
    context: DownloadEventContext,
) -> None:
    await connection.execute(
        text(
            """
            INSERT INTO local_skill_download_event (
                skill_id, skill_version_id, user_id, namespace_slug, skill_slug,
                version, source, request_id, client_ip, user_agent, created_at
            )
            VALUES (
                :skill_id, :skill_version_id, :user_id, :namespace, :slug,
                :version, :source, :request_id, :client_ip, :user_agent, CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "skill_id": skill_id,
            "skill_version_id": skill_version_id,
            "user_id": context.user_id,
            "namespace": namespace,
            "slug": slug,
            "version": version,
            "source": context.source,
            "request_id": _bounded_text(context.request_id, REQUEST_ID_MAX_LENGTH),
            "client_ip": _bounded_text(context.client_ip, CLIENT_IP_MAX_LENGTH),
            "user_agent": _bounded_text(context.user_agent, USER_AGENT_MAX_LENGTH),
        },
    )

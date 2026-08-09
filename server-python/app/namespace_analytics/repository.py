from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text

NAMESPACE_TYPES = {"ALL", "TEAM", "GLOBAL"}
NAMESPACE_STATUSES = {"ALL", "ACTIVE", "FROZEN", "ARCHIVED"}
DOWNLOAD_SOURCES = {"web", "cli", "api"}
SORT_COLUMNS = {
    "namespace": "display_name",
    "maintainers": "maintainer_count",
    "skills": "skill_count",
    "lifetimeDownloads": "lifetime_downloads",
    "periodDownloads": "period_downloads",
}
DIRECTIONS = {"asc", "desc"}
NAMESPACE_ANALYTICS_CSV_EXPORT_LIMIT = 10_000
NAMESPACE_ANALYTICS_CSV_FIELDS = (
    "namespace_id",
    "namespace_slug",
    "display_name",
    "namespace_type",
    "namespace_status",
    "maintainer_count",
    "skill_count",
    "lifetime_downloads",
    "period_downloads",
    "period_start_time",
    "period_end_time",
    "source",
)
CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")

COMMON_CTE_SQL = """
WITH filtered_namespaces AS (
    SELECT n.id,
           n.slug,
           n.display_name,
           n.type,
           n.status
    FROM namespace n
    WHERE (CAST(:namespace_type AS text) IS NULL OR n.type = CAST(:namespace_type AS text))
      AND (CAST(:namespace_status AS text) IS NULL OR n.status = CAST(:namespace_status AS text))
      AND (
          CAST(:query AS text) IS NULL
          OR LOWER(n.slug) LIKE CAST(:query AS text)
          OR LOWER(n.display_name) LIKE CAST(:query AS text)
      )
),
eligible_skills AS (
    SELECT s.id AS skill_id,
           s.namespace_id,
           s.owner_id,
           s.download_count
    FROM skill s
    JOIN filtered_namespaces fn ON fn.id = s.namespace_id
    WHERE s.status = 'ACTIVE'
      AND s.hidden = FALSE
      AND EXISTS (
          SELECT 1
          FROM skill_version sv
          WHERE sv.skill_id = s.id
            AND sv.status = 'PUBLISHED'
      )
),
period_by_skill AS (
    SELECT de.skill_id,
           COUNT(*) AS period_downloads
    FROM local_skill_download_event de
    JOIN eligible_skills es ON de.skill_id = es.skill_id
    WHERE de.created_at >= CAST(:start_time AS timestamptz)
      AND de.created_at <= CAST(:end_time AS timestamptz)
      AND (CAST(:source AS text) IS NULL OR de.source = CAST(:source AS text))
    GROUP BY de.skill_id
),
namespace_metrics AS (
    SELECT fn.id AS namespace_id,
           fn.slug,
           fn.display_name,
           fn.type,
           fn.status,
           COUNT(DISTINCT es.owner_id) AS maintainer_count,
           COUNT(es.skill_id) AS skill_count,
           COALESCE(SUM(es.download_count), 0) AS lifetime_downloads,
           COALESCE(SUM(pd.period_downloads), 0) AS period_downloads
    FROM filtered_namespaces fn
    LEFT JOIN eligible_skills es ON es.namespace_id = fn.id
    LEFT JOIN period_by_skill pd ON pd.skill_id = es.skill_id
    GROUP BY fn.id, fn.slug, fn.display_name, fn.type, fn.status
)
"""


@dataclass(frozen=True)
class ResolvedPeriod:
    start_time: datetime
    end_time: datetime


@dataclass(frozen=True)
class NormalizedNamespaceAnalyticsQuery:
    params: dict[str, Any]
    sort: str
    direction: str
    period: ResolvedPeriod


class NamespaceAnalyticsError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _parse_instant(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    text_value = value.strip()
    if text_value == "":
        return None
    try:
        parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise NamespaceAnalyticsError("error.namespaceAnalytics.invalidTimeRange") from exc
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def resolve_period(
    start_time: datetime | str | None,
    end_time: datetime | str | None,
    *,
    now: datetime | None = None,
) -> ResolvedPeriod:
    resolved_now = now or datetime.now(UTC)
    if resolved_now.tzinfo is None:
        resolved_now = resolved_now.replace(tzinfo=UTC)
    resolved_end = _parse_instant(end_time) or resolved_now
    resolved_start = _parse_instant(start_time) or (resolved_end - timedelta(days=30))
    if resolved_start > resolved_end:
        raise NamespaceAnalyticsError("error.namespaceAnalytics.invalidTimeRange")
    return ResolvedPeriod(start_time=resolved_start, end_time=resolved_end)


def _trim(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    return value.strip()


def _normalize_upper(value: str, allowed: set[str]) -> str:
    normalized = value.strip().upper()
    if normalized not in allowed:
        raise NamespaceAnalyticsError("error.namespaceAnalytics.invalidFilter")
    return normalized


def _normalize_lower(value: str, allowed: set[str]) -> str:
    normalized = value.strip().lower()
    if normalized not in allowed:
        raise NamespaceAnalyticsError("error.namespaceAnalytics.invalidFilter")
    return normalized


def _normalize_sort(value: str) -> str:
    normalized = value.strip()
    if normalized not in SORT_COLUMNS:
        raise NamespaceAnalyticsError("error.namespaceAnalytics.invalidFilter")
    return normalized


def _summary_item(row: dict[str, Any]) -> dict[str, int]:
    return {
        "namespaceCount": int(row.get("namespace_count") or 0),
        "maintainerCount": int(row.get("maintainer_count") or 0),
        "skillCount": int(row.get("skill_count") or 0),
        "lifetimeDownloads": int(row.get("lifetime_downloads") or 0),
        "periodDownloads": int(row.get("period_downloads") or 0),
    }


def _namespace_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "namespaceId": int(row["namespace_id"]),
        "slug": str(row["slug"]),
        "displayName": str(row["display_name"]),
        "type": str(row["type"]),
        "status": str(row["status"]),
        "maintainerCount": int(row.get("maintainer_count") or 0),
        "skillCount": int(row.get("skill_count") or 0),
        "lifetimeDownloads": int(row.get("lifetime_downloads") or 0),
        "periodDownloads": int(row.get("period_downloads") or 0),
    }


def _order_sql(sort: str, direction: str) -> str:
    column = SORT_COLUMNS[sort]
    sql_direction = direction.upper()
    if sort == "periodDownloads" and direction == "desc":
        return "period_downloads DESC, lifetime_downloads DESC, skill_count DESC, slug ASC"
    return f"{column} {sql_direction}, slug ASC"


def _normalize_analytics_query(
    *,
    query: str | None,
    namespace_type: str,
    namespace_status: str,
    start_time: datetime | str | None,
    end_time: datetime | str | None,
    source: str | None,
    sort: str,
    direction: str,
    now: datetime | None,
) -> NormalizedNamespaceAnalyticsQuery:
    normalized_type = _normalize_upper(namespace_type, NAMESPACE_TYPES)
    normalized_status = _normalize_upper(namespace_status, NAMESPACE_STATUSES)
    normalized_source = None if _trim(source) is None else _normalize_lower(source or "", DOWNLOAD_SOURCES)
    normalized_sort = _normalize_sort(sort)
    normalized_direction = _normalize_lower(direction, DIRECTIONS)
    period = resolve_period(start_time, end_time, now=now)
    normalized_query = _trim(query)
    return NormalizedNamespaceAnalyticsQuery(
        params={
            "query": f"%{normalized_query.lower()}%" if normalized_query is not None else None,
            "namespace_type": None if normalized_type == "ALL" else normalized_type,
            "namespace_status": None if normalized_status == "ALL" else normalized_status,
            "start_time": period.start_time,
            "end_time": period.end_time,
            "source": normalized_source,
        },
        sort=normalized_sort,
        direction=normalized_direction,
        period=period,
    )


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    text_value = str(value)
    if text_value.startswith(CSV_FORMULA_PREFIXES):
        return f"'{text_value}"
    return text_value


def render_namespace_analytics_csv(
    items: list[dict[str, Any]],
    period: ResolvedPeriod,
    *,
    source: str | None,
) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=NAMESPACE_ANALYTICS_CSV_FIELDS,
        extrasaction="ignore",
        lineterminator="\r\n",
    )
    writer.writeheader()
    period_start = period.start_time.astimezone(UTC).isoformat()
    period_end = period.end_time.astimezone(UTC).isoformat()
    for item in items:
        row = {
            "namespace_id": item["namespaceId"],
            "namespace_slug": item["slug"],
            "display_name": item["displayName"],
            "namespace_type": item["type"],
            "namespace_status": item["status"],
            "maintainer_count": item["maintainerCount"],
            "skill_count": item["skillCount"],
            "lifetime_downloads": item["lifetimeDownloads"],
            "period_downloads": item["periodDownloads"],
            "period_start_time": period_start,
            "period_end_time": period_end,
            "source": source,
        }
        writer.writerow({field: _csv_cell(row.get(field)) for field in NAMESPACE_ANALYTICS_CSV_FIELDS})
    return f"\ufeff{buffer.getvalue()}"


async def list_namespace_analytics(
    engine: Any,
    *,
    query: str | None,
    namespace_type: str,
    namespace_status: str,
    start_time: datetime | str | None,
    end_time: datetime | str | None,
    source: str | None,
    sort: str,
    direction: str,
    page: int,
    size: int,
    retention_months: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    normalized = _normalize_analytics_query(
        query=query,
        namespace_type=namespace_type,
        namespace_status=namespace_status,
        start_time=start_time,
        end_time=end_time,
        source=source,
        sort=sort,
        direction=direction,
        now=now,
    )
    normalized_page = max(0, int(page))
    normalized_size = max(1, min(int(size), 100))
    summary_sql = text(
        COMMON_CTE_SQL
        + """
        SELECT /* namespace-analytics-summary */
               (SELECT COUNT(*) FROM filtered_namespaces) AS namespace_count,
               (SELECT COUNT(DISTINCT es.owner_id) FROM eligible_skills es) AS maintainer_count,
               COALESCE(SUM(nm.skill_count), 0) AS skill_count,
               COALESCE(SUM(nm.lifetime_downloads), 0) AS lifetime_downloads,
               COALESCE(SUM(nm.period_downloads), 0) AS period_downloads
        FROM namespace_metrics nm
        """
    )
    item_sql = text(
        COMMON_CTE_SQL
        + f"""
        SELECT /* namespace-analytics-items */
               namespace_id,
               slug,
               display_name,
               type,
               status,
               maintainer_count,
               skill_count,
               lifetime_downloads,
               period_downloads
        FROM namespace_metrics
        ORDER BY {_order_sql(normalized.sort, normalized.direction)}
        LIMIT :limit OFFSET :offset
        """
    )
    async with engine.connect() as connection:
        summary_row = dict((await connection.execute(summary_sql, normalized.params)).mappings().one())
        rows = (
            await connection.execute(
                item_sql,
                {
                    **normalized.params,
                    "limit": normalized_size,
                    "offset": normalized_page * normalized_size,
                },
            )
        ).mappings().all()
    summary = _summary_item(summary_row)
    return {
        "summary": summary,
        "period": {
            "startTime": normalized.period.start_time,
            "endTime": normalized.period.end_time,
            "source": normalized.params["source"],
            "retentionMonths": max(0, int(retention_months)),
        },
        "items": [_namespace_item(dict(row)) for row in rows],
        "page": normalized_page,
        "size": normalized_size,
        "total": summary["namespaceCount"],
    }


async def export_namespace_analytics_csv(
    engine: Any,
    *,
    query: str | None,
    namespace_type: str,
    namespace_status: str,
    start_time: datetime | str | None,
    end_time: datetime | str | None,
    source: str | None,
    sort: str,
    direction: str,
    limit: int = NAMESPACE_ANALYTICS_CSV_EXPORT_LIMIT,
    now: datetime | None = None,
) -> tuple[str, bool]:
    normalized = _normalize_analytics_query(
        query=query,
        namespace_type=namespace_type,
        namespace_status=namespace_status,
        start_time=start_time,
        end_time=end_time,
        source=source,
        sort=sort,
        direction=direction,
        now=now,
    )
    normalized_limit = max(1, min(int(limit), NAMESPACE_ANALYTICS_CSV_EXPORT_LIMIT))
    export_sql = text(
        COMMON_CTE_SQL
        + f"""
        SELECT /* namespace-analytics-export */
               namespace_id,
               slug,
               display_name,
               type,
               status,
               maintainer_count,
               skill_count,
               lifetime_downloads,
               period_downloads
        FROM namespace_metrics
        ORDER BY {_order_sql(normalized.sort, normalized.direction)}
        LIMIT :limit
        """
    )
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                export_sql,
                {**normalized.params, "limit": normalized_limit + 1},
            )
        ).mappings().all()
    truncated = len(rows) > normalized_limit
    items = [_namespace_item(dict(row)) for row in rows[:normalized_limit]]
    return (
        render_namespace_analytics_csv(
            items,
            normalized.period,
            source=normalized.params["source"],
        ),
        truncated,
    )

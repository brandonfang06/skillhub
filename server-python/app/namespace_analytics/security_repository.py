from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

NAMESPACE_TYPES = {"ALL", "TEAM", "GLOBAL"}
NAMESPACE_STATUSES = {"ALL", "ACTIVE", "FROZEN", "ARCHIVED"}
SKILL_STATUSES = {"ALL", "ACTIVE", "ARCHIVED"}
VISIBILITIES = {"ALL", "PUBLIC", "NAMESPACE_ONLY", "PRIVATE"}
HIDDEN_STATES = {"ALL", "VISIBLE", "HIDDEN"}
VERSION_STATUSES = {
    "ALL",
    "DRAFT",
    "SCANNING",
    "SCAN_FAILED",
    "UPLOADED",
    "PENDING_REVIEW",
    "PUBLISHED",
    "REJECTED",
    "YANKED",
}
SEVERITIES = {"ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNCLASSIFIED"}
SCANNER_TYPES = {"skill-scanner": "SKILL_SCANNER", "custom": "CUSTOM"}
SCANNER_TYPES_DB_TO_API = {value: key for key, value in SCANNER_TYPES.items()}
SORT_COLUMNS = {
    "namespace": "display_name",
    "affectedSkills": "skill_count",
    "affectedVersions": "version_count",
    "findings": "finding_count",
    "latestScan": "latest_scan_at",
}
DIRECTIONS = {"asc", "desc"}

SECURITY_CTE_SQL = """
WITH latest_audits AS (
    SELECT DISTINCT ON (sa.skill_version_id, sa.scanner_type)
           sa.id,
           sa.skill_version_id,
           sa.scanner_type,
           sa.findings_count,
           sa.findings,
           sa.scanned_at,
           sa.created_at
    FROM security_audit sa
    WHERE sa.deleted_at IS NULL
    ORDER BY sa.skill_version_id,
             sa.scanner_type,
             sa.created_at DESC,
             sa.id DESC
),
audit_severity_counts AS (
    SELECT la.id AS audit_id,
           la.skill_version_id,
           la.scanner_type,
           COALESCE(la.scanned_at, la.created_at) AS scan_at,
           GREATEST(la.findings_count::bigint, COUNT(finding.value)) AS finding_count,
           COUNT(finding.value) FILTER (
               WHERE UPPER(COALESCE(finding.value ->> 'severity', '')) = 'CRITICAL'
           ) AS critical_count,
           COUNT(finding.value) FILTER (
               WHERE UPPER(COALESCE(finding.value ->> 'severity', '')) = 'HIGH'
           ) AS high_count,
           COUNT(finding.value) FILTER (
               WHERE UPPER(COALESCE(finding.value ->> 'severity', '')) = 'MEDIUM'
           ) AS medium_count,
           COUNT(finding.value) FILTER (
               WHERE UPPER(COALESCE(finding.value ->> 'severity', '')) = 'LOW'
           ) AS low_count,
           COUNT(finding.value) FILTER (
               WHERE UPPER(COALESCE(finding.value ->> 'severity', '')) = 'INFO'
           ) AS info_count,
           GREATEST(
               GREATEST(la.findings_count::bigint, COUNT(finding.value))
               - COUNT(finding.value) FILTER (
                   WHERE UPPER(COALESCE(finding.value ->> 'severity', ''))
                         IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO')
               ),
               0
           ) AS unclassified_count
    FROM latest_audits la
    LEFT JOIN LATERAL jsonb_array_elements(
        CASE
            WHEN jsonb_typeof(la.findings) = 'array' THEN la.findings
            ELSE '[]'::jsonb
        END
    ) AS finding(value) ON TRUE
    GROUP BY la.id,
             la.skill_version_id,
             la.scanner_type,
             la.findings_count,
             la.scanned_at,
             la.created_at
),
filtered_findings AS (
    SELECT n.id AS namespace_id,
           n.slug AS namespace_slug,
           n.display_name AS namespace_display_name,
           n.type AS namespace_type,
           n.status AS namespace_status,
           s.id AS skill_id,
           s.slug AS skill_slug,
           s.display_name AS skill_display_name,
           s.owner_id,
           s.visibility,
           s.status AS skill_status,
           COALESCE(s.hidden, FALSE) AS hidden,
           sv.id AS version_id,
           sv.version,
           sv.status AS version_status,
           counts.scanner_type,
           counts.scan_at,
           counts.finding_count,
           counts.critical_count,
           counts.high_count,
           counts.medium_count,
           counts.low_count,
           counts.info_count,
           counts.unclassified_count
    FROM audit_severity_counts counts
    JOIN skill_version sv ON sv.id = counts.skill_version_id
    JOIN skill s ON s.id = sv.skill_id
    JOIN namespace n ON n.id = s.namespace_id
    WHERE counts.finding_count > 0
      AND (CAST(:namespace_type AS text) IS NULL OR n.type = CAST(:namespace_type AS text))
      AND (CAST(:namespace_status AS text) IS NULL OR n.status = CAST(:namespace_status AS text))
      AND (CAST(:skill_status AS text) IS NULL OR s.status = CAST(:skill_status AS text))
      AND (CAST(:visibility AS text) IS NULL OR s.visibility = CAST(:visibility AS text))
      AND (CAST(:hidden AS boolean) IS NULL OR COALESCE(s.hidden, FALSE) = CAST(:hidden AS boolean))
      AND (CAST(:version_status AS text) IS NULL OR sv.status = CAST(:version_status AS text))
      AND (CAST(:scanner_type AS text) IS NULL OR counts.scanner_type = CAST(:scanner_type AS text))
      AND (CAST(:namespace_id AS bigint) IS NULL OR n.id = CAST(:namespace_id AS bigint))
      AND (
          CAST(:query AS text) IS NULL
          OR LOWER(n.slug) LIKE CAST(:query AS text)
          OR LOWER(n.display_name) LIKE CAST(:query AS text)
          OR LOWER(s.slug) LIKE CAST(:query AS text)
          OR LOWER(COALESCE(s.display_name, '')) LIKE CAST(:query AS text)
      )
      AND (
          CAST(:severity AS text) IS NULL
          OR (CAST(:severity AS text) = 'CRITICAL' AND counts.critical_count > 0)
          OR (CAST(:severity AS text) = 'HIGH' AND counts.high_count > 0)
          OR (CAST(:severity AS text) = 'MEDIUM' AND counts.medium_count > 0)
          OR (CAST(:severity AS text) = 'LOW' AND counts.low_count > 0)
          OR (CAST(:severity AS text) = 'INFO' AND counts.info_count > 0)
          OR (CAST(:severity AS text) = 'UNCLASSIFIED' AND counts.unclassified_count > 0)
      )
),
namespace_security_metrics AS (
    SELECT namespace_id,
           namespace_slug AS slug,
           namespace_display_name AS display_name,
           namespace_type AS type,
           namespace_status AS status,
           COUNT(DISTINCT skill_id) AS skill_count,
           COUNT(DISTINCT version_id) AS version_count,
           COALESCE(SUM(finding_count), 0) AS finding_count,
           COALESCE(SUM(critical_count), 0) AS critical_count,
           COALESCE(SUM(high_count), 0) AS high_count,
           COALESCE(SUM(medium_count), 0) AS medium_count,
           COALESCE(SUM(low_count), 0) AS low_count,
           COALESCE(SUM(info_count), 0) AS info_count,
           COALESCE(SUM(unclassified_count), 0) AS unclassified_count,
           MAX(scan_at) AS latest_scan_at
    FROM filtered_findings
    GROUP BY namespace_id,
             namespace_slug,
             namespace_display_name,
             namespace_type,
             namespace_status
)
"""


class NamespaceSecurityAnalyticsError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class NormalizedSecurityAnalyticsQuery:
    params: dict[str, Any]
    sort: str
    direction: str


def _trim(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    return value.strip()


def _normalize_upper(value: str, allowed: set[str]) -> str:
    normalized = value.strip().upper()
    if normalized not in allowed:
        raise NamespaceSecurityAnalyticsError("error.namespaceSecurityAnalytics.invalidFilter")
    return normalized


def _normalize_lower(value: str, allowed: set[str]) -> str:
    normalized = value.strip().lower()
    if normalized not in allowed:
        raise NamespaceSecurityAnalyticsError("error.namespaceSecurityAnalytics.invalidFilter")
    return normalized


def _normalize_query(
    *,
    query: str | None,
    severity: str,
    namespace_type: str,
    namespace_status: str,
    skill_status: str,
    visibility: str,
    hidden: str,
    version_status: str,
    scanner_type: str | None,
    sort: str,
    direction: str,
) -> NormalizedSecurityAnalyticsQuery:
    normalized_severity = _normalize_upper(severity, SEVERITIES)
    normalized_namespace_type = _normalize_upper(namespace_type, NAMESPACE_TYPES)
    normalized_namespace_status = _normalize_upper(namespace_status, NAMESPACE_STATUSES)
    normalized_skill_status = _normalize_upper(skill_status, SKILL_STATUSES)
    normalized_visibility = _normalize_upper(visibility, VISIBILITIES)
    normalized_hidden = _normalize_upper(hidden, HIDDEN_STATES)
    normalized_version_status = _normalize_upper(version_status, VERSION_STATUSES)
    normalized_scanner = _trim(scanner_type)
    if normalized_scanner is not None and normalized_scanner not in SCANNER_TYPES:
        raise NamespaceSecurityAnalyticsError("error.namespaceSecurityAnalytics.invalidFilter")
    normalized_sort = sort.strip()
    if normalized_sort != "risk" and normalized_sort not in SORT_COLUMNS:
        raise NamespaceSecurityAnalyticsError("error.namespaceSecurityAnalytics.invalidFilter")
    normalized_direction = _normalize_lower(direction, DIRECTIONS)
    normalized_text = _trim(query)
    return NormalizedSecurityAnalyticsQuery(
        params={
            "query": f"%{normalized_text.lower()}%" if normalized_text is not None else None,
            "severity": None if normalized_severity == "ALL" else normalized_severity,
            "namespace_type": None if normalized_namespace_type == "ALL" else normalized_namespace_type,
            "namespace_status": None if normalized_namespace_status == "ALL" else normalized_namespace_status,
            "skill_status": None if normalized_skill_status == "ALL" else normalized_skill_status,
            "visibility": None if normalized_visibility == "ALL" else normalized_visibility,
            "hidden": None if normalized_hidden == "ALL" else normalized_hidden == "HIDDEN",
            "version_status": None if normalized_version_status == "ALL" else normalized_version_status,
            "scanner_type": SCANNER_TYPES.get(normalized_scanner) if normalized_scanner is not None else None,
            "namespace_id": None,
        },
        sort=normalized_sort,
        direction=normalized_direction,
    )


def _severity_counts(row: dict[str, Any]) -> dict[str, int]:
    return {
        "critical": int(row.get("critical_count") or 0),
        "high": int(row.get("high_count") or 0),
        "medium": int(row.get("medium_count") or 0),
        "low": int(row.get("low_count") or 0),
        "info": int(row.get("info_count") or 0),
        "unclassified": int(row.get("unclassified_count") or 0),
    }


def _max_severity(counts: dict[str, int]) -> str:
    for key in ("critical", "high", "medium", "low", "info", "unclassified"):
        if counts[key] > 0:
            return key.upper()
    return "UNCLASSIFIED"


def _summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "affectedNamespaceCount": int(row.get("namespace_count") or 0),
        "affectedSkillCount": int(row.get("skill_count") or 0),
        "affectedVersionCount": int(row.get("version_count") or 0),
        "findingCount": int(row.get("finding_count") or 0),
        "severityCounts": _severity_counts(row),
    }


def _namespace_item(row: dict[str, Any]) -> dict[str, Any]:
    counts = _severity_counts(row)
    return {
        "namespaceId": int(row["namespace_id"]),
        "slug": str(row["slug"]),
        "displayName": str(row["display_name"]),
        "type": str(row["type"]),
        "status": str(row["status"]),
        "affectedSkillCount": int(row.get("skill_count") or 0),
        "affectedVersionCount": int(row.get("version_count") or 0),
        "findingCount": int(row.get("finding_count") or 0),
        "severityCounts": counts,
        "maxSeverity": _max_severity(counts),
        "latestScanAt": row["latest_scan_at"],
    }


def _order_sql(sort: str, direction: str) -> str:
    sql_direction = direction.upper()
    if sort == "risk":
        return (
            f"critical_count {sql_direction}, high_count {sql_direction}, "
            f"medium_count {sql_direction}, finding_count {sql_direction}, "
            f"latest_scan_at {sql_direction} NULLS LAST, slug ASC"
        )
    column = SORT_COLUMNS[sort]
    nulls = " NULLS LAST" if sort == "latestScan" else ""
    return f"{column} {sql_direction}{nulls}, slug ASC"


async def list_namespace_security_analytics(
    engine: Any,
    *,
    query: str | None,
    severity: str,
    namespace_type: str,
    namespace_status: str,
    skill_status: str,
    visibility: str,
    hidden: str,
    version_status: str,
    scanner_type: str | None,
    sort: str,
    direction: str,
    page: int,
    size: int,
) -> dict[str, Any]:
    normalized = _normalize_query(
        query=query,
        severity=severity,
        namespace_type=namespace_type,
        namespace_status=namespace_status,
        skill_status=skill_status,
        visibility=visibility,
        hidden=hidden,
        version_status=version_status,
        scanner_type=scanner_type,
        sort=sort,
        direction=direction,
    )
    normalized_page = max(0, int(page))
    normalized_size = max(1, min(int(size), 100))
    summary_sql = text(
        SECURITY_CTE_SQL
        + """
        SELECT /* namespace-security-summary */
               COUNT(DISTINCT namespace_id) AS namespace_count,
               COUNT(DISTINCT skill_id) AS skill_count,
               COUNT(DISTINCT version_id) AS version_count,
               COALESCE(SUM(finding_count), 0) AS finding_count,
               COALESCE(SUM(critical_count), 0) AS critical_count,
               COALESCE(SUM(high_count), 0) AS high_count,
               COALESCE(SUM(medium_count), 0) AS medium_count,
               COALESCE(SUM(low_count), 0) AS low_count,
               COALESCE(SUM(info_count), 0) AS info_count,
               COALESCE(SUM(unclassified_count), 0) AS unclassified_count
        FROM filtered_findings
        """
    )
    item_sql = text(
        SECURITY_CTE_SQL
        + f"""
        SELECT /* namespace-security-items */
               namespace_id,
               slug,
               display_name,
               type,
               status,
               skill_count,
               version_count,
               finding_count,
               critical_count,
               high_count,
               medium_count,
               low_count,
               info_count,
               unclassified_count,
               latest_scan_at
        FROM namespace_security_metrics
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
    summary = _summary(summary_row)
    return {
        "summary": summary,
        "items": [_namespace_item(dict(row)) for row in rows],
        "page": normalized_page,
        "size": normalized_size,
        "total": summary["affectedNamespaceCount"],
    }


SKILL_SECURITY_CTE_SQL = (
    SECURITY_CTE_SQL
    + """,
skill_security_metrics AS (
    SELECT findings.skill_id,
           findings.skill_slug AS slug,
           COALESCE(findings.skill_display_name, findings.skill_slug) AS display_name,
           findings.owner_id,
           NULLIF(BTRIM(owner.display_name), '') AS owner_display_name,
           findings.visibility,
           findings.skill_status AS status,
           findings.hidden,
           COUNT(DISTINCT findings.version_id) AS version_count,
           COALESCE(SUM(findings.finding_count), 0) AS finding_count,
           COALESCE(SUM(findings.critical_count), 0) AS critical_count,
           COALESCE(SUM(findings.high_count), 0) AS high_count,
           COALESCE(SUM(findings.medium_count), 0) AS medium_count,
           COALESCE(SUM(findings.low_count), 0) AS low_count,
           COALESCE(SUM(findings.info_count), 0) AS info_count,
           COALESCE(SUM(findings.unclassified_count), 0) AS unclassified_count,
           MAX(findings.scan_at) AS latest_scan_at
    FROM filtered_findings findings
    LEFT JOIN user_account owner ON owner.id = findings.owner_id
    GROUP BY findings.skill_id,
             findings.skill_slug,
             findings.skill_display_name,
             findings.owner_id,
             owner.display_name,
             findings.visibility,
             findings.skill_status,
             findings.hidden
)
"""
)

SKILL_SORT_COLUMNS = {
    "skill": "display_name",
    "affectedVersions": "version_count",
    "findings": "finding_count",
    "latestScan": "latest_scan_at",
}


def _skill_order_sql(sort: str, direction: str) -> str:
    sql_direction = direction.upper()
    if sort == "risk":
        return (
            f"critical_count {sql_direction}, high_count {sql_direction}, "
            f"medium_count {sql_direction}, finding_count {sql_direction}, "
            f"latest_scan_at {sql_direction} NULLS LAST, slug ASC"
        )
    column = SKILL_SORT_COLUMNS[sort]
    nulls = " NULLS LAST" if sort == "latestScan" else ""
    return f"{column} {sql_direction}{nulls}, slug ASC"


def _version_item(row: dict[str, Any]) -> dict[str, Any]:
    counts = _severity_counts(row)
    return {
        "versionId": int(row["version_id"]),
        "version": str(row["version"]),
        "status": str(row["status"]),
        "findingCount": int(row.get("finding_count") or 0),
        "severityCounts": counts,
        "maxSeverity": _max_severity(counts),
        "latestScanAt": row["latest_scan_at"],
        "scannerTypes": [
            SCANNER_TYPES_DB_TO_API.get(str(scanner_type), str(scanner_type).lower().replace("_", "-"))
            for scanner_type in (row.get("scanner_types") or [])
        ],
    }


def _skill_item(row: dict[str, Any], versions: list[dict[str, Any]]) -> dict[str, Any]:
    counts = _severity_counts(row)
    return {
        "skillId": int(row["skill_id"]),
        "slug": str(row["slug"]),
        "displayName": str(row["display_name"]),
        "ownerId": str(row["owner_id"]),
        "ownerDisplayName": row.get("owner_display_name"),
        "visibility": str(row["visibility"]),
        "status": str(row["status"]),
        "hidden": bool(row["hidden"]),
        "affectedVersionCount": int(row.get("version_count") or 0),
        "findingCount": int(row.get("finding_count") or 0),
        "severityCounts": counts,
        "maxSeverity": _max_severity(counts),
        "latestScanAt": row["latest_scan_at"],
        "versions": versions,
    }


async def list_namespace_security_skills(
    engine: Any,
    *,
    namespace_id: int,
    query: str | None,
    severity: str,
    skill_status: str,
    visibility: str,
    hidden: str,
    version_status: str,
    scanner_type: str | None,
    sort: str,
    direction: str,
    page: int,
    size: int,
) -> dict[str, Any]:
    normalized_sort = sort.strip()
    if normalized_sort != "risk" and normalized_sort not in SKILL_SORT_COLUMNS:
        raise NamespaceSecurityAnalyticsError("error.namespaceSecurityAnalytics.invalidFilter")
    normalized = _normalize_query(
        query=query,
        severity=severity,
        namespace_type="ALL",
        namespace_status="ALL",
        skill_status=skill_status,
        visibility=visibility,
        hidden=hidden,
        version_status=version_status,
        scanner_type=scanner_type,
        sort="risk",
        direction=direction,
    )
    params = {**normalized.params, "namespace_id": max(1, int(namespace_id))}
    normalized_page = max(0, int(page))
    normalized_size = max(1, min(int(size), 100))
    total_sql = text(
        SKILL_SECURITY_CTE_SQL
        + """
        SELECT /* namespace-security-skill-total */
               COUNT(*) AS skill_count
        FROM skill_security_metrics
        """
    )
    item_sql = text(
        SKILL_SECURITY_CTE_SQL
        + f"""
        SELECT /* namespace-security-skill-items */
               skill_id,
               slug,
               display_name,
               owner_id,
               owner_display_name,
               visibility,
               status,
               hidden,
               version_count,
               finding_count,
               critical_count,
               high_count,
               medium_count,
               low_count,
               info_count,
               unclassified_count,
               latest_scan_at
        FROM skill_security_metrics
        ORDER BY {_skill_order_sql(normalized_sort, normalized.direction)}
        LIMIT :limit OFFSET :offset
        """
    )
    version_sql = text(
        SECURITY_CTE_SQL
        + """
        SELECT /* namespace-security-version-items */
               skill_id,
               version_id,
               version,
               version_status AS status,
               COALESCE(SUM(finding_count), 0) AS finding_count,
               COALESCE(SUM(critical_count), 0) AS critical_count,
               COALESCE(SUM(high_count), 0) AS high_count,
               COALESCE(SUM(medium_count), 0) AS medium_count,
               COALESCE(SUM(low_count), 0) AS low_count,
               COALESCE(SUM(info_count), 0) AS info_count,
               COALESCE(SUM(unclassified_count), 0) AS unclassified_count,
               MAX(scan_at) AS latest_scan_at,
               ARRAY_AGG(DISTINCT scanner_type ORDER BY scanner_type) AS scanner_types
        FROM filtered_findings
        WHERE skill_id = ANY(CAST(:skill_ids AS bigint[]))
        GROUP BY skill_id, version_id, version, version_status
        ORDER BY skill_id ASC,
                 critical_count DESC,
                 high_count DESC,
                 medium_count DESC,
                 finding_count DESC,
                 version ASC
        """
    )
    async with engine.connect() as connection:
        total_row = dict((await connection.execute(total_sql, params)).mappings().one())
        rows = (
            await connection.execute(
                item_sql,
                {
                    **params,
                    "limit": normalized_size,
                    "offset": normalized_page * normalized_size,
                },
            )
        ).mappings().all()
        skill_ids = [int(row["skill_id"]) for row in rows]
        version_rows = []
        if skill_ids:
            version_rows = (
                await connection.execute(version_sql, {**params, "skill_ids": skill_ids})
            ).mappings().all()
    versions_by_skill: dict[int, list[dict[str, Any]]] = {skill_id: [] for skill_id in skill_ids}
    for version_row in version_rows:
        row = dict(version_row)
        versions_by_skill[int(row["skill_id"])].append(_version_item(row))
    return {
        "items": [
            _skill_item(dict(row), versions_by_skill[int(row["skill_id"])])
            for row in rows
        ],
        "page": normalized_page,
        "size": normalized_size,
        "total": int(total_row.get("skill_count") or 0),
    }

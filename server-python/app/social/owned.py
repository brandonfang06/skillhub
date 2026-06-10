from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.api.skills import to_java_instant, to_lifecycle_version


MY_SKILL_FILTERS = {"ALL", "PENDING_REVIEW", "PUBLISHED", "REJECTED", "ARCHIVED", "HIDDEN"}


def _normalize_filter(value: str | None) -> str:
    if value is None or value.strip() == "":
        return "ALL"
    normalized = value.strip().upper()
    return normalized if normalized in MY_SKILL_FILTERS else "ALL"


def _normalize_keyword(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    return value.strip().lower()


def _normalize_namespace(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    return value.strip()


def _has_filter_path(filter_value: str | None, keyword: str | None, namespace: str | None) -> bool:
    return (
        (filter_value is not None and filter_value.strip() != "")
        or _normalize_keyword(keyword) is not None
        or _normalize_namespace(namespace) is not None
    )


def _matches_keyword(row: dict[str, Any], keyword: str | None) -> bool:
    if keyword is None:
        return True
    return any(
        keyword in str(row.get(field) or "").lower()
        for field in ("display_name", "slug", "summary")
    )


def _matches_namespace(row: dict[str, Any], namespace: str | None) -> bool:
    return namespace is None or str(row.get("namespace")) == namespace


def _matches_filter(row: dict[str, Any], filter_value: str, platform_roles: set[str]) -> bool:
    if filter_value == "HIDDEN":
        return "SUPER_ADMIN" in platform_roles and bool(row.get("hidden"))
    if bool(row.get("hidden")):
        return False
    if filter_value == "ARCHIVED":
        return str(row.get("status")) == "ARCHIVED"
    if str(row.get("status")) == "ARCHIVED":
        return False

    owner_preview = to_lifecycle_version(
        row,
        id_key="owner_preview_version_id",
        version_key="owner_preview_version",
        status_key="owner_preview_version_status",
    )
    published = to_lifecycle_version(row)
    if filter_value == "PENDING_REVIEW":
        return owner_preview is not None and owner_preview["status"] == "PENDING_REVIEW"
    if filter_value == "PUBLISHED":
        return published is not None
    if filter_value == "REJECTED":
        return owner_preview is not None and owner_preview["status"] == "REJECTED"
    return True


def _summary(row: dict[str, Any]) -> dict[str, Any]:
    published = to_lifecycle_version(row)
    owner_preview = to_lifecycle_version(
        row,
        id_key="owner_preview_version_id",
        version_key="owner_preview_version",
        status_key="owner_preview_version_status",
    )
    headline = published if published is not None else owner_preview
    if headline is None:
        resolution_mode = "NONE"
    elif published is not None:
        resolution_mode = "PUBLISHED"
    else:
        resolution_mode = "OWNER_PREVIEW"
    can_submit_promotion = (
        str(row.get("namespace_type")) != "GLOBAL"
        and str(row.get("namespace_status")) == "ACTIVE"
        and str(row.get("status")) == "ACTIVE"
        and published is not None
        and not bool(row.get("promotion_blocked"))
    )
    return {
        "id": int(row["id"]),
        "slug": str(row["slug"]),
        "displayName": row["display_name"],
        "summary": row["summary"],
        "visibility": str(row["visibility"]),
        "status": str(row["status"]),
        "downloadCount": int(row["download_count"]),
        "starCount": int(row["star_count"]),
        "ratingAvg": float(row["rating_avg"]),
        "ratingCount": int(row["rating_count"]),
        "namespace": str(row["namespace"]),
        "updatedAt": to_java_instant(row["updated_at"]),
        "canSubmitPromotion": can_submit_promotion,
        "headlineVersion": headline,
        "publishedVersion": published,
        "ownerPreviewVersion": owner_preview,
        "resolutionMode": resolution_mode,
    }


async def list_my_owned_skills(
    engine: Any,
    *,
    user_id: str,
    platform_roles: set[str],
    page: int,
    size: int,
    filter_value: str | None,
    keyword: str | None,
    namespace: str | None,
) -> dict[str, Any]:
    normalized_filter = _normalize_filter(filter_value)
    normalized_keyword = _normalize_keyword(keyword)
    normalized_namespace = _normalize_namespace(namespace)
    filter_path = _has_filter_path(filter_value, keyword, namespace)

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT s.id,
                           s.slug,
                           s.display_name,
                           s.summary,
                           s.visibility,
                           s.status,
                           s.hidden,
                           s.download_count,
                           s.star_count,
                           s.rating_avg,
                           s.rating_count,
                           n.slug AS namespace,
                           n.type AS namespace_type,
                           n.status AS namespace_status,
                           s.updated_at,
                           pv.id AS published_version_id,
                           pv.version AS published_version,
                           pv.status AS published_version_status,
                           opv.id AS owner_preview_version_id,
                           opv.version AS owner_preview_version,
                           opv.status AS owner_preview_version_status,
                           EXISTS (
                               SELECT 1
                               FROM promotion_request pr
                               WHERE pr.source_skill_id = s.id
                                 AND pr.status IN ('PENDING', 'APPROVED')
                           ) AS promotion_blocked
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    LEFT JOIN LATERAL (
                        SELECT sv.id, sv.version, sv.status, sv.created_at, sv.published_at
                        FROM skill_version sv
                        WHERE sv.skill_id = s.id
                          AND sv.status = 'PUBLISHED'
                        ORDER BY
                          CASE WHEN sv.id = s.latest_version_id THEN 0 ELSE 1 END,
                          sv.published_at DESC NULLS LAST,
                          sv.created_at DESC NULLS LAST,
                          sv.id DESC
                        LIMIT 1
                    ) pv ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT sv.id, sv.version, sv.status
                        FROM skill_version sv
                        WHERE sv.skill_id = s.id
                          AND sv.status NOT IN ('PUBLISHED', 'YANKED')
                          AND (
                              pv.id IS NULL
                              OR (sv.created_at, sv.id) > (pv.created_at, pv.id)
                          )
                        ORDER BY sv.created_at DESC NULLS LAST, sv.id DESC
                        LIMIT 1
                    ) opv ON TRUE
                    WHERE s.owner_id = :user_id
                    ORDER BY s.updated_at DESC NULLS LAST, s.id DESC
                    """
                ),
                {"user_id": user_id},
            )
        ).mappings().all()

    filtered_rows = [dict(row) for row in rows]
    if filter_path:
        filtered_rows = [
            row
            for row in filtered_rows
            if _matches_namespace(row, normalized_namespace)
            and _matches_keyword(row, normalized_keyword)
            and _matches_filter(row, normalized_filter, platform_roles)
        ]

    start = min(page * size, len(filtered_rows))
    end = min(start + size, len(filtered_rows))
    page_rows = filtered_rows[start:end]
    return {
        "items": [_summary(row) for row in page_rows],
        "total": len(filtered_rows),
        "page": page,
        "size": size,
    }

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text


PROMOTION_STATUSES = {"PENDING", "APPROVED", "REJECTED"}
PLATFORM_PROMOTION_ROLES = {"SKILL_ADMIN", "SUPER_ADMIN"}


@dataclass(frozen=True)
class PromotionListQuery:
    status: str | None
    page: int
    size: int
    user_id: str
    sort_by: str | None = None
    sort_direction: str | None = None


class PromotionQueryError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _normalize_status(status: str | None) -> str:
    if status is None:
        return "PENDING"
    normalized = status.strip().upper()
    if normalized not in PROMOTION_STATUSES:
        raise PromotionQueryError("promotion.status.invalid")
    return normalized


def _history_sort_direction(sort_direction: str | None) -> str:
    if sort_direction is None:
        return "DESC"
    normalized = sort_direction.strip().upper()
    if normalized not in {"ASC", "DESC"}:
        raise PromotionQueryError("promotion.sort.direction.invalid")
    return normalized


def _order_clause_for_status(status: str, sort_by: str | None, sort_direction: str | None) -> str:
    if status == "PENDING":
        if sort_by is not None or sort_direction is not None:
            raise PromotionQueryError("promotion.sort.pending_unsupported")
        return "pr.submitted_at DESC, pr.id DESC"

    if sort_by is not None and (not sort_by.strip() or sort_by.strip() != "reviewedAt"):
        raise PromotionQueryError("promotion.sort.field.invalid")

    direction = _history_sort_direction(sort_direction)
    return (
        "CASE WHEN pr.reviewed_at IS NULL THEN 1 ELSE 0 END ASC, "
        f"pr.reviewed_at {direction}, pr.id {direction}"
    )


def _normalize_page(page: int) -> int:
    return max(page, 0)


def _normalize_size(size: int) -> int:
    return size if size > 0 else 20


def _java_instant(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        instant = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return instant.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return str(value).replace("+00:00", "Z")


def _promotion_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "sourceSkillId": int(row["source_skill_id"]),
        "sourceSkillDisplayName": row.get("source_skill_display_name"),
        "sourceSkillSummary": row.get("source_skill_summary"),
        "sourceNamespace": str(row["source_namespace"]),
        "sourceSkillSlug": str(row["skill_slug"]),
        "sourceVersion": str(row["version_name"]),
        "sourceVersionFileCount": int(row.get("source_version_file_count") or 0),
        "sourceVersionTotalSize": int(row.get("source_version_total_size") or 0),
        "sourceSkillDownloadCount": int(row.get("source_skill_download_count") or 0),
        "sourceSkillStarCount": int(row.get("source_skill_star_count") or 0),
        "targetNamespace": str(row["target_namespace"]),
        "targetSkillId": int(row["target_skill_id"]) if row.get("target_skill_id") is not None else None,
        "status": str(row["status"]),
        "submittedBy": str(row["submitted_by"]),
        "submittedByName": row.get("submitted_by_name"),
        "reviewedBy": row.get("reviewed_by"),
        "reviewedByName": row.get("reviewed_by_name"),
        "reviewComment": row.get("review_comment"),
        "submittedAt": _java_instant(row.get("submitted_at")),
        "reviewedAt": _java_instant(row.get("reviewed_at")),
    }


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


def _has_platform_promotion_role(platform_roles: set[str]) -> bool:
    return bool(platform_roles & PLATFORM_PROMOTION_ROLES)


async def _require_promotion_admin(connection: Any, user_id: str) -> set[str]:
    platform_roles = await _read_platform_roles(connection, user_id)
    if not _has_platform_promotion_role(platform_roles):
        raise PromotionQueryError("promotion.no_permission", status_code=403)
    return platform_roles


async def _count_promotions(connection: Any, *, status: str) -> int:
    return int(
        (
            await connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM promotion_request pr
                    WHERE pr.status = :status
                    """
                ),
                {"status": status},
            )
        ).scalar_one()
    )


async def _read_promotion_rows(
    connection: Any,
    *,
    status: str,
    page: int,
    size: int,
    order_clause: str,
) -> list[dict[str, Any]]:
    rows = (
        await connection.execute(
            text(
                f"""
                SELECT pr.id,
                       pr.source_skill_id,
                       source_skill.display_name AS source_skill_display_name,
                       source_skill.summary AS source_skill_summary,
                       source_ns.slug AS source_namespace,
                       source_skill.slug AS skill_slug,
                       source_version.version AS version_name,
                       source_version.file_count AS source_version_file_count,
                       source_version.total_size AS source_version_total_size,
                       source_skill.download_count AS source_skill_download_count,
                       source_skill.star_count AS source_skill_star_count,
                       target_ns.slug AS target_namespace,
                       pr.target_skill_id,
                       pr.status,
                       pr.submitted_by,
                       submitter.display_name AS submitted_by_name,
                       pr.reviewed_by,
                       reviewer.display_name AS reviewed_by_name,
                       pr.review_comment,
                       pr.submitted_at,
                       pr.reviewed_at
                FROM promotion_request pr
                JOIN skill source_skill ON source_skill.id = pr.source_skill_id
                JOIN skill_version source_version ON source_version.id = pr.source_version_id
                JOIN namespace source_ns ON source_ns.id = source_skill.namespace_id
                JOIN namespace target_ns ON target_ns.id = pr.target_namespace_id
                LEFT JOIN user_account submitter ON submitter.id = pr.submitted_by
                LEFT JOIN user_account reviewer ON reviewer.id = pr.reviewed_by
                WHERE pr.status = :status
                ORDER BY {order_clause}
                LIMIT :limit OFFSET :offset
                """
            ),
            {"status": status, "limit": size, "offset": page * size},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def _read_promotion_row(connection: Any, promotion_id: int) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT pr.id,
                       pr.source_skill_id,
                       source_skill.display_name AS source_skill_display_name,
                       source_skill.summary AS source_skill_summary,
                       source_ns.slug AS source_namespace,
                       source_skill.slug AS skill_slug,
                       source_version.version AS version_name,
                       source_version.file_count AS source_version_file_count,
                       source_version.total_size AS source_version_total_size,
                       source_skill.download_count AS source_skill_download_count,
                       source_skill.star_count AS source_skill_star_count,
                       target_ns.slug AS target_namespace,
                       pr.target_skill_id,
                       pr.status,
                       pr.submitted_by,
                       submitter.display_name AS submitted_by_name,
                       pr.reviewed_by,
                       reviewer.display_name AS reviewed_by_name,
                       pr.review_comment,
                       pr.submitted_at,
                       pr.reviewed_at
                FROM promotion_request pr
                JOIN skill source_skill ON source_skill.id = pr.source_skill_id
                JOIN skill_version source_version ON source_version.id = pr.source_version_id
                JOIN namespace source_ns ON source_ns.id = source_skill.namespace_id
                JOIN namespace target_ns ON target_ns.id = pr.target_namespace_id
                LEFT JOIN user_account submitter ON submitter.id = pr.submitted_by
                LEFT JOIN user_account reviewer ON reviewer.id = pr.reviewed_by
                WHERE pr.id = :promotion_id
                """
            ),
            {"promotion_id": promotion_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise PromotionQueryError("promotion.not_found", status_code=404)
    return dict(row)


async def _build_page_response(connection: Any, *, status: str, page: int, size: int, order_clause: str) -> dict[str, Any]:
    total = await _count_promotions(connection, status=status)
    rows = await _read_promotion_rows(connection, status=status, page=page, size=size, order_clause=order_clause)
    return {
        "items": [_promotion_response(row) for row in rows],
        "total": total,
        "page": page,
        "size": size,
    }


async def list_promotions(engine: Any, query: PromotionListQuery) -> dict[str, Any]:
    status = _normalize_status(query.status)
    page = _normalize_page(query.page)
    size = _normalize_size(query.size)
    order_clause = _order_clause_for_status(status, query.sort_by, query.sort_direction)
    async with engine.connect() as connection:
        await _require_promotion_admin(connection, query.user_id)
        return await _build_page_response(connection, status=status, page=page, size=size, order_clause=order_clause)


async def list_pending_promotions(engine: Any, *, page: int, size: int, user_id: str) -> dict[str, Any]:
    page = _normalize_page(page)
    size = _normalize_size(size)
    async with engine.connect() as connection:
        await _require_promotion_admin(connection, user_id)
        return await _build_page_response(
            connection,
            status="PENDING",
            page=page,
            size=size,
            order_clause=_order_clause_for_status("PENDING", None, None),
        )


async def read_promotion_detail(engine: Any, *, promotion_id: int, user_id: str) -> dict[str, Any]:
    async with engine.connect() as connection:
        row = await _read_promotion_row(connection, promotion_id)
        platform_roles = await _read_platform_roles(connection, user_id)
        if str(row["submitted_by"]) != user_id and not _has_platform_promotion_role(platform_roles):
            raise PromotionQueryError("promotion.no_permission", status_code=403)
        return _promotion_response(row)

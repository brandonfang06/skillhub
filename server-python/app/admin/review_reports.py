from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from app.api.skills import to_java_instant


SKILL_REPORT_READ_ROLES = {"SKILL_ADMIN", "SUPER_ADMIN"}
PROFILE_REVIEW_READ_ROLES = {"USER_ADMIN", "SUPER_ADMIN"}
SKILL_REPORT_STATUSES = {"PENDING", "RESOLVED", "DISMISSED"}
PROFILE_REVIEW_STATUSES = {"PENDING", "MACHINE_REJECTED", "APPROVED", "REJECTED", "CANCELLED"}


class AdminReviewReportError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def require_skill_report_reader(platform_roles: list[str]) -> None:
    if {str(role) for role in platform_roles}.isdisjoint(SKILL_REPORT_READ_ROLES):
        raise AdminReviewReportError("error.admin.skillReport.readDenied", status_code=403)


def require_profile_review_reader(platform_roles: list[str]) -> None:
    if {str(role) for role in platform_roles}.isdisjoint(PROFILE_REVIEW_READ_ROLES):
        raise AdminReviewReportError("error.profileReview.readDenied", status_code=403)


def _normalize_status(status: str | None, allowed: set[str], default: str, error_key: str) -> str:
    if status is None or status.strip() == "":
        return default
    normalized = status.strip().upper()
    if normalized not in allowed:
        raise AdminReviewReportError(error_key, status_code=400)
    return normalized


def _page_number(page: int) -> int:
    return max(0, int(page))


def _page_size(size: int) -> int:
    return max(1, int(size))


def _json_map(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _skill_report_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "skillId": int(row["skill_id"]),
        "namespace": row.get("namespace"),
        "skillSlug": row.get("skill_slug"),
        "skillDisplayName": row.get("skill_display_name"),
        "reporterId": row.get("reporter_id"),
        "reason": row.get("reason"),
        "details": row.get("details"),
        "status": row.get("status"),
        "handledBy": row.get("handled_by"),
        "handleComment": row.get("handle_comment"),
        "createdAt": to_java_instant(row.get("created_at")),
        "handledAt": to_java_instant(row.get("handled_at")) if row.get("handled_at") is not None else None,
    }


def _profile_review_item(row: dict[str, Any]) -> dict[str, Any]:
    changes = _json_map(row.get("changes"))
    old_values = _json_map(row.get("old_values"))
    submitter_name = row.get("submitter_name")
    return {
        "id": int(row["id"]),
        "userId": row.get("user_id"),
        "username": submitter_name if submitter_name is not None else row.get("user_id"),
        "currentDisplayName": old_values.get("displayName", submitter_name),
        "requestedDisplayName": changes.get("displayName"),
        "status": row.get("status"),
        "machineResult": row.get("machine_result"),
        "reviewerId": row.get("reviewer_id"),
        "reviewerName": row.get("reviewer_name"),
        "reviewComment": row.get("review_comment"),
        "createdAt": to_java_instant(row.get("created_at")),
        "reviewedAt": to_java_instant(row.get("reviewed_at")) if row.get("reviewed_at") is not None else None,
    }


async def list_admin_skill_reports(
    engine: Any,
    *,
    status: str | None,
    page: int,
    size: int,
    platform_roles: list[str],
) -> dict[str, Any]:
    require_skill_report_reader(platform_roles)
    normalized_status = _normalize_status(status, SKILL_REPORT_STATUSES, "PENDING", "error.skill.report.status.invalid")
    normalized_page = _page_number(page)
    normalized_size = _page_size(size)
    params = {
        "status": normalized_status,
        "limit": normalized_size,
        "offset": normalized_page * normalized_size,
    }
    async with engine.connect() as connection:
        total = int(
            (
                await connection.execute(
                    text("SELECT COUNT(*) FROM skill_report sr WHERE sr.status = :status"),
                    params,
                )
            ).scalar_one()
        )
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT sr.id,
                           sr.skill_id,
                           n.slug AS namespace,
                           s.slug AS skill_slug,
                           s.display_name AS skill_display_name,
                           sr.reporter_id,
                           sr.reason,
                           sr.details,
                           sr.status,
                           sr.handled_by,
                           sr.handle_comment,
                           sr.created_at,
                           sr.handled_at
                    FROM skill_report sr
                    LEFT JOIN skill s ON s.id = sr.skill_id
                    LEFT JOIN namespace n ON n.id = s.namespace_id
                    WHERE sr.status = :status
                    ORDER BY sr.created_at DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            )
        ).mappings().all()
    return {
        "items": [_skill_report_item(dict(row)) for row in rows],
        "total": total,
        "page": normalized_page,
        "size": normalized_size,
    }


async def list_admin_profile_reviews(
    engine: Any,
    *,
    status: str | None,
    page: int,
    size: int,
    sort_direction: str | None,
    platform_roles: list[str],
) -> dict[str, Any]:
    require_profile_review_reader(platform_roles)
    normalized_status = _normalize_status(status, PROFILE_REVIEW_STATUSES, "PENDING", "error.profileReview.status.invalid")
    normalized_page = _page_number(page)
    normalized_size = _page_size(size)
    sort_desc = str(sort_direction or "DESC").strip().upper() != "ASC"
    sort_column = "created_at" if normalized_status == "PENDING" else "reviewed_at"
    sort_order = "DESC" if sort_desc else "ASC"
    params = {
        "status": normalized_status,
        "limit": normalized_size,
        "offset": normalized_page * normalized_size,
        "sort_desc": sort_desc,
    }
    async with engine.connect() as connection:
        total = int(
            (
                await connection.execute(
                    text("SELECT COUNT(*) FROM profile_change_request pcr WHERE pcr.status = :status"),
                    params,
                )
            ).scalar_one()
        )
        rows = (
            await connection.execute(
                text(
                    f"""
                    SELECT pcr.id,
                           pcr.user_id,
                           submitter.display_name AS submitter_name,
                           pcr.changes,
                           pcr.old_values,
                           pcr.status,
                           pcr.machine_result,
                           pcr.reviewer_id,
                           reviewer.display_name AS reviewer_name,
                           pcr.review_comment,
                           pcr.created_at,
                           pcr.reviewed_at
                    FROM profile_change_request pcr
                    LEFT JOIN user_account submitter ON submitter.id = pcr.user_id
                    LEFT JOIN user_account reviewer ON reviewer.id = pcr.reviewer_id
                    WHERE pcr.status = :status
                    ORDER BY pcr.{sort_column} {sort_order}, pcr.id {sort_order}
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            )
        ).mappings().all()
    return {
        "items": [_profile_review_item(dict(row)) for row in rows],
        "total": total,
        "page": normalized_page,
        "size": normalized_size,
    }

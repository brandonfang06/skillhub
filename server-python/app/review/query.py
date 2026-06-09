from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text


PLATFORM_REVIEW_ROLES = {"SKILL_ADMIN", "SUPER_ADMIN"}
NAMESPACE_REVIEW_ROLES = {"OWNER", "ADMIN"}
REVIEW_STATUSES = {"PENDING", "APPROVED", "REJECTED"}


@dataclass(frozen=True)
class ReviewListQuery:
    status: str
    namespace_id: int | None
    page: int
    size: int
    sort_direction: str
    user_id: str


class ReviewQueryError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _normalize_status(status: str) -> str:
    normalized = status.strip().upper()
    if normalized not in REVIEW_STATUSES:
        raise ReviewQueryError("review.status.invalid")
    return normalized


def _normalize_page(page: int) -> int:
    return max(page, 0)


def _normalize_size(size: int) -> int:
    return size if size > 0 else 20


def _normalize_sort_direction(sort_direction: str) -> str:
    return "ASC" if sort_direction.strip().upper() == "ASC" else "DESC"


def _java_instant(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        instant = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return instant.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return str(value).replace("+00:00", "Z")


def _task_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "skillVersionId": int(row["skill_version_id"]),
        "namespace": str(row["namespace_slug"]),
        "skillSlug": str(row["skill_slug"]),
        "version": str(row["version_name"]),
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


async def _read_namespace_roles(connection: Any, user_id: str) -> dict[int, str]:
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
    return {int(row["namespace_id"]): str(row["role"]) for row in rows}


async def _read_namespace(connection: Any, namespace_id: int) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT id, type, status
                FROM namespace
                WHERE id = :namespace_id
                """
            ),
            {"namespace_id": namespace_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise ReviewQueryError("namespace.not_found", status_code=404)
    return dict(row)


def _has_platform_review_role(platform_roles: set[str]) -> bool:
    return bool(platform_roles & PLATFORM_REVIEW_ROLES)


def _can_review_namespace(
    namespace_id: int,
    namespace_type: str,
    namespace_roles: dict[int, str],
    platform_roles: set[str],
) -> bool:
    if _has_platform_review_role(platform_roles):
        return True
    if namespace_type == "GLOBAL":
        return False
    return namespace_roles.get(namespace_id) in NAMESPACE_REVIEW_ROLES


def _can_view_review(row: dict[str, Any], user_id: str, namespace_roles: dict[int, str], platform_roles: set[str]) -> bool:
    if str(row["submitted_by"]) == user_id:
        return True
    return _can_review_namespace(int(row["namespace_id"]), str(row["namespace_type"]), namespace_roles, platform_roles)


def _order_clause(status: str, sort_direction: str) -> str:
    primary = "submitted_at" if status == "PENDING" else "reviewed_at"
    return f"ORDER BY rt.{primary} {sort_direction}, rt.id {sort_direction}"


async def _count_review_tasks(
    connection: Any,
    *,
    status: str,
    namespace_id: int | None,
    submitted_by: str | None,
) -> int:
    if submitted_by is not None:
        return int(
            (
                await connection.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM review_task rt
                        WHERE rt.status = :status
                          AND rt.submitted_by = :submitted_by
                        """
                    ),
                    {"status": status, "submitted_by": submitted_by},
                )
            ).scalar_one()
        )
    if namespace_id is not None:
        return int(
            (
                await connection.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM review_task rt
                        WHERE rt.status = :status
                          AND rt.namespace_id = :namespace_id
                        """
                    ),
                    {"status": status, "namespace_id": namespace_id},
                )
            ).scalar_one()
        )
    return int(
        (
            await connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM review_task rt
                    WHERE rt.status = :status
                    """
                ),
                {"status": status},
            )
        ).scalar_one()
    )


async def _read_review_task_rows(
    connection: Any,
    *,
    status: str,
    namespace_id: int | None,
    submitted_by: str | None,
    page: int,
    size: int,
    sort_direction: str,
) -> list[dict[str, Any]]:
    filters = ["rt.status = :status"]
    params: dict[str, Any] = {
        "status": status,
        "limit": size,
        "offset": page * size,
    }
    if namespace_id is not None:
        filters.append("rt.namespace_id = :namespace_id")
        params["namespace_id"] = namespace_id
    if submitted_by is not None:
        filters.append("rt.submitted_by = :submitted_by")
        params["submitted_by"] = submitted_by

    where_clause = " AND ".join(filters)
    order_clause = _order_clause(status, sort_direction)
    rows = (
        await connection.execute(
            text(
                f"""
                SELECT rt.id,
                       rt.skill_version_id,
                       rt.namespace_id,
                       rt.status,
                       rt.submitted_by,
                       submitter.display_name AS submitted_by_name,
                       rt.reviewed_by,
                       reviewer.display_name AS reviewed_by_name,
                       rt.review_comment,
                       rt.submitted_at,
                       rt.reviewed_at,
                       n.slug AS namespace_slug,
                       n.type AS namespace_type,
                       s.slug AS skill_slug,
                       sv.version AS version_name
                FROM review_task rt
                JOIN namespace n ON n.id = rt.namespace_id
                JOIN skill_version sv ON sv.id = rt.skill_version_id
                JOIN skill s ON s.id = sv.skill_id
                LEFT JOIN user_account submitter ON submitter.id = rt.submitted_by
                LEFT JOIN user_account reviewer ON reviewer.id = rt.reviewed_by
                WHERE {where_clause}
                {order_clause}
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def _read_review_task_row(connection: Any, review_task_id: int) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT rt.id,
                       rt.skill_version_id,
                       rt.namespace_id,
                       rt.status,
                       rt.submitted_by,
                       submitter.display_name AS submitted_by_name,
                       rt.reviewed_by,
                       reviewer.display_name AS reviewed_by_name,
                       rt.review_comment,
                       rt.submitted_at,
                       rt.reviewed_at,
                       n.slug AS namespace_slug,
                       n.type AS namespace_type,
                       s.slug AS skill_slug,
                       sv.version AS version_name
                FROM review_task rt
                JOIN namespace n ON n.id = rt.namespace_id
                JOIN skill_version sv ON sv.id = rt.skill_version_id
                JOIN skill s ON s.id = sv.skill_id
                LEFT JOIN user_account submitter ON submitter.id = rt.submitted_by
                LEFT JOIN user_account reviewer ON reviewer.id = rt.reviewed_by
                WHERE rt.id = :review_task_id
                """
            ),
            {"review_task_id": review_task_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise ReviewQueryError("review_task.not_found", status_code=404)
    return dict(row)


async def _build_page_response(
    connection: Any,
    *,
    status: str,
    namespace_id: int | None,
    submitted_by: str | None,
    page: int,
    size: int,
    sort_direction: str,
) -> dict[str, Any]:
    total = await _count_review_tasks(connection, status=status, namespace_id=namespace_id, submitted_by=submitted_by)
    rows = await _read_review_task_rows(
        connection,
        status=status,
        namespace_id=namespace_id,
        submitted_by=submitted_by,
        page=page,
        size=size,
        sort_direction=sort_direction,
    )
    return {
        "items": [_task_response(row) for row in rows],
        "total": total,
        "page": page,
        "size": size,
    }


async def list_review_tasks(engine: Any, query: ReviewListQuery) -> dict[str, Any]:
    status = _normalize_status(query.status)
    page = _normalize_page(query.page)
    size = _normalize_size(query.size)
    sort_direction = _normalize_sort_direction(query.sort_direction)
    async with engine.connect() as connection:
        platform_roles = await _read_platform_roles(connection, query.user_id)
        namespace_roles = await _read_namespace_roles(connection, query.user_id)
        if query.namespace_id is None:
            if not _has_platform_review_role(platform_roles):
                raise ReviewQueryError("review.no_permission", status_code=403)
        else:
            namespace = await _read_namespace(connection, int(query.namespace_id))
            if not _can_review_namespace(int(query.namespace_id), str(namespace["type"]), namespace_roles, platform_roles):
                raise ReviewQueryError("review.no_permission", status_code=403)

        return await _build_page_response(
            connection,
            status=status,
            namespace_id=query.namespace_id,
            submitted_by=None,
            page=page,
            size=size,
            sort_direction=sort_direction,
        )


async def list_pending_reviews(engine: Any, *, namespace_id: int, page: int, size: int, user_id: str) -> dict[str, Any]:
    page = _normalize_page(page)
    size = _normalize_size(size)
    async with engine.connect() as connection:
        platform_roles = await _read_platform_roles(connection, user_id)
        namespace_roles = await _read_namespace_roles(connection, user_id)
        namespace = await _read_namespace(connection, int(namespace_id))
        if not _can_review_namespace(int(namespace_id), str(namespace["type"]), namespace_roles, platform_roles):
            raise ReviewQueryError("review.no_permission", status_code=403)
        return await _build_page_response(
            connection,
            status="PENDING",
            namespace_id=int(namespace_id),
            submitted_by=None,
            page=page,
            size=size,
            sort_direction="DESC",
        )


async def list_my_review_submissions(engine: Any, *, page: int, size: int, user_id: str) -> dict[str, Any]:
    page = _normalize_page(page)
    size = _normalize_size(size)
    async with engine.connect() as connection:
        return await _build_page_response(
            connection,
            status="PENDING",
            namespace_id=None,
            submitted_by=user_id,
            page=page,
            size=size,
            sort_direction="DESC",
        )


async def read_review_detail(engine: Any, *, review_task_id: int, user_id: str) -> dict[str, Any]:
    async with engine.connect() as connection:
        row = await _read_review_task_row(connection, review_task_id)
        platform_roles = await _read_platform_roles(connection, user_id)
        namespace_roles = await _read_namespace_roles(connection, user_id)
        if not _can_view_review(row, user_id, namespace_roles, platform_roles):
            raise ReviewQueryError("review.no_permission", status_code=403)
        return _task_response(row)

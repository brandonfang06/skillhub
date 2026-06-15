from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
import mimetypes
from typing import Any
from zipfile import ZipFile

from sqlalchemy import text

from app.auth.policy import NAMESPACE_MANAGER_ROLES, namespace_role_allows
from app.object_storage import ObjectNotFoundError, object_storage_for_base_path


PLATFORM_REVIEW_ROLES = {"SKILL_ADMIN", "SUPER_ADMIN"}
NAMESPACE_REVIEW_ROLES = NAMESPACE_MANAGER_ROLES
REVIEW_STATUSES = {"PENDING", "APPROVED", "REJECTED"}
REVIEW_VERSION_STATUSES = (
    "PUBLISHED",
    "PENDING_REVIEW",
    "UPLOADED",
    "DRAFT",
    "REJECTED",
    "YANKED",
    "SCANNING",
    "SCAN_FAILED",
)


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


@dataclass(frozen=True)
class ReviewDownloadResult:
    content: bytes
    content_type: str
    filename: str
    content_length: int | None = None

    def __post_init__(self) -> None:
        if self.content_length is None:
            object.__setattr__(self, "content_length", len(self.content))

    def as_bytes_io(self) -> BytesIO:
        return BytesIO(self.content)


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
        "versionStatus": str(row["version_status"]),
        "status": str(row["status"]),
        "submittedBy": str(row["submitted_by"]),
        "submittedByName": row.get("submitted_by_name"),
        "reviewedBy": row.get("reviewed_by"),
        "reviewedByName": row.get("reviewed_by_name"),
        "reviewComment": row.get("review_comment"),
        "submittedAt": _java_instant(row.get("submitted_at")),
        "reviewedAt": _java_instant(row.get("reviewed_at")),
    }


def _lifecycle_version(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "version": str(row["version"]),
        "status": str(row["status"]),
    }


def _review_skill_lifecycle_version(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["active_version_id"]),
        "version": str(row["active_version"]),
        "status": str(row["active_version_status"]),
    }


def _file_exists(storage_base_path: str, storage_key: str) -> bool:
    try:
        return object_storage_for_base_path(storage_base_path).exists(storage_key)
    except ValueError:
        return False


def _read_storage_text(storage_base_path: str, storage_key: str) -> str:
    return _read_storage_bytes(storage_base_path, storage_key).decode("utf-8")


def _read_storage_bytes(storage_base_path: str, storage_key: str) -> bytes:
    try:
        return object_storage_for_base_path(storage_base_path).read_bytes(storage_key)
    except (FileNotFoundError, ObjectNotFoundError, ValueError) as exc:
        raise ReviewQueryError("error.skill.file.notFound", status_code=400) from exc


def _read_bundle_storage_bytes(storage_base_path: str, storage_key: str) -> bytes:
    try:
        return _read_storage_bytes(storage_base_path, storage_key)
    except ReviewQueryError as exc:
        raise ReviewQueryError("error.skill.bundle.notFound", status_code=400) from exc


def _sanitize_download_filename(value: str) -> str:
    import re

    sanitized = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "-", value)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized if sanitized != "" else "skill"


def _build_download_filename(display_name: str | None, slug: str, version: str) -> str:
    base_name = display_name if display_name is not None and display_name.strip() != "" else slug
    return f"{_sanitize_download_filename(base_name)}-{version}.zip"


def _bundle_storage_key(skill_id: int, version_id: int) -> str:
    return f"packages/{skill_id}/{version_id}/bundle.zip"


def _probe_bundle_content_type(storage_key: str) -> str:
    return mimetypes.guess_type(storage_key)[0] or "application/zip"


def _build_review_download_result(
    storage_base_path: str,
    version_row: dict[str, Any],
    file_rows: list[dict[str, Any]],
) -> ReviewDownloadResult:
    skill_id = int(version_row["skill_id"])
    version_id = int(version_row["version_id"])
    filename = _build_download_filename(
        version_row.get("display_name"),
        str(version_row["slug"]),
        str(version_row["version"]),
    )
    bundle_key = _bundle_storage_key(skill_id, version_id)
    if _file_exists(storage_base_path, bundle_key):
        content = _read_bundle_storage_bytes(storage_base_path, bundle_key)
        return ReviewDownloadResult(
            content=content,
            content_type=_probe_bundle_content_type(bundle_key),
            filename=filename,
            content_length=len(content),
        )

    available_files: list[tuple[str, bytes]] = []
    for file_row in sorted(file_rows, key=lambda row: str(row["file_path"])):
        storage_key = file_row.get("storage_key")
        if storage_key is None:
            continue
        try:
            content = _read_storage_bytes(storage_base_path, str(storage_key))
        except ReviewQueryError:
            continue
        available_files.append((str(file_row["file_path"]), content))

    if not available_files:
        raise ReviewQueryError("error.skill.bundle.notFound", status_code=400)

    buffer = BytesIO()
    with ZipFile(buffer, "w") as zip_file:
        for file_path, content in available_files:
            zip_file.writestr(file_path, content)
    content = buffer.getvalue()
    return ReviewDownloadResult(
        content=content,
        content_type="application/zip",
        filename=filename,
        content_length=len(content),
    )


def _resolve_documentation_file(files: list[dict[str, Any]]) -> dict[str, Any] | None:
    by_path = {str(file["file_path"]): file for file in files}
    return by_path.get("README.md") or by_path.get("SKILL.md")


def _review_skill_file_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "filePath": str(row["file_path"]),
        "fileSize": int(row["file_size"]),
        "contentType": row["content_type"],
        "sha256": row["sha256"],
    }


def _review_skill_version_response(row: dict[str, Any], active_version_id: int) -> dict[str, Any]:
    status = str(row["status"])
    return {
        "id": int(row["id"]),
        "version": str(row["version"]),
        "status": status,
        "changelog": row["changelog"],
        "fileCount": int(row["file_count"]),
        "totalSize": int(row["total_size"]),
        "publishedAt": _java_instant(row.get("published_at")),
        "downloadAvailable": int(row["id"]) == active_version_id or (status == "PUBLISHED" and bool(row["download_ready"])),
    }


def _review_skill_detail_response(
    *,
    review_task_id: int,
    snapshot: dict[str, Any],
    versions: list[dict[str, Any]],
    files: list[dict[str, Any]],
    documentation_file: dict[str, Any] | None,
    documentation_content: str | None,
) -> dict[str, Any]:
    active_version = _review_skill_lifecycle_version(snapshot)
    published_version = next((version for version in versions if str(version["status"]) == "PUBLISHED"), None)
    published_lifecycle = _lifecycle_version(published_version) if published_version is not None else None
    return {
        "skill": {
            "id": int(snapshot["id"]),
            "slug": str(snapshot["slug"]),
            "displayName": snapshot["display_name"],
            "ownerId": str(snapshot["owner_id"]),
            "ownerDisplayName": snapshot["owner_display_name"],
            "summary": snapshot["summary"],
            "visibility": str(snapshot["visibility"]),
            "status": str(snapshot["status"]),
            "downloadCount": int(snapshot["download_count"]),
            "starCount": int(snapshot["star_count"]),
            "subscriptionCount": int(snapshot["subscription_count"]),
            "ratingAvg": float(snapshot["rating_avg"]),
            "ratingCount": int(snapshot["rating_count"]),
            "hidden": bool(snapshot["hidden"]),
            "namespace": str(snapshot["namespace"]),
            "labels": [],
            "canManageLifecycle": False,
            "canSubmitPromotion": False,
            "canInteract": False,
            "canReport": False,
            "headlineVersion": active_version,
            "publishedVersion": published_lifecycle,
            "ownerPreviewVersion": active_version,
            "ownerPreviewReviewComment": None,
            "resolutionMode": "REVIEW_TASK",
        },
        "versions": [_review_skill_version_response(version, int(snapshot["active_version_id"])) for version in versions],
        "files": [_review_skill_file_response(file) for file in files],
        "documentationPath": str(documentation_file["file_path"]) if documentation_file is not None else None,
        "documentationContent": documentation_content,
        "downloadUrl": f"/api/v1/reviews/{review_task_id}/download",
        "activeVersion": str(snapshot["active_version"]),
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
    return namespace_role_allows(namespace_roles.get(namespace_id), NAMESPACE_REVIEW_ROLES)


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
                       sv.version AS version_name,
                       sv.status AS version_status
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
                       sv.version AS version_name,
                       sv.status AS version_status
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


async def _read_review_skill_snapshot(connection: Any, skill_version_id: int) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT s.id,
                       s.slug,
                       s.display_name,
                       s.owner_id,
                       NULLIF(owner.display_name, '') AS owner_display_name,
                       s.summary,
                       s.visibility,
                       s.status,
                       s.download_count,
                       s.star_count,
                       s.subscription_count,
                       s.rating_avg,
                       s.rating_count,
                       s.hidden,
                       n.slug AS namespace,
                       active.id AS active_version_id,
                       active.version AS active_version,
                       active.status AS active_version_status
                FROM skill_version active
                JOIN skill s ON s.id = active.skill_id
                JOIN namespace n ON n.id = s.namespace_id
                LEFT JOIN user_account owner ON owner.id = s.owner_id
                WHERE active.id = :skill_version_id
                """
            ),
            {"skill_version_id": skill_version_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise ReviewQueryError("error.skill.version.notFound", status_code=400)
    return dict(row)


async def _read_review_download_version_row(connection: Any, skill_version_id: int) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT s.id AS skill_id,
                       active.id AS version_id,
                       s.slug,
                       s.display_name,
                       active.version
                FROM skill_version active
                JOIN skill s ON s.id = active.skill_id
                WHERE active.id = :skill_version_id
                """
            ),
            {"skill_version_id": skill_version_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise ReviewQueryError("error.skill.version.notFound", status_code=400)
    return dict(row)


async def _read_review_skill_versions(connection: Any, skill_id: int) -> list[dict[str, Any]]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT sv.id,
                       sv.version,
                       sv.status,
                       sv.changelog,
                       sv.file_count,
                       sv.total_size,
                       sv.published_at,
                       sv.download_ready,
                       sv.created_at
                FROM skill_version sv
                WHERE sv.skill_id = :skill_id
                  AND sv.status = ANY(:statuses)
                ORDER BY CASE sv.status
                             WHEN 'PUBLISHED' THEN 0
                             WHEN 'SCANNING' THEN 1
                             WHEN 'SCAN_FAILED' THEN 1
                             WHEN 'UPLOADED' THEN 2
                             WHEN 'REJECTED' THEN 3
                             WHEN 'PENDING_REVIEW' THEN 4
                             WHEN 'DRAFT' THEN 5
                             WHEN 'YANKED' THEN 5
                             ELSE 3
                         END,
                         sv.published_at DESC NULLS LAST,
                         sv.created_at DESC NULLS LAST,
                         sv.id DESC
                """
            ),
            {"skill_id": skill_id, "statuses": list(REVIEW_VERSION_STATUSES)},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def _read_review_skill_files(connection: Any, version_id: int, storage_base_path: str) -> list[dict[str, Any]]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT id, file_path, file_size, content_type, sha256, storage_key
                FROM skill_file
                WHERE version_id = :version_id
                ORDER BY id ASC
                """
            ),
            {"version_id": version_id},
        )
    ).mappings().all()
    return [
        dict(row)
        for row in rows
        if row.get("storage_key") is not None and _file_exists(storage_base_path, str(row["storage_key"]))
    ]


async def _read_review_download_file_rows(connection: Any, version_id: int) -> list[dict[str, Any]]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT file_path, storage_key
                FROM skill_file
                WHERE version_id = :version_id
                ORDER BY file_path ASC
                """
            ),
            {"version_id": version_id},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


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


async def read_review_skill_detail(
    engine: Any,
    storage_base_path: str,
    *,
    review_task_id: int,
    user_id: str,
) -> dict[str, Any]:
    async with engine.connect() as connection:
        task = await _read_review_task_row(connection, review_task_id)
        platform_roles = await _read_platform_roles(connection, user_id)
        namespace_roles = await _read_namespace_roles(connection, user_id)
        if not _can_view_review(task, user_id, namespace_roles, platform_roles):
            raise ReviewQueryError("review.no_permission", status_code=403)

        snapshot = await _read_review_skill_snapshot(connection, int(task["skill_version_id"]))
        versions = await _read_review_skill_versions(connection, int(snapshot["id"]))
        files = await _read_review_skill_files(connection, int(snapshot["active_version_id"]), storage_base_path)
        documentation_file = _resolve_documentation_file(files)
        documentation_content = (
            _read_storage_text(storage_base_path, str(documentation_file["storage_key"]))
            if documentation_file is not None
            else None
        )
        return _review_skill_detail_response(
            review_task_id=review_task_id,
            snapshot=snapshot,
            versions=versions,
            files=files,
            documentation_file=documentation_file,
            documentation_content=documentation_content,
        )


async def read_review_file_content(
    engine: Any,
    storage_base_path: str,
    *,
    review_task_id: int,
    file_path: str,
    user_id: str,
) -> bytes:
    async with engine.connect() as connection:
        task = await _read_review_task_row(connection, review_task_id)
        platform_roles = await _read_platform_roles(connection, user_id)
        namespace_roles = await _read_namespace_roles(connection, user_id)
        if not _can_view_review(task, user_id, namespace_roles, platform_roles):
            raise ReviewQueryError("review.no_permission", status_code=403)

        files = await _read_review_skill_files(connection, int(task["skill_version_id"]), storage_base_path)
        file_row = next((file for file in files if str(file["file_path"]) == file_path), None)
        if file_row is None:
            raise ReviewQueryError("error.skill.file.notFound", status_code=400)
        return _read_storage_bytes(storage_base_path, str(file_row["storage_key"]))


async def read_review_download_package(
    engine: Any,
    storage_base_path: str,
    *,
    review_task_id: int,
    user_id: str,
) -> ReviewDownloadResult:
    async with engine.connect() as connection:
        task = await _read_review_task_row(connection, review_task_id)
        platform_roles = await _read_platform_roles(connection, user_id)
        namespace_roles = await _read_namespace_roles(connection, user_id)
        if not _can_view_review(task, user_id, namespace_roles, platform_roles):
            raise ReviewQueryError("review.no_permission", status_code=403)

        version_row = await _read_review_download_version_row(connection, int(task["skill_version_id"]))
        file_rows = await _read_review_download_file_rows(connection, int(version_row["version_id"]))
        return _build_review_download_result(storage_base_path, version_row, file_rows)

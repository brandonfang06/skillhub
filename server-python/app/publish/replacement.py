from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.object_storage import object_storage_for_base_path
from sqlalchemy import text


class VersionReplacementConflict(ValueError):
    pass


@dataclass(frozen=True)
class ReplaceableVersion:
    skill_id: int
    namespace: str
    slug: str
    version_id: int
    version: str
    status: str
    publisher_id: str
    latest_version_id: int | None = None
    now: datetime | None = None


@dataclass(frozen=True)
class ArchivedReviewAttempt:
    original_review_task_id: int
    original_skill_version_id: int
    skill_id: int
    namespace_id: int
    namespace_slug: str
    skill_slug: str
    version: str
    status: str
    submitted_by: str
    reviewed_by: str | None
    review_comment: str | None
    submitted_at: datetime
    reviewed_at: datetime | None
    parsed_metadata_json: Any
    manifest_json: Any
    files: list[dict[str, Any]]
    scanner_summary: list[dict[str, Any]]
    original_request_id: str | None


@dataclass(frozen=True)
class ReplacementCleanupResult:
    storage_keys: list[str]
    archived_review: ArchivedReviewAttempt | None = None


@dataclass(frozen=True)
class StorageDeleteCompensationInput:
    skill_id: int
    namespace: str
    slug: str
    storage_keys: list[str]
    last_error: str | None
    now: datetime | None = None


@dataclass(frozen=True)
class StorageDeleteResult:
    deleted_keys: list[str]
    compensation_recorded: bool


def bundle_storage_key(skill_id: int, version_id: int) -> str:
    return f"packages/{skill_id}/{version_id}/bundle.zip"


REPLACEABLE_VERSION_STATUSES = {"DRAFT", "SCAN_FAILED", "UPLOADED", "REJECTED"}


def _assert_replaceable_status(status: str, version: str) -> None:
    if status == "PUBLISHED":
        raise VersionReplacementConflict(f"Version already published: {version}")
    if status not in REPLACEABLE_VERSION_STATUSES:
        raise VersionReplacementConflict(f"Version cannot be replaced from status {status}")


def _assert_locked_replacement(row: dict[str, Any], version: ReplaceableVersion) -> None:
    if int(row["skill_id"]) != version.skill_id or str(row["owner_id"]) != version.publisher_id:
        raise VersionReplacementConflict("Replacement owner changed")
    if (
        str(row["namespace_slug"]) != version.namespace
        or str(row["slug"]) != version.slug
        or str(row["version"]) != version.version
    ):
        raise VersionReplacementConflict("Replacement coordinates changed")
    if str(row["skill_status"]) != "ACTIVE":
        raise VersionReplacementConflict("Skill is not writable")
    if str(row["namespace_status"]) != "ACTIVE":
        raise VersionReplacementConflict("Namespace is not writable")
    if str(row["status"]) == "REJECTED" and bool(row["has_pending_review"]):
        raise VersionReplacementConflict("Skill already has a pending review")


async def _read_rejected_review_attempt(
    connection: Any,
    version: ReplaceableVersion,
) -> ArchivedReviewAttempt:
    review_row = (
        await connection.execute(
            text(
                """
                SELECT rt.id AS review_task_id,
                       rt.namespace_id,
                       rt.submitted_by,
                       rt.reviewed_by,
                       rt.review_comment,
                       rt.submitted_at,
                       rt.reviewed_at,
                       sv.parsed_metadata_json,
                       sv.manifest_json,
                       (
                           SELECT al.request_id
                           FROM audit_log al
                           WHERE al.target_type = 'REVIEW_TASK'
                             AND al.target_id = rt.id
                             AND al.action = 'REVIEW_REJECT'
                           ORDER BY al.created_at DESC, al.id DESC
                           LIMIT 1
                       ) AS original_request_id
                FROM review_task rt
                JOIN skill_version sv ON sv.id = rt.skill_version_id
                WHERE rt.skill_version_id = :version_id
                  AND rt.status = 'REJECTED'
                ORDER BY rt.reviewed_at DESC NULLS LAST, rt.id DESC
                LIMIT 1
                FOR UPDATE OF rt
                """
            ),
            {"version_id": version.version_id},
        )
    ).mappings().one_or_none()
    if review_row is None:
        raise ValueError("Rejected version is missing completed review task")

    file_rows = (
        await connection.execute(
            text(
                """
                SELECT file_path, file_size, content_type, sha256, storage_key
                FROM skill_file
                WHERE version_id = :version_id
                ORDER BY id ASC
                """
            ),
            {"version_id": version.version_id},
        )
    ).mappings().all()
    scanner_rows = (
        await connection.execute(
            text(
                """
                SELECT scanner_type, verdict, max_severity, findings_count,
                       findings, scanned_at, created_at
                FROM security_audit
                WHERE skill_version_id = :version_id
                  AND deleted_at IS NULL
                ORDER BY created_at ASC, id ASC
                """
            ),
            {"version_id": version.version_id},
        )
    ).mappings().all()

    files = [
        {
            "path": str(row["file_path"]),
            "size": int(row["file_size"]),
            "contentType": row.get("content_type"),
            "sha256": str(row["sha256"]),
        }
        for row in file_rows
    ]
    scanner_summary = [
        {
            "scannerType": str(row["scanner_type"]),
            "verdict": str(row["verdict"]),
            "maxSeverity": row.get("max_severity"),
            "findingsCount": int(row.get("findings_count") or 0),
            "findings": row.get("findings") or [],
            "scannedAt": row.get("scanned_at"),
            "createdAt": row.get("created_at"),
        }
        for row in scanner_rows
    ]

    return ArchivedReviewAttempt(
        original_review_task_id=int(review_row["review_task_id"]),
        original_skill_version_id=version.version_id,
        skill_id=version.skill_id,
        namespace_id=int(review_row["namespace_id"]),
        namespace_slug=version.namespace,
        skill_slug=version.slug,
        version=version.version,
        status="REJECTED",
        submitted_by=str(review_row["submitted_by"]),
        reviewed_by=str(review_row["reviewed_by"]) if review_row.get("reviewed_by") is not None else None,
        review_comment=str(review_row["review_comment"]) if review_row.get("review_comment") is not None else None,
        submitted_at=review_row["submitted_at"],
        reviewed_at=review_row.get("reviewed_at"),
        parsed_metadata_json=review_row.get("parsed_metadata_json"),
        manifest_json=review_row.get("manifest_json"),
        files=files,
        scanner_summary=scanner_summary,
        original_request_id=(
            str(review_row["original_request_id"]) if review_row.get("original_request_id") is not None else None
        ),
    )


async def find_replaceable_version(
    connection: Any,
    *,
    namespace_id: int,
    namespace: str,
    slug: str,
    version: str,
    publisher_id: str,
    now: datetime | None = None,
) -> ReplaceableVersion | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT s.id AS skill_id,
                       s.latest_version_id AS latest_version_id,
                       sv.id AS version_id,
                       sv.version AS version,
                       sv.status AS status
                FROM skill s
                JOIN skill_version sv ON sv.skill_id = s.id
                WHERE s.namespace_id = :namespace_id
                  AND s.slug = :slug
                  AND s.owner_id = :publisher_id
                  AND sv.version = :version
                LIMIT 1
                """
            ),
            {
                "namespace_id": namespace_id,
                "slug": slug,
                "version": version,
                "publisher_id": publisher_id,
            },
        )
    ).mappings().one_or_none()

    if row is None:
        return None

    return ReplaceableVersion(
        skill_id=int(row["skill_id"]),
        namespace=namespace,
        slug=slug,
        version_id=int(row["version_id"]),
        version=str(row["version"]),
        status=str(row["status"]),
        publisher_id=publisher_id,
        latest_version_id=int(row["latest_version_id"]) if row.get("latest_version_id") is not None else None,
        now=now,
    )


async def cleanup_replaceable_version(connection: Any, version: ReplaceableVersion) -> ReplacementCleanupResult:
    _assert_replaceable_status(version.status, version.version)

    locked_row = (
        await connection.execute(
            text(
                """
                SELECT sv.status,
                       sv.version,
                       s.id AS skill_id,
                       s.slug,
                       s.owner_id,
                       s.status AS skill_status,
                       n.slug AS namespace_slug,
                       n.status AS namespace_status,
                       EXISTS (
                           SELECT 1
                           FROM review_task pending_rt
                           JOIN skill_version pending_sv ON pending_sv.id = pending_rt.skill_version_id
                           WHERE pending_sv.skill_id = s.id
                             AND pending_rt.status = 'PENDING'
                       ) AS has_pending_review
                FROM skill_version sv
                JOIN skill s ON s.id = sv.skill_id
                JOIN namespace n ON n.id = s.namespace_id
                WHERE sv.id = :version_id
                FOR UPDATE OF s, sv
                """
            ),
            {"version_id": version.version_id},
        )
    ).mappings().one_or_none()
    if locked_row is None:
        raise VersionReplacementConflict("Replacement version no longer exists")
    locked_row = dict(locked_row)
    _assert_locked_replacement(locked_row, version)
    current_status = str(locked_row["status"])
    _assert_replaceable_status(current_status, version.version)

    archived_review = (
        await _read_rejected_review_attempt(connection, version)
        if current_status == "REJECTED"
        else None
    )

    now = normalized_now(version.now)
    if version.latest_version_id == version.version_id:
        await connection.execute(
            text(
                """
                UPDATE skill
                SET latest_version_id = NULL,
                    updated_by = :publisher_id,
                    updated_at = :updated_at
                WHERE id = :skill_id
                """
            ),
            {"skill_id": version.skill_id, "publisher_id": version.publisher_id, "updated_at": now},
        )

    await connection.execute(
        text(
            """
            DELETE FROM review_task
            WHERE skill_version_id = :version_id
            """
        ),
        {"version_id": version.version_id},
    )

    file_rows = (
        await connection.execute(
            text(
                """
                SELECT file_path, file_size, content_type, sha256, storage_key
                FROM skill_file
                WHERE version_id = :version_id
                ORDER BY id ASC
                """
            ),
            {"version_id": version.version_id},
        )
    ).mappings().all()
    storage_keys = [
        str(row["storage_key"])
        for row in file_rows
        if row.get("storage_key") is not None and str(row["storage_key"]).strip()
    ]
    storage_keys.append(bundle_storage_key(version.skill_id, version.version_id))

    await connection.execute(
        text(
            """
            DELETE FROM skill_file
            WHERE version_id = :version_id
            """
        ),
        {"version_id": version.version_id},
    )
    await connection.execute(
        text(
            """
            UPDATE security_audit
            SET deleted_at = :deleted_at
            WHERE skill_version_id = :version_id
              AND deleted_at IS NULL
            """
        ),
        {"version_id": version.version_id, "deleted_at": now},
    )
    await connection.execute(
        text(
            """
            DELETE FROM skill_version
            WHERE id = :version_id
            """
        ),
        {"version_id": version.version_id},
    )

    return ReplacementCleanupResult(
        storage_keys=storage_keys,
        archived_review=archived_review,
    )


def delete_local_storage_objects(storage_base_path: str, storage_keys: list[str]) -> list[str]:
    return object_storage_for_base_path(storage_base_path).delete_many(storage_keys)


async def record_storage_delete_compensation(
    connection: Any,
    request: StorageDeleteCompensationInput,
) -> None:
    now = normalized_now(request.now)
    await connection.execute(
        text(
            """
            INSERT INTO skill_storage_delete_compensation (
                skill_id, namespace, slug, storage_keys_json, status, attempt_count,
                last_error, created_at, updated_at
            )
            VALUES (
                :skill_id, :namespace, :slug, :storage_keys_json, :status, :attempt_count,
                :last_error, :created_at, :updated_at
            )
            """
        ),
        {
            "skill_id": request.skill_id,
            "namespace": request.namespace,
            "slug": request.slug,
            "storage_keys_json": json.dumps(request.storage_keys, separators=(",", ":")),
            "status": "PENDING",
            "attempt_count": 0,
            "last_error": request.last_error,
            "created_at": now,
            "updated_at": now,
        },
    )


async def delete_local_storage_objects_or_record_compensation(
    connection: Any,
    storage_base_path: str,
    request: StorageDeleteCompensationInput,
) -> StorageDeleteResult:
    try:
        deleted = delete_local_storage_objects(storage_base_path, request.storage_keys)
        return StorageDeleteResult(deleted_keys=deleted, compensation_recorded=False)
    except Exception as exc:
        await record_storage_delete_compensation(
            connection,
            StorageDeleteCompensationInput(
                skill_id=request.skill_id,
                namespace=request.namespace,
                slug=request.slug,
                storage_keys=request.storage_keys,
                last_error=str(exc),
                now=request.now,
            ),
        )
        return StorageDeleteResult(deleted_keys=[], compensation_recorded=True)


def normalized_now(value: datetime | None) -> datetime:
    now = value or datetime.now(tz=UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)

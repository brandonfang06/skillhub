from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.audit.writer import write_audit_log
from app.publish.replacement import ArchivedReviewAttempt


@dataclass(frozen=True)
class ReviewAttemptArchiveInput:
    attempt: ArchivedReviewAttempt
    replacement_version_id: int | None
    replacement_review_task_id: int | None
    actor_user_id: str | None
    request_id: str | None
    client_ip: str | None
    user_agent: str | None
    archived_at: datetime | None = None
    actor_service_principal_id: str | None = None
    archive_reason: str = "REJECTED_VERSION_RESUBMIT"
    audit_action: str = "REJECTED_VERSION_RESUBMIT"


def _normalized_now(value: datetime | None) -> datetime:
    now = value or datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        normalized = _normalized_now(value)
        return normalized.isoformat().replace("+00:00", "Z")
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def _encode_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        default=_json_default,
    )


async def archive_review_attempt(
    connection: Any,
    request: ReviewAttemptArchiveInput,
) -> None:
    attempt = request.attempt
    archived_at = _normalized_now(request.archived_at)
    await connection.execute(
        text(
            """
            INSERT INTO review_attempt_archive (
                original_review_task_id, original_skill_version_id, skill_id,
                namespace_id, namespace_slug, skill_slug, version, status,
                submitted_by, reviewed_by, review_comment, submitted_at,
                reviewed_at, parsed_metadata_json, manifest_json, files_json,
                scanner_summary_json, original_request_id,
                replacement_version_id, replacement_review_task_id,
                archive_reason, archived_at
            )
            VALUES (
                :original_review_task_id, :original_skill_version_id, :skill_id,
                :namespace_id, :namespace_slug, :skill_slug, :version, :status,
                :submitted_by, :reviewed_by, :review_comment, :submitted_at,
                :reviewed_at, CAST(:parsed_metadata_json AS jsonb),
                CAST(:manifest_json AS jsonb), CAST(:files_json AS jsonb),
                CAST(:scanner_summary_json AS jsonb), :original_request_id,
                :replacement_version_id, :replacement_review_task_id,
                :archive_reason, :archived_at
            )
            """
        ),
        {
            "original_review_task_id": attempt.original_review_task_id,
            "original_skill_version_id": attempt.original_skill_version_id,
            "skill_id": attempt.skill_id,
            "namespace_id": attempt.namespace_id,
            "namespace_slug": attempt.namespace_slug,
            "skill_slug": attempt.skill_slug,
            "version": attempt.version,
            "status": attempt.status,
            "submitted_by": attempt.submitted_by,
            "reviewed_by": attempt.reviewed_by,
            "review_comment": attempt.review_comment,
            "submitted_at": attempt.submitted_at,
            "reviewed_at": attempt.reviewed_at,
            "parsed_metadata_json": _encode_json(attempt.parsed_metadata_json),
            "manifest_json": _encode_json(attempt.manifest_json),
            "files_json": _encode_json(attempt.files),
            "scanner_summary_json": _encode_json(attempt.scanner_summary),
            "original_request_id": attempt.original_request_id,
            "replacement_version_id": request.replacement_version_id,
            "replacement_review_task_id": request.replacement_review_task_id,
            "archive_reason": request.archive_reason,
            "archived_at": archived_at,
        },
    )
    await write_audit_log(
        connection,
        actor_user_id=request.actor_user_id,
        actor_service_principal_id=request.actor_service_principal_id,
        action=request.audit_action,
        target_type="SKILL_VERSION",
        target_id=request.replacement_version_id or attempt.original_skill_version_id,
        request_id=request.request_id,
        client_ip=request.client_ip,
        user_agent=request.user_agent,
        detail={
            "namespace": attempt.namespace_slug,
            "slug": attempt.skill_slug,
            "version": attempt.version,
            "archivedReviewTaskId": attempt.original_review_task_id,
            "archivedVersionId": attempt.original_skill_version_id,
            "replacementReviewTaskId": request.replacement_review_task_id,
        },
        created_at=archived_at,
    )


__all__ = [
    "ReviewAttemptArchiveInput",
    "archive_review_attempt",
]

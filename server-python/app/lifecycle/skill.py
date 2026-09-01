from __future__ import annotations

import json
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import yaml
from sqlalchemy import text

from app.admin.search import upsert_skill_search_document
from app.audit.writer import write_audit_log
from app.db.unit_of_work import transaction_connection

from app.auth.policy import NAMESPACE_MANAGER_ROLES, namespace_role_allows
from app.notifications.publisher import NotificationFanout
from app.object_storage import ObjectNotFoundError, object_storage_for_base_path
from app.publish.orchestration import PublishWriteInput, PublishWriteResult, execute_publish_write
from app.publish.package import PackageEntry, SkillMetadata, parse_skill_metadata, validate_package
from app.publish.publication_outcomes import (
    PublicationOutcomeInput,
    publish_publication_notifications,
    write_publication_outcomes,
)
from app.publish.replacement import (
    ReplaceableVersion,
    StorageDeleteCompensationInput,
    bundle_storage_key,
    delete_local_storage_objects_or_record_compensation,
    read_rejected_review_attempt,
)
from app.review.archive import ReviewAttemptArchiveInput, archive_review_attempt
from app.review.notifications import (
    publish_review_notifications,
    read_review_submission_recipients,
    write_review_submitted_notifications,
)


LIFECYCLE_NAMESPACE_ROLES = NAMESPACE_MANAGER_ROLES
DELETABLE_VERSION_STATUSES = {"DRAFT", "REJECTED", "SCAN_FAILED", "UPLOADED"}
CONFIRM_PUBLISH_VERSION_STATUSES = {"UPLOADED", "DRAFT"}
SUBMIT_REVIEW_VERSION_STATUSES = {"UPLOADED", "DRAFT"}
SUBMIT_REVIEW_VISIBILITIES = {"PUBLIC", "NAMESPACE_ONLY"}
SKILL_VISIBILITIES = {"PUBLIC", "NAMESPACE_ONLY", "PRIVATE"}


@dataclass(frozen=True)
class SkillArchiveInput:
    namespace: str
    slug: str
    user_id: str
    reason: str | None = None
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    now: datetime | None = None


@dataclass(frozen=True)
class SkillVisibilityUpdateInput:
    namespace: str
    slug: str
    visibility: str
    user_id: str
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    now: datetime | None = None


@dataclass(frozen=True)
class SkillVersionDeleteInput:
    namespace: str
    slug: str
    version: str
    user_id: str
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    now: datetime | None = None


@dataclass(frozen=True)
class SkillVersionWithdrawReviewInput:
    namespace: str
    slug: str
    version: str
    user_id: str
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    now: datetime | None = None


@dataclass(frozen=True)
class SkillConfirmPublishInput:
    namespace: str
    slug: str
    version: str
    user_id: str
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    now: datetime | None = None


@dataclass(frozen=True)
class SkillSubmitReviewInput:
    namespace: str
    slug: str
    version: str
    target_visibility: str
    user_id: str
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    now: datetime | None = None


@dataclass(frozen=True)
class SkillRereleaseInput:
    namespace: str
    slug: str
    version: str
    target_version: str
    confirm_warnings: bool
    user_id: str
    storage_base_path: str
    allowed_extensions: AbstractSet[str] | None = None
    scanner_enabled: bool = False
    scan_mode: str = "local"
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    now: datetime | None = None


@dataclass(frozen=True)
class SkillVersionDeleteResult:
    response: dict[str, Any]
    storage_keys: list[str]
    namespace: str
    slug: str
    skill_id: int


class SkillLifecycleError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _now(value: datetime | None) -> datetime:
    return value or datetime.now(UTC)


def _clean_namespace(namespace: str) -> str:
    return namespace[1:] if namespace.startswith("@") else namespace


def _reason_detail(reason: str | None) -> str | None:
    if reason is None or reason.strip() == "":
        return None
    return json.dumps({"reason": reason}, separators=(",", ":"))


async def _read_skill_context(
    connection: Any,
    namespace: str,
    slug: str,
    *,
    lock_skill: bool = False,
) -> dict[str, Any]:
    lock_clause = "FOR UPDATE OF n, s" if lock_skill else ""
    row = (
        await connection.execute(
            text(
                f"""
                SELECT s.id AS skill_id,
                       s.namespace_id,
                       s.slug AS skill_slug,
                       s.owner_id,
                       s.visibility,
                       s.status,
                       s.latest_version_id,
                       n.slug AS namespace_slug,
                       n.status AS namespace_status
                FROM namespace n
                JOIN skill s ON s.namespace_id = n.id
                WHERE n.slug = :namespace_slug
                  AND s.slug = :skill_slug
                LIMIT 1
                {lock_clause}
                """
            ),
            {"namespace_slug": _clean_namespace(namespace), "skill_slug": slug},
        )
    ).mappings().one_or_none()
    if row is None:
        raise SkillLifecycleError("error.skill.notFound", status_code=404)
    return dict(row)


async def _read_namespace_role(connection: Any, namespace_id: int, user_id: str) -> str | None:
    row = (
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
    ).mappings().one_or_none()
    return str(row["role"]) if row is not None else None


def _assert_can_manage(skill: dict[str, Any], user_id: str, namespace_role: str | None) -> None:
    if str(skill["owner_id"]) == user_id:
        return
    if namespace_role_allows(namespace_role, LIFECYCLE_NAMESPACE_ROLES):
        return
    raise SkillLifecycleError("error.skill.lifecycle.noPermission", status_code=403)


def _assert_namespace_active(namespace_status: object) -> None:
    status = str(namespace_status)
    if status == "FROZEN":
        raise SkillLifecycleError("error.namespace.frozen")
    if status == "ARCHIVED":
        raise SkillLifecycleError("error.namespace.archived")


async def _write_audit(
    connection: Any,
    *,
    actor_user_id: str,
    action: str,
    target_type: str,
    target_id: int,
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
    detail_json: str | None,
    created_at: datetime,
) -> None:
    await write_audit_log(
        connection,
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        request_id=request_id,
        client_ip=client_ip,
        user_agent=user_agent,
        detail={},
        detail_json=detail_json,
        created_at=created_at,
    )


async def _mutate_archive_status(
    engine: Any,
    request: SkillArchiveInput,
    *,
    status: str,
    action: str,
    audit_action: str,
    detail_json: str | None,
) -> dict[str, Any]:
    timestamp = _now(request.now)
    async with transaction_connection(engine) as connection:
        skill = await _read_skill_context(connection, request.namespace, request.slug)
        namespace_role = await _read_namespace_role(connection, int(skill["namespace_id"]), request.user_id)
        _assert_can_manage(skill, request.user_id, namespace_role)
        await connection.execute(
            text(
                """
                UPDATE skill
                SET status = :status,
                    updated_by = :updated_by,
                    updated_at = :updated_at
                WHERE id = :skill_id
                """
            ),
            {
                "status": status,
                "updated_by": request.user_id,
                "updated_at": timestamp,
                "skill_id": int(skill["skill_id"]),
            },
        )
        await _write_audit(
            connection,
            actor_user_id=request.user_id,
            action=audit_action,
            target_type="SKILL",
            target_id=int(skill["skill_id"]),
            request_id=request.request_id,
            client_ip=request.client_ip,
            user_agent=request.user_agent,
            detail_json=detail_json,
            created_at=timestamp,
        )
    return {"skillId": int(skill["skill_id"]), "versionId": None, "action": action, "status": status}


async def archive_skill(engine: Any, request: SkillArchiveInput) -> dict[str, Any]:
    return await _mutate_archive_status(
        engine,
        request,
        status="ARCHIVED",
        action="ARCHIVE",
        audit_action="ARCHIVE_SKILL",
        detail_json=_reason_detail(request.reason),
    )


async def unarchive_skill(engine: Any, request: SkillArchiveInput) -> dict[str, Any]:
    return await _mutate_archive_status(
        engine,
        request,
        status="ACTIVE",
        action="UNARCHIVE",
        audit_action="UNARCHIVE_SKILL",
        detail_json=None,
    )


async def update_skill_visibility(engine: Any, request: SkillVisibilityUpdateInput) -> dict[str, Any]:
    if request.visibility not in SKILL_VISIBILITIES:
        raise SkillLifecycleError("error.skill.publish.visibility.invalid")

    timestamp = _now(request.now)
    async with transaction_connection(engine) as connection:
        skill = await _read_skill_context(
            connection,
            request.namespace,
            request.slug,
            lock_skill=True,
        )
        namespace_role = await _read_namespace_role(connection, int(skill["namespace_id"]), request.user_id)
        _assert_can_manage(skill, request.user_id, namespace_role)
        _assert_namespace_active(skill["namespace_status"])

        skill_id = int(skill["skill_id"])
        previous_visibility = str(skill["visibility"])
        if previous_visibility == request.visibility:
            return {"skillId": skill_id, "visibility": request.visibility, "changed": False}

        await connection.execute(
            text(
                """
                UPDATE skill
                SET visibility = :visibility,
                    updated_by = :updated_by,
                    updated_at = :updated_at
                WHERE id = :skill_id
                """
            ),
            {
                "visibility": request.visibility,
                "updated_by": request.user_id,
                "updated_at": timestamp,
                "skill_id": skill_id,
            },
        )
        await _write_audit(
            connection,
            actor_user_id=request.user_id,
            action="UPDATE_SKILL_VISIBILITY",
            target_type="SKILL",
            target_id=skill_id,
            request_id=request.request_id,
            client_ip=request.client_ip,
            user_agent=request.user_agent,
            detail_json=json.dumps(
                {
                    "previousVisibility": previous_visibility,
                    "visibility": request.visibility,
                },
                separators=(",", ":"),
            ),
            created_at=timestamp,
        )
        await upsert_skill_search_document(connection, skill_id)

    return {"skillId": skill_id, "visibility": request.visibility, "changed": True}


async def _read_version(connection: Any, skill_id: int, version: str) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT id AS version_id,
                       version,
                       status,
                       published_at
                FROM skill_version
                WHERE skill_id = :skill_id
                  AND version = :version
                LIMIT 1
                """
            ),
            {"skill_id": skill_id, "version": version},
        )
    ).mappings().one_or_none()
    if row is None:
        raise SkillLifecycleError("error.skill.version.notFound", status_code=404)
    return dict(row)


async def _read_original_confirm_publish_actor(connection: Any, version_id: int) -> str:
    row = (
        await connection.execute(
            text(
                """
                SELECT actor_user_id
                FROM audit_log
                WHERE action = 'CONFIRM_PUBLISH'
                  AND target_type = 'SKILL_VERSION'
                  AND target_id = :version_id
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """
            ),
            {"version_id": version_id},
        )
    ).mappings().one_or_none()
    if row is None or row.get("actor_user_id") is None:
        raise SkillLifecycleError("error.skill.confirm.replay.missingAudit", status_code=409)
    return str(row["actor_user_id"])


async def _find_version(connection: Any, skill_id: int, version: str) -> dict[str, Any] | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT id AS version_id,
                       version,
                       status
                FROM skill_version
                WHERE skill_id = :skill_id
                  AND version = :version
                LIMIT 1
                """
            ),
            {"skill_id": skill_id, "version": version},
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


async def _read_source_files(connection: Any, version_id: int) -> list[dict[str, Any]]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT file_path,
                       content_type,
                       storage_key
                FROM skill_file
                WHERE version_id = :version_id
                ORDER BY file_path ASC
                """
            ),
            {"version_id": version_id},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def _read_versions_for_update(connection: Any, skill_id: int) -> list[dict[str, Any]]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT id AS version_id,
                       version,
                       status
                FROM skill_version
                WHERE skill_id = :skill_id
                ORDER BY id ASC
                FOR UPDATE
                """
            ),
            {"skill_id": skill_id},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def _read_review_tasks_for_update(connection: Any, version_id: int) -> list[dict[str, Any]]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT id AS review_task_id,
                       status
                FROM review_task
                WHERE skill_version_id = :version_id
                ORDER BY id ASC
                FOR UPDATE
                """
            ),
            {"version_id": version_id},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def _read_pending_review_task_count(connection: Any, version_id: int) -> int:
    result = await connection.execute(
        text(
            """
            SELECT COUNT(*) AS pending_count
            FROM review_task
            WHERE skill_version_id = :version_id
              AND status = 'PENDING'
            """
        ),
        {"version_id": version_id},
    )
    if hasattr(result, "scalar_one"):
        return int(result.scalar_one())
    row = result.mappings().one_or_none()
    return int(row["pending_count"]) if row is not None else 0


async def _read_storage_keys(connection: Any, version_id: int, skill_id: int) -> list[str]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT storage_key
                FROM skill_file
                WHERE version_id = :version_id
                ORDER BY id ASC
                """
            ),
            {"version_id": version_id},
        )
    ).mappings().all()
    storage_keys = [
        str(row["storage_key"])
        for row in rows
        if row.get("storage_key") is not None and str(row["storage_key"]).strip()
    ]
    storage_keys.append(bundle_storage_key(skill_id, version_id))
    return storage_keys


async def _read_latest_published_version_id(connection: Any, skill_id: int, excluding_version_id: int) -> int | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT id
                FROM skill_version
                WHERE skill_id = :skill_id
                  AND status = 'PUBLISHED'
                  AND id <> :excluding_version_id
                ORDER BY published_at DESC NULLS LAST,
                         created_at DESC NULLS LAST,
                         id DESC
                LIMIT 1
                """
            ),
            {"skill_id": skill_id, "excluding_version_id": excluding_version_id},
        )
    ).mappings().one_or_none()
    return int(row["id"]) if row is not None and row.get("id") is not None else None


async def delete_skill_version(engine: Any, request: SkillVersionDeleteInput) -> SkillVersionDeleteResult:
    timestamp = _now(request.now)
    async with transaction_connection(engine) as connection:
        skill = await _read_skill_context(connection, request.namespace, request.slug)
        namespace_role = await _read_namespace_role(connection, int(skill["namespace_id"]), request.user_id)
        _assert_can_manage(skill, request.user_id, namespace_role)

        skill_id = int(skill["skill_id"])
        versions = await _read_versions_for_update(connection, skill_id)
        version = next((candidate for candidate in versions if str(candidate["version"]) == request.version), None)
        if version is None:
            raise SkillLifecycleError("error.skill.version.notFound", status_code=404)
        version_id = int(version["version_id"])
        version_name = str(version["version"])
        version_status = str(version["status"])
        if version_status not in DELETABLE_VERSION_STATUSES:
            raise SkillLifecycleError("error.skill.version.delete.unsupported")
        if len(versions) <= 1:
            raise SkillLifecycleError("error.skill.version.delete.lastVersion")

        review_tasks = await _read_review_tasks_for_update(connection, version_id)
        if any(str(task["status"]) == "PENDING" for task in review_tasks):
            raise SkillLifecycleError("error.skill.version.delete.pendingReview", status_code=409)

        if version_status == "REJECTED" and any(
            str(task["status"]) == "REJECTED" for task in review_tasks
        ):
            archived_review = await read_rejected_review_attempt(
                connection,
                ReplaceableVersion(
                    skill_id=skill_id,
                    namespace=str(skill["namespace_slug"]),
                    slug=str(skill["skill_slug"]),
                    version_id=version_id,
                    version=version_name,
                    status=version_status,
                    publisher_id=str(skill["owner_id"]),
                    latest_version_id=(
                        int(skill["latest_version_id"]) if skill.get("latest_version_id") is not None else None
                    ),
                    now=timestamp,
                ),
            )
            await archive_review_attempt(
                connection,
                ReviewAttemptArchiveInput(
                    attempt=archived_review,
                    replacement_version_id=None,
                    replacement_review_task_id=None,
                    actor_user_id=request.user_id,
                    request_id=request.request_id,
                    client_ip=request.client_ip,
                    user_agent=request.user_agent,
                    archived_at=timestamp,
                    archive_reason="REJECTED_VERSION_DELETE",
                    audit_action="REJECTED_VERSION_DELETE",
                ),
            )

        storage_keys = await _read_storage_keys(connection, version_id, skill_id)

        if skill.get("latest_version_id") is not None and int(skill["latest_version_id"]) == version_id:
            latest_version_id = await _read_latest_published_version_id(connection, skill_id, version_id)
            await connection.execute(
                text(
                    """
                    UPDATE skill
                    SET latest_version_id = :latest_version_id,
                        updated_by = :updated_by,
                        updated_at = :updated_at
                    WHERE id = :skill_id
                    """
                ),
                {
                    "latest_version_id": latest_version_id,
                    "updated_by": request.user_id,
                    "updated_at": timestamp,
                    "skill_id": skill_id,
                },
            )

        await connection.execute(
            text(
                """
                DELETE FROM review_task
                WHERE skill_version_id = :version_id
                """
            ),
            {"version_id": version_id},
        )
        await connection.execute(
            text(
                """
                DELETE FROM scan_task_outbox
                WHERE version_id = :version_id
                """
            ),
            {"version_id": version_id},
        )
        await connection.execute(
            text(
                """
                DELETE FROM skill_file
                WHERE version_id = :version_id
                """
            ),
            {"version_id": version_id},
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
            {"version_id": version_id, "deleted_at": timestamp},
        )
        await connection.execute(
            text(
                """
                DELETE FROM skill_version
                WHERE id = :version_id
                """
            ),
            {"version_id": version_id},
        )
        await _write_audit(
            connection,
            actor_user_id=request.user_id,
            action="DELETE_SKILL_VERSION",
            target_type="SKILL_VERSION",
            target_id=version_id,
            request_id=request.request_id,
            client_ip=request.client_ip,
            user_agent=request.user_agent,
            detail_json=json.dumps({"version": version_name}, separators=(",", ":")),
            created_at=timestamp,
        )

    return SkillVersionDeleteResult(
        response={"skillId": skill_id, "versionId": version_id, "action": "DELETE_VERSION", "status": version_name},
        storage_keys=storage_keys,
        namespace=_clean_namespace(request.namespace),
        slug=request.slug,
        skill_id=skill_id,
    )


async def _read_pending_review_task_for_version(connection: Any, version_id: int) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT id AS review_task_id,
                       submitted_by,
                       status
                FROM review_task
                WHERE skill_version_id = :version_id
                  AND status = 'PENDING'
                LIMIT 1
                """
            ),
            {"version_id": version_id},
        )
    ).mappings().one_or_none()
    if not row:
        raise SkillLifecycleError("review_task.not_found_for_version", status_code=404)
    return dict(row)


async def withdraw_skill_version_review(engine: Any, request: SkillVersionWithdrawReviewInput) -> dict[str, Any]:
    timestamp = _now(request.now)
    async with transaction_connection(engine) as connection:
        skill = await _read_skill_context(connection, request.namespace, request.slug)
        _assert_namespace_active(skill.get("namespace_status"))

        skill_id = int(skill["skill_id"])
        version = await _read_version(connection, skill_id, request.version)
        version_id = int(version["version_id"])
        version_name = str(version["version"])
        if str(version["status"]) != "PENDING_REVIEW":
            raise SkillLifecycleError("review.withdraw.not_pending")

        review_task = await _read_pending_review_task_for_version(connection, version_id)
        if str(review_task["submitted_by"]) != request.user_id:
            raise SkillLifecycleError("review.withdraw.not_submitter", status_code=403)

        await connection.execute(
            text(
                """
                DELETE FROM review_task
                WHERE id = :review_task_id
                """
            ),
            {"review_task_id": int(review_task["review_task_id"])},
        )
        await connection.execute(
            text(
                """
                UPDATE skill_version
                SET status = :status
                WHERE id = :version_id
                """
            ),
            {"status": "UPLOADED", "version_id": version_id},
        )
        await connection.execute(
            text(
                """
                UPDATE skill
                SET updated_by = :updated_by,
                    updated_at = :updated_at
                WHERE id = :skill_id
                """
            ),
            {"updated_by": request.user_id, "updated_at": timestamp, "skill_id": skill_id},
        )
        await _write_audit(
            connection,
            actor_user_id=request.user_id,
            action="REVIEW_WITHDRAW",
            target_type="SKILL_VERSION",
            target_id=version_id,
            request_id=request.request_id,
            client_ip=request.client_ip,
            user_agent=request.user_agent,
            detail_json=json.dumps({"version": version_name}, separators=(",", ":")),
            created_at=timestamp,
        )

    return {"skillId": skill_id, "versionId": version_id, "action": "WITHDRAW_REVIEW", "status": "UPLOADED"}


async def confirm_publish_skill_version(
    engine: Any,
    request: SkillConfirmPublishInput,
    *,
    notification_fanout: NotificationFanout | None = None,
    publication_outcome_writer: Any = write_publication_outcomes,
    publication_notification_publisher: Any = publish_publication_notifications,
) -> dict[str, Any]:
    timestamp = _now(request.now)
    outcome_publisher_id = request.user_id
    outcome_created_at = timestamp
    async with transaction_connection(engine) as connection:
        skill = await _read_skill_context(
            connection,
            request.namespace,
            request.slug,
            lock_skill=True,
        )
        namespace_role = await _read_namespace_role(connection, int(skill["namespace_id"]), request.user_id)
        _assert_can_manage(skill, request.user_id, namespace_role)

        if str(skill.get("visibility")) != "PRIVATE":
            raise SkillLifecycleError("error.skill.confirm.notPrivate")

        skill_id = int(skill["skill_id"])
        version = await _read_version(connection, skill_id, request.version)
        version_id = int(version["version_id"])
        version_name = str(version["version"])
        version_status = str(version["status"])
        replay = version_status == "PUBLISHED" and skill.get("latest_version_id") == version_id
        if version_status not in CONFIRM_PUBLISH_VERSION_STATUSES and not replay:
            raise SkillLifecycleError("error.skill.version.confirm.notUploaded")

        if replay:
            published_at = version.get("published_at")
            if not isinstance(published_at, datetime):
                raise SkillLifecycleError(
                    "error.skill.confirm.replay.missingPublishedAt",
                    status_code=409,
                )
            outcome_created_at = published_at
            outcome_publisher_id = await _read_original_confirm_publish_actor(
                connection,
                version_id,
            )
        else:
            await connection.execute(
                text(
                    """
                    UPDATE skill_version
                    SET status = :status,
                        published_at = :published_at
                    WHERE id = :version_id
                    """
                ),
                {"status": "PUBLISHED", "published_at": timestamp, "version_id": version_id},
            )
            await connection.execute(
                text(
                    """
                    UPDATE skill
                    SET latest_version_id = :latest_version_id,
                        updated_by = :updated_by,
                        updated_at = :updated_at
                    WHERE id = :skill_id
                    """
                ),
                {
                    "latest_version_id": version_id,
                    "updated_by": request.user_id,
                    "updated_at": timestamp,
                    "skill_id": skill_id,
                },
            )
            await _write_audit(
                connection,
                actor_user_id=request.user_id,
                action="CONFIRM_PUBLISH",
                target_type="SKILL_VERSION",
                target_id=version_id,
                request_id=request.request_id,
                client_ip=request.client_ip,
                user_agent=request.user_agent,
                detail_json=json.dumps({"version": version_name}, separators=(",", ":")),
                created_at=timestamp,
            )

        publication_outcome = PublicationOutcomeInput(
            skill_id=skill_id,
            version_id=version_id,
            publisher_id=outcome_publisher_id,
            created_at=outcome_created_at,
        )
        publication_notification_rows = await publication_outcome_writer(
            connection,
            publication_outcome,
        )

    await publication_notification_publisher(
        notification_fanout,
        publication_notification_rows,
        publication_outcome,
    )

    return {"skillId": skill_id, "versionId": version_id, "action": "CONFIRM_PUBLISH", "status": "PUBLISHED"}


async def submit_skill_version_for_review(
    engine: Any,
    request: SkillSubmitReviewInput,
    *,
    notification_fanout: NotificationFanout | None = None,
) -> dict[str, Any]:
    if request.target_visibility not in SUBMIT_REVIEW_VISIBILITIES:
        raise SkillLifecycleError("error.skill.review.visibility.invalid")

    timestamp = _now(request.now)
    notification_rows: list[dict[str, Any]] = []
    async with transaction_connection(engine) as connection:
        skill = await _read_skill_context(connection, request.namespace, request.slug)
        namespace_role = await _read_namespace_role(connection, int(skill["namespace_id"]), request.user_id)
        _assert_can_manage(skill, request.user_id, namespace_role)

        skill_id = int(skill["skill_id"])
        namespace_id = int(skill["namespace_id"])
        version = await _read_version(connection, skill_id, request.version)
        version_id = int(version["version_id"])
        version_name = str(version["version"])
        if str(version["status"]) not in SUBMIT_REVIEW_VERSION_STATUSES:
            raise SkillLifecycleError("error.skill.version.submit.notUploaded")

        if await _read_pending_review_task_count(connection, version_id) > 0:
            raise SkillLifecycleError("review.submit.duplicate")

        updated = (
            await connection.execute(
                text(
                    """
                    UPDATE skill_version
                    SET status = :status,
                        requested_visibility = :requested_visibility
                    WHERE id = :version_id
                      AND status IN ('DRAFT', 'UPLOADED')
                    RETURNING 1
                    """
                ),
                {
                    "status": "PENDING_REVIEW",
                    "requested_visibility": request.target_visibility,
                    "version_id": version_id,
                },
            )
        ).scalar_one_or_none()
        if updated is None:
            raise SkillLifecycleError("review.concurrent_update", status_code=409)
        review_task_row = (
            await connection.execute(
                text(
                    """
                    INSERT INTO review_task (
                        skill_version_id, namespace_id, status, version, submitted_by, submitted_at
                    )
                    VALUES (
                        :version_id, :namespace_id, 'PENDING', 1, :submitted_by, :submitted_at
                    )
                    RETURNING id
                    """
                ),
                {
                    "version_id": version_id,
                    "namespace_id": namespace_id,
                    "submitted_by": request.user_id,
                    "submitted_at": timestamp,
                },
            )
        ).mappings().one_or_none()
        if review_task_row is None:
            raise SkillLifecycleError("review.submit.duplicate")
        review_task_id = int(review_task_row["id"])
        await _write_audit(
            connection,
            actor_user_id=request.user_id,
            action="SUBMIT_REVIEW",
            target_type="SKILL_VERSION",
            target_id=version_id,
            request_id=request.request_id,
            client_ip=request.client_ip,
            user_agent=request.user_agent,
            detail_json=json.dumps(
                {"version": version_name, "targetVisibility": request.target_visibility},
                separators=(",", ":"),
            ),
            created_at=timestamp,
        )
        notification_rows = await write_review_submitted_notifications(
            connection,
            recipients=await read_review_submission_recipients(
                connection,
                namespace_id=namespace_id,
            ),
            review_task_id=review_task_id,
            skill_id=skill_id,
            version_id=version_id,
            submitter_id=request.user_id,
            namespace=str(skill["namespace_slug"]),
            slug=str(skill["skill_slug"]),
            skill_name=str(skill["skill_slug"]),
            version=version_name,
            created_at=timestamp,
        )

    await publish_review_notifications(notification_fanout, notification_rows)
    return {"skillId": skill_id, "versionId": version_id, "action": "SUBMIT_REVIEW", "status": "PENDING_REVIEW"}


def _read_local_object(storage_base_path: str, object_key: str) -> bytes:
    try:
        return object_storage_for_base_path(storage_base_path).read_bytes(object_key)
    except ValueError as exc:
        raise SkillLifecycleError(f"Object key escapes storage base: {object_key}") from exc
    except (OSError, ObjectNotFoundError) as exc:
        raise SkillLifecycleError("error.skill.rerelease.sourceFileNotFound") from exc


def _rewrite_skill_md_version(content: bytes, target_version: str) -> bytes:
    text_content = content.decode("utf-8")
    lines = text_content.splitlines()
    closing_index: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing_index = index
            break
    if not lines or lines[0].strip() != "---" or closing_index is None:
        raise SkillLifecycleError("error.skill.publish.skillMd.notFound")

    metadata = parse_skill_metadata(content)
    frontmatter = dict(metadata.frontmatter)
    frontmatter["version"] = target_version
    body = "\n".join(lines[closing_index + 1 :])
    rewritten = "---\n" + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip() + "\n---\n" + body
    if text_content.endswith("\n"):
        rewritten += "\n"
    return rewritten.encode("utf-8")


def _rebuild_rerelease_entries(
    storage_base_path: str,
    files: list[dict[str, Any]],
    target_version: str,
) -> list[PackageEntry]:
    entries: list[PackageEntry] = []
    for file in files:
        path = str(file["file_path"])
        content = _read_local_object(storage_base_path, str(file["storage_key"]))
        if path == "SKILL.md":
            content = _rewrite_skill_md_version(content, target_version)
        entries.append(PackageEntry(path, content, str(file.get("content_type") or "application/octet-stream")))
    return entries


def _validate_rerelease_entries(
    entries: list[PackageEntry],
    confirm_warnings: bool,
    allowed_extensions: AbstractSet[str] | None,
) -> SkillMetadata:
    validation = validate_package(entries, allowed_extensions=allowed_extensions)
    if not validation.valid:
        raise SkillLifecycleError("error.skill.publish.package.invalid")
    if validation.warnings and not confirm_warnings:
        raise SkillLifecycleError("error.skill.publish.precheck.confirmRequired")
    if validation.metadata is None:
        raise SkillLifecycleError("error.skill.publish.skillMd.notFound")
    return validation.metadata


async def rerelease_skill_version(
    engine: Any,
    request: SkillRereleaseInput,
    *,
    publish_writer: Any | None = None,
    notification_fanout: NotificationFanout | None = None,
) -> dict[str, Any]:
    timestamp = _now(request.now)
    target_version = request.target_version.strip()
    if not target_version:
        raise SkillLifecycleError("validation.required")

    async with transaction_connection(engine) as connection:
        skill = await _read_skill_context(connection, request.namespace, request.slug)
        _assert_namespace_active(skill.get("namespace_status"))
        namespace_role = await _read_namespace_role(connection, int(skill["namespace_id"]), request.user_id)
        _assert_can_manage(skill, request.user_id, namespace_role)

        skill_id = int(skill["skill_id"])
        source_version = await _read_version(connection, skill_id, request.version)
        source_version_id = int(source_version["version_id"])
        source_version_name = str(source_version["version"])
        if str(source_version["status"]) != "PUBLISHED":
            raise SkillLifecycleError("error.skill.version.notPublished")

        existing_target = await _find_version(connection, skill_id, target_version)
        if existing_target:
            raise SkillLifecycleError("error.skill.version.exists")

        files = await _read_source_files(connection, source_version_id)

    entries = _rebuild_rerelease_entries(request.storage_base_path, files, target_version)
    metadata = _validate_rerelease_entries(entries, request.confirm_warnings, request.allowed_extensions)
    write_input = PublishWriteInput(
        namespace_id=int(skill["namespace_id"]),
        namespace_slug=str(skill["namespace_slug"]),
        slug=str(skill["skill_slug"]),
        display_name=metadata.name,
        summary=metadata.description,
        publisher_id=request.user_id,
        visibility=str(skill["visibility"]),
        version=target_version,
        auto_publish=False,
        metadata=metadata,
        entries=entries,
        storage_base_path=request.storage_base_path,
        scanner_enabled=request.scanner_enabled,
        scan_mode=request.scan_mode,
        request_id=request.request_id,
        client_ip=request.client_ip,
        user_agent=request.user_agent,
        now=timestamp,
    )
    async def write_rerelease_audit(connection: Any, _skill_id: int | None = None, _version_id: int | None = None) -> None:
        await _write_audit(
            connection,
            actor_user_id=request.user_id,
            action="RERELEASE_SKILL_VERSION",
            target_type="SKILL_VERSION",
            target_id=source_version_id,
            request_id=request.request_id,
            client_ip=request.client_ip,
            user_agent=request.user_agent,
            detail_json=json.dumps(
                {"sourceVersion": source_version_name, "targetVersion": target_version},
                separators=(",", ":"),
            ),
            created_at=timestamp,
        )

    if publish_writer is not None:
        publish_result = await publish_writer(write_input)
        async with transaction_connection(engine) as connection:
            await write_rerelease_audit(connection)
    else:
        publish_result = await execute_publish_write(
            engine,
            write_input,
            notification_fanout=notification_fanout,
            after_publish=write_rerelease_audit,
        )

    return {
        "skillId": publish_result.skill_id,
        "versionId": publish_result.version_id,
        "action": "RERELEASE_VERSION",
        "status": publish_result.version_status,
    }


async def cleanup_deleted_version_storage(engine: Any, storage_base_path: str, result: SkillVersionDeleteResult) -> None:
    async with transaction_connection(engine) as connection:
        await delete_local_storage_objects_or_record_compensation(
            connection,
            storage_base_path,
            StorageDeleteCompensationInput(
                skill_id=result.skill_id,
                namespace=result.namespace,
                slug=result.slug,
                storage_keys=result.storage_keys,
                last_error=None,
            ),
        )

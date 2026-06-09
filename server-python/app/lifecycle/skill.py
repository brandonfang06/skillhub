from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.publish.replacement import (
    StorageDeleteCompensationInput,
    bundle_storage_key,
    delete_local_storage_objects_or_record_compensation,
)


LIFECYCLE_NAMESPACE_ROLES = {"OWNER", "ADMIN"}
DELETABLE_VERSION_STATUSES = {"DRAFT", "REJECTED", "SCAN_FAILED", "UPLOADED"}
CONFIRM_PUBLISH_VERSION_STATUSES = {"UPLOADED", "DRAFT"}
SUBMIT_REVIEW_VERSION_STATUSES = {"UPLOADED", "DRAFT"}
SUBMIT_REVIEW_VISIBILITIES = {"PUBLIC", "NAMESPACE_ONLY"}


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


async def _read_skill_context(connection: Any, namespace: str, slug: str) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
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
    if namespace_role in LIFECYCLE_NAMESPACE_ROLES:
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
    await connection.execute(
        text(
            """
            INSERT INTO audit_log (
                actor_user_id, action, target_type, target_id, request_id,
                client_ip, user_agent, detail_json, created_at
            )
            VALUES (
                :actor_user_id, :action, :target_type, :target_id, :request_id,
                :client_ip, :user_agent, :detail_json, :created_at
            )
            """
        ),
        {
            "actor_user_id": actor_user_id,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "request_id": request_id,
            "client_ip": client_ip,
            "user_agent": user_agent,
            "detail_json": detail_json,
            "created_at": created_at,
        },
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
    async with engine.begin() as connection:
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


async def _read_version(connection: Any, skill_id: int, version: str) -> dict[str, Any]:
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
    if row is None:
        raise SkillLifecycleError("error.skill.version.notFound", status_code=404)
    return dict(row)


async def _read_version_count(connection: Any, skill_id: int) -> int:
    row = (
        await connection.execute(
            text(
                """
                SELECT COUNT(*) AS version_count
                FROM skill_version
                WHERE skill_id = :skill_id
                """
            ),
            {"skill_id": skill_id},
        )
    ).mappings().one_or_none()
    return int(row["version_count"]) if row is not None else 0


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
    async with engine.begin() as connection:
        skill = await _read_skill_context(connection, request.namespace, request.slug)
        namespace_role = await _read_namespace_role(connection, int(skill["namespace_id"]), request.user_id)
        _assert_can_manage(skill, request.user_id, namespace_role)

        skill_id = int(skill["skill_id"])
        version = await _read_version(connection, skill_id, request.version)
        version_id = int(version["version_id"])
        version_name = str(version["version"])
        version_status = str(version["status"])
        if version_status not in DELETABLE_VERSION_STATUSES:
            raise SkillLifecycleError("error.skill.version.delete.unsupported")
        if await _read_version_count(connection, skill_id) <= 1:
            raise SkillLifecycleError("error.skill.version.delete.lastVersion")

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
    async with engine.begin() as connection:
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


async def confirm_publish_skill_version(engine: Any, request: SkillConfirmPublishInput) -> dict[str, Any]:
    timestamp = _now(request.now)
    async with engine.begin() as connection:
        skill = await _read_skill_context(connection, request.namespace, request.slug)
        namespace_role = await _read_namespace_role(connection, int(skill["namespace_id"]), request.user_id)
        _assert_can_manage(skill, request.user_id, namespace_role)

        if str(skill.get("visibility")) != "PRIVATE":
            raise SkillLifecycleError("error.skill.confirm.notPrivate")

        skill_id = int(skill["skill_id"])
        version = await _read_version(connection, skill_id, request.version)
        version_id = int(version["version_id"])
        version_name = str(version["version"])
        if str(version["status"]) not in CONFIRM_PUBLISH_VERSION_STATUSES:
            raise SkillLifecycleError("error.skill.version.confirm.notUploaded")

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

    return {"skillId": skill_id, "versionId": version_id, "action": "CONFIRM_PUBLISH", "status": "PUBLISHED"}


async def submit_skill_version_for_review(engine: Any, request: SkillSubmitReviewInput) -> dict[str, Any]:
    if request.target_visibility not in SUBMIT_REVIEW_VISIBILITIES:
        raise SkillLifecycleError("error.skill.review.visibility.invalid")

    timestamp = _now(request.now)
    async with engine.begin() as connection:
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

        await connection.execute(
            text(
                """
                UPDATE skill_version
                SET status = :status,
                    requested_visibility = :requested_visibility
                WHERE id = :version_id
                """
            ),
            {
                "status": "PENDING_REVIEW",
                "requested_visibility": request.target_visibility,
                "version_id": version_id,
            },
        )
        await connection.execute(
            text(
                """
                INSERT INTO review_task (
                    skill_version_id, namespace_id, status, version, submitted_by, submitted_at
                )
                VALUES (
                    :version_id, :namespace_id, 'PENDING', 1, :submitted_by, :submitted_at
                )
                """
            ),
            {
                "version_id": version_id,
                "namespace_id": namespace_id,
                "submitted_by": request.user_id,
                "submitted_at": timestamp,
            },
        )
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

    return {"skillId": skill_id, "versionId": version_id, "action": "SUBMIT_REVIEW", "status": "PENDING_REVIEW"}


async def cleanup_deleted_version_storage(engine: Any, storage_base_path: str, result: SkillVersionDeleteResult) -> None:
    async with engine.begin() as connection:
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

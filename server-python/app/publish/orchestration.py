from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Protocol

from app.admin.search import upsert_skill_search_document
from app.db.unit_of_work import transaction_connection
from app.notifications.publisher import NotificationFanout
from app.object_storage import ObjectStorage, object_storage_for_base_path
from app.publish.package import PackageEntry, SkillMetadata
from app.publish.publication_outcomes import (
    PublicationOutcomeInput,
    publish_publication_notifications,
    write_publication_outcomes,
)
from app.publish.replacement import (
    ReplaceableVersion,
    StorageDeleteCompensationInput,
    VersionReplacementConflict,
    cleanup_replaceable_version,
    delete_local_storage_objects_or_record_compensation,
)
from app.publish.scan_worker import mark_scan_task_failed
from app.publish.side_effects import (
    PublishSideEffectInput,
    PublishSideEffectResult,
    apply_publish_side_effects,
)
from app.publish.storage import StoredPackageResult, write_package_objects
from app.publish.transaction import (
    PublishDbFinalizeInput,
    PublishDbPrepareInput,
    finalize_publish_db_records,
    prepare_publish_db_records,
)
from app.review.archive import ReviewAttemptArchiveInput, archive_review_attempt
from app.review.notifications import (
    publish_review_notifications,
    read_review_submission_recipients,
    write_review_submitted_notifications,
)


@dataclass(frozen=True)
class PublishWriteInput:
    namespace_id: int
    namespace_slug: str
    slug: str
    display_name: str
    summary: str
    publisher_id: str
    visibility: str
    version: str
    auto_publish: bool
    metadata: SkillMetadata
    entries: list[PackageEntry]
    storage_base_path: str
    storage: ObjectStorage | None = None
    scanner_enabled: bool = False
    scan_mode: str = "local"
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    compat_namespace: str | None = None
    compat_slug: str | None = None
    replacement: ReplaceableVersion | None = None
    now: datetime | None = None
    task_id: str | None = None
    submitter_id: str | None = None
    actor_user_id: str | None = None
    actor_service_principal_id: str | None = None

    def with_replacement(
        self, replacement_version: ReplaceableVersion
    ) -> PublishWriteInput:
        return replace(self, replacement=replacement_version)

    @property
    def resolved_submitter_id(self) -> str:
        return self.submitter_id or self.publisher_id

    @property
    def resolved_actor_user_id(self) -> str:
        return self.actor_user_id or self.publisher_id

    @property
    def audit_actor_user_id(self) -> str | None:
        if self.actor_service_principal_id is not None:
            return None
        return self.resolved_actor_user_id


@dataclass(frozen=True)
class PublishWriteResult:
    skill_id: int
    version_id: int
    version_status: str
    latest_version_updated: bool
    stored_package: StoredPackageResult
    side_effects: PublishSideEffectResult
    replacement_deleted_keys: list[str]
    replacement_compensation_recorded: bool


class ScanTaskPublisher(Protocol):
    async def publish_scan_task(self, task: Any) -> None:
        pass


def write_local_package_objects(
    storage_base_path: str,
    skill_id: int,
    version_id: int,
    entries: list[PackageEntry],
) -> StoredPackageResult:
    return write_package_objects(
        object_storage_for_base_path(storage_base_path), skill_id, version_id, entries
    )


async def execute_publish_write(
    engine: Any,
    request: PublishWriteInput,
    *,
    scan_task_publisher: ScanTaskPublisher | None = None,
    notification_fanout: NotificationFanout | None = None,
    publication_outcome_writer: Callable[
        [Any, PublicationOutcomeInput], Awaitable[list[dict[str, Any]]]
    ] = write_publication_outcomes,
    publication_notification_publisher: Callable[
        [NotificationFanout | None, list[dict[str, Any]], PublicationOutcomeInput],
        Awaitable[None],
    ] = publish_publication_notifications,
    after_prepare: Callable[[Any, int, int], Awaitable[None]] | None = None,
    after_publish: Callable[[Any, int, int], Awaitable[None]] | None = None,
) -> PublishWriteResult:
    if request.replacement is not None and request.replacement.status == "REJECTED":
        if request.auto_publish or request.visibility == "PRIVATE":
            raise VersionReplacementConflict(
                "Rejected version resubmission requires review"
            )
    if request.scanner_enabled and scan_task_publisher is None:
        raise ValueError(
            "Scan task publisher is required when scanner is enabled"
        )

    replacement_storage_keys: list[str] = []
    replacement_cleanup = None
    notification_rows: list[dict[str, Any]] = []
    publication_outcome: PublicationOutcomeInput | None = None
    publication_notification_rows: list[dict[str, Any]] = []
    async with transaction_connection(engine) as connection:
        if request.replacement is not None:
            replacement_cleanup = await cleanup_replaceable_version(
                connection, request.replacement
            )
            replacement_storage_keys = replacement_cleanup.storage_keys
            if replacement_cleanup.archived_review is not None and (
                request.auto_publish or request.visibility == "PRIVATE"
            ):
                raise VersionReplacementConflict(
                    "Rejected version resubmission requires review"
                )

        prepared = await prepare_publish_db_records(
            connection,
            PublishDbPrepareInput(
                namespace_id=request.namespace_id,
                slug=request.slug,
                display_name=request.display_name,
                summary=request.summary,
                publisher_id=request.publisher_id,
                visibility=request.visibility,
                version=request.version,
                auto_publish=request.auto_publish,
                metadata=request.metadata,
                entries=request.entries,
                now=request.now,
            ),
        )
        if after_prepare is not None:
            await after_prepare(connection, prepared.skill_id, prepared.version_id)
        if request.storage is None:
            stored_package = write_local_package_objects(
                request.storage_base_path,
                prepared.skill_id,
                prepared.version_id,
                request.entries,
            )
        else:
            stored_package = write_package_objects(
                request.storage,
                prepared.skill_id,
                prepared.version_id,
                request.entries,
            )
        await finalize_publish_db_records(
            connection,
            PublishDbFinalizeInput(
                skill_id=prepared.skill_id,
                version_id=prepared.version_id,
                display_name=request.display_name,
                summary=request.summary,
                publisher_id=request.publisher_id,
                visibility=request.visibility,
                latest_version_updated=prepared.latest_version_updated,
                stored_package=stored_package,
                now=request.now,
            ),
        )
        side_effects = await apply_publish_side_effects(
            connection,
            PublishSideEffectInput(
                skill_id=prepared.skill_id,
                version_id=prepared.version_id,
                namespace_id=request.namespace_id,
                publisher_id=request.publisher_id,
                version_status=prepared.version_status,
                visibility=request.visibility,
                scanner_enabled=request.scanner_enabled,
                scan_mode=request.scan_mode,
                bundle_key=stored_package.bundle_key,
                request_id=request.request_id,
                client_ip=request.client_ip,
                user_agent=request.user_agent,
                compat_namespace=request.compat_namespace,
                compat_slug=request.compat_slug,
                now=request.now,
                task_id=request.task_id,
                submitter_id=request.resolved_submitter_id,
                actor_user_id=request.audit_actor_user_id,
                actor_service_principal_id=request.actor_service_principal_id,
            ),
        )
        if (
            replacement_cleanup is not None
            and replacement_cleanup.archived_review is not None
        ):
            if side_effects.review_task_id is None:
                raise ValueError(
                    "Rejected version resubmission must create a review task"
                )
            await archive_review_attempt(
                connection,
                ReviewAttemptArchiveInput(
                    attempt=replacement_cleanup.archived_review,
                    replacement_version_id=prepared.version_id,
                    replacement_review_task_id=side_effects.review_task_id,
                    actor_user_id=request.audit_actor_user_id,
                    actor_service_principal_id=request.actor_service_principal_id,
                    request_id=request.request_id,
                    client_ip=request.client_ip,
                    user_agent=request.user_agent,
                    archived_at=request.now,
                ),
            )
        if side_effects.review_task_id is not None:
            notification_rows = await write_review_submitted_notifications(
                connection,
                recipients=await read_review_submission_recipients(
                    connection,
                    namespace_id=request.namespace_id,
                ),
                review_task_id=side_effects.review_task_id,
                skill_id=prepared.skill_id,
                version_id=prepared.version_id,
                submitter_id=request.resolved_submitter_id,
                namespace=request.namespace_slug,
                slug=request.slug,
                skill_name=request.display_name,
                version=request.version,
                created_at=request.now or datetime.now(UTC),
            )
        if after_publish is not None:
            await after_publish(connection, prepared.skill_id, prepared.version_id)
        if prepared.version_status == "PUBLISHED":
            publication_outcome = PublicationOutcomeInput(
                skill_id=prepared.skill_id,
                version_id=prepared.version_id,
                publisher_id=request.publisher_id,
                created_at=request.now or datetime.now(UTC),
            )
            publication_notification_rows = await publication_outcome_writer(
                connection,
                publication_outcome,
            )
        elif prepared.latest_version_updated:
            await upsert_skill_search_document(connection, prepared.skill_id)

    if publication_outcome is not None:
        await publication_notification_publisher(
            notification_fanout,
            publication_notification_rows,
            publication_outcome,
        )

    scan_task_publish_error: Exception | None = None
    if side_effects.scan_task is not None and scan_task_publisher is not None:
        try:
            await scan_task_publisher.publish_scan_task(side_effects.scan_task)
        except Exception as publish_error:  # noqa: BLE001
            # Publisher implementations can surface transport-specific errors.
            scan_task_publish_error = publish_error
            try:
                async with transaction_connection(engine) as connection:
                    await mark_scan_task_failed(
                        connection,
                        version_id=side_effects.scan_task.version_id,
                        scanner_type=side_effects.scan_task.metadata.get(
                            "scannerType", "skill-scanner"
                        ),
                        failure_code="SCAN_TASK_PUBLISH_FAILED",
                    )
            except Exception as compensation_error:  # noqa: BLE001
                # Keep the Redis publication failure as the primary exception.
                publish_error.add_note(
                    "Scan task publish compensation failed: "
                    f"{compensation_error!r}"
                )
    if scan_task_publish_error is None:
        await publish_review_notifications(notification_fanout, notification_rows)

    replacement_deleted_keys: list[str] = []
    replacement_compensation_recorded = False
    if request.replacement is not None and replacement_storage_keys:
        try:
            async with transaction_connection(engine) as connection:
                delete_result = (
                    await delete_local_storage_objects_or_record_compensation(
                        connection,
                        request.storage_base_path,
                        StorageDeleteCompensationInput(
                            skill_id=request.replacement.skill_id,
                            namespace=request.replacement.namespace,
                            slug=request.replacement.slug,
                            storage_keys=replacement_storage_keys,
                            last_error=None,
                            now=request.now,
                        ),
                    )
                )
            replacement_deleted_keys = delete_result.deleted_keys
            replacement_compensation_recorded = (
                delete_result.compensation_recorded
            )
        except Exception as replacement_cleanup_error:
            if scan_task_publish_error is None:
                raise
            # Cleanup failure must not replace the Redis publication failure.
            scan_task_publish_error.add_note(
                "Replacement storage cleanup failed: "
                f"{replacement_cleanup_error!r}"
            )

    if scan_task_publish_error is not None:
        raise scan_task_publish_error

    return PublishWriteResult(
        skill_id=prepared.skill_id,
        version_id=prepared.version_id,
        version_status=prepared.version_status,
        latest_version_updated=prepared.latest_version_updated,
        stored_package=stored_package,
        side_effects=side_effects,
        replacement_deleted_keys=replacement_deleted_keys,
        replacement_compensation_recorded=replacement_compensation_recorded,
    )

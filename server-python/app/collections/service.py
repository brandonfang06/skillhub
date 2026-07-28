from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import total_ordering
from typing import Any, Awaitable, Callable

from sqlalchemy.exc import IntegrityError

from app.audit.writer import write_audit_log
from app.collections.access import require_collection_curator
from app.collections.contracts import (
    CollectionDraftReplaceRequest,
    CollectionPublishRequest,
    CollectionStatusRequest,
)
from app.collections.mutation_repository import (
    CollectionMutationRepository,
    collection_mutation_repository,
)


AuditWriter = Callable[..., Awaitable[None]]
COLLECTION_SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
SEMANTIC_VERSION_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


class CollectionMutationError(ValueError):
    def __init__(self, detail: str, *, status_code: int = 400) -> None:
        super().__init__(detail)
        self.status_code = status_code


@dataclass(frozen=True)
class MutationContext:
    actor_user_id: str
    platform_roles: list[str]
    request_id: str | None
    client_ip: str | None
    user_agent: str | None


@total_ordering
@dataclass(frozen=True)
class SemanticVersion:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...]

    @classmethod
    def parse(cls, value: str) -> "SemanticVersion":
        match = SEMANTIC_VERSION_PATTERN.fullmatch(value.strip())
        if match is None:
            raise CollectionMutationError("error.collection.version.invalid")
        prerelease = tuple(match.group(4).split(".")) if match.group(4) else ()
        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
            prerelease=prerelease,
        )

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        base = (self.major, self.minor, self.patch)
        other_base = (other.major, other.minor, other.patch)
        if base != other_base:
            return base < other_base
        if not self.prerelease:
            return False
        if not other.prerelease:
            return True
        for left, right in zip(self.prerelease, other.prerelease, strict=False):
            if left == right:
                continue
            left_numeric = left.isdigit()
            right_numeric = right.isdigit()
            if left_numeric and right_numeric:
                return int(left) < int(right)
            if left_numeric != right_numeric:
                return left_numeric
            return left < right
        return len(self.prerelease) < len(other.prerelease)


def _validate_collection_slug(value: str) -> str:
    normalized = value.strip()
    if (
        len(normalized) > 128
        or COLLECTION_SLUG_PATTERN.fullmatch(normalized) is None
        or "--" in normalized
    ):
        raise CollectionMutationError("error.collection.slug.invalid")
    return normalized


def _validate_metadata(display_name: str, summary: str) -> tuple[str, str]:
    normalized_name = display_name.strip()
    normalized_summary = summary.strip()
    if not normalized_name or len(normalized_name) > 256:
        raise CollectionMutationError("error.collection.displayName.invalid")
    if not normalized_summary or len(normalized_summary) > 2000:
        raise CollectionMutationError("error.collection.summary.invalid")
    return normalized_name, normalized_summary


def _validate_idempotency_key(value: str | None) -> str:
    if value is None or not value.strip() or len(value.strip()) > 64:
        raise CollectionMutationError("error.collection.idempotency.required")
    return value.strip()


async def _read_authorized_namespace(
    repository: CollectionMutationRepository,
    connection: Any,
    *,
    namespace: str,
    context: MutationContext,
) -> dict[str, Any]:
    row = await repository.read_namespace_for_update(
        connection,
        namespace=namespace,
        actor_user_id=context.actor_user_id,
    )
    if row is None:
        raise CollectionMutationError("error.collection.notFound", status_code=404)
    require_collection_curator(
        namespace_type=str(row["type"]),
        namespace_status=str(row["status"]),
        namespace_role=row.get("namespace_role"),
        platform_roles=context.platform_roles,
    )
    return row


async def _read_collection(
    repository: CollectionMutationRepository,
    connection: Any,
    *,
    namespace_id: int,
    collection: str,
) -> dict[str, Any]:
    row = await repository.read_collection_for_update(
        connection,
        namespace_id=namespace_id,
        collection=collection,
    )
    if row is None:
        raise CollectionMutationError("error.collection.notFound", status_code=404)
    return row


def _assert_collection_writable(collection: dict[str, Any]) -> None:
    if str(collection["status"]) != "ACTIVE" or bool(collection["hidden"]):
        raise CollectionMutationError("error.collection.lifecycle.conflict", status_code=409)


async def _write_collection_audit(
    audit_writer: AuditWriter,
    connection: Any,
    *,
    context: MutationContext,
    action: str,
    collection_id: int,
    detail: dict[str, Any],
) -> None:
    await audit_writer(
        connection,
        actor_user_id=context.actor_user_id,
        action=action,
        target_type="COLLECTION",
        target_id=collection_id,
        request_id=context.request_id,
        client_ip=context.client_ip,
        user_agent=context.user_agent,
        detail=detail,
        created_at=datetime.now(UTC),
    )


async def _prepare_idempotency(
    repository: CollectionMutationRepository,
    connection: Any,
    *,
    idempotency_key: str,
    resource_type: str,
) -> dict[str, Any] | None:
    await repository.delete_expired_idempotency(connection, idempotency_key)
    existing = await repository.read_idempotency(connection, idempotency_key)
    if existing is not None:
        return existing
    reserved = await repository.reserve_idempotency(
        connection,
        idempotency_key=idempotency_key,
        resource_type=resource_type,
    )
    if reserved:
        return None
    return await repository.read_idempotency(connection, idempotency_key)


def _completed_idempotency_resource(
    record: dict[str, Any],
    *,
    resource_type: str,
) -> int:
    if (
        str(record.get("resource_type")) != resource_type
        or str(record.get("status")) != "COMPLETED"
        or record.get("resource_id") is None
    ):
        raise CollectionMutationError(
            "error.collection.idempotency.conflict",
            status_code=409,
        )
    return int(record["resource_id"])


def _collection_result(row: dict[str, Any], namespace: str) -> dict[str, Any]:
    return {
        "collectionId": int(row["id"]),
        "namespace": namespace,
        "slug": str(row["slug"]),
        "status": str(row["status"]),
    }


async def create_collection(
    engine: Any,
    *,
    namespace: str,
    slug: str,
    display_name: str,
    summary: str,
    idempotency_key: str | None,
    context: MutationContext,
    repository: CollectionMutationRepository = collection_mutation_repository,
    audit_writer: AuditWriter = write_audit_log,
) -> dict[str, Any]:
    normalized_slug = _validate_collection_slug(slug)
    normalized_name, normalized_summary = _validate_metadata(display_name, summary)
    key = _validate_idempotency_key(idempotency_key)
    try:
        async with engine.begin() as connection:
            namespace_row = await _read_authorized_namespace(
                repository,
                connection,
                namespace=namespace,
                context=context,
            )
            idempotency = await _prepare_idempotency(
                repository,
                connection,
                idempotency_key=key,
                resource_type="COLLECTION_CREATE",
            )
            if idempotency is not None:
                collection_id = _completed_idempotency_resource(
                    idempotency,
                    resource_type="COLLECTION_CREATE",
                )
                existing = await repository.read_collection_by_id(connection, collection_id)
                if (
                    existing is None
                    or int(existing["namespace_id"]) != int(namespace_row["id"])
                    or str(existing["slug"]) != normalized_slug
                ):
                    raise CollectionMutationError(
                        "error.collection.idempotency.conflict",
                        status_code=409,
                    )
                return _collection_result(existing, namespace)

            existing = await repository.read_collection_for_update(
                connection,
                namespace_id=int(namespace_row["id"]),
                collection=normalized_slug,
            )
            if existing is not None:
                raise CollectionMutationError("error.collection.exists", status_code=409)
            created = await repository.insert_collection(
                connection,
                namespace_id=int(namespace_row["id"]),
                slug=normalized_slug,
                display_name=normalized_name,
                summary=normalized_summary,
                actor_user_id=context.actor_user_id,
            )
            await _write_collection_audit(
                audit_writer,
                connection,
                context=context,
                action="COLLECTION_CREATE",
                collection_id=int(created["id"]),
                detail={"namespace": namespace, "slug": normalized_slug},
            )
            await repository.complete_idempotency(
                connection,
                idempotency_key=key,
                resource_id=int(created["id"]),
            )
            return _collection_result(created, namespace)
    except IntegrityError as exc:
        raise CollectionMutationError("error.collection.exists", status_code=409) from exc


async def create_collection_draft(
    engine: Any,
    *,
    namespace: str,
    collection: str,
    context: MutationContext,
    repository: CollectionMutationRepository = collection_mutation_repository,
    audit_writer: AuditWriter = write_audit_log,
) -> dict[str, Any]:
    normalized_collection = _validate_collection_slug(collection)
    async with engine.begin() as connection:
        namespace_row = await _read_authorized_namespace(
            repository,
            connection,
            namespace=namespace,
            context=context,
        )
        collection_row = await _read_collection(
            repository,
            connection,
            namespace_id=int(namespace_row["id"]),
            collection=normalized_collection,
        )
        _assert_collection_writable(collection_row)
        if await repository.read_draft_for_update(connection, int(collection_row["id"])) is not None:
            raise CollectionMutationError("error.collection.draft.exists", status_code=409)
        draft = await repository.insert_draft(
            connection,
            collection_id=int(collection_row["id"]),
            actor_user_id=context.actor_user_id,
        )
        source_version_id = collection_row.get("latest_published_version_id")
        if source_version_id is not None:
            await repository.clone_members(
                connection,
                source_version_id=int(source_version_id),
                target_version_id=int(draft["id"]),
            )
        await _write_collection_audit(
            audit_writer,
            connection,
            context=context,
            action="COLLECTION_DRAFT_CREATE",
            collection_id=int(collection_row["id"]),
            detail={
                "draftRevision": int(draft["draft_revision"]),
                "sourceVersionId": int(source_version_id) if source_version_id is not None else None,
            },
        )
        return {
            "collectionId": int(collection_row["id"]),
            "versionId": int(draft["id"]),
            "draftRevision": int(draft["draft_revision"]),
        }


def _validate_draft_members(payload: CollectionDraftReplaceRequest) -> None:
    seen_skill_ids: set[int] = set()
    seen_positions: set[int] = set()
    for member in payload.members:
        if member.skill_id <= 0 or member.skill_version_id <= 0:
            raise CollectionMutationError("error.collection.member.invalid")
        if (
            member.position < 0
            or member.position in seen_positions
            or member.skill_id in seen_skill_ids
        ):
            raise CollectionMutationError("error.collection.member.duplicate")
        if member.note is not None and len(member.note) > 500:
            raise CollectionMutationError("error.collection.member.invalid")
        seen_skill_ids.add(member.skill_id)
        seen_positions.add(member.position)


async def replace_collection_draft(
    engine: Any,
    *,
    namespace: str,
    collection: str,
    payload: CollectionDraftReplaceRequest,
    expected_revision: int,
    context: MutationContext,
    repository: CollectionMutationRepository = collection_mutation_repository,
    audit_writer: AuditWriter = write_audit_log,
) -> dict[str, Any]:
    if expected_revision <= 0:
        raise CollectionMutationError("error.collection.draft.ifMatch.required")
    normalized_collection = _validate_collection_slug(collection)
    normalized_name, normalized_summary = _validate_metadata(payload.display_name, payload.summary)
    _validate_draft_members(payload)
    async with engine.begin() as connection:
        namespace_row = await _read_authorized_namespace(
            repository,
            connection,
            namespace=namespace,
            context=context,
        )
        collection_row = await _read_collection(
            repository,
            connection,
            namespace_id=int(namespace_row["id"]),
            collection=normalized_collection,
        )
        _assert_collection_writable(collection_row)
        draft = await repository.read_draft_for_update(connection, int(collection_row["id"]))
        if draft is None:
            raise CollectionMutationError("error.collection.draft.notFound", status_code=404)
        if int(draft["draft_revision"]) != expected_revision:
            raise CollectionMutationError("error.collection.draft.stale", status_code=409)

        references = []
        for member in payload.members:
            reference = await repository.read_skill_version_reference(
                connection,
                namespace_id=int(namespace_row["id"]),
                skill_id=member.skill_id,
                skill_version_id=member.skill_version_id,
            )
            if reference is None:
                raise CollectionMutationError("error.collection.member.notFound")
            references.append((member, reference))

        await repository.update_collection_metadata(
            connection,
            collection_id=int(collection_row["id"]),
            display_name=normalized_name,
            summary=normalized_summary,
            actor_user_id=context.actor_user_id,
        )
        await repository.delete_draft_members(connection, int(draft["id"]))
        for member, reference in references:
            await repository.insert_draft_member(
                connection,
                draft_id=int(draft["id"]),
                skill_id=int(reference["skill_id"]),
                skill_version_id=int(reference["skill_version_id"]),
                skill_slug_snapshot=str(reference["skill_slug_snapshot"]),
                skill_version_snapshot=str(reference["skill_version_snapshot"]),
                skill_owner_id_snapshot=str(reference["skill_owner_id_snapshot"]),
                skill_visibility_snapshot=str(
                    reference["skill_visibility_snapshot"]
                ),
                position=member.position,
                note=member.note,
            )
        updated = await repository.increment_draft_revision(
            connection,
            draft_id=int(draft["id"]),
            expected_revision=expected_revision,
            release_notes=payload.release_notes,
        )
        if updated is None:
            raise CollectionMutationError("error.collection.draft.stale", status_code=409)
        await _write_collection_audit(
            audit_writer,
            connection,
            context=context,
            action="COLLECTION_DRAFT_UPDATE",
            collection_id=int(collection_row["id"]),
            detail={
                "draftRevision": int(updated["draft_revision"]),
                "memberCount": len(references),
            },
        )
        return {
            "collectionId": int(collection_row["id"]),
            "versionId": int(updated["id"]),
            "draftRevision": int(updated["draft_revision"]),
        }


async def delete_collection_draft(
    engine: Any,
    *,
    namespace: str,
    collection: str,
    context: MutationContext,
    repository: CollectionMutationRepository = collection_mutation_repository,
    audit_writer: AuditWriter = write_audit_log,
) -> dict[str, Any]:
    normalized_collection = _validate_collection_slug(collection)
    async with engine.begin() as connection:
        namespace_row = await _read_authorized_namespace(
            repository,
            connection,
            namespace=namespace,
            context=context,
        )
        collection_row = await _read_collection(
            repository,
            connection,
            namespace_id=int(namespace_row["id"]),
            collection=normalized_collection,
        )
        _assert_collection_writable(collection_row)
        draft = await repository.read_draft_for_update(connection, int(collection_row["id"]))
        if draft is None:
            raise CollectionMutationError("error.collection.draft.notFound", status_code=404)
        await repository.delete_draft_members(connection, int(draft["id"]))
        if not await repository.delete_draft(connection, int(draft["id"])):
            raise CollectionMutationError("error.collection.draft.notFound", status_code=404)
        await _write_collection_audit(
            audit_writer,
            connection,
            context=context,
            action="COLLECTION_DRAFT_DELETE",
            collection_id=int(collection_row["id"]),
            detail={"draftRevision": int(draft["draft_revision"])},
        )
        return {"deleted": True}


def _validate_publish_members(
    members: list[dict[str, Any]],
    *,
    namespace_id: int,
) -> None:
    if not members:
        raise CollectionMutationError("error.collection.member.required")
    seen_skills: set[int] = set()
    seen_positions: set[int] = set()
    for member in members:
        if (
            member.get("skill_id") is None
            or member.get("skill_version_id") is None
            or member.get("namespace_id") is None
            or member.get("version_skill_id") is None
        ):
            raise CollectionMutationError("error.collection.member.invalid")
        skill_id = int(member["skill_id"])
        position = int(member["position"])
        if skill_id in seen_skills or position in seen_positions:
            raise CollectionMutationError("error.collection.member.duplicate")
        if (
            int(member["namespace_id"]) != namespace_id
            or int(member["version_skill_id"]) != skill_id
            or str(member["skill_status"]) != "ACTIVE"
            or bool(member["skill_hidden"])
            or str(member["version_status"]) != "PUBLISHED"
            or not bool(member["download_ready"])
            or member.get("yanked_at") is not None
        ):
            raise CollectionMutationError("error.collection.member.invalid")
        seen_skills.add(skill_id)
        seen_positions.add(position)


async def publish_collection(
    engine: Any,
    *,
    namespace: str,
    collection: str,
    payload: CollectionPublishRequest,
    idempotency_key: str | None,
    context: MutationContext,
    repository: CollectionMutationRepository = collection_mutation_repository,
    audit_writer: AuditWriter = write_audit_log,
) -> dict[str, Any]:
    normalized_collection = _validate_collection_slug(collection)
    version_value = payload.version.strip()
    requested_version = SemanticVersion.parse(version_value)
    if payload.draft_revision <= 0:
        raise CollectionMutationError("error.collection.draft.stale", status_code=409)
    key = _validate_idempotency_key(idempotency_key)
    async with engine.begin() as connection:
        namespace_row = await _read_authorized_namespace(
            repository,
            connection,
            namespace=namespace,
            context=context,
        )
        collection_row = await _read_collection(
            repository,
            connection,
            namespace_id=int(namespace_row["id"]),
            collection=normalized_collection,
        )
        idempotency = await _prepare_idempotency(
            repository,
            connection,
            idempotency_key=key,
            resource_type="COLLECTION_PUBLISH",
        )
        if idempotency is not None:
            version_id = _completed_idempotency_resource(
                idempotency,
                resource_type="COLLECTION_PUBLISH",
            )
            published = await repository.read_published_version_by_id(connection, version_id)
            if (
                published is None
                or int(published["collection_id"]) != int(collection_row["id"])
                or str(published["version"]) != version_value
            ):
                raise CollectionMutationError(
                    "error.collection.idempotency.conflict",
                    status_code=409,
                )
            return {
                "collectionId": int(collection_row["id"]),
                "versionId": int(published["id"]),
                "version": str(published["version"]),
            }

        _assert_collection_writable(collection_row)
        draft = await repository.read_draft_for_update(connection, int(collection_row["id"]))
        if draft is None:
            raise CollectionMutationError("error.collection.draft.notFound", status_code=404)
        if int(draft["draft_revision"]) != payload.draft_revision:
            raise CollectionMutationError("error.collection.draft.stale", status_code=409)
        members = await repository.read_draft_members_for_publish(connection, int(draft["id"]))
        _validate_publish_members(members, namespace_id=int(namespace_row["id"]))

        latest_version_id = collection_row.get("latest_published_version_id")
        if latest_version_id is not None:
            latest = await repository.read_latest_version_for_update(
                connection,
                int(latest_version_id),
            )
            if latest is None or str(latest["status"]) != "PUBLISHED":
                raise CollectionMutationError(
                    "error.collection.lifecycle.conflict",
                    status_code=409,
                )
            if requested_version <= SemanticVersion.parse(str(latest["version"])):
                raise CollectionMutationError("error.collection.version.notGreater")

        published = await repository.publish_draft(
            connection,
            draft_id=int(draft["id"]),
            expected_revision=payload.draft_revision,
            version=version_value,
            actor_user_id=context.actor_user_id,
        )
        if published is None:
            raise CollectionMutationError("error.collection.draft.stale", status_code=409)
        await repository.update_latest_published_version(
            connection,
            collection_id=int(collection_row["id"]),
            version_id=int(published["id"]),
            actor_user_id=context.actor_user_id,
        )
        await _write_collection_audit(
            audit_writer,
            connection,
            context=context,
            action="COLLECTION_PUBLISH",
            collection_id=int(collection_row["id"]),
            detail={
                "version": version_value,
                "draftRevision": payload.draft_revision,
                "memberCount": len(members),
            },
        )
        await repository.complete_idempotency(
            connection,
            idempotency_key=key,
            resource_id=int(published["id"]),
        )
        return {
            "collectionId": int(collection_row["id"]),
            "versionId": int(published["id"]),
            "version": str(published["version"]),
        }


async def set_collection_status(
    engine: Any,
    *,
    namespace: str,
    collection: str,
    payload: CollectionStatusRequest,
    context: MutationContext,
    repository: CollectionMutationRepository = collection_mutation_repository,
    audit_writer: AuditWriter = write_audit_log,
) -> dict[str, Any]:
    normalized_collection = _validate_collection_slug(collection)
    if payload.reason is not None and len(payload.reason) > 1000:
        raise CollectionMutationError("error.collection.status.reason.invalid")
    async with engine.begin() as connection:
        namespace_row = await _read_authorized_namespace(
            repository,
            connection,
            namespace=namespace,
            context=context,
        )
        collection_row = await _read_collection(
            repository,
            connection,
            namespace_id=int(namespace_row["id"]),
            collection=normalized_collection,
        )
        target_status = payload.status
        current_status = str(collection_row["status"])
        if current_status == target_status:
            raise CollectionMutationError(
                "error.collection.lifecycle.conflict",
                status_code=409,
            )
        if (current_status, target_status) not in {
            ("ACTIVE", "ARCHIVED"),
            ("ARCHIVED", "ACTIVE"),
        }:
            raise CollectionMutationError(
                "error.collection.lifecycle.conflict",
                status_code=409,
            )
        updated = await repository.update_collection_status(
            connection,
            collection_id=int(collection_row["id"]),
            status=target_status,
            actor_user_id=context.actor_user_id,
        )
        action = "COLLECTION_ARCHIVE" if target_status == "ARCHIVED" else "COLLECTION_RESTORE"
        await _write_collection_audit(
            audit_writer,
            connection,
            context=context,
            action=action,
            collection_id=int(collection_row["id"]),
            detail={"status": target_status, "reason": payload.reason},
        )
        return _collection_result(updated, namespace)

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from app.publish.auto_withdraw import auto_withdraw_pending_review_versions
from app.publish.package import PackageEntry, SkillMetadata
from app.publish.storage import StoredPackageResult


@dataclass(frozen=True)
class PublishDbTransactionInput:
    namespace_id: int
    slug: str
    display_name: str
    summary: str
    publisher_id: str
    visibility: str
    version: str
    auto_publish: bool
    metadata: SkillMetadata
    entries: list[PackageEntry]
    stored_package: StoredPackageResult
    now: datetime | None = None


@dataclass(frozen=True)
class PublishDbPrepareInput:
    namespace_id: int
    slug: str
    display_name: str
    summary: str
    publisher_id: str
    visibility: str
    version: str
    auto_publish: bool
    metadata: SkillMetadata
    entries: list[PackageEntry]
    now: datetime | None = None


@dataclass(frozen=True)
class PublishDbPrepareResult:
    skill_id: int
    version_id: int
    version_status: str
    latest_version_updated: bool


@dataclass(frozen=True)
class PublishDbFinalizeInput:
    skill_id: int
    version_id: int
    display_name: str
    summary: str
    publisher_id: str
    visibility: str
    latest_version_updated: bool
    stored_package: StoredPackageResult
    now: datetime | None = None


@dataclass(frozen=True)
class PublishDbTransactionResult:
    skill_id: int
    version_id: int
    version_status: str
    latest_version_updated: bool
    file_count: int
    total_size: int


def determine_initial_version_status(*, auto_publish: bool, visibility: str) -> str:
    if auto_publish:
        return "PUBLISHED"
    if visibility == "PRIVATE":
        return "UPLOADED"
    return "PENDING_REVIEW"


def build_manifest_json(entries: list[PackageEntry]) -> list[dict[str, object]]:
    return [
        {
            "path": entry.path,
            "size": entry.size,
            "contentType": entry.content_type,
        }
        for entry in entries
    ]


def build_parsed_metadata_json(metadata: SkillMetadata) -> dict[str, object]:
    if metadata.frontmatter:
        return metadata.frontmatter
    payload: dict[str, object] = {
        "name": metadata.name,
        "description": metadata.description,
    }
    if metadata.version is not None:
        payload["version"] = metadata.version
    return payload


def encode_jsonb(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


async def create_publish_db_records(engine: Any, request: PublishDbTransactionInput) -> PublishDbTransactionResult:
    async with engine.begin() as connection:
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
                stored_package=request.stored_package,
                now=request.now,
            ),
        )

    return PublishDbTransactionResult(
        skill_id=prepared.skill_id,
        version_id=prepared.version_id,
        version_status=prepared.version_status,
        latest_version_updated=prepared.latest_version_updated,
        file_count=request.stored_package.file_count,
        total_size=request.stored_package.total_size,
    )


async def prepare_publish_db_records(connection: Any, request: PublishDbPrepareInput) -> PublishDbPrepareResult:
    version_status = determine_initial_version_status(
        auto_publish=request.auto_publish,
        visibility=request.visibility,
    )
    now = normalized_now(request.now)
    published_at = now if version_status in {"PUBLISHED", "UPLOADED"} else None
    latest_version_updated = version_status in {"PUBLISHED", "UPLOADED"}

    existing_skill = (
        await connection.execute(
            text(
                """
                SELECT id, status
                FROM skill
                WHERE namespace_id = :namespace_id
                  AND slug = :slug
                  AND owner_id = :publisher_id
                LIMIT 1
                """
            ),
            {
                "namespace_id": request.namespace_id,
                "slug": request.slug,
                "publisher_id": request.publisher_id,
            },
        )
    ).mappings().one_or_none()

    if existing_skill is not None:
        skill_id = int(existing_skill["id"])
        if str(existing_skill["status"]) == "ARCHIVED":
            raise ValueError(f"Cannot publish to archived skill: {request.slug}")
        await auto_withdraw_pending_review_versions(
            connection,
            skill_id=skill_id,
        )
    else:
        inserted_skill = (
            await connection.execute(
                text(
                    """
                    INSERT INTO skill (
                        namespace_id, slug, display_name, summary, owner_id, visibility, status,
                        created_by, created_at, updated_by, updated_at
                    )
                    VALUES (
                        :namespace_id, :slug, :display_name, :summary, :publisher_id, :visibility, 'ACTIVE',
                        :publisher_id, :now, :publisher_id, :now
                    )
                    RETURNING id, status
                    """
                ),
                {
                    "namespace_id": request.namespace_id,
                    "slug": request.slug,
                    "display_name": request.display_name,
                    "summary": request.summary,
                    "publisher_id": request.publisher_id,
                    "visibility": request.visibility,
                    "now": now,
                },
            )
        ).mappings().one_or_none()
        if inserted_skill is None:
            raise ValueError("Failed to create skill")
        skill_id = int(inserted_skill["id"])

    version_id = int(
        (
            await connection.execute(
                text(
                    """
                    INSERT INTO skill_version (
                        skill_id, version, status, parsed_metadata_json, manifest_json,
                        file_count, total_size, published_at, created_by, created_at,
                        bundle_ready, download_ready, requested_visibility
                    )
                    VALUES (
                        :skill_id, :version, :status, :parsed_metadata_json, :manifest_json,
                        0, 0, :published_at, :publisher_id, :now,
                        FALSE, FALSE, :visibility
                    )
                    RETURNING id
                    """
                ),
                {
                    "skill_id": skill_id,
                    "version": request.version,
                    "status": version_status,
                    "parsed_metadata_json": encode_jsonb(build_parsed_metadata_json(request.metadata)),
                    "manifest_json": encode_jsonb(build_manifest_json(request.entries)),
                    "published_at": published_at,
                    "publisher_id": request.publisher_id,
                    "now": now,
                    "visibility": request.visibility,
                },
            )
        ).scalar_one()
    )

    return PublishDbPrepareResult(
        skill_id=skill_id,
        version_id=version_id,
        version_status=version_status,
        latest_version_updated=latest_version_updated,
    )


async def finalize_publish_db_records(connection: Any, request: PublishDbFinalizeInput) -> None:
    now = normalized_now(request.now)

    for file_record in request.stored_package.files:
        await connection.execute(
            text(
                """
                INSERT INTO skill_file (
                    version_id, file_path, file_size, content_type, sha256, storage_key, created_at
                )
                VALUES (
                    :version_id, :file_path, :file_size, :content_type, :sha256, :storage_key, :now
                )
                """
            ),
            {
                "version_id": request.version_id,
                "file_path": file_record.file_path,
                "file_size": file_record.file_size,
                "content_type": file_record.content_type,
                "sha256": file_record.sha256,
                "storage_key": file_record.storage_key,
                "now": now,
            },
        )

    await connection.execute(
        text(
            """
            UPDATE skill_version
            SET file_count = :file_count,
                total_size = :total_size,
                bundle_ready = :bundle_ready,
                download_ready = :download_ready
            WHERE id = :version_id
            """
        ),
        {
            "version_id": request.version_id,
            "file_count": request.stored_package.file_count,
            "total_size": request.stored_package.total_size,
            "bundle_ready": request.stored_package.bundle_ready,
            "download_ready": request.stored_package.download_ready,
        },
    )

    skill_update_params: dict[str, object] = {
        "skill_id": request.skill_id,
        "display_name": request.display_name,
        "summary": request.summary,
        "updated_by": request.publisher_id,
        "updated_at": now,
    }
    if request.latest_version_updated:
        skill_update_params["latest_version_id"] = request.version_id
        skill_update_params["visibility"] = request.visibility
        update_skill_sql = """
            UPDATE skill
            SET display_name = :display_name,
                summary = :summary,
                latest_version_id = :latest_version_id,
                visibility = :visibility,
                updated_by = :updated_by,
                updated_at = :updated_at
            WHERE id = :skill_id
        """
    else:
        update_skill_sql = """
            UPDATE skill
            SET display_name = :display_name,
                summary = :summary,
                updated_by = :updated_by,
                updated_at = :updated_at
            WHERE id = :skill_id
        """
    await connection.execute(text(update_skill_sql), skill_update_params)


def normalized_now(value: datetime | None) -> datetime:
    now = value or datetime.now(tz=UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text


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
class ReplacementCleanupResult:
    storage_keys: list[str]


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


async def cleanup_replaceable_version(connection: Any, version: ReplaceableVersion) -> ReplacementCleanupResult:
    if version.status == "PUBLISHED":
        raise ValueError(f"Version already published: {version.version}")

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
              AND status = 'PENDING'
            """
        ),
        {"version_id": version.version_id},
    )

    file_rows = (
        await connection.execute(
            text(
                """
                SELECT storage_key
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

    return ReplacementCleanupResult(storage_keys=storage_keys)


def delete_local_storage_objects(storage_base_path: str, storage_keys: list[str]) -> list[str]:
    base = Path(storage_base_path).resolve()
    deleted: list[str] = []
    for key in storage_keys:
        target = (base / key).resolve()
        try:
            target.relative_to(base)
        except ValueError as exc:
            raise ValueError(f"Object key escapes storage base: {key}") from exc

        if target.exists():
            target.unlink()
            deleted.append(key)
    return deleted


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

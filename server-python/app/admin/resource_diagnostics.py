from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.object_storage import ObjectStorage, object_storage_for_base_path
from app.skills.read_files import bundle_storage_key


MAX_FILE_OBJECT_PROBES = 500


class AdminResourceDiagnosticError(RuntimeError):
    def __init__(self, detail: str, *, status_code: int = 400) -> None:
        super().__init__(detail)
        self.status_code = status_code


async def _object_exists(storage: ObjectStorage, key: str) -> bool:
    return await asyncio.to_thread(storage.exists, key)


async def read_skill_resource_diagnostics(
    engine: AsyncEngine,
    storage_base_path: str,
    skill_id: int,
    *,
    storage: ObjectStorage | None = None,
) -> dict[str, object]:
    async with engine.connect() as connection:
        skill = (
            await connection.execute(
                text(
                    """
                    SELECT s.id AS skill_id,
                           s.slug,
                           s.latest_version_id,
                           n.slug AS namespace,
                           n.status AS namespace_status
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE s.id = :skill_id
                    LIMIT 1
                    """
                ),
                {"skill_id": skill_id},
            )
        ).mappings().one_or_none()
        if skill is None:
            raise AdminResourceDiagnosticError("error.skill.notFound", status_code=404)

        versions = (
            await connection.execute(
                text(
                    """
                    SELECT id, version, status, file_count
                    FROM skill_version
                    WHERE skill_id = :skill_id
                    ORDER BY id ASC
                    """
                ),
                {"skill_id": skill_id},
            )
        ).mappings().all()
        files = (
            await connection.execute(
                text(
                    """
                    SELECT version_id, file_path, storage_key
                    FROM skill_file
                    WHERE version_id = ANY(CAST(:version_ids AS bigint[]))
                    ORDER BY version_id ASC, file_path ASC
                    """
                ),
                {"version_ids": [int(row["id"]) for row in versions]},
            )
        ).mappings().all() if versions else []

    files_by_version: dict[int, int] = {}
    valid_file_objects: list[tuple[str, str]] = []
    blank_storage_key_count = 0
    for row in files:
        version_id = int(row["version_id"])
        files_by_version[version_id] = files_by_version.get(version_id, 0) + 1
        storage_key = row.get("storage_key")
        if storage_key is None or not str(storage_key).strip():
            blank_storage_key_count += 1
            continue
        valid_file_objects.append((str(row["file_path"]), str(storage_key)))

    latest_version_id = int(skill["latest_version_id"]) if skill.get("latest_version_id") is not None else None
    versions_without_files = [
        int(row["id"])
        for row in versions
        if files_by_version.get(int(row["id"]), 0) == 0
    ]
    missing_db_files = bool(versions_without_files)
    checked_file_objects = valid_file_objects[:MAX_FILE_OBJECT_PROBES]
    unchecked_file_object_count = max(0, len(valid_file_objects) - len(checked_file_objects))
    bundle_objects = [
        (False, f"bundle:{row['version']}", bundle_storage_key(skill_id, int(row["id"])))
        for row in versions
    ]
    file_objects = [(True, label, key) for label, key in checked_file_objects]

    selected_storage = storage or object_storage_for_base_path(storage_base_path)
    missing_objects: list[dict[str, str]] = []
    checked_object_count = 0
    checked_file_object_count = 0
    storage_probe_error: dict[str, str] | None = None
    for is_file, label, key in [*bundle_objects, *file_objects]:
        try:
            exists = await _object_exists(selected_storage, key)
        except Exception:
            storage_probe_error = {"code": "STORAGE_PROBE_FAILED"}
            break
        checked_object_count += 1
        if is_file:
            checked_file_object_count += 1
        if not exists:
            missing_objects.append({"path": label, "storageKey": key})

    known_issue = missing_db_files or blank_storage_key_count > 0 or bool(missing_objects)
    if storage_probe_error is not None:
        diagnostic_status = "PARTIAL" if known_issue else "UNVERIFIED"
    elif missing_db_files:
        diagnostic_status = "MISSING_DB_FILES"
    elif blank_storage_key_count:
        diagnostic_status = "MISSING_STORAGE_KEYS"
    elif missing_objects:
        diagnostic_status = "MISSING_OBJECTS"
    elif unchecked_file_object_count:
        diagnostic_status = "PARTIAL"
    else:
        diagnostic_status = "HEALTHY"

    return {
        "skillId": int(skill["skill_id"]),
        "namespace": str(skill["namespace"]),
        "slug": str(skill["slug"]),
        "namespaceStatus": str(skill["namespace_status"]),
        "latestVersionId": latest_version_id,
        "versionCount": len(versions),
        "fileCount": len(files),
        "versionsWithoutFiles": versions_without_files,
        "blankStorageKeyCount": blank_storage_key_count,
        "checkedObjectCount": checked_object_count,
        "checkedFileObjectCount": checked_file_object_count,
        "uncheckedFileObjectCount": unchecked_file_object_count,
        "missingObjects": missing_objects,
        "storageProbeError": storage_probe_error,
        "diagnosticStatus": diagnostic_status,
    }


__all__ = [
    "AdminResourceDiagnosticError",
    "MAX_FILE_OBJECT_PROBES",
    "read_skill_resource_diagnostics",
]

from collections.abc import Awaitable
from datetime import UTC, datetime
from hashlib import sha256
from inspect import isawaitable
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.response import ok

router = APIRouter()

VersionRow = dict[str, Any]
FileRow = dict[str, Any]


class SkillResolveError(ValueError):
    pass


def has_text(value: str | None) -> bool:
    return value is not None and value.strip() != ""


def to_java_instant(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        instant = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return instant.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return str(value).replace("+00:00", "Z")


def normalize_page_request(page: int, size: int) -> tuple[int, int]:
    normalized_page = max(page, 0)
    if size < 1:
        normalized_size = 20
    else:
        normalized_size = min(size, 100)
    return normalized_page, normalized_size


def paginate_rows(rows: list[dict[str, Any]], page: int, size: int) -> tuple[list[dict[str, Any]], int]:
    start = min(page * size, len(rows))
    end = min(start + size, len(rows))
    return rows[start:end], len(rows)


def build_versions_page_response(
    rows: list[dict[str, Any]],
    total: int,
    page: int,
    size: int,
) -> dict[str, object]:
    return {
        "items": [
            {
                "id": int(row["id"]),
                "version": str(row["version"]),
                "status": str(row["status"]),
                "changelog": row["changelog"],
                "fileCount": int(row["file_count"]),
                "totalSize": int(row["total_size"]),
                "publishedAt": to_java_instant(row["published_at"]),
                "downloadAvailable": str(row["status"]) == "PUBLISHED" and bool(row["download_ready"]),
            }
            for row in rows
        ],
        "total": total,
        "page": page,
        "size": size,
    }


def build_version_detail_response(row: dict[str, Any]) -> dict[str, object]:
    return {
        "id": int(row["id"]),
        "version": str(row["version"]),
        "status": str(row["status"]),
        "changelog": row["changelog"],
        "fileCount": int(row["file_count"]),
        "totalSize": int(row["total_size"]),
        "publishedAt": to_java_instant(row["published_at"]),
        "parsedMetadataJson": row["parsed_metadata_json"],
        "manifestJson": row["manifest_json"],
    }


def compute_version_fingerprint(files: list[FileRow]) -> str:
    digest = sha256()
    for file in sorted(files, key=lambda row: str(row["file_path"])):
        line = f"{file['file_path']}:{file['sha256']}\n"
        digest.update(line.encode("utf-8"))
    return f"sha256:{digest.hexdigest()}"


def find_latest_version(versions_by_id: dict[int, VersionRow], latest_version_id: int | None) -> VersionRow:
    if latest_version_id is None or latest_version_id not in versions_by_id:
        raise SkillResolveError("error.skill.version.latest.unavailable")
    return versions_by_id[latest_version_id]


def matched_value(hash_value: str | None, version_id: int, fingerprints: dict[int, str]) -> bool | None:
    if not has_text(hash_value):
        return None
    return hash_value == fingerprints[version_id]


def resolve_version_row(
    versions: list[VersionRow],
    latest_version_id: int | None,
    tags: dict[str, int],
    fingerprints: dict[int, str],
    version: str | None,
    tag: str | None,
    hash_value: str | None,
) -> tuple[VersionRow, bool | None]:
    if has_text(version) and has_text(tag):
        raise SkillResolveError("error.skill.resolve.versionTag.conflict")

    versions_by_id = {int(row["id"]): row for row in versions}
    versions_by_name = {str(row["version"]): row for row in versions}

    if has_text(version):
        selected = versions_by_name.get(str(version).strip())
        if selected is None:
            raise SkillResolveError("error.skill.version.notFound")
        selected_id = int(selected["id"])
        return selected, matched_value(hash_value, selected_id, fingerprints)

    if has_text(tag):
        normalized_tag = str(tag).strip()
        if normalized_tag.lower() == "latest":
            selected = find_latest_version(versions_by_id, latest_version_id)
            selected_id = int(selected["id"])
            return selected, matched_value(hash_value, selected_id, fingerprints)
        tag_version_id = tags.get(normalized_tag)
        if tag_version_id is None:
            raise SkillResolveError("error.skill.tag.notFound")
        selected = versions_by_id.get(tag_version_id)
        if selected is None:
            raise SkillResolveError("error.skill.tag.version.notFound")
        return selected, matched_value(hash_value, tag_version_id, fingerprints)

    if not versions:
        raise SkillResolveError("error.skill.version.latest.unavailable")

    if has_text(hash_value):
        for candidate in versions:
            candidate_id = int(candidate["id"])
            if hash_value == fingerprints[candidate_id]:
                return candidate, True

    selected = find_latest_version(versions_by_id, latest_version_id)
    return selected, False if has_text(hash_value) else None


def build_resolve_response(
    skill_id: int,
    namespace: str,
    slug: str,
    version_row: VersionRow,
    fingerprint: str,
    matched: bool | None,
) -> dict[str, object]:
    version = str(version_row["version"])
    return {
        "skillId": skill_id,
        "namespace": namespace,
        "slug": slug,
        "version": version,
        "versionId": int(version_row["id"]),
        "fingerprint": fingerprint,
        "matched": matched,
        "downloadUrl": (
            f"/api/v1/skills/{quote(namespace, safe='')}/{quote(slug, safe='')}"
            f"/versions/{quote(version, safe='')}/download"
        ),
    }


async def read_skill_resolve(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    version: str | None,
    tag: str | None,
    hash_value: str | None,
) -> dict[str, object]:
    async with engine.connect() as connection:
        skill_row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id, s.slug, s.latest_version_id
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                      AND s.visibility = 'PUBLIC'
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).mappings().one_or_none()

        if skill_row is None:
            raise SkillResolveError("error.skill.notFound")

        version_rows = (
            await connection.execute(
                text(
                    """
                    SELECT id, version
                    FROM skill_version
                    WHERE skill_id = :skill_id
                      AND status = 'PUBLISHED'
                    ORDER BY id ASC
                    """
                ),
                {"skill_id": skill_row["id"]},
            )
        ).mappings().all()

        versions = [dict(row) for row in version_rows]
        version_ids = [row["id"] for row in versions]
        if not version_ids:
            raise SkillResolveError("error.skill.version.latest.unavailable")

        tag_rows = (
            await connection.execute(
                text(
                    """
                    SELECT tag_name, version_id
                    FROM skill_tag
                    WHERE skill_id = :skill_id
                    ORDER BY tag_name ASC
                    """
                ),
                {"skill_id": skill_row["id"]},
            )
        ).mappings().all()

        file_rows = (
            await connection.execute(
                text(
                    """
                    SELECT version_id, file_path, sha256
                    FROM skill_file
                    WHERE version_id = ANY(CAST(:version_ids AS bigint[]))
                    ORDER BY version_id ASC, file_path ASC
                    """
                ),
                {"version_ids": version_ids},
            )
        ).mappings().all()

    files_by_version: dict[int, list[FileRow]] = {int(version_id): [] for version_id in version_ids}
    for row in file_rows:
        files_by_version[int(row["version_id"])].append(dict(row))

    fingerprints = {
        int(version_row["id"]): compute_version_fingerprint(files_by_version[int(version_row["id"])])
        for version_row in versions
    }
    selected, matched = resolve_version_row(
        versions=versions,
        latest_version_id=int(skill_row["latest_version_id"]) if skill_row["latest_version_id"] is not None else None,
        tags={str(row["tag_name"]): int(row["version_id"]) for row in tag_rows},
        fingerprints=fingerprints,
        version=version,
        tag=tag,
        hash_value=hash_value,
    )
    selected_id = int(selected["id"])
    return build_resolve_response(
        skill_id=int(skill_row["id"]),
        namespace=namespace,
        slug=str(skill_row["slug"]),
        version_row=selected,
        fingerprint=fingerprints[selected_id],
        matched=matched,
    )


async def read_skill_versions(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    page: int,
    size: int,
) -> dict[str, object]:
    page, size = normalize_page_request(page, size)
    async with engine.connect() as connection:
        skill_id = (
            await connection.execute(
                text(
                    """
                    SELECT s.id
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                      AND s.visibility = 'PUBLIC'
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).scalar_one_or_none()

        if skill_id is None:
            raise SkillResolveError("error.skill.notFound")

        rows = (
            await connection.execute(
                text(
                    """
                    SELECT id, version, status, changelog, file_count, total_size, published_at, download_ready
                    FROM skill_version
                    WHERE skill_id = :skill_id
                      AND status = 'PUBLISHED'
                    ORDER BY created_at DESC
                    """
                ),
                {"skill_id": skill_id},
            )
        ).mappings().all()

    page_rows, total = paginate_rows([dict(row) for row in rows], page, size)
    return build_versions_page_response(page_rows, total, page, size)


async def read_skill_version_detail(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    version: str,
) -> dict[str, object]:
    async with engine.connect() as connection:
        row = (
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
                           sv.parsed_metadata_json::text AS parsed_metadata_json,
                           sv.manifest_json::text AS manifest_json
                    FROM skill_version sv
                    JOIN skill s ON s.id = sv.skill_id
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                      AND s.visibility = 'PUBLIC'
                      AND sv.version = :version
                      AND sv.status = 'PUBLISHED'
                    ORDER BY sv.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug, "version": version},
            )
        ).mappings().one_or_none()

    if row is None:
        raise SkillResolveError("error.skill.version.notFound")
    return build_version_detail_response(dict(row))


async def read_skill_version_files(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    version: str,
) -> list[dict[str, object]]:
    async with engine.connect() as connection:
        skill_id = (
            await connection.execute(
                text(
                    """
                    SELECT s.id
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                      AND s.visibility = 'PUBLIC'
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).scalar_one_or_none()

        if skill_id is None:
            raise SkillResolveError("error.skill.notFound")

        version_row = (
            await connection.execute(
                text(
                    """
                    SELECT id
                    FROM skill_version
                    WHERE skill_id = :skill_id
                      AND version = :version
                      AND status = 'PUBLISHED'
                    LIMIT 1
                    """
                ),
                {"skill_id": skill_id, "version": version},
            )
        ).mappings().one_or_none()

        if version_row is None:
            raise SkillResolveError("error.skill.version.notFound")

        version_id = version_row["id"]

        rows = (
            await connection.execute(
                text(
                    """
                    SELECT id, file_path, file_size, content_type, sha256
                    FROM skill_file
                    WHERE version_id = :version_id
                    ORDER BY file_path ASC
                    """
                ),
                {"version_id": version_id},
            )
        ).mappings().all()

    return [
        {
            "id": int(row["id"]),
            "filePath": str(row["file_path"]),
            "fileSize": int(row["file_size"]),
            "contentType": row["content_type"],
            "sha256": str(row["sha256"]),
        }
        for row in rows
    ]


async def read_skill_tag_files(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    tag_name: str,
) -> list[dict[str, object]]:
    async with engine.connect() as connection:
        skill_row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id, s.latest_version_id
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                      AND s.visibility = 'PUBLIC'
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).mappings().one_or_none()

        if skill_row is None:
            raise SkillResolveError("error.skill.notFound")

        skill_id = skill_row["id"]

        if tag_name.lower() == "latest":
            version_id = skill_row["latest_version_id"]
        else:
            version_id = (
                await connection.execute(
                    text(
                        """
                        SELECT version_id
                        FROM skill_tag
                        WHERE skill_id = :skill_id
                          AND tag_name = :tag_name
                        LIMIT 1
                        """
                    ),
                    {"skill_id": skill_id, "tag_name": tag_name},
                )
            ).scalar_one_or_none()

            if version_id is None:
                raise SkillResolveError("error.skill.tag.notFound")

        version_row = (
            await connection.execute(
                text(
                    """
                    SELECT id
                    FROM skill_version
                    WHERE id = :version_id
                      AND status = 'PUBLISHED'
                    LIMIT 1
                    """
                ),
                {"version_id": version_id},
            )
        ).mappings().one_or_none()

        if version_row is None:
            raise SkillResolveError("error.skill.tag.version.notFound")

        rows = (
            await connection.execute(
                text(
                    """
                    SELECT id, file_path, file_size, content_type, sha256
                    FROM skill_file
                    WHERE version_id = :version_id
                    ORDER BY file_path ASC
                    """
                ),
                {"version_id": version_id},
            )
        ).mappings().all()

    return [
        {
            "id": int(row["id"]),
            "filePath": str(row["file_path"]),
            "fileSize": int(row["file_size"]),
            "contentType": row["content_type"],
            "sha256": str(row["sha256"]),
        }
        for row in rows
    ]



async def _resolve_reader_result(result: dict[str, object] | Awaitable[dict[str, object]]) -> dict[str, object]:
    if isawaitable(result):
        return await result
    return result


@router.get("/api/v1/skills/{namespace}/{slug}/resolve")
@router.get("/api/web/skills/{namespace}/{slug}/resolve")
async def resolve_skill_version(
    namespace: str,
    slug: str,
    request: Request,
    version: str | None = None,
    tag: str | None = None,
    hash_value: str | None = Query(default=None, alias="hash"),
) -> dict[str, object]:
    reader = getattr(request.app.state, "skill_resolve_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, version, tag, hash_value))
        else:
            data = await read_skill_resolve(request.app.state.db_engine, namespace, slug, version, tag, hash_value)
    except SkillResolveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("获取成功", data, request)


@router.get("/api/v1/skills/{namespace}/{slug}/versions/{version}")
@router.get("/api/web/skills/{namespace}/{slug}/versions/{version}")
async def get_skill_version_detail(
    namespace: str,
    slug: str,
    version: str,
    request: Request,
) -> dict[str, object]:
    reader = getattr(request.app.state, "skill_version_detail_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, version))
        else:
            data = await read_skill_version_detail(request.app.state.db_engine, namespace, slug, version)
    except SkillResolveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("获取成功", data, request)


@router.get("/api/v1/skills/{namespace}/{slug}/versions")
@router.get("/api/web/skills/{namespace}/{slug}/versions")
async def list_skill_versions(
    namespace: str,
    slug: str,
    request: Request,
    page: int = 0,
    size: int = 20,
) -> dict[str, object]:
    reader = getattr(request.app.state, "skill_versions_reader", None)
    page, size = normalize_page_request(page, size)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, page, size))
        else:
            data = await read_skill_versions(request.app.state.db_engine, namespace, slug, page, size)
    except SkillResolveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("获取成功", data, request)


@router.get("/api/v1/skills/{namespace}/{slug}/versions/{version}/files")
@router.get("/api/web/skills/{namespace}/{slug}/versions/{version}/files")
async def list_skill_version_files(
    namespace: str,
    slug: str,
    version: str,
    request: Request,
) -> dict[str, object]:
    reader = getattr(request.app.state, "skill_version_files_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, version))
        else:
            data = await read_skill_version_files(request.app.state.db_engine, namespace, slug, version)
    except SkillResolveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("获取成功", data, request)


@router.get("/api/v1/skills/{namespace}/{slug}/tags/{tagName}/files")
@router.get("/api/web/skills/{namespace}/{slug}/tags/{tagName}/files")
async def list_skill_tag_files(
    namespace: str,
    slug: str,
    tagName: str,
    request: Request,
) -> dict[str, object]:
    reader = getattr(request.app.state, "skill_tag_files_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, tagName))
        else:
            data = await read_skill_tag_files(request.app.state.db_engine, namespace, slug, tagName)
    except SkillResolveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("获取成功", data, request)


from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import re
from typing import Any
from zipfile import ZipFile

from fastapi import Response

from app.object_storage import ObjectNotFoundError, object_storage_for_base_path


class SkillResolveError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class DownloadResult:
    content: bytes
    content_type: str
    filename: str
    content_length: int | None = None

    def __post_init__(self) -> None:
        if self.content_length is None:
            object.__setattr__(self, "content_length", len(self.content))

    def as_bytes_io(self) -> BytesIO:
        return BytesIO(self.content)


def read_local_storage_bytes(storage_base_path: str, storage_key: str) -> bytes:
    try:
        return object_storage_for_base_path(storage_base_path).read_bytes(storage_key)
    except (FileNotFoundError, ObjectNotFoundError, ValueError) as exc:
        raise SkillResolveError("error.skill.file.notFound") from exc


def read_local_storage_text(storage_base_path: str, storage_key: str) -> str:
    return read_local_storage_bytes(storage_base_path, storage_key).decode("utf-8")


def assert_version_file_content_access(version_row: dict[str, Any], can_manage: bool) -> None:
    if str(version_row["status"]) != "PUBLISHED" and not can_manage:
        raise SkillResolveError("error.skill.version.notPublished")


def read_file_content_from_row(storage_base_path: str, file_row: dict[str, Any]) -> bytes:
    try:
        return read_local_storage_bytes(storage_base_path, str(file_row["storage_key"]))
    except SkillResolveError as exc:
        raise SkillResolveError("error.skill.file.notFound") from exc


def sanitize_download_filename(value: str) -> str:
    sanitized = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "-", value)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized if sanitized != "" else "skill"


def build_download_filename(display_name: str | None, slug: str, version: str) -> str:
    base_name = display_name if display_name is not None and display_name.strip() != "" else slug
    return f"{sanitize_download_filename(base_name)}-{version}.zip"


def bundle_storage_key(skill_id: int, version_id: int) -> str:
    return f"packages/{skill_id}/{version_id}/bundle.zip"


def read_bundle_or_build_fallback_zip(
    storage_base_path: str,
    version_row: dict[str, Any],
    file_rows: list[dict[str, Any]],
) -> DownloadResult:
    skill_id = int(version_row["skill_id"])
    version_id = int(version_row["version_id"])
    filename = build_download_filename(
        version_row.get("display_name"),
        str(version_row["slug"]),
        str(version_row["version"]),
    )
    storage_key = bundle_storage_key(skill_id, version_id)
    storage = object_storage_for_base_path(storage_base_path)
    if storage.exists(storage_key):
        content = read_local_storage_bytes(storage_base_path, storage_key)
        content_type = version_row.get("content_type") or "application/zip"
        content_length = version_row.get("content_length")
        return DownloadResult(
            content=content,
            content_type=str(content_type),
            filename=filename,
            content_length=int(content_length) if content_length is not None else len(content),
        )

    available_files = []
    for file_row in sorted(file_rows, key=lambda row: str(row["file_path"])):
        try:
            content = read_file_content_from_row(storage_base_path, file_row)
        except SkillResolveError:
            continue
        available_files.append((str(file_row["file_path"]), content))

    if not available_files:
        raise SkillResolveError("error.skill.bundle.notFound")

    buffer = BytesIO()
    with ZipFile(buffer, "w") as zip_file:
        for file_path, content in available_files:
            zip_file.writestr(file_path, content)

    content = buffer.getvalue()
    return DownloadResult(
        content=content,
        content_type="application/zip",
        filename=filename,
        content_length=len(content),
    )


def assert_download_access(version_row: dict[str, Any], can_manage: bool) -> None:
    status = str(version_row["status"])
    if status in {"PUBLISHED", "UPLOADED", "PENDING_REVIEW"}:
        return
    raise SkillResolveError("error.skill.version.notDownloadable")


def build_download_response(result: DownloadResult) -> Response:
    return Response(
        content=result.content,
        media_type=result.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{result.filename}"',
            "Content-Length": str(result.content_length),
        },
    )


__all__ = [
    "DownloadResult",
    "SkillResolveError",
    "assert_download_access",
    "assert_version_file_content_access",
    "build_download_filename",
    "build_download_response",
    "bundle_storage_key",
    "read_bundle_or_build_fallback_zip",
    "read_file_content_from_row",
    "read_local_storage_bytes",
    "read_local_storage_text",
    "sanitize_download_filename",
]

from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from hashlib import sha256
from inspect import isawaitable
from io import BytesIO
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote
from zipfile import ZipFile

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.auth.policy import is_namespace_manager, is_namespace_member
from app.core.response import ok

router = APIRouter()

VersionRow = dict[str, Any]
FileRow = dict[str, Any]

LIFECYCLE_MANAGER_STATUSES = (
    "PUBLISHED",
    "REJECTED",
    "PENDING_REVIEW",
    "UPLOADED",
    "DRAFT",
    "SCANNING",
    "SCAN_FAILED",
    "YANKED",
)
LIFECYCLE_LIST_PRIORITY = {status: index for index, status in enumerate(LIFECYCLE_MANAGER_STATUSES)}
COMPARE_MAX_FILE_BYTES = 1024 * 1024
COMPARE_MAX_LINES = 5000
BINARY_FILE_EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".zip",
    ".tar",
    ".gz",
    ".jar",
    ".war",
    ".class",
    ".so",
    ".dll",
    ".exe",
    ".pdf",
)


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


def has_text(value: str | None) -> bool:
    return value is not None and value.strip() != ""


def normalized_current_user_id(mock_user_id: str | None) -> str | None:
    return mock_user_id.strip() if mock_user_id is not None and mock_user_id.strip() != "" else None


def lifecycle_visible_statuses(can_manage: bool) -> tuple[str, ...]:
    return LIFECYCLE_MANAGER_STATUSES if can_manage else ("PUBLISHED",)


def lifecycle_list_priority(status: str) -> int:
    return LIFECYCLE_LIST_PRIORITY.get(status, len(LIFECYCLE_LIST_PRIORITY))


async def read_namespace_role(
    connection: Any,
    namespace_id: int,
    current_user_id: str | None,
) -> str | None:
    if current_user_id is None:
        return None
    return (
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
            {"namespace_id": namespace_id, "user_id": current_user_id},
        )
    ).scalar_one_or_none()


def can_manage_lifecycle_for_row(row: dict[str, Any], current_user_id: str | None, namespace_role: str | None) -> bool:
    return current_user_id is not None and (
        str(row["owner_id"]) == str(current_user_id) or is_namespace_manager(namespace_role)
    )


def can_access_skill_row(row: dict[str, Any], current_user_id: str | None, namespace_role: str | None) -> bool:
    visibility = str(row["visibility"])
    if row.get("latest_version_id") is None:
        return current_user_id is not None and str(row["owner_id"]) == str(current_user_id)
    if visibility == "PUBLIC":
        return True
    if visibility == "NAMESPACE_ONLY":
        return current_user_id is not None and is_namespace_member(namespace_role)
    if visibility == "PRIVATE":
        return can_manage_lifecycle_for_row(row, current_user_id, namespace_role)
    return False


def assert_skill_row_access(row: dict[str, Any], current_user_id: str | None, namespace_role: str | None) -> None:
    if not can_access_skill_row(row, current_user_id, namespace_role):
        raise SkillResolveError("error.skill.access.denied", status_code=403)


def to_java_instant(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        instant = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return instant.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return str(value).replace("+00:00", "Z")


def to_epoch_millis(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        instant = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    else:
        normalized = str(value).replace("Z", "+00:00")
        instant = datetime.fromisoformat(normalized)
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=UTC)
    return int(instant.astimezone(UTC).timestamp() * 1000)


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


def normalize_search_sort(sort: str | None) -> str:
    if sort is None or sort.strip() == "":
        return "newest"
    return sort.strip()


def parse_non_negative_int(raw_value: str | None, default_value: int) -> int:
    if raw_value is None or raw_value.strip() == "":
        return default_value
    normalized = raw_value.strip()
    if not re.fullmatch(r"\d+", normalized):
        return default_value
    try:
        return int(normalized)
    except ValueError:
        return default_value


def parse_positive_int(raw_value: str | None, default_value: int) -> int:
    parsed = parse_non_negative_int(raw_value, default_value)
    return parsed if parsed > 0 else default_value


def normalize_label_slugs(label_slugs: list[str] | None) -> list[str]:
    if not label_slugs:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for value in label_slugs:
        slug = value.strip().lower()
        if slug == "" or slug in seen:
            continue
        normalized.append(slug)
        seen.add(slug)
    return normalized


def normalize_search_keyword(keyword: str | None) -> str | None:
    if keyword is None or keyword.strip() == "":
        return None
    return keyword.strip().lower()


def build_skill_search_ts_query(keyword: str | None) -> str | None:
    normalized = normalize_search_keyword(keyword)
    if normalized is None:
        return None
    terms = re.findall(r"[\w\u4e00-\u9fff]+", normalized)[:8]
    compatible_terms = [
        term
        for term in terms
        if any(ch.isalpha() or "\u4e00" <= ch <= "\u9fff" or ch == "_" for ch in term)
    ]
    if not compatible_terms:
        return None
    ts_terms = [
        f"{term}:*" if all(ord(ch) < 128 for ch in term) and any(ch.isalpha() for ch in term) else term
        for term in compatible_terms
    ]
    return " & ".join(ts_terms)


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


def build_tag_response(row: dict[str, Any]) -> dict[str, object]:
    return {
        "id": int(row["id"]) if row.get("id") is not None else None,
        "tagName": str(row["tag_name"]),
        "versionId": int(row["version_id"]),
        "createdAt": to_java_instant(row.get("created_at")),
    }


def to_lifecycle_version(
    row: dict[str, Any],
    *,
    id_key: str = "published_version_id",
    version_key: str = "published_version",
    status_key: str = "published_version_status",
) -> dict[str, object] | None:
    if row.get(id_key) is None:
        return None
    return {
        "id": int(row[id_key]),
        "version": str(row[version_key]),
        "status": str(row[status_key]),
    }


def build_skill_detail_response(
    row: dict[str, Any],
    labels: list[dict[str, object]],
) -> dict[str, object]:
    published_version = to_lifecycle_version(row)
    owner_preview_version = to_lifecycle_version(
        row,
        id_key="owner_preview_version_id",
        version_key="owner_preview_version",
        status_key="owner_preview_version_status",
    )
    headline_version = published_version if published_version is not None else owner_preview_version
    if headline_version is None:
        resolution_mode = "NONE"
    elif published_version is not None:
        resolution_mode = "PUBLISHED"
    else:
        resolution_mode = "OWNER_PREVIEW"
    current_user_id = row.get("current_user_id")
    namespace_role = row.get("namespace_role")
    can_manage_lifecycle = current_user_id is not None and (
        str(row["owner_id"]) == str(current_user_id) or is_namespace_manager(namespace_role)
    )
    can_submit_promotion = (
        can_manage_lifecycle
        and str(row.get("namespace_type")) != "GLOBAL"
        and str(row.get("namespace_status", "ACTIVE")) == "ACTIVE"
        and str(row["status"]) == "ACTIVE"
        and published_version is not None
        and published_version["status"] == "PUBLISHED"
        and not bool(row.get("promotion_blocked", False))
    )
    can_report = current_user_id is None or str(row["owner_id"]) != str(current_user_id)
    return {
        "id": int(row["id"]),
        "slug": str(row["slug"]),
        "displayName": row["display_name"],
        "ownerId": str(row["owner_id"]),
        "ownerDisplayName": row["owner_display_name"],
        "summary": row["summary"],
        "visibility": str(row["visibility"]),
        "status": str(row["status"]),
        "downloadCount": int(row["download_count"]),
        "starCount": int(row["star_count"]),
        "subscriptionCount": int(row["subscription_count"]),
        "ratingAvg": float(row["rating_avg"]),
        "ratingCount": int(row["rating_count"]),
        "hidden": bool(row["hidden"]),
        "namespace": str(row["namespace"]),
        "labels": labels,
        "canManageLifecycle": can_manage_lifecycle,
        "canSubmitPromotion": can_submit_promotion,
        "canInteract": headline_version is None or headline_version["status"] == "PUBLISHED",
        "canReport": can_report,
        "headlineVersion": headline_version,
        "publishedVersion": published_version,
        "ownerPreviewVersion": owner_preview_version,
        "ownerPreviewReviewComment": row.get("owner_preview_review_comment"),
        "resolutionMode": resolution_mode,
    }


def build_skill_summary_response(row: dict[str, Any]) -> dict[str, object]:
    published_version = to_lifecycle_version(row)
    return {
        "id": int(row["id"]),
        "slug": str(row["slug"]),
        "displayName": row["display_name"],
        "summary": row["summary"],
        "visibility": str(row["visibility"]),
        "status": str(row["status"]),
        "downloadCount": int(row["download_count"]),
        "starCount": int(row["star_count"]),
        "ratingAvg": float(row["rating_avg"]),
        "ratingCount": int(row["rating_count"]),
        "namespace": str(row["namespace"]),
        "updatedAt": to_java_instant(row["updated_at"]),
        "canSubmitPromotion": False,
        "headlineVersion": published_version,
        "publishedVersion": published_version,
        "ownerPreviewVersion": None,
        "resolutionMode": str(row["resolution_mode"]),
    }


def build_skill_search_response(
    rows: list[dict[str, Any]],
    total: int,
    page: int,
    size: int,
) -> dict[str, object]:
    return {
        "items": [build_skill_summary_response(row) for row in rows],
        "total": total,
        "page": page,
        "size": size,
    }


def to_clawhub_canonical_slug(namespace: str, slug: str) -> str:
    return slug if namespace == "global" else f"{namespace}--{slug}"


def from_clawhub_canonical_slug(canonical_slug: str) -> tuple[str, str]:
    separator_index = canonical_slug.find("--")
    if separator_index > 0:
        return canonical_slug[:separator_index], canonical_slug[separator_index + 2 :]
    return "global", canonical_slug


def build_clawhub_search_response(search_response: dict[str, object]) -> dict[str, object]:
    results = []
    for item in search_response["items"]:  # type: ignore[index]
        summary = dict(item)  # type: ignore[arg-type]
        published_version = summary.get("publishedVersion")
        star_count = summary.get("starCount") or 0
        download_count = summary.get("downloadCount") or 0
        results.append(
            {
                "slug": to_clawhub_canonical_slug(str(summary["namespace"]), str(summary["slug"])),
                "displayName": summary["displayName"],
                "summary": summary["summary"],
                "version": published_version["version"] if published_version is not None else None,  # type: ignore[index]
                "score": ((int(star_count) * 10) + int(download_count)) / 100.0,
                "updatedAt": to_epoch_millis(summary.get("updatedAt")),
            }
        )
    return {"results": results}


def build_cli_search_response(search_response: dict[str, object], limit: int) -> dict[str, object]:
    items = []
    for item in search_response["items"]:  # type: ignore[index]
        summary = dict(item)  # type: ignore[arg-type]
        published_version = summary.get("publishedVersion")
        items.append(
            {
                "namespace": str(summary["namespace"]),
                "slug": str(summary["slug"]),
                "latestVersion": published_version["version"] if published_version is not None else None,  # type: ignore[index]
                "summary": summary.get("summary"),
            }
        )
    return {"items": items, "total": int(search_response["total"]), "limit": limit}


def build_clawhub_skills_list_response(search_response: dict[str, object]) -> dict[str, object]:
    items = []
    for item in search_response["items"]:  # type: ignore[index]
        summary = dict(item)  # type: ignore[arg-type]
        updated_at = to_epoch_millis(summary.get("updatedAt")) or 0
        published_version = summary.get("publishedVersion")
        latest_version = None
        if published_version is not None:
            latest_version = {
                "version": published_version["version"],  # type: ignore[index]
                "createdAt": updated_at,
                "changelog": "",
                "license": None,
            }

        stats: dict[str, object] = {}
        if summary.get("downloadCount") is not None:
            stats["downloads"] = summary["downloadCount"]
        if summary.get("starCount") is not None:
            stats["stars"] = summary["starCount"]

        items.append(
            {
                "slug": to_clawhub_canonical_slug(str(summary["namespace"]), str(summary["slug"])),
                "displayName": summary["displayName"],
                "summary": summary.get("summary"),
                "tags": {},
                "stats": stats,
                "createdAt": 0,
                "updatedAt": updated_at,
                "latestVersion": latest_version,
            }
        )

    page = int(search_response["page"])
    size = int(search_response["size"])
    total = int(search_response["total"])
    current_offset = page * size
    next_cursor = str(page + 1) if current_offset + len(items) < total else None
    return {"items": items, "nextCursor": next_cursor}


def build_clawhub_resolve_response(resolve_response: dict[str, object]) -> dict[str, object]:
    version = resolve_response.get("version")
    version_info = {"version": version} if version is not None else None
    return {"match": version_info, "latestVersion": version_info}


def build_cli_resolve_response(resolve_response: dict[str, object]) -> dict[str, object]:
    return {
        "namespace": str(resolve_response["namespace"]),
        "slug": str(resolve_response["slug"]),
        "version": resolve_response.get("version"),
        "versionId": resolve_response.get("versionId"),
        "fingerprint": resolve_response.get("fingerprint"),
        "downloadUrl": resolve_response.get("downloadUrl"),
    }


def build_clawhub_skill_detail_response(detail_response: dict[str, object]) -> dict[str, object]:
    namespace = str(detail_response["namespace"])
    slug = str(detail_response["slug"])
    published_version = detail_response.get("publishedVersion")
    latest_version = None
    if published_version is not None:
        latest_version = {
            "version": published_version["version"],  # type: ignore[index]
            "createdAt": to_epoch_millis(detail_response.get("publishedAt")) or 0,
            "changelog": detail_response.get("changelog") or "",
            "license": None,
        }
    return {
        "skill": {
            "slug": to_clawhub_canonical_slug(namespace, slug),
            "displayName": detail_response["displayName"],
            "summary": detail_response.get("summary"),
            "tags": {},
            "stats": {},
            "createdAt": to_epoch_millis(detail_response.get("createdAt")) or 0,
            "updatedAt": to_epoch_millis(detail_response.get("updatedAt")) or 0,
        },
        "latestVersion": latest_version,
        "owner": None,
        "moderation": {
            "isSuspicious": False,
            "isMalwareBlocked": False,
            "verdict": "clean",
            "reasonCodes": [],
            "updatedAt": None,
            "engineVersion": None,
            "summary": None,
        },
    }


def clawhub_resolve_selectors(version: str | None, default_latest: bool) -> tuple[str | None, str | None]:
    selected = "latest" if version is None and default_latest else version
    if selected == "latest":
        return None, "latest"
    return selected, None


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


def is_binary_compare_path(path: str) -> bool:
    lower_path = path.lower()
    return any(lower_path.endswith(extension) for extension in BINARY_FILE_EXTENSIONS)


def split_compare_lines(content: str | None) -> list[str]:
    if not content:
        return []
    lines = content.splitlines()
    if content.endswith(("\n", "\r")):
        lines.append("")
    return lines


def build_compare_hunks(old_content: str, new_content: str) -> list[dict[str, object]]:
    old_lines = split_compare_lines(old_content)
    new_lines = split_compare_lines(new_content)
    hunks: list[dict[str, object]] = []
    matcher = SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag == "equal":
            continue

        lines: list[dict[str, object]] = []
        for offset, line in enumerate(old_lines[old_start:old_end], start=old_start + 1):
            lines.append(
                {
                    "type": "DELETE",
                    "content": line,
                    "oldLineNumber": offset,
                    "newLineNumber": None,
                }
            )
        for offset, line in enumerate(new_lines[new_start:new_end], start=new_start + 1):
            lines.append(
                {
                    "type": "ADD",
                    "content": line,
                    "oldLineNumber": None,
                    "newLineNumber": offset,
                }
            )

        hunks.append(
            {
                "oldStart": old_start + 1,
                "oldLines": old_end - old_start,
                "newStart": new_start + 1,
                "newLines": new_end - new_start,
                "lines": lines,
            }
        )
    return hunks


def build_compare_file(
    path: str,
    from_file: dict[str, object] | None,
    to_file: dict[str, object] | None,
) -> dict[str, object] | None:
    if from_file is not None and to_file is not None and from_file.get("sha256") == to_file.get("sha256"):
        return None

    if from_file is None:
        change_type = "ADDED"
        old_size = None
        new_size = int(to_file["file_size"]) if to_file is not None else None
        old_content = ""
        new_content = str(to_file.get("content") or "") if to_file is not None else ""
    elif to_file is None:
        change_type = "REMOVED"
        old_size = int(from_file["file_size"])
        new_size = None
        old_content = str(from_file.get("content") or "")
        new_content = ""
    else:
        change_type = "MODIFIED"
        old_size = int(from_file["file_size"])
        new_size = int(to_file["file_size"])
        old_content = str(from_file.get("content") or "")
        new_content = str(to_file.get("content") or "")

    binary = is_binary_compare_path(path)
    old_lines = split_compare_lines(old_content)
    new_lines = split_compare_lines(new_content)
    truncated = (
        (old_size is not None and old_size > COMPARE_MAX_FILE_BYTES)
        or (new_size is not None and new_size > COMPARE_MAX_FILE_BYTES)
        or len(old_lines) > COMPARE_MAX_LINES
        or len(new_lines) > COMPARE_MAX_LINES
    )
    hunks = [] if binary or truncated else build_compare_hunks(old_content, new_content)
    return {
        "path": path,
        "changeType": change_type,
        "oldSize": old_size,
        "newSize": new_size,
        "binary": binary,
        "truncated": truncated,
        "hunks": hunks,
    }


def build_compare_response(
    from_version: str,
    to_version: str,
    from_files: dict[str, dict[str, object]],
    to_files: dict[str, dict[str, object]],
) -> dict[str, object]:
    files = [
        file
        for path in sorted(set(from_files) | set(to_files))
        if (file := build_compare_file(path, from_files.get(path), to_files.get(path))) is not None
    ]
    added_files = sum(1 for file in files if file["changeType"] == "ADDED")
    removed_files = sum(1 for file in files if file["changeType"] == "REMOVED")
    modified_files = sum(1 for file in files if file["changeType"] == "MODIFIED")
    added_lines = sum(
        1
        for file in files
        for hunk in file["hunks"]
        for line in hunk["lines"]
        if line["type"] == "ADD"
    )
    removed_lines = sum(
        1
        for file in files
        for hunk in file["hunks"]
        for line in hunk["lines"]
        if line["type"] == "DELETE"
    )
    return {
        "from": from_version,
        "to": to_version,
        "summary": {
            "totalFiles": len(files),
            "addedFiles": added_files,
            "modifiedFiles": modified_files,
            "removedFiles": removed_files,
            "addedLines": added_lines,
            "removedLines": removed_lines,
        },
        "files": files,
    }


def read_local_storage_bytes(storage_base_path: str, storage_key: str) -> bytes:
    base = Path(storage_base_path).resolve()
    target = (base / storage_key).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise SkillResolveError("error.skill.file.notFound") from exc

    try:
        return target.read_bytes()
    except FileNotFoundError as exc:
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
    bundle_path = (Path(storage_base_path).resolve() / storage_key).resolve()
    try:
        bundle_path.relative_to(Path(storage_base_path).resolve())
    except ValueError as exc:
        raise SkillResolveError("error.skill.bundle.notFound") from exc

    if bundle_path.exists():
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


async def increment_published_download_counters(connection: Any, skill_id: int, version_id: int) -> None:
    await connection.execute(
        text("UPDATE skill SET download_count = download_count + 1 WHERE id = :skill_id"),
        {"skill_id": skill_id},
    )
    await connection.execute(
        text(
            """
            INSERT INTO skill_version_stats (skill_version_id, skill_id, download_count, updated_at)
            VALUES (:version_id, :skill_id, 1, CURRENT_TIMESTAMP)
            ON CONFLICT (skill_version_id)
            DO UPDATE SET download_count = skill_version_stats.download_count + 1,
                          updated_at = CURRENT_TIMESTAMP
            """
        ),
        {"version_id": version_id, "skill_id": skill_id},
    )


async def read_skill_resolve(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    version: str | None,
    tag: str | None,
    hash_value: str | None,
    current_user_id: str | None = None,
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


async def read_clawhub_legacy_slug_coordinate(engine: AsyncEngine, slug: str) -> tuple[str, str]:
    if "--" in slug:
        return from_clawhub_canonical_slug(slug)

    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    """
                    SELECT n.slug AS namespace, s.slug AS slug
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE s.slug = :slug
                      AND n.status = 'ACTIVE'
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"slug": slug},
            )
        ).mappings().one_or_none()

    if row is None:
        return from_clawhub_canonical_slug(slug)
    return str(row["namespace"]), str(row["slug"])


async def read_skill_versions(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    page: int,
    size: int,
    current_user_id: str | None = None,
) -> dict[str, object]:
    page, size = normalize_page_request(page, size)
    async with engine.connect() as connection:
        skill_row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id, s.owner_id, s.namespace_id
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).mappings().one_or_none()

        if skill_row is None:
            raise SkillResolveError("error.skill.notFound")

        namespace_role = await read_namespace_role(connection, int(skill_row["namespace_id"]), current_user_id)
        can_manage = can_manage_lifecycle_for_row(dict(skill_row), current_user_id, namespace_role)
        visible_statuses = lifecycle_visible_statuses(can_manage)
        status_literals = ", ".join(f"'{status}'" for status in visible_statuses)
        rows = (
            await connection.execute(
                text(
                    f"""
                    SELECT id, version, status, changelog, file_count, total_size, published_at, download_ready
                    FROM skill_version
                    WHERE skill_id = :skill_id
                      AND status IN ({status_literals})
                    ORDER BY
                      CASE status
                        WHEN 'PUBLISHED' THEN 0
                        WHEN 'REJECTED' THEN 1
                        WHEN 'PENDING_REVIEW' THEN 2
                        WHEN 'UPLOADED' THEN 3
                        WHEN 'DRAFT' THEN 4
                        WHEN 'SCANNING' THEN 5
                        WHEN 'SCAN_FAILED' THEN 6
                        WHEN 'YANKED' THEN 7
                        ELSE 8
                      END,
                      published_at DESC NULLS LAST,
                      created_at DESC NULLS LAST,
                      id DESC
                    """
                ),
                {"skill_id": skill_row["id"]},
            )
        ).mappings().all()

    page_rows, total = paginate_rows([dict(row) for row in rows], page, size)
    return build_versions_page_response(page_rows, total, page, size)


async def read_skill_version_detail(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    version: str,
    current_user_id: str | None = None,
) -> dict[str, object]:
    async with engine.connect() as connection:
        skill_row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id, s.owner_id, s.namespace_id
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).mappings().one_or_none()

        if skill_row is None:
            raise SkillResolveError("error.skill.notFound")

        namespace_role = await read_namespace_role(connection, int(skill_row["namespace_id"]), current_user_id)
        can_manage = can_manage_lifecycle_for_row(dict(skill_row), current_user_id, namespace_role)
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
                    WHERE sv.skill_id = :skill_id
                      AND sv.version = :version
                    ORDER BY sv.id ASC
                    LIMIT 1
                    """
                ),
                {"skill_id": skill_row["id"], "version": version},
            )
        ).mappings().one_or_none()

    if row is None:
        raise SkillResolveError("error.skill.version.notFound")
    if str(row["status"]) != "PUBLISHED" and not can_manage:
        raise SkillResolveError("error.skill.version.notPublished")
    return build_version_detail_response(dict(row))


async def read_skill_detail(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    current_user_id: str | None = None,
) -> dict[str, object]:
    async with engine.connect() as connection:
        skill_row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id,
                           s.slug,
                           s.display_name,
                           s.owner_id,
                           NULLIF(BTRIM(ua.display_name), '') AS owner_display_name,
                           s.summary,
                           s.visibility,
                           s.status,
                           s.download_count,
                           s.star_count,
                           s.subscription_count,
                           s.rating_avg,
                           s.rating_count,
                           s.hidden,
                           s.namespace_id,
                           s.latest_version_id,
                           n.slug AS namespace,
                           n.type AS namespace_type,
                           n.status AS namespace_status
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    LEFT JOIN user_account ua ON ua.id = s.owner_id
                    WHERE n.slug = :namespace
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).mappings().one_or_none()

        if skill_row is None:
            raise SkillResolveError("error.skill.notFound")
        if str(skill_row["namespace_status"]) == "ARCHIVED":
            raise SkillResolveError("error.namespace.archived", status_code=403)
        if str(skill_row["visibility"]) != "PUBLIC":
            raise SkillResolveError("error.skill.access.denied", status_code=403)

        namespace_role = None
        if current_user_id is not None:
            namespace_role = (
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
                    {
                        "namespace_id": skill_row["namespace_id"],
                        "user_id": current_user_id,
                    },
                )
            ).scalar_one_or_none()

        published_version = (
            await connection.execute(
                text(
                    """
                    SELECT id, version, status, created_at
                    FROM skill_version
                    WHERE skill_id = :skill_id
                      AND status = 'PUBLISHED'
                    ORDER BY
                      CASE WHEN id = :latest_version_id THEN 0 ELSE 1 END,
                      published_at DESC NULLS LAST,
                      created_at DESC NULLS LAST,
                      id DESC
                    LIMIT 1
                    """
                ),
                {
                    "skill_id": skill_row["id"],
                    "latest_version_id": skill_row["latest_version_id"],
                },
            )
        ).mappings().one_or_none()

        can_manage_lifecycle = current_user_id is not None and (
            str(skill_row["owner_id"]) == str(current_user_id) or is_namespace_manager(namespace_role)
        )
        owner_preview_version = None
        owner_preview_review_comment = None
        if can_manage_lifecycle:
            if published_version is None:
                preview_where_sql = ""
                preview_params: dict[str, Any] = {"skill_id": skill_row["id"]}
            elif published_version["created_at"] is None:
                preview_where_sql = "AND sv.created_at IS NULL AND sv.id > :published_version_id"
                preview_params = {
                    "skill_id": skill_row["id"],
                    "published_version_id": published_version["id"],
                }
            else:
                preview_where_sql = """
                          AND (
                              sv.created_at IS NULL
                              OR (
                                  sv.created_at IS NOT NULL
                                  AND (
                                      sv.created_at > :published_created_at
                                      OR (sv.created_at = :published_created_at AND sv.id > :published_version_id)
                                  )
                              )
                          )
                """
                preview_params = {
                    "skill_id": skill_row["id"],
                    "published_version_id": published_version["id"],
                    "published_created_at": published_version["created_at"],
                }
            owner_preview_version = (
                await connection.execute(
                    text(
                        f"""
                        SELECT sv.id, sv.version, sv.status, sv.created_at
                        FROM skill_version sv
                        WHERE sv.skill_id = :skill_id
                          AND sv.status NOT IN ('PUBLISHED', 'YANKED')
                          {preview_where_sql}
                        ORDER BY sv.created_at DESC NULLS FIRST, sv.id DESC
                        LIMIT 1
                        """
                    ),
                    preview_params,
                )
            ).mappings().one_or_none()

            if owner_preview_version is not None and str(owner_preview_version["status"]) == "REJECTED":
                owner_preview_review_comment = (
                    await connection.execute(
                        text(
                            """
                            SELECT review_comment
                            FROM review_task
                            WHERE skill_version_id = :skill_version_id
                              AND status = 'REJECTED'
                            ORDER BY reviewed_at DESC NULLS LAST, id DESC
                            LIMIT 1
                            """
                        ),
                        {"skill_version_id": owner_preview_version["id"]},
                    )
                ).scalar_one_or_none()

        promotion_blocked = (
            await connection.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM promotion_request
                        WHERE source_skill_id = :skill_id
                          AND status IN ('PENDING', 'APPROVED')
                    )
                    """
                ),
                {"skill_id": skill_row["id"]},
            )
        ).scalar_one()

        labels = (
            await connection.execute(
                text(
                    """
                    SELECT ld.slug,
                           ld.type,
                           COALESCE(lt.display_name, ld.slug) AS display_name
                    FROM skill_label sl
                    JOIN label_definition ld ON ld.id = sl.label_id
                    LEFT JOIN label_translation lt
                      ON lt.label_id = ld.id
                     AND LOWER(REPLACE(lt.locale, '_', '-')) = 'en'
                    WHERE sl.skill_id = :skill_id
                    ORDER BY sl.id ASC
                    """
                ),
                {"skill_id": skill_row["id"]},
            )
        ).mappings().all()

    row = dict(skill_row)
    row["published_version_id"] = published_version["id"] if published_version is not None else None
    row["published_version"] = published_version["version"] if published_version is not None else None
    row["published_version_status"] = published_version["status"] if published_version is not None else None
    row["owner_preview_version_id"] = owner_preview_version["id"] if owner_preview_version is not None else None
    row["owner_preview_version"] = owner_preview_version["version"] if owner_preview_version is not None else None
    row["owner_preview_version_status"] = owner_preview_version["status"] if owner_preview_version is not None else None
    row["owner_preview_review_comment"] = owner_preview_review_comment
    row["current_user_id"] = current_user_id
    row["namespace_role"] = namespace_role
    row["promotion_blocked"] = promotion_blocked
    label_rows = [
        {
            "slug": str(label["slug"]),
            "type": str(label["type"]),
            "displayName": str(label["display_name"]),
        }
        for label in labels
    ]
    return build_skill_detail_response(row, label_rows)


async def read_clawhub_skill_detail(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
) -> dict[str, object]:
    async with engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id,
                           s.slug,
                           s.display_name,
                           s.summary,
                           s.visibility,
                           s.status,
                           s.hidden,
                           s.created_at,
                           s.updated_at,
                           s.latest_version_id,
                           n.slug AS namespace,
                           n.status AS namespace_status,
                           pv.id AS published_version_id,
                           pv.version AS published_version,
                           pv.status AS published_version_status,
                           pv.published_at,
                           pv.changelog
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    LEFT JOIN LATERAL (
                        SELECT sv.id, sv.version, sv.status, sv.published_at, sv.changelog
                        FROM skill_version sv
                        WHERE sv.skill_id = s.id
                          AND sv.status = 'PUBLISHED'
                        ORDER BY
                          CASE WHEN sv.id = s.latest_version_id THEN 0 ELSE 1 END,
                          sv.published_at DESC NULLS LAST,
                          sv.created_at DESC NULLS LAST,
                          sv.id DESC
                        LIMIT 1
                    ) pv ON TRUE
                    WHERE n.slug = :namespace
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).mappings().one_or_none()

    if row is None:
        raise SkillResolveError("error.skill.notFound")
    if str(row["namespace_status"]) == "ARCHIVED":
        raise SkillResolveError("error.namespace.archived", status_code=403)
    if str(row["visibility"]) != "PUBLIC":
        raise SkillResolveError("error.skill.access.denied", status_code=403)

    published_version = None
    if row["published_version_id"] is not None:
        published_version = {
            "id": int(row["published_version_id"]),
            "version": str(row["published_version"]),
            "status": str(row["published_version_status"]),
        }

    return {
        "slug": str(row["slug"]),
        "displayName": row["display_name"],
        "summary": row["summary"],
        "namespace": str(row["namespace"]),
        "publishedVersion": published_version,
        "createdAt": to_java_instant(row["created_at"]),
        "publishedAt": to_java_instant(row["published_at"]),
        "updatedAt": to_java_instant(row["updated_at"]),
        "changelog": row["changelog"],
    }


async def read_skill_search(
    engine: AsyncEngine,
    keyword: str | None,
    namespace: str | None,
    labels: list[str],
    sort: str,
    page: int,
    size: int,
) -> dict[str, object]:
    normalized_keyword = normalize_search_keyword(keyword)
    ts_query = build_skill_search_ts_query(normalized_keyword)
    has_keyword = normalized_keyword is not None
    use_relevance_ordering = sort == "relevance" and has_keyword

    filters = [
        "d.visibility = 'PUBLIC'",
        "d.status = 'ACTIVE'",
        "s.status = 'ACTIVE'",
        "s.hidden = FALSE",
        "n.status <> 'ARCHIVED'",
    ]
    params: dict[str, object] = {
        "limit": size,
        "offset": page * size,
    }

    if namespace is not None and namespace.strip() != "":
        filters.append("d.namespace_slug = :namespace")
        params["namespace"] = namespace.strip()

    if labels:
        filters.append(
            """
            d.skill_id IN (
                SELECT sl.skill_id
                FROM skill_label sl
                JOIN label_definition ld ON ld.id = sl.label_id
                WHERE LOWER(ld.slug) = ANY(CAST(:label_slugs AS text[]))
            )
            """
        )
        params["label_slugs"] = labels

    if has_keyword:
        keyword_filters = []
        if ts_query is not None:
            keyword_filters.append("d.search_vector @@ to_tsquery('simple', :ts_query)")
            params["ts_query"] = ts_query
        keyword_filters.append("LOWER(d.title) LIKE :title_like")
        filters.append("(" + " OR ".join(keyword_filters) + ")")
        params["title_like"] = f"%{normalized_keyword}%"

    if sort == "downloads":
        order_sql = "s.download_count DESC, s.updated_at DESC, d.skill_id DESC"
    elif sort == "rating":
        order_sql = "s.rating_avg DESC, s.updated_at DESC, d.skill_id DESC"
    elif use_relevance_ordering:
        params["title_exact"] = normalized_keyword
        params["title_prefix"] = f"{normalized_keyword}%"
        if ts_query is not None:
            rank_sql = "ts_rank_cd(d.search_vector, to_tsquery('simple', :ts_query)) DESC,"
        else:
            rank_sql = ""
        order_sql = (
            "CASE "
            "WHEN LOWER(d.title) = :title_exact THEN 4 "
            "WHEN LOWER(d.title) LIKE :title_prefix THEN 3 "
            "WHEN LOWER(d.title) LIKE :title_like THEN 2 "
            f"ELSE 1 END DESC, {rank_sql} d.updated_at DESC, d.skill_id DESC"
        )
    else:
        order_sql = "s.updated_at DESC, d.skill_id DESC"

    where_sql = " AND ".join(filters)

    async with engine.connect() as connection:
        total = (
            await connection.execute(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM skill_search_document d
                    JOIN skill s ON s.id = d.skill_id
                    JOIN namespace n ON n.id = d.namespace_id
                    WHERE {where_sql}
                    """
                ),
                params,
            )
        ).scalar_one()

        rows = (
            await connection.execute(
                text(
                    f"""
                    SELECT s.id,
                           s.slug,
                           s.display_name,
                           s.summary,
                           s.visibility,
                           s.status,
                           s.download_count,
                           s.star_count,
                           s.rating_avg,
                           s.rating_count,
                           n.slug AS namespace,
                           s.updated_at,
                           pv.id AS published_version_id,
                           pv.version AS published_version,
                           pv.status AS published_version_status,
                           CASE WHEN pv.id IS NULL THEN 'NONE' ELSE 'PUBLISHED' END AS resolution_mode
                    FROM skill_search_document d
                    JOIN skill s ON s.id = d.skill_id
                    JOIN namespace n ON n.id = d.namespace_id
                    LEFT JOIN LATERAL (
                        SELECT sv.id, sv.version, sv.status
                        FROM skill_version sv
                        WHERE sv.skill_id = s.id
                          AND sv.status = 'PUBLISHED'
                        ORDER BY
                          CASE WHEN sv.id = s.latest_version_id THEN 0 ELSE 1 END,
                          sv.published_at DESC NULLS LAST,
                          sv.created_at DESC NULLS LAST,
                          sv.id DESC
                        LIMIT 1
                    ) pv ON TRUE
                    WHERE {where_sql}
                    ORDER BY {order_sql}
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            )
        ).mappings().all()

    return build_skill_search_response([dict(row) for row in rows], int(total), page, size)


async def read_skill_version_files(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    version: str,
    current_user_id: str | None = None,
) -> list[dict[str, object]]:
    async with engine.connect() as connection:
        skill_row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id, s.owner_id, s.namespace_id, s.visibility, s.latest_version_id
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).mappings().one_or_none()

        if skill_row is None:
            raise SkillResolveError("error.skill.notFound")

        namespace_role = await read_namespace_role(connection, int(skill_row["namespace_id"]), current_user_id)
        assert_skill_row_access(dict(skill_row), current_user_id, namespace_role)
        can_manage = can_manage_lifecycle_for_row(dict(skill_row), current_user_id, namespace_role)
        version_row = (
            await connection.execute(
                text(
                    """
                    SELECT id, status
                    FROM skill_version
                    WHERE skill_id = :skill_id
                      AND version = :version
                    LIMIT 1
                    """
                ),
                {"skill_id": skill_row["id"], "version": version},
            )
        ).mappings().one_or_none()

        if version_row is None:
            raise SkillResolveError("error.skill.version.notFound")
        if str(version_row["status"]) != "PUBLISHED" and not can_manage:
            raise SkillResolveError("error.skill.version.notPublished")

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


async def read_skill_version_compare(
    engine: AsyncEngine,
    storage_base_path: str,
    namespace: str,
    slug: str,
    from_version: str,
    to_version: str,
    current_user_id: str | None = None,
) -> dict[str, object]:
    if from_version == to_version:
        raise SkillResolveError("error.skill.version.compare.same")

    async with engine.connect() as connection:
        skill_row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id, s.owner_id, s.namespace_id, s.visibility, s.latest_version_id
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).mappings().one_or_none()

        if skill_row is None:
            raise SkillResolveError("error.skill.notFound")

        namespace_role = await read_namespace_role(connection, int(skill_row["namespace_id"]), current_user_id)
        assert_skill_row_access(dict(skill_row), current_user_id, namespace_role)
        can_manage = can_manage_lifecycle_for_row(dict(skill_row), current_user_id, namespace_role)
        version_rows = (
            await connection.execute(
                text(
                    """
                    SELECT id, version, status
                    FROM skill_version
                    WHERE skill_id = :skill_id
                      AND version = ANY(CAST(:versions AS varchar[]))
                    ORDER BY version ASC
                    """
                ),
                {"skill_id": skill_row["id"], "versions": [from_version, to_version]},
            )
        ).mappings().all()

        versions_by_name = {str(row["version"]): row for row in version_rows}
        missing_version = from_version if from_version not in versions_by_name else to_version
        if missing_version not in versions_by_name:
            raise SkillResolveError("error.skill.version.notFound")

        for selected_version in (from_version, to_version):
            version_row = versions_by_name[selected_version]
            if str(version_row["status"]) != "PUBLISHED" and not can_manage:
                raise SkillResolveError("error.skill.version.notPublished")

        from_id = int(versions_by_name[from_version]["id"])
        to_id = int(versions_by_name[to_version]["id"])
        file_rows = (
            await connection.execute(
                text(
                    """
                    SELECT version_id, file_path, file_size, content_type, sha256, storage_key
                    FROM skill_file
                    WHERE version_id = ANY(CAST(:version_ids AS bigint[]))
                    ORDER BY version_id ASC, file_path ASC
                    """
                ),
                {"version_ids": [from_id, to_id]},
            )
        ).mappings().all()

    rows_by_version: dict[int, dict[str, dict[str, object]]] = {from_id: {}, to_id: {}}
    for row in file_rows:
        rows_by_version[int(row["version_id"])][str(row["file_path"])] = {
            "file_path": str(row["file_path"]),
            "file_size": int(row["file_size"]),
            "content_type": row["content_type"],
            "sha256": str(row["sha256"]),
            "storage_key": str(row["storage_key"]),
        }

    changed_paths = {
        path
        for path in set(rows_by_version[from_id]) | set(rows_by_version[to_id])
        if rows_by_version[from_id].get(path, {}).get("sha256") != rows_by_version[to_id].get(path, {}).get("sha256")
    }
    files_by_version: dict[int, dict[str, dict[str, object]]] = {from_id: {}, to_id: {}}
    for version_id in (from_id, to_id):
        for path in changed_paths:
            row = rows_by_version[version_id].get(path)
            if row is None:
                continue
            files_by_version[version_id][path] = {
                "file_path": row["file_path"],
                "file_size": row["file_size"],
                "content_type": row["content_type"],
                "sha256": row["sha256"],
                "content": read_local_storage_text(storage_base_path, str(row["storage_key"])),
            }

    return build_compare_response(
        from_version,
        to_version,
        files_by_version[from_id],
        files_by_version[to_id],
    )


async def read_skill_tag_files(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    tag_name: str,
    current_user_id: str | None = None,
) -> list[dict[str, object]]:
    async with engine.connect() as connection:
        skill_row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id, s.owner_id, s.namespace_id, s.visibility, s.latest_version_id
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).mappings().one_or_none()

        if skill_row is None:
            raise SkillResolveError("error.skill.notFound")

        namespace_role = await read_namespace_role(connection, int(skill_row["namespace_id"]), current_user_id)
        assert_skill_row_access(dict(skill_row), current_user_id, namespace_role)
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


async def list_skill_tags(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    current_user_id: str | None = None,
) -> list[dict[str, object]]:
    async with engine.connect() as connection:
        skill_row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id, s.owner_id, s.namespace_id, s.visibility, s.latest_version_id
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND (
                          (CAST(:current_user_id AS varchar) IS NOT NULL AND s.owner_id = CAST(:current_user_id AS varchar))
                          OR (s.latest_version_id IS NOT NULL AND s.hidden = false)
                      )
                    ORDER BY
                      CASE
                        WHEN CAST(:current_user_id AS varchar) IS NOT NULL AND s.owner_id = CAST(:current_user_id AS varchar) THEN 0
                        ELSE 1
                      END,
                      CASE
                        WHEN s.latest_version_id IS NOT NULL AND s.hidden = false THEN 0
                        ELSE 1
                      END,
                      s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug, "current_user_id": current_user_id},
            )
        ).mappings().one_or_none()

        if skill_row is None:
            raise SkillResolveError("error.skill.notFound")

        namespace_role = await read_namespace_role(connection, int(skill_row["namespace_id"]), current_user_id)
        assert_skill_row_access(dict(skill_row), current_user_id, namespace_role)

        tag_rows = (
            await connection.execute(
                text(
                    """
                    SELECT id, tag_name, version_id, created_at
                    FROM skill_tag
                    WHERE skill_id = :skill_id
                    ORDER BY tag_name ASC
                    """
                ),
                {"skill_id": skill_row["id"]},
            )
        ).mappings().all()

    tags = [build_tag_response(dict(row)) for row in tag_rows]
    if skill_row.get("latest_version_id") is not None:
        tags.append(
            {
                "id": None,
                "tagName": "latest",
                "versionId": int(skill_row["latest_version_id"]),
                "createdAt": None,
            }
        )
    return tags


async def read_namespace_row_for_tag_write(connection: Any, namespace: str) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT n.id, n.status
                FROM namespace n
                WHERE n.slug = :namespace
                LIMIT 1
                """
            ),
            {"namespace": namespace},
        )
    ).mappings().one_or_none()
    if row is None:
        raise SkillResolveError("error.namespace.slug.notFound")
    return dict(row)


async def assert_namespace_tag_admin(connection: Any, namespace_id: int, user_id: str) -> None:
    role = await read_namespace_role(connection, namespace_id, user_id)
    if role is None:
        raise SkillResolveError("error.namespace.membership.required", status_code=403)
    if not is_namespace_manager(role):
        raise SkillResolveError("error.namespace.admin.required", status_code=403)


async def read_skill_row_for_tag_write(connection: Any, namespace_id: int, slug: str, current_user_id: str) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT s.id, s.owner_id, s.namespace_id, s.visibility, s.latest_version_id
                FROM skill s
                WHERE s.namespace_id = :namespace_id
                  AND s.slug = :slug
                  AND (
                      s.owner_id = :current_user_id
                      OR (s.latest_version_id IS NOT NULL AND s.hidden = false)
                  )
                ORDER BY
                  CASE
                    WHEN s.owner_id = :current_user_id THEN 0
                    ELSE 1
                  END,
                  CASE
                    WHEN s.latest_version_id IS NOT NULL AND s.hidden = false THEN 0
                    ELSE 1
                  END,
                  s.id ASC
                LIMIT 1
                """
            ),
            {"namespace_id": namespace_id, "slug": slug, "current_user_id": current_user_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise SkillResolveError("error.skill.notFound")
    return dict(row)


async def create_or_move_skill_tag(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    tag_name: str,
    target_version: str,
    user_id: str,
) -> dict[str, object]:
    if tag_name.lower() == "latest":
        raise SkillResolveError("error.skill.tag.latest.reserved")

    async with engine.begin() as connection:
        namespace_row = await read_namespace_row_for_tag_write(connection, namespace)
        await assert_namespace_tag_admin(connection, int(namespace_row["id"]), user_id)
        skill_row = await read_skill_row_for_tag_write(connection, int(namespace_row["id"]), slug, user_id)

        version_row = (
            await connection.execute(
                text(
                    """
                    SELECT id, status
                    FROM skill_version
                    WHERE skill_id = :skill_id
                      AND version = :target_version
                    LIMIT 1
                    """
                ),
                {"skill_id": skill_row["id"], "target_version": target_version},
            )
        ).mappings().one_or_none()
        if version_row is None:
            raise SkillResolveError("error.skill.version.notFound")
        if str(version_row["status"]) != "PUBLISHED":
            raise SkillResolveError("error.skill.tag.targetVersion.notPublished")

        existing_tag = (
            await connection.execute(
                text(
                    """
                    SELECT id, skill_id, tag_name, version_id
                    FROM skill_tag
                    WHERE skill_id = :skill_id
                      AND tag_name = :tag_name
                    LIMIT 1
                    """
                ),
                {"skill_id": skill_row["id"], "tag_name": tag_name},
            )
        ).mappings().one_or_none()

        if existing_tag is None:
            saved_row = (
                await connection.execute(
                    text(
                        """
                        INSERT INTO skill_tag (skill_id, tag_name, version_id, created_by)
                        VALUES (:skill_id, :tag_name, :version_id, :created_by)
                        RETURNING id, tag_name, version_id, created_at
                        """
                    ),
                    {
                        "skill_id": int(skill_row["id"]),
                        "tag_name": tag_name,
                        "version_id": int(version_row["id"]),
                        "created_by": user_id,
                    },
                )
            ).mappings().one()
        else:
            saved_row = (
                await connection.execute(
                    text(
                        """
                        UPDATE skill_tag
                        SET version_id = :version_id,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE skill_id = :skill_id
                          AND tag_name = :tag_name
                        RETURNING id, tag_name, version_id, created_at
                        """
                    ),
                    {
                        "skill_id": int(skill_row["id"]),
                        "tag_name": tag_name,
                        "version_id": int(version_row["id"]),
                    },
                )
            ).mappings().one()

    return build_tag_response(dict(saved_row))


async def delete_skill_tag(
    engine: AsyncEngine,
    namespace: str,
    slug: str,
    tag_name: str,
    user_id: str,
) -> dict[str, str]:
    if tag_name.lower() == "latest":
        raise SkillResolveError("error.skill.tag.latest.delete")

    async with engine.begin() as connection:
        namespace_row = await read_namespace_row_for_tag_write(connection, namespace)
        await assert_namespace_tag_admin(connection, int(namespace_row["id"]), user_id)
        skill_row = await read_skill_row_for_tag_write(connection, int(namespace_row["id"]), slug, user_id)
        tag_row = (
            await connection.execute(
                text(
                    """
                    SELECT id, skill_id, tag_name, version_id
                    FROM skill_tag
                    WHERE skill_id = :skill_id
                      AND tag_name = :tag_name
                    LIMIT 1
                    """
                ),
                {"skill_id": skill_row["id"], "tag_name": tag_name},
            )
        ).mappings().one_or_none()
        if tag_row is None:
            raise SkillResolveError("error.skill.tag.notFound")

        await connection.execute(
            text(
                """
                DELETE FROM skill_tag
                WHERE skill_id = :skill_id
                  AND tag_name = :tag_name
                """
            ),
            {"skill_id": skill_row["id"], "tag_name": tag_name},
        )

    return {"message": "Tag deleted"}


async def read_skill_version_file_content(
    engine: AsyncEngine,
    storage_base_path: str,
    namespace: str,
    slug: str,
    version: str,
    file_path: str,
    current_user_id: str | None = None,
) -> bytes:
    async with engine.connect() as connection:
        skill_row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id, s.owner_id, s.namespace_id, s.visibility, s.latest_version_id
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).mappings().one_or_none()

        if skill_row is None:
            raise SkillResolveError("error.skill.notFound")

        namespace_role = await read_namespace_role(connection, int(skill_row["namespace_id"]), current_user_id)
        assert_skill_row_access(dict(skill_row), current_user_id, namespace_role)
        can_manage = can_manage_lifecycle_for_row(dict(skill_row), current_user_id, namespace_role)
        version_row = (
            await connection.execute(
                text(
                    """
                    SELECT id, status
                    FROM skill_version
                    WHERE skill_id = :skill_id
                      AND version = :version
                    LIMIT 1
                    """
                ),
                {"skill_id": skill_row["id"], "version": version},
            )
        ).mappings().one_or_none()

        if version_row is None:
            raise SkillResolveError("error.skill.version.notFound")
        assert_version_file_content_access(dict(version_row), can_manage)

        file_row = (
            await connection.execute(
                text(
                    """
                    SELECT file_path, storage_key
                    FROM skill_file
                    WHERE version_id = :version_id
                      AND file_path = :file_path
                    LIMIT 1
                    """
                ),
                {"version_id": version_row["id"], "file_path": file_path},
            )
        ).mappings().one_or_none()

    if file_row is None:
        raise SkillResolveError("error.skill.file.notFound")
    return read_file_content_from_row(storage_base_path, dict(file_row))


async def read_skill_tag_file_content(
    engine: AsyncEngine,
    storage_base_path: str,
    namespace: str,
    slug: str,
    tag_name: str,
    file_path: str,
    current_user_id: str | None = None,
) -> bytes:
    async with engine.connect() as connection:
        skill_row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id, s.owner_id, s.namespace_id, s.visibility, s.latest_version_id
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).mappings().one_or_none()

        if skill_row is None:
            raise SkillResolveError("error.skill.notFound")

        namespace_role = await read_namespace_role(connection, int(skill_row["namespace_id"]), current_user_id)
        assert_skill_row_access(dict(skill_row), current_user_id, namespace_role)
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

        file_row = (
            await connection.execute(
                text(
                    """
                    SELECT file_path, storage_key
                    FROM skill_file
                    WHERE version_id = :version_id
                      AND file_path = :file_path
                    LIMIT 1
                    """
                ),
                {"version_id": version_row["id"], "file_path": file_path},
            )
        ).mappings().one_or_none()

    if file_row is None:
        raise SkillResolveError("error.skill.file.notFound")
    return read_file_content_from_row(storage_base_path, dict(file_row))


async def read_skill_download_version(
    engine: AsyncEngine,
    storage_base_path: str,
    namespace: str,
    slug: str,
    version: str,
    current_user_id: str | None = None,
) -> DownloadResult:
    async with engine.begin() as connection:
        skill_row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id, s.owner_id, s.namespace_id, s.slug, s.display_name
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).mappings().one_or_none()

        if skill_row is None:
            raise SkillResolveError("error.skill.notFound")

        namespace_role = await read_namespace_role(connection, int(skill_row["namespace_id"]), current_user_id)
        can_manage = can_manage_lifecycle_for_row(dict(skill_row), current_user_id, namespace_role)
        version_row = (
            await connection.execute(
                text(
                    """
                    SELECT id, version, status
                    FROM skill_version
                    WHERE skill_id = :skill_id
                      AND version = :version
                    LIMIT 1
                    """
                ),
                {"skill_id": skill_row["id"], "version": version},
            )
        ).mappings().one_or_none()

        if version_row is None:
            raise SkillResolveError("error.skill.version.notFound")
        assert_download_access(dict(version_row), can_manage)

        file_rows = (
            await connection.execute(
                text(
                    """
                    SELECT file_path, storage_key
                    FROM skill_file
                    WHERE version_id = :version_id
                    ORDER BY file_path ASC
                    """
                ),
                {"version_id": version_row["id"]},
            )
        ).mappings().all()

        row = {
            "skill_id": int(skill_row["id"]),
            "version_id": int(version_row["id"]),
            "version": str(version_row["version"]),
            "status": str(version_row["status"]),
            "display_name": skill_row["display_name"],
            "slug": str(skill_row["slug"]),
            "content_type": "application/zip",
            "content_length": None,
        }
        result = read_bundle_or_build_fallback_zip(storage_base_path, row, [dict(file_row) for file_row in file_rows])

        if str(version_row["status"]) == "PUBLISHED":
            await increment_published_download_counters(connection, int(skill_row["id"]), int(version_row["id"]))

    return result


async def read_skill_download_latest(
    engine: AsyncEngine,
    storage_base_path: str,
    namespace: str,
    slug: str,
    current_user_id: str | None = None,
) -> DownloadResult:
    async with engine.connect() as connection:
        version = (
            await connection.execute(
                text(
                    """
                    SELECT sv.version
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    JOIN skill_version sv ON sv.id = s.latest_version_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug},
            )
        ).scalar_one_or_none()

    if version is None:
        raise SkillResolveError("error.skill.version.latest.unavailable")
    return await read_skill_download_version(engine, storage_base_path, namespace, slug, str(version), current_user_id)


async def read_skill_download_tag(
    engine: AsyncEngine,
    storage_base_path: str,
    namespace: str,
    slug: str,
    tag_name: str,
    current_user_id: str | None = None,
) -> DownloadResult:
    async with engine.connect() as connection:
        version = (
            await connection.execute(
                text(
                    """
                    SELECT sv.version
                    FROM skill s
                    JOIN namespace n ON n.id = s.namespace_id
                    JOIN skill_tag st ON st.skill_id = s.id
                    JOIN skill_version sv ON sv.id = st.version_id
                    WHERE n.slug = :namespace
                      AND n.status = 'ACTIVE'
                      AND s.slug = :slug
                      AND s.status = 'ACTIVE'
                      AND s.latest_version_id IS NOT NULL
                      AND s.hidden = false
                      AND st.tag_name = :tag_name
                    ORDER BY s.id ASC
                    LIMIT 1
                    """
                ),
                {"namespace": namespace, "slug": slug, "tag_name": tag_name},
            )
        ).scalar_one_or_none()

    if version is None:
        raise SkillResolveError("error.skill.tag.notFound")
    return await read_skill_download_version(engine, storage_base_path, namespace, slug, str(version), current_user_id)


async def _resolve_reader_result(result: Any | Awaitable[Any]) -> Any:
    if isawaitable(result):
        return await result
    return result


async def resolve_clawhub_download_coordinate(
    request: Request,
    slug: str,
    current_user_id: str | None,
) -> tuple[str, str]:
    reader = getattr(request.app.state, "clawhub_download_coordinate_reader", None)
    if reader is not None:
        coordinate = reader(slug, current_user_id)
        coordinate = await _resolve_reader_result(coordinate)
    else:
        legacy_reader = getattr(request.app.state, "clawhub_legacy_slug_reader", None)
        if legacy_reader is not None:
            coordinate = legacy_reader(slug)
            coordinate = await _resolve_reader_result(coordinate)
        elif "--" in slug:
            coordinate = from_clawhub_canonical_slug(slug)
        else:
            db_engine = getattr(request.app.state, "db_engine", None)
            coordinate = (
                from_clawhub_canonical_slug(slug)
                if db_engine is None
                else await read_clawhub_legacy_slug_coordinate(db_engine, slug)
            )

    if isinstance(coordinate, dict):
        return str(coordinate["namespace"]), str(coordinate["slug"])
    namespace, skill_slug = coordinate
    return str(namespace), str(skill_slug)


def build_download_redirect(namespace: str, slug: str, version: str | None) -> RedirectResponse:
    namespace_path = quote(namespace, safe="")
    slug_path = quote(slug, safe="")
    if version is None or version == "latest":
        location = f"/api/v1/skills/{namespace_path}/{slug_path}/download"
    else:
        location = (
            f"/api/v1/skills/{namespace_path}/{slug_path}/versions/"
            f"{quote(version, safe='')}/download"
        )
    return RedirectResponse(location, status_code=302)


@router.get("/api/v1/download")
async def download_clawhub_skill_by_query(
    request: Request,
    slug: str,
    version: str | None = "latest",
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> RedirectResponse:
    current_user_id = normalized_current_user_id(mock_user_id)
    try:
        namespace, skill_slug = await resolve_clawhub_download_coordinate(request, slug, current_user_id)
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return build_download_redirect(namespace, skill_slug, version)


@router.get("/api/v1/download/{canonicalSlug}")
async def download_clawhub_skill_by_path(
    canonicalSlug: str,
    version: str | None = "latest",
) -> RedirectResponse:
    namespace, slug = from_clawhub_canonical_slug(canonicalSlug)
    return build_download_redirect(namespace, slug, version)


@router.get("/api/web/skills")
async def search_skills(
    request: Request,
    q: str | None = None,
    namespace: str | None = None,
    label: list[str] = Query(default_factory=list),
    sort: str | None = None,
    page: str | None = None,
    size: str | None = None,
) -> dict[str, object]:
    normalized_labels = normalize_label_slugs(label)
    normalized_sort = normalize_search_sort(sort)
    normalized_page = parse_non_negative_int(page, 0)
    normalized_size = parse_positive_int(size, 20)
    reader = getattr(request.app.state, "skill_search_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(
                reader(
                    keyword=q,
                    namespace=namespace,
                    labels=normalized_labels,
                    sort=normalized_sort,
                    page=normalized_page,
                    size=normalized_size,
                )
            )
        else:
            data = await read_skill_search(
                request.app.state.db_engine,
                keyword=q,
                namespace=namespace,
                labels=normalized_labels,
                sort=normalized_sort,
                page=normalized_page,
                size=normalized_size,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("获取成功", data, request)


@router.get("/api/v1/search")
async def search_clawhub_skills(
    request: Request,
    q: str = "",
    page: int = 0,
    limit: int = 20,
) -> dict[str, object]:
    normalized_page = max(page, 0)
    normalized_limit = limit if limit > 0 else 20
    sort = "newest" if q.strip() == "" else "relevance"
    reader = getattr(request.app.state, "clawhub_search_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(
                reader(
                    keyword=q,
                    namespace=None,
                    labels=[],
                    sort=sort,
                    page=normalized_page,
                    size=normalized_limit,
                )
            )
        else:
            data = await read_skill_search(
                request.app.state.db_engine,
                keyword=q,
                namespace=None,
                labels=[],
                sort=sort,
                page=normalized_page,
                size=normalized_limit,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return build_clawhub_search_response(data)


@router.get("/api/cli/v1/skills/search")
async def search_cli_skills(
    request: Request,
    q: str | None = None,
    limit: int = 20,
) -> dict[str, object]:
    normalized_limit = limit if limit > 0 else 20
    reader = getattr(request.app.state, "cli_skill_search_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(
                reader(
                    keyword=q,
                    namespace=None,
                    labels=[],
                    sort="newest",
                    page=0,
                    size=normalized_limit,
                )
            )
        else:
            data = await read_skill_search(
                request.app.state.db_engine,
                keyword=q,
                namespace=None,
                labels=[],
                sort="newest",
                page=0,
                size=normalized_limit,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u83b7\u53d6\u6210\u529f", build_cli_search_response(data, normalized_limit), request)


@router.get("/api/v1/resolve")
async def resolve_clawhub_skill_by_query(
    request: Request,
    slug: str,
    version: str | None = None,
    hash: str | None = Query(default=None, alias="hash"),
) -> dict[str, object]:
    try:
        if "--" in slug:
            namespace, skill_slug = from_clawhub_canonical_slug(slug)
        else:
            legacy_reader = getattr(request.app.state, "clawhub_legacy_slug_reader", None)
            if legacy_reader is not None:
                coordinate = legacy_reader(slug)
                if isawaitable(coordinate):
                    coordinate = await coordinate
                if isinstance(coordinate, dict):
                    namespace = str(coordinate["namespace"])
                    skill_slug = str(coordinate["slug"])
                else:
                    namespace, skill_slug = coordinate
            else:
                db_engine = getattr(request.app.state, "db_engine", None)
                if db_engine is None:
                    namespace, skill_slug = from_clawhub_canonical_slug(slug)
                else:
                    namespace, skill_slug = await read_clawhub_legacy_slug_coordinate(db_engine, slug)

        version_selector, tag_selector = clawhub_resolve_selectors(version, default_latest=False)
        reader = getattr(request.app.state, "skill_resolve_reader", None)
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, skill_slug, version_selector, tag_selector, hash))
        else:
            data = await read_skill_resolve(
                request.app.state.db_engine,
                namespace,
                skill_slug,
                version_selector,
                tag_selector,
                hash,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return build_clawhub_resolve_response(data)


@router.get("/api/cli/v1/skills/{namespace}/{slug}/resolve")
async def resolve_cli_skill(
    request: Request,
    namespace: str,
    slug: str,
    version: str | None = None,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    current_user_id = normalized_current_user_id(mock_user_id)
    reader = getattr(request.app.state, "skill_resolve_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, version, None, None, current_user_id))
        else:
            data = await read_skill_resolve(
                request.app.state.db_engine,
                namespace,
                slug,
                version,
                None,
                None,
                current_user_id,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u83b7\u53d6\u6210\u529f", build_cli_resolve_response(data), request)


@router.get("/api/v1/resolve/{canonicalSlug}")
async def resolve_clawhub_skill_by_path(
    request: Request,
    canonicalSlug: str,
    version: str | None = "latest",
) -> dict[str, object]:
    namespace, slug = from_clawhub_canonical_slug(canonicalSlug)
    version_selector, tag_selector = clawhub_resolve_selectors(version, default_latest=True)
    reader = getattr(request.app.state, "skill_resolve_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, version_selector, tag_selector, None))
        else:
            data = await read_skill_resolve(
                request.app.state.db_engine,
                namespace,
                slug,
                version_selector,
                tag_selector,
                None,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return build_clawhub_resolve_response(data)


@router.get("/api/v1/skills")
async def list_clawhub_skills(
    request: Request,
    page: str | None = None,
    limit: str | None = None,
    sort: str | None = None,
) -> dict[str, object]:
    normalized_page = parse_non_negative_int(page, 0)
    normalized_limit = parse_positive_int(limit, 25)
    normalized_sort = normalize_search_sort(sort)
    reader = getattr(request.app.state, "clawhub_skills_list_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(
                reader(
                    keyword="",
                    namespace=None,
                    labels=[],
                    sort=normalized_sort,
                    page=normalized_page,
                    size=normalized_limit,
                )
            )
        else:
            data = await read_skill_search(
                request.app.state.db_engine,
                keyword="",
                namespace=None,
                labels=[],
                sort=normalized_sort,
                page=normalized_page,
                size=normalized_limit,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return build_clawhub_skills_list_response(data)


@router.get("/api/v1/skills/{canonicalSlug}")
async def get_clawhub_skill_detail(request: Request, canonicalSlug: str) -> dict[str, object]:
    namespace, slug = from_clawhub_canonical_slug(canonicalSlug)
    reader = getattr(request.app.state, "clawhub_skill_detail_reader", None)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug))
        else:
            data = await read_clawhub_skill_detail(request.app.state.db_engine, namespace, slug)
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return build_clawhub_skill_detail_response(data)


def clawhub_delete_placeholder_response(mock_user_id: str | None) -> dict[str, bool]:
    if normalized_current_user_id(mock_user_id) is None:
        raise HTTPException(status_code=401, detail="error.auth.required")
    return {"ok": True}


@router.delete("/api/v1/skills/{canonicalSlug}")
async def delete_clawhub_skill_placeholder(
    canonicalSlug: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, bool]:
    return clawhub_delete_placeholder_response(x_mock_user_id)


@router.post("/api/v1/skills/{canonicalSlug}/undelete")
async def undelete_clawhub_skill_placeholder(
    canonicalSlug: str,
    x_mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, bool]:
    return clawhub_delete_placeholder_response(x_mock_user_id)


@router.get("/api/v1/skills/{namespace}/{slug}")
@router.get("/api/web/skills/{namespace}/{slug}")
async def get_skill_detail(
    namespace: str,
    slug: str,
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    reader = getattr(request.app.state, "skill_detail_reader", None)
    current_user_id = mock_user_id.strip() if mock_user_id is not None and mock_user_id.strip() != "" else None
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, current_user_id))
        else:
            data = await read_skill_detail(request.app.state.db_engine, namespace, slug, current_user_id)
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("获取成功", data, request)


@router.get("/api/v1/skills/{namespace}/{slug}/resolve")
@router.get("/api/web/skills/{namespace}/{slug}/resolve")
async def resolve_skill_version(
    namespace: str,
    slug: str,
    request: Request,
    version: str | None = None,
    tag: str | None = None,
    hash_value: str | None = Query(default=None, alias="hash"),
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    reader = getattr(request.app.state, "skill_resolve_reader", None)
    current_user_id = normalized_current_user_id(mock_user_id)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, version, tag, hash_value, current_user_id))
        else:
            data = await read_skill_resolve(
                request.app.state.db_engine,
                namespace,
                slug,
                version,
                tag,
                hash_value,
                current_user_id,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("获取成功", data, request)


@router.get("/api/v1/skills/{namespace}/{slug}/versions/compare")
@router.get("/api/web/skills/{namespace}/{slug}/versions/compare")
async def compare_skill_versions(
    namespace: str,
    slug: str,
    request: Request,
    from_version: str = Query(alias="from"),
    to_version: str = Query(alias="to"),
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    reader = getattr(request.app.state, "skill_version_compare_reader", None)
    current_user_id = normalized_current_user_id(mock_user_id)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, from_version, to_version, current_user_id))
        else:
            data = await read_skill_version_compare(
                request.app.state.db_engine,
                request.app.state.settings.storage_base_path,
                namespace,
                slug,
                from_version,
                to_version,
                current_user_id,
            )
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
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    reader = getattr(request.app.state, "skill_version_detail_reader", None)
    current_user_id = mock_user_id.strip() if mock_user_id is not None and mock_user_id.strip() != "" else None
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, version, current_user_id))
        else:
            data = await read_skill_version_detail(
                request.app.state.db_engine,
                namespace,
                slug,
                version,
                current_user_id,
            )
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
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    reader = getattr(request.app.state, "skill_versions_reader", None)
    page, size = normalize_page_request(page, size)
    current_user_id = mock_user_id.strip() if mock_user_id is not None and mock_user_id.strip() != "" else None
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, page, size, current_user_id))
        else:
            data = await read_skill_versions(request.app.state.db_engine, namespace, slug, page, size, current_user_id)
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
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    reader = getattr(request.app.state, "skill_version_files_reader", None)
    current_user_id = normalized_current_user_id(mock_user_id)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, version, current_user_id))
        else:
            data = await read_skill_version_files(
                request.app.state.db_engine,
                namespace,
                slug,
                version,
                current_user_id,
            )
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
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    reader = getattr(request.app.state, "skill_tag_files_reader", None)
    current_user_id = normalized_current_user_id(mock_user_id)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, tagName, current_user_id))
        else:
            data = await read_skill_tag_files(
                request.app.state.db_engine,
                namespace,
                slug,
                tagName,
                current_user_id,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok("获取成功", data, request)


@router.get("/api/v1/skills/{namespace}/{slug}/tags")
@router.get("/api/web/skills/{namespace}/{slug}/tags")
async def list_skill_tags_route(
    namespace: str,
    slug: str,
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    reader = getattr(request.app.state, "skill_tags_reader", None)
    current_user_id = normalized_current_user_id(mock_user_id)
    try:
        if reader is not None:
            data = await _resolve_reader_result(reader(namespace, slug, current_user_id))
        else:
            data = await list_skill_tags(request.app.state.db_engine, namespace, slug, current_user_id)
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


@router.put("/api/v1/skills/{namespace}/{slug}/tags/{tagName}")
@router.put("/api/web/skills/{namespace}/{slug}/tags/{tagName}")
async def create_or_move_skill_tag_route(
    namespace: str,
    slug: str,
    tagName: str,
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    current_user_id = normalized_current_user_id(mock_user_id)
    if current_user_id is None:
        raise HTTPException(status_code=401, detail="error.auth.required")
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="error.validation")
    body_tag_name = str(payload.get("tagName") or "").strip()
    target_version = str(payload.get("targetVersion") or "").strip()
    if body_tag_name == "" or target_version == "":
        raise HTTPException(status_code=400, detail="error.validation")

    writer = getattr(request.app.state, "skill_tag_writer", None)
    try:
        if writer is not None:
            data = await _resolve_reader_result(writer(namespace, slug, tagName, target_version, current_user_id))
        else:
            data = await create_or_move_skill_tag(
                request.app.state.db_engine,
                namespace,
                slug,
                tagName,
                target_version,
                current_user_id,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u66f4\u65b0\u6210\u529f", data, request)


@router.delete("/api/v1/skills/{namespace}/{slug}/tags/{tagName}")
@router.delete("/api/web/skills/{namespace}/{slug}/tags/{tagName}")
async def delete_skill_tag_route(
    namespace: str,
    slug: str,
    tagName: str,
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, object]:
    current_user_id = normalized_current_user_id(mock_user_id)
    if current_user_id is None:
        raise HTTPException(status_code=401, detail="error.auth.required")
    writer = getattr(request.app.state, "skill_tag_delete_writer", None)
    try:
        if writer is not None:
            data = await _resolve_reader_result(writer(namespace, slug, tagName, current_user_id))
        else:
            data = await delete_skill_tag(request.app.state.db_engine, namespace, slug, tagName, current_user_id)
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("\u5220\u9664\u6210\u529f", data, request)


@router.get("/api/v1/skills/{namespace}/{slug}/versions/{version}/file")
@router.get("/api/web/skills/{namespace}/{slug}/versions/{version}/file")
async def get_skill_version_file_content(
    namespace: str,
    slug: str,
    version: str,
    request: Request,
    path: str = Query(...),
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> Response:
    reader = getattr(request.app.state, "skill_version_file_content_reader", None)
    current_user_id = normalized_current_user_id(mock_user_id)
    try:
        if reader is not None:
            content = await _resolve_reader_result(reader(namespace, slug, version, path, current_user_id))
        else:
            content = await read_skill_version_file_content(
                request.app.state.db_engine,
                request.app.state.settings.storage_base_path,
                namespace,
                slug,
                version,
                path,
                current_user_id,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return Response(content=content, media_type="application/octet-stream")


@router.get("/api/v1/skills/{namespace}/{slug}/tags/{tagName}/file")
@router.get("/api/web/skills/{namespace}/{slug}/tags/{tagName}/file")
async def get_skill_tag_file_content(
    namespace: str,
    slug: str,
    tagName: str,
    request: Request,
    path: str = Query(...),
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> Response:
    reader = getattr(request.app.state, "skill_tag_file_content_reader", None)
    current_user_id = normalized_current_user_id(mock_user_id)
    try:
        if reader is not None:
            content = await _resolve_reader_result(reader(namespace, slug, tagName, path, current_user_id))
        else:
            content = await read_skill_tag_file_content(
                request.app.state.db_engine,
                request.app.state.settings.storage_base_path,
                namespace,
                slug,
                tagName,
                path,
                current_user_id,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return Response(content=content, media_type="application/octet-stream")


@router.get("/api/v1/skills/{namespace}/{slug}/download")
@router.get("/api/web/skills/{namespace}/{slug}/download")
async def download_skill_latest(
    namespace: str,
    slug: str,
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> Response:
    reader = getattr(request.app.state, "skill_download_latest_reader", None)
    current_user_id = normalized_current_user_id(mock_user_id)
    try:
        if reader is not None:
            result = await _resolve_reader_result(reader(namespace, slug, current_user_id))
        else:
            result = await read_skill_download_latest(
                request.app.state.db_engine,
                request.app.state.settings.storage_base_path,
                namespace,
                slug,
                current_user_id,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return build_download_response(result)


@router.get("/api/v1/skills/{namespace}/{slug}/versions/{version}/download")
@router.get("/api/web/skills/{namespace}/{slug}/versions/{version}/download")
async def download_skill_version(
    namespace: str,
    slug: str,
    version: str,
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> Response:
    reader = getattr(request.app.state, "skill_download_version_reader", None)
    current_user_id = normalized_current_user_id(mock_user_id)
    try:
        if reader is not None:
            result = await _resolve_reader_result(reader(namespace, slug, version, current_user_id))
        else:
            result = await read_skill_download_version(
                request.app.state.db_engine,
                request.app.state.settings.storage_base_path,
                namespace,
                slug,
                version,
                current_user_id,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return build_download_response(result)


@router.get("/api/cli/v1/skills/{namespace}/{slug}/download")
async def download_cli_skill_latest(
    namespace: str,
    slug: str,
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> Response:
    return await download_skill_latest(namespace, slug, request, mock_user_id)


@router.get("/api/cli/v1/skills/{namespace}/{slug}/versions/{version}/download")
async def download_cli_skill_version(
    namespace: str,
    slug: str,
    version: str,
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> Response:
    return await download_skill_version(namespace, slug, version, request, mock_user_id)


@router.get("/api/v1/skills/{namespace}/{slug}/tags/{tagName}/download")
@router.get("/api/web/skills/{namespace}/{slug}/tags/{tagName}/download")
async def download_skill_tag(
    namespace: str,
    slug: str,
    tagName: str,
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> Response:
    reader = getattr(request.app.state, "skill_download_tag_reader", None)
    current_user_id = normalized_current_user_id(mock_user_id)
    try:
        if reader is not None:
            result = await _resolve_reader_result(reader(namespace, slug, tagName, current_user_id))
        else:
            result = await read_skill_download_tag(
                request.app.state.db_engine,
                request.app.state.settings.storage_base_path,
                namespace,
                slug,
                tagName,
                current_user_id,
            )
    except SkillResolveError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return build_download_response(result)

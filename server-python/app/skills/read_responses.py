from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.skills.compliance_projection import (
    compliance_snapshot_from_parsed_metadata,
    compliance_snapshot_from_value,
)
from app.skills.read_access import can_manage_lifecycle_for_row
from app.source_import.source import source_provenance_from_row


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
                "complianceSnapshot": compliance_snapshot_from_value(row.get("compliance_snapshot_json")),
            }
            for row in rows
        ],
        "total": total,
        "page": page,
        "size": size,
    }


def build_version_attribution_response(
    row: dict[str, Any],
) -> dict[str, object] | None:
    attribution_type = row.get("version_attribution_type")
    submitted_by = row.get("version_submitted_by")
    submitted_at = row.get("version_submitted_at")
    if (
        attribution_type not in {"NATIVE_SUBMISSION", "OSS_IMPORT"}
        or submitted_by is None
        or submitted_at is None
    ):
        return None
    return {
        "type": str(attribution_type),
        "submittedBy": str(submitted_by),
        "submittedByName": (
            str(row["version_submitted_by_name"])
            if row.get("version_submitted_by_name") is not None
            else None
        ),
        "submittedAt": to_java_instant(submitted_at),
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
        "sourceProvenance": source_provenance_from_row(row),
        "versionAttribution": build_version_attribution_response(row),
        "complianceSnapshot": compliance_snapshot_from_parsed_metadata(row.get("parsed_metadata_json")),
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
    can_manage_lifecycle = can_manage_lifecycle_for_row(row, current_user_id, namespace_role)
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
        "platformAdminOverride": bool(row.get("platform_read_override", False)),
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
        "complianceSnapshot": compliance_snapshot_from_value(
            row.get("published_version_compliance_snapshot_json")
        ),
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


__all__ = [
    "build_skill_detail_response",
    "build_skill_search_response",
    "build_skill_summary_response",
    "build_tag_response",
    "build_version_attribution_response",
    "build_version_detail_response",
    "build_versions_page_response",
    "normalize_page_request",
    "paginate_rows",
    "to_epoch_millis",
    "to_java_instant",
    "to_lifecycle_version",
]

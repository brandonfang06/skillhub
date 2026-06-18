from __future__ import annotations

from app.skills.read_responses import to_epoch_millis


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


__all__ = [
    "build_clawhub_resolve_response",
    "build_clawhub_search_response",
    "build_clawhub_skill_detail_response",
    "build_clawhub_skills_list_response",
    "build_cli_resolve_response",
    "build_cli_search_response",
    "clawhub_resolve_selectors",
    "from_clawhub_canonical_slug",
    "to_clawhub_canonical_slug",
]

from __future__ import annotations

from hashlib import sha256
from typing import Any
from urllib.parse import quote

from app.skills.read_files import SkillResolveError


VersionRow = dict[str, Any]
FileRow = dict[str, Any]


def has_text(value: str | None) -> bool:
    return value is not None and value.strip() != ""


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


__all__ = [
    "build_resolve_response",
    "compute_version_fingerprint",
    "find_latest_version",
    "has_text",
    "matched_value",
    "resolve_version_row",
]

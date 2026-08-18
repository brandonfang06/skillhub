from __future__ import annotations

import hashlib
import re
from typing import Any, cast
from urllib.parse import quote, urlsplit

from app.publish.package import PackageEntry
from app.source_import.contracts import SourceRefType, SourceRepository, SourceRevision


GITHUB_OWNER_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
GITHUB_REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?")
COMMIT_SHA_PATTERN = re.compile(r"[0-9a-fA-F]{40}")
SOURCE_REF_TYPES: set[str] = {"TAG", "BRANCH", "COMMIT"}


class SourceInputError(ValueError):
    pass


def canonicalize_github_repository(raw_url: str) -> SourceRepository:
    value = raw_url.strip()
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
    ):
        raise SourceInputError("Only credential-free HTTPS github.com repository URLs are supported")

    path_parts = parsed.path.strip("/").split("/")
    if len(path_parts) != 2:
        raise SourceInputError("GitHub repository URL must contain exactly owner and repository")
    owner, repository = path_parts
    if repository.lower().endswith(".git"):
        repository = repository[:-4]
    if not GITHUB_OWNER_PATTERN.fullmatch(owner) or not GITHUB_REPOSITORY_PATTERN.fullmatch(repository):
        raise SourceInputError("GitHub owner or repository cannot form a SkillHub namespace")

    normalized_owner = owner.lower()
    normalized_repository = repository.lower()
    namespace_slug = f"oss-{normalized_owner}-{normalized_repository}"
    if len(namespace_slug) > 64:
        raise SourceInputError("Derived SkillHub namespace slug exceeds 64 characters")
    return SourceRepository(
        owner=normalized_owner,
        repository=normalized_repository,
        canonical_url=f"https://github.com/{normalized_owner}/{normalized_repository}",
        namespace_slug=namespace_slug,
        namespace_display_name=f"OSS-{normalized_owner}-{normalized_repository}",
    )


def normalize_source_path(raw_path: str) -> str:
    value = raw_path.strip()
    if value == ".":
        return value
    if not value or value.startswith("/") or "\\" in value:
        raise SourceInputError("Source path must be repository-relative POSIX path")
    parts = [part for part in value.split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts) or parts[0] == ".git":
        raise SourceInputError("Source path contains an unsafe segment")
    return "/".join(parts)


def validate_source_revision(commit_sha: str, ref_type: str, source_ref: str | None) -> SourceRevision:
    normalized_sha = commit_sha.strip().lower()
    normalized_type = ref_type.strip().upper()
    normalized_ref = source_ref.strip() if source_ref is not None else None
    if not COMMIT_SHA_PATTERN.fullmatch(normalized_sha):
        raise SourceInputError("Repository revision must be a 40-character hexadecimal commit SHA")
    if normalized_type not in SOURCE_REF_TYPES:
        raise SourceInputError("Unsupported source ref type")
    if normalized_type == "COMMIT" and normalized_ref is not None:
        raise SourceInputError("Commit source ref type cannot include a source ref")
    if normalized_type in {"TAG", "BRANCH"} and not normalized_ref:
        raise SourceInputError("Tag and branch source ref types require a source ref")
    return SourceRevision(
        commit_sha=normalized_sha,
        ref_type=cast(SourceRefType, normalized_type),
        ref=normalized_ref,
    )


def build_browse_url(repository: SourceRepository, revision: SourceRevision, source_path: str) -> str:
    normalized_path = normalize_source_path(source_path)
    base = f"{repository.canonical_url}/tree/{revision.commit_sha}"
    if normalized_path == ".":
        return base
    return f"{base}/{quote(normalized_path, safe='/')}"


def source_provenance_from_row(row: dict[str, Any]) -> dict[str, object] | None:
    repository_url = row.get("source_repository_url")
    if repository_url is None:
        return None
    repository = canonicalize_github_repository(str(repository_url))
    revision = validate_source_revision(
        str(row["source_revision_sha"]),
        str(row["source_ref_type"]),
        str(row["source_ref"]) if row.get("source_ref") is not None else None,
    )
    source_path = normalize_source_path(str(row["source_path"]))
    result: dict[str, object] = {
        "repositoryUrl": repository.canonical_url,
        "repositoryRevisionSha": revision.commit_sha,
        "sourceRefType": revision.ref_type,
        "sourcePath": source_path,
        "contentFingerprint": str(row["source_content_fingerprint"]),
        "browseUrl": build_browse_url(repository, revision, source_path),
    }
    if revision.ref is not None:
        result["sourceRef"] = revision.ref
    return result


def content_fingerprint(entries: list[PackageEntry]) -> str:
    digest = hashlib.sha256()
    for entry in sorted(entries, key=lambda item: item.path):
        file_digest = hashlib.sha256(entry.content).hexdigest()
        digest.update(entry.path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_digest.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()

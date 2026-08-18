from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


class SourceError(ValueError):
    pass


@dataclass(frozen=True)
class GitHubRepository:
    canonical_url: str
    owner: str
    repository: str
    namespace_slug: str
    namespace_display_name: str


_OWNER = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
_REPOSITORY = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?")


def canonicalize_repository(raw_url: str) -> GitHubRepository:
    parsed = urlsplit(raw_url.strip())
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
    ):
        raise SourceError("Only credential-free HTTPS github.com repository URLs are supported")
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 2:
        raise SourceError("GitHub repository URL must contain exactly owner and repository")
    owner, repository = parts
    if repository.lower().endswith(".git"):
        repository = repository[:-4]
    if not _OWNER.fullmatch(owner) or not _REPOSITORY.fullmatch(repository):
        raise SourceError("Invalid GitHub owner or repository")
    owner = owner.lower()
    repository = repository.lower()
    namespace_slug = f"oss-{owner}-{repository}"
    if len(namespace_slug) > 64:
        raise SourceError("Derived namespace exceeds 64 characters")
    return GitHubRepository(
        canonical_url=f"https://github.com/{owner}/{repository}",
        owner=owner,
        repository=repository,
        namespace_slug=namespace_slug,
        namespace_display_name=f"OSS-{owner}-{repository}",
    )


def verify_checkout_revision(project_dir: Path, expected_sha: str) -> None:
    try:
        actual = subprocess.run(
            ["git", "-C", str(project_dir), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip().lower()
    except (OSError, subprocess.SubprocessError) as exc:
        raise SourceError("Unable to read Git checkout revision") from exc
    if actual != expected_sha.lower():
        raise SourceError(f"Git checkout HEAD {actual} does not match CI_COMMIT_SHA {expected_sha.lower()}")

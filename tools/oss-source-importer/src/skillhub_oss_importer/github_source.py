from __future__ import annotations

import os
import re
import subprocess
from base64 import b64encode
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


@dataclass(frozen=True)
class SourceCheckout:
    checkout_dir: Path
    commit_sha: str
    ref_type: str
    source_ref: str | None


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


def clone_repository(
    clone_url: str,
    destination: Path,
    branch: str,
    ref_type: str,
    source_ref: str | None,
    job_token: str,
) -> SourceCheckout:
    if destination.exists():
        raise SourceError("Git checkout destination already exists")
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GIT_LFS_SKIP_SMUDGE"] = "1"
    try:
        config_count = int(environment.get("GIT_CONFIG_COUNT", "0"))
    except ValueError as exc:
        raise SourceError("Invalid inherited Git configuration") from exc
    if config_count < 0:
        raise SourceError("Invalid inherited Git configuration")
    credentials = b64encode(f"gitlab-ci-token:{job_token}".encode()).decode()
    for key, value in (
        ("http.extraHeader", f"Authorization: Basic {credentials}"),
        ("http.followRedirects", "false"),
    ):
        environment[f"GIT_CONFIG_KEY_{config_count}"] = key
        environment[f"GIT_CONFIG_VALUE_{config_count}"] = value
        config_count += 1
    environment["GIT_CONFIG_COUNT"] = str(config_count)
    try:
        destination.mkdir(parents=False)
        for command in (
            ["git", "init", "-q", str(destination)],
            ["git", "-C", str(destination), "remote", "add", "origin", clone_url],
            [
                "git",
                "-C",
                str(destination),
                "fetch",
                "--depth",
                "1",
                "--no-tags",
                "origin",
                f"refs/heads/{branch}",
            ],
            ["git", "-C", str(destination), "checkout", "--detach", "-q", "FETCH_HEAD"],
        ):
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
                env=environment,
            )
        commit_sha = (
            subprocess.run(
                ["git", "-c", f"safe.directory={destination}", "-C", str(destination), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
                env=environment,
            )
            .stdout.strip()
            .lower()
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SourceError("Unable to clone the landed Dev GitLab project") from exc
    return SourceCheckout(
        checkout_dir=destination.resolve(),
        commit_sha=commit_sha,
        ref_type=ref_type,
        source_ref=source_ref,
    )

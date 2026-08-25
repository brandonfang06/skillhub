from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from skillhub_oss_importer.github_source import (
    SourceError,
    canonicalize_repository,
    clone_repository,
)

INTERNAL_REPOSITORY_URL = "https://gitlab.internal/dev/oss-source.git"


def test_canonicalizes_only_github_https_repository() -> None:
    source = canonicalize_repository("https://github.com/MattPocock/Skills.git")
    assert source.canonical_url == "https://github.com/mattpocock/skills"
    assert source.namespace_slug == "oss-mattpocock-skills"
    assert source.namespace_display_name == "OSS-mattpocock-skills"
    with pytest.raises(SourceError):
        canonicalize_repository("https://gitlab.com/mattpocock/skills")


def make_source_repository(tmp_path: Path) -> tuple[Path, str, str]:
    source = tmp_path / "source"
    subprocess.run(["git", "init", "-q", "-b", "main", str(source)], check=True)
    subprocess.run(["git", "-C", str(source), "config", "user.email", "test@example.test"], check=True)
    subprocess.run(["git", "-C", str(source), "config", "user.name", "Test"], check=True)
    (source / "SKILL.md").write_text("---\nname: first\ndescription: first\n---\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(source), "add", "SKILL.md"], check=True)
    subprocess.run(["git", "-C", str(source), "commit", "-qm", "first"], check=True)
    first_sha = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(["git", "-C", str(source), "branch", "release", first_sha], check=True)
    (source / "SKILL.md").write_text("---\nname: second\ndescription: second\n---\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(source), "commit", "-qam", "second"], check=True)
    second_sha = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return source, first_sha, second_sha


def route_internal_clone_to_local_repository(
    source: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", f"url.{source.as_uri()}.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", INTERNAL_REPOSITORY_URL)
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file")


def test_clones_the_requested_internal_gitlab_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, first_sha, _second_sha = make_source_repository(tmp_path)
    route_internal_clone_to_local_repository(source, monkeypatch)

    checkout = clone_repository(
        INTERNAL_REPOSITORY_URL,
        tmp_path / "checkout",
        "release",
        "BRANCH",
        "main",
        "job-secret",
    )

    assert checkout.commit_sha == first_sha
    assert checkout.ref_type == "BRANCH"
    assert checkout.source_ref == "main"
    assert "name: first" in (checkout.checkout_dir / "SKILL.md").read_text(encoding="utf-8")


def test_records_the_internal_gitlab_pipeline_tag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, _first_sha, second_sha = make_source_repository(tmp_path)
    route_internal_clone_to_local_repository(source, monkeypatch)

    checkout = clone_repository(
        INTERNAL_REPOSITORY_URL,
        tmp_path / "tagged-checkout",
        "main",
        "TAG",
        "v1.0.0",
        "job-secret",
    )

    assert checkout.commit_sha == second_sha
    assert checkout.ref_type == "TAG"
    assert checkout.source_ref == "v1.0.0"


def test_internal_gitlab_clone_failure_does_not_leak_the_job_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, _first_sha, _second_sha = make_source_repository(tmp_path)
    route_internal_clone_to_local_repository(source, monkeypatch)

    with pytest.raises(SourceError, match="Unable to clone the landed Dev GitLab project") as error:
        clone_repository(
            INTERNAL_REPOSITORY_URL,
            tmp_path / "missing-branch",
            "missing",
            "COMMIT",
            None,
            "job-secret",
        )

    assert "job-secret" not in str(error.value)


def test_job_token_is_not_exposed_in_git_command_arguments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, _first_sha, _second_sha = make_source_repository(tmp_path)
    route_internal_clone_to_local_repository(source, monkeypatch)
    original_run = subprocess.run
    commands: list[list[str]] = []
    environments: list[dict[str, str]] = []

    def recording_run(command: list[str], *args: object, **kwargs: object):
        commands.append(command)
        environments.append(dict(kwargs["env"]))
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr("skillhub_oss_importer.github_source.subprocess.run", recording_run)

    clone_repository(
        INTERNAL_REPOSITORY_URL,
        tmp_path / "secure-checkout",
        "main",
        "COMMIT",
        None,
        "job-secret",
    )

    assert all("job-secret" not in argument for command in commands for argument in command)
    assert any(command[-1] == "refs/heads/main" for command in commands if "fetch" in command)
    assert any(
        value.startswith("Authorization: Basic ")
        for environment in environments
        for name, value in environment.items()
        if name.startswith("GIT_CONFIG_VALUE_")
    )
    assert any(
        environment.get(f"GIT_CONFIG_VALUE_{index}") == "false"
        for environment in environments
        for index in range(int(environment["GIT_CONFIG_COUNT"]))
        if environment.get(f"GIT_CONFIG_KEY_{index}") == "http.followRedirects"
    )

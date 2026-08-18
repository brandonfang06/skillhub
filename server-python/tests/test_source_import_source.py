from __future__ import annotations

import pytest

from app.publish.package import PackageEntry
from app.source_import.source import (
    SourceInputError,
    build_browse_url,
    canonicalize_github_repository,
    content_fingerprint,
    normalize_source_path,
    validate_source_revision,
)


@pytest.mark.parametrize(
    ("raw", "canonical", "slug", "display_name"),
    [
        (
            "https://github.com/mattpocock/skills",
            "https://github.com/mattpocock/skills",
            "oss-mattpocock-skills",
            "OSS-mattpocock-skills",
        ),
        (
            "https://github.com/MattPocock/Skills.git",
            "https://github.com/mattpocock/skills",
            "oss-mattpocock-skills",
            "OSS-mattpocock-skills",
        ),
    ],
)
def test_canonicalizes_supported_github_repository_urls(
    raw: str,
    canonical: str,
    slug: str,
    display_name: str,
) -> None:
    repository = canonicalize_github_repository(raw)

    assert repository.canonical_url == canonical
    assert repository.namespace_slug == slug
    assert repository.namespace_display_name == display_name


@pytest.mark.parametrize(
    "raw",
    [
        "http://github.com/a/b",
        "https://gitlab.com/a/b",
        "https://user@github.com/a/b",
        "https://github.com:443/a/b",
        "https://github.com/a/b/issues",
        "https://github.com/a/b?tab=readme",
        "https://github.com/a/b#readme",
        "git@github.com:a/b.git",
        "https://github.com/a",
        "https://github.com//b",
        "https://github.com/a/.git",
        f"https://github.com/{'a' * 39}/{'b' * 25}",
    ],
)
def test_rejects_unsupported_or_unusable_repository_urls(raw: str) -> None:
    with pytest.raises(SourceInputError):
        canonicalize_github_repository(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (".", "."),
        ("skills/code-review", "skills/code-review"),
        ("skills//code-review", "skills/code-review"),
    ],
)
def test_normalizes_repository_relative_source_paths(raw: str, expected: str) -> None:
    assert normalize_source_path(raw) == expected


@pytest.mark.parametrize("raw", ["", "/skills/a", "../skills/a", "skills/../a", "skills\\a", ".git/a"])
def test_rejects_unsafe_source_paths(raw: str) -> None:
    with pytest.raises(SourceInputError):
        normalize_source_path(raw)


def test_validates_commit_first_source_revision() -> None:
    revision = validate_source_revision("A" * 40, "BRANCH", "main")

    assert revision.commit_sha == "a" * 40
    assert revision.ref_type == "BRANCH"
    assert revision.ref == "main"


@pytest.mark.parametrize(
    ("sha", "ref_type", "ref"),
    [
        ("abc", "COMMIT", None),
        ("g" * 40, "COMMIT", None),
        ("a" * 40, "RELEASE", "v1"),
        ("a" * 40, "COMMIT", "main"),
        ("a" * 40, "TAG", None),
        ("a" * 40, "BRANCH", " "),
    ],
)
def test_rejects_invalid_source_revision_combinations(sha: str, ref_type: str, ref: str | None) -> None:
    with pytest.raises(SourceInputError):
        validate_source_revision(sha, ref_type, ref)


def test_builds_exact_commit_browse_url_with_encoded_source_path() -> None:
    repository = canonicalize_github_repository("https://github.com/mattpocock/skills")
    revision = validate_source_revision("0123456789abcdef0123456789abcdef01234567", "TAG", "v1.0.0")

    assert build_browse_url(repository, revision, "skills/agent tools/code-review") == (
        "https://github.com/mattpocock/skills/tree/"
        "0123456789abcdef0123456789abcdef01234567/skills/agent%20tools/code-review"
    )
    assert build_browse_url(repository, revision, ".") == (
        "https://github.com/mattpocock/skills/tree/0123456789abcdef0123456789abcdef01234567"
    )


def test_content_fingerprint_ignores_entry_order_and_archive_metadata() -> None:
    first = [
        PackageEntry(path="SKILL.md", content=b"name: demo", content_type="text/markdown"),
        PackageEntry(path="reference.txt", content=b"hello", content_type="text/plain"),
    ]
    reordered = [
        PackageEntry(path="reference.txt", content=b"hello", content_type="application/octet-stream"),
        PackageEntry(path="SKILL.md", content=b"name: demo", content_type="text/plain"),
    ]

    assert content_fingerprint(first) == content_fingerprint(reordered)


def test_content_fingerprint_changes_for_path_or_content_changes() -> None:
    original = [PackageEntry(path="SKILL.md", content=b"name: demo", content_type="text/markdown")]
    changed_path = [PackageEntry(path="skill.md", content=b"name: demo", content_type="text/markdown")]
    changed_content = [PackageEntry(path="SKILL.md", content=b"name: other", content_type="text/markdown")]

    assert content_fingerprint(original) != content_fingerprint(changed_path)
    assert content_fingerprint(original) != content_fingerprint(changed_content)

import pytest

from app.api.skills import (
    SkillResolveError,
    build_resolve_response,
    compute_version_fingerprint,
    resolve_version_row,
)


def test_compute_version_fingerprint_sorts_files_by_path() -> None:
    files = [
        {"file_path": "z.txt", "sha256": "hash-z"},
        {"file_path": "a.txt", "sha256": "hash-a"},
    ]

    assert compute_version_fingerprint(files) == (
        "sha256:f7a0f0028a3fb59e80b283f5b130ab24da663a2ae734455867d47d1227354108"
    )


def test_resolve_version_row_uses_latest_without_selector() -> None:
    latest = {"id": 20, "version": "1.2.0"}

    assert resolve_version_row(
        versions=[{"id": 10, "version": "1.0.0"}, latest],
        latest_version_id=20,
        tags={},
        fingerprints={10: "sha256:old", 20: "sha256:new"},
        version=None,
        tag=None,
        hash_value=None,
    ) == (latest, None)


def test_resolve_version_row_uses_exact_published_version() -> None:
    version_row = {"id": 10, "version": "1.0.0"}

    assert resolve_version_row(
        versions=[version_row, {"id": 20, "version": "1.2.0"}],
        latest_version_id=20,
        tags={},
        fingerprints={10: "sha256:old", 20: "sha256:new"},
        version="1.0.0",
        tag=None,
        hash_value=None,
    ) == (version_row, None)


def test_resolve_version_row_uses_tagged_version() -> None:
    version_row = {"id": 10, "version": "1.0.0"}

    assert resolve_version_row(
        versions=[version_row, {"id": 20, "version": "1.2.0"}],
        latest_version_id=20,
        tags={"stable": 10},
        fingerprints={10: "sha256:old", 20: "sha256:new"},
        version=None,
        tag="stable",
        hash_value=None,
    ) == (version_row, None)


def test_resolve_version_row_uses_matching_hash() -> None:
    version_row = {"id": 10, "version": "1.0.0"}

    assert resolve_version_row(
        versions=[version_row, {"id": 20, "version": "1.2.0"}],
        latest_version_id=20,
        tags={},
        fingerprints={10: "sha256:old", 20: "sha256:new"},
        version=None,
        tag=None,
        hash_value="sha256:old",
    ) == (version_row, True)


def test_resolve_version_row_falls_back_to_latest_when_hash_does_not_match() -> None:
    latest = {"id": 20, "version": "1.2.0"}

    assert resolve_version_row(
        versions=[{"id": 10, "version": "1.0.0"}, latest],
        latest_version_id=20,
        tags={},
        fingerprints={10: "sha256:old", 20: "sha256:new"},
        version=None,
        tag=None,
        hash_value="sha256:missing",
    ) == (latest, False)


def test_resolve_version_row_rejects_version_and_tag_conflict() -> None:
    with pytest.raises(SkillResolveError, match="error.skill.resolve.versionTag.conflict"):
        resolve_version_row(
            versions=[],
            latest_version_id=None,
            tags={},
            fingerprints={},
            version="1.0.0",
            tag="latest",
            hash_value=None,
        )


def test_build_resolve_response_encodes_download_url_path_segments() -> None:
    assert build_resolve_response(
        skill_id=1,
        namespace="global",
        slug="demo skill",
        version_row={"id": 11, "version": "1.0.0 beta"},
        fingerprint="sha256:abc",
        matched=None,
    )["downloadUrl"] == "/api/v1/skills/global/demo%20skill/versions/1.0.0%20beta/download"

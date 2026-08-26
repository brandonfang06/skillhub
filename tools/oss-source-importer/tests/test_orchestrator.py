from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillhub_oss_importer.client import AuthorizationError
from skillhub_oss_importer.github_source import SourceCheckout
from skillhub_oss_importer.orchestrator import run_import


class FakeClient:
    def __init__(self, validation_outcomes: list[str]) -> None:
        self.validation_outcomes = iter(validation_outcomes)
        self.calls: list[str] = []
        self.metadata: list[dict[str, object]] = []

    def ensure_namespace(self, _slug: str, _body: dict[str, object]) -> dict[str, object]:
        self.calls.append("ensure")
        return {"outcome": "CREATED"}

    def validate_skill(self, _slug: str, _content: bytes, metadata: dict[str, object]) -> dict[str, object]:
        self.calls.append(f"validate:{metadata['sourcePath']}")
        self.metadata.append(metadata)
        outcome = next(self.validation_outcomes)
        if outcome == "ERROR":
            raise ValueError("invalid package")
        return {"outcome": outcome, "coordinate": "@oss/x", "version": "1.0.0"}

    def submit_skill(self, _slug: str, _content: bytes, metadata: dict[str, object]) -> dict[str, object]:
        self.calls.append(f"submit:{metadata['sourcePath']}")
        self.metadata.append(metadata)
        return {"outcome": "IMPORTED", "coordinate": "@oss/x", "version": "1.0.0"}


def fixture_config(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        project_dir=tmp_path,
        source_subdirectory=Path("."),
        namespace_slug="oss-owner-repo",
        namespace_display_name="OSS-owner-repo",
        repository_url="https://github.com/owner/repo",
        owner_provider_code="keycloak",
        owner_login_name="owner",
        trigger_provider_code="keycloak",
        trigger_login_name="alice",
        pipeline_id="1",
        job_id="2",
        scan_status="PASSED",
        scan_id="scan-123",
    )


def fixture_checkout(tmp_path: Path) -> SourceCheckout:
    return SourceCheckout(
        checkout_dir=tmp_path,
        commit_sha="a" * 40,
        ref_type="COMMIT",
        source_ref=None,
    )


def make_skills(tmp_path: Path) -> None:
    for name in ("a", "b"):
        root = tmp_path / name
        root.mkdir()
        (root / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {name}\n---", encoding="utf-8")


def test_validates_every_package_before_sequential_submit(tmp_path: Path, caplog) -> None:
    make_skills(tmp_path)
    client = FakeClient(["IMPORT", "SKIPPED_UNCHANGED"])
    with caplog.at_level(logging.INFO, logger="skillhub_oss_importer.orchestrator"):
        report = run_import(fixture_config(tmp_path), client, fixture_checkout(tmp_path))
    assert client.calls == ["ensure", "validate:a", "validate:b", "submit:a"]
    assert report["status"] == "SUCCESS"
    job_log = "\n".join(record.getMessage() for record in caplog.records)
    assert "event=discovery_completed skills=2" in job_log
    assert "event=packaging_started skills=2" in job_log
    assert "event=packaging_completed skills=2" in job_log
    assert 'event=namespace_started namespace="oss-owner-repo"' in job_log
    assert 'event=namespace_completed namespace="oss-owner-repo" outcome="CREATED"' in job_log
    assert 'event=validation_started source_path="a" index=1 total=2' in job_log
    assert 'event=validation_completed source_path="a" outcome="IMPORT"' in job_log
    assert 'event=validation_completed source_path="b" outcome="SKIPPED_UNCHANGED"' in job_log
    assert 'event=submission_started source_path="a" index=1 total=2' in job_log
    assert 'event=submission_completed source_path="a" outcome="IMPORTED"' in job_log
    assert 'event=submission_skipped source_path="b" outcome="SKIPPED_UNCHANGED"' in job_log
    assert (
        'event=import_completed status="SUCCESS" skills=2 validated=2 submitted=1 skipped=1 '
        "failed=0"
    ) in job_log


def test_uses_checked_out_revision_and_leaves_missing_version_to_backend(tmp_path: Path) -> None:
    unversioned = tmp_path / "unversioned"
    unversioned.mkdir()
    (unversioned / "SKILL.md").write_text(
        "---\nname: unversioned\ndescription: fixture\n---\n",
        encoding="utf-8",
    )
    versioned = tmp_path / "versioned"
    versioned.mkdir()
    (versioned / "SKILL.md").write_text(
        "---\nname: versioned\ndescription: fixture\nversion: 1.2.3\n---\n",
        encoding="utf-8",
    )
    client = FakeClient(["IMPORT", "IMPORT"])

    report = run_import(fixture_config(tmp_path), client, fixture_checkout(tmp_path))

    assert all("versionOverride" not in metadata for metadata in client.metadata)
    assert all(metadata["repositoryRevisionSha"] == "a" * 40 for metadata in client.metadata)
    assert "ciRefName" not in client.metadata[0]
    assert report["commitSha"] == "a" * 40
    assert "devGitlabCommitSha" not in report
    assert report["scanStatus"] == "PASSED"
    assert "scanCommitSha" not in report
    assert report["scanId"] == "scan-123"
    assert "importerProjectCommitSha" not in report


def test_validation_failure_prevents_all_submissions(tmp_path: Path, caplog) -> None:
    make_skills(tmp_path)
    client = FakeClient(["IMPORT"])
    original_validate = client.validate_skill

    def validate_with_injected_line(
        slug: str, content: bytes, metadata: dict[str, object]
    ) -> dict[str, object]:
        if metadata["sourcePath"] == "b":
            raise ValueError("invalid package\nlevel=INFO event=fake")
        return original_validate(slug, content, metadata)

    client.validate_skill = validate_with_injected_line  # type: ignore[method-assign]
    with caplog.at_level(logging.INFO, logger="skillhub_oss_importer.orchestrator"):
        report = run_import(fixture_config(tmp_path), client, fixture_checkout(tmp_path))
    assert not any(call.startswith("submit:") for call in client.calls)
    assert report["status"] == "VALIDATION_FAILED"
    job_log = "\n".join(record.getMessage() for record in caplog.records)
    assert 'event=validation_failed source_path="b" error_type="ValueError"' in job_log
    assert "invalid package\\nlevel=INFO event=fake" in job_log
    assert "invalid package\nlevel=INFO event=fake" not in job_log
    assert 'event=submission_phase_skipped reason="validation_failed"' in job_log
    assert (
        'event=import_completed status="VALIDATION_FAILED" skills=2 validated=1 submitted=0 '
        "skipped=0 failed=1"
    ) in job_log


def test_submission_failure_is_visible_in_job_log_and_summary(tmp_path: Path, caplog) -> None:
    make_skills(tmp_path)
    client = FakeClient(["IMPORT", "IMPORT"])
    original_submit = client.submit_skill

    def fail_first_submission(
        slug: str, content: bytes, metadata: dict[str, object]
    ) -> dict[str, object]:
        if metadata["sourcePath"] == "a":
            raise ValueError("publish failed")
        return original_submit(slug, content, metadata)

    client.submit_skill = fail_first_submission  # type: ignore[method-assign]
    with caplog.at_level(logging.INFO, logger="skillhub_oss_importer.orchestrator"):
        report = run_import(fixture_config(tmp_path), client, fixture_checkout(tmp_path))

    assert report["status"] == "PARTIAL_SUBMISSION"
    job_log = "\n".join(record.getMessage() for record in caplog.records)
    assert (
        'event=submission_failed source_path="a" error_type="ValueError" '
        'error="publish failed"'
    ) in job_log
    assert 'event=submission_completed source_path="b" outcome="IMPORTED"' in job_log
    assert (
        'event=import_completed status="PARTIAL_SUBMISSION" skills=2 validated=2 submitted=1 '
        "skipped=0 failed=1"
    ) in job_log


def test_authorization_failure_keeps_stable_cli_error_class(tmp_path: Path) -> None:
    make_skills(tmp_path)
    client = FakeClient(["IMPORT", "IMPORT"])

    def denied(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AuthorizationError("denied")

    client.validate_skill = denied  # type: ignore[method-assign]
    with pytest.raises(AuthorizationError):
        run_import(fixture_config(tmp_path), client, fixture_checkout(tmp_path))

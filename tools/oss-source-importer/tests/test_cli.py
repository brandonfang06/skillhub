from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillhub_oss_importer.cli import (
    EXIT_AUTHORIZATION,
    EXIT_CONFIGURATION,
    EXIT_INTERNAL,
    EXIT_SUCCESS,
    EXIT_TRANSPORT,
    EXIT_VALIDATION,
    main,
)
from skillhub_oss_importer.client import AuthorizationError, TransportError
from skillhub_oss_importer.discovery import DiscoveryError
from skillhub_oss_importer.github_source import SourceCheckout


def test_cli_maps_configuration_error_and_writes_atomic_report(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    report = tmp_path / "report.json"
    monkeypatch.setenv("SKILLHUB_IMPORT_REPORT_PATH", str(report))
    monkeypatch.setenv("SKILLHUB_SERVICE_TOKEN", "st_should_not_log")
    assert main([]) == EXIT_CONFIGURATION
    assert report.exists()
    assert not report.with_suffix(".json.tmp").exists()
    job_log = capsys.readouterr().out
    assert "event=importer_started" in job_log
    assert (
        'event=importer_failed status="CONFIGURATION_FAILED" exit_code=2 '
        'error_type="ConfigError"'
    ) in job_log
    assert "Missing required environment variable" in job_log
    assert "event=report_written" in job_log
    assert 'event=importer_finished status="CONFIGURATION_FAILED" exit_code=2' in job_log
    assert "st_should_not_log" not in job_log


@pytest.mark.parametrize(
    ("error", "status", "exit_code", "report_error"),
    [
        (DiscoveryError("invalid package"), "VALIDATION_FAILED", EXIT_VALIDATION, "invalid package"),
        (
            AuthorizationError("authorization denied"),
            "AUTHORIZATION_FAILED",
            EXIT_AUTHORIZATION,
            "authorization denied",
        ),
        (TransportError("request timeout"), "TRANSPORT_FAILED", EXIT_TRANSPORT, "request timeout"),
        (RuntimeError("private internal detail"), "INTERNAL_FAILED", EXIT_INTERNAL, "RuntimeError"),
    ],
)
def test_cli_logs_stable_failure_classes(
    tmp_path: Path,
    monkeypatch,
    capsys,
    error: Exception,
    status: str,
    exit_code: int,
    report_error: str,
) -> None:
    report = tmp_path / "report.json"
    monkeypatch.setenv("SKILLHUB_IMPORT_REPORT_PATH", str(report))

    def fail_config():
        raise error

    monkeypatch.setattr("skillhub_oss_importer.cli.Config.from_env", fail_config)

    assert main([]) == exit_code
    assert json.loads(report.read_text(encoding="utf-8")) == {
        "error": report_error,
        "status": status,
    }
    job_log = capsys.readouterr().out
    assert f'event=importer_failed status="{status}" exit_code={exit_code}' in job_log
    assert f'error_type="{type(error).__name__}"' in job_log
    assert f'event=importer_finished status="{status}" exit_code={exit_code}' in job_log
    if status == "INTERNAL_FAILED":
        assert "private internal detail" not in job_log


def test_cli_keeps_stable_internal_exit_when_report_cannot_be_written(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    report_path = tmp_path / "report.json"
    report_path.mkdir()
    config = SimpleNamespace(
        base_url="https://skillhub.example/skillhub",
        service_token="st_secret",
        timeout_seconds=60.0,
        repository_url="https://github.com/mattpocock/skills",
        source_clone_url="https://gitlab.internal/dev/skills.git",
        gitlab_job_token="job-secret",
        dev_gitlab_branch="main",
        ref_type="BRANCH",
        source_ref="main",
        namespace_slug="oss-mattpocock-skills",
        scan_id="scan-123",
        pipeline_id="456",
        job_id="789",
        report_path=report_path,
    )

    class FakeClient:
        def __init__(self, *_args: object) -> None:
            pass

        def close(self) -> None:
            pass

    def fake_clone(
        _clone_url: str,
        destination: Path,
        _branch: str,
        ref_type: str,
        source_ref: str | None,
        _job_token: str,
    ) -> SourceCheckout:
        destination.mkdir()
        return SourceCheckout(destination, "a" * 40, ref_type, source_ref)

    monkeypatch.setattr("skillhub_oss_importer.cli.Config.from_env", lambda: config)
    monkeypatch.setattr("skillhub_oss_importer.cli.SkillHubClient", FakeClient)
    monkeypatch.setattr("skillhub_oss_importer.cli.clone_repository", fake_clone)
    monkeypatch.setattr(
        "skillhub_oss_importer.cli.run_import",
        lambda *_args: {"status": "SUCCESS"},
    )

    assert main([]) == EXIT_INTERNAL
    job_log = capsys.readouterr().out
    assert 'event=importer_failed status="INTERNAL_FAILED" exit_code=10' in job_log
    assert "event=report_write_failed" in job_log
    assert 'event=importer_finished status="INTERNAL_FAILED" exit_code=10' in job_log
    assert "st_secret" not in job_log
    assert "job-secret" not in job_log


def test_cli_clones_the_landed_dev_gitlab_branch_before_import(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    report_path = tmp_path / "report.json"
    config = SimpleNamespace(
        base_url="https://skillhub.example/skillhub",
        service_token="st_secret",
        timeout_seconds=60.0,
        repository_url="https://github.com/mattpocock/skills",
        source_clone_url="https://gitlab.internal/dev/skills.git",
        gitlab_job_token="job-secret",
        dev_gitlab_branch="release/accepted",
        ref_type="TAG",
        source_ref="v1.2.3",
        namespace_slug="oss-mattpocock-skills",
        scan_id="scan-123",
        pipeline_id="456",
        job_id="789",
        report_path=report_path,
    )
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, *_args: object) -> None:
            pass

        def close(self) -> None:
            captured["closed"] = True

    def fake_clone(
        clone_url: str,
        destination: Path,
        branch: str,
        ref_type: str,
        source_ref: str | None,
        job_token: str,
    ) -> SourceCheckout:
        captured["clone_url"] = clone_url
        captured["branch"] = branch
        captured["ref_type"] = ref_type
        captured["source_ref"] = source_ref
        captured["job_token"] = job_token
        destination.mkdir()
        return SourceCheckout(destination, "a" * 40, ref_type, source_ref)

    def fake_run(_config, _client, checkout: SourceCheckout) -> dict[str, object]:
        captured["checkout_exists_during_import"] = checkout.checkout_dir.is_dir()
        return {"status": "SUCCESS"}

    monkeypatch.setattr("skillhub_oss_importer.cli.Config.from_env", lambda: config)
    monkeypatch.setattr("skillhub_oss_importer.cli.SkillHubClient", FakeClient)
    monkeypatch.setattr("skillhub_oss_importer.cli.clone_repository", fake_clone)
    monkeypatch.setattr("skillhub_oss_importer.cli.run_import", fake_run)

    assert main([]) == EXIT_SUCCESS
    assert captured == {
        "clone_url": "https://gitlab.internal/dev/skills.git",
        "branch": "release/accepted",
        "ref_type": "TAG",
        "source_ref": "v1.2.3",
        "job_token": "job-secret",
        "checkout_exists_during_import": True,
        "closed": True,
    }
    job_log = capsys.readouterr().out
    assert "event=importer_started" in job_log
    assert 'event=config_loaded repository="https://github.com/mattpocock/skills"' in job_log
    assert 'skillhub_base_url="https://skillhub.example/skillhub"' in job_log
    assert "timeout_seconds=60.0" in job_log
    assert 'dev_branch="release/accepted"' in job_log
    assert "event=clone_started" in job_log
    assert 'event=clone_completed revision="' + ("a" * 40) + '"' in job_log
    assert "event=report_written" in job_log
    assert "report.json" in job_log
    assert 'event=importer_finished status="SUCCESS" exit_code=0' in job_log
    assert "st_secret" not in job_log
    assert "job-secret" not in job_log

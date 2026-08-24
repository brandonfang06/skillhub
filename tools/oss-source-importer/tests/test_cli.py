from pathlib import Path
from types import SimpleNamespace

from skillhub_oss_importer.cli import EXIT_CONFIGURATION, EXIT_SUCCESS, main
from skillhub_oss_importer.github_source import SourceCheckout


def test_cli_maps_configuration_error_and_writes_atomic_report(tmp_path: Path, monkeypatch) -> None:
    report = tmp_path / "report.json"
    monkeypatch.setenv("SKILLHUB_IMPORT_REPORT_PATH", str(report))
    assert main([]) == EXIT_CONFIGURATION
    assert report.exists()
    assert not report.with_suffix(".json.tmp").exists()


def test_cli_clones_the_current_internal_gitlab_project_before_import(tmp_path: Path, monkeypatch) -> None:
    report_path = tmp_path / "report.json"
    config = SimpleNamespace(
        base_url="https://skillhub.example/skillhub",
        service_token="st_secret",
        timeout_seconds=60.0,
        repository_url="https://github.com/mattpocock/skills",
        source_clone_url="https://gitlab-ci-token:secret@gitlab.internal/platform/skills.git",
        commit_sha="a" * 40,
        ref_type="TAG",
        source_ref="v1.2.3",
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
        expected_sha: str,
        ref_type: str,
        source_ref: str | None,
    ) -> SourceCheckout:
        captured["clone_url"] = clone_url
        captured["expected_sha"] = expected_sha
        captured["ref_type"] = ref_type
        captured["source_ref"] = source_ref
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
        "clone_url": "https://gitlab-ci-token:secret@gitlab.internal/platform/skills.git",
        "expected_sha": "a" * 40,
        "ref_type": "TAG",
        "source_ref": "v1.2.3",
        "checkout_exists_during_import": True,
        "closed": True,
    }

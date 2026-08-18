from pathlib import Path

from skillhub_oss_importer.cli import EXIT_CONFIGURATION, main


def test_cli_maps_configuration_error_and_writes_atomic_report(tmp_path: Path, monkeypatch) -> None:
    report = tmp_path / "report.json"
    monkeypatch.setenv("SKILLHUB_IMPORT_REPORT_PATH", str(report))
    assert main([]) == EXIT_CONFIGURATION
    assert report.exists()
    assert not report.with_suffix(".json.tmp").exists()

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from types import TracebackType

import pytest

from scanner_adapter.cli import main
from scanner_adapter.config import ScannerAdapterConfig
from scanner_adapter.errors import (
    ConfigurationError,
    InputValidationError,
    ScannerHttpError,
    ScannerResponseError,
    ScannerUnavailableError,
)
from scanner_adapter.models import ScanResult
from scanner_adapter.normalize import normalize_scan_response

ClientFactory = Callable[[ScannerAdapterConfig], "FakeClient"]


class FakeClient:
    def __init__(
        self,
        config: ScannerAdapterConfig,
        *,
        scan_result: ScanResult,
        error: Exception | None = None,
    ) -> None:
        self.config = config
        self.scan_result = scan_result
        self.error = error
        self.calls: list[str] = []

    def __enter__(self) -> FakeClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def health(self) -> Mapping[str, object]:
        self.calls.append("health")
        self._raise_if_configured()
        return {"status": "healthy", "version": "1.2.3"}

    def list_analyzers(self) -> list[Mapping[str, object]]:
        self.calls.append("analyzers")
        self._raise_if_configured()
        return [{"name": "aidefense_analyzer", "available": True}]

    def scan_zip(self, path: str | Path) -> ScanResult:
        self.calls.append(f"scan:{Path(path).name}")
        self._raise_if_configured()
        return self.scan_result

    def _raise_if_configured(self) -> None:
        if self.error is not None:
            raise self.error


def make_result(*, is_safe: bool) -> ScanResult:
    findings: list[dict[str, object]] = []
    max_severity = "INFO"
    if not is_safe:
        max_severity = "HIGH"
        findings.append(
            {
                "rule_id": "RULE-001",
                "severity": "HIGH",
                "category": "data-exfiltration",
                "title": "Potential data exfiltration",
                "description": "Description from the scanner",
            }
        )
    raw: dict[str, object] = {
        "scan_id": "scan-id",
        "skill_name": "example",
        "is_safe": is_safe,
        "max_severity": max_severity,
        "findings_count": len(findings),
        "scan_duration_seconds": 1.0,
        "timestamp": "2026-07-28T01:02:03+00:00",
        "findings": findings,
    }
    return normalize_scan_response(
        raw,
        analyzers_requested=("static", "behavioral", "aidefense"),
    )


def build_factory(client: FakeClient) -> ClientFactory:
    def factory(config: ScannerAdapterConfig) -> FakeClient:
        client.config = config
        return client

    return factory


def test_health_prints_json(capsys: pytest.CaptureFixture[str]) -> None:
    client = FakeClient(ScannerAdapterConfig.from_env({}), scan_result=make_result(is_safe=True))

    exit_code = main(["health"], environ={}, client_factory=build_factory(client))

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "healthy",
        "version": "1.2.3",
    }
    assert client.calls == ["health"]


def test_analyzers_prints_json(capsys: pytest.CaptureFixture[str]) -> None:
    client = FakeClient(ScannerAdapterConfig.from_env({}), scan_result=make_result(is_safe=True))

    exit_code = main(["analyzers"], environ={}, client_factory=build_factory(client))

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == [
        {"name": "aidefense_analyzer", "available": True}
    ]
    assert client.calls == ["analyzers"]


def test_scan_prints_normalized_json(
    capsys: pytest.CaptureFixture[str],
    skill_zip: Path,
) -> None:
    client = FakeClient(ScannerAdapterConfig.from_env({}), scan_result=make_result(is_safe=True))

    exit_code = main(
        ["scan", str(skill_zip)],
        environ={},
        client_factory=build_factory(client),
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1"
    assert payload["is_safe"] is True
    assert "raw_response" not in payload
    assert client.calls == ["scan:example.zip"]


def test_scan_writes_selected_output_file(
    capsys: pytest.CaptureFixture[str],
    skill_zip: Path,
    tmp_path: Path,
) -> None:
    output = tmp_path / "result.json"
    client = FakeClient(ScannerAdapterConfig.from_env({}), scan_result=make_result(is_safe=True))

    exit_code = main(
        ["scan", str(skill_zip), "--output", str(output)],
        environ={},
        client_factory=build_factory(client),
    )

    assert exit_code == 0
    assert capsys.readouterr().out == ""
    assert json.loads(output.read_text(encoding="utf-8"))["is_safe"] is True


def test_scan_can_check_health_first(
    skill_zip: Path,
) -> None:
    client = FakeClient(ScannerAdapterConfig.from_env({}), scan_result=make_result(is_safe=True))

    exit_code = main(
        ["scan", str(skill_zip), "--check-health"],
        environ={},
        client_factory=build_factory(client),
    )

    assert exit_code == 0
    assert client.calls == ["health", "scan:example.zip"]


def test_unsafe_scan_is_success_by_default(
    capsys: pytest.CaptureFixture[str],
    skill_zip: Path,
) -> None:
    client = FakeClient(ScannerAdapterConfig.from_env({}), scan_result=make_result(is_safe=False))

    exit_code = main(
        ["scan", str(skill_zip)],
        environ={},
        client_factory=build_factory(client),
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["is_safe"] is False


def test_fail_on_unsafe_prints_result_and_returns_five(
    capsys: pytest.CaptureFixture[str],
    skill_zip: Path,
) -> None:
    client = FakeClient(ScannerAdapterConfig.from_env({}), scan_result=make_result(is_safe=False))

    exit_code = main(
        ["scan", str(skill_zip), "--fail-on-unsafe"],
        environ={},
        client_factory=build_factory(client),
    )

    assert exit_code == 5
    assert json.loads(capsys.readouterr().out)["is_safe"] is False


@pytest.mark.parametrize(
    ("error", "exit_code"),
    [
        (ConfigurationError("bad config"), 2),
        (InputValidationError("bad input"), 3),
        (ScannerUnavailableError("unavailable"), 4),
        (ScannerHttpError("bad http"), 4),
        (ScannerResponseError("bad response"), 4),
    ],
)
def test_cli_maps_expected_errors(
    error: Exception,
    exit_code: int,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = FakeClient(
        ScannerAdapterConfig.from_env({}),
        scan_result=make_result(is_safe=True),
        error=error,
    )

    actual = main(["health"], environ={}, client_factory=build_factory(client))

    captured = capsys.readouterr()
    assert actual == exit_code
    assert captured.out == ""
    assert str(error) in captured.err

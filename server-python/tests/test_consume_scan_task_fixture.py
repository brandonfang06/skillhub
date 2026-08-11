from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.publish.scan_consumer import ScanConsumerResult
from scripts import consume_scan_task_fixture


@pytest.mark.anyio
async def test_fixture_uses_runtime_redis_client_and_passes_engine_to_consumer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    findings_file = tmp_path / "findings.json"
    findings_file.write_text("[]", encoding="utf-8")
    args = argparse.Namespace(
        storage_base_path=str(tmp_path),
        scan_temp_dir=str(tmp_path / "scans"),
        stream_key="skillhub:test:fixture",
        group_name="fixture-group",
        consumer_name="fixture-consumer",
        scan_id="fixture-scan",
        verdict="SAFE",
        findings_count=0,
        max_severity="LOW",
        findings_file=str(findings_file),
        duration=0.1,
        count=1,
        block_ms=100,
        scanner_source="fixture",
    )

    class FakeRedis:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    class FakeEngine:
        def begin(self) -> Any:
            raise AssertionError("fixture must pass the engine to ScanConsumerRuntime")

    fake_redis = FakeRedis()
    fake_engine = FakeEngine()
    disposed: list[FakeEngine] = []

    class FakeRuntime:
        def __init__(self, redis: Any, **kwargs: Any) -> None:
            assert redis.redis_client is fake_redis

        async def consume_once(self, engine: Any, scanner: Any, **kwargs: Any) -> ScanConsumerResult:
            assert engine is fake_engine
            return ScanConsumerResult(processed=1, acknowledged=1)

    async def fake_dispose(engine: FakeEngine) -> None:
        disposed.append(engine)

    monkeypatch.setattr(consume_scan_task_fixture, "parse_args", lambda: args)
    monkeypatch.setattr(
        consume_scan_task_fixture,
        "get_settings",
        lambda: SimpleNamespace(redis_url="redis://unused"),
    )
    monkeypatch.setattr(consume_scan_task_fixture, "create_redis_client", lambda settings: fake_redis, raising=False)
    monkeypatch.setattr(consume_scan_task_fixture, "create_database_engine", lambda settings: fake_engine)
    monkeypatch.setattr(consume_scan_task_fixture, "dispose_database_engine", fake_dispose)
    monkeypatch.setattr(consume_scan_task_fixture, "ScanConsumerRuntime", FakeRuntime)

    await consume_scan_task_fixture.main()

    output = json.loads(capsys.readouterr().out)
    assert output["processed"] == 1
    assert output["acknowledged"] == 1
    assert fake_redis.closed is True
    assert disposed == [fake_engine]

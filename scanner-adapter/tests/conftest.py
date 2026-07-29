from __future__ import annotations

import json
from pathlib import Path

import pytest

from scanner_adapter.config import ScannerAdapterConfig

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def config() -> ScannerAdapterConfig:
    return ScannerAdapterConfig.from_env(
        {"SCANNER_API_BASE_URL": "https://scanner.internal"}
    )


@pytest.fixture
def safe_response() -> dict[str, object]:
    return json.loads((FIXTURES / "safe_response.json").read_text(encoding="utf-8"))


@pytest.fixture
def skill_zip(tmp_path: Path) -> Path:
    path = tmp_path / "example.zip"
    path.write_bytes(b"PK\x03\x04teaching-fixture")
    return path

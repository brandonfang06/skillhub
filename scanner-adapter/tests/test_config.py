from __future__ import annotations

import math

import pytest

from scanner_adapter.config import ScannerAdapterConfig
from scanner_adapter.errors import ConfigurationError


def test_config_uses_teaching_defaults() -> None:
    config = ScannerAdapterConfig.from_env({})

    assert config.base_url == "http://localhost:8000"
    assert config.scan_path == "/scan-upload"
    assert config.health_path == "/health"
    assert config.analyzers_path == "/analyzers"
    assert config.connect_timeout_seconds == 5.0
    assert config.read_timeout_seconds == 300.0
    assert config.max_zip_bytes == 50 * 1024 * 1024
    assert config.use_behavioral is True
    assert config.use_llm is False
    assert config.llm_provider == "openai"
    assert config.use_ai_defense is False
    assert config.policy == "balanced"


def test_config_reads_environment_overrides() -> None:
    config = ScannerAdapterConfig.from_env(
        {
            "SCANNER_API_BASE_URL": "https://scanner.internal/",
            "SCANNER_SCAN_PATH": "/v1/scan-upload",
            "SCANNER_HEALTH_PATH": "/ready",
            "SCANNER_ANALYZERS_PATH": "/v1/analyzers",
            "SCANNER_CONNECT_TIMEOUT_SECONDS": "2.5",
            "SCANNER_READ_TIMEOUT_SECONDS": "45",
            "SCANNER_MAX_ZIP_BYTES": "1024",
            "SCANNER_USE_BEHAVIORAL": "off",
            "SCANNER_USE_LLM": "on",
            "SCANNER_LLM_PROVIDER": "anthropic",
            "SCANNER_USE_AI_DEFENSE": "0",
            "SCANNER_POLICY": "strict",
        }
    )

    assert config.base_url == "https://scanner.internal"
    assert config.scan_path == "/v1/scan-upload"
    assert config.health_path == "/ready"
    assert config.analyzers_path == "/v1/analyzers"
    assert config.connect_timeout_seconds == 2.5
    assert config.read_timeout_seconds == 45.0
    assert config.max_zip_bytes == 1024
    assert config.use_behavioral is False
    assert config.use_llm is True
    assert config.llm_provider == "anthropic"
    assert config.use_ai_defense is False
    assert config.policy == "strict"


@pytest.mark.parametrize(
    "value",
    [
        "ftp://scanner.internal",
        "http://user:password@scanner.internal",
        "http://scanner.internal?debug=true",
        "http://scanner.internal/#fragment",
        "scanner.internal",
        "http:///missing-host",
    ],
)
def test_config_rejects_unsafe_base_url(value: str) -> None:
    with pytest.raises(ConfigurationError, match="SCANNER_API_BASE_URL"):
        ScannerAdapterConfig.from_env({"SCANNER_API_BASE_URL": value})


@pytest.mark.parametrize(
    "name",
    ["SCANNER_SCAN_PATH", "SCANNER_HEALTH_PATH", "SCANNER_ANALYZERS_PATH"],
)
@pytest.mark.parametrize("value", ["relative", "//other-host/path", "/path?query=1", "/path#part"])
def test_config_rejects_invalid_endpoint_path(name: str, value: str) -> None:
    with pytest.raises(ConfigurationError, match=name):
        ScannerAdapterConfig.from_env({name: value})


def test_config_rejects_invalid_boolean() -> None:
    with pytest.raises(ConfigurationError, match="SCANNER_USE_AI_DEFENSE"):
        ScannerAdapterConfig.from_env({"SCANNER_USE_AI_DEFENSE": "sometimes"})


def test_config_rejects_unknown_llm_provider() -> None:
    with pytest.raises(ConfigurationError, match="SCANNER_LLM_PROVIDER"):
        ScannerAdapterConfig.from_env({"SCANNER_LLM_PROVIDER": "gemini"})


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_config_rejects_non_positive_or_non_finite_timeout(value: str) -> None:
    with pytest.raises(ConfigurationError, match="SCANNER_READ_TIMEOUT_SECONDS"):
        ScannerAdapterConfig.from_env({"SCANNER_READ_TIMEOUT_SECONDS": value})


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "abc"])
def test_config_rejects_invalid_max_zip_bytes(value: str) -> None:
    with pytest.raises(ConfigurationError, match="SCANNER_MAX_ZIP_BYTES"):
        ScannerAdapterConfig.from_env({"SCANNER_MAX_ZIP_BYTES": value})


def test_config_rejects_unknown_policy() -> None:
    with pytest.raises(ConfigurationError, match="SCANNER_POLICY"):
        ScannerAdapterConfig.from_env({"SCANNER_POLICY": "custom.yaml"})


def test_timeout_defaults_are_finite() -> None:
    config = ScannerAdapterConfig.from_env({})

    assert math.isfinite(config.connect_timeout_seconds)
    assert math.isfinite(config.read_timeout_seconds)

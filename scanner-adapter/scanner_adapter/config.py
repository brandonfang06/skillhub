"""Environment-backed configuration for the scanner adapter."""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

from scanner_adapter.errors import ConfigurationError

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})
_POLICIES = frozenset({"strict", "balanced", "permissive"})
_LLM_PROVIDERS = frozenset({"anthropic", "openai"})


@dataclass(frozen=True, slots=True)
class ScannerAdapterConfig:
    """Validated scanner endpoint and request settings."""

    base_url: str
    scan_path: str
    health_path: str
    analyzers_path: str
    connect_timeout_seconds: float
    read_timeout_seconds: float
    max_zip_bytes: int
    use_behavioral: bool
    use_llm: bool
    llm_provider: str
    use_ai_defense: bool
    policy: str

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> ScannerAdapterConfig:
        values = os.environ if environ is None else environ
        return cls(
            base_url=_parse_base_url(
                values.get("SCANNER_API_BASE_URL", "http://localhost:8000")
            ),
            scan_path=_parse_endpoint_path(
                "SCANNER_SCAN_PATH",
                values.get("SCANNER_SCAN_PATH", "/scan-upload"),
            ),
            health_path=_parse_endpoint_path(
                "SCANNER_HEALTH_PATH",
                values.get("SCANNER_HEALTH_PATH", "/health"),
            ),
            analyzers_path=_parse_endpoint_path(
                "SCANNER_ANALYZERS_PATH",
                values.get("SCANNER_ANALYZERS_PATH", "/analyzers"),
            ),
            connect_timeout_seconds=_parse_positive_float(
                "SCANNER_CONNECT_TIMEOUT_SECONDS",
                values.get("SCANNER_CONNECT_TIMEOUT_SECONDS", "5"),
            ),
            read_timeout_seconds=_parse_positive_float(
                "SCANNER_READ_TIMEOUT_SECONDS",
                values.get("SCANNER_READ_TIMEOUT_SECONDS", "300"),
            ),
            max_zip_bytes=_parse_positive_int(
                "SCANNER_MAX_ZIP_BYTES",
                values.get("SCANNER_MAX_ZIP_BYTES", str(50 * 1024 * 1024)),
            ),
            use_behavioral=_parse_bool(
                "SCANNER_USE_BEHAVIORAL",
                values.get("SCANNER_USE_BEHAVIORAL", "true"),
            ),
            use_llm=_parse_bool(
                "SCANNER_USE_LLM",
                values.get("SCANNER_USE_LLM", "false"),
            ),
            llm_provider=_parse_llm_provider(
                values.get("SCANNER_LLM_PROVIDER", "openai")
            ),
            use_ai_defense=_parse_bool(
                "SCANNER_USE_AI_DEFENSE",
                values.get("SCANNER_USE_AI_DEFENSE", "false"),
            ),
            policy=_parse_policy(values.get("SCANNER_POLICY", "balanced")),
        )


def _parse_base_url(value: str) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigurationError(
            "SCANNER_API_BASE_URL must be an http(s) URL without credentials, query, or fragment"
        )
    return candidate.rstrip("/")


def _parse_endpoint_path(name: str, value: str) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate)
    if (
        not candidate.startswith("/")
        or candidate.startswith("//")
        or parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigurationError(f"{name} must be an absolute URL path without query or fragment")
    return candidate


def _parse_bool(name: str, value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ConfigurationError(
        f"{name} must be one of: true, false, 1, 0, yes, no, on, off"
    )


def _parse_positive_float(name: str, value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise ConfigurationError(f"{name} must be a positive number") from error
    if not math.isfinite(parsed) or parsed <= 0:
        raise ConfigurationError(f"{name} must be a positive finite number")
    return parsed


def _parse_positive_int(name: str, value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise ConfigurationError(f"{name} must be a positive integer") from error
    if parsed <= 0:
        raise ConfigurationError(f"{name} must be a positive integer")
    return parsed


def _parse_policy(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in _POLICIES:
        raise ConfigurationError(
            "SCANNER_POLICY must be one of: strict, balanced, permissive"
        )
    return normalized


def _parse_llm_provider(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in _LLM_PROVIDERS:
        raise ConfigurationError(
            "SCANNER_LLM_PROVIDER must be one of: anthropic, openai"
        )
    return normalized

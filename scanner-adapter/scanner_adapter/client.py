"""Synchronous HTTP lifecycle for Cisco Skill Scanner."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import TracebackType
from typing import cast

import httpx

from scanner_adapter.config import ScannerAdapterConfig
from scanner_adapter.errors import (
    InputValidationError,
    ScannerHttpError,
    ScannerResponseError,
    ScannerUnavailableError,
)
from scanner_adapter.models import ScanResult
from scanner_adapter.normalize import normalize_scan_response

_MAX_ERROR_DETAIL_CHARS = 500


class ScannerClient:
    """Small synchronous client for the scanner's teaching endpoints."""

    def __init__(
        self,
        config: ScannerAdapterConfig,
        *,
        http_client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if http_client is not None and transport is not None:
            raise ValueError("pass either http_client or transport, not both")

        self.config = config
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.Client(
            timeout=httpx.Timeout(
                connect=config.connect_timeout_seconds,
                read=config.read_timeout_seconds,
                write=config.read_timeout_seconds,
                pool=config.connect_timeout_seconds,
            ),
            transport=transport,
        )

    def __enter__(self) -> ScannerClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_http_client:
            self._http_client.close()

    def health(self) -> Mapping[str, object]:
        payload = self._request_json("GET", self.config.health_path)
        if not isinstance(payload, Mapping):
            raise ScannerResponseError("health endpoint must return a JSON object")
        return cast(Mapping[str, object], payload)

    def list_analyzers(self) -> list[Mapping[str, object]]:
        payload = self._request_json("GET", self.config.analyzers_path)
        if isinstance(payload, Mapping):
            payload = payload.get("analyzers")
        if not isinstance(payload, list) or not all(
            isinstance(item, Mapping) for item in payload
        ):
            raise ScannerResponseError("analyzers endpoint must return a JSON list of objects")
        return cast(list[Mapping[str, object]], payload)

    def scan_zip(self, path: str | Path) -> ScanResult:
        zip_path = self._validate_zip_path(Path(path))
        data = {
            "policy": self.config.policy,
            "use_behavioral": str(self.config.use_behavioral).lower(),
            "use_llm": str(self.config.use_llm).lower(),
            "llm_provider": self.config.llm_provider,
            "use_aidefense": str(self.config.use_ai_defense).lower(),
        }
        with zip_path.open("rb") as zip_file:
            payload = self._request_json(
                "POST",
                self.config.scan_path,
                data=data,
                params=data,
                files={
                    "file": (
                        zip_path.name,
                        zip_file,
                        "application/zip",
                    )
                },
            )

        if not isinstance(payload, Mapping):
            raise ScannerResponseError("scan endpoint must return a JSON object")
        return normalize_scan_response(
            cast(Mapping[str, object], payload),
            analyzers_requested=self._requested_analyzers(),
        )

    def _request_json(
        self,
        method: str,
        endpoint_path: str,
        **kwargs: object,
    ) -> object:
        url = f"{self.config.base_url}{endpoint_path}"
        try:
            response = self._http_client.request(method, url, **kwargs)
        except httpx.RequestError as error:
            raise ScannerUnavailableError(f"scanner request failed: {error}") from error

        if not response.is_success:
            detail = " ".join(response.text.split())[:_MAX_ERROR_DETAIL_CHARS]
            if not detail:
                detail = "<empty response>"
            raise ScannerHttpError(
                f"scanner returned HTTP {response.status_code}: {detail}"
            )

        try:
            return response.json()
        except ValueError as error:
            raise ScannerResponseError("scanner response was not valid JSON") from error

    def _validate_zip_path(self, path: Path) -> Path:
        if not path.exists():
            raise InputValidationError(f"ZIP file does not exist: {path}")
        if not path.is_file():
            raise InputValidationError(f"ZIP path is not a regular file: {path}")
        if path.suffix.lower() != ".zip":
            raise InputValidationError(f"input must use the .zip extension: {path}")
        size = path.stat().st_size
        if size > self.config.max_zip_bytes:
            raise InputValidationError(
                f"ZIP file is {size} bytes; limit is {self.config.max_zip_bytes} bytes"
            )
        return path

    def _requested_analyzers(self) -> tuple[str, ...]:
        analyzers = ["static"]
        if self.config.use_behavioral:
            analyzers.append("behavioral")
        if self.config.use_llm:
            analyzers.append("llm")
        if self.config.use_ai_defense:
            analyzers.append("aidefense")
        return tuple(analyzers)

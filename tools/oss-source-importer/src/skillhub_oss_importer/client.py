from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import httpx


class SkillHubError(RuntimeError):
    pass


class AuthorizationError(SkillHubError):
    pass


class TransportError(SkillHubError):
    pass


class SkillHubClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        timeout_seconds: float,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            timeout=timeout_seconds,
            transport=transport,
            headers={"Authorization": f"Bearer {token}", "User-Agent": "skillhub-oss-source-importer/0.1"},
        )

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, object]:
        request_id = str(uuid4())
        try:
            response = self._client.request(
                method,
                f"{self._base_url}{path}",
                headers={"X-Request-Id": request_id},
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise TransportError(f"SkillHub request failed ({request_id}): {type(exc).__name__}") from exc
        if response.status_code in {401, 403}:
            raise AuthorizationError(f"SkillHub authorization failed ({response.status_code}, {request_id})")
        try:
            payload = response.json()
        except ValueError as exc:
            raise SkillHubError(f"SkillHub returned non-JSON response ({response.status_code}, {request_id})") from exc
        if response.is_error or payload.get("code") != 0:
            detail = payload.get("detail") or payload.get("msg") or "request failed"
            raise SkillHubError(f"SkillHub request failed ({response.status_code}, {request_id}): {detail}")
        data = dict(payload.get("data") or {})
        data["requestId"] = str(payload.get("requestId") or response.headers.get("X-Request-Id") or request_id)
        return data

    def ensure_namespace(self, namespace_slug: str, body: dict[str, object]) -> dict[str, object]:
        return self._request(
            "PUT",
            f"/api/cli/v1/source-imports/namespaces/{namespace_slug}",
            json=body,
        )

    def _send_package(
        self,
        suffix: str,
        namespace_slug: str,
        content: bytes,
        metadata: dict[str, object],
    ) -> dict[str, object]:
        return self._request(
            "POST",
            f"/api/cli/v1/source-imports/{namespace_slug}/skills{suffix}",
            files={
                "file": ("skill.zip", content, "application/zip"),
                "metadata": (None, json.dumps(metadata, separators=(",", ":")), "application/json"),
            },
        )

    def validate_skill(self, namespace_slug: str, content: bytes, metadata: dict[str, object]) -> dict[str, object]:
        return self._send_package("/validate", namespace_slug, content, metadata)

    def submit_skill(self, namespace_slug: str, content: bytes, metadata: dict[str, object]) -> dict[str, object]:
        return self._send_package("", namespace_slug, content, metadata)

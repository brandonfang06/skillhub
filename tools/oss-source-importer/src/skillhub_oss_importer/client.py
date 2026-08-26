from __future__ import annotations

import json
import ssl
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
from uuid import uuid4


class SkillHubError(RuntimeError):
    pass


class AuthorizationError(SkillHubError):
    pass


class TransportError(SkillHubError):
    pass


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None


_skillhub_https_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
_skillhub_https_context.check_hostname = False
_skillhub_https_context.verify_mode = ssl.CERT_NONE
_open_without_redirects = build_opener(
    _NoRedirectHandler(),
    HTTPSHandler(context=_skillhub_https_context),
).open


class SkillHubClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        timeout_seconds: float,
        *,
        opener: Callable[..., Any] = _open_without_redirects,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout_seconds = timeout_seconds
        self._opener = opener

    def close(self) -> None:
        pass

    def _request(
        self,
        method: str,
        path: str,
        *,
        content: bytes,
        content_type: str,
    ) -> dict[str, object]:
        request_id = str(uuid4())
        request = Request(
            f"{self._base_url}{path}",
            data=content,
            method=method,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._token}",
                "Content-Type": content_type,
                "User-Agent": "skillhub-oss-source-importer/0.1",
                "X-Request-Id": request_id,
            },
        )
        try:
            with self._opener(request, timeout=self._timeout_seconds) as response:
                status_code = response.getcode()
                response_headers = response.headers
                response_body = response.read()
        except HTTPError as exc:
            status_code = exc.code
            response_headers = exc.headers
            try:
                response_body = exc.read()
            finally:
                exc.close()
        except (OSError, TimeoutError, URLError) as exc:
            raise TransportError(f"SkillHub request failed ({request_id}): {type(exc).__name__}") from exc
        if status_code in {401, 403}:
            raise AuthorizationError(f"SkillHub authorization failed ({status_code}, {request_id})")
        try:
            payload = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SkillHubError(
                f"SkillHub returned non-JSON response ({status_code}, {request_id})"
            ) from exc
        if not isinstance(payload, dict):
            raise SkillHubError(f"SkillHub returned non-JSON response ({status_code}, {request_id})")
        if status_code >= 400 or payload.get("code") != 0:
            detail = payload.get("detail") or payload.get("msg") or "request failed"
            raise SkillHubError(f"SkillHub request failed ({status_code}, {request_id}): {detail}")
        data = dict(payload.get("data") or {})
        data["requestId"] = str(payload.get("requestId") or response_headers.get("X-Request-Id") or request_id)
        return data

    def ensure_namespace(self, namespace_slug: str, body: dict[str, object]) -> dict[str, object]:
        content = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return self._request(
            "PUT",
            f"/api/cli/v1/source-imports/namespaces/{namespace_slug}",
            content=content,
            content_type="application/json",
        )

    def _send_package(
        self,
        suffix: str,
        namespace_slug: str,
        content: bytes,
        metadata: dict[str, object],
    ) -> dict[str, object]:
        boundary = f"skillhub-{uuid4().hex}"
        metadata_content = json.dumps(metadata, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        multipart = b"".join(
            (
                f"--{boundary}\r\n".encode(),
                b'Content-Disposition: form-data; name="file"; filename="skill.zip"\r\n',
                b"Content-Type: application/zip\r\n\r\n",
                content,
                b"\r\n",
                f"--{boundary}\r\n".encode(),
                b'Content-Disposition: form-data; name="metadata"\r\n',
                b"Content-Type: application/json\r\n\r\n",
                metadata_content,
                b"\r\n",
                f"--{boundary}--\r\n".encode(),
            )
        )
        return self._request(
            "POST",
            f"/api/cli/v1/source-imports/{namespace_slug}/skills{suffix}",
            content=multipart,
            content_type=f"multipart/form-data; boundary={boundary}",
        )

    def validate_skill(
        self,
        namespace_slug: str,
        content: bytes,
        metadata: dict[str, object],
    ) -> dict[str, object]:
        return self._send_package("/validate", namespace_slug, content, metadata)

    def submit_skill(
        self,
        namespace_slug: str,
        content: bytes,
        metadata: dict[str, object],
    ) -> dict[str, object]:
        return self._send_package("", namespace_slug, content, metadata)

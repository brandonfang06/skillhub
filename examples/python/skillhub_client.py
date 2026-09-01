"""Dependency-light reference client for the SkillHub REST API."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests


class SkillHubError(RuntimeError):
    """Raised when SkillHub returns a non-zero business code."""

    def __init__(self, code: Any, message: str, request_id: str | None = None):
        self.code = code
        self.request_id = request_id
        suffix = f" (requestId={request_id})" if request_id else ""
        super().__init__(f"SkillHub API error {code}: {message}{suffix}")


class SkillHubClient:
    """Thin wrapper over the public and token-authenticated SkillHub API."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: int = 30,
        session: requests.Session | None = None,
    ):
        resolved_base_url = base_url or os.environ.get("SKILLHUB_URL")
        if not resolved_base_url:
            raise ValueError(
                "base_url is required (pass it explicitly or set SKILLHUB_URL)"
            )
        self.base_url = resolved_base_url.rstrip("/")
        self.token = token or os.environ.get("SKILLHUB_TOKEN")
        self.timeout = timeout
        self.session = session or requests.Session()

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if extra:
            headers.update(extra)
        return headers

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    @staticmethod
    def _unwrap(response: requests.Response) -> Any:
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and "code" in payload and "data" in payload:
            if payload.get("code") not in (0, None):
                raise SkillHubError(
                    payload.get("code"),
                    payload.get("msg", ""),
                    payload.get("requestId"),
                )
            return payload["data"]
        return payload

    def search(
        self,
        keyword: str | None = None,
        namespace: str | None = None,
        page: int = 0,
        size: int = 20,
    ) -> Any:
        params = {
            key: value
            for key, value in {
                "keyword": keyword,
                "namespace": namespace,
                "page": page,
                "size": size,
            }.items()
            if value is not None
        }
        response = self.session.get(
            self._url("/api/v1/skills"),
            params=params,
            headers=self._headers(),
            timeout=self.timeout,
        )
        return self._unwrap(response)

    def get_skill(self, namespace: str, slug: str) -> Any:
        response = self.session.get(
            self._url(f"/api/v1/skills/{namespace}/{slug}"),
            headers=self._headers(),
            timeout=self.timeout,
        )
        return self._unwrap(response)

    def list_versions(self, namespace: str, slug: str) -> Any:
        response = self.session.get(
            self._url(f"/api/v1/skills/{namespace}/{slug}/versions"),
            headers=self._headers(),
            timeout=self.timeout,
        )
        return self._unwrap(response)

    def resolve(
        self,
        namespace: str,
        slug: str,
        version: str | None = None,
        tag: str | None = None,
    ) -> Any:
        params = {
            key: value
            for key, value in {"version": version, "tag": tag}.items()
            if value is not None
        }
        response = self.session.get(
            self._url(f"/api/v1/skills/{namespace}/{slug}/resolve"),
            params=params,
            headers=self._headers(),
            timeout=self.timeout,
        )
        return self._unwrap(response)

    def download(
        self,
        namespace: str,
        slug: str,
        version: str | None = None,
        dest: str | None = None,
    ) -> str:
        path = f"/api/v1/skills/{namespace}/{slug}/download"
        if version:
            path = f"/api/v1/skills/{namespace}/{slug}/versions/{version}/download"
        destination = Path(dest or (f"{slug}-{version}.zip" if version else f"{slug}.zip"))
        with self.session.get(
            self._url(path),
            headers=self._headers(),
            timeout=self.timeout,
            stream=True,
        ) as response:
            response.raise_for_status()
            with destination.open("wb") as output:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        output.write(chunk)
        return str(destination)

    def whoami(self) -> Any:
        response = self.session.get(
            self._url("/api/v1/whoami"),
            headers=self._headers(),
            timeout=self.timeout,
        )
        return self._unwrap(response)

    def publish(
        self,
        zip_path: str,
        namespace: str,
        request_id: str | None = None,
    ) -> Any:
        extra = {"X-Request-Id": request_id} if request_id else None
        with Path(zip_path).open("rb") as archive:
            response = self.session.post(
                self._url("/api/v1/publish"),
                files={"file": (Path(zip_path).name, archive, "application/zip")},
                data={"namespace": namespace},
                headers=self._headers(extra),
                timeout=self.timeout,
            )
        return self._unwrap(response)

    def star(self, skill_id: str) -> Any:
        response = self.session.put(
            self._url(f"/api/v1/skills/{skill_id}/star"),
            headers=self._headers(),
            timeout=self.timeout,
        )
        return self._unwrap(response)

    def rate(self, skill_id: str, score: int) -> Any:
        if not 1 <= score <= 5:
            raise ValueError("score must be between 1 and 5")
        response = self.session.put(
            self._url(f"/api/v1/skills/{skill_id}/rating"),
            json={"score": score},
            headers=self._headers(),
            timeout=self.timeout,
        )
        return self._unwrap(response)

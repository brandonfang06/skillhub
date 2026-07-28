from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import re
from urllib.parse import quote, urlsplit

import httpx


class GitLabImportError(RuntimeError):
    def __init__(self, detail: str, *, status_code: int = 502) -> None:
        super().__init__(detail)
        self.status_code = status_code


@dataclass(frozen=True)
class GitLabClientConfig:
    base_url: str
    token: str = field(repr=False)
    allowed_groups: tuple[str, ...]
    connect_timeout_ms: int
    read_timeout_ms: int
    archive_max_bytes: int
    ca_bundle_path: str = ""
    allow_insecure_http: bool = False


@dataclass(frozen=True)
class GitLabPreviewSource:
    project_id: str
    project_full_path: str
    requested_ref: str
    commit_sha: str
    source_web_url: str
    archive: bytes = field(repr=False)
    archive_sha256: str


@dataclass(frozen=True)
class GitLabResolvedRef:
    project_id: str
    project_full_path: str
    requested_ref: str
    commit_sha: str
    source_web_url: str


class GitLabImportClient:
    def __init__(
        self,
        config: GitLabClientConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        parsed = urlsplit(config.base_url.rstrip("/"))
        if (
            parsed.scheme != "https"
            and not (config.allow_insecure_http and parsed.scheme == "http")
        ):
            raise GitLabImportError(
                "error.repositoryImport.gitlab.baseUrl.httpsRequired",
                status_code=422,
            )
        if not parsed.hostname or parsed.query or parsed.fragment:
            raise GitLabImportError(
                "error.repositoryImport.gitlab.baseUrl.invalid",
                status_code=422,
            )
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self._client = client

    def _validate_project(self, project_path: str) -> str:
        normalized = project_path.strip().strip("/")
        if (
            not normalized
            or ".." in normalized.split("/")
            or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+", normalized)
        ):
            raise GitLabImportError(
                "error.repositoryImport.gitlab.project.invalid",
                status_code=422,
            )
        if not any(
            normalized == group or normalized.startswith(f"{group}/")
            for group in self.config.allowed_groups
        ):
            raise GitLabImportError(
                "error.repositoryImport.gitlab.project.notAllowed",
                status_code=403,
            )
        return normalized

    def _new_client(self) -> httpx.AsyncClient:
        timeout = httpx.Timeout(
            connect=self.config.connect_timeout_ms / 1000,
            read=self.config.read_timeout_ms / 1000,
            write=self.config.read_timeout_ms / 1000,
            pool=self.config.connect_timeout_ms / 1000,
        )
        verify: bool | str = self.config.ca_bundle_path or True
        return httpx.AsyncClient(
            timeout=timeout,
            verify=verify,
            follow_redirects=False,
        )

    async def resolve_ref(
        self,
        project_path: str,
        requested_ref: str,
    ) -> GitLabResolvedRef:
        project = self._validate_project(project_path)
        ref = requested_ref.strip()
        if not ref or len(ref) > 256:
            raise GitLabImportError(
                "error.repositoryImport.gitlab.ref.invalid",
                status_code=422,
            )
        client = self._client or self._new_client()
        owns_client = self._client is None
        try:
            headers = {"PRIVATE-TOKEN": self.config.token}
            project_id = quote(project, safe="")
            ref_id = quote(ref, safe="")
            commit_url = (
                f"{self.base_url}/api/v4/projects/{project_id}"
                f"/repository/commits/{ref_id}"
            )
            commit_response = await client.get(commit_url, headers=headers)
            self._require_success(commit_response)
            payload = commit_response.json()
            commit_sha = str(payload.get("id", ""))
            if not re.fullmatch(r"[0-9a-fA-F]{40}", commit_sha):
                raise GitLabImportError(
                    "error.repositoryImport.gitlab.commit.invalid"
                )
            source_web_url = str(payload.get("web_url", self.base_url))
            return GitLabResolvedRef(
                project_id=project_id,
                project_full_path=project,
                requested_ref=ref,
                commit_sha=commit_sha.lower(),
                source_web_url=source_web_url,
            )
        except httpx.TimeoutException as exc:
            raise GitLabImportError(
                "error.repositoryImport.gitlab.timeout",
                status_code=504,
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            if isinstance(exc, GitLabImportError):
                raise
            raise GitLabImportError(
                "error.repositoryImport.gitlab.upstream"
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

    async def preview_source(
        self,
        project_path: str,
        requested_ref: str,
    ) -> GitLabPreviewSource:
        resolved = await self.resolve_ref(project_path, requested_ref)
        archive = await self.download_archive(
            resolved.project_full_path,
            resolved.commit_sha,
        )
        return GitLabPreviewSource(
            project_id=resolved.project_id,
            project_full_path=resolved.project_full_path,
            requested_ref=resolved.requested_ref,
            commit_sha=resolved.commit_sha,
            source_web_url=resolved.source_web_url,
            archive=archive,
            archive_sha256=sha256(archive).hexdigest(),
        )

    async def download_archive(
        self,
        project_path: str,
        commit_sha: str,
    ) -> bytes:
        project = self._validate_project(project_path)
        if not re.fullmatch(r"[0-9a-fA-F]{40}", commit_sha):
            raise GitLabImportError(
                "error.repositoryImport.gitlab.commit.invalid",
                status_code=422,
            )
        client = self._client or self._new_client()
        owns_client = self._client is None
        try:
            return await self._download_archive(
                client,
                quote(project, safe=""),
                commit_sha.lower(),
                {"PRIVATE-TOKEN": self.config.token},
            )
        except httpx.TimeoutException as exc:
            raise GitLabImportError(
                "error.repositoryImport.gitlab.timeout",
                status_code=504,
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise GitLabImportError(
                "error.repositoryImport.gitlab.upstream"
            ) from exc
        finally:
            if owns_client:
                await client.aclose()

    async def _download_archive(
        self,
        client: httpx.AsyncClient,
        project_id: str,
        commit_sha: str,
        headers: dict[str, str],
    ) -> bytes:
        archive_url = (
            f"{self.base_url}/api/v4/projects/{project_id}"
            f"/repository/archive.zip"
        )
        content = bytearray()
        async with client.stream(
            "GET",
            archive_url,
            params={"sha": commit_sha},
            headers=headers,
        ) as response:
            self._require_success(response)
            declared = response.headers.get("content-length")
            if declared and int(declared) > self.config.archive_max_bytes:
                raise GitLabImportError(
                    "error.repositoryImport.gitlab.archive.tooLarge",
                    status_code=413,
                )
            async for chunk in response.aiter_bytes():
                content.extend(chunk)
                if len(content) > self.config.archive_max_bytes:
                    raise GitLabImportError(
                        "error.repositoryImport.gitlab.archive.tooLarge",
                        status_code=413,
                    )
        return bytes(content)

    @staticmethod
    def _require_success(response: httpx.Response) -> None:
        if 300 <= response.status_code < 400:
            raise GitLabImportError(
                "error.repositoryImport.gitlab.upstream.redirect"
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise GitLabImportError(
                "error.repositoryImport.gitlab.upstream"
            )

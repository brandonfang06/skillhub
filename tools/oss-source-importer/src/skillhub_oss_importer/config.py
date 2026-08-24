from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from .github_source import SourceError, canonicalize_repository


class ConfigError(ValueError):
    pass


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Config:
    base_url: str
    service_token: str = field(repr=False)
    repository_url: str
    namespace_slug: str
    namespace_display_name: str
    owner_provider_code: str
    owner_login_name: str
    trigger_provider_code: str
    trigger_login_name: str | None
    project_dir: Path
    source_clone_url: str = field(repr=False)
    source_subdirectory: Path
    report_path: Path
    timeout_seconds: float
    commit_sha: str
    ref_type: str
    source_ref: str | None
    pipeline_id: str | None
    job_id: str | None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        values = os.environ if env is None else env
        base_url = _required(values, "SKILLHUB_BASE_URL").rstrip("/")
        parsed_base = urlsplit(base_url)
        if parsed_base.scheme not in {"http", "https"} or not parsed_base.netloc:
            raise ConfigError("SKILLHUB_BASE_URL must be an absolute HTTP(S) URL")
        try:
            repository = canonicalize_repository(_required(values, "SKILLHUB_SOURCE_REPOSITORY_URL"))
        except SourceError as exc:
            raise ConfigError(str(exc)) from exc
        project_dir = Path(_required(values, "CI_PROJECT_DIR")).resolve()
        source_clone_url = _required(values, "CI_REPOSITORY_URL")
        parsed_clone_url = urlsplit(source_clone_url)
        if parsed_clone_url.scheme not in {"http", "https"} or not parsed_clone_url.netloc:
            raise ConfigError("CI_REPOSITORY_URL must be an absolute HTTP(S) URL")
        source_value = values.get("SKILLHUB_IMPORT_SOURCE_ROOT", ".").strip() or "."
        source_subdirectory = Path(source_value)
        if source_subdirectory.is_absolute() or ".." in source_subdirectory.parts:
            raise ConfigError(
                "SKILLHUB_IMPORT_SOURCE_ROOT must be a safe relative path within the cloned repository"
            )
        commit_sha = _required(values, "CI_COMMIT_SHA").lower()
        if not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
            raise ConfigError("CI_COMMIT_SHA must be a 40-character hexadecimal SHA")
        tag = values.get("CI_COMMIT_TAG", "").strip()
        branch = values.get("CI_COMMIT_BRANCH", "").strip()
        ref_type, source_ref = ("TAG", tag) if tag else (("BRANCH", branch) if branch else ("COMMIT", None))
        owner_provider = _required(values, "SKILLHUB_NAMESPACE_OWNER_PROVIDER_CODE")
        report_value = values.get("SKILLHUB_IMPORT_REPORT_PATH", "skillhub-oss-import-report.json").strip()
        report_path = Path(report_value)
        if not report_path.is_absolute():
            report_path = project_dir / report_path
        try:
            timeout = float(values.get("SKILLHUB_IMPORT_TIMEOUT_SECONDS", "60"))
        except ValueError as exc:
            raise ConfigError("SKILLHUB_IMPORT_TIMEOUT_SECONDS must be numeric") from exc
        if timeout <= 0:
            raise ConfigError("SKILLHUB_IMPORT_TIMEOUT_SECONDS must be positive")
        trigger_login = values.get("SKILLHUB_IMPORT_TRIGGER_LOGIN_NAME", "").strip() or None
        return cls(
            base_url=base_url,
            service_token=_required(values, "SKILLHUB_SERVICE_TOKEN"),
            repository_url=repository.canonical_url,
            namespace_slug=repository.namespace_slug,
            namespace_display_name=repository.namespace_display_name,
            owner_provider_code=owner_provider,
            owner_login_name=_required(values, "SKILLHUB_NAMESPACE_OWNER_LOGIN_NAME"),
            trigger_provider_code=(
                values.get("SKILLHUB_IMPORT_TRIGGER_PROVIDER_CODE", "").strip() or owner_provider
            ),
            trigger_login_name=trigger_login,
            project_dir=project_dir,
            source_clone_url=source_clone_url,
            source_subdirectory=source_subdirectory,
            report_path=report_path.resolve(),
            timeout_seconds=timeout,
            commit_sha=commit_sha,
            ref_type=ref_type,
            source_ref=source_ref,
            pipeline_id=values.get("CI_PIPELINE_ID", "").strip() or None,
            job_id=values.get("CI_JOB_ID", "").strip() or None,
        )

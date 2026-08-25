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


_HANDOFF_REQUIRED = frozenset(
    {
        "SKILLHUB_SOURCE_REPOSITORY_URL",
        "SKILLHUB_SOURCE_REF_TYPE",
        "SKILLHUB_DEV_GITLAB_REPOSITORY_URL",
        "SKILLHUB_DEV_GITLAB_BRANCH",
        "SKILLHUB_SOURCE_SCAN_STATUS",
    }
)
_HANDOFF_OPTIONAL = frozenset(
    {
        "SKILLHUB_SOURCE_REF",
        "SKILLHUB_SOURCE_SCAN_ID",
        "SKILLHUB_IMPORT_TRIGGER_PROVIDER_CODE",
        "SKILLHUB_IMPORT_TRIGGER_LOGIN_NAME",
    }
)
_HANDOFF_VARIABLES = _HANDOFF_REQUIRED | _HANDOFF_OPTIONAL
_GIT_BRANCH_PATTERN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._/-]{0,254}")


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _git_branch(env: Mapping[str, str], name: str) -> str:
    value = _required(env, name)
    parts = value.split("/")
    if (
        not _GIT_BRANCH_PATTERN.fullmatch(value)
        or ".." in value
        or "//" in value
        or "@{" in value
        or value.endswith(("/", "."))
        or any(part.startswith(".") or part.endswith(".lock") for part in parts)
    ):
        raise ConfigError(f"{name} must be a valid Git branch")
    return value


def _load_pull_code_handoff(project_dir: Path, env: Mapping[str, str]) -> dict[str, str]:
    handoff_path = project_dir / "pull-code.env"
    try:
        resolved_path = handoff_path.resolve(strict=True)
        resolved_path.relative_to(project_dir)
        content = resolved_path.read_bytes()
    except (OSError, ValueError) as exc:
        raise ConfigError("pull-code.env must be a readable file inside CI_PROJECT_DIR") from exc
    if len(content) > 64 * 1024:
        raise ConfigError("pull-code.env exceeds 64 KiB")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError("pull-code.env must be UTF-8") from exc

    handoff: dict[str, str] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line:
            continue
        if "=" not in line:
            raise ConfigError(f"Invalid pull-code.env line {line_number}")
        name, value = line.split("=", 1)
        if name not in _HANDOFF_VARIABLES:
            raise ConfigError(f"Unexpected pull-code.env variable: {name}")
        if name in handoff:
            raise ConfigError(f"Duplicate pull-code.env variable: {name}")
        if value != value.strip():
            raise ConfigError(f"pull-code.env value has surrounding whitespace: {name}")
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ConfigError(f"pull-code.env value contains control characters: {name}")
        handoff[name] = value

    missing = sorted(_HANDOFF_REQUIRED - handoff.keys())
    if missing:
        raise ConfigError(f"Missing pull-code.env variable: {missing[0]}")
    for name in _HANDOFF_VARIABLES:
        environment_value = env.get(name, "")
        artifact_value = handoff.get(name, "")
        if environment_value and environment_value != artifact_value:
            raise ConfigError(f"{name} conflicts with pull-code.env")

    values = dict(env)
    for name in _HANDOFF_VARIABLES:
        values.pop(name, None)
    values.update(handoff)
    return values


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
    gitlab_job_token: str = field(repr=False)
    source_subdirectory: Path
    report_path: Path
    timeout_seconds: float
    dev_gitlab_branch: str
    ref_type: str
    source_ref: str | None
    scan_status: str
    scan_id: str | None
    pipeline_id: str | None
    job_id: str | None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        environment = os.environ if env is None else env
        project_dir = Path(_required(environment, "CI_PROJECT_DIR")).resolve()
        values = _load_pull_code_handoff(project_dir, environment)
        base_url = _required(values, "SKILLHUB_BASE_URL").rstrip("/")
        parsed_base = urlsplit(base_url)
        if parsed_base.scheme not in {"http", "https"} or not parsed_base.netloc:
            raise ConfigError("SKILLHUB_BASE_URL must be an absolute HTTP(S) URL")
        try:
            repository = canonicalize_repository(_required(values, "SKILLHUB_SOURCE_REPOSITORY_URL"))
        except SourceError as exc:
            raise ConfigError(str(exc)) from exc
        source_clone_url = _required(values, "SKILLHUB_DEV_GITLAB_REPOSITORY_URL")
        parsed_clone_url = urlsplit(source_clone_url)
        if (
            parsed_clone_url.scheme != "https"
            or not parsed_clone_url.netloc
            or parsed_clone_url.username is not None
            or parsed_clone_url.password is not None
            or parsed_clone_url.query
            or parsed_clone_url.fragment
        ):
            raise ConfigError(
                "SKILLHUB_DEV_GITLAB_REPOSITORY_URL must be a credential-free absolute HTTPS URL"
            )
        source_value = values.get("SKILLHUB_IMPORT_SOURCE_ROOT", ".").strip() or "."
        source_subdirectory = Path(source_value)
        if source_subdirectory.is_absolute() or ".." in source_subdirectory.parts:
            raise ConfigError(
                "SKILLHUB_IMPORT_SOURCE_ROOT must be a safe relative path within the cloned repository"
            )
        dev_gitlab_branch = _git_branch(values, "SKILLHUB_DEV_GITLAB_BRANCH")
        scan_status = values.get("SKILLHUB_SOURCE_SCAN_STATUS", "").strip()
        if scan_status != "PASSED":
            raise ConfigError("SKILLHUB_SOURCE_SCAN_STATUS must be PASSED")
        ref_type = _required(values, "SKILLHUB_SOURCE_REF_TYPE")
        if ref_type not in {"TAG", "BRANCH", "COMMIT"}:
            raise ConfigError("SKILLHUB_SOURCE_REF_TYPE must be TAG, BRANCH, or COMMIT")
        source_ref = values.get("SKILLHUB_SOURCE_REF", "").strip() or None
        if ref_type in {"TAG", "BRANCH"} and source_ref is None:
            raise ConfigError("SKILLHUB_SOURCE_REF is required for TAG and BRANCH sources")
        if ref_type == "COMMIT" and source_ref is not None:
            raise ConfigError("SKILLHUB_SOURCE_REF must be empty for COMMIT sources")
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
            gitlab_job_token=_required(values, "CI_JOB_TOKEN"),
            source_subdirectory=source_subdirectory,
            report_path=report_path.resolve(),
            timeout_seconds=timeout,
            dev_gitlab_branch=dev_gitlab_branch,
            ref_type=ref_type,
            source_ref=source_ref,
            scan_status=scan_status,
            scan_id=values.get("SKILLHUB_SOURCE_SCAN_ID", "").strip() or None,
            pipeline_id=values.get("CI_PIPELINE_ID", "").strip() or None,
            job_id=values.get("CI_JOB_ID", "").strip() or None,
        )

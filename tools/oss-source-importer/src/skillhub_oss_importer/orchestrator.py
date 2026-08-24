from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .client import AuthorizationError, SkillHubError, TransportError
from .discovery import discover_skill_roots
from .github_source import SourceCheckout
from .package import BuiltPackage, build_skill_package


def _metadata(
    config: Any,
    checkout: SourceCheckout,
    package: BuiltPackage,
) -> dict[str, object]:
    data: dict[str, object] = {
        "repositoryUrl": config.repository_url,
        "repositoryRevisionSha": checkout.commit_sha,
        "sourceRefType": checkout.ref_type,
        "sourcePath": package.source_path,
        "pipelineId": config.pipeline_id,
        "jobId": config.job_id,
    }
    if checkout.source_ref is not None:
        data["sourceRef"] = checkout.source_ref
    if not package.has_explicit_version:
        data["versionOverride"] = f"git-{checkout.commit_sha}"
    if config.trigger_login_name is not None:
        data["initiatorProviderCode"] = config.trigger_provider_code
        data["initiatorLoginName"] = config.trigger_login_name
    return data


def run_import(config: Any, client: Any, checkout: SourceCheckout) -> dict[str, object]:
    started_at = datetime.now(UTC).isoformat()
    source_root = (checkout.checkout_dir / config.source_subdirectory).resolve()
    roots = discover_skill_roots(checkout.checkout_dir, source_root)
    root_paths = {root.path for root in roots}
    packages = [build_skill_package(root, root_paths) for root in roots]
    namespace = client.ensure_namespace(
        config.namespace_slug,
        {
            "repositoryUrl": config.repository_url,
            "displayName": config.namespace_display_name,
            "fallbackOwnerProviderCode": config.owner_provider_code,
            "fallbackOwnerLoginName": config.owner_login_name,
        },
    )
    records: list[dict[str, object]] = []
    validation_failed = False
    for package in packages:
        record: dict[str, object] = {"sourcePath": package.source_path}
        try:
            validation = client.validate_skill(
                config.namespace_slug,
                package.content,
                _metadata(config, checkout, package),
            )
            record["validation"] = validation
        except (AuthorizationError, TransportError):
            raise
        except (SkillHubError, ValueError) as exc:
            record["validationError"] = str(exc)
            validation_failed = True
        records.append(record)
    if validation_failed:
        return _report(config, checkout, namespace, records, started_at, "VALIDATION_FAILED")

    partial = False
    for package, record in zip(packages, records, strict=True):
        validation = record["validation"]
        if isinstance(validation, dict) and str(validation.get("outcome", "")).startswith("SKIPPED_"):
            record["submission"] = validation
            continue
        try:
            record["submission"] = client.submit_skill(
                config.namespace_slug,
                package.content,
                _metadata(config, checkout, package),
            )
        except (AuthorizationError, TransportError):
            raise
        except (SkillHubError, ValueError) as exc:
            record["submissionError"] = str(exc)
            partial = True
    return _report(
        config,
        checkout,
        namespace,
        records,
        started_at,
        "PARTIAL_SUBMISSION" if partial else "SUCCESS",
    )


def _report(
    config: Any,
    checkout: SourceCheckout,
    namespace: dict[str, object],
    records: list[dict[str, object]],
    started_at: str,
    status: str,
) -> dict[str, object]:
    return {
        "status": status,
        "startedAt": started_at,
        "finishedAt": datetime.now(UTC).isoformat(),
        "repositoryUrl": config.repository_url,
        "commitSha": checkout.commit_sha,
        "sourceRefType": checkout.ref_type,
        "sourceRef": checkout.source_ref,
        "namespaceSlug": config.namespace_slug,
        "namespace": namespace,
        "pipelineId": config.pipeline_id,
        "jobId": config.job_id,
        "skills": records,
    }

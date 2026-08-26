from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .client import AuthorizationError, SkillHubError, TransportError
from .discovery import discover_skill_roots
from .github_source import SourceCheckout
from .job_logging import job_value
from .package import BuiltPackage, build_skill_package

logger = logging.getLogger(__name__)
FALLBACK_OWNER_PROVIDER_CODE = "keycloak"


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
    if config.trigger_login_name is not None:
        data["initiatorProviderCode"] = config.trigger_provider_code
        data["initiatorLoginName"] = config.trigger_login_name
    return data


def run_import(config: Any, client: Any, checkout: SourceCheckout) -> dict[str, object]:
    started_at = datetime.now(timezone.utc).isoformat()
    source_root = (checkout.checkout_dir / config.source_subdirectory).resolve()
    logger.info("event=discovery_started source_root=%s", job_value(config.source_subdirectory))
    roots = discover_skill_roots(checkout.checkout_dir, source_root)
    logger.info("event=discovery_completed skills=%s", len(roots))
    root_paths = {root.path for root in roots}
    logger.info("event=packaging_started skills=%s", len(roots))
    packages = [build_skill_package(root, root_paths) for root in roots]
    logger.info(
        "event=packaging_completed skills=%s bytes=%s",
        len(packages),
        sum(len(package.content) for package in packages),
    )
    logger.info("event=namespace_started namespace=%s", job_value(config.namespace_slug))
    namespace = client.ensure_namespace(
        config.namespace_slug,
        {
            "repositoryUrl": config.repository_url,
            "displayName": config.namespace_display_name,
            "fallbackOwnerProviderCode": FALLBACK_OWNER_PROVIDER_CODE,
            "fallbackOwnerLoginName": config.owner_login_name,
        },
    )
    logger.info(
        "event=namespace_completed namespace=%s outcome=%s request_id=%s",
        job_value(config.namespace_slug),
        job_value(namespace.get("outcome")),
        job_value(namespace.get("requestId")),
    )
    records: list[dict[str, object]] = []
    validation_failed = False
    for index, package in enumerate(packages, start=1):
        record: dict[str, object] = {"sourcePath": package.source_path}
        logger.info(
            "event=validation_started source_path=%s index=%s total=%s",
            job_value(package.source_path),
            index,
            len(packages),
        )
        try:
            validation = client.validate_skill(
                config.namespace_slug,
                package.content,
                _metadata(config, checkout, package),
            )
            record["validation"] = validation
            logger.info(
                "event=validation_completed source_path=%s outcome=%s version=%s request_id=%s",
                job_value(package.source_path),
                job_value(validation.get("outcome")),
                job_value(validation.get("version")),
                job_value(validation.get("requestId")),
            )
        except (AuthorizationError, TransportError) as exc:
            logger.error(
                "event=validation_failed source_path=%s error_type=%s error=%s",
                job_value(package.source_path),
                job_value(type(exc).__name__),
                job_value(str(exc)),
            )
            raise
        except (SkillHubError, ValueError) as exc:
            record["validationError"] = str(exc)
            validation_failed = True
            logger.error(
                "event=validation_failed source_path=%s error_type=%s error=%s",
                job_value(package.source_path),
                job_value(type(exc).__name__),
                job_value(str(exc)),
            )
        records.append(record)
    if validation_failed:
        logger.warning('event=submission_phase_skipped reason="validation_failed"')
        _log_summary("VALIDATION_FAILED", records)
        return _report(config, checkout, namespace, records, started_at, "VALIDATION_FAILED")

    partial = False
    for index, (package, record) in enumerate(zip(packages, records), start=1):
        validation = record["validation"]
        if isinstance(validation, dict) and str(validation.get("outcome", "")).startswith("SKIPPED_"):
            record["submission"] = validation
            logger.info(
                "event=submission_skipped source_path=%s outcome=%s version=%s request_id=%s",
                job_value(package.source_path),
                job_value(validation.get("outcome")),
                job_value(validation.get("version")),
                job_value(validation.get("requestId")),
            )
            continue
        logger.info(
            "event=submission_started source_path=%s index=%s total=%s",
            job_value(package.source_path),
            index,
            len(packages),
        )
        try:
            submission = client.submit_skill(
                config.namespace_slug,
                package.content,
                _metadata(config, checkout, package),
            )
            record["submission"] = submission
            logger.info(
                "event=submission_completed source_path=%s outcome=%s version=%s request_id=%s",
                job_value(package.source_path),
                job_value(submission.get("outcome")),
                job_value(submission.get("version")),
                job_value(submission.get("requestId")),
            )
        except (AuthorizationError, TransportError) as exc:
            logger.error(
                "event=submission_failed source_path=%s error_type=%s error=%s",
                job_value(package.source_path),
                job_value(type(exc).__name__),
                job_value(str(exc)),
            )
            raise
        except (SkillHubError, ValueError) as exc:
            record["submissionError"] = str(exc)
            partial = True
            logger.error(
                "event=submission_failed source_path=%s error_type=%s error=%s",
                job_value(package.source_path),
                job_value(type(exc).__name__),
                job_value(str(exc)),
            )
    status = "PARTIAL_SUBMISSION" if partial else "SUCCESS"
    _log_summary(status, records)
    return _report(
        config,
        checkout,
        namespace,
        records,
        started_at,
        status,
    )


def _log_summary(status: str, records: list[dict[str, object]]) -> None:
    validated = sum("validation" in record for record in records)
    submitted = 0
    skipped = 0
    failed = 0
    for record in records:
        if "validationError" in record or "submissionError" in record:
            failed += 1
        submission = record.get("submission")
        if not isinstance(submission, dict):
            continue
        if str(submission.get("outcome", "")).startswith("SKIPPED_"):
            skipped += 1
        else:
            submitted += 1
    logger.info(
        "event=import_completed status=%s skills=%s validated=%s submitted=%s skipped=%s failed=%s",
        job_value(status),
        len(records),
        validated,
        submitted,
        skipped,
        failed,
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
        "finishedAt": datetime.now(timezone.utc).isoformat(),
        "repositoryUrl": config.repository_url,
        "commitSha": checkout.commit_sha,
        "sourceRefType": checkout.ref_type,
        "sourceRef": checkout.source_ref,
        "scanStatus": config.scan_status,
        "scanId": config.scan_id,
        "namespaceSlug": config.namespace_slug,
        "namespace": namespace,
        "pipelineId": config.pipeline_id,
        "jobId": config.job_id,
        "skills": records,
    }

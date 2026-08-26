from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from .client import AuthorizationError, SkillHubClient, TransportError
from .config import Config, ConfigError
from .discovery import DiscoveryError
from .github_source import SourceError, clone_repository, clone_url_without_userinfo
from .job_logging import configured_job_logging, job_value
from .orchestrator import run_import
from .report import write_report

EXIT_SUCCESS = 0
EXIT_CONFIGURATION = 2
EXIT_VALIDATION = 3
EXIT_AUTHORIZATION = 4
EXIT_TRANSPORT = 5
EXIT_PARTIAL_SUBMISSION = 6
EXIT_INTERNAL = 10

logger = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Clone the landed Dev GitLab branch and import every SKILL.md root"
    )
    parser.add_argument("--json-report", type=Path, help="Override SKILLHUB_IMPORT_REPORT_PATH")
    return parser


def _write_failure(
    path: Path,
    *,
    status: str,
    exit_code: int,
    error_type: str,
    error: str,
) -> int:
    logger.error(
        "event=importer_failed status=%s exit_code=%s error_type=%s error=%s",
        job_value(status),
        exit_code,
        job_value(error_type),
        job_value(error),
    )
    try:
        write_report(path, {"status": status, "error": error})
    except OSError as exc:
        logger.error(
            "event=report_write_failed path=%s error_type=%s",
            job_value(path),
            job_value(type(exc).__name__),
        )
    else:
        logger.info("event=report_written path=%s", job_value(path))
    logger.info(
        "event=importer_finished status=%s exit_code=%s",
        job_value(status),
        exit_code,
    )
    return exit_code


def _run(args: argparse.Namespace) -> int:
    logger.info("event=importer_started")
    configured_path = args.json_report or Path(
        os.environ.get("SKILLHUB_IMPORT_REPORT_PATH", "skillhub-oss-import-report.json")
    )
    client: SkillHubClient | None = None
    try:
        config = Config.from_env()
        logger.info(
            "event=config_loaded repository=%s skillhub_base_url=%s timeout_seconds=%s "
            "dev_branch=%s ref_type=%s source_ref=%s namespace=%s scan_id=%s pipeline_id=%s "
            "job_id=%s skillhub_tls_verify=false",
            job_value(config.repository_url),
            job_value(config.base_url),
            config.timeout_seconds,
            job_value(config.dev_gitlab_branch),
            job_value(config.ref_type),
            job_value(config.source_ref),
            job_value(config.namespace_slug),
            job_value(config.scan_id),
            job_value(config.pipeline_id),
            job_value(config.job_id),
        )
        report_path = args.json_report.resolve() if args.json_report else config.report_path
        configured_path = report_path
        client = SkillHubClient(config.base_url, config.service_token, config.timeout_seconds)
        with tempfile.TemporaryDirectory(prefix="skillhub-oss-import-") as temporary_directory:
            logger.info(
                "event=clone_started repository=%s dev_branch=%s",
                job_value(clone_url_without_userinfo(config.source_clone_url)),
                job_value(config.dev_gitlab_branch),
            )
            checkout = clone_repository(
                config.source_clone_url,
                Path(temporary_directory) / "checkout",
                config.dev_gitlab_branch,
                config.ref_type,
                config.source_ref,
                config.gitlab_job_token,
            )
            logger.info(
                "event=clone_completed revision=%s",
                job_value(checkout.commit_sha),
            )
            report = run_import(config, client, checkout)
        write_report(report_path, report)
        logger.info("event=report_written path=%s", job_value(report_path))
        if report["status"] == "VALIDATION_FAILED":
            logger.info('event=importer_finished status="VALIDATION_FAILED" exit_code=3')
            return EXIT_VALIDATION
        if report["status"] == "PARTIAL_SUBMISSION":
            logger.info('event=importer_finished status="PARTIAL_SUBMISSION" exit_code=6')
            return EXIT_PARTIAL_SUBMISSION
        logger.info('event=importer_finished status="SUCCESS" exit_code=0')
        return EXIT_SUCCESS
    except ConfigError as exc:
        return _write_failure(
            configured_path,
            status="CONFIGURATION_FAILED",
            exit_code=EXIT_CONFIGURATION,
            error_type=type(exc).__name__,
            error=str(exc),
        )
    except (DiscoveryError, SourceError) as exc:
        return _write_failure(
            configured_path,
            status="VALIDATION_FAILED",
            exit_code=EXIT_VALIDATION,
            error_type=type(exc).__name__,
            error=str(exc),
        )
    except AuthorizationError as exc:
        return _write_failure(
            configured_path,
            status="AUTHORIZATION_FAILED",
            exit_code=EXIT_AUTHORIZATION,
            error_type=type(exc).__name__,
            error=str(exc),
        )
    except TransportError as exc:
        return _write_failure(
            configured_path,
            status="TRANSPORT_FAILED",
            exit_code=EXIT_TRANSPORT,
            error_type=type(exc).__name__,
            error=str(exc),
        )
    except Exception as exc:  # noqa: BLE001 -- CLI boundary must emit the stable internal-failure exit.
        error_type = type(exc).__name__
        return _write_failure(
            configured_path,
            status="INTERNAL_FAILED",
            exit_code=EXIT_INTERNAL,
            error_type=error_type,
            error=error_type,
        )
    finally:
        if client is not None:
            client.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    with configured_job_logging():
        return _run(args)


if __name__ == "__main__":
    sys.exit(main())

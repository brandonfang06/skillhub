from __future__ import annotations

import argparse
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from .client import AuthorizationError, SkillHubClient, TransportError
from .config import Config, ConfigError
from .discovery import DiscoveryError
from .github_source import SourceError, clone_repository
from .orchestrator import run_import
from .report import write_report

EXIT_SUCCESS = 0
EXIT_CONFIGURATION = 2
EXIT_VALIDATION = 3
EXIT_AUTHORIZATION = 4
EXIT_TRANSPORT = 5
EXIT_PARTIAL_SUBMISSION = 6
EXIT_INTERNAL = 10


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Clone the landed Dev GitLab commit and import every SKILL.md root"
    )
    parser.add_argument("--json-report", type=Path, help="Override SKILLHUB_IMPORT_REPORT_PATH")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    configured_path = args.json_report or Path(
        os.environ.get("SKILLHUB_IMPORT_REPORT_PATH", "skillhub-oss-import-report.json")
    )
    client: SkillHubClient | None = None
    try:
        config = Config.from_env()
        report_path = args.json_report.resolve() if args.json_report else config.report_path
        client = SkillHubClient(config.base_url, config.service_token, config.timeout_seconds)
        with tempfile.TemporaryDirectory(prefix="skillhub-oss-import-") as temporary_directory:
            checkout = clone_repository(
                config.source_clone_url,
                Path(temporary_directory) / "checkout",
                config.dev_gitlab_commit_sha,
                config.ref_type,
                config.source_ref,
                config.gitlab_job_token,
            )
            report = run_import(config, client, checkout)
        write_report(report_path, report)
        if report["status"] == "VALIDATION_FAILED":
            return EXIT_VALIDATION
        if report["status"] == "PARTIAL_SUBMISSION":
            return EXIT_PARTIAL_SUBMISSION
        return EXIT_SUCCESS
    except ConfigError as exc:
        write_report(configured_path, {"status": "CONFIGURATION_FAILED", "error": str(exc)})
        return EXIT_CONFIGURATION
    except (DiscoveryError, SourceError) as exc:
        write_report(configured_path, {"status": "VALIDATION_FAILED", "error": str(exc)})
        return EXIT_VALIDATION
    except AuthorizationError as exc:
        write_report(configured_path, {"status": "AUTHORIZATION_FAILED", "error": str(exc)})
        return EXIT_AUTHORIZATION
    except TransportError as exc:
        write_report(configured_path, {"status": "TRANSPORT_FAILED", "error": str(exc)})
        return EXIT_TRANSPORT
    except Exception as exc:  # noqa: BLE001 -- CLI boundary must emit the stable internal-failure exit.
        write_report(configured_path, {"status": "INTERNAL_FAILED", "error": type(exc).__name__})
        return EXIT_INTERNAL
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    sys.exit(main())

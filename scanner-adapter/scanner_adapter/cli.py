"""Command-line teaching interface for the scanner adapter."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol, TextIO

from scanner_adapter.client import ScannerClient
from scanner_adapter.config import ScannerAdapterConfig
from scanner_adapter.errors import (
    ConfigurationError,
    InputValidationError,
    ScannerHttpError,
    ScannerResponseError,
    ScannerUnavailableError,
)
from scanner_adapter.models import ScanResult


class ClientProtocol(Protocol):
    def __enter__(self) -> ClientProtocol: ...

    def __exit__(self, *args: object) -> None: ...

    def health(self) -> Mapping[str, object]: ...

    def list_analyzers(self) -> list[Mapping[str, object]]: ...

    def scan_zip(self, path: str | Path) -> ScanResult: ...


ClientFactory = Callable[[ScannerAdapterConfig], ClientProtocol]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Call a deployed Cisco Skill Scanner from a small Python example.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("health", help="Call the scanner health endpoint.")
    commands.add_parser("analyzers", help="List analyzers advertised by the scanner.")

    scan = commands.add_parser("scan", help="Synchronously scan one skill ZIP.")
    scan.add_argument("zip_path", type=Path, help="Path to one skill .zip file.")
    scan.add_argument(
        "--check-health",
        action="store_true",
        help="Call /health before uploading the ZIP.",
    )
    scan.add_argument(
        "--output",
        type=Path,
        help="Write normalized JSON to this file instead of stdout.",
    )
    scan.add_argument(
        "--fail-on-unsafe",
        action="store_true",
        help="Return exit code 5 after printing a completed unsafe result.",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    client_factory: ClientFactory = ScannerClient,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    output_stream = sys.stdout if stdout is None else stdout
    error_stream = sys.stderr if stderr is None else stderr

    try:
        config = ScannerAdapterConfig.from_env(environ)
        with client_factory(config) as client:
            if args.command == "health":
                _print_json(client.health(), output_stream)
                return 0
            if args.command == "analyzers":
                _print_json(client.list_analyzers(), output_stream)
                return 0

            if args.check_health:
                client.health()
            result = client.scan_zip(args.zip_path)
            output = result.normalized.to_dict()
            if args.output is None:
                _print_json(output, output_stream)
            else:
                args.output.write_text(
                    _json_text(output) + "\n",
                    encoding="utf-8",
                )
            if args.fail_on_unsafe and not result.normalized.is_safe:
                return 5
            return 0
    except ConfigurationError as error:
        print(f"configuration error: {error}", file=error_stream)
        return 2
    except InputValidationError as error:
        print(f"input error: {error}", file=error_stream)
        return 3
    except (ScannerUnavailableError, ScannerHttpError, ScannerResponseError) as error:
        print(f"scanner error: {error}", file=error_stream)
        return 4


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _print_json(value: object, output: TextIO) -> None:
    print(_json_text(value), file=output)

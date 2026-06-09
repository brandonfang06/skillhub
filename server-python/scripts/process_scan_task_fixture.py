from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.core.config import get_settings
from app.core.database import create_database_engine, dispose_database_engine
from app.publish.scan_worker import StaticScannerClient, parse_scan_task_fields, process_scan_task
from app.publish.scanner_result import SecurityScanResultInput


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fields-file", required=True)
    parser.add_argument("--storage-base-path", required=True)
    parser.add_argument("--scan-temp-dir", required=True)
    parser.add_argument("--scan-id", required=True)
    parser.add_argument("--verdict", required=True)
    parser.add_argument("--findings-count", required=True, type=int)
    parser.add_argument("--max-severity")
    parser.add_argument("--findings-file")
    parser.add_argument("--duration", default=0.0, type=float)
    args = parser.parse_args()

    fields = json.loads(Path(args.fields_file).read_text(encoding="utf-8"))
    if not isinstance(fields, dict):
        raise ValueError("fields-file must decode to an object")
    task = parse_scan_task_fields({str(key): str(value) for key, value in fields.items()})
    if task is None:
        raise ValueError("Invalid scan task fields")

    findings_json = Path(args.findings_file).read_text(encoding="utf-8") if args.findings_file else "[]"
    findings = json.loads(findings_json)
    if not isinstance(findings, list):
        raise ValueError("findings must decode to a list")

    scanner = StaticScannerClient(
        SecurityScanResultInput(
            scan_id=args.scan_id,
            verdict=args.verdict,
            findings_count=args.findings_count,
            max_severity=args.max_severity,
            findings=findings,
            scan_duration_seconds=args.duration,
        )
    )

    engine = create_database_engine(get_settings())
    try:
        async with engine.begin() as connection:
            result = await process_scan_task(
                connection,
                task,
                scanner,
                storage_base_path=args.storage_base_path,
                scan_temp_dir=args.scan_temp_dir,
            )
        print(
            json.dumps(
                {
                    "auditId": result.audit_id,
                    "previousStatus": result.previous_status,
                    "newStatus": result.new_status,
                    "statusChanged": result.status_changed,
                    "skillPath": scanner.seen_tasks[0].skill_path if scanner.seen_tasks else None,
                },
                separators=(",", ":"),
            )
        )
    finally:
        await dispose_database_engine(engine)


if __name__ == "__main__":
    asyncio.run(main())

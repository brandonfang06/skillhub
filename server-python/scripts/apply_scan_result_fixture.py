from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.core.config import get_settings
from app.core.database import create_database_engine, dispose_database_engine
from app.publish.scanner_result import SecurityScanResultInput, apply_security_scan_result


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version-id", required=True, type=int)
    parser.add_argument("--scanner-type", default="skill-scanner")
    parser.add_argument("--scan-id", required=True)
    parser.add_argument("--verdict", required=True)
    parser.add_argument("--findings-count", required=True, type=int)
    parser.add_argument("--max-severity")
    parser.add_argument("--findings-json", default="[]")
    parser.add_argument("--findings-file")
    parser.add_argument("--duration", default=0.0, type=float)
    args = parser.parse_args()

    findings_json = Path(args.findings_file).read_text(encoding="utf-8") if args.findings_file else args.findings_json
    findings = json.loads(findings_json)
    if not isinstance(findings, list):
        raise ValueError("findings-json must decode to a list")

    engine = create_database_engine(get_settings())
    try:
        async with engine.begin() as connection:
            result = await apply_security_scan_result(
                connection,
                version_id=args.version_id,
                scanner_type=args.scanner_type,
                scan_result=SecurityScanResultInput(
                    scan_id=args.scan_id,
                    verdict=args.verdict,
                    findings_count=args.findings_count,
                    max_severity=args.max_severity,
                    findings=findings,
                    scan_duration_seconds=args.duration,
                ),
            )
        print(
            json.dumps(
                {
                    "auditId": result.audit_id,
                    "previousStatus": result.previous_status,
                    "newStatus": result.new_status,
                    "statusChanged": result.status_changed,
                },
                separators=(",", ":"),
            )
        )
    finally:
        await dispose_database_engine(engine)


if __name__ == "__main__":
    asyncio.run(main())

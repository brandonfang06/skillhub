from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.core.config import get_settings
from app.core.database import create_database_engine, dispose_database_engine
from app.publish.scan_consumer import DEFAULT_SCAN_GROUP_NAME, RedisStreamClient, ScanConsumerRuntime
from app.publish.scan_worker import StaticScannerClient
from app.publish.scanner_result import SecurityScanResultInput


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Consume one Redis scan task batch with a deterministic scanner result.")
    parser.add_argument("--storage-base-path", required=True)
    parser.add_argument("--scan-temp-dir", required=True)
    parser.add_argument("--stream-key", required=True)
    parser.add_argument("--group-name", default=DEFAULT_SCAN_GROUP_NAME)
    parser.add_argument("--consumer-name", default="scanner-python-fixture")
    parser.add_argument("--scan-id", required=True)
    parser.add_argument("--verdict", required=True)
    parser.add_argument("--findings-count", required=True, type=int)
    parser.add_argument("--max-severity", required=True)
    parser.add_argument("--findings-file", required=True)
    parser.add_argument("--duration", required=True, type=float)
    parser.add_argument("--count", default=10, type=int)
    parser.add_argument("--block-ms", default=2000, type=int)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    findings = json.loads(Path(args.findings_file).read_text(encoding="utf-8"))
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
    redis = RedisStreamClient(get_settings().redis_url)
    runtime = ScanConsumerRuntime(
        redis,
        stream_key=args.stream_key,
        group_name=args.group_name,
        consumer_name=args.consumer_name,
        storage_base_path=args.storage_base_path,
        scan_temp_dir=args.scan_temp_dir,
    )
    engine = create_database_engine(get_settings())
    try:
        async with engine.begin() as connection:
            result = await runtime.consume_once(connection, scanner, count=args.count, block_ms=args.block_ms)
    finally:
        await dispose_database_engine(engine)

    print(
        json.dumps(
            {
                "processed": result.processed,
                "acknowledged": result.acknowledged,
                "retried": result.retried,
                "failed": result.failed,
                "invalid": result.invalid,
                "scannerSeenTasks": len(scanner.seen_tasks),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())

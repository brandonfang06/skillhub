from __future__ import annotations

from app.publish.scanner_handoff import build_scan_stream_fields, encode_resp_command
from app.publish.side_effects import ScanTaskPayload


def scan_task() -> ScanTaskPayload:
    return ScanTaskPayload(
        task_id="task-1",
        version_id=42,
        skill_path=None,
        bundle_key="packages/7/42/bundle.zip",
        publisher_id="local-admin",
        created_at_millis=1780928116000,
        metadata={"scannerType": "skill-scanner"},
    )


def test_build_scan_stream_fields_matches_java_producer_upload_mode() -> None:
    assert build_scan_stream_fields(scan_task()) == {
        "taskId": "task-1",
        "versionId": "42",
        "bundleKey": "packages/7/42/bundle.zip",
        "publisherId": "local-admin",
        "createdAtMillis": "1780928116000",
        "scannerType": "skill-scanner",
    }


def test_encode_resp_command_uses_bulk_string_arguments() -> None:
    command = encode_resp_command(["XADD", "skillhub:scan:requests", "*", "taskId", "task-1"])

    assert command == (
        b"*5\r\n"
        b"$4\r\nXADD\r\n"
        b"$22\r\nskillhub:scan:requests\r\n"
        b"$1\r\n*\r\n"
        b"$6\r\ntaskId\r\n"
        b"$6\r\ntask-1\r\n"
    )

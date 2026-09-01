from __future__ import annotations

from datetime import UTC, datetime
from types import TracebackType
from typing import Any

import pytest

from app.publish.scan_outbox import ScanOutboxDispatcher


class FakeResult:
    def __init__(
        self,
        *,
        rows: list[dict[str, Any]] | None = None,
        rowcount: int = 0,
    ) -> None:
        self.rows = rows or []
        self.rowcount = rowcount

    def mappings(self) -> FakeResult:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self.rows

    def first(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None


class FakeConnection:
    def __init__(self, results: list[FakeResult]) -> None:
        self.results = results
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(
        self,
        statement: Any,
        params: dict[str, Any] | None = None,
    ) -> FakeResult:
        self.statements.append(str(statement))
        self.params.append(params or {})
        return self.results.pop(0)


class FakeTransaction:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        pass


class FakeEngine:
    def __init__(self, connections: list[FakeConnection]) -> None:
        self.connections = connections

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connections.pop(0))


class RecordingPublisher:
    def __init__(self) -> None:
        self.tasks: list[Any] = []

    async def publish_scan_task(self, task: Any) -> None:
        self.tasks.append(task)


class FailingPublisher:
    async def publish_scan_task(self, task: Any) -> None:
        raise ConnectionError(f"Redis unavailable for {task.task_id}")


@pytest.mark.anyio
async def test_dispatch_once_claims_due_task_publishes_and_marks_sent() -> None:
    now = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
    claim_connection = FakeConnection(
        [
            FakeResult(
                rows=[
                    {
                        "id": 17,
                        "task_id": "task-17",
                        "version_id": 42,
                        "skill_path": None,
                        "bundle_key": "packages/7/42/bundle.zip",
                        "publisher_id": "publisher-1",
                        "metadata": {
                            "scannerType": "skill-scanner",
                            "skillhub.request_id": "request-17",
                        },
                        "entity_version": 3,
                    }
                ]
            )
        ]
    )
    mark_connection = FakeConnection([FakeResult(rowcount=1)])
    publisher = RecordingPublisher()
    dispatcher = ScanOutboxDispatcher(
        FakeEngine([claim_connection, mark_connection]),
        publisher,
        batch_size=5,
        lease_seconds=120,
    )

    result = await dispatcher.dispatch_once(now=now)

    assert result.claimed == 1
    assert result.sent == 1
    assert result.retried == 0
    assert result.failed == 0
    assert len(publisher.tasks) == 1
    assert publisher.tasks[0].task_id == "task-17"
    assert publisher.tasks[0].bundle_key == "packages/7/42/bundle.zip"
    assert publisher.tasks[0].request_id == "request-17"
    assert "FOR UPDATE SKIP LOCKED" in claim_connection.statements[0]
    assert "status = 'SENT'" in mark_connection.statements[0]
    assert mark_connection.params[0]["entity_version"] == 3


@pytest.mark.anyio
async def test_dispatch_once_schedules_retry_after_transient_publish_failure() -> None:
    now = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
    claim_connection = FakeConnection(
        [
            FakeResult(
                rows=[
                    {
                        "id": 18,
                        "task_id": "task-18",
                        "version_id": 43,
                        "skill_path": None,
                        "bundle_key": "packages/7/43/bundle.zip",
                        "publisher_id": "publisher-1",
                        "metadata": {"scannerType": "skill-scanner"},
                        "retry_count": 0,
                        "entity_version": 4,
                    }
                ]
            )
        ]
    )
    retry_connection = FakeConnection([FakeResult(rowcount=1)])
    dispatcher = ScanOutboxDispatcher(
        FakeEngine([claim_connection, retry_connection]),
        FailingPublisher(),
        max_attempts=3,
        max_backoff_seconds=60,
    )

    result = await dispatcher.dispatch_once(now=now)

    assert result.claimed == 1
    assert result.sent == 0
    assert result.retried == 1
    assert result.failed == 0
    assert "status = 'PENDING'" in retry_connection.statements[0]
    assert retry_connection.params[0]["retry_count"] == 1
    assert retry_connection.params[0]["next_attempt_at"] == datetime(
        2026, 8, 31, 12, 0, 2, tzinfo=UTC
    )
    assert retry_connection.params[0]["last_error"] == (
        "Redis unavailable for task-18"
    )


@pytest.mark.anyio
async def test_dispatch_once_marks_outbox_and_scanning_version_failed_at_limit() -> None:
    now = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
    claim_connection = FakeConnection(
        [
            FakeResult(
                rows=[
                    {
                        "id": 19,
                        "task_id": "task-19",
                        "version_id": 44,
                        "skill_path": None,
                        "bundle_key": "packages/7/44/bundle.zip",
                        "publisher_id": "publisher-1",
                        "metadata": {"scannerType": "skill-scanner"},
                        "retry_count": 2,
                        "entity_version": 5,
                    }
                ]
            )
        ]
    )
    failure_connection = FakeConnection(
        [
            FakeResult(rowcount=1),
            FakeResult(rows=[{"id": 44}]),
            FakeResult(rows=[{"id": 801}]),
            FakeResult(),
        ]
    )
    dispatcher = ScanOutboxDispatcher(
        FakeEngine([claim_connection, failure_connection]),
        FailingPublisher(),
        max_attempts=3,
    )

    result = await dispatcher.dispatch_once(now=now)

    assert result.claimed == 1
    assert result.sent == 0
    assert result.retried == 0
    assert result.failed == 1
    assert "status = 'FAILED'" in failure_connection.statements[0]
    assert failure_connection.params[0]["retry_count"] == 3
    assert "status = 'SCAN_FAILED'" in failure_connection.statements[1]
    assert failure_connection.params[1]["version_id"] == 44
    assert "INSERT INTO local_security_scan_execution" in failure_connection.statements[3]
    assert failure_connection.params[3]["scan_status"] == "FAILED"
    assert failure_connection.params[3]["failure_code"] == "OUTBOX_DELIVERY_FAILED"


@pytest.mark.anyio
async def test_cleanup_sent_deletes_only_rows_older_than_retention_window() -> None:
    now = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)
    cleanup_connection = FakeConnection([FakeResult(rowcount=3)])
    dispatcher = ScanOutboxDispatcher(
        FakeEngine([cleanup_connection]),
        RecordingPublisher(),
    )

    deleted = await dispatcher.cleanup_sent(now=now, retention_days=7)

    assert deleted == 3
    assert "DELETE FROM scan_task_outbox" in cleanup_connection.statements[0]
    assert "status = 'SENT'" in cleanup_connection.statements[0]
    assert cleanup_connection.params[0]["sent_before"] == datetime(
        2026, 8, 24, 12, 0, tzinfo=UTC
    )

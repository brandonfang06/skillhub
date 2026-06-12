from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from app.audit.writer import write_audit_log
from app.db.unit_of_work import transaction_connection


class _FakeTransaction:
    def __init__(self, connection: object) -> None:
        self.connection = connection
        self.entered = False
        self.exited = False

    async def __aenter__(self) -> object:
        self.entered = True
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.exited = True


class _FakeEngine:
    def __init__(self, connection: object) -> None:
        self.transaction = _FakeTransaction(connection)

    def begin(self) -> _FakeTransaction:
        return self.transaction


class _FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[object, dict[str, object]]] = []

    async def execute(self, statement: object, params: dict[str, object]) -> None:
        self.calls.append((statement, params))


def test_transaction_connection_yields_engine_transaction_connection() -> None:
    connection = object()
    engine = _FakeEngine(connection)

    async def run() -> None:
        async with transaction_connection(engine) as yielded:
            assert yielded is connection
            assert engine.transaction.entered is True

        assert engine.transaction.exited is True

    asyncio.run(run())


def test_write_audit_log_uses_common_insert_shape() -> None:
    connection = _FakeConnection()
    created_at = datetime(2026, 6, 12, tzinfo=UTC)

    async def run() -> None:
        await write_audit_log(
            connection,
            actor_user_id="admin",
            action="SKILL_ARCHIVED",
            target_type="SKILL",
            target_id=42,
            request_id="req-1",
            client_ip="127.0.0.1",
            user_agent="pytest",
            detail={"status": "ARCHIVED"},
            created_at=created_at,
        )

    asyncio.run(run())

    assert len(connection.calls) == 1
    statement, params = connection.calls[0]
    assert "INSERT INTO audit_log" in str(statement)
    assert params == {
        "actor_user_id": "admin",
        "action": "SKILL_ARCHIVED",
        "target_type": "SKILL",
        "target_id": 42,
        "request_id": "req-1",
        "client_ip": "127.0.0.1",
        "user_agent": "pytest",
        "detail_json": json.dumps({"status": "ARCHIVED"}),
        "created_at": created_at,
    }


def test_write_audit_log_preserves_null_detail() -> None:
    connection = _FakeConnection()
    created_at = datetime(2026, 6, 12, tzinfo=UTC)

    async def run() -> None:
        await write_audit_log(
            connection,
            actor_user_id="admin",
            action="SKILL_UNARCHIVED",
            target_type="SKILL",
            target_id=42,
            request_id=None,
            client_ip=None,
            user_agent=None,
            detail={},
            created_at=created_at,
        )

    asyncio.run(run())

    _, params = connection.calls[0]
    assert params["detail_json"] is None

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest

from app.publish.publication_outcomes import (
    PublicationOutcomeInput,
    apply_publication_outcomes,
)


class FakeResult:
    def __init__(
        self,
        *,
        row: dict[str, Any] | None = None,
        rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.row = row
        self.rows = rows or []

    def mappings(self) -> FakeResult:
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        return self.row

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class FakePublicationConnection:
    def __init__(self, *, fail_on_notification: bool = False) -> None:
        self.fail_on_notification = fail_on_notification
        self.display_name = "Agent Helper"
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.notifications: list[dict[str, Any]] = []
        self.search_upserts = 0
        self._next_notification_id = 800

    async def execute(
        self, statement: object, params: dict[str, Any] | None = None
    ) -> FakeResult:
        sql = str(statement)
        values = params or {}
        self.statements.append(sql)
        self.params.append(values)

        if "FOR UPDATE" in sql and "FROM skill s" in sql:
            return FakeResult(
                row={
                    "skill_id": 101,
                    "owner_id": "owner",
                    "slug": "agent-helper",
                    "display_name": self.display_name,
                    "namespace_slug": "team-a",
                    "version": "1.1.0",
                }
            )
        if "JOIN LATERAL" in sql and "FROM skill s" in sql:
            return FakeResult(
                row={
                    "skill_id": 101,
                    "namespace_id": 20,
                    "namespace_slug": "team-a",
                    "owner_id": "owner",
                    "slug": "agent-helper",
                    "display_name": self.display_name,
                    "summary": "Helps agents",
                    "visibility": "PRIVATE",
                    "status": "ACTIVE",
                    "parsed_metadata_json": None,
                }
            )
        if "FROM skill_label" in sql:
            return FakeResult(rows=[])
        if "INSERT INTO skill_search_document" in sql:
            self.search_upserts += 1
            return FakeResult()
        if "notification_preference" in sql and "owner_id" in values:
            return FakeResult(row={"enabled": True})
        if "FROM skill_subscription" in sql:
            return FakeResult(rows=[{"user_id": "subscriber-a"}])
        if "INSERT INTO notification" in sql:
            if self.fail_on_notification:
                raise RuntimeError("notification write failed")
            key = (
                values["recipient_id"],
                values["event_type"],
                values["entity_id"],
                values["version_id_text"],
            )
            if any(
                (
                    row["recipient_id"],
                    row["event_type"],
                    row["entity_id"],
                    row["version_id_text"],
                )
                == key
                for row in self.notifications
            ):
                return FakeResult(rows=[])
            self._next_notification_id += 1
            row = {
                "id": self._next_notification_id,
                "category": "PUBLISH",
                "entity_type": "SKILL",
                **values,
            }
            self.notifications.append(row)
            return FakeResult(rows=[row])
        raise AssertionError(f"unexpected SQL: {sql}")


class FakeTransaction:
    def __init__(self, engine: FakeEngine) -> None:
        self.engine = engine
        self.notification_snapshot: list[dict[str, Any]] = []
        self.search_upserts_snapshot = 0

    async def __aenter__(self) -> FakePublicationConnection:
        self.notification_snapshot = deepcopy(self.engine.connection.notifications)
        self.search_upserts_snapshot = self.engine.connection.search_upserts
        return self.engine.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is None:
            self.engine.events.append("commit")
        else:
            self.engine.connection.notifications = self.notification_snapshot
            self.engine.connection.search_upserts = self.search_upserts_snapshot
            self.engine.events.append("rollback")


class FakeEngine:
    def __init__(self, connection: FakePublicationConnection) -> None:
        self.connection = connection
        self.events: list[str] = []

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self)


class FakeNotificationFanout:
    def __init__(self, transaction_events: list[str]) -> None:
        self.transaction_events = transaction_events
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, user_id: str, payload: dict[str, Any]) -> None:
        assert self.transaction_events[-1] == "commit"
        self.published.append((user_id, payload))


class FailingNotificationFanout:
    def __init__(self) -> None:
        self.attempts = 0

    async def publish(self, user_id: str, payload: dict[str, Any]) -> None:
        self.attempts += 1
        raise RuntimeError("SSE connection failed")


def outcome_input() -> PublicationOutcomeInput:
    return PublicationOutcomeInput(
        skill_id=101,
        version_id=42,
        publisher_id="owner",
        created_at=datetime(2026, 6, 9, 14, 30, tzinfo=UTC),
    )


@pytest.mark.anyio
async def test_publication_outcomes_refresh_search_and_notify_owner_and_subscribers_after_commit() -> (
    None
):
    connection = FakePublicationConnection()
    engine = FakeEngine(connection)
    fanout = FakeNotificationFanout(engine.events)

    await apply_publication_outcomes(engine, outcome_input(), fanout)

    assert engine.events == ["commit"]
    assert connection.search_upserts == 1
    assert [
        (row["recipient_id"], row["event_type"]) for row in connection.notifications
    ] == [
        ("owner", "SKILL_PUBLISHED"),
        ("subscriber-a", "SUBSCRIPTION_NEW_VERSION"),
    ]
    assert [user_id for user_id, _payload in fanout.published] == [
        "owner",
        "subscriber-a",
    ]
    bodies = [row["body_json"] for row in connection.notifications]
    assert bodies == [
        '{"skillId":101,"versionId":42,"namespace":"team-a","slug":"agent-helper","skillName":"Agent Helper","version":"1.1.0"}',
        '{"skillId":101,"versionId":42,"namespace":"team-a","slug":"agent-helper","skillName":"Agent Helper","version":"1.1.0"}',
    ]
    lock_index = next(
        index for index, sql in enumerate(connection.statements) if "FOR UPDATE" in sql
    )
    search_index = next(
        index
        for index, sql in enumerate(connection.statements)
        if "INSERT INTO skill_search_document" in sql
    )
    notification_index = next(
        index
        for index, sql in enumerate(connection.statements)
        if "INSERT INTO notification" in sql
    )
    assert lock_index < search_index < notification_index
    assert all(
        "NOT EXISTS" in sql
        for sql in connection.statements
        if "INSERT INTO notification" in sql
    )


@pytest.mark.anyio
async def test_publication_outcome_replay_does_not_duplicate_durable_or_fanout_notifications() -> (
    None
):
    connection = FakePublicationConnection()
    engine = FakeEngine(connection)
    fanout = FakeNotificationFanout(engine.events)

    await apply_publication_outcomes(engine, outcome_input(), fanout)
    connection.display_name = "Renamed Agent Helper"
    await apply_publication_outcomes(engine, outcome_input(), fanout)

    assert connection.search_upserts == 2
    assert len(connection.notifications) == 2
    assert len(fanout.published) == 2
    assert engine.events == ["commit", "commit"]


@pytest.mark.anyio
async def test_publication_outcome_fanout_failure_keeps_durable_rows_and_replay_does_not_duplicate(
    caplog: pytest.LogCaptureFixture,
) -> None:
    connection = FakePublicationConnection()
    engine = FakeEngine(connection)
    fanout = FailingNotificationFanout()
    caplog.set_level(logging.ERROR, logger="uvicorn.error")

    await apply_publication_outcomes(engine, outcome_input(), fanout)
    await apply_publication_outcomes(engine, outcome_input(), fanout)

    assert engine.events == ["commit", "commit"]
    assert len(connection.notifications) == 2
    assert fanout.attempts == 1
    assert "durable publication notifications remain authoritative" in caplog.text


@pytest.mark.anyio
async def test_publication_outcome_rollback_does_not_fanout_or_leave_partial_state() -> (
    None
):
    connection = FakePublicationConnection(fail_on_notification=True)
    engine = FakeEngine(connection)
    fanout = FakeNotificationFanout(engine.events)

    with pytest.raises(RuntimeError, match="notification write failed"):
        await apply_publication_outcomes(engine, outcome_input(), fanout)

    assert engine.events == ["rollback"]
    assert connection.search_upserts == 0
    assert connection.notifications == []
    assert fanout.published == []

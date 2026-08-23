from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import lifecycle as lifecycle_api
from app.lifecycle.skill import (
    SkillConfirmPublishInput,
    SkillLifecycleError,
    confirm_publish_skill_version,
)
from app.main import create_app


class FakeResult:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self.row = row

    def mappings(self) -> "FakeResult":
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        return self.row


class FakeTransaction:
    def __init__(self, connection: "FakeConfirmPublishConnection", events: list[str]) -> None:
        self.connection = connection
        self.events = events

    async def __aenter__(self) -> "FakeConfirmPublishConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.events.append("commit" if exc_type is None else "rollback")
        return None


class FakeEngine:
    def __init__(self, connection: "FakeConfirmPublishConnection") -> None:
        self.connection = connection
        self.transaction_events: list[str] = []
        connection.transaction_events = self.transaction_events

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection, self.transaction_events)


class FakeNotificationFanout:
    async def publish(self, user_id: str, payload: dict[str, Any]) -> None:
        raise AssertionError("the injected outcome writer owns fanout in this test")


class FakeConfirmPublishConnection:
    def __init__(
        self,
        *,
        skill_visibility: str = "PRIVATE",
        version_status: str = "UPLOADED",
        owner_id: str = "owner",
        namespace_role: str | None = None,
        latest_version_id: int | None = None,
        fail_audit: bool = False,
        confirm_audit_actor: str = "owner",
        published_at: datetime | None = None,
    ) -> None:
        self.skill_visibility = skill_visibility
        self.version_status = version_status
        self.owner_id = owner_id
        self.namespace_role = namespace_role
        self.latest_version_id = latest_version_id
        self.fail_audit = fail_audit
        self.confirm_audit_actor = confirm_audit_actor
        self.published_at = published_at
        self.transaction_events: list[str] = []
        self.audit_read_commit_count: int | None = None
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        values = params or {}
        self.statements.append(sql)
        self.params.append(values)

        if "FROM namespace n" in sql and "JOIN skill s" in sql:
            return FakeResult(
                {
                    "skill_id": 101,
                    "namespace_id": 20,
                    "namespace_slug": "team-a",
                    "namespace_status": "ACTIVE",
                    "skill_slug": "agent-helper",
                    "owner_id": self.owner_id,
                    "visibility": self.skill_visibility,
                    "status": "ACTIVE",
                    "latest_version_id": self.latest_version_id,
                }
            )
        if "FROM namespace_member" in sql:
            return FakeResult({"role": self.namespace_role}) if self.namespace_role else FakeResult()
        if "FROM skill_version" in sql:
            return FakeResult(
                {
                    "version_id": 42,
                    "version": "1.1.0",
                    "status": self.version_status,
                    "published_at": self.published_at,
                }
            )
        if "UPDATE skill_version" in sql:
            return FakeResult()
        if "UPDATE skill" in sql:
            return FakeResult()
        if "FROM audit_log" in sql and "CONFIRM_PUBLISH" in sql:
            self.audit_read_commit_count = self.transaction_events.count("commit")
            return FakeResult({"actor_user_id": self.confirm_audit_actor})
        if "INSERT INTO audit_log" in sql:
            if self.fail_audit:
                raise RuntimeError("audit write failed")
            return FakeResult()
        raise AssertionError(f"unexpected SQL: {sql}")


def confirm_input(**overrides: Any) -> SkillConfirmPublishInput:
    data: dict[str, Any] = {
        "namespace": "team-a",
        "slug": "agent-helper",
        "version": "1.1.0",
        "user_id": "owner",
        "request_id": "req-confirm-publish",
        "client_ip": "127.0.0.1",
        "user_agent": "pytest",
        "now": datetime(2026, 6, 9, 14, 30, tzinfo=UTC),
    }
    data.update(overrides)
    return SkillConfirmPublishInput(**data)


async def ignore_publication_outcomes(*_args: object) -> None:
    return None


@pytest.mark.anyio
async def test_confirm_publish_updates_private_uploaded_version_latest_pointer_and_audit() -> None:
    connection = FakeConfirmPublishConnection()

    response = await confirm_publish_skill_version(
        FakeEngine(connection),
        confirm_input(),
        publication_outcome_writer=ignore_publication_outcomes,
    )

    assert response == {"skillId": 101, "versionId": 42, "action": "CONFIRM_PUBLISH", "status": "PUBLISHED"}
    version_update = next(index for index, sql in enumerate(connection.statements) if "UPDATE skill_version" in sql)
    skill_update = next(index for index, sql in enumerate(connection.statements) if "UPDATE skill\n" in sql)
    audit_insert = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO audit_log" in sql)
    assert version_update < skill_update < audit_insert
    assert "updated_at" not in connection.statements[version_update]
    assert connection.params[version_update]["status"] == "PUBLISHED"
    assert connection.params[version_update]["published_at"] == datetime(2026, 6, 9, 14, 30, tzinfo=UTC)
    assert connection.params[skill_update]["latest_version_id"] == 42
    assert connection.params[skill_update]["updated_by"] == "owner"
    assert connection.params[audit_insert]["action"] == "CONFIRM_PUBLISH"
    assert connection.params[audit_insert]["target_type"] == "SKILL_VERSION"
    assert connection.params[audit_insert]["target_id"] == 42
    assert json.loads(connection.params[audit_insert]["detail_json"]) == {"version": "1.1.0"}


@pytest.mark.anyio
async def test_confirm_publish_persists_outcomes_in_status_transaction_and_fans_out_after_commit() -> None:
    connection = FakeConfirmPublishConnection()
    engine = FakeEngine(connection)
    fanout = FakeNotificationFanout()
    outcome_calls: list[tuple[object, object]] = []
    fanout_calls: list[tuple[object, object, object]] = []

    async def publication_outcome_writer(
        outcome_connection: object,
        outcome: object,
    ) -> list[dict[str, object]]:
        assert engine.transaction_events == []
        outcome_calls.append((outcome_connection, outcome))
        return [{"recipient_id": "subscriber-a"}]

    async def publication_notification_publisher(
        notification_fanout: object,
        rows: object,
        outcome: object,
    ) -> None:
        assert engine.transaction_events == ["commit"]
        fanout_calls.append((notification_fanout, rows, outcome))

    response = await confirm_publish_skill_version(
        engine,
        confirm_input(),
        notification_fanout=fanout,
        publication_outcome_writer=publication_outcome_writer,
        publication_notification_publisher=publication_notification_publisher,
    )

    assert response["status"] == "PUBLISHED"
    assert len(outcome_calls) == 1
    assert outcome_calls[0][0] is connection
    outcome = outcome_calls[0][1]
    assert outcome.skill_id == 101
    assert outcome.version_id == 42
    assert outcome.publisher_id == "owner"
    assert outcome.created_at == datetime(2026, 6, 9, 14, 30, tzinfo=UTC)
    assert fanout_calls == [
        (
            fanout,
            [{"recipient_id": "subscriber-a"}],
            outcome,
        )
    ]
    skill_read = next(sql for sql in connection.statements if "FROM namespace n" in sql)
    assert "FOR UPDATE OF n, s" in skill_read


@pytest.mark.anyio
async def test_confirm_publish_rollback_never_runs_publication_outcomes() -> None:
    connection = FakeConfirmPublishConnection(fail_audit=True)
    engine = FakeEngine(connection)
    outcome_calls: list[object] = []

    async def publication_outcome_writer(*args: object) -> None:
        outcome_calls.append(args)

    with pytest.raises(RuntimeError, match="audit write failed"):
        await confirm_publish_skill_version(
            engine,
            confirm_input(),
            publication_outcome_writer=publication_outcome_writer,
        )

    assert engine.transaction_events == ["rollback"]
    assert outcome_calls == []


@pytest.mark.anyio
async def test_confirm_publish_replay_reconciles_outcomes_without_repeating_mutation_or_audit() -> None:
    original_published_at = datetime(2026, 6, 8, 9, 15, tzinfo=UTC)
    connection = FakeConfirmPublishConnection(
        version_status="PUBLISHED",
        latest_version_id=42,
        published_at=original_published_at,
    )
    engine = FakeEngine(connection)
    outcome_calls: list[object] = []

    async def publication_outcome_writer(*args: object) -> None:
        outcome_calls.append(args)

    response = await confirm_publish_skill_version(
        engine,
        confirm_input(),
        publication_outcome_writer=publication_outcome_writer,
    )

    assert response == {"skillId": 101, "versionId": 42, "action": "CONFIRM_PUBLISH", "status": "PUBLISHED"}
    assert engine.transaction_events == ["commit"]
    assert len(outcome_calls) == 1
    assert outcome_calls[0][1].created_at == original_published_at
    assert connection.audit_read_commit_count == 0
    assert not any("UPDATE skill_version" in statement for statement in connection.statements)
    assert not any("UPDATE skill\n" in statement for statement in connection.statements)
    assert not any("INSERT INTO audit_log" in statement for statement in connection.statements)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("request_actor", "original_actor"),
    [("manager", "owner"), ("owner", "manager")],
)
async def test_confirm_publish_cross_actor_replay_uses_original_audit_actor_for_outcomes(
    request_actor: str,
    original_actor: str,
) -> None:
    connection = FakeConfirmPublishConnection(
        version_status="PUBLISHED",
        latest_version_id=42,
        namespace_role="ADMIN" if request_actor == "manager" else None,
        confirm_audit_actor=original_actor,
        published_at=datetime(2026, 6, 8, 9, 15, tzinfo=UTC),
    )
    outcome_calls: list[object] = []

    async def publication_outcome_writer(*args: object) -> None:
        outcome_calls.append(args)

    await confirm_publish_skill_version(
        FakeEngine(connection),
        confirm_input(user_id=request_actor),
        publication_outcome_writer=publication_outcome_writer,
    )

    assert len(outcome_calls) == 1
    outcome = outcome_calls[0][1]
    assert outcome.publisher_id == original_actor
    audit_read = next(sql for sql in connection.statements if "FROM audit_log" in sql)
    assert "ORDER BY created_at ASC" in audit_read
    assert "id ASC" in audit_read


@pytest.mark.anyio
async def test_confirm_publish_allows_namespace_manager_for_private_draft_version() -> None:
    connection = FakeConfirmPublishConnection(version_status="DRAFT", owner_id="owner", namespace_role="ADMIN")

    response = await confirm_publish_skill_version(
        FakeEngine(connection),
        confirm_input(user_id="manager"),
        publication_outcome_writer=ignore_publication_outcomes,
    )

    assert response["status"] == "PUBLISHED"
    version_update = next(index for index, sql in enumerate(connection.statements) if "UPDATE skill_version" in sql)
    assert connection.params[version_update]["status"] == "PUBLISHED"


@pytest.mark.anyio
async def test_confirm_publish_rejects_non_private_skill() -> None:
    connection = FakeConfirmPublishConnection(skill_visibility="PUBLIC")

    with pytest.raises(SkillLifecycleError, match="error.skill.confirm.notPrivate"):
        await confirm_publish_skill_version(FakeEngine(connection), confirm_input())

    assert not any("UPDATE skill_version" in statement for statement in connection.statements)


@pytest.mark.anyio
async def test_confirm_publish_rejects_non_uploaded_or_draft_version() -> None:
    connection = FakeConfirmPublishConnection(version_status="PENDING_REVIEW")

    with pytest.raises(SkillLifecycleError, match="error.skill.version.confirm.notUploaded"):
        await confirm_publish_skill_version(FakeEngine(connection), confirm_input())

    assert not any("UPDATE skill_version" in statement for statement in connection.statements)


@pytest.mark.anyio
async def test_confirm_publish_rejects_non_manager_before_mutation() -> None:
    connection = FakeConfirmPublishConnection(owner_id="owner", namespace_role="MEMBER")

    with pytest.raises(SkillLifecycleError, match="error.skill.lifecycle.noPermission"):
        await confirm_publish_skill_version(FakeEngine(connection), confirm_input(user_id="viewer"))

    assert not any("UPDATE skill_version" in statement for statement in connection.statements)


def test_confirm_publish_routes_return_java_envelopes() -> None:
    app = create_app()
    seen: list[SkillConfirmPublishInput] = []

    async def confirmer(lifecycle_input: SkillConfirmPublishInput) -> dict[str, object]:
        seen.append(lifecycle_input)
        return {"skillId": 101, "versionId": 42, "action": "CONFIRM_PUBLISH", "status": "PUBLISHED"}

    app.state.skill_confirm_publish_writer = confirmer
    client = TestClient(app)

    response = client.post(
        "/api/web/skills/team-a/agent-helper/confirm-publish",
        json={"version": "1.1.0"},
        headers={"X-Mock-User-Id": "owner", "X-Request-Id": "confirm-publish-test"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["msg"] == "\u66f4\u65b0\u6210\u529f"
    assert body["requestId"] == "confirm-publish-test"
    assert body["data"]["action"] == "CONFIRM_PUBLISH"
    assert body["data"]["status"] == "PUBLISHED"
    assert seen[0].namespace == "team-a"
    assert seen[0].version == "1.1.0"
    assert seen[0].user_id == "owner"


def test_confirm_publish_routes_require_mock_user() -> None:
    app = create_app()
    client = TestClient(app)

    assert client.post(
        "/api/v1/skills/team-a/agent-helper/confirm-publish",
        json={"version": "1.1.0"},
    ).status_code == 401


def test_confirm_publish_route_wires_runtime_notification_fanout(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    fanout = object()
    engine = object()
    seen: list[tuple[object, SkillConfirmPublishInput, object]] = []

    async def confirmer(
        passed_engine: object,
        lifecycle_input: SkillConfirmPublishInput,
        *,
        notification_fanout: object,
    ) -> dict[str, object]:
        seen.append((passed_engine, lifecycle_input, notification_fanout))
        return {"skillId": 101, "versionId": 42, "action": "CONFIRM_PUBLISH", "status": "PUBLISHED"}

    monkeypatch.setattr(lifecycle_api, "confirm_publish_skill_version", confirmer)
    app.state.db_engine = engine
    app.state.notification_fanout = fanout
    client = TestClient(app)

    response = client.post(
        "/api/v1/skills/team-a/agent-helper/confirm-publish",
        json={"version": "1.1.0"},
        headers={"X-Mock-User-Id": "owner"},
    )

    assert response.status_code == 200
    assert len(seen) == 1
    assert seen[0][0] is engine
    assert seen[0][2] is fanout

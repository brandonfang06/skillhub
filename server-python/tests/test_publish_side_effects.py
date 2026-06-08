from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.publish.side_effects import (
    PublishSideEffectInput,
    apply_publish_side_effects,
    build_compat_publish_audit_detail,
    build_scan_task_payload,
    plan_publish_side_effects,
)


class FakeResult:
    def __init__(self, scalar: int | None = None) -> None:
        self.scalar = scalar

    def scalar_one(self) -> int:
        if self.scalar is None:
            raise AssertionError("No scalar configured")
        return self.scalar


class FakeConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.params: list[dict[str, object]] = []

    async def execute(self, statement: object, params: dict[str, object] | None = None) -> FakeResult:
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(params or {})
        if "INSERT INTO review_task" in sql:
            return FakeResult(701)
        if "INSERT INTO security_audit" in sql:
            return FakeResult(801)
        return FakeResult()


def side_effect_input(
    *,
    version_status: str = "PENDING_REVIEW",
    visibility: str = "PUBLIC",
    scanner_enabled: bool = False,
    scan_mode: str = "upload",
    compat_namespace: str | None = None,
    compat_slug: str | None = None,
) -> PublishSideEffectInput:
    return PublishSideEffectInput(
        skill_id=101,
        version_id=202,
        namespace_id=303,
        publisher_id="local-user",
        version_status=version_status,
        visibility=visibility,
        scanner_enabled=scanner_enabled,
        scan_mode=scan_mode,
        bundle_key="packages/101/202/bundle.zip",
        skill_path="/tmp/skillhub-scans/202",
        request_id="req-123",
        client_ip="127.0.0.1",
        user_agent="pytest",
        compat_namespace=compat_namespace,
        compat_slug=compat_slug,
        now=datetime(2026, 6, 8, 14, 15, 16, tzinfo=UTC),
        task_id="scan-task-1",
    )


def test_plan_pending_review_creates_review_and_review_event() -> None:
    plan = plan_publish_side_effects(side_effect_input())

    assert plan.create_review_task is True
    assert plan.emit_review_submitted is True
    assert plan.emit_skill_published is False
    assert plan.create_security_audit is False
    assert plan.mark_version_scanning is False


def test_plan_published_creates_published_event_without_review() -> None:
    plan = plan_publish_side_effects(side_effect_input(version_status="PUBLISHED", scanner_enabled=True))

    assert plan.create_review_task is False
    assert plan.emit_review_submitted is False
    assert plan.emit_skill_published is True
    assert plan.create_security_audit is True
    assert plan.mark_version_scanning is False


def test_plan_uploaded_private_creates_no_review_or_publish_event() -> None:
    plan = plan_publish_side_effects(side_effect_input(version_status="UPLOADED", visibility="PRIVATE"))

    assert plan.create_review_task is False
    assert plan.emit_review_submitted is False
    assert plan.emit_skill_published is False


def test_scanner_payload_upload_mode_uses_bundle_key() -> None:
    payload = build_scan_task_payload(side_effect_input(scanner_enabled=True, scan_mode="upload"))

    assert payload.task_id == "scan-task-1"
    assert payload.version_id == 202
    assert payload.skill_path is None
    assert payload.bundle_key == "packages/101/202/bundle.zip"
    assert payload.publisher_id == "local-user"
    assert payload.created_at_millis == 1780928116000
    assert payload.metadata == {"scannerType": "skill-scanner"}


def test_scanner_payload_local_mode_uses_skill_path() -> None:
    payload = build_scan_task_payload(side_effect_input(scanner_enabled=True, scan_mode="local"))

    assert payload.skill_path == "/tmp/skillhub-scans/202"
    assert payload.bundle_key is None


def test_compat_audit_detail_matches_java_fields() -> None:
    assert build_compat_publish_audit_detail(namespace="global", slug="agent-helper") == (
        '{"namespace":"global","slug":"agent-helper"}'
    )
    assert build_compat_publish_audit_detail(namespace="team", slug=None) == '{"namespace":"team"}'


@pytest.mark.anyio
async def test_apply_side_effects_inserts_review_task_and_event_intent() -> None:
    connection = FakeConnection()

    result = await apply_publish_side_effects(connection, side_effect_input())

    assert result.review_task_id == 701
    assert result.scan_task is None
    assert [event.type for event in result.events] == ["ReviewSubmittedEvent"]
    assert result.events[0].payload == {
        "reviewId": 701,
        "skillId": 101,
        "versionId": 202,
        "submitterId": "local-user",
        "namespaceId": 303,
    }
    assert any("INSERT INTO review_task" in statement for statement in connection.statements)
    assert connection.params[0]["status"] == "PENDING"


@pytest.mark.anyio
async def test_apply_side_effects_scanner_enabled_adds_audit_task_and_scanning_status() -> None:
    connection = FakeConnection()

    result = await apply_publish_side_effects(connection, side_effect_input(scanner_enabled=True))

    assert result.security_audit_id == 801
    assert result.scan_task is not None
    assert result.scan_task.bundle_key == "packages/101/202/bundle.zip"
    assert any("INSERT INTO security_audit" in statement for statement in connection.statements)
    assert any("UPDATE skill_version" in statement and "SCANNING" in statement for statement in connection.statements)
    audit_params = next(params for statement, params in zip(connection.statements, connection.params) if "INSERT INTO security_audit" in statement)
    assert audit_params["verdict"] == "SUSPICIOUS"
    assert audit_params["is_safe"] is False
    assert audit_params["findings_count"] == 0
    assert audit_params["findings"] == []


@pytest.mark.anyio
async def test_apply_side_effects_scanner_keeps_published_status_and_emits_publish_event() -> None:
    connection = FakeConnection()

    result = await apply_publish_side_effects(
        connection,
        side_effect_input(version_status="PUBLISHED", scanner_enabled=True),
    )

    assert result.review_task_id is None
    assert [event.type for event in result.events] == ["SkillPublishedEvent"]
    assert result.events[0].payload == {
        "skillId": 101,
        "versionId": 202,
        "publisherId": "local-user",
    }
    assert not any("UPDATE skill_version" in statement and "SCANNING" in statement for statement in connection.statements)


@pytest.mark.anyio
async def test_apply_side_effects_records_compat_publish_audit_when_requested() -> None:
    connection = FakeConnection()

    await apply_publish_side_effects(
        connection,
        side_effect_input(compat_namespace="global", compat_slug="agent-helper"),
    )

    audit_statement_index = next(
        index for index, statement in enumerate(connection.statements) if "INSERT INTO audit_log" in statement
    )
    audit_params = connection.params[audit_statement_index]
    assert audit_params["actor_user_id"] == "local-user"
    assert audit_params["action"] == "COMPAT_PUBLISH"
    assert audit_params["target_type"] == "SKILL_VERSION"
    assert audit_params["target_id"] == 202
    assert audit_params["request_id"] == "req-123"
    assert audit_params["client_ip"] == "127.0.0.1"
    assert audit_params["user_agent"] == "pytest"
    assert audit_params["detail_json"] == {"namespace": "global", "slug": "agent-helper"}

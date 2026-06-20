from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.promotion.workflow import (
    PromotionApproveInput,
    PromotionRejectInput,
    PromotionSubmitInput,
    approve_promotion,
    reject_promotion,
    submit_promotion,
)
from tests.support.fake_db import FakeEngine, FakeResult


class FakePromotionWriteConnection:
    def __init__(
        self,
        *,
        platform_roles: list[str] | None = None,
        namespace_role: str | None = None,
        duplicate_pending: int = 0,
        duplicate_approved: int = 0,
        version_status: str = "PUBLISHED",
        promotion_status: str = "PENDING",
        submitted_by: str = "submitter",
        duplicate_target: bool = False,
    ) -> None:
        self.platform_roles = platform_roles or []
        self.namespace_role = namespace_role
        self.duplicate_pending = duplicate_pending
        self.duplicate_approved = duplicate_approved
        self.version_status = version_status
        self.promotion_status = promotion_status
        self.submitted_by = submitted_by
        self.duplicate_target = duplicate_target
        self.statements: list[str] = []
        self.params: list[dict[str, Any] | None] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(params)

        if "FROM user_role_binding" in sql:
            return FakeResult(rows=[{"code": role} for role in self.platform_roles])
        if "FROM user_account" in sql:
            return FakeResult(row={"display_name": "Reviewer"})
        if "FROM namespace_member" in sql:
            if self.namespace_role is None:
                return FakeResult(row=None)
            return FakeResult(row={"role": self.namespace_role})
        if "FROM skill source_skill" in sql and "source_skill.slug AS source_skill_slug" in sql:
            return FakeResult(
                row={
                    "source_skill_id": 101,
                    "source_namespace_id": 20,
                    "source_skill_slug": "agent-helper",
                    "source_owner_id": "submitter",
                    "source_display_name": "Agent Helper",
                    "source_summary": "Helps agents",
                    "source_version_id": 501,
                    "source_version_name": "1.0.0",
                    "source_version_created_by": "submitter",
                    "source_changelog": "Initial",
                    "source_parsed_metadata_json": {"name": "Agent Helper"},
                    "source_manifest_json": [{"path": "SKILL.md"}],
                    "source_file_count": 2,
                    "source_total_size": 120,
                    "source_bundle_ready": True,
                    "source_download_ready": True,
                    "target_namespace_id": 1,
                }
            )
        if "FROM skill source_skill" in sql:
            return FakeResult(
                row={
                    "source_skill_id": 101,
                    "source_namespace_id": 20,
                    "owner_id": "owner",
                    "source_namespace_status": "ACTIVE",
                    "source_version_id": 501,
                    "version_skill_id": 101,
                    "version_status": self.version_status,
                    "version_name": "1.0.0",
                    "target_namespace_id": 1,
                    "target_namespace_type": "GLOBAL",
                }
            )
        if "pending_count" in sql:
            return FakeResult(row={"pending_count": self.duplicate_pending, "approved_count": self.duplicate_approved})
        if "INSERT INTO promotion_request" in sql:
            return FakeResult(row={"id": 301, "submitted_at": datetime(2026, 6, 9, 12, 0, tzinfo=UTC)})
        if "FROM promotion_request pr" in sql:
            return FakeResult(
                row={
                    "id": 301,
                    "source_skill_id": 101,
                    "source_version_id": 501,
                    "target_namespace_id": 1,
                    "source_namespace": "team-a",
                    "skill_slug": "agent-helper",
                    "version_name": "1.0.0",
                    "target_namespace": "global",
                    "target_skill_id": None,
                    "status": self.promotion_status,
                    "version": 1,
                    "submitted_by": self.submitted_by,
                    "submitted_by_name": "Submitter",
                    "reviewed_by": None,
                    "reviewed_by_name": None,
                    "review_comment": None,
                    "submitted_at": datetime(2026, 6, 9, 11, 0, tzinfo=UTC),
                    "reviewed_at": None,
                }
            )
        if "FROM skill existing_target" in sql:
            if self.duplicate_target:
                return FakeResult(row={"id": 999})
            return FakeResult(row=None)
        if "INSERT INTO skill (" in sql:
            return FakeResult(scalar=901)
        if "INSERT INTO skill_version" in sql:
            return FakeResult(scalar=902)
        if "UPDATE skill" in sql:
            return FakeResult(scalar=1)
        if "FROM skill_file" in sql:
            return FakeResult(
                rows=[
                    {
                        "file_path": "SKILL.md",
                        "file_size": 80,
                        "content_type": "text/markdown",
                        "sha256": "abc",
                        "storage_key": "skills/101/501/SKILL.md",
                    },
                    {
                        "file_path": "src/main.py",
                        "file_size": 40,
                        "content_type": "text/x-python",
                        "sha256": "def",
                        "storage_key": "skills/101/501/src/main.py",
                    },
                ]
            )
        if "INSERT INTO skill_file" in sql:
            return FakeResult()
        if "UPDATE promotion_request" in sql:
            return FakeResult(scalar=1)
        if "INSERT INTO audit_log" in sql:
            return FakeResult()
        if "INSERT INTO user_notification" in sql:
            return FakeResult()

        raise AssertionError(f"unexpected SQL: {sql}")


def submit_input(**overrides: Any) -> PromotionSubmitInput:
    data = {
        "source_skill_id": 101,
        "source_version_id": 501,
        "target_namespace_id": 1,
        "user_id": "owner",
        "request_id": "req-submit",
        "client_ip": "127.0.0.1",
        "user_agent": "pytest",
        "now": datetime(2026, 6, 9, 12, 0, tzinfo=UTC),
    }
    data.update(overrides)
    return PromotionSubmitInput(**data)


def approve_input(**overrides: Any) -> PromotionApproveInput:
    data = {
        "promotion_id": 301,
        "reviewer_id": "admin",
        "comment": "ship it",
        "request_id": "req-approve",
        "client_ip": "127.0.0.1",
        "user_agent": "pytest",
        "now": datetime(2026, 6, 9, 14, 0, tzinfo=UTC),
    }
    data.update(overrides)
    return PromotionApproveInput(**data)


@pytest.mark.anyio
async def test_submit_promotion_creates_request_and_audits() -> None:
    connection = FakePromotionWriteConnection()

    response = await submit_promotion(FakeEngine(connection), submit_input())

    assert response["id"] == 301
    assert response["sourceSkillId"] == 101
    assert response["sourceSkillSlug"] == "agent-helper"
    assert response["sourceVersion"] == "1.0.0"
    assert response["status"] == "PENDING"
    insert_request = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO promotion_request" in sql)
    audit_insert = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO audit_log" in sql)
    assert insert_request < audit_insert
    assert connection.params[insert_request]["submitted_by"] == "owner"
    assert connection.params[audit_insert]["action"] == "PROMOTION_SUBMIT"
    assert connection.params[audit_insert]["target_type"] == "PROMOTION_REQUEST"
    assert connection.params[audit_insert]["target_id"] == 301
    assert json.loads(connection.params[audit_insert]["detail_json"]) == {"sourceSkillId": 101, "sourceVersionId": 501}


@pytest.mark.anyio
async def test_submit_promotion_rejects_duplicate_pending_before_insert() -> None:
    connection = FakePromotionWriteConnection(duplicate_pending=1)

    with pytest.raises(ValueError, match="promotion.duplicate_pending"):
        await submit_promotion(FakeEngine(connection), submit_input())

    assert not any("INSERT INTO promotion_request" in sql for sql in connection.statements)


@pytest.mark.anyio
async def test_submit_promotion_requires_published_source_version() -> None:
    connection = FakePromotionWriteConnection(version_status="UPLOADED")

    with pytest.raises(ValueError, match="promotion.version_not_published"):
        await submit_promotion(FakeEngine(connection), submit_input())


@pytest.mark.anyio
async def test_submit_promotion_allows_namespace_admin_when_not_owner() -> None:
    connection = FakePromotionWriteConnection(namespace_role="ADMIN")

    response = await submit_promotion(FakeEngine(connection), submit_input(user_id="team-admin"))

    assert response["submittedBy"] == "team-admin"


@pytest.mark.anyio
async def test_reject_promotion_updates_request_audits_and_notifies_submitter() -> None:
    connection = FakePromotionWriteConnection(platform_roles=["SKILL_ADMIN"], submitted_by="submitter")

    response = await reject_promotion(
        FakeEngine(connection),
        PromotionRejectInput(
            promotion_id=301,
            reviewer_id="admin",
            comment="not ready",
            request_id="req-reject",
            client_ip="127.0.0.1",
            user_agent="pytest",
            now=datetime(2026, 6, 9, 13, 0, tzinfo=UTC),
        ),
    )

    assert response["status"] == "REJECTED"
    assert response["reviewedBy"] == "admin"
    assert response["reviewedByName"] == "Reviewer"
    update_request = next(index for index, sql in enumerate(connection.statements) if "UPDATE promotion_request" in sql)
    audit_insert = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO audit_log" in sql)
    notification_insert = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO user_notification" in sql)
    assert update_request < audit_insert < notification_insert
    assert connection.params[update_request]["status"] == "REJECTED"
    assert connection.params[audit_insert]["action"] == "PROMOTION_REJECT"
    assert json.loads(connection.params[audit_insert]["detail_json"]) == {"comment": "not ready"}
    assert connection.params[notification_insert]["user_id"] == "submitter"
    assert connection.params[notification_insert]["category"] == "PROMOTION"


@pytest.mark.anyio
async def test_reject_promotion_allows_super_admin_self_review_and_audits_marker() -> None:
    connection = FakePromotionWriteConnection(platform_roles=["SUPER_ADMIN"], submitted_by="admin")

    response = await reject_promotion(
        FakeEngine(connection),
        PromotionRejectInput(promotion_id=301, reviewer_id="admin", comment=None),
    )

    assert response["status"] == "REJECTED"
    audit_insert = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO audit_log" in sql)
    assert json.loads(connection.params[audit_insert]["detail_json"]) == {"selfReview": True}


@pytest.mark.anyio
async def test_reject_promotion_forbids_skill_admin_submitter_self_review() -> None:
    connection = FakePromotionWriteConnection(platform_roles=["SKILL_ADMIN"], submitted_by="admin")

    with pytest.raises(ValueError, match="promotion.no_permission"):
        await reject_promotion(
            FakeEngine(connection),
            PromotionRejectInput(promotion_id=301, reviewer_id="admin", comment=None),
        )

    assert not any("UPDATE promotion_request" in sql for sql in connection.statements)


@pytest.mark.anyio
async def test_approve_promotion_materializes_target_skill_version_files_audits_and_notifies() -> None:
    connection = FakePromotionWriteConnection(platform_roles=["SUPER_ADMIN"], submitted_by="submitter")

    response = await approve_promotion(FakeEngine(connection), approve_input())

    assert response["status"] == "APPROVED"
    assert response["targetSkillId"] == 901
    assert response["reviewedBy"] == "admin"
    assert response["reviewedByName"] == "Reviewer"

    update_approval = next(index for index, sql in enumerate(connection.statements) if "UPDATE promotion_request" in sql)
    target_skill_insert = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO skill (" in sql)
    target_version_insert = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO skill_version" in sql)
    first_file_insert = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO skill_file" in sql)
    target_id_update = max(index for index, sql in enumerate(connection.statements) if "UPDATE promotion_request" in sql)
    audit_insert = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO audit_log" in sql)
    notification_insert = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO user_notification" in sql)

    assert update_approval < target_skill_insert < target_version_insert < first_file_insert < target_id_update < audit_insert < notification_insert
    assert connection.params[update_approval]["status"] == "APPROVED"
    assert connection.params[target_skill_insert]["namespace_id"] == 1
    assert connection.params[target_skill_insert]["slug"] == "agent-helper"
    assert connection.params[target_skill_insert]["visibility"] == "PUBLIC"
    assert connection.params[target_skill_insert]["source_skill_id"] == 101
    assert connection.params[target_version_insert]["skill_id"] == 901
    assert connection.params[target_version_insert]["status"] == "PUBLISHED"
    assert connection.params[target_version_insert]["requested_visibility"] == "PUBLIC"
    assert connection.params[first_file_insert]["version_id"] == 902
    assert connection.params[first_file_insert]["storage_key"] == "skills/101/501/SKILL.md"
    assert connection.params[target_id_update]["target_skill_id"] == 901
    assert connection.params[audit_insert]["action"] == "PROMOTION_APPROVE"
    assert json.loads(connection.params[audit_insert]["detail_json"]) == {"comment": "ship it"}
    assert connection.params[notification_insert]["user_id"] == "submitter"
    assert connection.params[notification_insert]["title"] == "Promotion approved"


@pytest.mark.anyio
async def test_approve_promotion_forbids_duplicate_target_skill_before_materialization() -> None:
    connection = FakePromotionWriteConnection(platform_roles=["SKILL_ADMIN"], duplicate_target=True)

    with pytest.raises(ValueError, match="promotion.target_skill_conflict"):
        await approve_promotion(FakeEngine(connection), approve_input())

    assert not any("INSERT INTO skill (" in sql for sql in connection.statements)


@pytest.mark.anyio
async def test_approve_promotion_allows_super_admin_self_review_and_audits_marker() -> None:
    connection = FakePromotionWriteConnection(platform_roles=["SUPER_ADMIN"], submitted_by="admin")

    response = await approve_promotion(FakeEngine(connection), approve_input())

    assert response["status"] == "APPROVED"
    audit_insert = next(index for index, sql in enumerate(connection.statements) if "INSERT INTO audit_log" in sql)
    assert json.loads(connection.params[audit_insert]["detail_json"]) == {
        "comment": "ship it",
        "selfReview": True,
    }


@pytest.mark.anyio
async def test_approve_promotion_forbids_skill_admin_submitter_self_review() -> None:
    connection = FakePromotionWriteConnection(platform_roles=["SKILL_ADMIN"], submitted_by="admin")

    with pytest.raises(ValueError, match="promotion.no_permission"):
        await approve_promotion(FakeEngine(connection), approve_input())

    assert not any("INSERT INTO skill (" in sql for sql in connection.statements)


def test_promotion_submit_and_reject_routes_return_java_envelopes() -> None:
    app = create_app()
    seen: list[object] = []

    async def submitter(promotion_input: PromotionSubmitInput) -> dict[str, object]:
        seen.append(promotion_input)
        return {"id": 301, "sourceSkillId": promotion_input.source_skill_id, "status": "PENDING"}

    async def rejecter(promotion_input: PromotionRejectInput) -> dict[str, object]:
        seen.append(promotion_input)
        return {"id": promotion_input.promotion_id, "sourceSkillId": 101, "status": "REJECTED", "reviewComment": promotion_input.comment}

    async def approver(promotion_input: PromotionApproveInput) -> dict[str, object]:
        seen.append(promotion_input)
        return {"id": promotion_input.promotion_id, "sourceSkillId": 101, "targetSkillId": 901, "status": "APPROVED", "reviewComment": promotion_input.comment}

    app.state.promotion_submit_writer = submitter
    app.state.promotion_reject_writer = rejecter
    app.state.promotion_approve_writer = approver
    client = TestClient(app)

    submitted = client.post(
        "/api/web/promotions",
        json={"sourceSkillId": 101, "sourceVersionId": 501, "targetNamespaceId": 1},
        headers={"X-Mock-User-Id": "owner", "X-Request-Id": "promotion-submit-test"},
    )
    rejected = client.post(
        "/api/v1/promotions/301/reject",
        json={"comment": "not ready"},
        headers={"X-Mock-User-Id": "admin", "X-Request-Id": "promotion-reject-test"},
    )
    approved = client.post(
        "/api/web/promotions/301/approve",
        json={"comment": "ship it"},
        headers={"X-Mock-User-Id": "admin", "X-Request-Id": "promotion-approve-test"},
    )

    assert submitted.status_code == 200
    assert submitted.json()["msg"] == "\u521b\u5efa\u6210\u529f"
    assert submitted.json()["requestId"] == "promotion-submit-test"
    assert rejected.status_code == 200
    assert rejected.json()["msg"] == "\u66f4\u65b0\u6210\u529f"
    assert rejected.json()["requestId"] == "promotion-reject-test"
    assert rejected.json()["data"]["status"] == "REJECTED"
    assert approved.status_code == 200
    assert approved.json()["msg"] == "\u66f4\u65b0\u6210\u529f"
    assert approved.json()["requestId"] == "promotion-approve-test"
    assert approved.json()["data"]["targetSkillId"] == 901
    assert len(seen) == 3


def test_promotion_write_routes_require_mock_user() -> None:
    app = create_app()
    client = TestClient(app)

    assert client.post("/api/v1/promotions", json={}).status_code == 401
    assert client.post("/api/v1/promotions/301/reject", json={}).status_code == 401
    assert client.post("/api/v1/promotions/301/approve", json={}).status_code == 401

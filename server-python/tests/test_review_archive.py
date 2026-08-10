from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from app.publish.replacement import ArchivedReviewAttempt
from app.review.archive import ReviewAttemptArchiveInput, archive_review_attempt


class FakeConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> None:
        self.statements.append(str(statement))
        self.params.append(params or {})


def rejected_attempt() -> ArchivedReviewAttempt:
    return ArchivedReviewAttempt(
        original_review_task_id=91,
        original_skill_version_id=41,
        skill_id=7,
        namespace_id=10,
        namespace_slug="global",
        skill_slug="agent-helper",
        version="1.0.0",
        status="REJECTED",
        submitted_by="local-user",
        reviewed_by="reviewer-1",
        review_comment="Fix metadata",
        submitted_at=datetime(2026, 6, 7, 10, 0, tzinfo=UTC),
        reviewed_at=datetime(2026, 6, 7, 11, 0, tzinfo=UTC),
        parsed_metadata_json={"name": "Agent Helper", "version": "1.0.0"},
        manifest_json=[{"path": "SKILL.md", "size": 42}],
        files=[{"path": "SKILL.md", "size": 42, "contentType": "text/markdown", "sha256": "abc123"}],
        scanner_summary=[
            {
                "scannerType": "STATIC",
                "verdict": "PASS",
                "createdAt": datetime(2026, 6, 7, 10, 30, tzinfo=UTC),
            }
        ],
        original_request_id="reject-request",
    )


@pytest.mark.anyio
async def test_archive_review_attempt_links_rejected_and_replacement_records() -> None:
    connection = FakeConnection()

    await archive_review_attempt(
        connection,
        ReviewAttemptArchiveInput(
            attempt=rejected_attempt(),
            replacement_version_id=42,
            replacement_review_task_id=900,
            actor_user_id="local-user",
            request_id="resubmit-request",
            client_ip="127.0.0.1",
            user_agent="pytest",
            archived_at=datetime(2026, 6, 8, 18, 19, 20, tzinfo=UTC),
        ),
    )

    assert "INSERT INTO review_attempt_archive" in connection.statements[0]
    params = connection.params[0]
    assert params["original_review_task_id"] == 91
    assert params["original_skill_version_id"] == 41
    assert params["replacement_version_id"] == 42
    assert params["replacement_review_task_id"] == 900
    assert json.loads(params["files_json"]) == [
        {"path": "SKILL.md", "size": 42, "contentType": "text/markdown", "sha256": "abc123"}
    ]
    assert json.loads(params["scanner_summary_json"])[0]["createdAt"] == "2026-06-07T10:30:00Z"
    assert "INSERT INTO audit_log" in connection.statements[1]
    assert connection.params[1]["action"] == "REJECTED_VERSION_RESUBMIT"
    assert connection.params[1]["target_type"] == "SKILL_VERSION"
    assert connection.params[1]["target_id"] == 42


@pytest.mark.anyio
async def test_archive_review_attempt_supports_explicit_version_deletion() -> None:
    connection = FakeConnection()

    await archive_review_attempt(
        connection,
        ReviewAttemptArchiveInput(
            attempt=rejected_attempt(),
            replacement_version_id=None,
            replacement_review_task_id=None,
            actor_user_id="local-user",
            request_id="delete-request",
            client_ip="127.0.0.1",
            user_agent="pytest",
            archive_reason="REJECTED_VERSION_DELETE",
            audit_action="REJECTED_VERSION_DELETE",
        ),
    )

    assert connection.params[0]["replacement_version_id"] is None
    assert connection.params[0]["replacement_review_task_id"] is None
    assert connection.params[0]["archive_reason"] == "REJECTED_VERSION_DELETE"
    assert connection.params[1]["action"] == "REJECTED_VERSION_DELETE"
    assert connection.params[1]["target_id"] == 41

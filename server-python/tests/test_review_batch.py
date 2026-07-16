from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

import app.review.batch as batch_module
from app.main import create_app
from app.review.approval import ReviewApprovalError
from app.review.batch import (
    ReviewBatchDecisionError,
    ReviewBatchDecisionInput,
    decide_review_tasks_batch,
    validate_review_batch_input,
)


def batch_input(**overrides: object) -> ReviewBatchDecisionInput:
    data = {
        "review_task_ids": [11, 12, 13],
        "decision": "APPROVE",
        "reviewer_id": "team-admin",
        "comment": "ship these",
        "request_id": "req-batch",
        "client_ip": "127.0.0.1",
        "user_agent": "pytest",
    }
    data.update(overrides)
    return ReviewBatchDecisionInput(**data)


@pytest.mark.parametrize(
    ("batch_request", "error"),
    [
        (batch_input(review_task_ids=[]), "review.batch.ids.required"),
        (batch_input(review_task_ids=[1, 1]), "review.batch.ids.duplicate"),
        (batch_input(review_task_ids=list(range(1, 102))), "review.batch.ids.limit"),
        (batch_input(decision="INVALID"), "review.batch.decision.invalid"),
        (batch_input(decision="REJECT", comment="  "), "review.batch.reject.comment.required"),
    ],
)
def test_validate_review_batch_input_rejects_invalid_requests(
    batch_request: ReviewBatchDecisionInput,
    error: str,
) -> None:
    with pytest.raises(ReviewBatchDecisionError, match=error):
        validate_review_batch_input(batch_request)


@pytest.mark.anyio
async def test_decide_review_tasks_batch_preserves_order_and_partial_success(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[int, str, object]] = []
    fanout = object()

    async def approve(_engine: object, request: object, *, notification_fanout: object) -> dict[str, object]:
        task_id = int(getattr(request, "review_task_id"))
        seen.append((task_id, str(getattr(request, "reviewer_id")), notification_fanout))
        if task_id == 12:
            raise ReviewApprovalError("review.task.notPending", status_code=400)
        return {"id": task_id, "status": "APPROVED"}

    monkeypatch.setattr(batch_module, "approve_review_task", approve)

    result = await decide_review_tasks_batch(object(), batch_input(), notification_fanout=fanout)

    assert seen == [(11, "team-admin", fanout), (12, "team-admin", fanout), (13, "team-admin", fanout)]
    assert result == {
        "totalCount": 3,
        "successCount": 2,
        "failureCount": 1,
        "results": [
            {"reviewTaskId": 11, "success": True, "status": "APPROVED", "errorCode": None},
            {"reviewTaskId": 12, "success": False, "status": None, "errorCode": "review.task.notPending"},
            {"reviewTaskId": 13, "success": True, "status": "APPROVED", "errorCode": None},
        ],
    }


@pytest.mark.anyio
async def test_decide_review_tasks_batch_reuses_reject_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[object] = []

    async def reject(_engine: object, request: object, *, notification_fanout: object) -> dict[str, object]:
        seen.append(request)
        return {"id": getattr(request, "review_task_id"), "status": "REJECTED"}

    monkeypatch.setattr(batch_module, "reject_review_task", reject)
    request = replace(batch_input(), review_task_ids=[21], decision="REJECT", comment="missing documentation")

    result = await decide_review_tasks_batch(object(), request)

    assert len(seen) == 1
    assert getattr(seen[0], "comment") == "missing documentation"
    assert result["results"] == [
        {"reviewTaskId": 21, "success": True, "status": "REJECTED", "errorCode": None}
    ]


def test_batch_review_route_passes_actor_metadata_and_returns_envelope() -> None:
    app = create_app()
    captured: list[ReviewBatchDecisionInput] = []

    async def writer(request: ReviewBatchDecisionInput) -> dict[str, object]:
        captured.append(request)
        return {
            "totalCount": 2,
            "successCount": 2,
            "failureCount": 0,
            "results": [],
        }

    app.state.review_batch_writer = writer
    app.state.db_engine = SimpleNamespace()
    client = TestClient(app)

    response = client.post(
        "/api/web/reviews/batch-decision",
        json={"reviewTaskIds": [31, 32], "decision": "APPROVE", "comment": "ship"},
        headers={
            "X-Mock-User-Id": "team-admin",
            "X-Request-Id": "req-route-batch",
            "User-Agent": "pytest-batch",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["successCount"] == 2
    assert len(captured) == 1
    assert captured[0].review_task_ids == [31, 32]
    assert captured[0].reviewer_id == "team-admin"
    assert captured[0].request_id == "req-route-batch"
    assert captured[0].user_agent == "pytest-batch"


def test_batch_review_route_rejects_duplicate_ids_before_writer() -> None:
    app = create_app()
    app.state.review_batch_writer = lambda _request: pytest.fail("writer must not run")
    client = TestClient(app)

    response = client.post(
        "/api/web/reviews/batch-decision",
        json={"reviewTaskIds": [31, 31], "decision": "APPROVE"},
        headers={"X-Mock-User-Id": "team-admin"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "review.batch.ids.duplicate"

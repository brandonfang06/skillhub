from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.notifications.publisher import NotificationFanout
from app.review.approval import (
    ReviewApprovalError,
    ReviewApproveInput,
    ReviewRejectInput,
    approve_review_task,
    reject_review_task,
)

MAX_BATCH_REVIEW_TASKS = 100


@dataclass(frozen=True)
class ReviewBatchDecisionInput:
    review_task_ids: list[int]
    decision: str
    reviewer_id: str
    comment: str | None = None
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None


class ReviewBatchDecisionError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def validate_review_batch_input(request: ReviewBatchDecisionInput) -> None:
    if not request.review_task_ids:
        raise ReviewBatchDecisionError("review.batch.ids.required")
    if len(request.review_task_ids) > MAX_BATCH_REVIEW_TASKS:
        raise ReviewBatchDecisionError("review.batch.ids.limit")
    if len(set(request.review_task_ids)) != len(request.review_task_ids):
        raise ReviewBatchDecisionError("review.batch.ids.duplicate")
    if request.decision not in {"APPROVE", "REJECT"}:
        raise ReviewBatchDecisionError("review.batch.decision.invalid")
    if request.decision == "REJECT" and (request.comment is None or request.comment.strip() == ""):
        raise ReviewBatchDecisionError("review.batch.reject.comment.required")


def _task_input(request: ReviewBatchDecisionInput, review_task_id: int) -> ReviewApproveInput | ReviewRejectInput:
    common = {
        "review_task_id": review_task_id,
        "reviewer_id": request.reviewer_id,
        "comment": request.comment,
        "request_id": request.request_id,
        "client_ip": request.client_ip,
        "user_agent": request.user_agent,
    }
    if request.decision == "APPROVE":
        return ReviewApproveInput(
            **common,
            allow_scan_override=False,
        )
    return ReviewRejectInput(
        **common,
    )


async def decide_review_tasks_batch(
    engine: Any,
    request: ReviewBatchDecisionInput,
    *,
    notification_fanout: NotificationFanout | None = None,
) -> dict[str, Any]:
    validate_review_batch_input(request)
    results: list[dict[str, Any]] = []
    for review_task_id in request.review_task_ids:
        try:
            task_input = _task_input(request, review_task_id)
            if request.decision == "APPROVE":
                await approve_review_task(engine, task_input, notification_fanout=notification_fanout)
            else:
                await reject_review_task(engine, task_input, notification_fanout=notification_fanout)
            results.append(
                {
                    "reviewTaskId": review_task_id,
                    "success": True,
                    "status": "APPROVED" if request.decision == "APPROVE" else "REJECTED",
                    "errorCode": None,
                }
            )
        except ReviewApprovalError as exc:
            results.append(
                {
                    "reviewTaskId": review_task_id,
                    "success": False,
                    "status": None,
                    "errorCode": str(exc),
                }
            )

    success_count = sum(1 for result in results if result["success"])
    return {
        "totalCount": len(results),
        "successCount": success_count,
        "failureCount": len(results) - success_count,
        "results": results,
    }

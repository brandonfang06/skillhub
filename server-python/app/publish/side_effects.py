from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from app.audit.writer import write_audit_log
from app.publish.scan_contracts import ScanTaskPayload
from app.publish.scan_outbox import enqueue_scan_task
from app.publish.scanner_result import scanner_type_db_value


@dataclass(frozen=True)
class PublishSideEffectInput:
    skill_id: int
    version_id: int
    namespace_id: int
    publisher_id: str
    version_status: str
    visibility: str
    scanner_enabled: bool = False
    scan_mode: str = "local"
    bundle_key: str | None = None
    skill_path: str | None = None
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    compat_namespace: str | None = None
    compat_slug: str | None = None
    now: datetime | None = None
    task_id: str | None = None
    submitter_id: str | None = None
    actor_user_id: str | None = None
    actor_service_principal_id: str | None = None

    @property
    def resolved_submitter_id(self) -> str:
        return self.submitter_id or self.publisher_id

    @property
    def resolved_actor_user_id(self) -> str:
        return self.actor_user_id or self.publisher_id

    @property
    def audit_actor_user_id(self) -> str | None:
        if self.actor_service_principal_id is not None:
            return None
        return self.resolved_actor_user_id


@dataclass(frozen=True)
class PublishSideEffectPlan:
    create_review_task: bool
    emit_review_submitted: bool
    emit_skill_published: bool
    create_security_audit: bool
    publish_scan_task: bool
    mark_version_scanning: bool
    create_compat_audit: bool


@dataclass(frozen=True)
class PublishEventIntent:
    type: str
    payload: dict[str, object]


@dataclass(frozen=True)
class PublishSideEffectResult:
    review_task_id: int | None
    security_audit_id: int | None
    scan_task: ScanTaskPayload | None
    events: list[PublishEventIntent]


def plan_publish_side_effects(request: PublishSideEffectInput) -> PublishSideEffectPlan:
    create_review_task = (
        request.version_status == "PENDING_REVIEW" and request.visibility != "PRIVATE"
    )
    create_security_audit = request.scanner_enabled
    return PublishSideEffectPlan(
        create_review_task=create_review_task,
        emit_review_submitted=create_review_task,
        emit_skill_published=request.version_status == "PUBLISHED",
        create_security_audit=create_security_audit,
        publish_scan_task=create_security_audit,
        mark_version_scanning=create_security_audit
        and request.version_status != "PUBLISHED",
        create_compat_audit=request.compat_namespace is not None,
    )


def build_scan_task_payload(request: PublishSideEffectInput) -> ScanTaskPayload:
    now = normalized_now(request.now)
    scan_mode = request.scan_mode.lower()
    if scan_mode == "upload":
        skill_path = None
        bundle_key = (
            request.bundle_key
            or f"packages/{request.skill_id}/{request.version_id}/bundle.zip"
        )
    else:
        skill_path = request.skill_path or f"/tmp/skillhub-scans/{request.version_id}"
        bundle_key = None

    return ScanTaskPayload(
        task_id=request.task_id or str(uuid4()),
        version_id=request.version_id,
        skill_path=skill_path,
        bundle_key=bundle_key,
        publisher_id=request.publisher_id,
        created_at_millis=int(now.timestamp() * 1000),
        metadata={"scannerType": "skill-scanner"},
        request_id=request.request_id,
    )


def build_compat_publish_audit_detail(*, namespace: str, slug: str | None) -> str:
    detail: dict[str, str] = {"namespace": namespace}
    if slug is not None:
        detail["slug"] = slug
    return json.dumps(detail, separators=(",", ":"))


async def apply_publish_side_effects(
    connection: Any, request: PublishSideEffectInput
) -> PublishSideEffectResult:
    plan = plan_publish_side_effects(request)
    now = normalized_now(request.now)
    review_task_id: int | None = None
    security_audit_id: int | None = None
    scan_task: ScanTaskPayload | None = None
    events: list[PublishEventIntent] = []

    if plan.create_review_task:
        review_task_id = int(
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO review_task (
                            skill_version_id, namespace_id, status, version, submitted_by, submitted_at
                        )
                        VALUES (
                            :skill_version_id, :namespace_id, :status, 1, :submitted_by, :submitted_at
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "skill_version_id": request.version_id,
                        "namespace_id": request.namespace_id,
                        "status": "PENDING",
                        "submitted_by": request.resolved_submitter_id,
                        "submitted_at": now,
                    },
                )
            ).scalar_one()
        )
        if plan.emit_review_submitted:
            events.append(
                PublishEventIntent(
                    type="ReviewSubmittedEvent",
                    payload={
                        "reviewId": review_task_id,
                        "skillId": request.skill_id,
                        "versionId": request.version_id,
                        "submitterId": request.resolved_submitter_id,
                        "namespaceId": request.namespace_id,
                    },
                )
            )

    if plan.create_security_audit:
        scan_task = build_scan_task_payload(request)
        security_audit_id = int(
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO security_audit (
                            skill_version_id, scanner_type, verdict, is_safe, findings_count,
                            findings, task_id, created_at
                        )
                        VALUES (
                            :skill_version_id, :scanner_type, :verdict, :is_safe, :findings_count,
                            :findings, :task_id, :created_at
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "skill_version_id": request.version_id,
                        "scanner_type": scanner_type_db_value("skill-scanner"),
                        "verdict": "SUSPICIOUS",
                        "is_safe": False,
                        "findings_count": 0,
                        "findings": json.dumps([], separators=(",", ":")),
                        "task_id": scan_task.task_id,
                        "created_at": now,
                    },
                )
            ).scalar_one()
        )
        await enqueue_scan_task(
            connection,
            scan_task,
            next_attempt_at=now,
            request_id=request.request_id,
        )
        if plan.mark_version_scanning:
            await connection.execute(
                text(
                    """
                    UPDATE skill_version
                    SET status = 'SCANNING'
                    WHERE id = :version_id
                    """
                ),
                {"version_id": request.version_id},
            )

    if plan.emit_skill_published:
        events.append(
            PublishEventIntent(
                type="SkillPublishedEvent",
                payload={
                    "skillId": request.skill_id,
                    "versionId": request.version_id,
                    "publisherId": request.publisher_id,
                },
            )
        )

    if plan.create_compat_audit:
        await write_audit_log(
            connection,
            actor_user_id=request.audit_actor_user_id,
            actor_service_principal_id=request.actor_service_principal_id,
            action="COMPAT_PUBLISH",
            target_type="SKILL_VERSION",
            target_id=request.version_id,
            request_id=request.request_id,
            client_ip=request.client_ip,
            user_agent=request.user_agent,
            detail={},
            detail_json=build_compat_publish_audit_detail(
                namespace=request.compat_namespace or "",
                slug=request.compat_slug,
            ),
            created_at=now,
        )

    return PublishSideEffectResult(
        review_task_id=review_task_id,
        security_audit_id=security_audit_id,
        scan_task=scan_task,
        events=events,
    )


def normalized_now(value: datetime | None) -> datetime:
    now = value or datetime.now(tz=UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)

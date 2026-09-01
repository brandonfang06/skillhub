from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import text

from app.core.request_id import MESSAGE_REQUEST_ID_FIELD, is_valid_request_id
from app.publish.scan_contracts import ScanTaskPayload
from app.publish.scan_worker import mark_scan_task_failed

logger = logging.getLogger("uvicorn.error")


class ScanTaskPublisher(Protocol):
    async def publish_scan_task(self, task: ScanTaskPayload) -> None: ...


@dataclass(frozen=True)
class ScanOutboxDispatchResult:
    claimed: int = 0
    sent: int = 0
    retried: int = 0
    failed: int = 0


@dataclass(frozen=True)
class _ClaimedScanTask:
    outbox_id: int
    entity_version: int
    retry_count: int
    task: ScanTaskPayload


async def enqueue_scan_task(
    connection: Any,
    task: ScanTaskPayload,
    *,
    next_attempt_at: datetime,
    request_id: str | None = None,
) -> None:
    metadata = dict(task.metadata)
    resolved_request_id = request_id or task.request_id
    if is_valid_request_id(resolved_request_id):
        metadata[MESSAGE_REQUEST_ID_FIELD] = str(resolved_request_id)

    await connection.execute(
        text(
            """
            INSERT INTO scan_task_outbox (
                task_id, version_id, skill_path, bundle_key, publisher_id,
                metadata, status, retry_count, next_attempt_at,
                created_at, updated_at
            )
            VALUES (
                :task_id, :version_id, :skill_path, :bundle_key, :publisher_id,
                CAST(:metadata AS JSONB), 'PENDING', 0, :next_attempt_at,
                :next_attempt_at, :next_attempt_at
            )
            """
        ),
        {
            "task_id": task.task_id,
            "version_id": task.version_id,
            "skill_path": task.skill_path,
            "bundle_key": task.bundle_key,
            "publisher_id": task.publisher_id,
            "metadata": json.dumps(
                metadata,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "next_attempt_at": next_attempt_at,
        },
    )


class ScanOutboxDispatcher:
    def __init__(
        self,
        engine: Any,
        publisher: ScanTaskPublisher,
        *,
        batch_size: int = 50,
        lease_seconds: int = 120,
        max_attempts: int = 10,
        max_backoff_seconds: int = 300,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be at least 1")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if max_backoff_seconds < 1:
            raise ValueError("max_backoff_seconds must be at least 1")
        self.engine = engine
        self.publisher = publisher
        self.batch_size = batch_size
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        self.max_backoff_seconds = max_backoff_seconds

    async def dispatch_once(
        self,
        *,
        now: datetime | None = None,
    ) -> ScanOutboxDispatchResult:
        dispatch_time = _normalized_now(now)
        claims = await self._claim_due(dispatch_time)
        sent = 0
        retried = 0
        failed = 0
        for claim in claims:
            try:
                await self.publisher.publish_scan_task(claim.task)
            except Exception as error:  # noqa: BLE001
                outcome = await self._record_failure(
                    claim,
                    error,
                    _normalized_now(now),
                )
                if outcome == "failed":
                    failed += 1
                elif outcome == "retried":
                    retried += 1
                continue
            if await self._mark_sent(claim, _normalized_now(now)):
                sent += 1
        return ScanOutboxDispatchResult(
            claimed=len(claims),
            sent=sent,
            retried=retried,
            failed=failed,
        )

    async def cleanup_sent(
        self,
        *,
        retention_days: int,
        now: datetime | None = None,
    ) -> int:
        if retention_days <= 0:
            return 0
        sent_before = _normalized_now(now) - timedelta(days=retention_days)
        async with self.engine.begin() as connection:
            result = await connection.execute(
                text(
                    """
                    DELETE FROM scan_task_outbox
                    WHERE status = 'SENT'
                      AND updated_at < :sent_before
                    """
                ),
                {"sent_before": sent_before},
            )
        return max(int(result.rowcount or 0), 0)

    async def _claim_due(self, now: datetime) -> list[_ClaimedScanTask]:
        lease_until = now + timedelta(seconds=self.lease_seconds)
        async with self.engine.begin() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        WITH candidates AS (
                            SELECT id
                            FROM scan_task_outbox
                            WHERE (status = 'PENDING' AND next_attempt_at <= :now)
                               OR (status = 'SENDING' AND lease_until < :now)
                            ORDER BY created_at, id
                            FOR UPDATE SKIP LOCKED
                            LIMIT :batch_size
                        )
                        UPDATE scan_task_outbox AS outbox
                        SET status = 'SENDING',
                            lease_until = :lease_until,
                            updated_at = :now,
                            entity_version = outbox.entity_version + 1
                        FROM candidates
                        WHERE outbox.id = candidates.id
                        RETURNING outbox.id, outbox.task_id, outbox.version_id,
                                  outbox.skill_path, outbox.bundle_key,
                                  outbox.publisher_id, outbox.metadata,
                                  outbox.created_at, outbox.retry_count,
                                  outbox.entity_version
                        """
                    ),
                    {
                        "now": now,
                        "lease_until": lease_until,
                        "batch_size": self.batch_size,
                    },
                )
            ).mappings().all()
        return [_claimed_task(dict(row)) for row in rows]

    async def _mark_sent(
        self,
        claim: _ClaimedScanTask,
        now: datetime,
    ) -> bool:
        async with self.engine.begin() as connection:
            result = await connection.execute(
                text(
                    """
                    UPDATE scan_task_outbox
                    SET status = 'SENT',
                        lease_until = NULL,
                        last_error = NULL,
                        updated_at = :now,
                        entity_version = entity_version + 1
                    WHERE id = :outbox_id
                      AND status = 'SENDING'
                      AND entity_version = :entity_version
                    """
                ),
                {
                    "outbox_id": claim.outbox_id,
                    "entity_version": claim.entity_version,
                    "now": now,
                },
            )
        return int(result.rowcount or 0) == 1

    async def _record_failure(
        self,
        claim: _ClaimedScanTask,
        error: Exception,
        now: datetime,
    ) -> str | None:
        retry_count = claim.retry_count + 1
        last_error = str(error)[:2000]
        terminal = retry_count >= self.max_attempts
        async with self.engine.begin() as connection:
            if terminal:
                result = await connection.execute(
                    text(
                        """
                        UPDATE scan_task_outbox
                        SET status = 'FAILED',
                            retry_count = :retry_count,
                            lease_until = NULL,
                            last_error = :last_error,
                            updated_at = :now,
                            entity_version = entity_version + 1
                        WHERE id = :outbox_id
                          AND status = 'SENDING'
                          AND entity_version = :entity_version
                        """
                    ),
                    {
                        "outbox_id": claim.outbox_id,
                        "entity_version": claim.entity_version,
                        "retry_count": retry_count,
                        "last_error": last_error,
                        "now": now,
                    },
                )
                if int(result.rowcount or 0) != 1:
                    return None
                await mark_scan_task_failed(
                    connection,
                    version_id=claim.task.version_id,
                    scanner_type=str(
                        claim.task.metadata.get("scannerType") or "skill-scanner"
                    ),
                    failure_code="OUTBOX_DELIVERY_FAILED",
                )
                logger.error(
                    "scan.outbox.failed task_id=%s version_id=%s attempts=%s error=%s",
                    claim.task.task_id,
                    claim.task.version_id,
                    retry_count,
                    last_error,
                )
                return "failed"

            delay_seconds = min(
                self.max_backoff_seconds,
                1 << min(retry_count, 16),
            )
            result = await connection.execute(
                text(
                    """
                    UPDATE scan_task_outbox
                    SET status = 'PENDING',
                        retry_count = :retry_count,
                        next_attempt_at = :next_attempt_at,
                        lease_until = NULL,
                        last_error = :last_error,
                        updated_at = :now,
                        entity_version = entity_version + 1
                    WHERE id = :outbox_id
                      AND status = 'SENDING'
                      AND entity_version = :entity_version
                    """
                ),
                {
                    "outbox_id": claim.outbox_id,
                    "entity_version": claim.entity_version,
                    "retry_count": retry_count,
                    "next_attempt_at": now
                    + timedelta(seconds=max(delay_seconds, 1)),
                    "last_error": last_error,
                    "now": now,
                },
            )
        if int(result.rowcount or 0) != 1:
            return None
        logger.warning(
            "scan.outbox.retry task_id=%s version_id=%s retry_count=%s error=%s",
            claim.task.task_id,
            claim.task.version_id,
            retry_count,
            last_error,
        )
        return "retried"


def _claimed_task(row: dict[str, Any]) -> _ClaimedScanTask:
    metadata = _metadata(row.get("metadata"))
    request_id_value = metadata.pop(MESSAGE_REQUEST_ID_FIELD, None)
    created_at = row.get("created_at")
    if isinstance(created_at, datetime):
        created_at_millis = int(_normalized_now(created_at).timestamp() * 1000)
    else:
        created_at_millis = 0
    return _ClaimedScanTask(
        outbox_id=int(row["id"]),
        entity_version=int(row["entity_version"]),
        retry_count=int(row.get("retry_count") or 0),
        task=ScanTaskPayload(
            task_id=str(row["task_id"]),
            version_id=int(row["version_id"]),
            skill_path=_optional_text(row.get("skill_path")),
            bundle_key=_optional_text(row.get("bundle_key")),
            publisher_id=str(row.get("publisher_id") or ""),
            created_at_millis=created_at_millis,
            metadata=metadata,
            request_id=(
                str(request_id_value)
                if is_valid_request_id(str(request_id_value or ""))
                else None
            ),
        ),
    )


def _metadata(value: Any) -> dict[str, str]:
    if isinstance(value, str):
        decoded = json.loads(value)
    elif isinstance(value, dict):
        decoded = value
    else:
        decoded = {}
    if not isinstance(decoded, dict):
        return {}
    return {str(key): str(item) for key, item in decoded.items()}


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value)
    return text_value if text_value else None


def _normalized_now(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        return current.replace(tzinfo=UTC)
    return current.astimezone(UTC)

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScanTaskPayload:
    task_id: str
    version_id: int
    skill_path: str | None
    bundle_key: str | None
    publisher_id: str
    created_at_millis: int
    metadata: dict[str, str]
    request_id: str | None = None

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class ResolvedPeriod:
    start_time: datetime
    end_time: datetime


class NamespaceAnalyticsError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _parse_instant(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    text_value = value.strip()
    if text_value == "":
        return None
    try:
        parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise NamespaceAnalyticsError("error.namespaceAnalytics.invalidTimeRange") from exc
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def resolve_period(
    start_time: datetime | str | None,
    end_time: datetime | str | None,
    *,
    now: datetime | None = None,
) -> ResolvedPeriod:
    resolved_now = now or datetime.now(UTC)
    if resolved_now.tzinfo is None:
        resolved_now = resolved_now.replace(tzinfo=UTC)
    resolved_end = _parse_instant(end_time) or resolved_now
    resolved_start = _parse_instant(start_time) or (resolved_end - timedelta(days=30))
    if resolved_start > resolved_end:
        raise NamespaceAnalyticsError("error.namespaceAnalytics.invalidTimeRange")
    return ResolvedPeriod(start_time=resolved_start, end_time=resolved_end)

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.namespace_analytics.repository import NamespaceAnalyticsError, resolve_period


def test_resolve_period_defaults_to_previous_thirty_days() -> None:
    resolved = resolve_period(None, None, now=datetime(2026, 8, 4, tzinfo=UTC))

    assert resolved.start_time == datetime(2026, 7, 5, tzinfo=UTC)
    assert resolved.end_time == datetime(2026, 8, 4, tzinfo=UTC)


def test_resolve_period_uses_end_time_as_default_window_anchor() -> None:
    resolved = resolve_period(None, "2026-08-01T12:30:00Z", now=datetime(2026, 8, 4, tzinfo=UTC))

    assert resolved.start_time == datetime(2026, 7, 2, 12, 30, tzinfo=UTC)
    assert resolved.end_time == datetime(2026, 8, 1, 12, 30, tzinfo=UTC)


def test_resolve_period_uses_now_when_only_start_time_is_supplied() -> None:
    resolved = resolve_period("2026-07-20T00:00:00Z", None, now=datetime(2026, 8, 4, tzinfo=UTC))

    assert resolved.start_time == datetime(2026, 7, 20, tzinfo=UTC)
    assert resolved.end_time == datetime(2026, 8, 4, tzinfo=UTC)


def test_resolve_period_rejects_reversed_range() -> None:
    with pytest.raises(NamespaceAnalyticsError, match="error.namespaceAnalytics.invalidTimeRange") as invalid:
        resolve_period("2026-08-04T00:00:00Z", "2026-08-03T00:00:00Z")

    assert invalid.value.status_code == 400

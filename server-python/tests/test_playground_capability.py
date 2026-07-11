from datetime import UTC, datetime, timedelta

import pytest

from app.playground.capability import (
    CapabilityError,
    issue_capability,
    verify_capability,
)


def issue_test_capability(now: datetime, *, ttl_seconds: int = 300) -> str:
    return issue_capability(
        secret="test-secret",
        issuer="skillhub-test",
        audience="skill-playground-sidecar",
        subject="user-1",
        namespace="global",
        slug="meeting-notes",
        version="1.2.3",
        ttl_seconds=ttl_seconds,
        now=now,
        token_id="token-1",
    )


def test_capability_round_trip_is_read_only_and_coordinate_bound() -> None:
    now = datetime(2026, 7, 10, tzinfo=UTC)

    claims = verify_capability(
        issue_test_capability(now),
        secret="test-secret",
        issuer="skillhub-test",
        audience="skill-playground-sidecar",
        now=now + timedelta(seconds=1),
    )

    assert claims["scope"] == "playground:read"
    assert claims["sub"] == "user-1"
    assert claims["namespace"] == "global"
    assert claims["slug"] == "meeting-notes"
    assert claims["version"] == "1.2.3"
    assert "install" not in claims["scope"]


def test_capability_rejects_tampering() -> None:
    now = datetime(2026, 7, 10, tzinfo=UTC)
    token = issue_test_capability(now)

    with pytest.raises(CapabilityError):
        verify_capability(
            token + "x",
            secret="test-secret",
            issuer="skillhub-test",
            audience="skill-playground-sidecar",
            now=now,
        )


def test_capability_rejects_expiry() -> None:
    now = datetime(2026, 7, 10, tzinfo=UTC)

    with pytest.raises(CapabilityError, match="expired"):
        verify_capability(
            issue_test_capability(now, ttl_seconds=1),
            secret="test-secret",
            issuer="skillhub-test",
            audience="skill-playground-sidecar",
            now=now + timedelta(seconds=2),
        )

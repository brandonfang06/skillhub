from datetime import UTC, datetime

import pytest

from app.service_accounts.service import (
    ServiceAccountError,
    generate_service_token,
    normalize_principal_code,
    normalize_scopes,
    parse_service_token_expiry,
)


def test_service_account_validation_normalizes_only_safe_values() -> None:
    assert normalize_principal_code(" gitlab-oss-importer ") == "gitlab-oss-importer"
    assert normalize_scopes(["source:import", "source:import"]) == ("source:import",)
    with pytest.raises(ServiceAccountError, match="validation.servicePrincipal.code"):
        normalize_principal_code("GitLab Importer")
    with pytest.raises(ServiceAccountError, match="validation.serviceToken.scopes"):
        normalize_scopes(["skill:publish"])


def test_service_token_expiry_allows_never_and_caps_dates_at_three_years() -> None:
    now = datetime(2026, 8, 24, 8, 0, tzinfo=UTC)
    assert parse_service_token_expiry(None, now=now) is None
    assert parse_service_token_expiry("2029-08-24T23:59:59Z", now=now) == datetime(
        2029, 8, 24, 23, 59, 59, tzinfo=UTC
    )
    for raw in ("", "2026-08-24T08:00:00Z", "2029-08-25T00:00:00Z"):
        with pytest.raises(
            ServiceAccountError, match="validation.serviceToken.expiresAt"
        ):
            parse_service_token_expiry(raw, now=now)


def test_service_token_expiry_uses_february_28_for_leap_day_anniversary() -> None:
    now = datetime(2028, 2, 29, 12, 0, tzinfo=UTC)
    assert parse_service_token_expiry("2031-02-28T23:59:59Z", now=now)
    with pytest.raises(ServiceAccountError, match="validation.serviceToken.expiresAt.range"):
        parse_service_token_expiry("2031-03-01T00:00:00Z", now=now)


def test_service_token_generation_uses_distinct_prefix() -> None:
    assert generate_service_token(lambda _: "fixed-secret") == "st_fixed-secret"

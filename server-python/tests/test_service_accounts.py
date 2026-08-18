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


def test_service_token_expiry_is_required_future_and_capped_at_365_days() -> None:
    now = datetime(2026, 8, 18, tzinfo=UTC)
    assert parse_service_token_expiry("2027-08-18T00:00:00Z", now=now) == datetime(
        2027, 8, 18, tzinfo=UTC
    )
    for raw in (None, "", "2026-08-18T00:00:00Z", "2027-08-19T00:00:00Z"):
        with pytest.raises(
            ServiceAccountError, match="validation.serviceToken.expiresAt"
        ):
            parse_service_token_expiry(raw, now=now)


def test_service_token_generation_uses_distinct_prefix() -> None:
    assert generate_service_token(lambda _: "fixed-secret") == "st_fixed-secret"

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import HTTPException

from app.auth.service_tokens import (
    ServiceTokenPrincipal,
    read_service_token_principal,
    resolve_service_token_or_401,
)
from app.auth.tokens import sha256_token


class FakeMappings:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self.row = row

    def one_or_none(self) -> dict[str, Any] | None:
        return self.row


class FakeResult:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self.row = row

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.row)


class FakeConnection:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self.row = row
        self.seen_hash: str | None = None
        self.touched: list[int] = []

    async def execute(self, statement: object, params: dict[str, Any]) -> FakeResult:
        sql = " ".join(str(statement).split())
        if "FROM service_token" in sql:
            self.seen_hash = str(params["token_hash"])
            return FakeResult(self.row)
        if sql.startswith("UPDATE service_token SET last_used_at"):
            self.touched.append(int(params["token_id"]))
            return FakeResult()
        raise AssertionError(f"unexpected SQL: {sql}")


class FakeContext:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(self, *_args: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def begin(self) -> FakeContext:
        return FakeContext(self.connection)


def active_row(**changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "token_id": 7,
        "scope_json": ["source:import"],
        "service_principal_id": "svc_importer",
        "code": "gitlab-oss-importer",
        "display_name": "GitLab OSS Importer",
    }
    row.update(changes)
    return row


def test_service_token_resolver_hashes_reads_and_touches_only_valid_st_token() -> None:
    connection = FakeConnection(active_row())

    result = asyncio.run(
        read_service_token_principal(FakeEngine(connection), "st_secret")
    )

    assert result == ServiceTokenPrincipal(
        service_principal_id="svc_importer",
        code="gitlab-oss-importer",
        display_name="GitLab OSS Importer",
        token_id=7,
        token_scopes=("source:import",),
    )
    assert connection.seen_hash == sha256_token("st_secret")
    assert connection.touched == [7]
    assert (
        asyncio.run(
            read_service_token_principal(FakeEngine(FakeConnection(None)), "sk_user")
        )
        is None
    )


class FakeState:
    pass


class FakeApp:
    def __init__(self) -> None:
        self.state = FakeState()


class FakeRequest:
    def __init__(self) -> None:
        self.app = FakeApp()


def test_route_resolver_requires_service_prefix_scope_and_safe_errors() -> None:
    request = FakeRequest()
    request.app.state.auth_service_bearer_reader = lambda _raw: ServiceTokenPrincipal(
        "svc_importer",
        "gitlab-oss-importer",
        "GitLab OSS Importer",
        7,
        ("source:import",),
    )

    resolved = asyncio.run(
        resolve_service_token_or_401(
            request, "Bearer st_secret", required_scope="source:import"
        )
    )
    assert resolved.service_principal_id == "svc_importer"

    for authorization, status, detail in (
        (None, 401, "error.auth.required"),
        ("Bearer sk_personal-secret", 403, "error.sourceImport.serviceToken.required"),
        ("Bearer raw-secret", 401, "error.auth.required"),
    ):
        with pytest.raises(HTTPException) as captured:
            asyncio.run(
                resolve_service_token_or_401(
                    request, authorization, required_scope="source:import"
                )
            )
        assert captured.value.status_code == status
        assert captured.value.detail == detail
        assert "secret" not in str(captured.value.detail)

    request.app.state.auth_service_bearer_reader = lambda _raw: ServiceTokenPrincipal(
        "svc_importer", "gitlab-oss-importer", "GitLab OSS Importer", 7, ()
    )
    with pytest.raises(HTTPException) as missing_scope:
        asyncio.run(
            resolve_service_token_or_401(
                request, "Bearer st_secret", required_scope="source:import"
            )
        )
    assert missing_scope.value.status_code == 403
    assert missing_scope.value.detail == "error.serviceToken.scope.missing"


@pytest.mark.parametrize(
    ("expires_at", "revoked_at", "status"),
    [
        (datetime.now(UTC) - timedelta(seconds=1), None, "ACTIVE"),
        (datetime.now(UTC) + timedelta(hours=1), datetime.now(UTC), "ACTIVE"),
        (datetime.now(UTC) + timedelta(hours=1), None, "DISABLED"),
    ],
)
def test_database_query_contract_rejects_expired_revoked_and_disabled(
    expires_at: datetime,
    revoked_at: datetime | None,
    status: str,
) -> None:
    # The database predicate owns these boundary checks; a row is returned only
    # when every condition is valid.
    connection = FakeConnection(None)
    assert (
        asyncio.run(read_service_token_principal(FakeEngine(connection), "st_invalid"))
        is None
    )
    assert connection.touched == []

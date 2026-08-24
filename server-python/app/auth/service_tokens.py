from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from inspect import isawaitable
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import text

from app.auth.context import bearer_token, has_bearer_authorization
from app.auth.tokens import sha256_token


@dataclass(frozen=True)
class ServiceTokenPrincipal:
    service_principal_id: str
    code: str
    display_name: str
    token_id: int
    token_scopes: tuple[str, ...]


def _scopes(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return ()
        if isinstance(parsed, list):
            return tuple(str(item) for item in parsed)
    return ()


async def read_service_token_principal(
    engine: Any,
    raw_token: str,
) -> ServiceTokenPrincipal | None:
    if not raw_token.startswith("st_"):
        return None
    now = datetime.now(UTC)
    async with engine.begin() as connection:
        row = (
            (
                await connection.execute(
                    text(
                        """
                    SELECT token.id AS token_id,
                           token.scope_json,
                           principal.id AS service_principal_id,
                           principal.code,
                           principal.display_name
                    FROM service_token token
                    JOIN service_principal principal
                      ON principal.id = token.service_principal_id
                    WHERE token.token_hash = :token_hash
                      AND token.revoked_at IS NULL
                      AND (token.expires_at IS NULL OR token.expires_at > :now)
                      AND principal.status = 'ACTIVE'
                    LIMIT 1
                    """
                    ),
                    {"token_hash": sha256_token(raw_token), "now": now},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        await connection.execute(
            text("UPDATE service_token SET last_used_at = :now WHERE id = :token_id"),
            {"now": now, "token_id": int(row["token_id"])},
        )
    return ServiceTokenPrincipal(
        service_principal_id=str(row["service_principal_id"]),
        code=str(row["code"]),
        display_name=str(row["display_name"]),
        token_id=int(row["token_id"]),
        token_scopes=_scopes(row.get("scope_json")),
    )


async def resolve_service_token_or_401(
    request: Request,
    authorization: str | None,
    *,
    required_scope: str,
) -> ServiceTokenPrincipal:
    raw_token = bearer_token(authorization)
    if not has_bearer_authorization(authorization) or raw_token is None:
        raise HTTPException(status_code=401, detail="error.auth.required")
    if raw_token.startswith("sk_"):
        raise HTTPException(
            status_code=403, detail="error.sourceImport.serviceToken.required"
        )
    if not raw_token.startswith("st_"):
        raise HTTPException(status_code=401, detail="error.auth.required")

    reader = getattr(request.app.state, "auth_service_bearer_reader", None)
    if reader is None:
        principal = await read_service_token_principal(
            request.app.state.db_engine, raw_token
        )
    else:
        result = reader(raw_token)
        principal = await result if isawaitable(result) else result
    if principal is None:
        raise HTTPException(status_code=401, detail="error.auth.required")
    if required_scope not in principal.token_scopes:
        raise HTTPException(status_code=403, detail="error.serviceToken.scope.missing")
    return principal

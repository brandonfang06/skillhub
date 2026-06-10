from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy import text

DEFAULT_TOKEN_SCOPES = ["skill:read", "skill:publish"]
MAX_TOKEN_NAME_LENGTH = 64


class ApiTokenError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def generate_raw_token() -> str:
    return f"sk_{secrets.token_urlsafe(32)}"


def sha256_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _normalize_name(name: str | None) -> str:
    return "" if name is None else name.strip()


def _validate_name(name: str) -> None:
    if name == "":
        raise ApiTokenError("validation.token.name.notBlank")
    if len(name) > MAX_TOKEN_NAME_LENGTH:
        raise ApiTokenError("validation.token.name.size")


def _normalize_scopes(scopes: Any) -> list[str]:
    if not scopes:
        return list(DEFAULT_TOKEN_SCOPES)
    if isinstance(scopes, list):
        return [str(scope) for scope in scopes]
    return list(DEFAULT_TOKEN_SCOPES)


def _parse_expires_at(value: str | None) -> datetime | None:
    if value is None or str(value).strip() == "":
        return None
    raw = str(value).strip()
    candidates = [raw]
    if raw.endswith("Z"):
        candidates.insert(0, f"{raw[:-1]}+00:00")
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            else:
                parsed = parsed.astimezone(UTC)
            if not parsed > datetime.now(UTC):
                raise ApiTokenError("validation.token.expiresAt.future")
            return parsed
        except ApiTokenError:
            raise
        except ValueError:
            continue
    raise ApiTokenError("validation.token.expiresAt.invalid")


def _format_instant(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        if value == "":
            return ""
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    elif isinstance(value, datetime):
        parsed = value
    else:
        return str(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)
    return parsed.isoformat().replace("+00:00", "Z")


def _decode_scope_json(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []


def _summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "name": str(row["name"]),
        "tokenPrefix": str(row["token_prefix"]),
        "createdAt": _format_instant(row.get("created_at")),
        "expiresAt": _format_instant(row.get("expires_at")),
        "lastUsedAt": _format_instant(row.get("last_used_at")),
    }


async def _find_active_by_name(connection: Any, user_id: str, name: str) -> dict[str, Any] | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT id
                FROM api_token
                WHERE user_id = :user_id
                  AND revoked_at IS NULL
                  AND LOWER(name) = LOWER(:name)
                LIMIT 1
                """
            ),
            {"user_id": user_id, "name": name},
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


async def create_api_token(
    engine: Any,
    *,
    user_id: str,
    name: str | None,
    scopes: Any = None,
    expires_at: str | None = None,
    token_generator: Any = generate_raw_token,
) -> dict[str, Any]:
    normalized_name = _normalize_name(name)
    _validate_name(normalized_name)
    parsed_expires_at = _parse_expires_at(expires_at)
    normalized_scopes = _normalize_scopes(scopes)
    raw_token = token_generator()
    token_hash = sha256_token(raw_token)
    token_prefix = raw_token[:8]
    now = datetime.now(UTC)

    async with engine.begin() as connection:
        existing = await _find_active_by_name(connection, user_id, normalized_name)
        if existing is not None:
            await connection.execute(
                text("UPDATE api_token SET revoked_at = :revoked_at WHERE id = :token_id"),
                {"token_id": int(existing["id"]), "revoked_at": now},
            )
        try:
            row = (
                await connection.execute(
                    text(
                        """
                        INSERT INTO api_token (
                            subject_type,
                            subject_id,
                            user_id,
                            name,
                            token_prefix,
                            token_hash,
                            scope_json,
                            expires_at
                        )
                        VALUES (
                            'USER',
                            :user_id,
                            :user_id,
                            :name,
                            :token_prefix,
                            :token_hash,
                            CAST(:scope_json AS jsonb),
                            :expires_at
                        )
                        RETURNING id, name, token_prefix, created_at, expires_at
                        """
                    ),
                    {
                        "user_id": user_id,
                        "name": normalized_name,
                        "token_prefix": token_prefix,
                        "token_hash": token_hash,
                        "scope_json": json.dumps(normalized_scopes, separators=(",", ":")),
                        "expires_at": parsed_expires_at,
                    },
                )
            ).mappings().one_or_none()
        except IntegrityError as exc:
            raise ApiTokenError("error.token.name.duplicate") from exc
    if row is None:
        raise ApiTokenError("error.token.createFailed", status_code=500)
    created = dict(row)
    return {
        "token": raw_token,
        "id": int(created["id"]),
        "name": str(created["name"]),
        "tokenPrefix": str(created["token_prefix"]),
        "createdAt": _format_instant(created.get("created_at")),
        "expiresAt": _format_instant(created.get("expires_at")),
    }


async def list_api_tokens(engine: Any, *, user_id: str, page: int, size: int) -> dict[str, Any]:
    resolved_page = max(int(page), 0)
    resolved_size = max(int(size), 1)
    async with engine.connect() as connection:
        total = (
            await connection.execute(
                text(
                    """
                    SELECT COUNT(*) AS count
                    FROM api_token
                    WHERE user_id = :user_id
                      AND revoked_at IS NULL
                    """
                ),
                {"user_id": user_id},
            )
        ).scalar_one()
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT id, name, token_prefix, created_at, expires_at, last_used_at, scope_json
                    FROM api_token
                    WHERE user_id = :user_id
                      AND revoked_at IS NULL
                    ORDER BY created_at DESC
                    OFFSET :offset
                    LIMIT :limit
                    """
                ),
                {"user_id": user_id, "offset": resolved_page * resolved_size, "limit": resolved_size},
            )
        ).mappings().all()
    return {
        "items": [_summary(dict(row)) for row in rows],
        "total": int(total),
        "page": resolved_page,
        "size": resolved_size,
    }


async def revoke_api_token(engine: Any, *, user_id: str, token_id: int) -> None:
    async with engine.begin() as connection:
        row = (
            await connection.execute(
                text("SELECT id, user_id FROM api_token WHERE id = :token_id LIMIT 1"),
                {"token_id": token_id},
            )
        ).mappings().one_or_none()
        if row is None or str(row["user_id"]) != user_id:
            return None
        await connection.execute(
            text("UPDATE api_token SET revoked_at = :revoked_at WHERE id = :token_id"),
            {"token_id": token_id, "revoked_at": datetime.now(UTC)},
        )
    return None


async def update_api_token_expiration(
    engine: Any,
    *,
    user_id: str,
    token_id: int,
    expires_at: str | None,
) -> dict[str, Any]:
    parsed_expires_at = _parse_expires_at(expires_at)
    async with engine.begin() as connection:
        existing = (
            await connection.execute(
                text(
                    """
                    SELECT id, user_id, revoked_at
                    FROM api_token
                    WHERE id = :token_id
                    LIMIT 1
                    """
                ),
                {"token_id": token_id},
            )
        ).mappings().one_or_none()
        if existing is None or str(existing["user_id"]) != user_id or existing["revoked_at"] is not None:
            raise ApiTokenError("error.token.notFound", status_code=404)
        row = (
            await connection.execute(
                text(
                    """
                    UPDATE api_token
                    SET expires_at = :expires_at
                    WHERE id = :token_id
                    RETURNING id, name, token_prefix, created_at, expires_at, last_used_at
                    """
                ),
                {"token_id": token_id, "expires_at": parsed_expires_at},
            )
        ).mappings().one_or_none()
    if row is None:
        raise ApiTokenError("error.token.notFound", status_code=404)
    return _summary(dict(row))

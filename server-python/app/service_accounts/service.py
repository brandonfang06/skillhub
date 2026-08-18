from __future__ import annotations

import re
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.audit.writer import write_audit_log
from app.auth.tokens import sha256_token
from app.service_accounts.contracts import (
    ServicePrincipal,
    ServicePrincipalSummary,
    ServiceTokenMetadata,
    ServiceTokenSecret,
)
from app.service_accounts.repository import ServiceAccountRepository

CODE_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,99}$")
ALLOWED_SCOPES = {"source:import"}
MAX_EXPIRY = timedelta(days=365)


class ServiceAccountError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def require_service_account_admin(platform_roles: list[str]) -> None:
    if "SUPER_ADMIN" not in {str(role) for role in platform_roles}:
        raise ServiceAccountError(
            "error.servicePrincipal.admin.required", status_code=403
        )


def normalize_principal_code(value: str) -> str:
    code = str(value or "").strip()
    if CODE_PATTERN.fullmatch(code) is None:
        raise ServiceAccountError("validation.servicePrincipal.code")
    return code


def _bounded_text(value: str | None, *, code: str, maximum: int) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > maximum:
        raise ServiceAccountError(code)
    return normalized


def normalize_scopes(values: Any) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple, set)):
        raise ServiceAccountError("validation.serviceToken.scopes")
    normalized = tuple(
        sorted({str(value).strip() for value in values if str(value).strip()})
    )
    if not normalized or set(normalized) != ALLOWED_SCOPES:
        raise ServiceAccountError("validation.serviceToken.scopes")
    return normalized


def parse_service_token_expiry(
    value: str | datetime | None, *, now: datetime
) -> datetime:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ServiceAccountError("validation.serviceToken.expiresAt.required")
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    except ValueError as exc:
        raise ServiceAccountError("validation.serviceToken.expiresAt.invalid") from exc
    parsed = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    parsed = parsed.astimezone(UTC)
    if parsed <= now or parsed > now + MAX_EXPIRY:
        raise ServiceAccountError("validation.serviceToken.expiresAt.range")
    return parsed


def generate_service_token(
    generator: Callable[[int], str] = secrets.token_urlsafe,
) -> str:
    return f"st_{generator(32)}"


def _secret(metadata: ServiceTokenMetadata, raw_token: str) -> ServiceTokenSecret:
    return ServiceTokenSecret(**metadata.__dict__, token=raw_token)


async def _write_admin_audit(
    connection: Any,
    *,
    actor_user_id: str,
    action: str,
    principal_id: str,
    token_id: int | None,
    now: datetime,
) -> None:
    await write_audit_log(
        connection,
        actor_user_id=actor_user_id,
        action=action,
        target_type="SERVICE_TOKEN" if token_id is not None else "SERVICE_PRINCIPAL",
        target_id=token_id,
        request_id=None,
        client_ip=None,
        user_agent=None,
        detail={"servicePrincipalId": principal_id},
        created_at=now,
    )


async def create_service_principal(
    engine: Any,
    *,
    code: str,
    display_name: str,
    actor_user_id: str,
    actor_platform_roles: list[str],
    id_generator: Callable[[], str] = lambda: f"svc_{uuid4().hex}",
    now: datetime | None = None,
) -> ServicePrincipal:
    require_service_account_admin(actor_platform_roles)
    normalized_code = normalize_principal_code(code)
    normalized_name = _bounded_text(
        display_name,
        code="validation.servicePrincipal.displayName",
        maximum=200,
    )
    timestamp = now or datetime.now(UTC)
    try:
        async with engine.begin() as connection:
            principal = await ServiceAccountRepository(connection).create_principal(
                principal_id=id_generator(),
                code=normalized_code,
                display_name=normalized_name,
                actor_user_id=actor_user_id,
                now=timestamp,
            )
            await _write_admin_audit(
                connection,
                actor_user_id=actor_user_id,
                action="SERVICE_PRINCIPAL_CREATE",
                principal_id=principal.id,
                token_id=None,
                now=timestamp,
            )
            return principal
    except IntegrityError as exc:
        raise ServiceAccountError(
            "error.servicePrincipal.code.duplicate", status_code=409
        ) from exc


async def list_service_principals(
    engine: Any,
    *,
    page: int,
    size: int,
    actor_platform_roles: list[str],
) -> tuple[list[ServicePrincipalSummary], int]:
    require_service_account_admin(actor_platform_roles)
    resolved_page = max(page, 0)
    resolved_size = min(max(size, 1), 100)
    async with engine.connect() as connection:
        return await ServiceAccountRepository(connection).list_principals(
            page=resolved_page,
            size=resolved_size,
        )


async def update_service_principal(
    engine: Any,
    *,
    service_principal_id: str,
    display_name: str | None,
    status: str | None,
    actor_user_id: str,
    actor_platform_roles: list[str],
    now: datetime | None = None,
) -> ServicePrincipal:
    require_service_account_admin(actor_platform_roles)
    timestamp = now or datetime.now(UTC)
    async with engine.begin() as connection:
        repository = ServiceAccountRepository(connection)
        current = await repository.read_principal(service_principal_id, for_update=True)
        if current is None:
            raise ServiceAccountError(
                "error.servicePrincipal.notFound", status_code=404
            )
        resolved_name = (
            _bounded_text(
                display_name,
                code="validation.servicePrincipal.displayName",
                maximum=200,
            )
            if display_name is not None
            else current.display_name
        )
        resolved_status = str(status or current.status)
        if resolved_status not in {"ACTIVE", "DISABLED"}:
            raise ServiceAccountError("validation.servicePrincipal.status")
        updated = await repository.update_principal(
            principal_id=current.id,
            display_name=resolved_name,
            status=resolved_status,
            now=timestamp,
        )
        await _write_admin_audit(
            connection,
            actor_user_id=actor_user_id,
            action="SERVICE_PRINCIPAL_UPDATE",
            principal_id=current.id,
            token_id=None,
            now=timestamp,
        )
        return updated


async def _active_principal(
    repository: ServiceAccountRepository, principal_id: str
) -> ServicePrincipal:
    principal = await repository.read_principal(principal_id, for_update=True)
    if principal is None:
        raise ServiceAccountError("error.servicePrincipal.notFound", status_code=404)
    if principal.status != "ACTIVE":
        raise ServiceAccountError("error.servicePrincipal.inactive", status_code=409)
    return principal


async def create_service_token(
    engine: Any,
    *,
    service_principal_id: str,
    name: str,
    scopes: Any,
    expires_at: str | datetime | None,
    actor_user_id: str,
    actor_platform_roles: list[str],
    token_generator: Callable[[int], str] = secrets.token_urlsafe,
    now: datetime | None = None,
) -> ServiceTokenSecret:
    require_service_account_admin(actor_platform_roles)
    timestamp = now or datetime.now(UTC)
    normalized_name = _bounded_text(
        name, code="validation.serviceToken.name", maximum=100
    )
    normalized_scopes = normalize_scopes(scopes)
    expiry = parse_service_token_expiry(expires_at, now=timestamp)
    raw_token = generate_service_token(token_generator)
    try:
        async with engine.begin() as connection:
            repository = ServiceAccountRepository(connection)
            await _active_principal(repository, service_principal_id)
            metadata = await repository.create_token(
                principal_id=service_principal_id,
                name=normalized_name,
                token_prefix=raw_token[:12],
                token_hash=sha256_token(raw_token),
                scopes=normalized_scopes,
                actor_user_id=actor_user_id,
                expires_at=expiry,
                now=timestamp,
            )
            await _write_admin_audit(
                connection,
                actor_user_id=actor_user_id,
                action="SERVICE_TOKEN_CREATE",
                principal_id=service_principal_id,
                token_id=metadata.id,
                now=timestamp,
            )
            return _secret(metadata, raw_token)
    except IntegrityError as exc:
        raise ServiceAccountError(
            "error.serviceToken.name.duplicate", status_code=409
        ) from exc


async def list_service_tokens(
    engine: Any,
    *,
    service_principal_id: str,
    actor_platform_roles: list[str],
    include_revoked: bool = False,
) -> list[ServiceTokenMetadata]:
    require_service_account_admin(actor_platform_roles)
    async with engine.connect() as connection:
        repository = ServiceAccountRepository(connection)
        if await repository.read_principal(service_principal_id) is None:
            raise ServiceAccountError(
                "error.servicePrincipal.notFound", status_code=404
            )
        return await repository.list_tokens(
            service_principal_id, include_revoked=include_revoked
        )


async def revoke_service_token(
    engine: Any,
    *,
    service_principal_id: str,
    token_id: int,
    actor_user_id: str,
    actor_platform_roles: list[str],
    now: datetime | None = None,
) -> None:
    require_service_account_admin(actor_platform_roles)
    timestamp = now or datetime.now(UTC)
    async with engine.begin() as connection:
        repository = ServiceAccountRepository(connection)
        token = await repository.read_token(
            service_principal_id, token_id, for_update=True
        )
        if token is None:
            raise ServiceAccountError("error.serviceToken.notFound", status_code=404)
        if token.revoked_at is None:
            await repository.revoke_token(token.id, now=timestamp)
            await _write_admin_audit(
                connection,
                actor_user_id=actor_user_id,
                action="SERVICE_TOKEN_REVOKE",
                principal_id=service_principal_id,
                token_id=token.id,
                now=timestamp,
            )


async def rotate_service_token(
    engine: Any,
    *,
    service_principal_id: str,
    token_id: int,
    expires_at: str | datetime | None,
    actor_user_id: str,
    actor_platform_roles: list[str],
    token_generator: Callable[[int], str] = secrets.token_urlsafe,
    now: datetime | None = None,
) -> ServiceTokenSecret:
    require_service_account_admin(actor_platform_roles)
    timestamp = now or datetime.now(UTC)
    expiry = parse_service_token_expiry(expires_at, now=timestamp)
    raw_token = generate_service_token(token_generator)
    try:
        async with engine.begin() as connection:
            repository = ServiceAccountRepository(connection)
            await _active_principal(repository, service_principal_id)
            old = await repository.read_token(
                service_principal_id, token_id, for_update=True
            )
            if old is None or old.revoked_at is not None:
                raise ServiceAccountError(
                    "error.serviceToken.notFound", status_code=404
                )
            await repository.revoke_token(old.id, now=timestamp)
            replacement = await repository.create_token(
                principal_id=service_principal_id,
                name=old.name,
                token_prefix=raw_token[:12],
                token_hash=sha256_token(raw_token),
                scopes=old.scopes,
                actor_user_id=actor_user_id,
                expires_at=expiry,
                now=timestamp,
            )
            await _write_admin_audit(
                connection,
                actor_user_id=actor_user_id,
                action="SERVICE_TOKEN_ROTATE",
                principal_id=service_principal_id,
                token_id=replacement.id,
                now=timestamp,
            )
            return _secret(replacement, raw_token)
    except IntegrityError as exc:
        raise ServiceAccountError(
            "error.serviceToken.rotateFailed", status_code=409
        ) from exc

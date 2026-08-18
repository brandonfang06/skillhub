from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

ServicePrincipalStatus = Literal["ACTIVE", "DISABLED"]


@dataclass(frozen=True)
class ServicePrincipal:
    id: str
    code: str
    display_name: str
    status: ServicePrincipalStatus
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ServicePrincipalSummary(ServicePrincipal):
    active_token_count: int
    nearest_token_expiry: datetime | None
    last_used_at: datetime | None


@dataclass(frozen=True)
class ServiceTokenMetadata:
    id: int
    service_principal_id: str
    name: str
    token_prefix: str
    scopes: tuple[str, ...]
    created_by_user_id: str
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


@dataclass(frozen=True)
class ServiceTokenSecret(ServiceTokenMetadata):
    token: str

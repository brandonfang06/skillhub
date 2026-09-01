from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Protocol
from uuid import uuid4

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from app.auth.context import (
    has_bearer_authorization,
    resolve_current_user_or_401,
)
from app.core.config import RateLimitCategoryOverride, get_settings, parse_bool

log = logging.getLogger("uvicorn.error")

SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local current = redis.call('ZCARD', key)
if current < limit then
    redis.call('ZADD', key, now, member)
    redis.call('EXPIRE', key, math.ceil(window / 1000))
    return 1
end
return 0
"""


class RateLimitChecker(Protocol):
    async def try_acquire(
        self,
        *,
        key: str,
        limit: int,
        window_seconds: int,
        member: str,
    ) -> bool: ...


class RedisSlidingWindowRateLimiter:
    def __init__(self, redis_client: Any) -> None:
        self.redis_client = redis_client

    async def try_acquire(
        self,
        *,
        key: str,
        limit: int,
        window_seconds: int,
        member: str,
    ) -> bool:
        if limit <= 0:
            return False
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        result = await self.redis_client.execute_command(
            "EVAL",
            SLIDING_WINDOW_SCRIPT,
            1,
            key,
            now_ms,
            window_seconds * 1000,
            limit,
            member,
        )
        return int(result) == 1


@dataclass(frozen=True)
class EffectiveRateLimit:
    limit: int
    window_seconds: int


class RateLimitExceeded(Exception):
    def __init__(self, window_seconds: int) -> None:
        super().__init__("error.rateLimit.exceeded")
        self.window_seconds = window_seconds


class RateLimitUnavailable(Exception):
    pass


def effective_rate_limit(
    settings: Any,
    *,
    category: str,
    authenticated: bool,
    authenticated_default: int,
    anonymous_default: int,
    window_seconds_default: int,
) -> EffectiveRateLimit:
    overrides: dict[str, RateLimitCategoryOverride] = getattr(
        settings, "rate_limit_overrides", {}
    )
    override = overrides.get(category)
    if authenticated:
        limit = (
            override.authenticated
            if override is not None and override.authenticated is not None
            else authenticated_default
        )
    else:
        limit = (
            override.anonymous
            if override is not None and override.anonymous is not None
            else anonymous_default
        )
    window_seconds = (
        override.window_seconds
        if override is not None and override.window_seconds is not None
        else window_seconds_default
    )
    return EffectiveRateLimit(limit=limit, window_seconds=window_seconds)


async def _optional_rate_limit_user(request: Request) -> dict[str, object] | None:
    mock_user_id = request.headers.get("X-Mock-User-Id")
    authorization = request.headers.get("Authorization")
    if (
        (mock_user_id is not None and mock_user_id.strip() != "")
        or has_bearer_authorization(authorization)
    ):
        return await resolve_current_user_or_401(
            request,
            mock_user_id,
            authorization,
        )
    try:
        return await resolve_current_user_or_401(request, None, None)
    except HTTPException as exc:
        if exc.status_code == 401:
            return None
        raise


def _identity_key(category: str, request: Request, user_id: str | None) -> str:
    if user_id is None:
        identity = request.client.host if request.client is not None else "unknown"
        identity_type = "ip"
    else:
        identity = user_id
        identity_type = "user"
    identity_digest = sha256(identity.encode("utf-8")).hexdigest()
    key = f"ratelimit:{category}:{identity_type}:{identity_digest}"
    if category != "download":
        return key

    values = request.path_params
    namespace = values.get("namespace")
    slug = values.get("slug")
    if namespace is None or slug is None:
        return key
    target = values.get("version") or values.get("tagName") or "latest"
    resource = f"{namespace}/{slug}/{target}"
    return f"{key}:resource:{sha256(resource.encode('utf-8')).hexdigest()}"


def rate_limit(
    category: str,
    *,
    authenticated: int = 60,
    anonymous: int = 20,
    window_seconds: int = 60,
) -> Callable[[Request], Awaitable[None]]:
    async def enforce(request: Request) -> None:
        settings = getattr(request.app.state, "settings", None)
        if settings is None:
            if not parse_bool(os.getenv("SKILLHUB_RATELIMIT_ENABLED")):
                return
            settings = get_settings()
        if not bool(getattr(settings, "rate_limit_enabled", False)):
            return

        user = await _optional_rate_limit_user(request)
        user_id = str(user["userId"]) if user is not None else None
        effective = effective_rate_limit(
            settings,
            category=category,
            authenticated=user is not None,
            authenticated_default=authenticated,
            anonymous_default=anonymous,
            window_seconds_default=window_seconds,
        )
        if user is None and effective.limit <= 0:
            raise HTTPException(status_code=401, detail="error.auth.required")
        checker: RateLimitChecker | None = getattr(
            request.app.state, "rate_limit_checker", None
        )
        if checker is None:
            redis_client = getattr(request.app.state, "redis_client", None)
            if redis_client is None:
                raise RateLimitUnavailable
            checker = RedisSlidingWindowRateLimiter(redis_client)

        try:
            allowed = await checker.try_acquire(
                key=_identity_key(category, request, user_id),
                limit=effective.limit,
                window_seconds=effective.window_seconds,
                member=f"{getattr(request.state, 'request_id', 'request')}:{uuid4().hex}",
            )
        except RateLimitUnavailable:
            raise
        except Exception as exc:
            log.warning(
                "Rate-limit dependency unavailable category=%s request_id=%s",
                category,
                getattr(request.state, "request_id", None),
            )
            raise RateLimitUnavailable from exc
        if not allowed:
            raise RateLimitExceeded(effective.window_seconds)

    return enforce


def _error_payload(request: Request, *, status_code: int, message: str) -> dict[str, object]:
    return {
        "code": status_code,
        "msg": message,
        "data": None,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "requestId": request.state.request_id,
    }


async def rate_limit_exceeded_response(
    request: Request,
    exc: RateLimitExceeded,
) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content=_error_payload(
            request,
            status_code=429,
            message="error.rateLimit.exceeded",
        ),
        headers={"Retry-After": str(exc.window_seconds)},
    )


async def rate_limit_unavailable_response(
    request: Request,
    exc: RateLimitUnavailable,
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content=_error_payload(
            request,
            status_code=503,
            message="error.rateLimit.unavailable",
        ),
        headers={"Retry-After": "1"},
    )


__all__ = [
    "EffectiveRateLimit",
    "RateLimitExceeded",
    "RateLimitUnavailable",
    "RedisSlidingWindowRateLimiter",
    "effective_rate_limit",
    "rate_limit",
    "rate_limit_exceeded_response",
    "rate_limit_unavailable_response",
]

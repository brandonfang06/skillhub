from __future__ import annotations

import asyncio
import json
import secrets
from typing import Any, Protocol

from app.auth.tokens import create_api_token
from app.publish.scanner_handoff import encode_resp_command, open_redis_connection, parse_redis_target, read_resp

DEVICE_CODE_PREFIX = "device:code:"
DEVICE_CLAIM_PREFIX = "device:claim:"
USER_CODE_PREFIX = "device:usercode:"
EXPIRES_IN_SECONDS = 900
POLL_INTERVAL_SECONDS = 5
USED_CODE_TTL_SECONDS = 60
USER_CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CLI_DEVICE_TOKEN_NAME = "CLI Device Flow"
CLI_DEVICE_SCOPES = ["skill:read", "skill:publish"]


class DeviceAuthError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class DeviceRedis(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ttl_seconds: int) -> None: ...
    async def set_if_absent(self, key: str, value: str, ttl_seconds: int) -> bool: ...
    async def delete(self, key: str) -> None: ...


class RedisDeviceStore:
    def __init__(self, redis_url: str) -> None:
        self.target = parse_redis_target(redis_url)

    async def get(self, key: str) -> str | None:
        response = await self._command(["GET", key])
        return None if response is None else str(response)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        await self._command(["SET", key, value, "EX", str(ttl_seconds)])

    async def set_if_absent(self, key: str, value: str, ttl_seconds: int) -> bool:
        response = await self._command(["SET", key, value, "NX", "EX", str(ttl_seconds)])
        return str(response).upper() == "OK"

    async def delete(self, key: str) -> None:
        await self._command(["DEL", key])

    async def _command(self, arguments: list[str]) -> Any:
        reader, writer = await open_redis_connection(self.target)
        try:
            writer.write(encode_resp_command(arguments))
            await writer.drain()
            return await read_resp(reader)
        finally:
            writer.close()
            await writer.wait_closed()


def generate_random_device_code() -> str:
    return secrets.token_urlsafe(32)


def generate_user_code() -> str:
    raw = "".join(secrets.choice(USER_CODE_CHARS) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def _encode_data(data: dict[str, Any]) -> str:
    return json.dumps(data, separators=(",", ":"))


def _decode_data(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DeviceAuthError("error.deviceAuth.deviceCode.invalid") from exc
    if not isinstance(data, dict):
        raise DeviceAuthError("error.deviceAuth.deviceCode.invalid")
    return data


async def generate_device_code(
    redis: DeviceRedis,
    *,
    device_code_generator: Any = generate_random_device_code,
    user_code_generator: Any = generate_user_code,
    verification_uri: str = "/cli/auth",
) -> dict[str, Any]:
    device_code = str(device_code_generator())
    user_code = str(user_code_generator())
    data = {
        "deviceCode": device_code,
        "userCode": user_code,
        "status": "PENDING",
        "userId": None,
    }
    await redis.set(f"{DEVICE_CODE_PREFIX}{device_code}", _encode_data(data), EXPIRES_IN_SECONDS)
    await redis.set(f"{USER_CODE_PREFIX}{user_code}", device_code, EXPIRES_IN_SECONDS)
    return {
        "deviceCode": device_code,
        "userCode": user_code,
        "verificationUri": verification_uri,
        "expiresIn": EXPIRES_IN_SECONDS,
        "interval": POLL_INTERVAL_SECONDS,
    }


async def authorize_device_code(redis: DeviceRedis, *, user_code: str | None, user_id: str) -> None:
    normalized_user_code = "" if user_code is None else str(user_code).strip()
    device_code = await redis.get(f"{USER_CODE_PREFIX}{normalized_user_code}")
    if device_code is None:
        raise DeviceAuthError("error.deviceAuth.userCode.invalid")

    raw = await redis.get(f"{DEVICE_CODE_PREFIX}{device_code}")
    if raw is None:
        raise DeviceAuthError("error.deviceAuth.deviceCode.expired")
    data = _decode_data(raw)
    status = str(data.get("status") or "")
    if status == "PENDING":
        data["status"] = "AUTHORIZED"
        data["userId"] = user_id
        await redis.set(f"{DEVICE_CODE_PREFIX}{device_code}", _encode_data(data), EXPIRES_IN_SECONDS)
        return
    if status == "AUTHORIZED":
        if data.get("userId") != user_id:
            raise DeviceAuthError("error.deviceAuth.deviceCode.alreadyAuthorized")
        return
    if status == "USED":
        raise DeviceAuthError("error.deviceAuth.deviceCode.used")
    raise DeviceAuthError("error.deviceAuth.deviceCode.invalid")


async def poll_device_token(
    redis: DeviceRedis,
    engine: Any,
    *,
    device_code: str | None,
    token_generator: Any = None,
) -> dict[str, Any]:
    normalized_device_code = "" if device_code is None else str(device_code)
    raw = await redis.get(f"{DEVICE_CODE_PREFIX}{normalized_device_code}")
    if raw is None:
        raise DeviceAuthError("error.deviceAuth.deviceCode.invalid")
    data = _decode_data(raw)
    status = str(data.get("status") or "")
    if status == "PENDING":
        return {"accessToken": None, "tokenType": None, "error": "authorization_pending"}
    if status == "USED":
        raise DeviceAuthError("error.deviceAuth.deviceCode.used")
    if status != "AUTHORIZED":
        raise DeviceAuthError("error.deviceAuth.deviceCode.invalid")

    claimed = await redis.set_if_absent(f"{DEVICE_CLAIM_PREFIX}{normalized_device_code}", "claimed", USED_CODE_TTL_SECONDS)
    if not claimed:
        raise DeviceAuthError("error.deviceAuth.deviceCode.used")

    try:
        user_id = str(data.get("userId") or "")
        if user_id == "":
            raise DeviceAuthError("error.deviceAuth.deviceCode.invalid")
        create_kwargs = {
            "user_id": user_id,
            "name": CLI_DEVICE_TOKEN_NAME,
            "scopes": CLI_DEVICE_SCOPES,
        }
        if token_generator is not None:
            create_kwargs["token_generator"] = token_generator
        created = await create_api_token(engine, **create_kwargs)
        data["status"] = "USED"
        await redis.set(f"{DEVICE_CODE_PREFIX}{normalized_device_code}", _encode_data(data), USED_CODE_TTL_SECONDS)
        await redis.delete(f"{USER_CODE_PREFIX}{data.get('userCode')}")
        return {"accessToken": created["token"], "tokenType": "Bearer", "error": None}
    except Exception:
        await redis.delete(f"{DEVICE_CLAIM_PREFIX}{normalized_device_code}")
        raise

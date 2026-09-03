from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text

from app.auth.context import normalize_platform_roles
from app.auth.password_reset import bcrypt_value, verify_bcrypt_value
from app.core.config import global_namespace_auto_join_enabled

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,64}$")
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
MAX_FAILED_ATTEMPTS = 5
LOCK_DURATION = timedelta(minutes=15)
DUMMY_PASSWORD_HASH = "$2a$12$8Q/2o2A0V.b18G2DutV4c.s5zZxH6MECM7tP8mYv6b6Q6x6o9v3vu"


class LocalAuthError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def normalize_username(username: str | None) -> str:
    return "" if username is None else username.strip().lower()


def normalize_email(email: str | None) -> str | None:
    if email is None or email.strip() == "":
        return None
    return email.strip().lower()


def validate_username(username: str | None) -> str:
    normalized = normalize_username(username)
    if USERNAME_PATTERN.fullmatch(normalized) is None:
        raise LocalAuthError("error.auth.local.username.invalid")
    return normalized


def validate_email(email: str | None) -> str:
    normalized = normalize_email(email)
    if normalized is None:
        raise LocalAuthError("validation.auth.local.email.notBlank")
    if EMAIL_PATTERN.fullmatch(normalized) is None:
        raise LocalAuthError("validation.auth.local.email.invalid")
    return normalized


def validate_password_policy(password: str | None) -> str:
    if password is None or len(password) < 8:
        raise LocalAuthError("error.auth.local.password.tooShort")
    if len(password) > 128:
        raise LocalAuthError("error.auth.local.password.tooLong")
    type_count = 0
    type_count += int(any(ch.islower() for ch in password))
    type_count += int(any(ch.isupper() for ch in password))
    type_count += int(any(ch.isdigit() for ch in password))
    type_count += int(any(not ch.isalnum() for ch in password))
    if type_count < 3:
        raise LocalAuthError("error.auth.local.password.tooWeak")
    return password


def new_local_user_id() -> str:
    return f"usr_{uuid.uuid4()}"


def _invalid_credentials() -> LocalAuthError:
    return LocalAuthError("error.auth.local.invalidCredentials", status_code=401)


def _principal_from_user(user: dict[str, Any], role_codes: list[str]) -> dict[str, object]:
    return {
        "userId": str(user["id"]),
        "displayName": str(user["display_name"]),
        "email": user.get("email") or "",
        "avatarUrl": user.get("avatar_url") or "",
        "oauthProvider": "local",
        "platformRoles": normalize_platform_roles(role_codes),
    }


async def _credential_by_username(connection: Any, username: str) -> dict[str, Any] | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT user_id, username, password_hash, failed_attempts, locked_until
                FROM local_credential
                WHERE LOWER(username) = LOWER(:username)
                LIMIT 1
                """
            ),
            {"username": username},
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


async def _credential_by_user_id(connection: Any, user_id: str) -> dict[str, Any] | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT user_id, username, password_hash, failed_attempts, locked_until
                FROM local_credential
                WHERE user_id = :user_id
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


async def _user_by_email(connection: Any, email: str) -> dict[str, Any] | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT id, display_name, email, avatar_url, status
                FROM user_account
                WHERE LOWER(email) = LOWER(:email)
                LIMIT 1
                """
            ),
            {"email": email},
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


async def _user_by_id(connection: Any, user_id: str) -> dict[str, Any] | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT id, display_name, email, avatar_url, status
                FROM user_account
                WHERE id = :user_id
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


async def _role_codes(connection: Any, user_id: str) -> list[str]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT r.code
                FROM user_role_binding urb
                JOIN role r ON r.id = urb.role_id
                WHERE urb.user_id = :user_id
                ORDER BY r.code ASC
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().all()
    return [str(row["code"]) for row in rows]


async def _ensure_global_namespace_membership(connection: Any, user_id: str) -> None:
    namespace = (
        await connection.execute(
            text(
                """
                SELECT id, slug
                FROM namespace
                WHERE slug = 'global'
                LIMIT 1
                """
            )
        )
    ).mappings().one_or_none()
    if namespace is None:
        return
    namespace_id = namespace["id"]
    existing = (
        await connection.execute(
            text(
                """
                SELECT id
                FROM namespace_member
                WHERE namespace_id = :namespace_id
                  AND user_id = :user_id
                LIMIT 1
                """
            ),
            {"namespace_id": namespace_id, "user_id": user_id},
        )
    ).mappings().one_or_none()
    if existing is not None:
        return
    await connection.execute(
        text(
            """
            INSERT INTO namespace_member (namespace_id, user_id, role)
            VALUES (:namespace_id, :user_id, :role)
            """
        ),
        {"namespace_id": namespace_id, "user_id": user_id, "role": "MEMBER"},
    )


async def _reset_failed_attempts(connection: Any, user_id: str) -> None:
    await connection.execute(
        text(
            """
            UPDATE local_credential
            SET failed_attempts = :failed_attempts,
                locked_until = :locked_until,
                updated_at = :updated_at
            WHERE user_id = :user_id
            """
        ),
        {"user_id": user_id, "failed_attempts": 0, "locked_until": None, "updated_at": datetime.now(UTC)},
    )


async def register_local_user(
    engine: Any,
    *,
    username: str | None,
    password: str | None,
    email: str | None,
    user_id_factory: Callable[[], str] = new_local_user_id,
    password_hasher: Callable[[str], str] = bcrypt_value,
) -> dict[str, object]:
    normalized_username = validate_username(username)
    normalized_email = validate_email(email)
    normalized_password = validate_password_policy(password)
    async with engine.begin() as connection:
        if await _credential_by_username(connection, normalized_username) is not None:
            raise LocalAuthError("error.auth.local.username.exists", status_code=409)
        if await _user_by_email(connection, normalized_email) is not None:
            raise LocalAuthError("error.auth.local.email.exists", status_code=409)

        user_id = user_id_factory()
        await connection.execute(
            text(
                """
                INSERT INTO user_account (id, display_name, email, avatar_url, status)
                VALUES (:id, :display_name, :email, :avatar_url, :status)
                """
            ),
            {
                "id": user_id,
                "display_name": normalized_username,
                "email": normalized_email,
                "avatar_url": None,
                "status": "ACTIVE",
            },
        )
        await connection.execute(
            text(
                """
                INSERT INTO local_credential (user_id, username, password_hash)
                VALUES (:user_id, :username, :password_hash)
                """
            ),
            {
                "user_id": user_id,
                "username": normalized_username,
                "password_hash": password_hasher(normalized_password),
            },
        )
        if global_namespace_auto_join_enabled():
            await _ensure_global_namespace_membership(connection, user_id)
        user = await _user_by_id(connection, user_id)
        if user is None:
            user = {
                "id": user_id,
                "display_name": normalized_username,
                "email": normalized_email,
                "avatar_url": None,
            }
        return _principal_from_user(user, await _role_codes(connection, user_id))


def _ensure_user_can_login(user: dict[str, Any]) -> None:
    status = str(user.get("status"))
    if status == "DISABLED":
        raise LocalAuthError("error.auth.local.accountDisabled", status_code=403)
    if status == "PENDING":
        raise LocalAuthError("error.auth.local.accountPending", status_code=403)
    if status == "MERGED":
        raise LocalAuthError("error.auth.local.accountMerged", status_code=403)


def _ensure_not_locked(credential: dict[str, Any]) -> None:
    locked_until = credential.get("locked_until")
    if locked_until is not None and locked_until > datetime.now(UTC):
        raise LocalAuthError("error.auth.local.locked", status_code=423)


async def _record_failed_login(connection: Any, credential: dict[str, Any]) -> None:
    failed_attempts = int(credential.get("failed_attempts") or 0) + 1
    locked_until = datetime.now(UTC) + LOCK_DURATION if failed_attempts >= MAX_FAILED_ATTEMPTS else None
    await connection.execute(
        text(
            """
            UPDATE local_credential
            SET failed_attempts = :failed_attempts,
                locked_until = :locked_until,
                updated_at = :updated_at
            WHERE user_id = :user_id
            """
        ),
        {
            "user_id": credential["user_id"],
            "failed_attempts": failed_attempts,
            "locked_until": locked_until,
            "updated_at": datetime.now(UTC),
        },
    )


async def login_local_user(
    engine: Any,
    *,
    username: str | None,
    password: str | None,
    password_verifier: Callable[[str, str], bool] = verify_bcrypt_value,
) -> dict[str, object]:
    normalized_username = normalize_username(username)
    raw_password = "" if password is None else password
    async with engine.begin() as connection:
        credential = await _credential_by_username(connection, normalized_username)
        if credential is None:
            password_verifier(raw_password, DUMMY_PASSWORD_HASH)
            raise _invalid_credentials()

        user = await _user_by_id(connection, str(credential["user_id"]))
        if user is None:
            raise RuntimeError("User not found for local credential")
        _ensure_user_can_login(user)
        _ensure_not_locked(credential)

        if not password_verifier(raw_password, str(credential["password_hash"])):
            await _record_failed_login(connection, credential)
            raise _invalid_credentials()

        await _reset_failed_attempts(connection, str(credential["user_id"]))
        return _principal_from_user(user, await _role_codes(connection, str(credential["user_id"])))


async def change_local_password(
    engine: Any,
    *,
    user_id: str,
    current_password: str | None,
    new_password: str | None,
    password_verifier: Callable[[str, str], bool] = verify_bcrypt_value,
    password_hasher: Callable[[str], str] = bcrypt_value,
) -> None:
    async with engine.begin() as connection:
        credential = await _credential_by_user_id(connection, user_id)
        if credential is None:
            raise LocalAuthError("error.auth.local.notEnabled")
        if not password_verifier("" if current_password is None else current_password, str(credential["password_hash"])):
            raise _invalid_credentials()
        normalized_password = validate_password_policy(new_password)
        await connection.execute(
            text(
                """
                UPDATE local_credential
                SET password_hash = :password_hash,
                    failed_attempts = 0,
                    locked_until = NULL,
                    updated_at = :updated_at
                WHERE user_id = :user_id
                """
            ),
            {"user_id": user_id, "password_hash": password_hasher(normalized_password), "updated_at": datetime.now(UTC)},
        )

from __future__ import annotations

import re
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from sqlalchemy import text

PASSWORD_RESET_CODE_DIGITS = 6
PASSWORD_RESET_EXPIRY = timedelta(minutes=10)
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


class PasswordResetError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def generate_reset_code() -> str:
    return f"{secrets.randbelow(10**PASSWORD_RESET_CODE_DIGITS):06d}"


def bcrypt_value(raw_value: str) -> str:
    return bcrypt.hashpw(raw_value.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


hash_bcrypt_value = bcrypt_value


def verify_bcrypt_value(raw_value: str, hashed_value: str) -> bool:
    try:
        return bcrypt.checkpw(raw_value.encode("utf-8"), hashed_value.encode("utf-8"))
    except ValueError:
        return False


def _normalize_email(email: str | None) -> str | None:
    if email is None or email.strip() == "":
        return None
    return email.strip().lower()


def _validate_email(email: str | None) -> str:
    normalized = _normalize_email(email)
    if normalized is None:
        raise PasswordResetError("validation.auth.password.reset.email.notBlank")
    if EMAIL_PATTERN.fullmatch(normalized) is None:
        raise PasswordResetError("validation.auth.password.reset.email.invalid")
    return normalized


def _validate_code(code: str | None) -> str:
    if code is None or code.strip() == "":
        raise PasswordResetError("validation.auth.password.reset.code.notBlank")
    normalized = code.strip()
    if re.fullmatch(r"\d{6}", normalized) is None:
        raise PasswordResetError("validation.auth.password.reset.code.invalid")
    return normalized


def _validate_new_password(password: str | None) -> str:
    if password is None or password == "":
        raise PasswordResetError("validation.auth.password.reset.newPassword.notBlank")
    if len(password) < 8:
        raise PasswordResetError("error.auth.local.password.tooShort")
    if len(password) > 128:
        raise PasswordResetError("error.auth.local.password.tooLong")
    type_count = 0
    type_count += int(any(ch.islower() for ch in password))
    type_count += int(any(ch.isupper() for ch in password))
    type_count += int(any(ch.isdigit() for ch in password))
    type_count += int(any(not ch.isalnum() for ch in password))
    if type_count < 3:
        raise PasswordResetError("error.auth.local.password.tooWeak")
    return password


def validate_password_reset_request(email: str | None) -> None:
    _validate_email(email)


def validate_password_reset_confirm(email: str | None, code: str | None, new_password: str | None) -> None:
    _validate_email(email)
    _validate_code(code)
    _validate_new_password(new_password)


async def _find_user_by_email(connection: Any, email: str) -> dict[str, Any] | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT id, email, status
                FROM user_account
                WHERE LOWER(email) = LOWER(:email)
                LIMIT 1
                """
            ),
            {"email": email},
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


async def _find_local_credential(connection: Any, user_id: str) -> dict[str, Any] | None:
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


async def _consume_pending_requests(connection: Any, user_id: str, consumed_at: datetime) -> None:
    await connection.execute(
        text(
            """
            UPDATE password_reset_request
            SET consumed_at = :consumed_at
            WHERE user_id = :user_id
              AND consumed_at IS NULL
              AND expires_at > :consumed_at
            """
        ),
        {"user_id": user_id, "consumed_at": consumed_at},
    )


async def request_password_reset(
    engine: Any,
    *,
    email: str | None,
    code_generator: Callable[[], str] = generate_reset_code,
    code_hasher: Callable[[str], str] = bcrypt_value,
    sender: Callable[[str, str, bool], None] | None = None,
) -> None:
    normalized_email = _validate_email(email)
    async with engine.begin() as connection:
        user = await _find_user_by_email(connection, normalized_email)
        if user is None:
            return None
        user_id = str(user["id"])
        credential = await _find_local_credential(connection, user_id)
        if str(user.get("status")) != "ACTIVE" or not str(user.get("email") or "").strip() or credential is None:
            return None

        now = datetime.now(UTC)
        code = code_generator()
        await _consume_pending_requests(connection, user_id, now)
        await connection.execute(
            text(
                """
                INSERT INTO password_reset_request (
                    user_id,
                    email,
                    code_hash,
                    expires_at,
                    requested_by_admin,
                    requested_by_user_id
                )
                VALUES (
                    :user_id,
                    :email,
                    :code_hash,
                    :expires_at,
                    :requested_by_admin,
                    :requested_by_user_id
                )
                """
            ),
            {
                "user_id": user_id,
                "email": normalized_email,
                "code_hash": code_hasher(code),
                "expires_at": now + PASSWORD_RESET_EXPIRY,
                "requested_by_admin": False,
                "requested_by_user_id": None,
            },
        )
        if sender is not None:
            try:
                sender(normalized_email, code, False)
            except Exception:
                pass
    return None


async def _pending_reset_requests(connection: Any, user_id: str, now: datetime) -> list[dict[str, Any]]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT id, user_id, email, code_hash, expires_at, consumed_at
                FROM password_reset_request
                WHERE user_id = :user_id
                  AND consumed_at IS NULL
                  AND expires_at > :now
                ORDER BY created_at DESC, id DESC
                """
            ),
            {"user_id": user_id, "now": now},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def confirm_password_reset(
    engine: Any,
    *,
    email: str | None,
    code: str | None,
    new_password: str | None,
    code_verifier: Callable[[str, str], bool] = verify_bcrypt_value,
    password_hasher: Callable[[str], str] = bcrypt_value,
) -> None:
    normalized_email = _validate_email(email)
    normalized_code = _validate_code(code)
    password = _validate_new_password(new_password)
    async with engine.begin() as connection:
        user = await _find_user_by_email(connection, normalized_email)
        if user is None:
            raise PasswordResetError("error.auth.password.reset.invalid.code")
        user_id = str(user["id"])
        now = datetime.now(UTC)
        pending_requests = await _pending_reset_requests(connection, user_id, now)
        matched = next((row for row in pending_requests if code_verifier(normalized_code, str(row["code_hash"]))), None)
        if matched is None:
            raise PasswordResetError("error.auth.password.reset.invalid.code")

        credential = await _find_local_credential(connection, user_id)
        if credential is None:
            raise PasswordResetError("error.auth.password.reset.no.credential")

        await connection.execute(
            text(
                """
                UPDATE local_credential
                SET password_hash = :password_hash,
                    failed_attempts = 0,
                    locked_until = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = :user_id
                """
            ),
            {"user_id": user_id, "password_hash": password_hasher(password)},
        )
        await _consume_pending_requests(connection, user_id, now)
    return None

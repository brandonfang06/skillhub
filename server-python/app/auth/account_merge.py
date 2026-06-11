from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
import base64
import secrets
from typing import Any

from sqlalchemy import text

from app.auth.password_reset import bcrypt_value, verify_bcrypt_value


class AccountMergeError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


NowProvider = Callable[[], datetime]
TokenGenerator = Callable[[], str]
TokenHasher = Callable[[str], str]
TokenVerifier = Callable[[str, str], bool]

NAMESPACE_ROLE_ORDER = {"MEMBER": 0, "ADMIN": 1, "OWNER": 2}


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _generate_verification_token() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(24)).decode("ascii").rstrip("=")


def _iso_z(value: datetime) -> str:
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.astimezone(UTC).isoformat().replace("+00:00", "Z")


async def initiate_account_merge(
    engine: Any,
    *,
    primary_user_id: str,
    secondary_identifier: str | None,
    now_provider: NowProvider = _now_utc,
    token_generator: TokenGenerator = _generate_verification_token,
    token_hasher: TokenHasher = bcrypt_value,
) -> dict[str, Any]:
    async with engine.begin() as connection:
        primary_user = await _load_active_user(connection, primary_user_id, primary=True)
        secondary_user = await _resolve_secondary_user(connection, secondary_identifier)
        _validate_merge_pair(primary_user, secondary_user)

        pending = (
            await connection.execute(
                text(
                    """
                    SELECT id
                    FROM account_merge_request
                    WHERE secondary_user_id = :secondary_user_id
                      AND status = 'PENDING'
                    LIMIT 1
                    """
                ),
                {"secondary_user_id": secondary_user["id"]},
            )
        ).mappings().one_or_none()
        if pending is not None:
            raise AccountMergeError(409, "error.auth.merge.pendingExists")

        primary_credential = await _find_local_credential_by_user_id(connection, primary_user_id)
        secondary_credential = await _find_local_credential_by_user_id(connection, str(secondary_user["id"]))
        if primary_credential is not None and secondary_credential is not None:
            raise AccountMergeError(409, "error.auth.merge.localCredentialConflict")

        raw_token = token_generator()
        now = now_provider()
        expires_at = now + timedelta(minutes=30)
        row = (
            await connection.execute(
                text(
                    """
                    INSERT INTO account_merge_request (
                        primary_user_id,
                        secondary_user_id,
                        verification_token,
                        token_expires_at,
                        created_at
                    )
                    VALUES (
                        :primary_user_id,
                        :secondary_user_id,
                        :verification_token,
                        :token_expires_at,
                        :created_at
                    )
                    RETURNING id, secondary_user_id, token_expires_at
                    """
                ),
                {
                    "primary_user_id": primary_user_id,
                    "secondary_user_id": secondary_user["id"],
                    "verification_token": token_hasher(raw_token),
                    "token_expires_at": expires_at,
                    "created_at": now,
                },
            )
        ).mappings().one_or_none()

    if row is None:
        raise AccountMergeError(500, "error.auth.merge.requestNotFound")
    return {
        "mergeRequestId": int(row["id"]),
        "secondaryUserId": str(row["secondary_user_id"]),
        "verificationToken": raw_token,
        "expiresAt": _iso_z(row["token_expires_at"]),
    }


async def verify_account_merge(
    engine: Any,
    *,
    primary_user_id: str,
    merge_request_id: int,
    verification_token: str | None,
    now_provider: NowProvider = _now_utc,
    token_verifier: TokenVerifier = verify_bcrypt_value,
) -> None:
    async with engine.begin() as connection:
        request = await _find_merge_request(connection, primary_user_id, merge_request_id)
        if request is None:
            raise AccountMergeError(404, "error.auth.merge.requestNotFound")
        if request["status"] != "PENDING":
            raise AccountMergeError(400, "error.auth.merge.requestNotPending")
        expires_at = request["token_expires_at"]
        if expires_at is None or _as_utc(expires_at) < now_provider():
            raise AccountMergeError(400, "error.auth.merge.tokenExpired")
        if not token_verifier(str(verification_token or ""), str(request["verification_token"] or "")):
            raise AccountMergeError(401, "error.auth.merge.invalidToken")

        primary_user = await _load_active_user(connection, primary_user_id, primary=True)
        secondary_user = await _load_user(connection, str(request["secondary_user_id"]))
        if secondary_user is None:
            raise AccountMergeError(404, "error.auth.merge.secondaryNotFound")
        _validate_merge_pair(primary_user, secondary_user)

        await connection.execute(
            text(
                """
                UPDATE account_merge_request
                SET status = 'VERIFIED'
                WHERE id = :merge_request_id
                """
            ),
            {"merge_request_id": merge_request_id},
        )


async def confirm_account_merge(
    engine: Any,
    *,
    primary_user_id: str,
    merge_request_id: int,
    now_provider: NowProvider = _now_utc,
) -> None:
    async with engine.begin() as connection:
        request = await _find_merge_request(connection, primary_user_id, merge_request_id)
        if request is None:
            raise AccountMergeError(404, "error.auth.merge.requestNotFound")
        if request["status"] != "VERIFIED":
            raise AccountMergeError(400, "error.auth.merge.requestNotVerified")

        primary_user = await _load_active_user(connection, primary_user_id, primary=True)
        secondary_user_id = str(request["secondary_user_id"])
        secondary_user = await _load_user(connection, secondary_user_id)
        if secondary_user is None:
            raise AccountMergeError(404, "error.auth.merge.secondaryNotFound")
        _validate_merge_pair(primary_user, secondary_user)

        await _migrate_identity_bindings(connection, primary_user_id, secondary_user_id)
        await _migrate_api_tokens(connection, primary_user_id, secondary_user_id)
        await _migrate_user_roles(connection, primary_user_id, secondary_user_id)
        await _migrate_namespace_memberships(connection, primary_user_id, secondary_user_id)
        await _migrate_local_credential(connection, primary_user_id, secondary_user_id)

        secondary_email = str(secondary_user.get("email") or "").strip()
        if not str(primary_user.get("email") or "").strip() and secondary_email:
            await connection.execute(
                text(
                    """
                    UPDATE user_account
                    SET email = :email,
                        updated_at = :updated_at
                    WHERE id = :primary_user_id
                    """
                ),
                {"email": secondary_email, "updated_at": now_provider(), "primary_user_id": primary_user_id},
            )

        now = now_provider()
        await connection.execute(
            text(
                """
                UPDATE user_account
                SET status = 'MERGED',
                    merged_to_user_id = :primary_user_id,
                    updated_at = :updated_at
                WHERE id = :secondary_user_id
                """
            ),
            {"primary_user_id": primary_user_id, "updated_at": now, "secondary_user_id": secondary_user_id},
        )
        await connection.execute(
            text(
                """
                UPDATE account_merge_request
                SET status = 'COMPLETED',
                    completed_at = :completed_at,
                    verification_token = NULL
                WHERE id = :merge_request_id
                """
            ),
            {"completed_at": now, "merge_request_id": merge_request_id},
        )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def _load_user(connection: Any, user_id: str) -> dict[str, Any] | None:
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


async def _load_active_user(connection: Any, user_id: str, *, primary: bool) -> dict[str, Any]:
    user = await _load_user(connection, user_id)
    if user is None:
        raise AccountMergeError(404, "error.auth.merge.primaryNotFound" if primary else "error.auth.merge.secondaryNotFound")
    if user["status"] != "ACTIVE":
        raise AccountMergeError(400, "error.auth.merge.primaryNotActive" if primary else "error.auth.merge.secondaryNotActive")
    return user


async def _resolve_secondary_user(connection: Any, identifier: str | None) -> dict[str, Any]:
    normalized = "" if identifier is None else identifier.strip()
    if not normalized:
        raise AccountMergeError(400, "error.auth.merge.identifierRequired")

    if ":" in normalized:
        parts = normalized.split(":", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise AccountMergeError(400, "error.auth.merge.identifierInvalid")
        binding = (
            await connection.execute(
                text(
                    """
                    SELECT user_id
                    FROM identity_binding
                    WHERE provider_code = :provider_code
                      AND subject = :subject
                    LIMIT 1
                    """
                ),
                {"provider_code": parts[0], "subject": parts[1]},
            )
        ).mappings().one_or_none()
        if binding is None:
            raise AccountMergeError(404, "error.auth.merge.secondaryNotFound")
        secondary = await _load_user(connection, str(binding["user_id"]))
    else:
        credential = (
            await connection.execute(
                text(
                    """
                    SELECT user_id
                    FROM local_credential
                    WHERE LOWER(username) = :username
                    LIMIT 1
                    """
                ),
                {"username": normalized.lower()},
            )
        ).mappings().one_or_none()
        if credential is None:
            raise AccountMergeError(404, "error.auth.merge.secondaryNotFound")
        secondary = await _load_user(connection, str(credential["user_id"]))

    if secondary is None:
        raise AccountMergeError(404, "error.auth.merge.secondaryNotFound")
    return secondary


def _validate_merge_pair(primary_user: dict[str, Any], secondary_user: dict[str, Any]) -> None:
    if primary_user["id"] == secondary_user["id"]:
        raise AccountMergeError(400, "error.auth.merge.sameAccount")
    if secondary_user["status"] != "ACTIVE":
        raise AccountMergeError(400, "error.auth.merge.secondaryNotActive")


async def _find_local_credential_by_user_id(connection: Any, user_id: str) -> dict[str, Any] | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT id, user_id, username, password_hash
                FROM local_credential
                WHERE user_id = :user_id
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


async def _find_merge_request(connection: Any, primary_user_id: str, merge_request_id: int) -> dict[str, Any] | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT id, primary_user_id, secondary_user_id, status, verification_token, token_expires_at, completed_at
                FROM account_merge_request
                WHERE id = :merge_request_id
                  AND primary_user_id = :primary_user_id
                LIMIT 1
                """
            ),
            {"merge_request_id": merge_request_id, "primary_user_id": primary_user_id},
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


async def _migrate_identity_bindings(connection: Any, primary_user_id: str, secondary_user_id: str) -> None:
    rows = (
        await connection.execute(
            text(
                """
                SELECT id, user_id, provider_code, subject, login_name
                FROM identity_binding
                WHERE user_id = :secondary_user_id
                """
            ),
            {"secondary_user_id": secondary_user_id},
        )
    ).mappings().all()
    for row in rows:
        await connection.execute(
            text("UPDATE identity_binding SET user_id = :primary_user_id, updated_at = :updated_at WHERE id = :binding_id"),
            {"primary_user_id": primary_user_id, "updated_at": _now_utc(), "binding_id": row["id"]},
        )


async def _migrate_api_tokens(connection: Any, primary_user_id: str, secondary_user_id: str) -> None:
    rows = (
        await connection.execute(
            text(
                """
                SELECT id, subject_type, subject_id, user_id
                FROM api_token
                WHERE user_id = :secondary_user_id
                """
            ),
            {"secondary_user_id": secondary_user_id},
        )
    ).mappings().all()
    for row in rows:
        subject_id = primary_user_id if row["subject_type"] == "USER" else row["subject_id"]
        await connection.execute(
            text(
                """
                UPDATE api_token
                SET user_id = :primary_user_id,
                    subject_id = :subject_id
                WHERE id = :token_id
                """
            ),
            {"primary_user_id": primary_user_id, "subject_id": subject_id, "token_id": row["id"]},
        )


async def _migrate_user_roles(connection: Any, primary_user_id: str, secondary_user_id: str) -> None:
    primary_rows = await _find_role_bindings(connection, primary_user_id)
    primary_codes = {str(row["code"]) for row in primary_rows}
    secondary_rows = await _find_role_bindings(connection, secondary_user_id)
    for row in secondary_rows:
        code = str(row["code"])
        if code not in primary_codes:
            await connection.execute(
                text(
                    """
                    INSERT INTO user_role_binding (user_id, role_id)
                    VALUES (:primary_user_id, :role_id)
                    """
                ),
                {"primary_user_id": primary_user_id, "role_id": row["role_id"]},
            )
            primary_codes.add(code)
        await connection.execute(
            text("DELETE FROM user_role_binding WHERE id = :binding_id"),
            {"binding_id": row["id"]},
        )


async def _find_role_bindings(connection: Any, user_id: str) -> list[dict[str, Any]]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT urb.id, urb.user_id, urb.role_id, r.code
                FROM user_role_binding urb
                JOIN role r ON r.id = urb.role_id
                WHERE urb.user_id = :user_id
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def _migrate_namespace_memberships(connection: Any, primary_user_id: str, secondary_user_id: str) -> None:
    secondary_rows = (
        await connection.execute(
            text(
                """
                SELECT id, namespace_id, user_id, role
                FROM namespace_member
                WHERE user_id = :user_id
                """
            ),
            {"user_id": secondary_user_id},
        )
    ).mappings().all()
    for secondary in secondary_rows:
        existing = (
            await connection.execute(
                text(
                    """
                    SELECT id, namespace_id, user_id, role
                    FROM namespace_member
                    WHERE namespace_id = :namespace_id
                      AND user_id = :primary_user_id
                    LIMIT 1
                    """
                ),
                {"namespace_id": secondary["namespace_id"], "primary_user_id": primary_user_id},
            )
        ).mappings().one_or_none()
        if existing is not None:
            if NAMESPACE_ROLE_ORDER[str(secondary["role"])] > NAMESPACE_ROLE_ORDER[str(existing["role"])]:
                await connection.execute(
                    text("UPDATE namespace_member SET role = :role, updated_at = :updated_at WHERE id = :member_id"),
                    {"role": secondary["role"], "updated_at": _now_utc(), "member_id": existing["id"]},
                )
            await connection.execute(
                text(
                    """
                    DELETE FROM namespace_member
                    WHERE namespace_id = :namespace_id
                      AND user_id = :secondary_user_id
                    """
                ),
                {"namespace_id": secondary["namespace_id"], "secondary_user_id": secondary_user_id},
            )
        else:
            await connection.execute(
                text("UPDATE namespace_member SET user_id = :primary_user_id, updated_at = :updated_at WHERE id = :member_id"),
                {"primary_user_id": primary_user_id, "updated_at": _now_utc(), "member_id": secondary["id"]},
            )


async def _migrate_local_credential(connection: Any, primary_user_id: str, secondary_user_id: str) -> None:
    primary_credential = await _find_local_credential_by_user_id(connection, primary_user_id)
    secondary_credential = await _find_local_credential_by_user_id(connection, secondary_user_id)
    if primary_credential is not None and secondary_credential is not None:
        raise AccountMergeError(409, "error.auth.merge.localCredentialConflict")
    if secondary_credential is not None:
        await connection.execute(
            text("UPDATE local_credential SET user_id = :primary_user_id, updated_at = :updated_at WHERE id = :credential_id"),
            {
                "primary_user_id": primary_user_id,
                "updated_at": _now_utc(),
                "credential_id": secondary_credential["id"],
            },
        )

from __future__ import annotations

from datetime import UTC, datetime
import json
import re
from typing import Any

from sqlalchemy import text

from app.core.config import parse_bool


DISPLAY_NAME_PATTERN = re.compile(r"^[\u4e00-\u9fa5a-zA-Z0-9_ -]+$")
DEFAULT_FIELD_POLICIES = {
    "displayName": {"editable": True, "requiresReview": True},
    "email": {"editable": False, "requiresReview": False},
}


class UserProfileError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _now(value: datetime | None) -> datetime:
    return value or datetime.now(UTC)


def _db_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _json_map(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return {str(key): str(item) for key, item in value.items() if item is not None}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return {str(key): str(item) for key, item in parsed.items() if item is not None}
    return {}


def _json_dumps(value: dict[str, Any]) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _field_policies(*, human_review: bool) -> dict[str, dict[str, bool]]:
    return {
        "displayName": {"editable": True, "requiresReview": human_review},
        "email": DEFAULT_FIELD_POLICIES["email"].copy(),
    }


def _validate_display_name(payload: dict[str, Any] | None) -> dict[str, str]:
    if payload is None or payload.get("displayName") is None:
        raise UserProfileError("error.profile.noChanges", status_code=400)

    display_name = str(payload.get("displayName")).strip()
    if len(display_name) < 2 or len(display_name) > 32:
        raise UserProfileError("error.profile.displayName.length", status_code=400)
    if DISPLAY_NAME_PATTERN.fullmatch(display_name) is None:
        raise UserProfileError("error.profile.displayName.pattern", status_code=400)
    return {"displayName": display_name}


async def _read_active_user(connection: Any, user_id: str) -> dict[str, Any] | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT id, display_name, email, avatar_url, status
                FROM user_account
                WHERE id = :user_id
                  AND status = 'ACTIVE'
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


async def _read_latest_pending_or_rejected(connection: Any, user_id: str) -> dict[str, Any] | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT id, user_id, changes, old_values, status, review_comment, created_at
                FROM profile_change_request
                WHERE user_id = :user_id
                  AND status IN ('PENDING', 'REJECTED')
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


def _pending_response(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "status": row.get("status"),
        "changes": _json_map(row.get("changes")),
        "reviewComment": row.get("review_comment"),
        "createdAt": row.get("created_at").isoformat() if row.get("created_at") is not None else None,
    }


async def get_user_profile(engine: Any, user_id: str, *, human_review: bool = True) -> dict[str, Any]:
    async with engine.connect() as connection:
        user = await _read_active_user(connection, user_id)
        if user is None:
            raise UserProfileError("error.auth.required", status_code=401)
        pending_changes = _pending_response(await _read_latest_pending_or_rejected(connection, user_id))

    display_name = user.get("display_name")
    avatar_url = user.get("avatar_url")
    if pending_changes is not None and pending_changes["status"] == "PENDING":
        changes = pending_changes["changes"]
        display_name = changes.get("displayName", display_name)
        avatar_url = changes.get("avatarUrl", avatar_url)

    return {
        "displayName": display_name,
        "avatarUrl": avatar_url,
        "email": user.get("email"),
        "pendingChanges": pending_changes,
        "fieldPolicies": _field_policies(human_review=human_review),
    }


async def _cancel_pending_requests(connection: Any, user_id: str) -> None:
    await connection.execute(
        text(
            """
            UPDATE profile_change_request
            SET status = :status
            WHERE user_id = :user_id
              AND status = 'PENDING'
            """
        ),
        {"status": "CANCELLED", "user_id": user_id},
    )


async def _insert_change_request(
    connection: Any,
    *,
    user_id: str,
    changes: dict[str, str],
    old_values: dict[str, str],
    status: str,
    machine_result: str,
    machine_reason: str | None,
    created_at: datetime,
) -> None:
    await connection.execute(
        text(
            """
            INSERT INTO profile_change_request (
                user_id, changes, old_values, status, machine_result, machine_reason, created_at
            )
            VALUES (
                :user_id, CAST(:changes AS jsonb), CAST(:old_values AS jsonb), :status,
                :machine_result, :machine_reason, :created_at
            )
            """
        ),
        {
            "user_id": user_id,
            "changes": _json_dumps(changes),
            "old_values": _json_dumps(old_values),
            "status": status,
            "machine_result": machine_result,
            "machine_reason": machine_reason,
            "created_at": created_at,
        },
    )


async def _write_profile_update_audit(
    connection: Any,
    *,
    user_id: str,
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
    changes: dict[str, str],
    old_values: dict[str, str],
    created_at: datetime,
) -> None:
    await connection.execute(
        text(
            """
            INSERT INTO audit_log (
                actor_user_id, action, target_type, target_id, request_id,
                client_ip, user_agent, detail_json, created_at
            )
            VALUES (
                :actor_user_id, :action, :target_type, :target_id, :request_id,
                :client_ip, :user_agent, CAST(:detail_json AS jsonb), :created_at
            )
            """
        ),
        {
            "actor_user_id": user_id,
            "action": "PROFILE_UPDATE",
            "target_type": "USER",
            "target_id": None,
            "request_id": request_id,
            "client_ip": client_ip,
            "user_agent": user_agent,
            "detail_json": _json_dumps({"changes": changes, "oldValues": old_values}),
            "created_at": created_at,
        },
    )


async def update_user_profile(
    engine: Any,
    *,
    user_id: str,
    payload: dict[str, Any] | None,
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
    human_review: bool = True,
    machine_review: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    changes = _validate_display_name(payload)
    timestamp = _db_timestamp(_now(now))
    machine_result = "PASS" if machine_review else "SKIPPED"

    async with engine.begin() as connection:
        user = await _read_active_user(connection, user_id)
        if user is None:
            raise UserProfileError(f"User not found: {user_id}", status_code=400)

        old_values = {"displayName": str(user.get("display_name"))}
        if human_review:
            await _cancel_pending_requests(connection, user_id)
            await _insert_change_request(
                connection,
                user_id=user_id,
                changes=changes,
                old_values=old_values,
                status="PENDING",
                machine_result=machine_result,
                machine_reason=None,
                created_at=timestamp,
            )
            return {"status": "PENDING_REVIEW", "message": "response.profile.pendingReview"}

        await connection.execute(
            text(
                """
                UPDATE user_account
                SET display_name = :display_name,
                    updated_at = :updated_at
                WHERE id = :user_id
                """
            ),
            {"display_name": changes["displayName"], "updated_at": timestamp, "user_id": user_id},
        )
        await _insert_change_request(
            connection,
            user_id=user_id,
            changes=changes,
            old_values=old_values,
            status="APPROVED",
            machine_result=machine_result,
            machine_reason=None,
            created_at=timestamp,
        )
        await _write_profile_update_audit(
            connection,
            user_id=user_id,
            request_id=request_id,
            client_ip=client_ip,
            user_agent=user_agent,
            changes=changes,
            old_values=old_values,
            created_at=timestamp,
        )
    return {"status": "APPLIED", "message": "response.profile.updated"}


def profile_human_review_enabled(configured: bool | None = None) -> bool:
    if configured is not None:
        return configured
    import os

    value = os.getenv("SKILLHUB_PROFILE_HUMAN_REVIEW_ENABLED")
    return True if value is None else parse_bool(value)


def profile_machine_review_enabled(configured: bool | None = None) -> bool:
    if configured is not None:
        return configured
    import os

    value = os.getenv("SKILLHUB_PROFILE_MACHINE_REVIEW_ENABLED")
    return True if value is None else parse_bool(value)

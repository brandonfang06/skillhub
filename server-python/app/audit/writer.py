from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import insert

from app.db.models import AuditLog


async def write_audit_log(
    connection: Any,
    *,
    actor_user_id: str,
    action: str,
    target_type: str,
    target_id: int,
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
    detail: dict[str, Any],
    created_at: datetime,
    detail_json: str | None = None,
) -> None:
    stored_detail = detail_json if detail_json is not None else (detail or None)
    await connection.execute(
        insert(AuditLog),
        {
            "actor_user_id": actor_user_id,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "request_id": request_id,
            "client_ip": client_ip,
            "user_agent": user_agent,
            "detail_json": stored_detail,
            "created_at": created_at,
        },
    )

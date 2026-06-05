from datetime import UTC, datetime
from typing import Any

from fastapi import Request


def ok(message_code: str, data: Any, request: Request) -> dict[str, Any]:
    return {
        "code": 0,
        "msg": message_code,
        "data": data,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "requestId": request.state.request_id,
    }


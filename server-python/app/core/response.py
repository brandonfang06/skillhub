from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from app.auth.policy import ApiTokenAccessDenied


def ok(message_code: str, data: Any, request: Request) -> dict[str, Any]:
    return {
        "code": 0,
        "msg": message_code,
        "data": data,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "requestId": request.state.request_id,
    }


async def api_token_access_denied_response(
    request: Request,
    exc: ApiTokenAccessDenied,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.status_code,
            "msg": exc.message_code,
            "data": {"args": list(exc.message_args)},
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "requestId": request.state.request_id,
        },
    )


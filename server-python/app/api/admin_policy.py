from __future__ import annotations

from fastapi import HTTPException, Request

from app.api.auth import _read_current_user_or_401


async def reject_bearer_api_token_for_admin_route(
    request: Request,
    mock_user_id: str | None,
    authorization: str | None,
) -> None:
    if mock_user_id is not None and mock_user_id.strip() != "":
        return
    if authorization is None or not authorization.startswith("Bearer "):
        return
    user = dict(await _read_current_user_or_401(request, None, authorization))
    if user.get("oauthProvider") == "api_token":
        raise HTTPException(status_code=403, detail=f"API token cannot access endpoint: {request.url.path}")

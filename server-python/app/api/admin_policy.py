from __future__ import annotations

from fastapi import Request

from app.auth.context import has_bearer_authorization, resolve_current_user_or_401
from app.auth.policy import reject_api_token_principal_for_route


async def reject_bearer_api_token_for_admin_route(
    request: Request,
    mock_user_id: str | None,
    authorization: str | None,
) -> None:
    if mock_user_id is not None and mock_user_id.strip() != "":
        return
    if not has_bearer_authorization(authorization):
        return
    user = dict(await resolve_current_user_or_401(request, None, authorization))
    reject_api_token_principal_for_route(user, request.url.path)

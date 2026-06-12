from __future__ import annotations

from collections.abc import Awaitable
from inspect import isawaitable
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.auth.account_merge import (
    AccountMergeError,
    confirm_account_merge,
    initiate_account_merge,
    verify_account_merge,
)
from app.auth.context import resolve_current_user_or_401
from app.core.response import ok

router = APIRouter()


async def _resolve_result(result: Any | Awaitable[Any]) -> Any:
    if isawaitable(result):
        return await result
    return result


async def _current_user_id(request: Request, mock_user_id: str | None) -> str:
    user = await resolve_current_user_or_401(request, mock_user_id, None)
    return str(user["userId"])


@router.post("/api/v1/account/merge/initiate")
async def initiate_account_merge_route(
    request: Request,
    payload: dict[str, Any],
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _current_user_id(request, mock_user_id)
    initiator = getattr(request.app.state, "account_merge_initiator", None)
    try:
        data = await _resolve_result(
            initiator(user_id, payload)
            if initiator is not None
            else initiate_account_merge(
                request.app.state.db_engine,
                primary_user_id=user_id,
                secondary_identifier=payload.get("secondaryIdentifier"),
            )
        )
    except AccountMergeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("response.success.created", data, request)


@router.post("/api/v1/account/merge/verify")
async def verify_account_merge_route(
    request: Request,
    payload: dict[str, Any],
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _current_user_id(request, mock_user_id)
    verifier = getattr(request.app.state, "account_merge_verifier", None)
    try:
        await _resolve_result(
            verifier(user_id, payload)
            if verifier is not None
            else verify_account_merge(
                request.app.state.db_engine,
                primary_user_id=user_id,
                merge_request_id=int(payload.get("mergeRequestId")),
                verification_token=payload.get("verificationToken"),
            )
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="error.auth.merge.requestNotFound") from exc
    except AccountMergeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("response.success.updated", {"message": "Account merge verified"}, request)


@router.post("/api/v1/account/merge/confirm")
async def confirm_account_merge_route(
    request: Request,
    payload: dict[str, Any],
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
) -> dict[str, Any]:
    user_id = await _current_user_id(request, mock_user_id)
    confirmer = getattr(request.app.state, "account_merge_confirmer", None)
    try:
        await _resolve_result(
            confirmer(user_id, payload)
            if confirmer is not None
            else confirm_account_merge(
                request.app.state.db_engine,
                primary_user_id=user_id,
                merge_request_id=int(payload.get("mergeRequestId")),
            )
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="error.auth.merge.requestNotFound") from exc
    except AccountMergeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ok("response.success.updated", {"message": "Account merge completed"}, request)

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Path, Query, Request, Response
from pydantic import BaseModel

from app.auth.context import resolve_current_user_or_401
from app.core.response import ok
from app.review.context_repository import read_version_review_context
from app.review.query import ReviewQueryError

router = APIRouter()


class NamespaceReviewer(BaseModel):
    userId: str
    displayName: str
    loginName: str | None = None


class VersionReviewContext(BaseModel):
    skillId: int
    version: str
    namespace: str
    namespaceType: str
    versionStatus: str
    reviewTaskId: int | None
    reviewStatus: str | None
    waitingReason: Literal['HUMAN_REVIEW', 'SCANNING', 'SCAN_FAILED', 'SCAN_PARTIAL', 'NAMESPACE_UNAVAILABLE', 'NOT_SUBMITTED', 'APPROVED', 'REJECTED']
    submittedAt: datetime | None
    reviewedAt: datetime | None
    reviewedByName: str | None
    reviewComment: str | None
    reviewers: list[NamespaceReviewer]
    total: int
    page: int
    size: int


class ReviewContextEnvelope(BaseModel):
    code: int
    msg: str
    data: VersionReviewContext
    timestamp: str
    requestId: str


@router.get('/api/v1/reviews/skills/{skill_id}/versions/{version}/context', response_model=ReviewContextEnvelope)
@router.get('/api/web/reviews/skills/{skill_id}/versions/{version}/context', response_model=ReviewContextEnvelope)
async def version_review_context_route(
    request: Request, response: Response,
    skill_id: int = Path(ge=1), version: str = Path(min_length=1, max_length=64),
    page: int = Query(0, ge=0, le=10000), size: int = Query(20, ge=1, le=100),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user = await resolve_current_user_or_401(request, None, authorization)
    try:
        async with request.app.state.db_engine.connect() as connection:
            data = await read_version_review_context(
                connection, skill_id=skill_id, version=version,
                user_id=str(user['userId']), page=page, size=size,
            )
    except ReviewQueryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    response.headers['Cache-Control'] = 'private, no-store'
    return ok('response.success', data, request)

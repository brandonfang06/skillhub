from fastapi import APIRouter, Request

from app.core.response import ok

router = APIRouter()


@router.get("/api/v1/health")
def health(request: Request) -> dict[str, object]:
    return ok("response.success.health", {"message": "UP"}, request)


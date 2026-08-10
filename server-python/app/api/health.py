from fastapi import APIRouter, Request, Response

from app.core.metrics import render_prometheus_metrics
from app.core.response import ok

router = APIRouter()


@router.get("/api/v1/health")
def health(request: Request) -> dict[str, object]:
    return ok("response.success.health", {"message": "UP"}, request)


@router.get("/api/v1/metrics/prometheus")
def prometheus_metrics() -> Response:
    return Response(content=render_prometheus_metrics(), media_type="text/plain; version=0.0.4; charset=utf-8")

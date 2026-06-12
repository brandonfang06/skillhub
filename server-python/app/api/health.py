from fastapi import APIRouter, Request, Response

from app.core.response import ok

router = APIRouter()


@router.get("/api/v1/health")
def health(request: Request) -> dict[str, object]:
    return ok("response.success.health", {"message": "UP"}, request)


@router.get("/api/v1/metrics/prometheus")
def prometheus_metrics() -> Response:
    body = "\n".join(
        [
            "# HELP skillhub_python_backend_up SkillHub Python backend availability.",
            "# TYPE skillhub_python_backend_up gauge",
            "skillhub_python_backend_up 1",
            "",
        ]
    )
    return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")

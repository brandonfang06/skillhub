from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.request_id import RequestIdMiddleware


def create_app() -> FastAPI:
    app = FastAPI(title="SkillHub Python Backend")
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health_router)
    return app


app = create_app()


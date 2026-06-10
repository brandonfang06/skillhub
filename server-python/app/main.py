from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.admin_audit_logs import router as admin_audit_logs_router
from app.api.admin_skills import router as admin_skills_router
from app.api.admin_labels import router as admin_labels_router
from app.api.admin_review_reports import router as admin_review_reports_router
from app.api.admin_users import router as admin_users_router
from app.api.auth import router as auth_router
from app.api.governance import router as governance_router
from app.api.health import router as health_router
from app.api.labels import router as labels_router
from app.api.lifecycle import router as lifecycle_router
from app.api.local_auth import router as local_auth_router
from app.api.notifications import router as notifications_router
from app.api.namespaces import router as namespaces_router
from app.api.promotions import router as promotions_router
from app.api.publish import router as publish_router
from app.api.reviews import router as reviews_router
from app.api.skills import router as skills_router
from app.api.social import router as social_router
from app.api.tokens import router as tokens_router
from app.api.well_known import router as well_known_router
from app.core.config import get_settings
from app.core.database import create_database_engine, dispose_database_engine
from app.core.request_id import RequestIdMiddleware
from app.publish.scan_daemon import create_scan_consumer_daemon


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.db_engine = create_database_engine(settings)
    app.state.scan_consumer_daemon = create_scan_consumer_daemon(settings, app.state.db_engine)
    if app.state.scan_consumer_daemon is not None:
        app.state.scan_consumer_daemon.start()
    try:
        yield
    finally:
        if app.state.scan_consumer_daemon is not None:
            await app.state.scan_consumer_daemon.shutdown()
        await dispose_database_engine(app.state.db_engine)


def create_app() -> FastAPI:
    app = FastAPI(title="SkillHub Python Backend", lifespan=lifespan)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(admin_audit_logs_router)
    app.include_router(admin_labels_router)
    app.include_router(admin_review_reports_router)
    app.include_router(admin_skills_router)
    app.include_router(admin_users_router)
    app.include_router(auth_router)
    app.include_router(governance_router)
    app.include_router(health_router)
    app.include_router(labels_router)
    app.include_router(lifecycle_router)
    app.include_router(local_auth_router)
    app.include_router(namespaces_router)
    app.include_router(notifications_router)
    app.include_router(promotions_router)
    app.include_router(publish_router)
    app.include_router(social_router)
    app.include_router(tokens_router)
    app.include_router(reviews_router)
    app.include_router(skills_router)
    app.include_router(well_known_router)
    return app


app = create_app()

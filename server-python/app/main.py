import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api.account_merge import router as account_merge_router
from app.api.admin_audit_logs import router as admin_audit_logs_router
from app.api.admin_skills import router as admin_skills_router
from app.api.admin_labels import router as admin_labels_router
from app.api.admin_review_reports import router as admin_review_reports_router
from app.api.admin_search import router as admin_search_router
from app.api.admin_users import router as admin_users_router
from app.api.auth import router as auth_router
from app.api.device_auth import router as device_auth_router
from app.api.download_analytics import router as download_analytics_router
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
from app.api.skill_reports import router as skill_reports_router
from app.api.security_audit import router as security_audit_router
from app.api.skills import router as skills_router
from app.api.social import router as social_router
from app.api.tokens import router as tokens_router
from app.api.user_profile import router as user_profile_router
from app.api.well_known import router as well_known_router
from app.bootstrap import initialize_bootstrap_admin
from app.builtin_skills import synchronize_builtin_skills
from app.core.config import get_settings
from app.core.database import create_database_engine, dispose_database_engine
from app.core.redis import create_redis_client
from app.core.request_id import RequestIdMiddleware
from app.notifications.fanout import NotificationFanoutManager
from app.publish.scan_daemon import create_scan_consumer_daemon


log = logging.getLogger(__name__)


async def run_builtin_skill_sync(engine: object, settings: object) -> None:
    try:
        await synchronize_builtin_skills(engine, settings)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log.warning("Built-in skill synchronization failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.settings = settings
    app.state.db_engine = create_database_engine(settings)
    app.state.redis_client = create_redis_client(settings)
    await initialize_bootstrap_admin(app.state.db_engine)
    app.state.builtin_skill_sync_task = asyncio.create_task(
        run_builtin_skill_sync(app.state.db_engine, settings)
    )
    app.state.notification_fanout = NotificationFanoutManager()
    app.state.scan_consumer_daemon = create_scan_consumer_daemon(settings, app.state.db_engine, app.state.redis_client)
    if app.state.scan_consumer_daemon is not None:
        app.state.scan_consumer_daemon.start()
    try:
        yield
    finally:
        app.state.builtin_skill_sync_task.cancel()
        with suppress(asyncio.CancelledError):
            await app.state.builtin_skill_sync_task
        if app.state.scan_consumer_daemon is not None:
            await app.state.scan_consumer_daemon.shutdown()
        await app.state.redis_client.aclose()
        await dispose_database_engine(app.state.db_engine)


def create_app() -> FastAPI:
    app = FastAPI(title="SkillHub Python Backend", lifespan=lifespan)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(account_merge_router)
    app.include_router(admin_audit_logs_router)
    app.include_router(admin_labels_router)
    app.include_router(admin_review_reports_router)
    app.include_router(admin_search_router)
    app.include_router(admin_skills_router)
    app.include_router(admin_users_router)
    app.include_router(auth_router)
    app.include_router(device_auth_router)
    app.include_router(download_analytics_router)
    app.include_router(governance_router)
    app.include_router(health_router)
    app.include_router(labels_router)
    app.include_router(social_router)
    app.include_router(lifecycle_router)
    app.include_router(local_auth_router)
    app.include_router(namespaces_router)
    app.include_router(notifications_router)
    app.include_router(promotions_router)
    app.include_router(publish_router)
    app.include_router(security_audit_router)
    app.include_router(skill_reports_router)
    app.include_router(tokens_router)
    app.include_router(user_profile_router)
    app.include_router(reviews_router)
    app.include_router(skills_router)
    app.include_router(well_known_router)
    return app


app = create_app()

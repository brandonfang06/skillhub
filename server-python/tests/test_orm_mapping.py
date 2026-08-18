from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app.db import models
from app.db.session import create_sessionmaker


EXPECTED_TABLES = {
    "skill",
    "skill_version",
    "review_task",
    "promotion_request",
    "namespace",
    "namespace_member",
    "user_account",
    "api_token",
    "audit_log",
}


def test_selective_orm_models_cover_mutation_aggregate_tables() -> None:
    assert set(models.Base.metadata.tables) == EXPECTED_TABLES


def test_selective_orm_models_define_expected_primary_keys_and_columns() -> None:
    expected = {
        "user_account": {"id", "status", "merged_to_user_id"},
        "namespace": {"id", "slug", "status", "created_by"},
        "namespace_member": {"id", "namespace_id", "user_id", "role"},
        "skill": {"id", "namespace_id", "slug", "status", "latest_version_id", "hidden", "subscription_count"},
        "skill_version": {
            "id",
            "skill_id",
            "version",
            "status",
            "requested_visibility",
            "bundle_ready",
            "download_ready",
            "yanked_at",
        },
        "review_task": {"id", "skill_version_id", "namespace_id", "status", "version", "submitted_by"},
        "promotion_request": {
            "id",
            "source_skill_id",
            "source_version_id",
            "target_namespace_id",
            "target_skill_id",
            "status",
            "version",
            "submitted_by",
        },
        "api_token": {"id", "subject_type", "subject_id", "user_id", "token_hash", "scope_json", "revoked_at"},
        "audit_log": {
            "id",
            "actor_user_id",
            "actor_service_principal_id",
            "action",
            "target_type",
            "target_id",
            "detail_json",
            "created_at",
        },
    }

    for table_name, columns in expected.items():
        table = models.Base.metadata.tables[table_name]
        assert {column.name for column in table.primary_key.columns} == {"id"}
        assert columns.issubset({column.name for column in table.columns})


def test_models_can_insert_and_load_basic_mutation_rows() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    created_at = datetime(2026, 6, 12, tzinfo=UTC)

    with engine.begin() as connection:
        models.Base.metadata.create_all(connection)

        with Session(bind=connection) as session:
            user = models.UserAccount(
                id="owner",
                display_name="Owner",
                email="owner@example.test",
                status="ACTIVE",
                created_at=created_at,
                updated_at=created_at,
            )
            namespace = models.Namespace(
                id=10,
                slug="team",
                display_name="Team",
                type="TEAM",
                status="ACTIVE",
                created_by=user.id,
                created_at=created_at,
                updated_at=created_at,
            )
            skill = models.Skill(
                id=20,
                namespace_id=namespace.id,
                slug="agent-helper",
                owner_id=user.id,
                visibility="PUBLIC",
                status="ACTIVE",
                created_by=user.id,
                created_at=created_at,
                updated_at=created_at,
            )
            version = models.SkillVersion(
                id=30,
                skill_id=skill.id,
                version="1.0.0",
                status="PUBLISHED",
                file_count=0,
                total_size=0,
                created_by=user.id,
                created_at=created_at,
                requested_visibility="PUBLIC",
            )
            review = models.ReviewTask(
                id=40,
                skill_version_id=version.id,
                namespace_id=namespace.id,
                status="PENDING",
                version=1,
                submitted_by=user.id,
                submitted_at=created_at,
            )

            session.add_all([user, namespace, skill, version, review])
            session.flush()

            loaded = session.scalars(select(models.SkillVersion).where(models.SkillVersion.id == version.id)).one()

    assert loaded.status == "PUBLISHED"
    assert loaded.requested_visibility == "PUBLIC"


def test_orm_session_factory_binds_existing_async_engine() -> None:
    class FakeAsyncEngine:
        pass

    fake_engine = FakeAsyncEngine()
    factory = create_sessionmaker(fake_engine)

    assert factory.kw["bind"] is fake_engine
    assert factory.kw["expire_on_commit"] is False


def test_only_db_models_module_declares_orm_classes() -> None:
    mapper_modules = {mapper.class_.__module__ for mapper in models.Base.registry.mappers}

    assert mapper_modules == {"app.db.models"}
    assert inspect(models.Skill).local_table.name == "skill"

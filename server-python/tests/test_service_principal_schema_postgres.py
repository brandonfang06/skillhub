from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine


TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")


@pytest.mark.anyio
@pytest.mark.skipif(TEST_DATABASE_URL is None, reason="SKILLHUB_TEST_DATABASE_URL is required")
async def test_service_principal_schema_enforces_identity_and_active_token_name() -> None:
    suffix = uuid4().hex[:12]
    admin_id = f"service-schema-admin-{suffix}"
    principal_id = f"svc_{suffix}"
    engine = create_async_engine(str(TEST_DATABASE_URL))

    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("INSERT INTO user_account (id, display_name) VALUES (:id, 'Service schema admin')"),
                {"id": admin_id},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO service_principal (
                        id, code, display_name, status, created_by_user_id
                    )
                    VALUES (:id, :code, 'GitLab Importer', 'ACTIVE', :admin_id)
                    """
                ),
                {"id": principal_id, "code": f"gitlab-{suffix}", "admin_id": admin_id},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO service_token (
                        service_principal_id, name, token_prefix, token_hash,
                        scope_json, created_by_user_id, expires_at
                    )
                    VALUES (
                        :principal_id, 'Production', 'st_test', :token_hash,
                        '["source:import"]'::jsonb, :admin_id, CURRENT_TIMESTAMP + INTERVAL '1 day'
                    )
                    """
                ),
                {"principal_id": principal_id, "token_hash": "a" * 64, "admin_id": admin_id},
            )
            with pytest.raises(IntegrityError):
                async with connection.begin_nested():
                    await connection.execute(
                        text(
                            """
                            INSERT INTO service_token (
                                service_principal_id, name, token_prefix, token_hash,
                                scope_json, created_by_user_id, expires_at
                            )
                            VALUES (
                                :principal_id, 'production', 'st_other', :token_hash,
                                '["source:import"]'::jsonb, :admin_id, CURRENT_TIMESTAMP + INTERVAL '1 day'
                            )
                            """
                        ),
                        {"principal_id": principal_id, "token_hash": "b" * 64, "admin_id": admin_id},
                    )
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM service_token WHERE service_principal_id = :id"),
                {"id": principal_id},
            )
            await connection.execute(text("DELETE FROM service_principal WHERE id = :id"), {"id": principal_id})
            await connection.execute(text("DELETE FROM user_account WHERE id = :id"), {"id": admin_id})
        await engine.dispose()

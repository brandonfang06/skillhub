from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.auth.service_tokens import read_service_token_principal
from app.service_accounts.service import (
    ServiceAccountError,
    create_service_principal,
    create_service_token,
    list_service_principals,
    list_service_tokens,
    revoke_service_token,
    rotate_service_token,
    update_service_principal,
)

TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")


@pytest.mark.anyio
@pytest.mark.skipif(
    TEST_DATABASE_URL is None, reason="SKILLHUB_TEST_DATABASE_URL is required"
)
async def test_service_token_lifecycle_is_independent_and_transactional() -> None:
    suffix = uuid4().hex[:12]
    admin_id = f"service-admin-{suffix}"
    engine = create_async_engine(str(TEST_DATABASE_URL))
    now = datetime.now(UTC)
    principal_id: str | None = None

    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO user_account (id, display_name) VALUES (:id, 'Service Admin')"
                ),
                {"id": admin_id},
            )

        principal = await create_service_principal(
            engine,
            code=f"gitlab-{suffix}",
            display_name="GitLab Importer",
            actor_user_id=admin_id,
            actor_platform_roles=["SUPER_ADMIN"],
            id_generator=lambda: f"svc_{suffix}",
            now=now,
        )
        principal_id = principal.id
        created = await create_service_token(
            engine,
            service_principal_id=principal.id,
            name="production",
            scopes=["source:import"],
            expires_at=(now + timedelta(days=30)).isoformat(),
            actor_user_id=admin_id,
            actor_platform_roles=["SUPER_ADMIN"],
            token_generator=lambda _: "first-secret",
            now=now,
        )
        assert created.token == "st_first-secret"
        resolved = await read_service_token_principal(engine, created.token)
        assert resolved is not None
        assert resolved.service_principal_id == principal.id
        assert resolved.token_scopes == ("source:import",)
        rows = await list_service_tokens(
            engine,
            service_principal_id=principal.id,
            actor_platform_roles=["SUPER_ADMIN"],
        )
        assert len(rows) == 1
        assert not hasattr(rows[0], "token")

        with pytest.raises(
            ServiceAccountError, match="error.serviceToken.rotateFailed"
        ):
            await rotate_service_token(
                engine,
                service_principal_id=principal.id,
                token_id=created.id,
                expires_at=(now + timedelta(days=60)).isoformat(),
                actor_user_id=admin_id,
                actor_platform_roles=["SUPER_ADMIN"],
                token_generator=lambda _: "first-secret",
                now=now + timedelta(seconds=1),
            )
        after_failed_rotation = await list_service_tokens(
            engine,
            service_principal_id=principal.id,
            actor_platform_roles=["SUPER_ADMIN"],
        )
        assert [row.id for row in after_failed_rotation] == [created.id]

        rotated = await rotate_service_token(
            engine,
            service_principal_id=principal.id,
            token_id=created.id,
            expires_at=None,
            actor_user_id=admin_id,
            actor_platform_roles=["SUPER_ADMIN"],
            token_generator=lambda _: "replacement-secret",
            now=now + timedelta(seconds=1),
        )
        assert rotated.token == "st_replacement-secret"
        assert rotated.expires_at is None
        assert await read_service_token_principal(engine, rotated.token) is not None
        states = await list_service_tokens(
            engine,
            service_principal_id=principal.id,
            actor_platform_roles=["SUPER_ADMIN"],
            include_revoked=True,
        )
        assert [(row.id, row.revoked_at is not None) for row in states] == [
            (rotated.id, False),
            (created.id, True),
        ]
        principals, total = await list_service_principals(
            engine,
            page=0,
            size=100,
            actor_platform_roles=["SUPER_ADMIN"],
        )
        summary = next(item for item in principals if item.id == principal.id)
        assert total >= 1
        assert summary.active_token_count == 1
        assert summary.nearest_token_expiry is None

        await update_service_principal(
            engine,
            service_principal_id=principal.id,
            display_name=None,
            status="DISABLED",
            actor_user_id=admin_id,
            actor_platform_roles=["SUPER_ADMIN"],
            now=now,
        )
        assert await read_service_token_principal(engine, rotated.token) is None
        with pytest.raises(
            ServiceAccountError, match="error.servicePrincipal.inactive"
        ):
            await create_service_token(
                engine,
                service_principal_id=principal.id,
                name="disabled",
                scopes=["source:import"],
                expires_at=(now + timedelta(days=10)).isoformat(),
                actor_user_id=admin_id,
                actor_platform_roles=["SUPER_ADMIN"],
                now=now,
            )

        await update_service_principal(
            engine,
            service_principal_id=principal.id,
            display_name=None,
            status="ACTIVE",
            actor_user_id=admin_id,
            actor_platform_roles=["SUPER_ADMIN"],
            now=now + timedelta(seconds=2),
        )
        assert await read_service_token_principal(engine, rotated.token) is not None

        await revoke_service_token(
            engine,
            service_principal_id=principal.id,
            token_id=rotated.id,
            actor_user_id=admin_id,
            actor_platform_roles=["SUPER_ADMIN"],
            now=now,
        )
        assert await read_service_token_principal(engine, rotated.token) is None
        await revoke_service_token(
            engine,
            service_principal_id=principal.id,
            token_id=rotated.id,
            actor_user_id=admin_id,
            actor_platform_roles=["SUPER_ADMIN"],
            now=now,
        )
    finally:
        async with engine.begin() as connection:
            if principal_id is not None:
                await connection.execute(
                    text(
                        "DELETE FROM audit_log WHERE detail_json ->> 'servicePrincipalId' = :id"
                    ),
                    {"id": principal_id},
                )
                await connection.execute(
                    text("DELETE FROM service_token WHERE service_principal_id = :id"),
                    {"id": principal_id},
                )
                await connection.execute(
                    text("DELETE FROM service_principal WHERE id = :id"),
                    {"id": principal_id},
                )
            await connection.execute(
                text("DELETE FROM user_account WHERE id = :id"), {"id": admin_id}
            )
        await engine.dispose()

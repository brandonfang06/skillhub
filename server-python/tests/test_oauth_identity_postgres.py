from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.auth.oauth import bind_oauth_principal

TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")


def _claims(
    subject: str,
    *,
    login: str,
    email: str,
    verified: bool,
) -> dict[str, object]:
    return {
        "subject": subject,
        "providerLogin": login,
        "email": email,
        "emailVerified": verified,
        "avatarUrl": "https://avatar.example.test/user.png",
        "extra": {"source": "postgres-test"},
    }


@pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="requires SKILLHUB_TEST_DATABASE_URL",
)
@pytest.mark.anyio
async def test_oauth_identity_trust_and_account_guards_in_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SKILLHUB_GLOBAL_NAMESPACE_AUTO_JOIN_ENABLED", raising=False)
    engine = create_async_engine(str(TEST_DATABASE_URL), pool_size=2, max_overflow=0)
    suffix = uuid4().hex[:12]
    provider = f"oauth-test-{suffix}"
    active_id = f"oauth-active-{suffix}"
    merged_id = f"oauth-merged-{suffix}"
    system_id = f"oauth-system-{suffix}"
    created_id: str | None = None
    auto_joined_id: str | None = None
    user_ids = [active_id, merged_id, system_id]
    try:
        async with engine.begin() as connection:
            for user_id, status, system_account in (
                (active_id, "ACTIVE", False),
                (merged_id, "MERGED", False),
                (system_id, "ACTIVE", True),
            ):
                await connection.execute(
                    text(
                        """
                        INSERT INTO user_account (
                            id, display_name, email, status, system_account,
                            merged_to_user_id
                        )
                        VALUES (
                            :user_id, :display_name, :email, :status,
                            :system_account, :merged_to_user_id
                        )
                        """
                    ),
                    {
                        "user_id": user_id,
                        "display_name": f"Original {user_id}",
                        "email": f"{user_id}@example.test",
                        "status": status,
                        "system_account": system_account,
                        "merged_to_user_id": (
                            active_id if status == "MERGED" else None
                        ),
                    },
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO identity_binding (
                            user_id, provider_code, subject, login_name
                        )
                        VALUES (:user_id, :provider, :subject, :login_name)
                        """
                    ),
                    {
                        "user_id": user_id,
                        "provider": provider,
                        "subject": user_id,
                        "login_name": f"original-{user_id}",
                    },
                )

        active_principal = await bind_oauth_principal(
            engine,
            {"id": provider},
            _claims(
                active_id,
                login="Renamed Active",
                email="untrusted@example.test",
                verified=False,
            ),
        )
        assert active_principal["email"] == f"{active_id}@example.test"

        created_principal = await bind_oauth_principal(
            engine,
            {"id": provider},
            _claims(
                f"new-{suffix}",
                login="New User",
                email="untrusted-new@example.test",
                verified=False,
            ),
        )
        created_id = str(created_principal["userId"])
        user_ids.append(created_id)
        assert created_principal["email"] == ""

        monkeypatch.setenv("SKILLHUB_GLOBAL_NAMESPACE_AUTO_JOIN_ENABLED", "true")
        auto_joined_principal = await bind_oauth_principal(
            engine,
            {"id": provider},
            _claims(
                f"auto-join-{suffix}",
                login="Auto Joined User",
                email="auto-joined@example.test",
                verified=True,
            ),
        )
        auto_joined_id = str(auto_joined_principal["userId"])
        user_ids.append(auto_joined_id)

        for user_id, message in (
            (merged_id, "error.auth.oauth.accountMerged"),
            (system_id, "error.auth.oauth.systemAccount"),
        ):
            with pytest.raises(PermissionError, match=message):
                await bind_oauth_principal(
                    engine,
                    {"id": provider},
                    _claims(
                        user_id,
                        login="Attacker Rename",
                        email="attacker@example.test",
                        verified=True,
                    ),
                )

        async with engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT id, display_name, email
                        FROM user_account
                        WHERE id = ANY(CAST(:user_ids AS varchar[]))
                        ORDER BY id
                        """
                    ),
                    {"user_ids": user_ids},
                )
            ).mappings().all()
        by_id = {str(row["id"]): dict(row) for row in rows}
        assert by_id[active_id]["display_name"] == "Renamed Active"
        assert by_id[active_id]["email"] == f"{active_id}@example.test"
        assert by_id[created_id]["email"] is None
        assert by_id[auto_joined_id]["email"] == "auto-joined@example.test"
        assert by_id[merged_id]["display_name"] == f"Original {merged_id}"
        assert by_id[system_id]["display_name"] == f"Original {system_id}"

        async with engine.connect() as connection:
            global_members = (
                await connection.execute(
                    text(
                        """
                        SELECT nm.user_id
                        FROM namespace_member nm
                        JOIN namespace n ON n.id = nm.namespace_id
                        WHERE n.slug = 'global'
                          AND nm.user_id = ANY(CAST(:user_ids AS varchar[]))
                        ORDER BY nm.user_id
                        """
                    ),
                    {"user_ids": [created_id, auto_joined_id]},
                )
            ).scalars().all()
        assert list(global_members) == [auto_joined_id]
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM namespace_member WHERE user_id = ANY(CAST(:user_ids AS varchar[]))"),
                {"user_ids": user_ids},
            )
            await connection.execute(
                text("DELETE FROM identity_binding WHERE user_id = ANY(CAST(:user_ids AS varchar[]))"),
                {"user_ids": user_ids},
            )
            await connection.execute(
                text("DELETE FROM user_account WHERE id = ANY(CAST(:user_ids AS varchar[]))"),
                {"user_ids": user_ids},
            )
        await engine.dispose()

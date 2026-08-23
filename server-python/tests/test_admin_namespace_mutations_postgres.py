from __future__ import annotations

import asyncio
import logging
import os
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.admin_namespace import mutations
from app.admin_namespace.mutation_repository import AdminNamespaceMutationError
from app.namespace import mutations as namespace_mutations
from app.namespace.members import (
    NamespaceMemberReadError,
    transfer_namespace_ownership,
)
from app.namespace.mutations import unfreeze_namespace, update_namespace

TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")


def _context(suffix: str) -> dict[str, str | None]:
    return {
        "request_id": f"request-{suffix}",
        "client_ip": "127.0.0.7",
        "user_agent": "admin-namespace-test",
    }


async def _seed(engine: Any, suffix: str) -> dict[str, Any]:
    users = {
        "admin": f"admin-{suffix}",
        "owner": f"owner-{suffix}",
        "member": f"member-{suffix}",
        "candidate": f"candidate-{suffix}",
        "candidate2": f"candidate2-{suffix}",
        "inactive": f"inactive-{suffix}",
    }
    slugs = {
        "active": f"admin-write-{suffix}",
        "frozen": f"admin-frozen-{suffix}",
        "archived": f"admin-archived-{suffix}",
        "global": f"admin-global-{suffix}",
    }
    async with engine.begin() as connection:
        for key, user_id in users.items():
            await connection.execute(
                text(
                    """
                    INSERT INTO user_account (id, display_name, email, status)
                    VALUES (:id, :name, :email, :status)
                    """
                ),
                {
                    "id": user_id,
                    "name": key.title(),
                    "email": f"{user_id}@example.test",
                    "status": "DISABLED" if key == "inactive" else "ACTIVE",
                },
            )
        for key, slug in slugs.items():
            row = (
                await connection.execute(
                    text(
                        """
                        INSERT INTO namespace (slug, display_name, type, status, created_by)
                        VALUES (:slug, :name, :type, :status, :owner)
                        RETURNING id
                        """
                    ),
                    {
                        "slug": slug,
                        "name": key.title(),
                        "status": "ACTIVE" if key == "global" else key.upper(),
                        "type": "GLOBAL" if key == "global" else "TEAM",
                        "owner": users["owner"],
                    },
                )
            ).scalar_one()
            if key == "active":
                active_id = int(row)
                await connection.execute(
                    text(
                        """
                        INSERT INTO namespace_member (namespace_id, user_id, role)
                        VALUES (:id, :owner, 'OWNER'), (:id, :member, 'MEMBER')
                        """
                    ),
                    {
                        "id": active_id,
                        "owner": users["owner"],
                        "member": users["member"],
                    },
                )
    return {"users": users, "slugs": slugs, "active_id": active_id}


async def _cleanup(engine: Any, seeded: dict[str, Any]) -> None:
    async with engine.begin() as connection:
        rows = (
            (
                await connection.execute(
                    text("SELECT id FROM namespace WHERE slug = ANY(:slugs)"),
                    {"slugs": list(seeded["slugs"].values())},
                )
            )
            .scalars()
            .all()
        )
        if rows:
            await connection.execute(
                text(
                    "DELETE FROM audit_log WHERE target_type = 'NAMESPACE' AND target_id = ANY(:ids)"
                ),
                {"ids": list(rows)},
            )
            await connection.execute(
                text("DELETE FROM namespace_member WHERE namespace_id = ANY(:ids)"),
                {"ids": list(rows)},
            )
            await connection.execute(
                text("DELETE FROM namespace WHERE id = ANY(:ids)"), {"ids": list(rows)}
            )
        await connection.execute(
            text("DELETE FROM user_account WHERE id = ANY(:ids)"),
            {"ids": list(seeded["users"].values())},
        )


async def _audit_rows(engine: Any, namespace_id: int) -> list[dict[str, Any]]:
    async with engine.connect() as connection:
        rows = (
            (
                await connection.execute(
                    text(
                        """
                    SELECT actor_user_id, action, request_id, client_ip, user_agent, detail_json
                    FROM audit_log WHERE target_type = 'NAMESPACE' AND target_id = :id
                    ORDER BY id
                    """
                    ),
                    {"id": namespace_id},
                )
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


async def _create_race_namespace(
    engine: Any,
    seeded: dict[str, Any],
    *,
    key: str,
    suffix: str,
    status: str = "ACTIVE",
) -> tuple[str, int]:
    slug = f"admin-race-{key}-{suffix}"
    seeded["slugs"][key] = slug
    users = seeded["users"]
    async with engine.begin() as connection:
        namespace_id = int(
            (
                await connection.execute(
                    text(
                        """
                        INSERT INTO namespace (slug, display_name, type, status, created_by)
                        VALUES (:slug, :display_name, 'TEAM', :status, :owner)
                        RETURNING id
                        """
                    ),
                    {
                        "slug": slug,
                        "display_name": f"Race {key} {suffix}",
                        "status": status,
                        "owner": users["owner"],
                    },
                )
            ).scalar_one()
        )
        await connection.execute(
            text(
                """
                INSERT INTO namespace_member (namespace_id, user_id, role)
                VALUES
                  (:id, :owner, 'OWNER'),
                  (:id, :member, 'ADMIN'),
                  (:id, :candidate, 'ADMIN')
                """
            ),
            {
                "id": namespace_id,
                "owner": users["owner"],
                "member": users["member"],
                "candidate": users["candidate"],
            },
        )
    return slug, namespace_id


async def _cross_surface_outcome(awaitable: Any) -> str:
    try:
        await awaitable
        return "success"
    except (AdminNamespaceMutationError, NamespaceMemberReadError) as exc:
        return str(exc)


@pytest.mark.skipif(
    TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL"
)
@pytest.mark.anyio
async def test_admin_member_mutations_enforce_invariants_and_write_atomic_audits() -> (
    None
):
    suffix = uuid4().hex
    engine = create_async_engine(str(TEST_DATABASE_URL))
    seeded = await _seed(engine, suffix)
    users, slugs = seeded["users"], seeded["slugs"]
    context = _context(suffix)
    try:
        added = await mutations.add_member(
            engine,
            slug=slugs["active"],
            member_user_id=users["candidate"],
            role="MEMBER",
            actor_user_id=users["admin"],
            **context,
        )
        assert added["userId"] == users["candidate"]
        updated = await mutations.update_member_role(
            engine,
            slug=slugs["active"],
            member_user_id=users["candidate"],
            role="ADMIN",
            actor_user_id=users["admin"],
            **context,
        )
        assert updated["role"] == "ADMIN"
        replayed = await mutations.update_member_role(
            engine,
            slug=slugs["active"],
            member_user_id=users["candidate"],
            role="ADMIN",
            actor_user_id=users["admin"],
            **context,
        )
        assert replayed["role"] == "ADMIN"
        await mutations.remove_member(
            engine,
            slug=slugs["active"],
            member_user_id=users["candidate"],
            actor_user_id=users["admin"],
            **context,
        )

        for call in (
            mutations.add_member(
                engine,
                slug=slugs["active"],
                member_user_id=users["inactive"],
                role="MEMBER",
                actor_user_id=users["admin"],
                **context,
            ),
            mutations.add_member(
                engine,
                slug=slugs["frozen"],
                member_user_id=users["candidate"],
                role="MEMBER",
                actor_user_id=users["admin"],
                **context,
            ),
            mutations.remove_member(
                engine,
                slug=slugs["active"],
                member_user_id=users["owner"],
                actor_user_id=users["admin"],
                **context,
            ),
        ):
            with pytest.raises(AdminNamespaceMutationError):
                await call

        with pytest.raises(
            AdminNamespaceMutationError, match="error.namespace.system.immutable"
        ):
            await mutations.add_member(
                engine,
                slug=slugs["global"],
                member_user_id=users["candidate"],
                role="OWNER",
                actor_user_id=users["admin"],
                **context,
            )

        rows = await _audit_rows(engine, seeded["active_id"])
        assert [row["action"] for row in rows] == [
            "ADD_NAMESPACE_MEMBER",
            "UPDATE_NAMESPACE_MEMBER_ROLE",
            "REMOVE_NAMESPACE_MEMBER",
        ]
        assert all(row["actor_user_id"] == users["admin"] for row in rows)
        assert all(row["request_id"] == context["request_id"] for row in rows)
        assert rows[0]["detail_json"] == {
            "userId": users["candidate"],
            "newRole": "MEMBER",
        }
        assert rows[1]["detail_json"] == {
            "userId": users["candidate"],
            "oldRole": "MEMBER",
            "newRole": "ADMIN",
        }
        assert "email" not in str(rows)

        async def fail_audit(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("audit unavailable")

        with pytest.raises(RuntimeError, match="audit unavailable"):
            await mutations.add_member(
                engine,
                slug=slugs["active"],
                member_user_id=users["candidate2"],
                role="MEMBER",
                actor_user_id=users["admin"],
                audit_writer=fail_audit,
                **context,
            )
        async with engine.connect() as connection:
            count = await connection.scalar(
                text(
                    "SELECT COUNT(*) FROM namespace_member WHERE namespace_id = :id AND user_id = :user"
                ),
                {"id": seeded["active_id"], "user": users["candidate2"]},
            )
        assert count == 0

        with pytest.raises(RuntimeError, match="audit unavailable"):
            await mutations.transition(
                engine,
                action="freeze",
                slug=slugs["active"],
                actor_user_id=users["admin"],
                reason="must roll back",
                audit_writer=fail_audit,
                **context,
            )
        async with engine.connect() as connection:
            status = await connection.scalar(
                text("SELECT status FROM namespace WHERE id = :id"),
                {"id": seeded["active_id"]},
            )
        assert status == "ACTIVE"
    finally:
        await _cleanup(engine, seeded)
        await engine.dispose()


@pytest.mark.skipif(
    TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL"
)
@pytest.mark.anyio
async def test_admin_batch_member_add_is_durable_per_item_and_audited_per_success(
    caplog: pytest.LogCaptureFixture,
) -> None:
    suffix = uuid4().hex
    engine = create_async_engine(str(TEST_DATABASE_URL))
    seeded = await _seed(engine, suffix)
    users, slugs = seeded["users"], seeded["slugs"]
    try:
        result = await mutations.batch_add_members(
            engine,
            slug=slugs["active"],
            members=[
                {"userId": users["candidate"], "role": "MEMBER"},
                {"userId": users["member"], "role": "ADMIN"},
                {"userId": users["inactive"], "role": "MEMBER"},
                {"userId": users["candidate2"], "role": "OWNER"},
            ],
            actor_user_id=users["admin"],
            **_context(suffix),
        )
        assert result["successCount"] == 1
        assert result["failureCount"] == 3
        assert [item["error"] for item in result["results"]] == [
            None,
            "ALREADY_MEMBER",
            "USER_NOT_FOUND",
            "INVALID_ROLE",
        ]
        rows = await _audit_rows(engine, seeded["active_id"])
        assert [row["action"] for row in rows] == ["ADD_NAMESPACE_MEMBER"]

        async def selective_audit_failure(connection: Any, **kwargs: Any) -> None:
            if kwargs["detail"]["userId"] == users["candidate2"]:
                raise RuntimeError("audit-token=do-not-log@example.test")
            from app.admin_namespace.mutation_repository import insert_audit

            await insert_audit(connection, **kwargs)

        with caplog.at_level(logging.ERROR, logger="app.admin_namespace.mutations"):
            result = await mutations.batch_add_members(
                engine,
                slug=slugs["active"],
                members=[
                    {"userId": users["candidate2"], "role": "MEMBER"},
                    {"userId": users["inactive"], "role": "MEMBER"},
                ],
                actor_user_id=users["admin"],
                audit_writer=selective_audit_failure,
                **_context(suffix),
            )
        assert result["successCount"] == 0
        assert result["failureCount"] == 2
        assert caplog.messages == [
            (
                f"Unexpected admin namespace batch member failure slug={slugs['active']} "
                f"user_id={users['candidate2']} role=MEMBER "
                f"actor_user_id={users['admin']} request_id=request-{suffix} "
                "error_type=RuntimeError"
            )
        ]
        assert "do-not-log" not in caplog.text
        async with engine.connect() as connection:
            count = await connection.scalar(
                text(
                    "SELECT COUNT(*) FROM namespace_member WHERE namespace_id = :id AND user_id = :user"
                ),
                {"id": seeded["active_id"], "user": users["candidate2"]},
            )
        assert count == 0
    finally:
        await _cleanup(engine, seeded)
        await engine.dispose()


async def _outcome(awaitable: Any) -> str:
    try:
        await awaitable
        return "success"
    except AdminNamespaceMutationError as exc:
        return str(exc)


@pytest.mark.skipif(
    TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL"
)
@pytest.mark.anyio
async def test_admin_namespace_concurrency_keeps_one_owner_and_one_lifecycle_audit() -> (
    None
):
    suffix = uuid4().hex
    engine = create_async_engine(str(TEST_DATABASE_URL))
    seeded = await _seed(engine, suffix)
    users, slugs = seeded["users"], seeded["slugs"]
    context = _context(suffix)
    try:
        duplicate = await asyncio.gather(
            *[
                _outcome(
                    mutations.add_member(
                        engine,
                        slug=slugs["active"],
                        member_user_id=users["candidate"],
                        role="MEMBER",
                        actor_user_id=users["admin"],
                        **context,
                    )
                )
                for _ in range(2)
            ]
        )
        assert duplicate.count("success") == 1
        assert sum("alreadyExists" in result for result in duplicate) == 1

        transfer = await asyncio.gather(
            *[
                _outcome(
                    mutations.transfer_ownership(
                        engine,
                        slug=slugs["active"],
                        new_owner_id=users["candidate"],
                        actor_user_id=users["admin"],
                        **context,
                    )
                )
                for _ in range(2)
            ]
        )
        assert transfer.count("success") == 1
        assert sum("owner.new.same" in result for result in transfer) == 1

        freeze = await asyncio.gather(
            *[
                _outcome(
                    mutations.transition(
                        engine,
                        action="freeze",
                        slug=slugs["active"],
                        actor_user_id=users["admin"],
                        reason="race",
                        **context,
                    )
                )
                for _ in range(2)
            ]
        )
        assert freeze.count("success") == 1
        assert sum("transition.invalid" in result for result in freeze) == 1

        async with engine.connect() as connection:
            owners = await connection.scalar(
                text(
                    "SELECT COUNT(*) FROM namespace_member WHERE namespace_id = :id AND role = 'OWNER'"
                ),
                {"id": seeded["active_id"]},
            )
            status = await connection.scalar(
                text("SELECT status FROM namespace WHERE id = :id"),
                {"id": seeded["active_id"]},
            )
        assert owners == 1
        assert status == "FROZEN"
        rows = await _audit_rows(engine, seeded["active_id"])
        assert [row["action"] for row in rows].count("ADD_NAMESPACE_MEMBER") == 1
        assert [row["action"] for row in rows].count(
            "TRANSFER_NAMESPACE_OWNERSHIP"
        ) == 1
        assert [row["action"] for row in rows].count("FREEZE_NAMESPACE") == 1
    finally:
        await _cleanup(engine, seeded)
        await engine.dispose()


@pytest.mark.skipif(
    TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL"
)
@pytest.mark.anyio
async def test_admin_and_ordinary_namespace_mutations_share_cross_surface_locks() -> (
    None
):
    suffix = uuid4().hex
    engine = create_async_engine(str(TEST_DATABASE_URL))
    seeded = await _seed(engine, suffix)
    users = seeded["users"]
    context = _context(suffix)
    try:
        transfer_slug, transfer_id = await _create_race_namespace(
            engine, seeded, key="transfer", suffix=suffix
        )
        transfer_results = await asyncio.gather(
            _cross_surface_outcome(
                mutations.transfer_ownership(
                    engine,
                    slug=transfer_slug,
                    new_owner_id=users["candidate"],
                    actor_user_id=users["admin"],
                    **context,
                )
            ),
            _cross_surface_outcome(
                transfer_namespace_ownership(
                    engine,
                    slug=transfer_slug,
                    current_owner_id=users["owner"],
                    new_owner_id=users["member"],
                )
            ),
        )
        assert "success" in transfer_results

        role_slug, role_id = await _create_race_namespace(
            engine, seeded, key="role", suffix=suffix
        )
        role_results = await asyncio.gather(
            _cross_surface_outcome(
                mutations.update_member_role(
                    engine,
                    slug=role_slug,
                    member_user_id=users["candidate"],
                    role="MEMBER",
                    actor_user_id=users["admin"],
                    **context,
                )
            ),
            _cross_surface_outcome(
                transfer_namespace_ownership(
                    engine,
                    slug=role_slug,
                    current_owner_id=users["owner"],
                    new_owner_id=users["candidate"],
                )
            ),
        )
        assert "success" in role_results

        remove_slug, remove_id = await _create_race_namespace(
            engine, seeded, key="remove", suffix=suffix
        )
        remove_results = await asyncio.gather(
            _cross_surface_outcome(
                mutations.remove_member(
                    engine,
                    slug=remove_slug,
                    member_user_id=users["candidate"],
                    actor_user_id=users["admin"],
                    **context,
                )
            ),
            _cross_surface_outcome(
                transfer_namespace_ownership(
                    engine,
                    slug=remove_slug,
                    current_owner_id=users["owner"],
                    new_owner_id=users["candidate"],
                )
            ),
        )
        assert "success" in remove_results

        async with engine.connect() as connection:
            for namespace_id in (transfer_id, role_id, remove_id):
                owner_count = await connection.scalar(
                    text(
                        """
                        SELECT COUNT(*) FROM namespace_member
                        WHERE namespace_id = :id AND role = 'OWNER'
                        """
                    ),
                    {"id": namespace_id},
                )
                assert owner_count == 1

        transfer_audits = await _audit_rows(engine, transfer_id)
        assert [row["action"] for row in transfer_audits] == [
            "TRANSFER_NAMESPACE_OWNERSHIP"
        ]
        role_audits = await _audit_rows(engine, role_id)
        assert len(role_audits) <= 1
        assert all(
            row["action"] == "UPDATE_NAMESPACE_MEMBER_ROLE" for row in role_audits
        )
        remove_audits = await _audit_rows(engine, remove_id)
        assert len(remove_audits) <= 1
        assert all(row["action"] == "REMOVE_NAMESPACE_MEMBER" for row in remove_audits)
    finally:
        await _cleanup(engine, seeded)
        await engine.dispose()


@pytest.mark.skipif(
    TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL"
)
@pytest.mark.anyio
async def test_admin_lifecycle_serializes_with_ordinary_profile_and_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid4().hex
    engine = create_async_engine(str(TEST_DATABASE_URL))
    seeded = await _seed(engine, suffix)
    users = seeded["users"]
    context = _context(suffix)
    try:
        profile_slug, profile_id = await _create_race_namespace(
            engine, seeded, key="profile", suffix=suffix
        )
        profile_entered = asyncio.Event()
        release_profile = asyncio.Event()
        original_require_manager = namespace_mutations._require_admin_or_owner

        async def paused_require_manager(
            connection: Any, namespace_id: int, user_id: str
        ) -> str:
            role = await original_require_manager(connection, namespace_id, user_id)
            profile_entered.set()
            await release_profile.wait()
            return role

        monkeypatch.setattr(
            namespace_mutations, "_require_admin_or_owner", paused_require_manager
        )
        profile_task = asyncio.create_task(
            update_namespace(
                engine,
                slug=profile_slug,
                display_name=f"Updated {suffix}",
                description="serialized",
                actor_user_id=users["owner"],
            )
        )
        await asyncio.wait_for(profile_entered.wait(), timeout=2)
        freeze_task = asyncio.create_task(
            mutations.transition(
                engine,
                action="freeze",
                slug=profile_slug,
                actor_user_id=users["admin"],
                reason="cross-surface",
                **context,
            )
        )
        await asyncio.sleep(0.1)
        assert not freeze_task.done()
        release_profile.set()
        await profile_task
        frozen = await freeze_task
        assert frozen["status"] == "FROZEN"
        assert [row["action"] for row in await _audit_rows(engine, profile_id)] == [
            "FREEZE_NAMESPACE"
        ]

        monkeypatch.setattr(
            namespace_mutations, "_require_admin_or_owner", original_require_manager
        )
        lifecycle_slug, lifecycle_id = await _create_race_namespace(
            engine, seeded, key="lifecycle", suffix=suffix, status="FROZEN"
        )
        lifecycle_entered = asyncio.Event()
        release_lifecycle = asyncio.Event()
        original_read_role = namespace_mutations._read_member_role

        async def paused_read_role(
            connection: Any, namespace_id: int, user_id: str
        ) -> str:
            role = await original_read_role(connection, namespace_id, user_id)
            lifecycle_entered.set()
            await release_lifecycle.wait()
            return role

        monkeypatch.setattr(namespace_mutations, "_read_member_role", paused_read_role)
        unfreeze_task = asyncio.create_task(
            unfreeze_namespace(
                engine,
                slug=lifecycle_slug,
                actor_user_id=users["owner"],
                request_id=f"ordinary-{suffix}",
                client_ip=None,
                user_agent="pytest",
            )
        )
        await asyncio.wait_for(lifecycle_entered.wait(), timeout=2)
        archive_task = asyncio.create_task(
            mutations.transition(
                engine,
                action="archive",
                slug=lifecycle_slug,
                actor_user_id=users["admin"],
                reason="archive wins after unfreeze",
                **context,
            )
        )
        await asyncio.sleep(0.1)
        assert not archive_task.done()
        release_lifecycle.set()
        ordinary_detail = await unfreeze_task
        archived_detail = await archive_task
        assert ordinary_detail["status"] == "ACTIVE"
        assert archived_detail["status"] == "ARCHIVED"
        assert [row["action"] for row in await _audit_rows(engine, lifecycle_id)] == [
            "UNFREEZE_NAMESPACE",
            "ARCHIVE_NAMESPACE",
        ]
    finally:
        await _cleanup(engine, seeded)
        await engine.dispose()


@pytest.mark.skipif(
    TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL"
)
@pytest.mark.anyio
async def test_admin_ownership_integrity_and_lifecycle_state_matrix() -> None:
    suffix = uuid4().hex
    engine = create_async_engine(str(TEST_DATABASE_URL))
    seeded = await _seed(engine, suffix)
    users, slugs = seeded["users"], seeded["slugs"]
    context = _context(suffix)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE namespace_member SET role = 'MEMBER' WHERE namespace_id = :id AND user_id = :owner"
                ),
                {"id": seeded["active_id"], "owner": users["owner"]},
            )
        with pytest.raises(
            AdminNamespaceMutationError, match="error.namespace.owner.current.invalid"
        ):
            await mutations.transfer_ownership(
                engine,
                slug=slugs["active"],
                new_owner_id=users["member"],
                actor_user_id=users["admin"],
                **context,
            )

        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE namespace_member SET role = 'OWNER' WHERE namespace_id = :id AND user_id = :owner"
                ),
                {"id": seeded["active_id"], "owner": users["owner"]},
            )
            await connection.execute(
                text(
                    "INSERT INTO namespace_member (namespace_id, user_id, role) VALUES (:id, :user, 'OWNER')"
                ),
                {"id": seeded["active_id"], "user": users["candidate"]},
            )
        with pytest.raises(
            AdminNamespaceMutationError, match="error.namespace.owner.current.invalid"
        ):
            await mutations.transfer_ownership(
                engine,
                slug=slugs["active"],
                new_owner_id=users["member"],
                actor_user_id=users["admin"],
                **context,
            )
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE namespace_member SET role = 'MEMBER' WHERE namespace_id = :id AND user_id = :user"
                ),
                {"id": seeded["active_id"], "user": users["candidate"]},
            )

        with pytest.raises(
            AdminNamespaceMutationError, match="error.namespace.owner.new.notFound"
        ):
            await mutations.transfer_ownership(
                engine,
                slug=slugs["active"],
                new_owner_id=users["candidate2"],
                actor_user_id=users["admin"],
                **context,
            )
        assert await _audit_rows(engine, seeded["active_id"]) == []

        await mutations.transition(
            engine,
            action="unfreeze",
            slug=slugs["frozen"],
            actor_user_id=users["admin"],
            reason=None,
            **context,
        )
        await mutations.transition(
            engine,
            action="archive",
            slug=slugs["frozen"],
            actor_user_id=users["admin"],
            reason="retired",
            **context,
        )
        await mutations.transition(
            engine,
            action="restore",
            slug=slugs["frozen"],
            actor_user_id=users["admin"],
            reason=None,
            **context,
        )
        await mutations.transition(
            engine,
            action="archive",
            slug=slugs["active"],
            actor_user_id=users["admin"],
            reason=None,
            **context,
        )
        await mutations.transition(
            engine,
            action="restore",
            slug=slugs["active"],
            actor_user_id=users["admin"],
            reason=None,
            **context,
        )
        with pytest.raises(
            AdminNamespaceMutationError, match="error.namespace.system.immutable"
        ):
            await mutations.transition(
                engine,
                action="freeze",
                slug=slugs["global"],
                actor_user_id=users["admin"],
                reason=None,
                **context,
            )

        async with engine.connect() as connection:
            statuses = dict(
                (
                    await connection.execute(
                        text(
                            "SELECT slug, status FROM namespace WHERE slug = ANY(:slugs)"
                        ),
                        {"slugs": [slugs["active"], slugs["frozen"]]},
                    )
                ).all()
            )
        assert statuses == {slugs["active"]: "ACTIVE", slugs["frozen"]: "ACTIVE"}
    finally:
        await _cleanup(engine, seeded)
        await engine.dispose()


@pytest.mark.skipif(
    TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL"
)
@pytest.mark.anyio
async def test_admin_lifecycle_returns_locked_transaction_projection_without_post_commit_read() -> (
    None
):
    suffix = uuid4().hex
    engine = create_async_engine(str(TEST_DATABASE_URL))
    seeded = await _seed(engine, suffix)

    class BeginOnlyEngine:
        def begin(self) -> Any:
            return engine.begin()

        def connect(self) -> Any:
            raise AssertionError("post-commit detail read must not run")

    try:
        detail = await mutations.transition(
            BeginOnlyEngine(),
            action="freeze",
            slug=seeded["slugs"]["active"],
            actor_user_id=seeded["users"]["admin"],
            reason="locked projection",
            **_context(suffix),
        )
        assert detail["status"] == "FROZEN"
        assert detail["permissions"]["canUnfreeze"] is True
    finally:
        await _cleanup(engine, seeded)
        await engine.dispose()


@pytest.mark.skipif(
    TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL"
)
@pytest.mark.anyio
async def test_admin_lifecycle_projection_precedes_competing_transition_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.admin_namespace.read_repository import read_admin_namespace_detail

    suffix = uuid4().hex
    engine = create_async_engine(str(TEST_DATABASE_URL))
    seeded = await _seed(engine, suffix)
    projection_entered = asyncio.Event()
    release_projection = asyncio.Event()

    async def paused_projection(
        connection: Any, *, slug: str, actor_user_id: str
    ) -> dict[str, Any]:
        projection_entered.set()
        await release_projection.wait()
        return await read_admin_namespace_detail(
            connection, slug=slug, actor_user_id=actor_user_id
        )

    monkeypatch.setattr(mutations, "read_admin_namespace_detail", paused_projection)
    context = _context(suffix)
    try:
        freeze_task = asyncio.create_task(
            mutations.transition(
                engine,
                action="freeze",
                slug=seeded["slugs"]["active"],
                actor_user_id=seeded["users"]["admin"],
                reason="interleaving",
                **context,
            )
        )
        await asyncio.wait_for(projection_entered.wait(), timeout=2)
        unfreeze_task = asyncio.create_task(
            mutations.transition(
                engine,
                action="unfreeze",
                slug=seeded["slugs"]["active"],
                actor_user_id=seeded["users"]["admin"],
                reason=None,
                **context,
            )
        )
        await asyncio.sleep(0.1)
        assert not unfreeze_task.done()

        release_projection.set()
        frozen_detail = await freeze_task
        active_detail = await unfreeze_task
        assert frozen_detail["status"] == "FROZEN"
        assert active_detail["status"] == "ACTIVE"
    finally:
        release_projection.set()
        await _cleanup(engine, seeded)
        await engine.dispose()

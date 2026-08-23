from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.admin_namespace import mutation_repository as repository
from app.admin_namespace.read_repository import read_admin_namespace_detail

AuditWriter = Callable[..., Awaitable[None]]
log = logging.getLogger(__name__)


def _assert_active_team(namespace: dict[str, Any]) -> None:
    if str(namespace["type"]) == "GLOBAL":
        raise repository.AdminNamespaceMutationError("error.namespace.system.immutable")
    if str(namespace["status"]) != "ACTIVE":
        raise repository.AdminNamespaceMutationError("error.namespace.readonly")


def _assert_mutable_team(namespace: dict[str, Any]) -> None:
    if str(namespace["type"]) == "GLOBAL":
        raise repository.AdminNamespaceMutationError("error.namespace.system.immutable")


async def _audit(
    writer: AuditWriter | None,
    connection: Any,
    **kwargs: Any,
) -> None:
    await (writer or repository.insert_audit)(connection, **kwargs)


def _audit_context(
    *, request_id: str | None, client_ip: str | None, user_agent: str | None
) -> dict[str, str | None]:
    return {
        "request_id": request_id,
        "client_ip": client_ip,
        "user_agent": user_agent,
    }


async def add_member(
    engine: Any,
    *,
    slug: str,
    member_user_id: str,
    role: str,
    actor_user_id: str,
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
    audit_writer: AuditWriter | None = None,
) -> dict[str, Any]:
    async with engine.begin() as connection:
        namespace = await repository.lock_namespace(connection, slug)
        _assert_active_team(namespace)
        if role == "OWNER":
            raise repository.AdminNamespaceMutationError(
                "error.namespace.member.owner.assignDirect"
            )
        if role not in {"ADMIN", "MEMBER"}:
            raise repository.AdminNamespaceMutationError(
                "error.namespace.member.role.invalid"
            )
        namespace_id = int(namespace["id"])
        await repository.require_active_user(connection, member_user_id)
        if await repository.read_member_role(connection, namespace_id, member_user_id):
            raise repository.AdminNamespaceMutationError(
                "error.namespace.member.alreadyExists"
            )
        await repository.insert_member(connection, namespace_id, member_user_id, role)
        await _audit(
            audit_writer,
            connection,
            actor_user_id=actor_user_id,
            action="ADD_NAMESPACE_MEMBER",
            namespace_id=namespace_id,
            detail={"userId": member_user_id, "newRole": role},
            **_audit_context(
                request_id=request_id, client_ip=client_ip, user_agent=user_agent
            ),
        )
        member = await repository.read_member(connection, namespace_id, member_user_id)
        if member is None:
            raise repository.AdminNamespaceMutationError(
                "error.namespace.member.notFound"
            )
        return member


def _batch_error(exc: Exception) -> str:
    detail = str(exc)
    if "alreadyExists" in detail:
        return "ALREADY_MEMBER"
    if "owner.assignDirect" in detail or "role.invalid" in detail:
        return "INVALID_ROLE"
    if "user.notFound" in detail or "user.inactive" in detail:
        return "USER_NOT_FOUND"
    if "immutable" in detail or "readonly" in detail:
        return "NAMESPACE_READONLY"
    return "UNKNOWN_ERROR"


async def batch_add_members(
    engine: Any,
    *,
    slug: str,
    members: list[dict[str, Any]],
    actor_user_id: str,
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
    audit_writer: AuditWriter | None = None,
) -> dict[str, Any]:
    async with engine.begin() as connection:
        namespace = await repository.lock_namespace(connection, slug)
        _assert_active_team(namespace)

    results: list[dict[str, Any]] = []
    for item in members:
        user_id, role = str(item["userId"]), str(item["role"])
        try:
            await add_member(
                engine,
                slug=slug,
                member_user_id=user_id,
                role=role,
                actor_user_id=actor_user_id,
                request_id=request_id,
                client_ip=client_ip,
                user_agent=user_agent,
                audit_writer=audit_writer,
            )
            results.append(
                {"userId": user_id, "role": role, "success": True, "error": None}
            )
        except repository.AdminNamespaceMutationError as exc:
            results.append(
                {
                    "userId": user_id,
                    "role": role,
                    "success": False,
                    "error": _batch_error(exc),
                }
            )
        # Batch semantics isolate every database/audit failure to its own item.
        except Exception as exc:  # noqa: BLE001
            log.error(
                "Unexpected admin namespace batch member failure "
                "slug=%s user_id=%s role=%s actor_user_id=%s request_id=%s "
                "error_type=%s",
                slug,
                user_id,
                role,
                actor_user_id,
                request_id,
                type(exc).__name__,
            )
            results.append(
                {
                    "userId": user_id,
                    "role": role,
                    "success": False,
                    "error": "UNKNOWN_ERROR",
                }
            )
    success_count = sum(bool(item["success"]) for item in results)
    return {
        "totalCount": len(results),
        "successCount": success_count,
        "failureCount": len(results) - success_count,
        "results": results,
    }


async def update_member_role(
    engine: Any,
    *,
    slug: str,
    member_user_id: str,
    role: str,
    actor_user_id: str,
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
    audit_writer: AuditWriter | None = None,
) -> dict[str, Any]:
    async with engine.begin() as connection:
        namespace = await repository.lock_namespace(connection, slug)
        _assert_active_team(namespace)
        if role == "OWNER":
            raise repository.AdminNamespaceMutationError(
                "error.namespace.member.owner.setDirect"
            )
        if role not in {"ADMIN", "MEMBER"}:
            raise repository.AdminNamespaceMutationError(
                "error.namespace.member.role.invalid"
            )
        namespace_id = int(namespace["id"])
        old_role = await repository.read_member_role(
            connection, namespace_id, member_user_id
        )
        if old_role is None:
            raise repository.AdminNamespaceMutationError(
                "error.namespace.member.notFound"
            )
        if old_role == "OWNER":
            raise repository.AdminNamespaceMutationError(
                "error.namespace.member.owner.setDirect"
            )
        if old_role == role:
            member = await repository.read_member(
                connection, namespace_id, member_user_id
            )
            if member is None:
                raise repository.AdminNamespaceMutationError(
                    "error.namespace.member.notFound"
                )
            return member
        await repository.update_member_role(
            connection, namespace_id, member_user_id, role
        )
        await _audit(
            audit_writer,
            connection,
            actor_user_id=actor_user_id,
            action="UPDATE_NAMESPACE_MEMBER_ROLE",
            namespace_id=namespace_id,
            detail={"userId": member_user_id, "oldRole": old_role, "newRole": role},
            **_audit_context(
                request_id=request_id, client_ip=client_ip, user_agent=user_agent
            ),
        )
        member = await repository.read_member(connection, namespace_id, member_user_id)
        if member is None:
            raise repository.AdminNamespaceMutationError(
                "error.namespace.member.notFound"
            )
        return member


async def remove_member(
    engine: Any,
    *,
    slug: str,
    member_user_id: str,
    actor_user_id: str,
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
    audit_writer: AuditWriter | None = None,
) -> dict[str, str]:
    async with engine.begin() as connection:
        namespace = await repository.lock_namespace(connection, slug)
        _assert_active_team(namespace)
        namespace_id = int(namespace["id"])
        old_role = await repository.read_member_role(
            connection, namespace_id, member_user_id
        )
        if old_role is None:
            raise repository.AdminNamespaceMutationError(
                "error.namespace.member.notFound"
            )
        if old_role == "OWNER":
            raise repository.AdminNamespaceMutationError(
                "error.namespace.member.owner.remove"
            )
        await repository.delete_member(connection, namespace_id, member_user_id)
        await _audit(
            audit_writer,
            connection,
            actor_user_id=actor_user_id,
            action="REMOVE_NAMESPACE_MEMBER",
            namespace_id=namespace_id,
            detail={"userId": member_user_id, "oldRole": old_role},
            **_audit_context(
                request_id=request_id, client_ip=client_ip, user_agent=user_agent
            ),
        )
    return {"message": "Member removed successfully"}


async def transfer_ownership(
    engine: Any,
    *,
    slug: str,
    new_owner_id: str,
    actor_user_id: str,
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
    audit_writer: AuditWriter | None = None,
) -> dict[str, str]:
    async with engine.begin() as connection:
        namespace = await repository.lock_namespace(connection, slug)
        _assert_active_team(namespace)
        namespace_id = int(namespace["id"])
        members = await repository.lock_members(connection, namespace_id)
        owners = [item for item in members if str(item["role"]) == "OWNER"]
        if len(owners) != 1:
            raise repository.AdminNamespaceMutationError(
                "error.namespace.owner.current.invalid"
            )
        current_owner_id = str(owners[0]["user_id"])
        if new_owner_id == current_owner_id:
            raise repository.AdminNamespaceMutationError(
                "error.namespace.owner.new.same"
            )
        new_owner = next(
            (item for item in members if str(item["user_id"]) == new_owner_id), None
        )
        if new_owner is None:
            raise repository.AdminNamespaceMutationError(
                "error.namespace.owner.new.notFound"
            )
        await repository.require_active_user(connection, new_owner_id)
        old_new_owner_role = str(new_owner["role"])
        await repository.update_member_role(
            connection, namespace_id, current_owner_id, "ADMIN"
        )
        await repository.update_member_role(
            connection, namespace_id, new_owner_id, "OWNER"
        )
        await _audit(
            audit_writer,
            connection,
            actor_user_id=actor_user_id,
            action="TRANSFER_NAMESPACE_OWNERSHIP",
            namespace_id=namespace_id,
            detail={
                "oldOwnerId": current_owner_id,
                "newOwnerId": new_owner_id,
                "oldOwnerNewRole": "ADMIN",
                "newOwnerOldRole": old_new_owner_role,
                "newOwnerNewRole": "OWNER",
            },
            **_audit_context(
                request_id=request_id, client_ip=client_ip, user_agent=user_agent
            ),
        )
    return {"message": "Ownership transferred successfully"}


_TRANSITIONS = {
    "freeze": ({"ACTIVE"}, "FROZEN", "FREEZE_NAMESPACE"),
    "unfreeze": ({"FROZEN"}, "ACTIVE", "UNFREEZE_NAMESPACE"),
    "archive": ({"ACTIVE", "FROZEN"}, "ARCHIVED", "ARCHIVE_NAMESPACE"),
    "restore": ({"ARCHIVED"}, "ACTIVE", "RESTORE_NAMESPACE"),
}


async def transition(
    engine: Any,
    *,
    action: str,
    slug: str,
    actor_user_id: str,
    reason: str | None,
    request_id: str | None,
    client_ip: str | None,
    user_agent: str | None,
    audit_writer: AuditWriter | None = None,
) -> dict[str, Any]:
    allowed, target, audit_action = _TRANSITIONS[action]
    async with engine.begin() as connection:
        namespace = await repository.lock_namespace(connection, slug)
        _assert_mutable_team(namespace)
        current = str(namespace["status"])
        if current not in allowed:
            raise repository.AdminNamespaceMutationError(
                "error.namespace.state.transition.invalid"
            )
        namespace_id = int(namespace["id"])
        await repository.update_namespace_status(connection, namespace_id, target)
        detail = {"oldStatus": current, "newStatus": target}
        if reason is not None and reason.strip():
            detail["reason"] = reason
        await _audit(
            audit_writer,
            connection,
            actor_user_id=actor_user_id,
            action=audit_action,
            namespace_id=namespace_id,
            detail=detail,
            **_audit_context(
                request_id=request_id, client_ip=client_ip, user_agent=user_agent
            ),
        )
        return await read_admin_namespace_detail(
            connection, slug=slug, actor_user_id=actor_user_id
        )

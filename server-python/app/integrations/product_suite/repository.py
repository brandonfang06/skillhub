from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import text

from app.integrations.product_suite.contracts import (
    ProductSuiteOwnerRecord,
    ProductSuiteSyncIssue,
    ProductSuiteSyncSummary,
    validate_snapshot,
)


class ProductSuiteSyncError(RuntimeError):
    pass


async def _read_namespace(
    connection: Any,
    namespace_slug: str,
) -> dict[str, Any] | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT id, slug, status, type
                FROM namespace
                WHERE slug = :slug
                LIMIT 1
                """
            ),
            {"slug": namespace_slug},
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


async def _read_identities(
    connection: Any,
    *,
    provider_code: str,
    login_name: str,
) -> list[dict[str, Any]]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT ib.id, ib.user_id, ib.login_name,
                       ua.status, ua.merged_to_user_id
                FROM identity_binding ib
                JOIN user_account ua ON ua.id = ib.user_id
                WHERE ib.provider_code = :provider_code
                  AND LOWER(BTRIM(ib.login_name)) = LOWER(:login_name)
                ORDER BY ib.id ASC
                """
            ),
            {
                "provider_code": provider_code,
                "login_name": login_name,
            },
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def _read_membership_role(
    connection: Any,
    *,
    namespace_id: int,
    user_id: str,
) -> str | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT role
                FROM namespace_member
                WHERE namespace_id = :namespace_id
                  AND user_id = :user_id
                LIMIT 1
                """
            ),
            {
                "namespace_id": namespace_id,
                "user_id": user_id,
            },
        )
    ).mappings().one_or_none()
    return str(row["role"]) if row is not None else None


def _add_issue(
    summary: ProductSuiteSyncSummary,
    record: ProductSuiteOwnerRecord,
    *,
    code: str,
    detail: str,
) -> None:
    summary.issues.append(
        ProductSuiteSyncIssue(
            external_suite_id=record.external_suite_id,
            namespace_slug=record.namespace_slug,
            owner_windows_account=record.owner_windows_account,
            code=code,
            detail=detail,
        )
    )


def _active_identity_rows(
    rows: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if str(row["status"]) == "ACTIVE" and row["merged_to_user_id"] is None
    ]


def _classify_stable_role(
    role: str | None,
    summary: ProductSuiteSyncSummary,
) -> None:
    if role in {"ADMIN", "OWNER"}:
        summary.memberships_unchanged += 1
        return
    raise ProductSuiteSyncError(
        f"membership did not converge to ADMIN or OWNER; current role={role!r}"
    )


async def _promote_member(
    connection: Any,
    *,
    namespace_id: int,
    user_id: str,
    summary: ProductSuiteSyncSummary,
) -> None:
    result = await connection.execute(
        text(
            """
            UPDATE namespace_member
            SET role = 'ADMIN',
                updated_at = CURRENT_TIMESTAMP
            WHERE namespace_id = :namespace_id
              AND user_id = :user_id
              AND role = 'MEMBER'
            """
        ),
        {
            "namespace_id": namespace_id,
            "user_id": user_id,
        },
    )
    if int(result.rowcount or 0) == 1:
        summary.members_promoted += 1
        return
    role = await _read_membership_role(
        connection,
        namespace_id=namespace_id,
        user_id=user_id,
    )
    _classify_stable_role(role, summary)


async def _add_admin(
    connection: Any,
    *,
    namespace_id: int,
    user_id: str,
    summary: ProductSuiteSyncSummary,
) -> None:
    result = await connection.execute(
        text(
            """
            INSERT INTO namespace_member (namespace_id, user_id, role)
            VALUES (:namespace_id, :user_id, 'ADMIN')
            ON CONFLICT (namespace_id, user_id) DO NOTHING
            """
        ),
        {
            "namespace_id": namespace_id,
            "user_id": user_id,
        },
    )
    if int(result.rowcount or 0) == 1:
        summary.administrators_added += 1
        return

    role = await _read_membership_role(
        connection,
        namespace_id=namespace_id,
        user_id=user_id,
    )
    if role == "MEMBER":
        await _promote_member(
            connection,
            namespace_id=namespace_id,
            user_id=user_id,
            summary=summary,
        )
        return
    _classify_stable_role(role, summary)


async def _reconcile_record(
    connection: Any,
    *,
    record: ProductSuiteOwnerRecord,
    identity_provider: str,
    dry_run: bool,
    summary: ProductSuiteSyncSummary,
) -> None:
    namespace = await _read_namespace(connection, record.namespace_slug)
    if namespace is None:
        summary.blocked += 1
        _add_issue(
            summary,
            record,
            code="NAMESPACE_NOT_FOUND",
            detail="namespace does not exist",
        )
        return

    summary.namespaces_resolved += 1
    if str(namespace["status"]) != "ACTIVE" or str(namespace["type"]) != "TEAM":
        summary.blocked += 1
        _add_issue(
            summary,
            record,
            code="NAMESPACE_BLOCKED",
            detail=(
                f"namespace status={namespace['status']!s} "
                f"type={namespace['type']!s}"
            ),
        )
        return

    identity_rows = await _read_identities(
        connection,
        provider_code=identity_provider,
        login_name=record.normalized_windows_account,
    )
    if not identity_rows:
        summary.waiting_for_login += 1
        return

    active_rows = _active_identity_rows(identity_rows)
    if len(active_rows) > 1:
        summary.identity_conflicts += 1
        _add_issue(
            summary,
            record,
            code="IDENTITY_CONFLICT",
            detail="multiple active identities match the Windows account",
        )
        return
    if not active_rows:
        summary.blocked += 1
        _add_issue(
            summary,
            record,
            code="USER_BLOCKED",
            detail="matching identity is disabled or merged",
        )
        return

    user_id = str(active_rows[0]["user_id"])
    namespace_id = int(namespace["id"])
    role = await _read_membership_role(
        connection,
        namespace_id=namespace_id,
        user_id=user_id,
    )
    if role in {"ADMIN", "OWNER"}:
        summary.memberships_unchanged += 1
        return
    if role == "MEMBER":
        summary.members_promoted += int(dry_run)
        if not dry_run:
            await _promote_member(
                connection,
                namespace_id=namespace_id,
                user_id=user_id,
                summary=summary,
            )
        return
    if role is not None:
        raise ProductSuiteSyncError(
            f"unsupported namespace membership role: {role!r}"
        )

    summary.administrators_added += int(dry_run)
    if not dry_run:
        await _add_admin(
            connection,
            namespace_id=namespace_id,
            user_id=user_id,
            summary=summary,
        )


async def reconcile_product_suite_admins(
    engine: Any,
    *,
    records: Sequence[ProductSuiteOwnerRecord],
    identity_provider: str,
    dry_run: bool,
) -> ProductSuiteSyncSummary:
    validated = validate_snapshot(records)
    summary = ProductSuiteSyncSummary(
        suites_fetched=len(validated),
        dry_run=dry_run,
    )
    async with engine.begin() as connection:
        for record in validated:
            await _reconcile_record(
                connection,
                record=record,
                identity_provider=identity_provider,
                dry_run=dry_run,
                summary=summary,
            )
    return summary

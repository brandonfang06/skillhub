from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.skills.read_responses import to_java_instant

VALID_STATUSES = {"ACTIVE", "FROZEN", "ARCHIVED"}
VALID_TYPES = {"TEAM", "GLOBAL"}
JAVA_INT_MAX = 2_147_483_647


class AdminNamespaceReadError(Exception):
    def __init__(self, detail: str, *, status_code: int = 400) -> None:
        super().__init__(detail)
        self.status_code = status_code


def normalize_page(page: int) -> int:
    if page > JAVA_INT_MAX:
        raise AdminNamespaceReadError(
            "error.pagination.page.invalid",
            status_code=400,
        )
    return max(page, 0)


def normalize_page_size(size: int) -> int:
    if size <= 0:
        return 20
    return min(size, 100)


def normalize_candidate_size(size: int) -> int:
    if size <= 0:
        return 10
    return min(size, 20)


def normalize_search(search: str) -> str | None:
    keyword = search.strip()
    if not keyword:
        return None
    if len(keyword) < 2:
        raise AdminNamespaceReadError(
            "error.namespace.member.search.tooShort",
            status_code=400,
        )
    return keyword


def _normalize_filter(value: str | None, allowed: set[str], detail: str) -> str | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip().upper()
    if normalized not in allowed:
        raise AdminNamespaceReadError(detail, status_code=400)
    return normalized


def _permissions(
    *,
    namespace_type: str,
    status: str,
    current_user_role: str | None,
) -> dict[str, Any]:
    mutable_team = namespace_type == "TEAM"
    active = status == "ACTIVE"
    frozen = status == "FROZEN"
    archived = status == "ARCHIVED"
    return {
        "currentUserRole": current_user_role,
        "platformOverride": True,
        "immutable": namespace_type == "GLOBAL",
        "canManageMembers": mutable_team and active,
        "canGovernNamespace": mutable_team,
        "canPublish": mutable_team and active,
        "canTransferOwnership": mutable_team and active,
        "canFreeze": mutable_team and active,
        "canUnfreeze": mutable_team and frozen,
        "canArchive": mutable_team and not archived,
        "canRestore": mutable_team and archived,
    }


def _namespace_response(row: dict[str, Any]) -> dict[str, Any]:
    namespace_type = str(row["type"])
    status = str(row["status"])
    role = (
        str(row["current_user_role"])
        if row.get("current_user_role") is not None
        else None
    )
    return {
        "id": int(row["id"]),
        "slug": str(row["slug"]),
        "displayName": str(row["display_name"]),
        "status": status,
        "description": row.get("description"),
        "type": namespace_type,
        "avatarUrl": row.get("avatar_url"),
        "createdBy": row.get("created_by"),
        "createdAt": to_java_instant(row["created_at"]),
        "updatedAt": to_java_instant(row["updated_at"]),
        "stats": {
            "memberCount": int(row.get("member_count") or 0),
            "skillCount": int(row.get("skill_count") or 0),
        },
        "permissions": _permissions(
            namespace_type=namespace_type,
            status=status,
            current_user_role=role,
        ),
    }


def _member_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "namespaceId": int(row["namespace_id"]),
        "userId": str(row["user_id"]),
        "displayName": row.get("display_name"),
        "email": row.get("email"),
        "role": str(row["role"]),
        "createdAt": to_java_instant(row["created_at"]),
        "updatedAt": to_java_instant(row["updated_at"]),
    }


def _candidate_response(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "userId": str(row["id"]),
        "displayName": str(row["display_name"]),
        "email": row.get("email"),
        "status": str(row["status"]),
    }


def _where_clause(
    *,
    keyword: str | None,
    status: str | None,
    namespace_type: str | None,
    params: dict[str, Any],
) -> str:
    conditions: list[str] = []
    if keyword is not None and keyword.strip():
        params["keyword"] = f"%{keyword.strip().lower()}%"
        conditions.append(
            "(lower(n.slug) LIKE :keyword OR lower(n.display_name) LIKE :keyword "
            "OR lower(coalesce(n.description, '')) LIKE :keyword)"
        )
    if status is not None:
        params["status"] = status
        conditions.append("n.status = :status")
    if namespace_type is not None:
        params["namespace_type"] = namespace_type
        conditions.append("n.type = :namespace_type")
    return f"WHERE {' AND '.join(conditions)}" if conditions else ""


async def list_admin_namespaces(
    engine: Any,
    *,
    keyword: str | None,
    status: str | None,
    namespace_type: str | None,
    page: int,
    size: int,
    actor_user_id: str,
) -> dict[str, Any]:
    normalized_status = _normalize_filter(
        status,
        VALID_STATUSES,
        "error.namespace.status.invalid",
    )
    normalized_type = _normalize_filter(
        namespace_type,
        VALID_TYPES,
        "error.namespace.type.invalid",
    )
    normalized_page = normalize_page(page)
    normalized_size = normalize_page_size(size)
    params: dict[str, Any] = {}
    where = _where_clause(
        keyword=keyword,
        status=normalized_status,
        namespace_type=normalized_type,
        params=params,
    )

    async with engine.connect() as connection:
        total = (
            await connection.execute(
                text(
                    f"""
                    SELECT /* admin-namespace-page-count */ COUNT(*) AS count
                    FROM namespace n
                    {where}
                    """
                ),
                params,
            )
        ).scalar_one()
        stats_result = await connection.execute(
            text(
                """
                    SELECT /* admin-namespace-list-stats */
                           COUNT(*) AS total,
                           COUNT(*) FILTER (WHERE status = 'ACTIVE') AS active,
                           COUNT(*) FILTER (WHERE status = 'FROZEN') AS frozen,
                           COUNT(*) FILTER (WHERE status = 'ARCHIVED') AS archived
                    FROM namespace
                    """
            )
        )
        stats_row = stats_result.mappings().one()
        page_params = {
            **params,
            "actor_user_id": actor_user_id,
            "limit": normalized_size,
            "offset": normalized_page * normalized_size,
        }
        page_result = await connection.execute(
            text(
                f"""
                    WITH namespace_page AS (
                        SELECT n.id, n.slug, n.display_name, n.status, n.description,
                               n.type, n.avatar_url, n.created_by, n.created_at, n.updated_at
                        FROM namespace n
                        {where}
                        ORDER BY n.updated_at DESC, n.slug ASC
                        LIMIT :limit OFFSET :offset
                    ),
                    member_counts AS (
                        SELECT nm.namespace_id, COUNT(*) AS member_count
                        FROM namespace_member nm
                        WHERE nm.namespace_id IN (SELECT id FROM namespace_page)
                        GROUP BY nm.namespace_id
                    ),
                    skill_counts AS (
                        SELECT s.namespace_id, COUNT(*) AS skill_count
                        FROM skill s
                        WHERE s.namespace_id IN (SELECT id FROM namespace_page)
                        GROUP BY s.namespace_id
                    )
                    SELECT /* admin-namespace-page */
                           n.id, n.slug, n.display_name, n.status, n.description,
                           n.type, n.avatar_url, n.created_by, n.created_at, n.updated_at,
                           coalesce(mc.member_count, 0) AS member_count,
                           coalesce(sc.skill_count, 0) AS skill_count,
                           actor_nm.role AS current_user_role
                    FROM namespace_page n
                    LEFT JOIN member_counts mc ON mc.namespace_id = n.id
                    LEFT JOIN skill_counts sc ON sc.namespace_id = n.id
                    LEFT JOIN namespace_member actor_nm
                      ON actor_nm.namespace_id = n.id
                     AND actor_nm.user_id = :actor_user_id
                    ORDER BY n.updated_at DESC, n.slug ASC
                    """
            ),
            page_params,
        )
        rows = page_result.mappings().all()
    return {
        "items": [_namespace_response(dict(row)) for row in rows],
        "total": int(total),
        "page": normalized_page,
        "size": normalized_size,
        "stats": {
            "total": int(stats_row["total"]),
            "active": int(stats_row["active"]),
            "frozen": int(stats_row["frozen"]),
            "archived": int(stats_row["archived"]),
        },
    }


async def get_admin_namespace(
    engine: Any,
    *,
    slug: str,
    actor_user_id: str,
) -> dict[str, Any]:
    async with engine.connect() as connection:
        return await read_admin_namespace_detail(
            connection, slug=slug, actor_user_id=actor_user_id
        )


async def read_admin_namespace_detail(
    connection: Any,
    *,
    slug: str,
    actor_user_id: str,
) -> dict[str, Any]:
    result = await connection.execute(
        text(
            """
                    SELECT /* admin-namespace-detail */
                           n.id, n.slug, n.display_name, n.status, n.description,
                           n.type, n.avatar_url, n.created_by, n.created_at, n.updated_at,
                           (SELECT COUNT(*) FROM namespace_member nm
                            WHERE nm.namespace_id = n.id) AS member_count,
                           (SELECT COUNT(*) FROM skill s
                            WHERE s.namespace_id = n.id) AS skill_count,
                           actor_nm.role AS current_user_role
                    FROM namespace n
                    LEFT JOIN namespace_member actor_nm
                      ON actor_nm.namespace_id = n.id
                     AND actor_nm.user_id = :actor_user_id
                    WHERE n.slug = :slug
                    LIMIT 1
                    """
        ),
        {"slug": slug, "actor_user_id": actor_user_id},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise AdminNamespaceReadError("error.namespace.slug.notFound", status_code=400)
    return _namespace_response(dict(row))


async def _read_namespace_identity(connection: Any, slug: str) -> dict[str, Any]:
    result = await connection.execute(
        text(
            """
                SELECT /* admin-namespace-identity */ id, slug, type, status
                FROM namespace
                WHERE slug = :slug
                LIMIT 1
                """
        ),
        {"slug": slug},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise AdminNamespaceReadError("error.namespace.slug.notFound", status_code=400)
    return dict(row)


async def list_admin_namespace_members(
    engine: Any,
    *,
    slug: str,
    page: int,
    size: int,
) -> dict[str, Any]:
    normalized_page = normalize_page(page)
    normalized_size = normalize_page_size(size)
    async with engine.connect() as connection:
        namespace = await _read_namespace_identity(connection, slug)
        namespace_id = int(namespace["id"])
        total = (
            await connection.execute(
                text(
                    """
                    SELECT /* admin-namespace-member-count */ COUNT(*) AS count
                    FROM namespace_member
                    WHERE namespace_id = :namespace_id
                    """
                ),
                {"namespace_id": namespace_id},
            )
        ).scalar_one()
        page_result = await connection.execute(
            text(
                """
                    SELECT /* admin-namespace-members */
                           nm.id, nm.namespace_id, nm.user_id, ua.display_name, ua.email,
                           nm.role, nm.created_at, nm.updated_at
                    FROM namespace_member nm
                    LEFT JOIN user_account ua ON ua.id = nm.user_id
                    WHERE nm.namespace_id = :namespace_id
                    ORDER BY nm.id ASC
                    LIMIT :limit OFFSET :offset
                    """
            ),
            {
                "namespace_id": namespace_id,
                "limit": normalized_size,
                "offset": normalized_page * normalized_size,
            },
        )
        rows = page_result.mappings().all()
    return {
        "items": [_member_response(dict(row)) for row in rows],
        "total": int(total),
        "page": normalized_page,
        "size": normalized_size,
    }


async def search_admin_namespace_member_candidates(
    engine: Any,
    *,
    slug: str,
    search: str,
    size: int,
) -> list[dict[str, Any]]:
    normalized_size = normalize_candidate_size(size)
    async with engine.connect() as connection:
        namespace = await _read_namespace_identity(connection, slug)
        if str(namespace["type"]) == "GLOBAL":
            raise AdminNamespaceReadError(
                "error.namespace.system.immutable", status_code=400
            )
        if str(namespace["status"]) != "ACTIVE":
            raise AdminNamespaceReadError("error.namespace.readonly", status_code=400)
        normalized_search = normalize_search(search)
        if normalized_search is None:
            return []
        candidate_result = await connection.execute(
            text(
                """
                    SELECT /* admin-namespace-member-candidates */
                           ua.id, ua.display_name, ua.email, ua.status
                    FROM user_account ua
                    WHERE ua.status = 'ACTIVE'
                      AND (
                        lower(ua.display_name) LIKE lower(:keyword)
                        OR lower(coalesce(ua.email, '')) LIKE lower(:keyword)
                        OR lower(ua.id) LIKE lower(:keyword)
                      )
                      AND NOT EXISTS (
                        SELECT 1
                        FROM namespace_member nm
                        WHERE nm.namespace_id = :namespace_id
                          AND nm.user_id = ua.id
                      )
                    ORDER BY ua.id ASC
                    LIMIT :limit
                    """
            ),
            {
                "namespace_id": int(namespace["id"]),
                "keyword": f"%{normalized_search}%",
                "limit": normalized_size,
            },
        )
        rows = candidate_result.mappings().all()
    return [_candidate_response(dict(row)) for row in rows]

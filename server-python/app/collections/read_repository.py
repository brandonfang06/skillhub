from __future__ import annotations

from collections import defaultdict
from typing import Any
from urllib.parse import quote

from sqlalchemy import text

from app.collections.access import can_curate_collection, can_read_collection_member
from app.skills.read_resolve import compute_version_fingerprint
from app.skills.read_responses import to_java_instant


class CollectionReadError(LookupError):
    def __init__(self, detail: str, *, status_code: int = 404) -> None:
        super().__init__(detail)
        self.status_code = status_code


async def _read_namespace_context(
    connection: Any,
    *,
    namespace: str,
    current_user_id: str | None,
) -> dict[str, Any]:
    row = (
        await connection.execute(
            text(
                """
                SELECT n.id, n.slug, n.type, n.status,
                       (
                           SELECT nm.role
                           FROM namespace_member nm
                           WHERE nm.namespace_id = n.id
                             AND nm.user_id = :current_user_id
                           LIMIT 1
                       ) AS namespace_role
                FROM namespace n
                WHERE n.slug = :namespace
                LIMIT 1
                """
            ),
            {
                "namespace": namespace,
                "current_user_id": current_user_id,
            },
        )
    ).mappings().one_or_none()
    if row is None or str(row["status"]) != "ACTIVE":
        raise CollectionReadError("error.collection.notFound")
    return dict(row)


def _collection_select() -> str:
    return """
        SELECT c.id, n.slug AS namespace, c.slug, c.display_name, c.summary,
               c.status, c.hidden, c.created_at, c.updated_at,
               published.id AS latest_version_id,
               published.version AS latest_version,
               published.status AS latest_status,
               published.draft_revision AS latest_draft_revision,
               published.release_notes AS latest_release_notes,
               published.created_at AS latest_created_at,
               published.published_at AS latest_published_at,
               (
                   SELECT COUNT(*)
                   FROM local_collection_version_member published_member
                   WHERE published_member.collection_version_id = published.id
               ) AS latest_member_count,
               draft.id AS draft_version_id,
               draft.version AS draft_version,
               draft.status AS draft_status,
               draft.draft_revision AS draft_revision,
               draft.release_notes AS draft_release_notes,
               draft.created_at AS draft_created_at,
               draft.published_at AS draft_published_at,
               (
                   SELECT COUNT(*)
                   FROM local_collection_version_member draft_member
                   WHERE draft_member.collection_version_id = draft.id
               ) AS draft_member_count
        FROM local_collection c
        JOIN namespace n ON n.id = c.namespace_id
        LEFT JOIN local_collection_version published
          ON published.id = c.latest_published_version_id
        LEFT JOIN local_collection_version draft
          ON draft.collection_id = c.id
         AND draft.status = 'DRAFT'
    """


async def _read_collection_rows(connection: Any, namespace_id: int) -> list[dict[str, Any]]:
    rows = (
        await connection.execute(
            text(
                _collection_select()
                + """
                  WHERE c.namespace_id = :namespace_id
                  ORDER BY c.slug ASC, c.id ASC
                """
            ),
            {"namespace_id": namespace_id},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def _read_collection_row(
    connection: Any,
    *,
    namespace_id: int,
    collection: str,
) -> dict[str, Any] | None:
    row = (
        await connection.execute(
            text(
                _collection_select()
                + """
                  WHERE c.namespace_id = :namespace_id
                    AND c.slug = :collection
                  LIMIT 1
                """
            ),
            {
                "namespace_id": namespace_id,
                "collection": collection,
            },
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


async def _read_members(
    connection: Any,
    version_ids: list[int],
) -> list[dict[str, Any]]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT member.collection_version_id, member.skill_id,
                       member.skill_version_id, collection_namespace.slug AS namespace,
                       member.skill_slug_snapshot AS skill_slug,
                       member.skill_version_snapshot AS version,
                       member.position,
                       member.note,
                       COALESCE(
                           s.owner_id,
                           member.skill_owner_id_snapshot
                       ) AS owner_id,
                       COALESCE(
                           s.visibility,
                           member.skill_visibility_snapshot
                       ) AS visibility,
                       sv.skill_id AS version_skill_id,
                       CASE
                           WHEN member.skill_id IS NULL THEN member.id
                           ELSE s.latest_version_id
                       END AS latest_version_id,
                       s.status AS skill_status,
                       s.hidden AS skill_hidden, sv.status AS version_status,
                       sv.download_ready, sv.yanked_at
                FROM local_collection_version_member member
                JOIN local_collection_version collection_version
                  ON collection_version.id = member.collection_version_id
                JOIN local_collection collection
                  ON collection.id = collection_version.collection_id
                JOIN namespace collection_namespace
                  ON collection_namespace.id = collection.namespace_id
                LEFT JOIN skill s ON s.id = member.skill_id
                LEFT JOIN skill_version sv ON sv.id = member.skill_version_id
                WHERE member.collection_version_id = ANY(CAST(:version_ids AS bigint[]))
                ORDER BY member.collection_version_id ASC,
                         member.position ASC,
                         member.id ASC
                """
            ),
            {"version_ids": version_ids},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def _read_files(
    connection: Any,
    version_ids: list[int],
) -> list[dict[str, Any]]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT version_id, file_path, sha256
                FROM skill_file
                WHERE version_id = ANY(CAST(:version_ids AS bigint[]))
                ORDER BY version_id ASC, file_path ASC
                """
            ),
            {"version_ids": version_ids},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


def _members_by_version(rows: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[int(row["collection_version_id"])].append(row)
    return grouped


def _version_summary(row: dict[str, Any], prefix: str) -> dict[str, Any] | None:
    version_id = row.get(f"{prefix}_version_id")
    if version_id is None:
        return None
    return {
        "versionId": int(version_id),
        "version": str(row[f"{prefix}_version"]),
        "status": str(row[f"{prefix}_status"]),
        "draftRevision": int(row[f"{prefix}_draft_revision"] if prefix == "latest" else row["draft_revision"]),
        "memberCount": int(row.get(f"{prefix}_member_count") or 0),
        "releaseNotes": row.get(f"{prefix}_release_notes"),
        "createdAt": to_java_instant(row[f"{prefix}_created_at"]),
        "publishedAt": (
            to_java_instant(row[f"{prefix}_published_at"])
            if row.get(f"{prefix}_published_at") is not None
            else None
        ),
    }


def _member_response(row: dict[str, Any]) -> dict[str, Any]:
    skill_id = row.get("skill_id")
    skill_version_id = row.get("skill_version_id")
    return {
        "skillId": int(skill_id) if skill_id is not None else None,
        "skillVersionId": (
            int(skill_version_id) if skill_version_id is not None else None
        ),
        "namespace": str(row["namespace"]),
        "skillSlug": str(row["skill_slug"]),
        "version": str(row["version"]),
        "position": int(row["position"]),
        "note": row.get("note"),
    }


def _version_response(
    collection_row: dict[str, Any],
    prefix: str,
    member_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    summary = _version_summary(collection_row, prefix)
    if summary is None:
        return None
    return {
        **summary,
        "members": [_member_response(row) for row in member_rows],
    }


def _member_is_browsable(
    row: dict[str, Any],
    *,
    collection_namespace: str,
    current_user_id: str | None,
    namespace_role: str | None,
    platform_roles: list[str],
) -> bool:
    skill_id = row.get("skill_id")
    skill_version_id = row.get("skill_version_id")
    if skill_id is None and skill_version_id is None:
        return (
            str(row["namespace"]) == collection_namespace
            and can_read_collection_member(
                row,
                current_user_id=current_user_id,
                namespace_role=namespace_role,
                platform_roles=platform_roles,
            )
        )
    if skill_id is None:
        return False
    skill_is_accessible = (
        str(row["namespace"]) == collection_namespace
        and str(row["skill_status"]) == "ACTIVE"
        and not bool(row["skill_hidden"])
        and can_read_collection_member(
            row,
            current_user_id=current_user_id,
            namespace_role=namespace_role,
            platform_roles=platform_roles,
        )
    )
    if skill_version_id is None:
        return skill_is_accessible
    return (
        skill_is_accessible
        and row.get("version_skill_id") is not None
        and int(skill_id) == int(row["version_skill_id"])
        and str(row["version_status"]) == "PUBLISHED"
        and bool(row["download_ready"])
        and row.get("yanked_at") is None
    )


def _snapshot_is_browsable(
    member_rows: list[dict[str, Any]],
    *,
    collection_namespace: str,
    current_user_id: str | None,
    namespace_role: str | None,
    platform_roles: list[str],
) -> bool:
    return bool(member_rows) and all(
        _member_is_browsable(
            row,
            collection_namespace=collection_namespace,
            current_user_id=current_user_id,
            namespace_role=namespace_role,
            platform_roles=platform_roles,
        )
        for row in member_rows
    )


def _collection_summary(
    row: dict[str, Any],
    *,
    can_curate: bool,
) -> dict[str, Any]:
    return {
        "collectionId": int(row["id"]),
        "namespace": str(row["namespace"]),
        "slug": str(row["slug"]),
        "displayName": str(row["display_name"]),
        "summary": str(row["summary"]),
        "status": str(row["status"]),
        "hidden": bool(row["hidden"]),
        "canCurate": can_curate,
        "latestPublishedVersion": _version_summary(row, "latest"),
        "draft": _version_summary(row, "draft") if can_curate else None,
        "createdAt": to_java_instant(row["created_at"]),
        "updatedAt": to_java_instant(row["updated_at"]),
    }


async def list_collections(
    engine: Any,
    *,
    namespace: str,
    current_user_id: str | None,
    platform_roles: list[str],
) -> dict[str, Any]:
    async with engine.connect() as connection:
        namespace_context = await _read_namespace_context(
            connection,
            namespace=namespace,
            current_user_id=current_user_id,
        )
        rows = await _read_collection_rows(connection, int(namespace_context["id"]))
        version_ids = [
            int(version_id)
            for row in rows
            for version_id in (row.get("latest_version_id"), row.get("draft_version_id"))
            if version_id is not None
        ]
        member_rows = await _read_members(connection, version_ids)

    grouped_members = _members_by_version(member_rows)
    can_curate = can_curate_collection(
        str(namespace_context["type"]),
        namespace_context.get("namespace_role"),
        platform_roles,
    )
    items = []
    for row in rows:
        latest_version_id = row.get("latest_version_id")
        latest_members = grouped_members.get(int(latest_version_id), []) if latest_version_id is not None else []
        visible = can_curate or (
            str(row["status"]) == "ACTIVE"
            and not bool(row["hidden"])
            and latest_version_id is not None
            and _snapshot_is_browsable(
                latest_members,
                collection_namespace=namespace,
                current_user_id=current_user_id,
                namespace_role=namespace_context.get("namespace_role"),
                platform_roles=platform_roles,
            )
        )
        if visible:
            items.append(_collection_summary(row, can_curate=can_curate))
    return {"items": items, "total": len(items)}


async def get_collection(
    engine: Any,
    *,
    namespace: str,
    collection: str,
    current_user_id: str | None,
    platform_roles: list[str],
) -> dict[str, Any]:
    async with engine.connect() as connection:
        namespace_context = await _read_namespace_context(
            connection,
            namespace=namespace,
            current_user_id=current_user_id,
        )
        row = await _read_collection_row(
            connection,
            namespace_id=int(namespace_context["id"]),
            collection=collection,
        )
        if row is None:
            raise CollectionReadError("error.collection.notFound")
        version_ids = [
            int(version_id)
            for version_id in (row.get("latest_version_id"), row.get("draft_version_id"))
            if version_id is not None
        ]
        member_rows = await _read_members(connection, version_ids)

    grouped_members = _members_by_version(member_rows)
    can_curate = can_curate_collection(
        str(namespace_context["type"]),
        namespace_context.get("namespace_role"),
        platform_roles,
    )
    latest_version_id = row.get("latest_version_id")
    latest_members = grouped_members.get(int(latest_version_id), []) if latest_version_id is not None else []
    if not can_curate and (
        str(row["status"]) != "ACTIVE"
        or bool(row["hidden"])
        or latest_version_id is None
        or not _snapshot_is_browsable(
            latest_members,
            collection_namespace=namespace,
            current_user_id=current_user_id,
            namespace_role=namespace_context.get("namespace_role"),
            platform_roles=platform_roles,
        )
    ):
        raise CollectionReadError("error.collection.notFound")

    draft_version_id = row.get("draft_version_id")
    draft_members = grouped_members.get(int(draft_version_id), []) if draft_version_id is not None else []
    return {
        **_collection_summary(row, can_curate=can_curate),
        "latestPublishedVersion": _version_response(row, "latest", latest_members),
        "draft": _version_response(row, "draft", draft_members) if can_curate else None,
    }


async def _read_resolve_version(
    connection: Any,
    *,
    namespace_id: int,
    collection: str,
    version: str | None,
) -> dict[str, Any] | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT c.id AS collection_id, n.slug AS namespace,
                       c.slug AS collection_slug, c.status AS collection_status,
                       c.hidden AS collection_hidden, cv.id AS version_id,
                       cv.version, cv.status AS version_status
                FROM local_collection c
                JOIN namespace n ON n.id = c.namespace_id
                JOIN local_collection_version cv ON cv.collection_id = c.id
                WHERE c.namespace_id = :namespace_id
                  AND c.slug = :collection
                  AND c.status = 'ACTIVE'
                  AND c.hidden = FALSE
                  AND cv.status = 'PUBLISHED'
                  AND (
                    (
                      CAST(:version AS varchar) IS NULL
                      AND cv.id = c.latest_published_version_id
                    )
                    OR (
                      CAST(:version AS varchar) IS NOT NULL
                      AND cv.version = CAST(:version AS varchar)
                    )
                  )
                ORDER BY cv.id ASC
                LIMIT 1
                """
            ),
            {
                "namespace_id": namespace_id,
                "collection": collection,
                "version": version,
            },
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


async def resolve_collection(
    engine: Any,
    *,
    namespace: str,
    collection: str,
    version: str | None,
    current_user_id: str | None,
    platform_roles: list[str],
) -> dict[str, Any]:
    async with engine.begin() as connection:
        namespace_context = await _read_namespace_context(
            connection,
            namespace=namespace,
            current_user_id=current_user_id,
        )
        version_row = await _read_resolve_version(
            connection,
            namespace_id=int(namespace_context["id"]),
            collection=collection,
            version=version,
        )
        if version_row is None:
            raise CollectionReadError("error.collection.notFound")
        member_rows = await _read_members(connection, [int(version_row["version_id"])])
        if not member_rows or any(
            row.get("skill_id") is None or row.get("skill_version_id") is None
            for row in member_rows
        ):
            raise CollectionReadError(
                "error.collection.resolve.degraded",
                status_code=409,
            )
        if not _snapshot_is_browsable(
            member_rows,
            collection_namespace=namespace,
            current_user_id=current_user_id,
            namespace_role=namespace_context.get("namespace_role"),
            platform_roles=platform_roles,
        ):
            raise CollectionReadError(
                "error.collection.resolve.degraded",
                status_code=409,
            )
        skill_version_ids = [int(row["skill_version_id"]) for row in member_rows]
        file_rows = await _read_files(connection, skill_version_ids)

    files_by_version: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in file_rows:
        files_by_version[int(row["version_id"])].append(row)

    members = []
    for row in member_rows:
        skill_namespace = str(row["namespace"])
        skill_slug = str(row["skill_slug"])
        skill_version = str(row["version"])
        skill_version_id = int(row["skill_version_id"])
        members.append(
            {
                "namespace": skill_namespace,
                "slug": skill_slug,
                "version": skill_version,
                "versionId": skill_version_id,
                "fingerprint": compute_version_fingerprint(files_by_version[skill_version_id]),
                "downloadUrl": (
                    f"/api/cli/v1/skills/{quote(skill_namespace, safe='')}/"
                    f"{quote(skill_slug, safe='')}/versions/{quote(skill_version, safe='')}/download"
                ),
            }
        )
    return {
        "namespace": str(version_row["namespace"]),
        "slug": str(version_row["collection_slug"]),
        "version": str(version_row["version"]),
        "versionId": int(version_row["version_id"]),
        "members": members,
    }

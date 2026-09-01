from __future__ import annotations

from typing import Any
from urllib.parse import quote

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.skills.read_resolve import compute_version_fingerprint
from app.skills.read_responses import to_java_instant


class NamespaceManifestError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def parse_namespace_manifest_cursor(cursor: str | None) -> int:
    if cursor is None or cursor.strip() == "":
        return 0
    try:
        page = int(cursor)
    except ValueError as exc:
        raise NamespaceManifestError("cursor must be a non-negative page number") from exc
    if page < 0:
        raise NamespaceManifestError("cursor must be a non-negative page number")
    return page


async def read_namespace_skill_manifest(
    engine: AsyncEngine,
    *,
    namespace: str,
    page: int,
    size: int,
    current_user_id: str,
) -> dict[str, object]:
    normalized_size = min(max(size, 1), 100)
    params: dict[str, object] = {
        "namespace": namespace,
        "current_user_id": current_user_id,
        "limit": normalized_size,
        "offset": page * normalized_size,
    }
    access_sql = """
        s.hidden = FALSE
        AND (
            s.visibility = 'PUBLIC'
            OR (
                s.visibility = 'NAMESPACE_ONLY'
                AND EXISTS (
                    SELECT 1
                    FROM namespace_member member
                    WHERE member.namespace_id = s.namespace_id
                      AND member.user_id = :current_user_id
                )
            )
            OR (
                s.visibility = 'PRIVATE'
                AND (
                    s.owner_id = :current_user_id
                    OR EXISTS (
                        SELECT 1
                        FROM namespace_member manager
                        WHERE manager.namespace_id = s.namespace_id
                          AND manager.user_id = :current_user_id
                          AND manager.role IN ('OWNER', 'ADMIN')
                    )
                )
            )
        )
    """

    async with engine.connect() as connection:
        namespace_row = (
            await connection.execute(
                text(
                    """
                    SELECT id
                    FROM namespace
                    WHERE slug = :namespace
                      AND status = 'ACTIVE'
                    LIMIT 1
                    """
                ),
                {"namespace": namespace},
            )
        ).mappings().one_or_none()
        if namespace_row is None:
            raise NamespaceManifestError("error.namespace.slug.notFound")

        params["namespace_id"] = int(namespace_row["id"])
        total = int(
            (
                await connection.execute(
                    text(
                        f"""
                        SELECT COUNT(*)
                        FROM skill s
                        JOIN LATERAL (
                            SELECT candidate.id
                            FROM skill_version candidate
                            WHERE candidate.skill_id = s.id
                              AND candidate.status = 'PUBLISHED'
                              AND candidate.download_ready = TRUE
                              AND candidate.yanked_at IS NULL
                            ORDER BY
                              CASE WHEN candidate.id = s.latest_version_id THEN 0 ELSE 1 END,
                              candidate.published_at DESC NULLS LAST,
                              candidate.created_at DESC NULLS LAST,
                              candidate.id DESC
                            LIMIT 1
                        ) sv ON TRUE
                        WHERE s.namespace_id = :namespace_id
                          AND s.status = 'ACTIVE'
                          AND {access_sql}
                        """
                    ),
                    params,
                )
            ).scalar_one()
        )
        rows = (
            await connection.execute(
                text(
                    f"""
                    SELECT s.id AS skill_id,
                           s.slug,
                           s.visibility,
                           s.updated_at,
                           sv.id AS version_id,
                           sv.version
                    FROM skill s
                    JOIN LATERAL (
                        SELECT candidate.id,
                               candidate.version
                        FROM skill_version candidate
                        WHERE candidate.skill_id = s.id
                          AND candidate.status = 'PUBLISHED'
                          AND candidate.download_ready = TRUE
                          AND candidate.yanked_at IS NULL
                        ORDER BY
                          CASE WHEN candidate.id = s.latest_version_id THEN 0 ELSE 1 END,
                          candidate.published_at DESC NULLS LAST,
                          candidate.created_at DESC NULLS LAST,
                          candidate.id DESC
                        LIMIT 1
                    ) sv ON TRUE
                    WHERE s.namespace_id = :namespace_id
                      AND s.status = 'ACTIVE'
                      AND {access_sql}
                    ORDER BY s.slug ASC, s.id ASC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            )
        ).mappings().all()

        version_ids = [int(row["version_id"]) for row in rows]
        file_rows = []
        if version_ids:
            file_rows = (
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

    files_by_version: dict[int, list[dict[str, Any]]] = {
        version_id: [] for version_id in version_ids
    }
    for file_row in file_rows:
        files_by_version[int(file_row["version_id"])].append(dict(file_row))

    items: list[dict[str, object]] = []
    for row in rows:
        version_id = int(row["version_id"])
        slug = str(row["slug"])
        version = str(row["version"])
        items.append(
            {
                "namespace": namespace,
                "slug": slug,
                "version": version,
                "versionId": version_id,
                "fingerprint": compute_version_fingerprint(
                    files_by_version[version_id]
                ),
                "updatedAt": to_java_instant(row["updated_at"]),
                "visibility": str(row["visibility"]),
                "downloadUrl": (
                    f"/api/v1/skills/{quote(namespace, safe='')}/"
                    f"{quote(slug, safe='')}/versions/{quote(version, safe='')}/download"
                ),
            }
        )

    has_next = page * normalized_size + len(items) < total
    return {
        "items": items,
        "nextCursor": str(page + 1) if has_next else None,
    }


__all__ = [
    "NamespaceManifestError",
    "parse_namespace_manifest_cursor",
    "read_namespace_skill_manifest",
]

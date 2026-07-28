from __future__ import annotations

from typing import Any

from sqlalchemy import text


class CollectionMutationRepository:
    async def read_namespace_for_update(
        self,
        connection: Any,
        *,
        namespace: str,
        actor_user_id: str,
    ) -> dict[str, Any] | None:
        row = (
            await connection.execute(
                text(
                    """
                    SELECT n.id, n.slug, n.type, n.status,
                           (
                               SELECT nm.role
                               FROM namespace_member nm
                               WHERE nm.namespace_id = n.id
                                 AND nm.user_id = :actor_user_id
                               LIMIT 1
                           ) AS namespace_role
                    FROM namespace n
                    WHERE n.slug = :namespace
                    FOR UPDATE OF n
                    """
                ),
                {
                    "namespace": namespace,
                    "actor_user_id": actor_user_id,
                },
            )
        ).mappings().one_or_none()
        return dict(row) if row is not None else None

    async def read_collection_for_update(
        self,
        connection: Any,
        *,
        namespace_id: int,
        collection: str,
    ) -> dict[str, Any] | None:
        row = (
            await connection.execute(
                text(
                    """
                    SELECT id, namespace_id, slug, display_name, summary,
                           status, hidden, latest_published_version_id,
                           created_by, updated_by, created_at, updated_at
                    FROM local_collection
                    WHERE namespace_id = :namespace_id
                      AND slug = :collection
                    FOR UPDATE
                    """
                ),
                {
                    "namespace_id": namespace_id,
                    "collection": collection,
                },
            )
        ).mappings().one_or_none()
        return dict(row) if row is not None else None

    async def read_collection_by_id(
        self,
        connection: Any,
        collection_id: int,
    ) -> dict[str, Any] | None:
        row = (
            await connection.execute(
                text(
                    """
                    SELECT id, namespace_id, slug, display_name, summary,
                           status, hidden, latest_published_version_id,
                           created_by, updated_by, created_at, updated_at
                    FROM local_collection
                    WHERE id = :collection_id
                    LIMIT 1
                    """
                ),
                {"collection_id": collection_id},
            )
        ).mappings().one_or_none()
        return dict(row) if row is not None else None

    async def delete_expired_idempotency(
        self,
        connection: Any,
        idempotency_key: str,
    ) -> None:
        await connection.execute(
            text(
                """
                DELETE FROM idempotency_record
                WHERE request_id = :request_id
                  AND expires_at <= CURRENT_TIMESTAMP
                """
            ),
            {"request_id": idempotency_key},
        )

    async def read_idempotency(
        self,
        connection: Any,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        row = (
            await connection.execute(
                text(
                    """
                    SELECT request_id, resource_type, resource_id, status,
                           response_status_code, created_at, expires_at
                    FROM idempotency_record
                    WHERE request_id = :request_id
                    FOR UPDATE
                    """
                ),
                {"request_id": idempotency_key},
            )
        ).mappings().one_or_none()
        return dict(row) if row is not None else None

    async def reserve_idempotency(
        self,
        connection: Any,
        *,
        idempotency_key: str,
        resource_type: str,
    ) -> bool:
        row = (
            await connection.execute(
                text(
                    """
                    INSERT INTO idempotency_record (
                        request_id, resource_type, resource_id, status,
                        response_status_code, created_at, expires_at
                    )
                    VALUES (
                        :request_id, :resource_type, NULL, 'IN_PROGRESS',
                        NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '24 hours'
                    )
                    ON CONFLICT (request_id) DO NOTHING
                    RETURNING request_id
                    """
                ),
                {
                    "request_id": idempotency_key,
                    "resource_type": resource_type,
                },
            )
        ).mappings().one_or_none()
        return row is not None

    async def complete_idempotency(
        self,
        connection: Any,
        *,
        idempotency_key: str,
        resource_id: int,
        response_status_code: int = 200,
    ) -> None:
        await connection.execute(
            text(
                """
                UPDATE idempotency_record
                SET resource_id = :resource_id,
                    status = 'COMPLETED',
                    response_status_code = :response_status_code
                WHERE request_id = :request_id
                  AND status = 'IN_PROGRESS'
                """
            ),
            {
                "request_id": idempotency_key,
                "resource_id": resource_id,
                "response_status_code": response_status_code,
            },
        )

    async def insert_collection(
        self,
        connection: Any,
        *,
        namespace_id: int,
        slug: str,
        display_name: str,
        summary: str,
        actor_user_id: str,
    ) -> dict[str, Any]:
        row = (
            await connection.execute(
                text(
                    """
                    INSERT INTO local_collection (
                        namespace_id, slug, display_name, summary, status,
                        hidden, created_by, updated_by, created_at, updated_at
                    )
                    VALUES (
                        :namespace_id, :slug, :display_name, :summary, 'ACTIVE',
                        FALSE, :actor_user_id, :actor_user_id,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    RETURNING id, namespace_id, slug, display_name, summary,
                              status, hidden, latest_published_version_id,
                              created_by, updated_by, created_at, updated_at
                    """
                ),
                {
                    "namespace_id": namespace_id,
                    "slug": slug,
                    "display_name": display_name,
                    "summary": summary,
                    "actor_user_id": actor_user_id,
                },
            )
        ).mappings().one()
        return dict(row)

    async def read_draft_for_update(
        self,
        connection: Any,
        collection_id: int,
    ) -> dict[str, Any] | None:
        row = (
            await connection.execute(
                text(
                    """
                    SELECT id, collection_id, version, status, draft_revision,
                           release_notes, created_by, published_by,
                           created_at, published_at
                    FROM local_collection_version
                    WHERE collection_id = :collection_id
                      AND status = 'DRAFT'
                    FOR UPDATE
                    """
                ),
                {"collection_id": collection_id},
            )
        ).mappings().one_or_none()
        return dict(row) if row is not None else None

    async def insert_draft(
        self,
        connection: Any,
        *,
        collection_id: int,
        actor_user_id: str,
    ) -> dict[str, Any]:
        row = (
            await connection.execute(
                text(
                    """
                    INSERT INTO local_collection_version (
                        collection_id, version, status, draft_revision,
                        release_notes, created_by, created_at
                    )
                    VALUES (
                        :collection_id, 'draft', 'DRAFT', 1,
                        NULL, :actor_user_id, CURRENT_TIMESTAMP
                    )
                    RETURNING id, collection_id, version, status,
                              draft_revision, release_notes, created_by,
                              published_by, created_at, published_at
                    """
                ),
                {
                    "collection_id": collection_id,
                    "actor_user_id": actor_user_id,
                },
            )
        ).mappings().one()
        return dict(row)

    async def clone_members(
        self,
        connection: Any,
        *,
        source_version_id: int,
        target_version_id: int,
    ) -> None:
        await connection.execute(
            text(
                """
                INSERT INTO local_collection_version_member (
                    collection_version_id, skill_id, skill_version_id,
                    skill_slug_snapshot, skill_version_snapshot,
                    skill_owner_id_snapshot, skill_visibility_snapshot,
                    position, note
                )
                SELECT :target_version_id, skill_id, skill_version_id,
                       skill_slug_snapshot, skill_version_snapshot,
                       skill_owner_id_snapshot, skill_visibility_snapshot,
                       position, note
                FROM local_collection_version_member
                WHERE collection_version_id = :source_version_id
                ORDER BY position ASC, id ASC
                """
            ),
            {
                "source_version_id": source_version_id,
                "target_version_id": target_version_id,
            },
        )

    async def update_collection_metadata(
        self,
        connection: Any,
        *,
        collection_id: int,
        display_name: str,
        summary: str,
        actor_user_id: str,
    ) -> None:
        await connection.execute(
            text(
                """
                UPDATE local_collection
                SET display_name = :display_name,
                    summary = :summary,
                    updated_by = :actor_user_id,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :collection_id
                """
            ),
            {
                "collection_id": collection_id,
                "display_name": display_name,
                "summary": summary,
                "actor_user_id": actor_user_id,
            },
        )

    async def delete_draft_members(
        self,
        connection: Any,
        draft_id: int,
    ) -> None:
        await connection.execute(
            text(
                """
                DELETE FROM local_collection_version_member
                WHERE collection_version_id = :draft_id
                """
            ),
            {"draft_id": draft_id},
        )

    async def read_skill_version_reference(
        self,
        connection: Any,
        *,
        namespace_id: int,
        skill_id: int,
        skill_version_id: int,
    ) -> dict[str, Any] | None:
        row = (
            await connection.execute(
                text(
                    """
                    SELECT s.id AS skill_id, sv.id AS skill_version_id,
                           s.slug AS skill_slug_snapshot,
                           sv.version AS skill_version_snapshot,
                           s.owner_id AS skill_owner_id_snapshot,
                           s.visibility AS skill_visibility_snapshot,
                           s.namespace_id, s.status AS skill_status,
                           s.hidden AS skill_hidden, sv.status AS version_status,
                           sv.download_ready, sv.yanked_at
                    FROM skill s
                    JOIN skill_version sv ON sv.skill_id = s.id
                    WHERE s.id = :skill_id
                      AND sv.id = :skill_version_id
                      AND sv.skill_id = s.id
                      AND s.namespace_id = :namespace_id
                      AND s.status = 'ACTIVE'
                      AND s.hidden = FALSE
                      AND sv.status = 'PUBLISHED'
                      AND sv.download_ready = TRUE
                      AND sv.yanked_at IS NULL
                    FOR KEY SHARE OF s, sv
                    """
                ),
                {
                    "namespace_id": namespace_id,
                    "skill_id": skill_id,
                    "skill_version_id": skill_version_id,
                },
            )
        ).mappings().one_or_none()
        return dict(row) if row is not None else None

    async def insert_draft_member(
        self,
        connection: Any,
        *,
        draft_id: int,
        skill_id: int,
        skill_version_id: int,
        skill_slug_snapshot: str,
        skill_version_snapshot: str,
        skill_owner_id_snapshot: str,
        skill_visibility_snapshot: str,
        position: int,
        note: str | None,
    ) -> None:
        await connection.execute(
            text(
                """
                INSERT INTO local_collection_version_member (
                    collection_version_id, skill_id, skill_version_id,
                    skill_slug_snapshot, skill_version_snapshot,
                    skill_owner_id_snapshot, skill_visibility_snapshot,
                    position, note
                )
                VALUES (
                    :draft_id, :skill_id, :skill_version_id,
                    :skill_slug_snapshot, :skill_version_snapshot,
                    :skill_owner_id_snapshot, :skill_visibility_snapshot,
                    :position, :note
                )
                """
            ),
            {
                "draft_id": draft_id,
                "skill_id": skill_id,
                "skill_version_id": skill_version_id,
                "skill_slug_snapshot": skill_slug_snapshot,
                "skill_version_snapshot": skill_version_snapshot,
                "skill_owner_id_snapshot": skill_owner_id_snapshot,
                "skill_visibility_snapshot": skill_visibility_snapshot,
                "position": position,
                "note": note,
            },
        )

    async def increment_draft_revision(
        self,
        connection: Any,
        *,
        draft_id: int,
        expected_revision: int,
        release_notes: str | None,
    ) -> dict[str, Any] | None:
        row = (
            await connection.execute(
                text(
                    """
                    UPDATE local_collection_version
                    SET draft_revision = draft_revision + 1,
                        release_notes = :release_notes
                    WHERE id = :draft_id
                      AND status = 'DRAFT'
                      AND draft_revision = :expected_revision
                    RETURNING id, collection_id, version, status,
                              draft_revision, release_notes, created_by,
                              published_by, created_at, published_at
                    """
                ),
                {
                    "draft_id": draft_id,
                    "expected_revision": expected_revision,
                    "release_notes": release_notes,
                },
            )
        ).mappings().one_or_none()
        return dict(row) if row is not None else None

    async def delete_draft(
        self,
        connection: Any,
        draft_id: int,
    ) -> bool:
        row = (
            await connection.execute(
                text(
                    """
                    DELETE FROM local_collection_version
                    WHERE id = :draft_id
                      AND status = 'DRAFT'
                    RETURNING id
                    """
                ),
                {"draft_id": draft_id},
            )
        ).mappings().one_or_none()
        return row is not None

    async def read_draft_members_for_publish(
        self,
        connection: Any,
        draft_id: int,
    ) -> list[dict[str, Any]]:
        rows = (
            await connection.execute(
                text(
                    """
                    SELECT member.skill_id, member.skill_version_id,
                           member.skill_slug_snapshot,
                           member.skill_version_snapshot,
                           member.skill_owner_id_snapshot,
                           member.skill_visibility_snapshot,
                           member.position, member.note, s.namespace_id,
                           sv.skill_id AS version_skill_id,
                           s.status AS skill_status, s.hidden AS skill_hidden,
                           sv.status AS version_status, sv.download_ready,
                           sv.yanked_at
                    FROM local_collection_version_member member
                    LEFT JOIN skill s ON s.id = member.skill_id
                    LEFT JOIN skill_version sv ON sv.id = member.skill_version_id
                    WHERE member.collection_version_id = :draft_id
                    ORDER BY member.position ASC, member.id ASC
                    FOR UPDATE OF member
                    """
                ),
                {"draft_id": draft_id},
            )
        ).mappings().all()
        return [dict(row) for row in rows]

    async def read_latest_version_for_update(
        self,
        connection: Any,
        latest_version_id: int,
    ) -> dict[str, Any] | None:
        row = (
            await connection.execute(
                text(
                    """
                    SELECT id, collection_id, version, status, draft_revision,
                           release_notes, created_by, published_by,
                           created_at, published_at
                    FROM local_collection_version
                    WHERE id = :latest_version_id
                    FOR UPDATE
                    """
                ),
                {"latest_version_id": latest_version_id},
            )
        ).mappings().one_or_none()
        return dict(row) if row is not None else None

    async def publish_draft(
        self,
        connection: Any,
        *,
        draft_id: int,
        expected_revision: int,
        version: str,
        actor_user_id: str,
    ) -> dict[str, Any] | None:
        row = (
            await connection.execute(
                text(
                    """
                    UPDATE local_collection_version
                    SET version = :version,
                        status = 'PUBLISHED',
                        published_by = :actor_user_id,
                        published_at = CURRENT_TIMESTAMP
                    WHERE id = :draft_id
                      AND status = 'DRAFT'
                      AND draft_revision = :expected_revision
                    RETURNING id, collection_id, version, status,
                              draft_revision, release_notes, created_by,
                              published_by, created_at, published_at
                    """
                ),
                {
                    "draft_id": draft_id,
                    "expected_revision": expected_revision,
                    "version": version,
                    "actor_user_id": actor_user_id,
                },
            )
        ).mappings().one_or_none()
        return dict(row) if row is not None else None

    async def update_latest_published_version(
        self,
        connection: Any,
        *,
        collection_id: int,
        version_id: int,
        actor_user_id: str,
    ) -> None:
        await connection.execute(
            text(
                """
                UPDATE local_collection
                SET latest_published_version_id = :version_id,
                    updated_by = :actor_user_id,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :collection_id
                """
            ),
            {
                "collection_id": collection_id,
                "version_id": version_id,
                "actor_user_id": actor_user_id,
            },
        )

    async def read_published_version_by_id(
        self,
        connection: Any,
        version_id: int,
    ) -> dict[str, Any] | None:
        row = (
            await connection.execute(
                text(
                    """
                    SELECT id, collection_id, version, status, draft_revision,
                           release_notes, created_by, published_by,
                           created_at, published_at
                    FROM local_collection_version
                    WHERE id = :version_id
                      AND status = 'PUBLISHED'
                    LIMIT 1
                    """
                ),
                {"version_id": version_id},
            )
        ).mappings().one_or_none()
        return dict(row) if row is not None else None

    async def update_collection_status(
        self,
        connection: Any,
        *,
        collection_id: int,
        status: str,
        actor_user_id: str,
    ) -> dict[str, Any]:
        row = (
            await connection.execute(
                text(
                    """
                    UPDATE local_collection
                    SET status = :status,
                        updated_by = :actor_user_id,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :collection_id
                    RETURNING id, namespace_id, slug, display_name, summary,
                              status, hidden, latest_published_version_id,
                              created_by, updated_by, created_at, updated_at
                    """
                ),
                {
                    "collection_id": collection_id,
                    "status": status,
                    "actor_user_id": actor_user_id,
                },
            )
        ).mappings().one()
        return dict(row)


collection_mutation_repository = CollectionMutationRepository()

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any

from sqlalchemy import text

from app.audit.writer import write_audit_log
from app.collections.access import require_collection_curator
from app.db.unit_of_work import transaction_connection
from app.repository_imports.discovery import RepositorySkillCandidate
from app.repository_imports.gitlab_client import GitLabPreviewSource


class RepositoryImportRepositoryError(ValueError):
    def __init__(self, detail: str, *, status_code: int = 400) -> None:
        super().__init__(detail)
        self.status_code = status_code


class RepositoryImportRepository:
    async def authorize_namespace(
        self,
        engine: Any,
        *,
        namespace: str,
        actor_user_id: str,
        platform_roles: list[str],
    ) -> dict[str, Any]:
        async with transaction_connection(engine) as connection:
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
                        """
                    ),
                    {"namespace": namespace, "actor_user_id": actor_user_id},
                )
            ).mappings().one_or_none()
        if row is None:
            raise RepositoryImportRepositoryError(
                "error.repositoryImport.notFound",
                status_code=404,
            )
        result = dict(row)
        require_collection_curator(
            namespace_type=str(result["type"]),
            namespace_status=str(result["status"]),
            namespace_role=result.get("namespace_role"),
            platform_roles=platform_roles,
        )
        return result

    async def create_preview(
        self,
        engine: Any,
        *,
        namespace_row: dict[str, Any],
        actor_user_id: str,
        source: GitLabPreviewSource,
        upstream_url: str | None,
        candidates: list[RepositorySkillCandidate],
        request_id: str | None,
        client_ip: str | None,
        user_agent: str | None,
        previous_import_id: int | None = None,
    ) -> dict[str, Any]:
        async with transaction_connection(engine) as connection:
            import_row = (
                await connection.execute(
                    text(
                        """
                        INSERT INTO local_repository_import (
                            namespace_id, actor_id, provider, connection_key,
                            project_id, project_full_path, requested_ref,
                            resolved_commit_sha, source_web_url, upstream_url,
                            archive_sha256, archive_bytes, state, error_code,
                            previous_import_id, created_at, updated_at
                        )
                        VALUES (
                            :namespace_id, :actor_id, 'GITLAB', 'internal-gitlab',
                            :project_id, :project_full_path, :requested_ref,
                            :resolved_commit_sha, :source_web_url, :upstream_url,
                            :archive_sha256, :archive_bytes, 'PREVIEW_READY', NULL,
                            :previous_import_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "namespace_id": int(namespace_row["id"]),
                        "actor_id": actor_user_id,
                        "project_id": source.project_id,
                        "project_full_path": source.project_full_path,
                        "requested_ref": source.requested_ref,
                        "resolved_commit_sha": source.commit_sha,
                        "source_web_url": source.source_web_url,
                        "upstream_url": upstream_url,
                        "archive_sha256": source.archive_sha256,
                        "archive_bytes": len(source.archive),
                        "previous_import_id": previous_import_id,
                    },
                )
            ).mappings().one()
            import_id = int(import_row["id"])
            candidate_rows: list[dict[str, Any]] = []
            for candidate in candidates:
                row = (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO local_repository_import_candidate (
                                import_id, source_path, detected_name,
                                detected_description, source_version, state,
                                warnings_json, created_at, updated_at
                            )
                            VALUES (
                                :import_id, :source_path, :detected_name,
                                :detected_description, :source_version,
                                'DISCOVERED', CAST(:warnings_json AS JSONB),
                                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                            )
                            RETURNING id
                            """
                        ),
                        {
                            "import_id": import_id,
                            "source_path": candidate.source_path,
                            "detected_name": candidate.detected_name,
                            "detected_description": candidate.detected_description,
                            "source_version": candidate.source_version,
                            "warnings_json": json.dumps(candidate.warnings),
                        },
                    )
                ).mappings().one()
                candidate_rows.append(
                    {
                        "candidate_id": int(row["id"]),
                        "source_path": candidate.source_path,
                        "detected_name": candidate.detected_name,
                        "detected_description": candidate.detected_description,
                        "source_version": candidate.source_version,
                        "state": "DISCOVERED",
                        "warnings": candidate.warnings,
                    }
                )
            await write_audit_log(
                connection,
                actor_user_id=actor_user_id,
                action="REPOSITORY_IMPORT_PREVIEW",
                target_type="REPOSITORY_IMPORT",
                target_id=import_id,
                request_id=request_id,
                client_ip=client_ip,
                user_agent=user_agent,
                detail={
                    "namespace": namespace_row["slug"],
                    "projectFullPath": source.project_full_path,
                    "resolvedCommitSha": source.commit_sha,
                    "candidateCount": len(candidate_rows),
                },
                created_at=datetime.now(UTC),
            )
        return {
            "import_id": import_id,
            "namespace": namespace_row["slug"],
            "provider": "GITLAB",
            "project_id": source.project_id,
            "project_full_path": source.project_full_path,
            "requested_ref": source.requested_ref,
            "resolved_commit_sha": source.commit_sha,
            "source_web_url": source.source_web_url,
            "upstream_url": upstream_url,
            "archive_sha256": source.archive_sha256,
            "archive_bytes": len(source.archive),
            "state": "PREVIEW_READY",
            "previous_import_id": previous_import_id,
            "candidates": candidate_rows,
        }

    async def read_authorized_import(
        self,
        engine: Any,
        *,
        import_id: int,
        actor_user_id: str,
        platform_roles: list[str],
    ) -> dict[str, Any]:
        async with transaction_connection(engine) as connection:
            row = (
                await connection.execute(
                    text(
                        """
                        SELECT ri.*, n.slug AS namespace, n.type AS namespace_type,
                               n.status AS namespace_status,
                               (
                                   SELECT nm.role
                                   FROM namespace_member nm
                                   WHERE nm.namespace_id = n.id
                                     AND nm.user_id = :actor_user_id
                                   LIMIT 1
                               ) AS namespace_role
                        FROM local_repository_import ri
                        JOIN namespace n ON n.id = ri.namespace_id
                        WHERE ri.id = :import_id
                        """
                    ),
                    {"import_id": import_id, "actor_user_id": actor_user_id},
                )
            ).mappings().one_or_none()
        if row is None:
            raise RepositoryImportRepositoryError(
                "error.repositoryImport.notFound",
                status_code=404,
            )
        result = dict(row)
        require_collection_curator(
            namespace_type=str(result["namespace_type"]),
            namespace_status=str(result["namespace_status"]),
            namespace_role=result.get("namespace_role"),
            platform_roles=platform_roles,
        )
        return result

    async def read_candidates(
        self,
        engine: Any,
        import_id: int,
    ) -> list[dict[str, Any]]:
        async with transaction_connection(engine) as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT ric.id AS candidate_id, ric.source_path,
                               ric.detected_name, ric.detected_description,
                               ric.source_version, ric.target_slug,
                               ric.target_version, ric.visibility, ric.state,
                               ric.skill_id, ric.skill_version_id,
                               ric.warnings_json, ric.error_code,
                               sv.status AS version_status
                        FROM local_repository_import_candidate ric
                        LEFT JOIN skill_version sv
                          ON sv.id = ric.skill_version_id
                        WHERE ric.import_id = :import_id
                        ORDER BY ric.id
                        """
                    ),
                    {"import_id": import_id},
                )
            ).mappings().all()
        return [
            {
                **dict(row),
                "warnings": list(row.get("warnings_json") or []),
            }
            for row in rows
        ]

    async def claim_ingest(
        self,
        engine: Any,
        *,
        import_id: int,
        operation_id: str,
        actor_user_id: str,
        request_id: str | None,
        client_ip: str | None,
        user_agent: str | None,
    ) -> bool:
        async with transaction_connection(engine) as connection:
            row = (
                await connection.execute(
                    text(
                        """
                        UPDATE local_repository_import
                        SET state = 'INGESTING',
                            error_code = NULL,
                            ingest_operation_id = :operation_id,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :import_id
                          AND state = 'PREVIEW_READY'
                        RETURNING id
                        """
                    ),
                    {
                        "import_id": import_id,
                        "operation_id": operation_id,
                    },
                )
            ).mappings().one_or_none()
            if row is not None:
                await write_audit_log(
                    connection,
                    actor_user_id=actor_user_id,
                    action="REPOSITORY_IMPORT_INGEST_STARTED",
                    target_type="REPOSITORY_IMPORT",
                    target_id=import_id,
                    request_id=request_id,
                    client_ip=client_ip,
                    user_agent=user_agent,
                    detail={"operationId": operation_id},
                    created_at=datetime.now(UTC),
                )
        return row is not None

    async def mark_candidate_selected(
        self,
        engine: Any,
        *,
        candidate_id: int,
        operation_id: str,
        target_slug: str,
        target_version: str,
        visibility: str,
    ) -> bool:
        async with transaction_connection(engine) as connection:
            row = (
                await connection.execute(
                    text(
                        """
                        UPDATE local_repository_import_candidate AS candidate
                        SET target_slug = :target_slug,
                            target_version = :target_version,
                            visibility = :visibility,
                            state = 'SELECTED',
                            error_code = NULL,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE candidate.id = :candidate_id
                          AND candidate.state <> 'CREATED'
                          AND EXISTS (
                              SELECT 1
                              FROM local_repository_import parent
                              WHERE parent.id = candidate.import_id
                                AND parent.state = 'INGESTING'
                                AND parent.ingest_operation_id = :operation_id
                          )
                        RETURNING candidate.id
                        """
                    ),
                    {
                        "candidate_id": candidate_id,
                        "operation_id": operation_id,
                        "target_slug": target_slug,
                        "target_version": target_version,
                        "visibility": visibility,
                    },
                )
            ).mappings().one_or_none()
        return row is not None

    async def mark_candidate_result(
        self,
        engine: Any,
        *,
        candidate_id: int,
        operation_id: str,
        skill_id: int | None,
        skill_version_id: int | None,
        error_code: str | None,
    ) -> bool:
        async with transaction_connection(engine) as connection:
            row = (
                await connection.execute(
                    text(
                        """
                        UPDATE local_repository_import_candidate AS candidate
                        SET state = :state,
                            skill_id = :skill_id,
                            skill_version_id = :skill_version_id,
                            error_code = :error_code,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE candidate.id = :candidate_id
                          AND candidate.state = 'SELECTED'
                          AND EXISTS (
                              SELECT 1
                              FROM local_repository_import parent
                              WHERE parent.id = candidate.import_id
                                AND parent.state = 'INGESTING'
                                AND parent.ingest_operation_id = :operation_id
                          )
                        RETURNING candidate.id
                        """
                    ),
                    {
                        "candidate_id": candidate_id,
                        "operation_id": operation_id,
                        "state": "CREATED" if error_code is None else "FAILED",
                        "skill_id": skill_id,
                        "skill_version_id": skill_version_id,
                        "error_code": error_code,
                    },
                )
            ).mappings().one_or_none()
        return row is not None

    async def complete_ingest(
        self,
        engine: Any,
        *,
        import_id: int,
        operation_id: str,
        state: str,
        error_code: str | None,
        actor_user_id: str,
        request_id: str | None,
        client_ip: str | None,
        user_agent: str | None,
    ) -> bool:
        async with transaction_connection(engine) as connection:
            row = (
                await connection.execute(
                    text(
                        """
                        UPDATE local_repository_import
                        SET state = :state,
                            error_code = :error_code,
                            ingest_operation_id = NULL,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :import_id
                          AND state = 'INGESTING'
                          AND ingest_operation_id = :operation_id
                        RETURNING id
                        """
                    ),
                    {
                        "import_id": import_id,
                        "operation_id": operation_id,
                        "state": state,
                        "error_code": error_code,
                    },
                )
            ).mappings().one_or_none()
            if row is None:
                return False
            await write_audit_log(
                connection,
                actor_user_id=actor_user_id,
                action="REPOSITORY_IMPORT_INGEST",
                target_type="REPOSITORY_IMPORT",
                target_id=import_id,
                request_id=request_id,
                client_ip=client_ip,
                user_agent=user_agent,
                detail={"state": state, "operationId": operation_id},
                created_at=datetime.now(UTC),
            )
        return True

    async def read_published_members(
        self,
        engine: Any,
        *,
        import_id: int,
        candidate_ids: list[int],
    ) -> list[dict[str, Any]]:
        async with transaction_connection(engine) as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT ric.id AS candidate_id, s.slug AS skill_slug,
                               sv.version, ric.skill_id, ric.skill_version_id
                        FROM local_repository_import_candidate ric
                        JOIN skill s ON s.id = ric.skill_id
                        JOIN skill_version sv ON sv.id = ric.skill_version_id
                        WHERE ric.import_id = :import_id
                          AND ric.id = ANY(:candidate_ids)
                          AND ric.state = 'CREATED'
                          AND sv.status = 'PUBLISHED'
                        ORDER BY ric.id
                        """
                    ),
                    {"import_id": import_id, "candidate_ids": candidate_ids},
                )
            ).mappings().all()
        return [dict(row) for row in rows]


repository_import_repository = RepositoryImportRepository()

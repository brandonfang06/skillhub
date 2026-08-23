from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.admin.search import rebuild_search_index
from app.publish.orchestration import PublishWriteInput, execute_publish_write
from app.publish.package import PackageEntry, validate_package
from app.review.query import read_review_skill_detail
from app.skills.read_repository import (
    read_skill_search,
    read_skill_version_detail,
    read_skill_versions,
)

TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")


def _entries(
    *, version: str, standard: str, control_id: str, evidence_marker: str
) -> list[PackageEntry]:
    skill_md = (
        "---\n"
        "name: Compliance Projection\n"
        "description: Compliance projection integration\n"
        f"version: {version}\n"
        "x-astron-compliance:\n"
        f"  - standard: {standard}\n"
        "    version: '2026'\n"
        f"    controlId: {control_id}\n"
        f"    title: {standard} control title\n"
        "    evidence:\n"
        "      - type: packaged-file\n"
        f"        path: references/{evidence_marker}.md\n"
        "---\n"
        "# Compliance Projection\n"
    ).encode()
    return [
        PackageEntry("SKILL.md", skill_md, "text/markdown"),
        PackageEntry(
            f"references/{evidence_marker}.md",
            evidence_marker.encode(),
            "text/markdown",
        ),
    ]


def _publish_input(
    tmp_path: Any,
    *,
    namespace_id: int,
    namespace_slug: str,
    publisher_id: str,
    slug: str,
    version: str,
    entries: list[PackageEntry],
) -> PublishWriteInput:
    validation = validate_package(entries)
    assert validation.valid
    assert validation.metadata is not None
    return PublishWriteInput(
        namespace_id=namespace_id,
        namespace_slug=namespace_slug,
        slug=slug,
        display_name=validation.metadata.name,
        summary=validation.metadata.description,
        publisher_id=publisher_id,
        visibility="PUBLIC",
        version=version,
        auto_publish=True,
        metadata=validation.metadata,
        entries=entries,
        storage_base_path=str(tmp_path),
    )


@pytest.mark.skipif(
    TEST_DATABASE_URL is None, reason="requires SKILLHUB_TEST_DATABASE_URL"
)
@pytest.mark.anyio
async def test_compliance_projects_and_searches_exact_immutable_versions_with_real_postgres(
    tmp_path: Any,
) -> None:
    suffix = uuid4().hex[:12]
    publisher_id = f"projection-publisher-{suffix}"
    namespace_slug = f"projection-{suffix}"
    slug = f"projection-skill-{suffix}"
    engine = create_async_engine(str(TEST_DATABASE_URL))
    namespace_id: int | None = None
    skill_id: int | None = None
    version_ids: list[int] = []
    review_task_id: int | None = None

    first_entries = _entries(
        version="1.0.0",
        standard="first-standard",
        control_id="FIRST-CONTROL",
        evidence_marker="first-evidence-never-index",
    )
    second_entries = _entries(
        version="2.0.0",
        standard="second-standard",
        control_id="SECOND-CONTROL",
        evidence_marker="second-evidence-never-index",
    )

    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO user_account (id, display_name) VALUES (:id, 'Projection publisher')"
                ),
                {"id": publisher_id},
            )
            namespace_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO namespace (slug, display_name, type, status, created_by)
                            VALUES (:slug, :slug, 'TEAM', 'ACTIVE', :publisher_id)
                            RETURNING id
                            """
                        ),
                        {"slug": namespace_slug, "publisher_id": publisher_id},
                    )
                ).scalar_one()
            )

        first = await execute_publish_write(
            engine,
            _publish_input(
                tmp_path,
                namespace_id=namespace_id,
                namespace_slug=namespace_slug,
                publisher_id=publisher_id,
                slug=slug,
                version="1.0.0",
                entries=first_entries,
            ),
        )
        second = await execute_publish_write(
            engine,
            _publish_input(
                tmp_path,
                namespace_id=namespace_id,
                namespace_slug=namespace_slug,
                publisher_id=publisher_id,
                slug=slug,
                version="2.0.0",
                entries=second_entries,
            ),
        )
        skill_id = first.skill_id
        version_ids.extend([first.version_id, second.version_id])

        async with engine.begin() as connection:
            review_task_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO review_task (
                                skill_version_id, namespace_id, status, submitted_by
                            )
                            VALUES (:version_id, :namespace_id, 'PENDING', :publisher_id)
                            RETURNING id
                            """
                        ),
                        {
                            "version_id": second.version_id,
                            "namespace_id": namespace_id,
                            "publisher_id": publisher_id,
                        },
                    )
                ).scalar_one()
            )
            malformed_ids = list(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO skill_version (
                                skill_id, version, status, parsed_metadata_json, created_by
                            )
                            VALUES
                                (:skill_id, 'historical-absent', 'UPLOADED', NULL, :publisher_id),
                                (:skill_id, 'historical-malformed', 'UPLOADED', '[]'::jsonb, :publisher_id)
                            RETURNING id
                            """
                        ),
                        {"skill_id": skill_id, "publisher_id": publisher_id},
                    )
                )
                .scalars()
                .all()
            )
            version_ids.extend(int(value) for value in malformed_ids)

        versions = await read_skill_versions(
            engine,
            namespace_slug,
            slug,
            page=0,
            size=20,
            current_user_id=publisher_id,
        )
        by_version = {str(item["version"]): item for item in versions["items"]}
        assert (
            by_version["1.0.0"]["complianceSnapshot"]["items"][0]["controlId"]
            == "FIRST-CONTROL"
        )
        assert (
            by_version["2.0.0"]["complianceSnapshot"]["items"][0]["controlId"]
            == "SECOND-CONTROL"
        )
        assert by_version["historical-absent"]["complianceSnapshot"] is None
        assert by_version["historical-malformed"]["complianceSnapshot"] is None

        first_detail = await read_skill_version_detail(
            engine,
            namespace_slug,
            slug,
            "1.0.0",
            current_user_id=publisher_id,
        )
        assert (
            first_detail["complianceSnapshot"]["items"][0]["standard"]
            == "first-standard"
        )

        second_search = await read_skill_search(
            engine,
            keyword="SECOND-CONTROL",
            namespace=namespace_slug,
            labels=[],
            sort="relevance",
            page=0,
            size=20,
        )
        assert [item["slug"] for item in second_search["items"]] == [slug]
        assert (
            second_search["items"][0]["complianceSnapshot"]["items"][0]["controlId"]
            == "SECOND-CONTROL"
        )
        first_search = await read_skill_search(
            engine,
            keyword="FIRST-CONTROL",
            namespace=namespace_slug,
            labels=[],
            sort="relevance",
            page=0,
            size=20,
        )
        assert first_search["items"] == []

        review = await read_review_skill_detail(
            engine,
            storage_base_path=str(tmp_path),
            review_task_id=review_task_id,
            user_id=publisher_id,
        )
        review_versions = {str(item["version"]): item for item in review["versions"]}
        assert (
            review_versions["1.0.0"]["complianceSnapshot"]["digest"]
            != review_versions["2.0.0"]["complianceSnapshot"]["digest"]
        )

        async with engine.connect() as connection:
            indexed = (
                (
                    await connection.execute(
                        text(
                            "SELECT keywords, search_text FROM skill_search_document WHERE skill_id = :skill_id"
                        ),
                        {"skill_id": skill_id},
                    )
                )
                .mappings()
                .one()
            )
        indexed_text = f"{indexed['keywords']} {indexed['search_text']}"
        assert "second-standard" in indexed_text
        assert "SECOND-CONTROL" in indexed_text
        assert "second-evidence-never-index" not in indexed_text
        assert "first-evidence-never-index" not in indexed_text

        await rebuild_search_index(
            engine,
            actor_user_id=publisher_id,
            platform_roles=["SUPER_ADMIN"],
            request_id="projection-rebuild",
            client_ip="127.0.0.1",
            user_agent="pytest",
        )
        rebuilt_search = await read_skill_search(
            engine,
            keyword="SECOND-CONTROL",
            namespace=namespace_slug,
            labels=[],
            sort="relevance",
            page=0,
            size=20,
        )
        assert [item["slug"] for item in rebuilt_search["items"]] == [slug]
    finally:
        async with engine.begin() as connection:
            if review_task_id is not None:
                await connection.execute(
                    text("DELETE FROM review_task WHERE id = :id"),
                    {"id": review_task_id},
                )
            if skill_id is not None:
                await connection.execute(
                    text("UPDATE skill SET latest_version_id = NULL WHERE id = :id"),
                    {"id": skill_id},
                )
                await connection.execute(
                    text("DELETE FROM skill_search_document WHERE skill_id = :id"),
                    {"id": skill_id},
                )
            if version_ids:
                await connection.execute(
                    text("DELETE FROM skill_file WHERE version_id = ANY(:ids)"),
                    {"ids": version_ids},
                )
                await connection.execute(
                    text("DELETE FROM skill_version WHERE id = ANY(:ids)"),
                    {"ids": version_ids},
                )
            if skill_id is not None:
                await connection.execute(
                    text("DELETE FROM skill WHERE id = :id"), {"id": skill_id}
                )
            if namespace_id is not None:
                await connection.execute(
                    text("DELETE FROM namespace WHERE id = :id"), {"id": namespace_id}
                )
            await connection.execute(
                text("DELETE FROM audit_log WHERE actor_user_id = :id"),
                {"id": publisher_id},
            )
            await connection.execute(
                text("DELETE FROM user_account WHERE id = :id"), {"id": publisher_id}
            )
        await engine.dispose()

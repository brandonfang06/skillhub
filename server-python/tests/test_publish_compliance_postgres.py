from __future__ import annotations

import json
import os
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.publish.compliance import ComplianceMetadataError
from app.publish.orchestration import PublishWriteInput, execute_publish_write
from app.publish.package import PackageEntry, SkillMetadata, validate_package


TEST_DATABASE_URL = os.getenv("SKILLHUB_TEST_DATABASE_URL")


def _entries(
    *,
    version: str,
    standard: str,
    control_id: str,
    evidence_content: bytes,
) -> list[PackageEntry]:
    skill_md = (
        "---\n"
        "name: Compliance Persistence\n"
        "description: Immutable compliance snapshot integration\n"
        f"version: {version}\n"
        "x-custom-field:\n"
        "  preserved: true\n"
        "x-astron-compliance:\n"
        f"  - standard: {standard}\n"
        "    version: '1'\n"
        f"    controlId: {control_id}\n"
        "    evidence:\n"
        "      - type: packaged-file\n"
        "        path: references/evidence.md\n"
        "---\n"
        "# Compliance Persistence\n"
    ).encode()
    return [
        PackageEntry("SKILL.md", skill_md, "text/markdown"),
        PackageEntry("references/evidence.md", evidence_content, "text/markdown"),
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


def _json_object(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        decoded = json.loads(value)
        assert isinstance(decoded, dict)
        return decoded
    assert isinstance(value, dict)
    return value


@pytest.mark.skipif(
    TEST_DATABASE_URL is None,
    reason="requires SKILLHUB_TEST_DATABASE_URL",
)
@pytest.mark.anyio
async def test_publish_persists_immutable_compliance_snapshots_without_a_migration(
    tmp_path: Any,
) -> None:
    suffix = uuid4().hex[:12]
    publisher_id = f"compliance-publisher-{suffix}"
    namespace_slug = f"compliance-{suffix}"
    slug = f"compliance-skill-{suffix}"
    engine = create_async_engine(str(TEST_DATABASE_URL))
    namespace_id: int | None = None

    first_entries = _entries(
        version="1.0.0",
        standard="MITRE-ATTACK",
        control_id="T1059",
        evidence_content=b"first evidence",
    )
    second_entries = _entries(
        version="2.0.0",
        standard="soc2",
        control_id="CC6.1",
        evidence_content=b"second evidence",
    )

    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO user_account (id, display_name) "
                    "VALUES (:publisher_id, 'Compliance publisher')"
                ),
                {"publisher_id": publisher_id},
            )
            namespace_id = int(
                (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO namespace (
                                slug, display_name, type, status, created_by
                            )
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

        invalid_metadata = SkillMetadata(
            name="Compliance Persistence",
            description="Immutable compliance snapshot integration",
            version="3.0.0",
            frontmatter={
                "name": "Compliance Persistence",
                "description": "Immutable compliance snapshot integration",
                "version": "3.0.0",
                "x-astron-compliance": [
                    {
                        "standard": "nist-csf",
                        "version": "2.0",
                        "controlId": "GV.OC-03",
                        "evidence": [
                            {
                                "type": "external-url",
                                "url": "https://exa mple.com/%zz",
                            }
                        ],
                    }
                ],
            },
        )
        with pytest.raises(ComplianceMetadataError, match="http or https URL"):
            await execute_publish_write(
                engine,
                PublishWriteInput(
                    namespace_id=namespace_id,
                    namespace_slug=namespace_slug,
                    slug=slug,
                    display_name=invalid_metadata.name,
                    summary=invalid_metadata.description,
                    publisher_id=publisher_id,
                    visibility="PUBLIC",
                    version="3.0.0",
                    auto_publish=True,
                    metadata=invalid_metadata,
                    entries=[PackageEntry("SKILL.md", b"# invalid\n", "text/markdown")],
                    storage_base_path=str(tmp_path),
                ),
            )

        async with engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT id, version, parsed_metadata_json
                        FROM skill_version
                        WHERE id IN (:first_version_id, :second_version_id)
                        ORDER BY version
                        """
                    ),
                    {
                        "first_version_id": first.version_id,
                        "second_version_id": second.version_id,
                    },
                )
            ).mappings().all()
            rejected_count = int(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM skill_version
                            WHERE skill_id = :skill_id
                              AND version = '3.0.0'
                            """
                        ),
                        {"skill_id": first.skill_id},
                    )
                ).scalar_one()
            )

        first_metadata = _json_object(rows[0]["parsed_metadata_json"])
        second_metadata = _json_object(rows[1]["parsed_metadata_json"])
        first_snapshot = first_metadata["complianceSnapshot"]
        second_snapshot = second_metadata["complianceSnapshot"]

        assert rows[0]["version"] == "1.0.0"
        assert rows[1]["version"] == "2.0.0"
        assert first_metadata["name"] == "Compliance Persistence"
        assert first_metadata["frontmatter"]["x-custom-field"] == {"preserved": True}
        assert first_snapshot["items"][0]["standard"] == "mitre-attack"
        assert first_snapshot["items"][0]["controlId"] == "T1059"
        assert second_snapshot["items"][0]["standard"] == "soc2"
        assert second_snapshot["items"][0]["controlId"] == "CC6.1"
        assert first_snapshot["digest"] != second_snapshot["digest"]
        assert rejected_count == 0
    finally:
        async with engine.begin() as connection:
            if namespace_id is not None:
                skill_ids = list(
                    (
                        await connection.execute(
                            text("SELECT id FROM skill WHERE namespace_id = :namespace_id"),
                            {"namespace_id": namespace_id},
                        )
                    ).scalars().all()
                )
                version_ids = list(
                    (
                        await connection.execute(
                            text(
                                """
                                SELECT version.id
                                FROM skill_version version
                                JOIN skill ON skill.id = version.skill_id
                                WHERE skill.namespace_id = :namespace_id
                                """
                            ),
                            {"namespace_id": namespace_id},
                        )
                    ).scalars().all()
                )
                if skill_ids:
                    await connection.execute(
                        text("UPDATE skill SET latest_version_id = NULL WHERE id = ANY(:skill_ids)"),
                        {"skill_ids": skill_ids},
                    )
                    await connection.execute(
                        text("DELETE FROM skill_search_document WHERE skill_id = ANY(:skill_ids)"),
                        {"skill_ids": skill_ids},
                    )
                if version_ids:
                    await connection.execute(
                        text("DELETE FROM skill_file WHERE version_id = ANY(:version_ids)"),
                        {"version_ids": version_ids},
                    )
                    await connection.execute(
                        text("DELETE FROM skill_version WHERE id = ANY(:version_ids)"),
                        {"version_ids": version_ids},
                    )
                if skill_ids:
                    await connection.execute(
                        text("DELETE FROM skill WHERE id = ANY(:skill_ids)"),
                        {"skill_ids": skill_ids},
                    )
                await connection.execute(
                    text("DELETE FROM namespace WHERE id = :namespace_id"),
                    {"namespace_id": namespace_id},
                )
            await connection.execute(
                text("DELETE FROM user_account WHERE id = :publisher_id"),
                {"publisher_id": publisher_id},
            )
        await engine.dispose()

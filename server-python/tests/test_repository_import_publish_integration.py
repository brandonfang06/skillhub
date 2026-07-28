import asyncio
from types import SimpleNamespace

from app.api.repository_imports import _publish_candidate, _seed_collection
from app.repository_imports.contracts import (
    RepositoryImportCollectionDraftRequest,
)
from app.core.config import get_settings
from app.publish.orchestration import PublishWriteResult
from app.publish.package import PackageEntry
from app.repository_imports.contracts import RepositoryImportSelection
from app.repository_imports.discovery import RepositorySkillCandidate
from app.repository_imports.service import RepositoryImportContext


def test_import_publisher_reuses_python_publish_write_boundary(monkeypatch) -> None:
    settings = get_settings()
    seen = []

    async def writer(write_input):
        seen.append(write_input)
        return SimpleNamespace(
            skill_id=10,
            version_id=20,
            version_status="PENDING",
        )

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                repository_import_publish_writer=writer,
            )
        )
    )
    candidate = RepositorySkillCandidate(
        source_path="alpha",
        detected_name="Alpha",
        detected_description="First",
        source_version="0.1.0",
        entries=[
            PackageEntry(
                path="SKILL.md",
                content=b"---\nname: Alpha\ndescription: First\nversion: 0.1.0\n---",
                content_type="text/markdown",
            )
        ],
        warnings=[],
    )
    result = asyncio.run(
        _publish_candidate(
            request,
            {"namespace_id": 7, "namespace": "opensource"},
            candidate,
            RepositoryImportSelection(
                candidate_id=1,
                target_slug="alpha",
                target_version="1.0.0",
                visibility="NAMESPACE_ONLY",
            ),
            RepositoryImportContext(
                actor_user_id="curator",
                platform_roles=[],
                request_id="req-1",
                client_ip="127.0.0.1",
                user_agent="pytest",
            ),
        )
    )

    assert result.version_status == "PENDING"
    assert seen[0].namespace_slug == "opensource"
    assert seen[0].slug == "alpha"
    assert seen[0].version == "1.0.0"
    assert seen[0].scanner_enabled == settings.security_scanner_enabled


def test_import_collection_seed_preserves_publisher_skill_and_version_ids(
    monkeypatch,
) -> None:
    captured = []

    async def read_detail(*_args, **_kwargs):
        return {"draft": {"draftRevision": 2}}

    async def replace_draft(*_args, **kwargs):
        captured.append(kwargs["payload"])
        return {"draftRevision": 3}

    monkeypatch.setattr(
        "app.api.repository_imports.read_collection_detail",
        read_detail,
    )
    monkeypatch.setattr(
        "app.api.repository_imports.replace_collection_draft",
        replace_draft,
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(db_engine=object()))
    )

    result = asyncio.run(
        _seed_collection(
            request,
            {"namespace": "opensource"},
            [
                {
                    "skill_id": 202,
                    "skill_version_id": 902,
                    "skill_slug": "duplicate-coordinate",
                    "version": "1.0.0",
                }
            ],
            RepositoryImportCollectionDraftRequest(
                collection_slug="superpowers",
                display_name="Superpowers",
                summary="Curated",
                candidate_ids=[1],
            ),
            RepositoryImportContext(
                actor_user_id="curator",
                platform_roles=[],
                request_id="req-1",
                client_ip="127.0.0.1",
                user_agent="pytest",
            ),
        )
    )

    member = captured[0].members[0]
    assert member.skill_id == 202
    assert member.skill_version_id == 902
    assert "skillSlug" not in member.model_dump(by_alias=True)
    assert "version" not in member.model_dump(by_alias=True)
    assert result["draft_revision"] == 3

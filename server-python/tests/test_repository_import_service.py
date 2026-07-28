import asyncio
from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zipfile import ZipFile

import pytest

import app.repository_imports.service as repository_import_service
from app.repository_imports.archive import RepositoryArchiveLimits
from app.repository_imports.contracts import RepositoryImportSelection
from app.repository_imports.gitlab_client import GitLabPreviewSource
from app.repository_imports.service import (
    ImportedSkillResult,
    RepositoryImportCandidatePublishError,
    RepositoryImportContext,
    RepositoryImportServiceError,
    check_repository_import_updates,
    ingest_repository_import,
    preview_repository_import,
    seed_repository_import_collection_draft,
)


def archive_bytes() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "repo/alpha/SKILL.md",
            "---\nname: Alpha\ndescription: First\nversion: 1.0.0\n---",
        )
        archive.writestr(
            "repo/beta/SKILL.md",
            "---\nname: Beta\ndescription: Second\nversion: 1.0.0\n---",
        )
    return buffer.getvalue()


def context() -> RepositoryImportContext:
    return RepositoryImportContext(
        actor_user_id="curator",
        platform_roles=[],
        request_id="req-1",
        client_ip="127.0.0.1",
        user_agent="pytest",
    )


class FakeClient:
    def __init__(self, archive: bytes) -> None:
        self.archive = archive

    async def preview_source(self, project_path: str, requested_ref: str):
        return GitLabPreviewSource(
            project_id="oss-mirrors/project",
            project_full_path=project_path,
            requested_ref=requested_ref,
            commit_sha="a" * 40,
            source_web_url="https://gitlab.internal/oss-mirrors/project",
            archive=self.archive,
            archive_sha256=sha256(self.archive).hexdigest(),
        )

    async def download_archive(self, project_path: str, commit_sha: str):
        assert project_path == "oss-mirrors/project"
        assert commit_sha == "a" * 40
        return self.archive


class FakeRepository:
    def __init__(self, archive: bytes) -> None:
        self.archive = archive
        self.created_kwargs = None
        self.rows = [
            {
                "candidate_id": 1,
                "source_path": "alpha",
                "state": "DISCOVERED",
                "version_status": None,
            },
            {
                "candidate_id": 2,
                "source_path": "beta",
                "state": "DISCOVERED",
                "version_status": None,
            },
        ]
        self.final_state = None
        self.state = "PREVIEW_READY"
        self.operation_id: str | None = None
        self.operation_ids: list[str] = []

    async def authorize_namespace(self, _engine, **_kwargs):
        return {
            "id": 7,
            "slug": "opensource",
            "type": "TEAM",
            "status": "ACTIVE",
            "namespace_role": "OWNER",
        }

    async def create_preview(self, _engine, **kwargs):
        self.created_kwargs = kwargs
        return {"import_id": 9, "candidates": kwargs["candidates"]}

    async def read_authorized_import(self, _engine, **_kwargs):
        return {
            "id": 9,
            "namespace_id": 7,
            "namespace": "opensource",
            "project_full_path": "oss-mirrors/project",
            "project_id": "oss-mirrors%2Fproject",
            "requested_ref": "main",
            "resolved_commit_sha": "a" * 40,
            "source_web_url": "https://gitlab.internal/oss-mirrors/project",
            "upstream_url": "https://github.com/example/project",
            "archive_sha256": sha256(self.archive).hexdigest(),
            "state": self.state,
        }

    async def read_candidates(self, _engine, _import_id):
        return self.rows

    async def claim_ingest(
        self,
        _engine,
        *,
        import_id,
        operation_id,
        actor_user_id,
        request_id,
        client_ip,
        user_agent,
    ):
        assert import_id == 9
        assert actor_user_id == "curator"
        assert request_id == "req-1"
        assert client_ip == "127.0.0.1"
        assert user_agent == "pytest"
        self.operation_ids.append(operation_id)
        if self.state != "PREVIEW_READY":
            return False
        self.state = "INGESTING"
        self.operation_id = operation_id
        return True

    async def mark_candidate_selected(self, _engine, **kwargs):
        operation_id = kwargs.get("operation_id")
        if (
            operation_id is not None
            and operation_id != self.operation_id
        ):
            return False
        row = next(item for item in self.rows if item["candidate_id"] == kwargs["candidate_id"])
        row.update(kwargs)
        row["state"] = "SELECTED"
        return True

    async def mark_candidate_result(self, _engine, **kwargs):
        operation_id = kwargs.get("operation_id")
        if (
            operation_id is not None
            and operation_id != self.operation_id
        ):
            return False
        row = next(item for item in self.rows if item["candidate_id"] == kwargs["candidate_id"])
        row.update(kwargs)
        row["state"] = "FAILED" if kwargs["error_code"] else "CREATED"
        return True

    async def complete_ingest(self, _engine, **kwargs):
        if (
            self.state != "INGESTING"
            or kwargs["operation_id"] != self.operation_id
        ):
            return False
        self.final_state = kwargs["state"]
        self.state = kwargs["state"]
        self.operation_id = None
        return True

    async def mark_import_state(self, _engine, **kwargs):
        self.final_state = kwargs["state"]
        self.state = kwargs["state"]


def test_preview_persists_safe_evidence_and_candidates_only() -> None:
    archive = archive_bytes()
    repository = FakeRepository(archive)

    result = asyncio.run(
        preview_repository_import(
            object(),
            namespace="opensource",
            project_path="oss-mirrors/project",
            requested_ref="main",
            upstream_url="https://github.com/example/project",
            context=context(),
            client=FakeClient(archive),
            repository=repository,
        )
    )

    assert result["import_id"] == 9
    assert [item.source_path for item in result["candidates"]] == ["alpha", "beta"]
    assert "token" not in repr(repository.created_kwargs).lower()


def test_preview_offloads_archive_parsing_from_the_event_loop(monkeypatch) -> None:
    archive = archive_bytes()
    repository = FakeRepository(archive)
    calls: list[tuple[str, tuple[object, ...]]] = []

    async def tracked_to_thread(function, *args):
        calls.append((function.__name__, args))
        return function(*args)

    monkeypatch.setattr(
        repository_import_service.asyncio,
        "to_thread",
        tracked_to_thread,
    )

    asyncio.run(
        preview_repository_import(
            object(),
            namespace="opensource",
            project_path="oss-mirrors/project",
            requested_ref="main",
            upstream_url=None,
            context=context(),
            client=FakeClient(archive),
            repository=repository,
        )
    )

    assert calls == [
        (
            "read_repository_archive",
            (archive, RepositoryArchiveLimits()),
        )
    ]


def test_preview_rejects_too_many_candidates_before_persistence() -> None:
    archive = archive_bytes()
    repository = FakeRepository(archive)
    limited_context = RepositoryImportContext(
        actor_user_id="curator",
        platform_roles=[],
        request_id="req-1",
        client_ip="127.0.0.1",
        user_agent="pytest",
        import_max_candidates=1,
    )

    with pytest.raises(
        RepositoryImportServiceError,
        match="error.repositoryImport.candidate.tooMany",
    ) as denied:
        asyncio.run(
            preview_repository_import(
                object(),
                namespace="opensource",
                project_path="oss-mirrors/project",
                requested_ref="main",
                upstream_url=None,
                context=limited_context,
                client=FakeClient(archive),
                repository=repository,
            )
        )

    assert denied.value.status_code == 413
    assert repository.created_kwargs is None


def test_ingest_preserves_partial_results_and_rejects_retry() -> None:
    archive = archive_bytes()
    repository = FakeRepository(archive)
    calls: list[str] = []
    fail_beta = True

    async def publisher(_import_row, candidate, selection, _context):
        nonlocal fail_beta
        calls.append(candidate.source_path)
        if candidate.source_path == "beta" and fail_beta:
            fail_beta = False
            raise RepositoryImportCandidatePublishError()
        return ImportedSkillResult(
            skill_id=selection.candidate_id + 100,
            version_id=selection.candidate_id + 200,
            version_status="PUBLISHED",
        )

    selections = [
        RepositoryImportSelection(
            candidate_id=1,
            target_slug="alpha",
            target_version="1.0.0",
            visibility="NAMESPACE_ONLY",
        ),
        RepositoryImportSelection(
            candidate_id=2,
            target_slug="beta",
            target_version="1.0.0",
            visibility="NAMESPACE_ONLY",
        ),
    ]
    first = asyncio.run(
        ingest_repository_import(
            object(),
            import_id=9,
            selections=selections,
            context=context(),
            client=FakeClient(archive),
            publisher=publisher,
            repository=repository,
        )
    )
    assert first["state"] == "PARTIAL"
    assert first["results"][1]["error_code"] == "error.repositoryImport.publishFailed"
    with pytest.raises(
        RepositoryImportServiceError,
        match="error.repositoryImport.ingest.notAvailable",
    ) as exc_info:
        asyncio.run(
            ingest_repository_import(
                object(),
                import_id=9,
                selections=selections,
                context=context(),
                client=FakeClient(archive),
                publisher=publisher,
                repository=repository,
            )
        )
    assert exc_info.value.status_code == 409
    assert calls == ["alpha", "beta"]
    assert repository.final_state == "PARTIAL"


def test_completed_ingest_preserves_created_status_and_rejects_republish() -> None:
    archive = archive_bytes()
    repository = FakeRepository(archive)
    repository.rows[0].update(
        {
            "state": "CREATED",
            "skill_id": 101,
            "skill_version_id": 201,
            "version_status": "PENDING",
        }
    )

    async def publisher(*_args):
        raise AssertionError("created candidate must not be published again")

    result = asyncio.run(
        ingest_repository_import(
            object(),
            import_id=9,
            selections=[
                RepositoryImportSelection(
                    candidate_id=1,
                    target_slug="alpha",
                    target_version="1.0.0",
                    visibility="NAMESPACE_ONLY",
                )
            ],
            context=context(),
            client=FakeClient(archive),
            publisher=publisher,
            repository=repository,
        )
    )

    assert result["results"][0]["version_status"] == "PENDING"
    with pytest.raises(
        RepositoryImportServiceError,
        match="error.repositoryImport.ingest.notAvailable",
    ) as exc_info:
        asyncio.run(
            ingest_repository_import(
                object(),
                import_id=9,
                selections=[
                    RepositoryImportSelection(
                        candidate_id=1,
                        target_slug="alpha",
                        target_version="1.0.0",
                        visibility="NAMESPACE_ONLY",
                    )
                ],
                context=context(),
                client=FakeClient(archive),
                publisher=publisher,
                repository=repository,
            )
        )
    assert exc_info.value.status_code == 409


def test_concurrent_ingest_claim_publishes_only_once() -> None:
    archive = archive_bytes()
    repository = FakeRepository(archive)
    publisher_entered = asyncio.Event()
    release_publisher = asyncio.Event()
    publish_calls = 0

    async def publisher(_import_row, _candidate, selection, _context):
        nonlocal publish_calls
        publish_calls += 1
        if publish_calls == 1:
            publisher_entered.set()
            await release_publisher.wait()
        return ImportedSkillResult(
            skill_id=selection.candidate_id + 100,
            version_id=selection.candidate_id + 200,
            version_status="PUBLISHED",
        )

    selection = RepositoryImportSelection(
        candidate_id=1,
        target_slug="alpha",
        target_version="1.0.0",
        visibility="NAMESPACE_ONLY",
    )

    async def scenario():
        first = asyncio.create_task(
            ingest_repository_import(
                object(),
                import_id=9,
                selections=[selection],
                context=context(),
                client=FakeClient(archive),
                publisher=publisher,
                repository=repository,
            )
        )
        await publisher_entered.wait()
        try:
            await ingest_repository_import(
                object(),
                import_id=9,
                selections=[selection],
                context=context(),
                client=FakeClient(archive),
                publisher=publisher,
                repository=repository,
            )
        except Exception as exc:
            competing_error = exc
        else:
            competing_error = None
        finally:
            release_publisher.set()
        return await first, competing_error

    first_result, competing_error = asyncio.run(scenario())

    assert first_result["state"] == "COMPLETED"
    assert competing_error is not None
    assert str(competing_error) == "error.repositoryImport.ingest.inProgress"
    assert competing_error.status_code == 409
    assert publish_calls == 1
    assert len(repository.operation_ids) == 1
    assert len(repository.operation_ids[0]) == 32


def test_operation_ownership_loss_leaves_import_ingesting() -> None:
    archive = archive_bytes()
    repository = FakeRepository(archive)

    async def lose_ownership(_engine, **_kwargs):
        repository.operation_id = "replacement-operation"
        return False

    repository.mark_candidate_result = lose_ownership

    async def publisher(_import_row, _candidate, selection, _context):
        return ImportedSkillResult(
            skill_id=selection.candidate_id + 100,
            version_id=selection.candidate_id + 200,
            version_status="PUBLISHED",
        )

    with pytest.raises(
        RepositoryImportServiceError,
        match="error.repositoryImport.ingest.ownershipLost",
    ) as exc_info:
        asyncio.run(
            ingest_repository_import(
                object(),
                import_id=9,
                selections=[
                    RepositoryImportSelection(
                        candidate_id=1,
                        target_slug="alpha",
                        target_version="1.0.0",
                        visibility="NAMESPACE_ONLY",
                    )
                ],
                context=context(),
                client=FakeClient(archive),
                publisher=publisher,
                repository=repository,
            )
        )

    assert exc_info.value.status_code == 409
    assert repository.state == "INGESTING"
    assert repository.final_state is None


def test_unexpected_post_commit_publisher_failure_leaves_import_ingesting() -> None:
    archive = archive_bytes()
    repository = FakeRepository(archive)
    publish_committed = False

    async def publisher(*_args):
        nonlocal publish_committed
        publish_committed = True
        raise RuntimeError("notification fanout failed after publish commit")

    with pytest.raises(
        RuntimeError,
        match="notification fanout failed after publish commit",
    ):
        asyncio.run(
            ingest_repository_import(
                object(),
                import_id=9,
                selections=[
                    RepositoryImportSelection(
                        candidate_id=1,
                        target_slug="alpha",
                        target_version="1.0.0",
                        visibility="NAMESPACE_ONLY",
                    )
                ],
                context=context(),
                client=FakeClient(archive),
                publisher=publisher,
                repository=repository,
            )
        )

    assert publish_committed is True
    assert repository.state == "INGESTING"
    assert repository.operation_id is not None
    assert repository.rows[0]["state"] == "SELECTED"
    assert repository.final_state is None


def test_archive_change_after_claim_leaves_import_for_operator_reconciliation() -> None:
    archive = archive_bytes()
    repository = FakeRepository(archive)
    changed_client = FakeClient(b"changed after preview")

    async def publisher(*_args):
        raise AssertionError("changed archive must not publish")

    with pytest.raises(
        RepositoryImportServiceError,
        match="error.repositoryImport.archive.changed",
    ) as exc_info:
        asyncio.run(
            ingest_repository_import(
                object(),
                import_id=9,
                selections=[
                    RepositoryImportSelection(
                        candidate_id=1,
                        target_slug="alpha",
                        target_version="1.0.0",
                        visibility="NAMESPACE_ONLY",
                    )
                ],
                context=context(),
                client=changed_client,
                publisher=publisher,
                repository=repository,
            )
        )

    assert exc_info.value.status_code == 409
    assert repository.state == "INGESTING"
    assert repository.operation_id is not None
    assert repository.final_state is None


@pytest.mark.parametrize(
    "selection",
    [
        RepositoryImportSelection(
            candidate_id=1,
            target_slug="INVALID",
            target_version="1.0.0",
            visibility="NAMESPACE_ONLY",
        ),
        RepositoryImportSelection(
            candidate_id=999,
            target_slug="missing",
            target_version="1.0.0",
            visibility="NAMESPACE_ONLY",
        ),
    ],
)
def test_client_selection_errors_do_not_consume_ingest_claim(
    selection: RepositoryImportSelection,
) -> None:
    archive = archive_bytes()
    repository = FakeRepository(archive)

    async def publisher(*_args):
        raise AssertionError("invalid selection must not publish")

    with pytest.raises(RepositoryImportServiceError):
        asyncio.run(
            ingest_repository_import(
                object(),
                import_id=9,
                selections=[selection],
                context=context(),
                client=FakeClient(archive),
                publisher=publisher,
                repository=repository,
            )
        )

    assert repository.state == "PREVIEW_READY"
    assert repository.operation_ids == []


def test_collection_draft_seed_requires_every_exact_published_version() -> None:
    archive = archive_bytes()
    repository = FakeRepository(archive)

    async def read_published_members(_engine, *, import_id, candidate_ids):
        assert import_id == 9
        return [
            {
                "candidate_id": 1,
                "skill_slug": "alpha",
                "version": "1.0.0",
            }
        ]

    repository.read_published_members = read_published_members
    called = False

    async def seeder(_import_row, _members, _payload, _context):
        nonlocal called
        called = True
        return {}

    try:
        asyncio.run(
            seed_repository_import_collection_draft(
                object(),
                import_id=9,
                candidate_ids=[1, 2],
                payload=object(),
                context=context(),
                seeder=seeder,
                repository=repository,
            )
        )
    except ValueError as exc:
        assert str(exc) == "error.repositoryImport.collectionDraft.publishedRequired"
    else:
        raise AssertionError("expected published-version gate")
    assert called is False


def test_collection_draft_seed_rejects_too_many_members_before_repository_read() -> None:
    archive = archive_bytes()
    repository = FakeRepository(archive)
    repository.read_published_members = AsyncMock(
        side_effect=AssertionError("over-limit seed must not read members")
    )

    with pytest.raises(
        RepositoryImportServiceError,
        match="error.repositoryImport.collectionDraft.tooManyMembers",
    ) as denied:
        asyncio.run(
            seed_repository_import_collection_draft(
                object(),
                import_id=9,
                candidate_ids=list(range(101)),
                payload=object(),
                context=context(),
                seeder=AsyncMock(),
                repository=repository,
            )
        )

    assert denied.value.status_code == 413
    repository.read_published_members.assert_not_awaited()


class FakeUpdateClient(FakeClient):
    def __init__(self, archive: bytes, commit_sha: str) -> None:
        super().__init__(archive)
        self.commit_sha = commit_sha
        self.download_calls = 0

    async def resolve_ref(self, project_path: str, requested_ref: str):
        return SimpleNamespace(
            project_id="oss-mirrors%2Fproject",
            project_full_path=project_path,
            requested_ref=requested_ref,
            commit_sha=self.commit_sha,
            source_web_url="https://gitlab.internal/oss-mirrors/project",
        )

    async def download_archive(self, project_path: str, commit_sha: str):
        assert project_path == "oss-mirrors/project"
        assert commit_sha == self.commit_sha
        self.download_calls += 1
        return self.archive


def test_update_check_unchanged_sha_creates_no_preview_or_archive_download() -> None:
    archive = archive_bytes()
    repository = FakeRepository(archive)
    client = FakeUpdateClient(archive, "a" * 40)

    result = asyncio.run(
        check_repository_import_updates(
            object(),
            import_id=9,
            context=context(),
            client=client,
            repository=repository,
        )
    )

    assert result == {
        "previous_import_id": 9,
        "changed": False,
        "previous_commit_sha": "a" * 40,
        "current_commit_sha": "a" * 40,
        "preview": None,
    }
    assert repository.created_kwargs is None
    assert client.download_calls == 0


def test_update_check_changed_sha_creates_linked_immutable_preview() -> None:
    archive = archive_bytes()
    repository = FakeRepository(archive)
    client = FakeUpdateClient(archive, "b" * 40)

    result = asyncio.run(
        check_repository_import_updates(
            object(),
            import_id=9,
            context=context(),
            client=client,
            repository=repository,
        )
    )

    assert result["changed"] is True
    assert result["current_commit_sha"] == "b" * 40
    assert result["preview"]["import_id"] == 9
    assert repository.created_kwargs["previous_import_id"] == 9
    assert repository.created_kwargs["source"].commit_sha == "b" * 40
    assert client.download_calls == 1

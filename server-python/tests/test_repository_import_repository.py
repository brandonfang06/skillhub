import asyncio
from contextlib import asynccontextmanager

import pytest

from app.repository_imports.discovery import RepositorySkillCandidate
from app.repository_imports.gitlab_client import GitLabPreviewSource
from app.repository_imports.repository import RepositoryImportRepository


class MappingResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def one(self):
        return self.row

    def one_or_none(self):
        return self.row


class FakeConnection:
    def __init__(self):
        self.params = []
        self.next_id = 9

    async def execute(self, statement, params=None):
        self.params.append(params or {})
        sql = str(statement)
        if "INSERT INTO local_repository_import (" in sql:
            return MappingResult({"id": self.next_id})
        if "INSERT INTO local_repository_import_candidate (" in sql:
            self.next_id += 1
            return MappingResult({"id": self.next_id})
        return MappingResult({})


class FakeEngine:
    def __init__(self):
        self.connection = FakeConnection()

    @asynccontextmanager
    async def begin(self):
        yield self.connection


def test_preview_repository_parameters_never_contain_gitlab_token() -> None:
    engine = FakeEngine()
    source = GitLabPreviewSource(
        project_id="oss-mirrors/project",
        project_full_path="oss-mirrors/project",
        requested_ref="main",
        commit_sha="a" * 40,
        source_web_url="https://gitlab.internal/oss-mirrors/project",
        archive=b"zip",
        archive_sha256="b" * 64,
    )
    candidate = RepositorySkillCandidate(
        source_path="alpha",
        detected_name="Alpha",
        detected_description="First",
        source_version="1.0.0",
        entries=[],
        warnings=[],
    )

    asyncio.run(
        RepositoryImportRepository().create_preview(
            engine,
            namespace_row={"id": 7, "slug": "opensource"},
            actor_user_id="curator",
            source=source,
            upstream_url=None,
            candidates=[candidate],
            request_id="req-1",
            client_ip="127.0.0.1",
            user_agent="pytest",
        )
    )

    serialized = repr(engine.connection.params).lower()
    assert "token" not in serialized
    assert "top-secret" not in serialized


class TransitionConnection:
    def __init__(self) -> None:
        self.statements: list[tuple[str, dict[str, object]]] = []
        self.claimed = False
        self.owned = True

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        values = params or {}
        self.statements.append((sql, values))
        if "SET state = 'INGESTING'" in sql:
            if self.claimed:
                return MappingResult(None)
            self.claimed = True
            return MappingResult({"id": values["import_id"]})
        if "UPDATE local_repository_import_candidate" in sql:
            return MappingResult(
                {"id": values["candidate_id"]} if self.owned else None
            )
        if "SET state = :state" in sql:
            return MappingResult(
                {"id": values["import_id"]} if self.owned else None
            )
        return MappingResult({})


class TransitionEngine:
    def __init__(self) -> None:
        self.connection = TransitionConnection()

    @asynccontextmanager
    async def begin(self):
        claimed_before = self.connection.claimed
        try:
            yield self.connection
        except Exception:
            self.connection.claimed = claimed_before
            raise


def test_claim_ingest_allows_only_one_preview_ready_transition() -> None:
    engine = TransitionEngine()
    repository = RepositoryImportRepository()

    first = asyncio.run(
        repository.claim_ingest(
            engine,
            import_id=9,
            operation_id="operation-a",
            actor_user_id="later-curator",
            request_id="req-claim",
            client_ip="127.0.0.1",
            user_agent="pytest",
        )
    )
    second = asyncio.run(
        repository.claim_ingest(
            engine,
            import_id=9,
            operation_id="operation-b",
            actor_user_id="later-curator",
            request_id="req-competing",
            client_ip="127.0.0.1",
            user_agent="pytest",
        )
    )

    assert first is True
    assert second is False
    sql, params = engine.connection.statements[0]
    assert "WHERE id = :import_id AND state = 'PREVIEW_READY'" in sql
    assert "ingest_operation_id = :operation_id" in sql
    assert "RETURNING id" in sql
    assert params == {"import_id": 9, "operation_id": "operation-a"}
    audit_params = next(
        params
        for sql, params in engine.connection.statements
        if "INSERT INTO audit_log" in sql
    )
    assert audit_params["actor_user_id"] == "later-curator"
    assert audit_params["action"] == "REPOSITORY_IMPORT_INGEST_STARTED"
    assert audit_params["request_id"] == "req-claim"
    assert '"operationId": "operation-a"' in audit_params["detail_json"]
    assert sum(
        "INSERT INTO audit_log" in sql
        for sql, _params in engine.connection.statements
    ) == 1


def test_claim_ingest_audit_failure_rolls_back_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = TransitionEngine()

    async def fail_audit(*_args, **_kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(
        "app.repository_imports.repository.write_audit_log",
        fail_audit,
    )

    with pytest.raises(RuntimeError, match="audit unavailable"):
        asyncio.run(
            RepositoryImportRepository().claim_ingest(
                engine,
                import_id=9,
                operation_id="operation-a",
                actor_user_id="later-curator",
                request_id="req-claim",
                client_ip="127.0.0.1",
                user_agent="pytest",
            )
        )

    assert engine.connection.claimed is False


def test_candidate_and_terminal_transitions_require_operation_ownership() -> None:
    engine = TransitionEngine()
    repository = RepositoryImportRepository()

    selected = asyncio.run(
        repository.mark_candidate_selected(
            engine,
            candidate_id=1,
            operation_id="operation-a",
            target_slug="alpha",
            target_version="1.0.0",
            visibility="NAMESPACE_ONLY",
        )
    )
    result = asyncio.run(
        repository.mark_candidate_result(
            engine,
            candidate_id=1,
            operation_id="operation-a",
            skill_id=101,
            skill_version_id=201,
            error_code=None,
        )
    )
    completed = asyncio.run(
        repository.complete_ingest(
            engine,
            import_id=9,
            operation_id="operation-a",
            state="COMPLETED",
            error_code=None,
            actor_user_id="curator",
            request_id="req-1",
            client_ip="127.0.0.1",
            user_agent="pytest",
        )
    )

    assert selected is True
    assert result is True
    assert completed is True
    candidate_sql = [
        sql
        for sql, _params in engine.connection.statements
        if "UPDATE local_repository_import_candidate" in sql
    ]
    assert all("parent.ingest_operation_id = :operation_id" in sql for sql in candidate_sql)
    terminal_sql = next(
        sql
        for sql, _params in engine.connection.statements
        if "ingest_operation_id = NULL" in sql
    )
    assert "AND state = 'INGESTING'" in terminal_sql
    assert "AND ingest_operation_id = :operation_id" in terminal_sql
    assert "ingest_operation_id = NULL" in terminal_sql
    assert "RETURNING id" in terminal_sql

    engine.connection.owned = False
    assert asyncio.run(
        repository.mark_candidate_result(
            engine,
            candidate_id=1,
            operation_id="operation-b",
            skill_id=None,
            skill_version_id=None,
            error_code="error.repositoryImport.publishFailed",
        )
    ) is False
    assert asyncio.run(
        repository.complete_ingest(
            engine,
            import_id=9,
            operation_id="operation-b",
            state="PARTIAL",
            error_code=None,
            actor_user_id="curator",
            request_id="req-2",
            client_ip="127.0.0.1",
            user_agent="pytest",
        )
    ) is False

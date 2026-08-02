from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.review.query import ReviewQueryError, read_review_file_content


def authenticated_client(app: Any, user_id: str = "team-admin") -> TestClient:
    app.state.local_auth_login = lambda payload: {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": "local",
        "platformRoles": ["USER"],
    }
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/local/login",
        json={"username": user_id, "password": "Abcd123!"},
    )
    assert response.status_code == 200
    return client


@dataclass
class FakeResult:
    row: dict[str, Any] | None = None
    rows: list[dict[str, Any]] | None = None

    def mappings(self) -> "FakeResult":
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        return self.row

    def all(self) -> list[dict[str, Any]]:
        return self.rows or []


class FakeReviewFileConnection:
    def __init__(
        self,
        *,
        submitted_by: str = "submitter",
        namespace_role: str | None = "ADMIN",
        platform_roles: list[str] | None = None,
        archived_task: bool = False,
    ) -> None:
        self.submitted_by = submitted_by
        self.namespace_role = namespace_role
        self.platform_roles = platform_roles or []
        self.archived_task = archived_task
        self.statements: list[str] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        self.statements.append(sql)
        if "FROM review_task rt" in sql:
            if self.archived_task:
                return FakeResult(row=None)
            return FakeResult(
                row={
                    "id": 801,
                    "skill_version_id": 52,
                    "namespace_id": 20,
                    "status": "PENDING",
                    "submitted_by": self.submitted_by,
                    "submitted_by_name": "Submitter",
                    "reviewed_by": None,
                    "reviewed_by_name": None,
                    "review_comment": None,
                    "submitted_at": datetime(2026, 6, 9, 10, 0, tzinfo=UTC),
                    "reviewed_at": None,
                    "namespace_slug": "team-a",
                    "namespace_type": "TEAM",
                    "skill_slug": "agent-helper",
                    "version_name": "1.0.0",
                }
            )
        if "FROM review_attempt_archive raa" in sql:
            if not self.archived_task:
                return FakeResult(row=None)
            return FakeResult(
                row={
                    "id": 801,
                    "skill_version_id": 52,
                    "namespace_id": 20,
                    "status": "REJECTED",
                    "submitted_by": self.submitted_by,
                    "namespace_type": "TEAM",
                }
            )
        if "FROM user_role_binding" in sql:
            return FakeResult(rows=[{"code": role} for role in self.platform_roles])
        if "FROM namespace_member" in sql:
            if self.namespace_role is None:
                return FakeResult(rows=[])
            return FakeResult(rows=[{"namespace_id": 20, "role": self.namespace_role}])
        if "FROM skill_file" in sql:
            return FakeResult(
                rows=[
                    {
                        "id": 901,
                        "file_path": "README.md",
                        "file_size": 12,
                        "content_type": "text/markdown",
                        "sha256": "readme-sha",
                        "storage_key": "skills/17/52/README.md",
                    },
                    {
                        "id": 902,
                        "file_path": "src/main.py",
                        "file_size": 15,
                        "content_type": "text/x-python",
                        "sha256": "py-sha",
                        "storage_key": "skills/17/52/src/main.py",
                    },
                    {
                        "id": 903,
                        "file_path": "missing.txt",
                        "file_size": 7,
                        "content_type": "text/plain",
                        "sha256": "missing-sha",
                        "storage_key": "skills/17/52/missing.txt",
                    },
                ]
            )
        raise AssertionError(f"unexpected SQL: {sql}")


class FakeConnect:
    def __init__(self, connection: FakeReviewFileConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeReviewFileConnection:
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: FakeReviewFileConnection) -> None:
        self.connection = connection

    def connect(self) -> FakeConnect:
        return FakeConnect(self.connection)


def write_storage_file(base: Path, key: str, content: bytes) -> None:
    target = base / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


@pytest.mark.anyio
async def test_read_review_file_content_returns_active_version_storage_bytes(tmp_path: Path) -> None:
    write_storage_file(tmp_path, "skills/17/52/README.md", b"# Review\r\n")
    write_storage_file(tmp_path, "skills/17/52/src/main.py", b"print('review')\n")
    connection = FakeReviewFileConnection(namespace_role="ADMIN")

    content = await read_review_file_content(
        FakeEngine(connection),
        storage_base_path=str(tmp_path),
        review_task_id=801,
        file_path="README.md",
        user_id="team-admin",
    )

    assert content == b"# Review\r\n"


@pytest.mark.anyio
async def test_read_review_file_content_allows_submitter(tmp_path: Path) -> None:
    write_storage_file(tmp_path, "skills/17/52/src/main.py", b"print('review')\n")
    connection = FakeReviewFileConnection(submitted_by="local-user", namespace_role=None)

    content = await read_review_file_content(
        FakeEngine(connection),
        storage_base_path=str(tmp_path),
        review_task_id=801,
        file_path="src/main.py",
        user_id="local-user",
    )

    assert content == b"print('review')\n"


@pytest.mark.anyio
async def test_read_review_file_content_forbids_unrelated_user(tmp_path: Path) -> None:
    connection = FakeReviewFileConnection(submitted_by="submitter", namespace_role="MEMBER")

    with pytest.raises(ValueError, match="review.no_permission"):
        await read_review_file_content(
            FakeEngine(connection),
            storage_base_path=str(tmp_path),
            review_task_id=801,
            file_path="README.md",
            user_id="member",
        )


@pytest.mark.anyio
async def test_read_review_file_content_returns_not_found_for_missing_storage(tmp_path: Path) -> None:
    write_storage_file(tmp_path, "skills/17/52/README.md", b"# Review\n")
    connection = FakeReviewFileConnection(namespace_role="ADMIN")

    with pytest.raises(ValueError, match="error.skill.file.notFound"):
        await read_review_file_content(
            FakeEngine(connection),
            storage_base_path=str(tmp_path),
            review_task_id=801,
            file_path="missing.txt",
            user_id="team-admin",
        )


@pytest.mark.anyio
async def test_read_review_file_content_rejects_archived_artifact(tmp_path: Path) -> None:
    connection = FakeReviewFileConnection(
        submitted_by="local-user",
        namespace_role=None,
        archived_task=True,
    )

    with pytest.raises(ReviewQueryError, match="review.artifact.unavailable") as exc_info:
        await read_review_file_content(
            FakeEngine(connection),
            storage_base_path=str(tmp_path),
            review_task_id=801,
            file_path="README.md",
            user_id="local-user",
        )

    assert exc_info.value.status_code == 410
    assert not any("FROM skill_file" in statement for statement in connection.statements)


def test_review_file_route_returns_octet_stream_bytes() -> None:
    app = create_app()
    seen: list[tuple[int, str, str, str]] = []

    async def reader(
        engine: object,
        storage_base_path: str,
        *,
        review_task_id: int,
        file_path: str,
        user_id: str,
    ) -> bytes:
        seen.append((review_task_id, file_path, user_id, storage_base_path))
        return b"# Review\r\n"

    app.state.review_file_reader = reader
    app.state.db_engine = object()
    app.state.settings = SimpleNamespace(storage_base_path="C:/tmp/review-file-test-storage")
    client = authenticated_client(app)
    response = client.get("/api/web/reviews/801/file?path=README.md")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.content == b"# Review\r\n"
    assert seen == [(801, "README.md", "team-admin", "C:/tmp/review-file-test-storage")]


@pytest.mark.parametrize("path", ["", "   ", "../secret.txt", "docs/../secret.txt", "/absolute.txt"])
def test_review_file_route_rejects_java_invalid_paths(path: str) -> None:
    app = create_app()
    app.state.db_engine = object()
    app.state.settings = SimpleNamespace(storage_base_path="C:/tmp/review-file-test-storage")
    client = authenticated_client(app)

    response = client.get(f"/api/v1/reviews/801/file?path={path}")

    assert response.status_code == 400


def test_review_file_route_requires_authentication() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/reviews/801/file?path=README.md")

    assert response.status_code == 401


def test_review_file_route_rejects_mock_header_without_session() -> None:
    app = create_app()
    seen: list[str] = []

    async def reader(
        engine: object,
        storage_base_path: str,
        *,
        review_task_id: int,
        file_path: str,
        user_id: str,
    ) -> bytes:
        seen.append(user_id)
        return b"review"

    app.state.review_file_reader = reader
    app.state.settings = SimpleNamespace(storage_base_path="C:/tmp/unused")

    response = TestClient(app).get(
        "/api/v1/reviews/801/file?path=README.md",
        headers={"X-Mock-User-Id": "docker-admin"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "error.auth.required"
    assert seen == []

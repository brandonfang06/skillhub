from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.review import query as review_query_module
from app.review.query import ReviewDownloadResult, ReviewQueryError, read_review_download_package


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


class FakeReviewDownloadConnection:
    def __init__(
        self,
        *,
        submitted_by: str = "submitter",
        namespace_role: str | None = "ADMIN",
        platform_roles: list[str] | None = None,
        display_name: str | None = "Review Download Skill",
        archived_task: bool = False,
    ) -> None:
        self.submitted_by = submitted_by
        self.namespace_role = namespace_role
        self.platform_roles = platform_roles or []
        self.display_name = display_name
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
        if "active.id AS version_id" in sql:
            return FakeResult(
                row={
                    "skill_id": 17,
                    "version_id": 52,
                    "slug": "agent-helper",
                    "display_name": self.display_name,
                    "version": "1.0.0",
                }
            )
        if "FROM skill_file" in sql:
            return FakeResult(
                rows=[
                    {"file_path": "src/main.py", "storage_key": "skills/17/52/src/main.py"},
                    {"file_path": "README.md", "storage_key": "skills/17/52/README.md"},
                    {"file_path": "missing.txt", "storage_key": "skills/17/52/missing.txt"},
                ]
            )
        raise AssertionError(f"unexpected SQL: {sql}")


class FakeConnect:
    def __init__(self, connection: FakeReviewDownloadConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeReviewDownloadConnection:
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: FakeReviewDownloadConnection) -> None:
        self.connection = connection

    def connect(self) -> FakeConnect:
        return FakeConnect(self.connection)


def write_storage_file(base: Path, key: str, content: bytes) -> None:
    target = base / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


@pytest.mark.anyio
async def test_read_review_download_prefers_prebuilt_bundle(tmp_path: Path) -> None:
    write_storage_file(tmp_path, "packages/17/52/bundle.zip", b"prebuilt-zip")
    write_storage_file(tmp_path, "skills/17/52/README.md", b"# Review\n")
    connection = FakeReviewDownloadConnection(namespace_role="ADMIN")

    result = await read_review_download_package(
        FakeEngine(connection),
        storage_base_path=str(tmp_path),
        review_task_id=801,
        user_id="team-admin",
    )

    assert result.content == b"prebuilt-zip"
    assert result.content_type in {"application/zip", "application/x-zip-compressed"}
    assert result.filename == "Review Download Skill-1.0.0.zip"
    assert result.content_length == len(b"prebuilt-zip")
    assert not any("UPDATE skill SET download_count" in statement for statement in connection.statements)


@pytest.mark.anyio
async def test_read_review_download_prefers_object_storage_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_object_storage_factory,
) -> None:
    storage = fake_object_storage_factory({"packages/17/52/bundle.zip": b"object-storage-review-zip"})
    monkeypatch.setattr(review_query_module, "object_storage_for_base_path", lambda storage_base_path: storage)
    connection = FakeReviewDownloadConnection(namespace_role="ADMIN")

    result = await read_review_download_package(
        FakeEngine(connection),
        storage_base_path=str(tmp_path / "missing-local-storage"),
        review_task_id=801,
        user_id="team-admin",
    )

    assert result.content == b"object-storage-review-zip"
    assert result.filename == "Review Download Skill-1.0.0.zip"
    assert not (tmp_path / "missing-local-storage").exists()


@pytest.mark.anyio
async def test_read_review_download_builds_fallback_zip_from_available_files(tmp_path: Path) -> None:
    write_storage_file(tmp_path, "skills/17/52/README.md", b"# Review\r\n")
    write_storage_file(tmp_path, "skills/17/52/src/main.py", b"print('review')\n")
    connection = FakeReviewDownloadConnection(namespace_role="ADMIN")

    result = await read_review_download_package(
        FakeEngine(connection),
        storage_base_path=str(tmp_path),
        review_task_id=801,
        user_id="team-admin",
    )

    assert result.content_type == "application/zip"
    assert result.filename == "Review Download Skill-1.0.0.zip"
    with ZipFile(result.as_bytes_io()) as zip_file:
        assert zip_file.namelist() == ["README.md", "src/main.py"]
        assert zip_file.read("README.md") == b"# Review\r\n"
        assert zip_file.read("src/main.py") == b"print('review')\n"


@pytest.mark.anyio
async def test_read_review_download_sanitizes_filename_and_allows_submitter(tmp_path: Path) -> None:
    write_storage_file(tmp_path, "packages/17/52/bundle.zip", b"zip")
    connection = FakeReviewDownloadConnection(
        submitted_by="local-user",
        namespace_role=None,
        display_name='Bad:/Name\tSkill',
    )

    result = await read_review_download_package(
        FakeEngine(connection),
        storage_base_path=str(tmp_path),
        review_task_id=801,
        user_id="local-user",
    )

    assert result.filename == "Bad--Name-Skill-1.0.0.zip"


@pytest.mark.anyio
async def test_read_review_download_forbids_unrelated_user(tmp_path: Path) -> None:
    connection = FakeReviewDownloadConnection(submitted_by="submitter", namespace_role="MEMBER")

    with pytest.raises(ValueError, match="review.no_permission"):
        await read_review_download_package(
            FakeEngine(connection),
            storage_base_path=str(tmp_path),
            review_task_id=801,
            user_id="member",
        )


@pytest.mark.anyio
async def test_read_review_download_returns_bundle_not_found_when_no_available_content(tmp_path: Path) -> None:
    connection = FakeReviewDownloadConnection(namespace_role="ADMIN")

    with pytest.raises(ValueError, match="error.skill.bundle.notFound"):
        await read_review_download_package(
            FakeEngine(connection),
            storage_base_path=str(tmp_path),
            review_task_id=801,
            user_id="team-admin",
        )


@pytest.mark.anyio
async def test_read_review_download_rejects_archived_artifact(tmp_path: Path) -> None:
    connection = FakeReviewDownloadConnection(
        submitted_by="local-user",
        namespace_role=None,
        archived_task=True,
    )

    with pytest.raises(ReviewQueryError, match="review.artifact.unavailable") as exc_info:
        await read_review_download_package(
            FakeEngine(connection),
            storage_base_path=str(tmp_path),
            review_task_id=801,
            user_id="local-user",
        )

    assert exc_info.value.status_code == 410
    assert not any("FROM skill_file" in statement for statement in connection.statements)


def test_review_download_route_returns_attachment_response() -> None:
    app = create_app()
    seen: list[tuple[int, str, str]] = []

    async def reader(
        engine: object,
        storage_base_path: str,
        *,
        review_task_id: int,
        user_id: str,
    ) -> ReviewDownloadResult:
        seen.append((review_task_id, user_id, storage_base_path))
        return ReviewDownloadResult(
            content=b"zip",
            content_type="application/zip",
            filename="Review Skill-1.0.0.zip",
        )

    app.state.review_download_reader = reader
    app.state.db_engine = object()
    app.state.settings = SimpleNamespace(storage_base_path="C:/tmp/review-download-test-storage")
    client = authenticated_client(app)
    response = client.get("/api/web/reviews/801/download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"] == 'attachment; filename="Review Skill-1.0.0.zip"'
    assert response.headers["content-length"] == "3"
    assert response.content == b"zip"
    assert seen == [(801, "team-admin", "C:/tmp/review-download-test-storage")]


def test_review_download_route_requires_authentication() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/reviews/801/download")

    assert response.status_code == 401


def test_review_download_route_rejects_mock_header_without_session() -> None:
    app = create_app()
    seen: list[str] = []

    async def reader(
        engine: object,
        storage_base_path: str,
        *,
        review_task_id: int,
        user_id: str,
    ) -> ReviewDownloadResult:
        seen.append(user_id)
        return ReviewDownloadResult(content=b"zip", content_type="application/zip", filename="Review.zip")

    app.state.review_download_reader = reader
    app.state.settings = SimpleNamespace(storage_base_path="C:/tmp/unused")

    response = TestClient(app).get(
        "/api/v1/reviews/801/download",
        headers={"X-Mock-User-Id": "docker-admin"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "error.auth.required"
    assert seen == []

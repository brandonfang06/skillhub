from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.review.query import read_review_skill_detail


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


class FakeReviewSkillDetailConnection:
    def __init__(
        self,
        *,
        submitted_by: str = "submitter",
        namespace_type: str = "TEAM",
        platform_roles: list[str] | None = None,
        namespace_role: str | None = "ADMIN",
        missing_task: bool = False,
        missing_snapshot: bool = False,
    ) -> None:
        self.submitted_by = submitted_by
        self.namespace_type = namespace_type
        self.platform_roles = platform_roles or []
        self.namespace_role = namespace_role
        self.missing_task = missing_task
        self.missing_snapshot = missing_snapshot
        self.statements: list[str] = []

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        self.statements.append(sql)

        if "FROM review_task rt" in sql:
            if self.missing_task:
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
                    "namespace_type": self.namespace_type,
                    "skill_slug": "agent-helper",
                    "version_name": "1.0.0",
                }
            )
        if "FROM user_role_binding" in sql:
            return FakeResult(rows=[{"code": role} for role in self.platform_roles])
        if "FROM namespace_member" in sql:
            if self.namespace_role is None:
                return FakeResult(rows=[])
            return FakeResult(rows=[{"namespace_id": 20, "role": self.namespace_role}])
        if "active.id AS active_version_id" in sql:
            if self.missing_snapshot:
                return FakeResult(row=None)
            return FakeResult(
                row={
                    "id": 17,
                    "slug": "agent-helper",
                    "display_name": "Agent Helper",
                    "owner_id": "submitter",
                    "owner_display_name": "Submitter",
                    "summary": "Review-bound helper",
                    "visibility": "NAMESPACE_ONLY",
                    "status": "ACTIVE",
                    "download_count": 4,
                    "star_count": 2,
                    "subscription_count": 1,
                    "rating_avg": 4.5,
                    "rating_count": 3,
                    "hidden": False,
                    "namespace": "team-a",
                    "active_version_id": 52,
                    "active_version": "1.0.0",
                    "active_version_status": "PENDING_REVIEW",
                }
            )
        if "FROM skill_version sv" in sql:
            return FakeResult(
                rows=[
                    {
                        "id": 51,
                        "version": "0.9.0",
                        "status": "PUBLISHED",
                        "changelog": "stable",
                        "file_count": 1,
                        "total_size": 80,
                        "published_at": datetime(2026, 6, 8, 9, 0, tzinfo=UTC),
                        "download_ready": True,
                        "created_at": datetime(2026, 6, 8, 8, 0, tzinfo=UTC),
                    },
                    {
                        "id": 52,
                        "version": "1.0.0",
                        "status": "PENDING_REVIEW",
                        "changelog": "review me",
                        "file_count": 2,
                        "total_size": 120,
                        "published_at": None,
                        "download_ready": False,
                        "created_at": datetime(2026, 6, 9, 9, 0, tzinfo=UTC),
                    },
                ]
            )
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
                        "file_path": "SKILL.md",
                        "file_size": 11,
                        "content_type": "text/markdown",
                        "sha256": "skill-sha",
                        "storage_key": "skills/17/52/SKILL.md",
                    },
                    {
                        "id": 903,
                        "file_path": "missing.txt",
                        "file_size": 11,
                        "content_type": "text/plain",
                        "sha256": "missing-sha",
                        "storage_key": "skills/17/52/missing.txt",
                    },
                ]
            )

        raise AssertionError(f"unexpected SQL: {sql}")


class FakeConnect:
    def __init__(self, connection: FakeReviewSkillDetailConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeReviewSkillDetailConnection:
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: FakeReviewSkillDetailConnection) -> None:
        self.connection = connection

    def connect(self) -> FakeConnect:
        return FakeConnect(self.connection)


def write_storage_file(base: Path, key: str, content: str) -> None:
    target = base / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content.encode("utf-8"))


@pytest.mark.anyio
async def test_read_review_skill_detail_builds_review_bound_snapshot(tmp_path: Path) -> None:
    write_storage_file(tmp_path, "skills/17/52/README.md", "# Review\r\n")
    write_storage_file(tmp_path, "skills/17/52/SKILL.md", "# Skill\n")
    connection = FakeReviewSkillDetailConnection(namespace_role="ADMIN")

    response = await read_review_skill_detail(
        FakeEngine(connection),
        storage_base_path=str(tmp_path),
        review_task_id=801,
        user_id="team-admin",
    )

    assert response["skill"]["id"] == 17
    assert response["skill"]["slug"] == "agent-helper"
    assert response["skill"]["namespace"] == "team-a"
    assert response["skill"]["labels"] == []
    assert response["skill"]["canManageLifecycle"] is False
    assert response["skill"]["canSubmitPromotion"] is False
    assert response["skill"]["canInteract"] is False
    assert response["skill"]["canReport"] is False
    assert response["skill"]["resolutionMode"] == "REVIEW_TASK"
    assert response["skill"]["headlineVersion"] == {"id": 52, "version": "1.0.0", "status": "PENDING_REVIEW"}
    assert response["skill"]["publishedVersion"] == {"id": 51, "version": "0.9.0", "status": "PUBLISHED"}
    assert response["skill"]["ownerPreviewVersion"] == {"id": 52, "version": "1.0.0", "status": "PENDING_REVIEW"}
    assert response["versions"] == [
        {
            "id": 51,
            "version": "0.9.0",
            "status": "PUBLISHED",
            "changelog": "stable",
            "fileCount": 1,
            "totalSize": 80,
            "publishedAt": "2026-06-08T09:00:00Z",
            "downloadAvailable": True,
        },
        {
            "id": 52,
            "version": "1.0.0",
            "status": "PENDING_REVIEW",
            "changelog": "review me",
            "fileCount": 2,
            "totalSize": 120,
            "publishedAt": None,
            "downloadAvailable": True,
        },
    ]
    assert response["files"] == [
        {
            "id": 901,
            "filePath": "README.md",
            "fileSize": 12,
            "contentType": "text/markdown",
            "sha256": "readme-sha",
        },
        {
            "id": 902,
            "filePath": "SKILL.md",
            "fileSize": 11,
            "contentType": "text/markdown",
            "sha256": "skill-sha",
        },
    ]
    assert response["documentationPath"] == "README.md"
    assert response["documentationContent"] == "# Review\r\n"
    assert response["downloadUrl"] == "/api/v1/reviews/801/download"
    assert response["activeVersion"] == "1.0.0"


@pytest.mark.anyio
async def test_read_review_skill_detail_allows_submitter_without_reviewer_role(tmp_path: Path) -> None:
    write_storage_file(tmp_path, "skills/17/52/README.md", "# Review\n")
    connection = FakeReviewSkillDetailConnection(submitted_by="local-user", namespace_role=None)

    response = await read_review_skill_detail(
        FakeEngine(connection),
        storage_base_path=str(tmp_path),
        review_task_id=801,
        user_id="local-user",
    )

    assert response["skill"]["resolutionMode"] == "REVIEW_TASK"


@pytest.mark.anyio
async def test_read_review_skill_detail_forbids_unrelated_user(tmp_path: Path) -> None:
    connection = FakeReviewSkillDetailConnection(submitted_by="submitter", namespace_role="MEMBER")

    with pytest.raises(ValueError, match="review.no_permission"):
        await read_review_skill_detail(
            FakeEngine(connection),
            storage_base_path=str(tmp_path),
            review_task_id=801,
            user_id="member",
        )


@pytest.mark.anyio
async def test_read_review_skill_detail_returns_not_found_for_missing_snapshot(tmp_path: Path) -> None:
    connection = FakeReviewSkillDetailConnection(missing_snapshot=True)

    with pytest.raises(ValueError, match="error.skill.version.notFound"):
        await read_review_skill_detail(
            FakeEngine(connection),
            storage_base_path=str(tmp_path),
            review_task_id=801,
            user_id="team-admin",
        )


def test_review_skill_detail_route_returns_java_read_envelope() -> None:
    app = create_app()
    seen: list[tuple[int, str, str]] = []
    app.state.local_auth_login = lambda payload: {
        "userId": "team-admin",
        "displayName": "Team Admin",
        "email": "team-admin@example.test",
        "avatarUrl": "",
        "oauthProvider": "local",
        "platformRoles": ["USER"],
    }

    async def reader(engine: object, storage_base_path: str, *, review_task_id: int, user_id: str) -> dict[str, object]:
        seen.append((review_task_id, user_id, storage_base_path))
        return {
            "skill": {"id": 17, "slug": "agent-helper", "resolutionMode": "REVIEW_TASK"},
            "versions": [],
            "files": [],
            "documentationPath": None,
            "documentationContent": None,
            "downloadUrl": f"/api/v1/reviews/{review_task_id}/download",
            "activeVersion": "1.0.0",
        }

    app.state.review_skill_detail_reader = reader
    app.state.db_engine = object()
    app.state.settings = SimpleNamespace(storage_base_path="C:/tmp/review-skill-detail-test-storage")
    client = TestClient(app)
    assert client.post(
        "/api/v1/auth/local/login",
        json={"username": "team-admin", "password": "Abcd123!"},
    ).status_code == 200

    response = client.get(
        "/api/web/reviews/801/skill-detail",
        headers={"X-Request-Id": "review-skill-detail-test"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["msg"] == "\u83b7\u53d6\u6210\u529f"
    assert body["requestId"] == "review-skill-detail-test"
    assert body["data"]["downloadUrl"] == "/api/v1/reviews/801/download"
    assert seen == [(801, "team-admin", "C:/tmp/review-skill-detail-test-storage")]


def test_review_skill_detail_route_requires_authentication() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/v1/reviews/801/skill-detail")

    assert response.status_code == 401


def test_review_skill_detail_route_rejects_mock_header_without_session() -> None:
    app = create_app()
    app.state.review_skill_detail_reader = lambda *args, **kwargs: pytest.fail(
        "mock header must not reach review content"
    )

    response = TestClient(app).get(
        "/api/v1/reviews/801/skill-detail",
        headers={"X-Mock-User-Id": "docker-admin"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "error.auth.required"

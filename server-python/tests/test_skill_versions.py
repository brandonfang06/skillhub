import asyncio

from fastapi.testclient import TestClient

import pytest

from app.api import skills
from app.api.skills import SkillResolveError
from app.main import create_app


class _FakeMappings:
    def __init__(self, value: object) -> None:
        self.value = value

    def one_or_none(self) -> object:
        return self.value

    def all(self) -> object:
        return self.value


class _FakeResult:
    def __init__(self, value: object) -> None:
        self.value = value

    def mappings(self) -> _FakeMappings:
        return _FakeMappings(self.value)

    def scalar_one_or_none(self) -> object:
        return self.value


class _SkillVersionsOwnerPreviewWithoutLatestConnection:
    async def execute(self, statement: object, params: dict[str, object] | None = None) -> _FakeResult:
        sql = str(statement)
        if "FROM skill s" in sql:
            assert "s.latest_version_id IS NOT NULL" not in sql
            return _FakeResult(
                {
                    "id": 11,
                    "owner_id": "owner-1",
                    "namespace_id": 7,
                    "visibility": "PUBLIC",
                    "latest_version_id": None,
                }
            )
        if "FROM namespace_member" in sql:
            return _FakeResult(None)
        if "FROM skill_version" in sql:
            return _FakeResult(
                [
                    {
                        "id": 101,
                        "version": "1.0.0",
                        "status": "PENDING_REVIEW",
                        "changelog": "initial",
                        "file_count": 2,
                        "total_size": 128,
                        "published_at": None,
                        "download_ready": False,
                    }
                ]
            )
        raise AssertionError(f"unexpected SQL: {sql}")


class _FakeConnectionContext:
    def __init__(self, connection: object) -> None:
        self.connection = connection

    async def __aenter__(self) -> object:
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class _FakeEngine:
    def __init__(self, connection: object) -> None:
        self.connection = connection

    def connect(self) -> _FakeConnectionContext:
        return _FakeConnectionContext(self.connection)


def version_page(page: int, size: int) -> dict[str, object]:
    return {
        "items": [
            {
                "id": 20,
                "version": "1.2.0",
                "status": "PUBLISHED",
                "changelog": "latest",
                "fileCount": 2,
                "totalSize": 128,
                "publishedAt": "2026-06-07T10:00:00Z",
                "downloadAvailable": True,
            }
        ],
        "total": 1,
        "page": page,
        "size": size,
    }


def test_skill_versions_v1_route_returns_page_envelope() -> None:
    app = create_app()
    app.state.skill_versions_reader = lambda namespace, slug, page, size, current_user_id: version_page(page, size)

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/versions",
        params={"page": 0, "size": 20},
        headers={"X-Request-Id": "versions-test"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "versions-test"
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "获取成功"
    assert response.json()["requestId"] == "versions-test"
    assert response.json()["data"] == version_page(0, 20)


def test_skill_versions_web_alias_returns_same_contract() -> None:
    app = create_app()
    app.state.skill_versions_reader = lambda namespace, slug, page, size, current_user_id: version_page(page, size)

    client = TestClient(app)
    response = client.get("/api/web/skills/global/demo/versions")

    assert response.status_code == 200
    assert response.json()["data"] == version_page(0, 20)


def test_skill_versions_route_forwards_page_size_and_current_user_to_reader() -> None:
    seen: list[tuple[int, int, str | None]] = []
    app = create_app()

    def reader(
        namespace: str,
        slug: str,
        page: int,
        size: int,
        current_user_id: str | None,
    ) -> dict[str, object]:
        seen.append((page, size, current_user_id))
        return version_page(page, size)

    app.state.skill_versions_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/versions",
        params={"page": 2, "size": 5},
        headers={"X-Mock-User-Id": " owner-1 "},
    )

    assert response.status_code == 200
    assert seen == [(2, 5, "owner-1")]
    assert response.json()["data"]["page"] == 2
    assert response.json()["data"]["size"] == 5


def test_skill_versions_route_forwards_missing_current_user_as_none() -> None:
    seen: list[str | None] = []
    app = create_app()

    def reader(
        namespace: str,
        slug: str,
        page: int,
        size: int,
        current_user_id: str | None,
    ) -> dict[str, object]:
        seen.append(current_user_id)
        return version_page(page, size)

    app.state.skill_versions_reader = reader

    client = TestClient(app)
    response = client.get("/api/v1/skills/global/demo/versions", headers={"X-Mock-User-Id": "   "})

    assert response.status_code == 200
    assert seen == [None]


def test_skill_versions_route_uses_session_principal_for_owner_preview() -> None:
    seen: list[str | None] = []
    app = create_app()
    app.state.local_auth_login = lambda payload: {
        "userId": "owner-1",
        "displayName": "Owner One",
        "email": "owner@example.test",
        "avatarUrl": "",
        "oauthProvider": "local",
        "platformRoles": ["USER"],
    }

    def reader(
        namespace: str,
        slug: str,
        page: int,
        size: int,
        current_user_id: str | None,
    ) -> dict[str, object]:
        seen.append(current_user_id)
        return version_page(page, size)

    app.state.skill_versions_reader = reader
    client = TestClient(app)
    client.post("/api/v1/auth/local/login", json={"username": "owner", "password": "Abcd123!"})

    response = client.get("/api/web/skills/global/demo/versions")

    assert response.status_code == 200
    assert seen == ["owner-1"]


def test_read_skill_versions_allows_owner_preview_without_latest_pointer() -> None:
    result = asyncio.run(
        skills.read_skill_versions(
            _FakeEngine(_SkillVersionsOwnerPreviewWithoutLatestConnection()),
            "global",
            "demo",
            0,
            20,
            "owner-1",
        )
    )

    assert result["items"] == [
        {
            "id": 101,
            "version": "1.0.0",
            "status": "PENDING_REVIEW",
            "changelog": "initial",
            "fileCount": 2,
            "totalSize": 128,
            "publishedAt": None,
            "downloadAvailable": False,
        }
    ]


def test_read_skill_versions_rejects_public_skill_without_latest_for_anonymous_user() -> None:
    with pytest.raises(SkillResolveError, match="error.skill.access.denied"):
        asyncio.run(
            skills.read_skill_versions(
                _FakeEngine(_SkillVersionsOwnerPreviewWithoutLatestConnection()),
                "global",
                "demo",
                0,
                20,
                None,
            )
        )

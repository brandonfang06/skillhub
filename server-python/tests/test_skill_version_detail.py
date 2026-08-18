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


class _FakeResult:
    def __init__(self, value: object) -> None:
        self.value = value

    def mappings(self) -> _FakeMappings:
        return _FakeMappings(self.value)

    def scalar_one_or_none(self) -> object:
        return self.value


class _SkillVersionDetailOwnerPreviewWithoutLatestConnection:
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
        if "FROM skill_version sv" in sql:
            return _FakeResult(
                {
                    "id": 101,
                    "version": "1.0.0",
                    "status": "PENDING_REVIEW",
                    "changelog": "initial",
                    "file_count": 2,
                    "total_size": 128,
                    "published_at": None,
                    "parsed_metadata_json": "{\"name\":\"demo\"}",
                    "manifest_json": "[{\"path\":\"SKILL.md\"}]",
                    "source_repository_url": "https://github.com/mattpocock/skills",
                    "source_revision_sha": "b" * 40,
                    "source_ref_type": "BRANCH",
                    "source_ref": "main",
                    "source_path": "skills/demo",
                    "source_content_fingerprint": "e" * 64,
                }
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


def detail_response(version: str = "1.2.0") -> dict[str, object]:
    return {
        "id": 20,
        "version": version,
        "status": "PUBLISHED",
        "changelog": "latest",
        "fileCount": 2,
        "totalSize": 128,
        "publishedAt": "2026-06-07T10:00:00Z",
        "parsedMetadataJson": "{\"name\":\"demo\"}",
        "manifestJson": "[{\"path\":\"SKILL.md\"}]",
    }


def test_skill_version_detail_v1_route_returns_envelope() -> None:
    app = create_app()
    app.state.skill_version_detail_reader = (
        lambda namespace, slug, version, current_user_id: detail_response(version)
    )

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/versions/1.2.0",
        headers={"X-Request-Id": "version-detail-test"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "version-detail-test"
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "获取成功"
    assert response.json()["requestId"] == "version-detail-test"
    assert response.json()["data"] == detail_response()


def test_skill_version_detail_web_alias_returns_same_contract() -> None:
    app = create_app()
    app.state.skill_version_detail_reader = (
        lambda namespace, slug, version, current_user_id: detail_response(version)
    )

    client = TestClient(app)
    response = client.get("/api/web/skills/global/demo/versions/1.2.0")

    assert response.status_code == 200
    assert response.json()["data"] == detail_response()


def test_skill_version_detail_route_forwards_version_and_current_user_to_reader() -> None:
    seen: list[tuple[str, str, str, str | None]] = []
    app = create_app()

    def reader(
        namespace: str,
        slug: str,
        version: str,
        current_user_id: str | None,
    ) -> dict[str, object]:
        seen.append((namespace, slug, version, current_user_id))
        return detail_response(version)

    app.state.skill_version_detail_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/versions/1.0.0",
        headers={"X-Mock-User-Id": " owner-1 "},
    )

    assert response.status_code == 200
    assert seen == [("global", "demo", "1.0.0", "owner-1")]
    assert response.json()["data"]["version"] == "1.0.0"


def test_skill_version_detail_route_forwards_blank_current_user_as_none() -> None:
    seen: list[str | None] = []
    app = create_app()

    def reader(
        namespace: str,
        slug: str,
        version: str,
        current_user_id: str | None,
    ) -> dict[str, object]:
        seen.append(current_user_id)
        return detail_response(version)

    app.state.skill_version_detail_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/web/skills/global/demo/versions/1.0.0",
        headers={"X-Mock-User-Id": "   "},
    )

    assert response.status_code == 200
    assert seen == [None]


def test_skill_version_detail_route_uses_session_principal_for_owner_preview() -> None:
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
        version: str,
        current_user_id: str | None,
    ) -> dict[str, object]:
        seen.append(current_user_id)
        return detail_response(version)

    app.state.skill_version_detail_reader = reader
    client = TestClient(app)
    client.post("/api/v1/auth/local/login", json={"username": "owner", "password": "Abcd123!"})

    response = client.get("/api/web/skills/global/demo/versions/1.0.0")

    assert response.status_code == 200
    assert seen == ["owner-1"]


def test_read_skill_version_detail_allows_owner_preview_without_latest_pointer() -> None:
    result = asyncio.run(
        skills.read_skill_version_detail(
            _FakeEngine(_SkillVersionDetailOwnerPreviewWithoutLatestConnection()),
            "global",
            "demo",
            "1.0.0",
            "owner-1",
        )
    )

    assert result["version"] == "1.0.0"
    assert result["status"] == "PENDING_REVIEW"
    assert result["sourceProvenance"]["browseUrl"] == (
        "https://github.com/mattpocock/skills/tree/" + "b" * 40 + "/skills/demo"
    )


def test_read_skill_version_detail_rejects_public_skill_without_latest_for_anonymous_user() -> None:
    with pytest.raises(SkillResolveError, match="error.skill.access.denied"):
        asyncio.run(
            skills.read_skill_version_detail(
                _FakeEngine(_SkillVersionDetailOwnerPreviewWithoutLatestConnection()),
                "global",
                "demo",
                "1.0.0",
                None,
            )
        )

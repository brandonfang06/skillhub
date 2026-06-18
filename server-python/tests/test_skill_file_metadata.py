import asyncio

from fastapi.testclient import TestClient

from app.api import skills
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


class _TagFilesConnection:
    async def execute(self, statement: object, params: dict[str, object] | None = None) -> _FakeResult:
        sql = str(statement)
        if "FROM skill s" in sql:
            assert "s.visibility = 'PUBLIC'" not in sql
            return _FakeResult(
                {
                    "id": 11,
                    "owner_id": "owner-1",
                    "namespace_id": 7,
                    "visibility": "PRIVATE",
                    "latest_version_id": 101,
                }
            )
        if "FROM namespace_member" in sql:
            return _FakeResult(None)
        if "FROM skill_version" in sql:
            return _FakeResult({"id": 101})
        if "FROM skill_file" in sql:
            return _FakeResult(
                [
                    {
                        "id": 201,
                        "file_path": "SKILL.md",
                        "file_size": 10,
                        "content_type": "text/markdown",
                        "sha256": "hash",
                    }
                ]
            )
        raise AssertionError(f"unexpected SQL: {sql}")


class _VersionFilesOwnerPreviewWithoutLatestConnection:
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
            return _FakeResult({"id": 101, "status": "PENDING_REVIEW"})
        if "FROM skill_file" in sql:
            return _FakeResult(
                [
                    {
                        "id": 201,
                        "file_path": "SKILL.md",
                        "file_size": 10,
                        "content_type": "text/markdown",
                        "sha256": "hash",
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

def files_response() -> list[dict[str, object]]:
    return [
        {
            "id": 21,
            "filePath": "SKILL.md",
            "fileSize": 1024,
            "contentType": "text/markdown",
            "sha256": "hash-skill-md"
        },
        {
            "id": 22,
            "filePath": "app.py",
            "fileSize": 2048,
            "contentType": "text/x-python",
            "sha256": "hash-app-py"
        }
    ]

def test_skill_version_files_route_returns_envelope() -> None:
    app = create_app()
    app.state.skill_version_files_reader = lambda namespace, slug, version, current_user_id: files_response()

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/versions/1.2.0/files",
        headers={"X-Request-Id": "files-version-test"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "files-version-test"
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "获取成功"
    assert response.json()["requestId"] == "files-version-test"
    assert response.json()["data"] == files_response()

def test_skill_version_files_web_alias_returns_same() -> None:
    app = create_app()
    app.state.skill_version_files_reader = lambda namespace, slug, version, current_user_id: files_response()

    client = TestClient(app)
    response = client.get("/api/web/skills/global/demo/versions/1.2.0/files")

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"] == files_response()

def test_skill_tag_files_route_returns_envelope() -> None:
    app = create_app()
    app.state.skill_tag_files_reader = lambda namespace, slug, tag, current_user_id: files_response()

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/tags/latest/files",
        headers={"X-Request-Id": "files-tag-test"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "files-tag-test"
    assert response.json()["code"] == 0
    assert response.json()["msg"] == "获取成功"
    assert response.json()["requestId"] == "files-tag-test"
    assert response.json()["data"] == files_response()

def test_skill_tag_files_web_alias_returns_same() -> None:
    app = create_app()
    app.state.skill_tag_files_reader = lambda namespace, slug, tag, current_user_id: files_response()

    client = TestClient(app)
    response = client.get("/api/web/skills/global/demo/tags/latest/files")

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"] == files_response()

def test_skill_version_files_route_forwards_params_and_current_user_to_reader() -> None:
    seen: list[tuple[str, str, str, str | None]] = []
    app = create_app()

    def reader(
        namespace: str,
        slug: str,
        version: str,
        current_user_id: str | None,
    ) -> list[dict[str, object]]:
        seen.append((namespace, slug, version, current_user_id))
        return files_response()

    app.state.skill_version_files_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/versions/1.0.0/files",
        headers={"X-Mock-User-Id": " owner-1 "},
    )

    assert response.status_code == 200
    assert seen == [("global", "demo", "1.0.0", "owner-1")]

def test_skill_version_files_route_forwards_blank_current_user_as_none() -> None:
    seen: list[str | None] = []
    app = create_app()

    def reader(
        namespace: str,
        slug: str,
        version: str,
        current_user_id: str | None,
    ) -> list[dict[str, object]]:
        seen.append(current_user_id)
        return files_response()

    app.state.skill_version_files_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/web/skills/global/demo/versions/1.0.0/files",
        headers={"X-Mock-User-Id": "   "},
    )

    assert response.status_code == 200
    assert seen == [None]


def test_skill_version_files_route_uses_session_principal_for_owner_preview() -> None:
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
    ) -> list[dict[str, object]]:
        seen.append(current_user_id)
        return files_response()

    app.state.skill_version_files_reader = reader
    client = TestClient(app)
    client.post("/api/v1/auth/local/login", json={"username": "owner", "password": "Abcd123!"})

    response = client.get("/api/web/skills/global/demo/versions/1.0.0/files")

    assert response.status_code == 200
    assert seen == ["owner-1"]


def test_read_skill_version_files_allows_owner_preview_without_latest_pointer() -> None:
    result = asyncio.run(
        skills.read_skill_version_files(
            _FakeEngine(_VersionFilesOwnerPreviewWithoutLatestConnection()),
            "global",
            "demo",
            "1.0.0",
            "owner-1",
        )
    )

    assert result == [
        {
            "id": 201,
            "filePath": "SKILL.md",
            "fileSize": 10,
            "contentType": "text/markdown",
            "sha256": "hash",
        }
    ]


def test_skill_tag_files_route_forwards_params_and_current_user_to_reader() -> None:
    seen: list[tuple[str, str, str, str | None]] = []
    app = create_app()

    def reader(
        namespace: str,
        slug: str,
        tag: str,
        current_user_id: str | None,
    ) -> list[dict[str, object]]:
        seen.append((namespace, slug, tag, current_user_id))
        return files_response()

    app.state.skill_tag_files_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/tags/stable/files",
        headers={"X-Mock-User-Id": " owner-1 "},
    )

    assert response.status_code == 200
    assert seen == [("global", "demo", "stable", "owner-1")]

def test_skill_tag_files_route_forwards_blank_current_user_as_none() -> None:
    seen: list[str | None] = []
    app = create_app()

    def reader(
        namespace: str,
        slug: str,
        tag: str,
        current_user_id: str | None,
    ) -> list[dict[str, object]]:
        seen.append(current_user_id)
        return files_response()

    app.state.skill_tag_files_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/web/skills/global/demo/tags/stable/files",
        headers={"X-Mock-User-Id": "   "},
    )

    assert response.status_code == 200
    assert seen == [None]


def test_read_skill_tag_files_does_not_hardcode_public_skill_visibility() -> None:
    result = asyncio.run(
        skills.read_skill_tag_files(
            _FakeEngine(_TagFilesConnection()),
            "global",
            "demo",
            "latest",
            "owner-1",
        )
    )

    assert result == [
        {
            "id": 201,
            "filePath": "SKILL.md",
            "fileSize": 10,
            "contentType": "text/markdown",
            "sha256": "hash",
        }
    ]

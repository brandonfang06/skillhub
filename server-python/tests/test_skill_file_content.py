import asyncio

from fastapi.testclient import TestClient

import pytest

from app.api import skills
from app.api.skills import SkillResolveError, read_local_storage_bytes
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


class _VersionFileContentConnection:
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
            return _FakeResult({"id": 101, "status": "PENDING_REVIEW"})
        if "FROM skill_file" in sql:
            return _FakeResult({"file_path": "SKILL.md", "storage_key": "objects/skill"})
        raise AssertionError(f"unexpected SQL: {sql}")


class _TagFileContentConnection:
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
            return _FakeResult({"file_path": "SKILL.md", "storage_key": "objects/skill"})
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


def test_skill_version_file_content_route_returns_raw_bytes() -> None:
    app = create_app()
    app.state.skill_version_file_content_reader = (
        lambda namespace, slug, version, file_path, current_user_id: b"version bytes"
    )

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/versions/1.0.0/file",
        params={"path": "SKILL.md"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.content == b"version bytes"


def test_skill_version_file_content_web_alias_returns_raw_bytes() -> None:
    app = create_app()
    app.state.skill_version_file_content_reader = (
        lambda namespace, slug, version, file_path, current_user_id: b"web version bytes"
    )

    client = TestClient(app)
    response = client.get(
        "/api/web/skills/global/demo/versions/1.0.0/file",
        params={"path": "SKILL.md"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.content == b"web version bytes"


def test_skill_tag_file_content_route_returns_raw_bytes() -> None:
    app = create_app()
    app.state.skill_tag_file_content_reader = (
        lambda namespace, slug, tag, file_path, current_user_id: b"tag bytes"
    )

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/global/demo/tags/stable/file",
        params={"path": "README.md"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.content == b"tag bytes"


def test_skill_tag_file_content_web_alias_returns_raw_bytes() -> None:
    app = create_app()
    app.state.skill_tag_file_content_reader = (
        lambda namespace, slug, tag, file_path, current_user_id: b"web tag bytes"
    )

    client = TestClient(app)
    response = client.get(
        "/api/web/skills/global/demo/tags/stable/file",
        params={"path": "README.md"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.content == b"web tag bytes"


def test_skill_version_file_content_route_forwards_params_and_current_user() -> None:
    seen: list[tuple[str, str, str, str, str | None]] = []
    app = create_app()

    def reader(
        namespace: str,
        slug: str,
        version: str,
        file_path: str,
        current_user_id: str | None,
    ) -> bytes:
        seen.append((namespace, slug, version, file_path, current_user_id))
        return b"ok"

    app.state.skill_version_file_content_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/team/demo/versions/1.1.0/file",
        params={"path": "src/app.py"},
        headers={"X-Mock-User-Id": " owner-1 "},
    )

    assert response.status_code == 200
    assert seen == [("team", "demo", "1.1.0", "src/app.py", "owner-1")]


def test_skill_version_file_content_web_alias_forwards_params_and_current_user() -> None:
    seen: list[tuple[str, str, str, str, str | None]] = []
    app = create_app()

    def reader(
        namespace: str,
        slug: str,
        version: str,
        file_path: str,
        current_user_id: str | None,
    ) -> bytes:
        seen.append((namespace, slug, version, file_path, current_user_id))
        return b"ok"

    app.state.skill_version_file_content_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/web/skills/team/demo/versions/1.1.0/file",
        params={"path": "src/app.py"},
        headers={"X-Mock-User-Id": " owner-1 "},
    )

    assert response.status_code == 200
    assert seen == [("team", "demo", "1.1.0", "src/app.py", "owner-1")]


def test_skill_tag_file_content_route_forwards_params_and_current_user() -> None:
    seen: list[tuple[str, str, str, str, str | None]] = []
    app = create_app()

    def reader(
        namespace: str,
        slug: str,
        tag: str,
        file_path: str,
        current_user_id: str | None,
    ) -> bytes:
        seen.append((namespace, slug, tag, file_path, current_user_id))
        return b"ok"

    app.state.skill_tag_file_content_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/team/demo/tags/stable/file",
        params={"path": "docs/guide.md"},
        headers={"X-Mock-User-Id": " local-admin "},
    )

    assert response.status_code == 200
    assert seen == [("team", "demo", "stable", "docs/guide.md", "local-admin")]


def test_skill_tag_file_content_web_alias_forwards_params_and_current_user() -> None:
    seen: list[tuple[str, str, str, str, str | None]] = []
    app = create_app()

    def reader(
        namespace: str,
        slug: str,
        tag: str,
        file_path: str,
        current_user_id: str | None,
    ) -> bytes:
        seen.append((namespace, slug, tag, file_path, current_user_id))
        return b"ok"

    app.state.skill_tag_file_content_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/web/skills/team/demo/tags/stable/file",
        params={"path": "docs/guide.md"},
        headers={"X-Mock-User-Id": " local-admin "},
    )

    assert response.status_code == 200
    assert seen == [("team", "demo", "stable", "docs/guide.md", "local-admin")]


def test_skill_file_content_route_forwards_blank_current_user_as_none() -> None:
    seen: list[str | None] = []
    app = create_app()

    def reader(
        namespace: str,
        slug: str,
        version: str,
        file_path: str,
        current_user_id: str | None,
    ) -> bytes:
        seen.append(current_user_id)
        return b"ok"

    app.state.skill_version_file_content_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/team/demo/versions/1.0.0/file",
        params={"path": "SKILL.md"},
        headers={"X-Mock-User-Id": "   "},
    )

    assert response.status_code == 200
    assert seen == [None]


def test_skill_file_content_route_maps_reader_error_to_bad_request() -> None:
    app = create_app()

    def reader(
        namespace: str,
        slug: str,
        version: str,
        file_path: str,
        current_user_id: str | None,
    ) -> bytes:
        raise SkillResolveError("error.skill.file.notFound")

    app.state.skill_version_file_content_reader = reader

    client = TestClient(app)
    response = client.get(
        "/api/v1/skills/team/demo/versions/1.0.0/file",
        params={"path": "missing.md"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "error.skill.file.notFound"


def test_read_local_storage_bytes_reads_exact_bytes(tmp_path) -> None:
    target = tmp_path / "packages" / "demo" / "SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"\x00skill bytes\n")

    assert read_local_storage_bytes(str(tmp_path), "packages/demo/SKILL.md") == b"\x00skill bytes\n"


def test_read_local_storage_bytes_missing_key_raises_file_not_found(tmp_path) -> None:
    with pytest.raises(SkillResolveError, match="error.skill.file.notFound"):
        read_local_storage_bytes(str(tmp_path), "packages/demo/missing.md")


def test_read_local_storage_bytes_rejects_path_traversal(tmp_path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_bytes(b"outside")

    with pytest.raises(SkillResolveError, match="error.skill.file.notFound"):
        read_local_storage_bytes(str(tmp_path), "../outside.txt")


def test_assert_version_file_content_access_rejects_non_manager_preview() -> None:
    from app.api.skills import assert_version_file_content_access

    with pytest.raises(SkillResolveError, match="error.skill.version.notPublished"):
        assert_version_file_content_access({"status": "PENDING_REVIEW"}, can_manage=False)


def test_assert_version_file_content_access_allows_manager_preview() -> None:
    from app.api.skills import assert_version_file_content_access

    assert_version_file_content_access({"status": "PENDING_REVIEW"}, can_manage=True)


def test_read_file_content_from_row_uses_storage_key(tmp_path) -> None:
    from app.api.skills import read_file_content_from_row

    target = tmp_path / "objects" / "demo.bin"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"\x01\x02demo")

    assert read_file_content_from_row(str(tmp_path), {"file_path": "demo.bin", "storage_key": "objects/demo.bin"}) == b"\x01\x02demo"


def test_read_file_content_from_row_maps_missing_storage_to_file_not_found(tmp_path) -> None:
    from app.api.skills import read_file_content_from_row

    with pytest.raises(SkillResolveError, match="error.skill.file.notFound"):
        read_file_content_from_row(str(tmp_path), {"file_path": "missing.md", "storage_key": "objects/missing.md"})


def test_read_skill_version_file_content_does_not_hardcode_public_skill_visibility(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(skills, "read_file_content_from_row", lambda storage_base_path, file_row: b"preview")

    result = asyncio.run(
        skills.read_skill_version_file_content(
            _FakeEngine(_VersionFileContentConnection()),
            "unused",
            "global",
            "demo",
            "1.1.0",
            "SKILL.md",
            "owner-1",
        )
    )

    assert result == b"preview"


def test_read_skill_tag_file_content_does_not_hardcode_public_skill_visibility(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(skills, "read_file_content_from_row", lambda storage_base_path, file_row: b"tag")

    result = asyncio.run(
        skills.read_skill_tag_file_content(
            _FakeEngine(_TagFileContentConnection()),
            "unused",
            "global",
            "demo",
            "latest",
            "SKILL.md",
            "owner-1",
        )
    )

    assert result == b"tag"

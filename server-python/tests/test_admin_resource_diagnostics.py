from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.admin.resource_diagnostics import read_skill_resource_diagnostics
from app.main import create_app


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def one_or_none(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)


class FakeConnection:
    def __init__(self, *, versions: list[dict[str, Any]], files: list[dict[str, Any]]) -> None:
        self.versions = versions
        self.files = files

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        if "FROM skill s" in sql:
            return FakeResult(
                [
                    {
                        "skill_id": 10,
                        "slug": "broken-skill",
                        "namespace": "team-a",
                        "namespace_status": "ARCHIVED",
                        "latest_version_id": 101,
                    }
                ]
            )
        if "FROM skill_version" in sql:
            return FakeResult(self.versions)
        if "FROM skill_file" in sql:
            return FakeResult(self.files)
        raise AssertionError(f"unexpected SQL: {sql}")


class FakeConnectionContext:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def connect(self) -> FakeConnectionContext:
        return FakeConnectionContext(self.connection)


class FakeStorage:
    def __init__(self, existing: set[str] | None = None, error: Exception | None = None) -> None:
        self.existing = existing or set()
        self.error = error
        self.checked: list[str] = []

    def exists(self, key: str) -> bool:
        self.checked.append(key)
        if self.error is not None:
            raise self.error
        return key in self.existing


class FileProbeErrorStorage(FakeStorage):
    def exists(self, key: str) -> bool:
        self.checked.append(key)
        if key.startswith("skills/"):
            raise PermissionError("forbidden")
        return True


def version(version_id: int = 101) -> dict[str, Any]:
    return {"id": version_id, "version": "1.0.0", "status": "PUBLISHED", "file_count": 1}


def file_row(index: int = 0, *, storage_key: str | None = None) -> dict[str, Any]:
    return {
        "version_id": 101,
        "file_path": f"file-{index}.md",
        "storage_key": storage_key if storage_key is not None else f"skills/10/101/file-{index}.md",
    }


@pytest.mark.anyio
async def test_resource_diagnostics_reports_healthy_resources() -> None:
    files = [file_row()]
    storage = FakeStorage({files[0]["storage_key"], "packages/10/101/bundle.zip"})

    result = await read_skill_resource_diagnostics(
        FakeEngine(FakeConnection(versions=[version()], files=files)),
        "unused",
        10,
        storage=storage,
    )

    assert result["diagnosticStatus"] == "HEALTHY"
    assert result["checkedObjectCount"] == 2
    assert result["missingObjects"] == []


@pytest.mark.anyio
async def test_resource_diagnostics_distinguishes_db_and_storage_failures() -> None:
    missing_db = await read_skill_resource_diagnostics(
        FakeEngine(FakeConnection(versions=[version()], files=[])),
        "unused",
        10,
        storage=FakeStorage({"packages/10/101/bundle.zip"}),
    )
    assert missing_db["diagnosticStatus"] == "MISSING_DB_FILES"

    blank_key = file_row(storage_key=" ")
    missing_key = await read_skill_resource_diagnostics(
        FakeEngine(FakeConnection(versions=[version()], files=[blank_key])),
        "unused",
        10,
        storage=FakeStorage({"packages/10/101/bundle.zip"}),
    )
    assert missing_key["diagnosticStatus"] == "MISSING_STORAGE_KEYS"
    assert missing_key["blankStorageKeyCount"] == 1

    missing_object = await read_skill_resource_diagnostics(
        FakeEngine(FakeConnection(versions=[version()], files=[file_row()])),
        "unused",
        10,
        storage=FakeStorage(),
    )
    assert missing_object["diagnosticStatus"] == "MISSING_OBJECTS"
    assert len(missing_object["missingObjects"]) == 2


@pytest.mark.anyio
async def test_resource_diagnostics_reports_any_version_without_db_files() -> None:
    versions = [version(100), version(101)]
    latest_file = file_row()
    storage = FakeStorage({str(latest_file["storage_key"]), "packages/10/100/bundle.zip", "packages/10/101/bundle.zip"})

    result = await read_skill_resource_diagnostics(
        FakeEngine(FakeConnection(versions=versions, files=[latest_file])),
        "unused",
        10,
        storage=storage,
    )

    assert result["diagnosticStatus"] == "MISSING_DB_FILES"
    assert result["versionsWithoutFiles"] == [100]


@pytest.mark.anyio
async def test_resource_diagnostics_caps_file_probes_without_claiming_missing() -> None:
    files = [file_row(index) for index in range(501)]
    existing = {str(row["storage_key"]) for row in files}
    existing.add("packages/10/101/bundle.zip")
    storage = FakeStorage(existing)

    result = await read_skill_resource_diagnostics(
        FakeEngine(FakeConnection(versions=[version()], files=files)),
        "unused",
        10,
        storage=storage,
    )

    assert result["diagnosticStatus"] == "PARTIAL"
    assert result["checkedFileObjectCount"] == 500
    assert result["uncheckedFileObjectCount"] == 1
    assert result["missingObjects"] == []


@pytest.mark.anyio
async def test_resource_diagnostics_marks_probe_errors_unverified() -> None:
    result = await read_skill_resource_diagnostics(
        FakeEngine(FakeConnection(versions=[version()], files=[file_row()])),
        "unused",
        10,
        storage=FakeStorage(error=PermissionError("forbidden")),
    )

    assert result["diagnosticStatus"] == "UNVERIFIED"
    assert result["storageProbeError"] == {"code": "STORAGE_PROBE_FAILED"}
    assert result["missingObjects"] == []


@pytest.mark.anyio
async def test_resource_diagnostics_does_not_count_bundle_probes_as_file_probes() -> None:
    result = await read_skill_resource_diagnostics(
        FakeEngine(FakeConnection(versions=[version()], files=[file_row()])),
        "unused",
        10,
        storage=FileProbeErrorStorage(),
    )

    assert result["checkedObjectCount"] == 1
    assert result["checkedFileObjectCount"] == 0


def auth_user(user_id: str, roles: list[str], *, provider: str = "mock") -> dict[str, object]:
    return {
        "userId": user_id,
        "displayName": user_id,
        "email": f"{user_id}@example.test",
        "avatarUrl": "",
        "oauthProvider": provider,
        "platformRoles": roles,
    }


def test_resource_diagnostics_route_is_session_super_admin_only() -> None:
    app = create_app()
    app.state.auth_me_reader = lambda user_id: auth_user(
        user_id,
        ["SUPER_ADMIN"] if user_id == "admin" else ["SKILL_ADMIN"],
    )
    app.state.auth_bearer_reader = lambda token: auth_user("token-admin", ["SUPER_ADMIN"], provider="api_token")
    app.state.admin_skill_resource_diagnostics_reader = lambda skill_id: {"skillId": skill_id}
    client = TestClient(app)

    assert client.get("/api/v1/admin/skills/10/resource-diagnostics").status_code == 401
    assert client.get(
        "/api/v1/admin/skills/10/resource-diagnostics",
        headers={"X-Mock-User-Id": "skill-admin"},
    ).status_code == 403
    assert client.get(
        "/api/v1/admin/skills/10/resource-diagnostics",
        headers={"Authorization": "Bearer valid"},
    ).status_code == 403
    response = client.get(
        "/api/v1/admin/skills/10/resource-diagnostics",
        headers={"X-Mock-User-Id": "admin"},
    )
    assert response.status_code == 200
    assert response.json()["data"] == {"skillId": 10}

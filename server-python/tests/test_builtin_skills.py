from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zipfile import ZipFile

import pytest

from app.builtin_skills import (
    SYSTEM_PUBLISHER_ID,
    download_builtin_skill_package,
    is_allowed_builtin_skill_url,
    load_builtin_skill_manifest,
    synchronize_builtin_skills,
)


class FakeMappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def one_or_none(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None, row: dict[str, Any] | None = None) -> None:
        self.rows = rows if rows is not None else ([row] if row is not None else [])

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.rows)


class FakeTransaction:
    def __init__(self, connection: "FakeBuiltinSkillConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "FakeBuiltinSkillConnection":
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: "FakeBuiltinSkillConnection") -> None:
        self.connection = connection

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self.connection)


class FakeBuiltinSkillConnection:
    def __init__(self) -> None:
        self.namespaces = {"global": {"id": 1, "slug": "global"}}
        self.users: dict[str, dict[str, Any]] = {}
        self.namespace_members: list[dict[str, Any]] = []
        self.skills: list[dict[str, Any]] = []
        self.versions: dict[int, list[dict[str, Any]]] = {}

    async def execute(self, statement: object, params: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        bound = params or {}
        if "FROM namespace" in sql and "slug = :slug" in sql:
            namespace = self.namespaces.get(str(bound["slug"]))
            return FakeResult(row=namespace.copy() if namespace else None)
        if "FROM user_account" in sql and "id = :user_id" in sql:
            user = self.users.get(str(bound["user_id"]))
            return FakeResult(row=user.copy() if user else None)
        if "INSERT INTO user_account" in sql:
            self.users[str(bound["id"])] = {
                "id": str(bound["id"]),
                "display_name": str(bound["display_name"]),
                "system_account": True,
            }
            return FakeResult()
        if "FROM namespace_member" in sql:
            row = next(
                (
                    member
                    for member in self.namespace_members
                    if member["namespace_id"] == bound["namespace_id"] and member["user_id"] == bound["user_id"]
                ),
                None,
            )
            return FakeResult(row=row.copy() if row else None)
        if "INSERT INTO namespace_member" in sql:
            self.namespace_members.append(
                {"namespace_id": bound["namespace_id"], "user_id": bound["user_id"], "role": "OWNER"}
            )
            return FakeResult()
        if "FROM skill" in sql and "namespace_id = :namespace_id" in sql:
            rows = [
                row.copy()
                for row in self.skills
                if row["namespace_id"] == bound["namespace_id"] and row["slug"] == bound["slug"]
            ]
            return FakeResult(rows=rows)
        if "FROM skill_version" in sql:
            rows = [
                row.copy()
                for row in self.versions.get(int(bound["skill_id"]), [])
                if row["version"] == bound["version"]
            ]
            return FakeResult(row=rows[0] if rows else None)
        raise AssertionError(f"unexpected SQL: {sql}")


def skill_zip(*, name: str = "SkillHub Hello", version: str = "1.0.0") -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "SKILL.md",
            f"---\nname: {name}\ndescription: Built in hello\nversion: {version}\n---\n# Hello\n",
        )
        archive.writestr("README.md", "# Hello\n")
    return buffer.getvalue()


def settings() -> SimpleNamespace:
    return SimpleNamespace(storage_base_path="C:/tmp/skillhub-storage")


def test_builtin_skill_manifest_loader_validates_limits_and_duplicates(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "skills": [
                    {"slug": "skillhub-hello", "version": "1.0.0", "url": "https://bjcdn.openstorage.cn/hello.zip"},
                    {"slug": "skillhub-hello", "version": "1.0.0", "url": "https://bjcdn.openstorage.cn/dup.zip"},
                    {"slug": "Bad Slug", "version": "1.0.0", "url": "https://bjcdn.openstorage.cn/bad.zip"},
                    {"slug": "missing-version", "url": "https://bjcdn.openstorage.cn/bad.zip"},
                ]
            }
        ),
        encoding="utf-8",
    )

    items = load_builtin_skill_manifest(manifest)

    assert [(item.slug, item.version, item.url) for item in items] == [
        ("skillhub-hello", "1.0.0", "https://bjcdn.openstorage.cn/hello.zip")
    ]


def test_builtin_skill_downloader_restricts_remote_urls() -> None:
    assert is_allowed_builtin_skill_url("https://bjcdn.openstorage.cn/a.zip")
    assert is_allowed_builtin_skill_url("https://assets.bjcdn.openstorage.cn/a.zip")
    assert not is_allowed_builtin_skill_url("http://bjcdn.openstorage.cn/a.zip")
    assert not is_allowed_builtin_skill_url("https://localhost/a.zip")
    assert not is_allowed_builtin_skill_url("https://127.0.0.1/a.zip")
    assert not is_allowed_builtin_skill_url("https://example.com/a.zip")

    assert (
        download_builtin_skill_package(
            "https://bjcdn.openstorage.cn/a.zip",
            max_package_size=100,
            http_get=lambda url, timeout, max_size: (200, b"x" * 101),
        )
        is None
    )
    assert download_builtin_skill_package(
        "https://bjcdn.openstorage.cn/a.zip",
        max_package_size=100,
        http_get=lambda url, timeout, max_size: (200, b"zip"),
    ) == b"zip"


@pytest.mark.anyio
async def test_builtin_skill_sync_ensures_system_publisher_and_publishes_manifest_item(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "skills": [
                    {
                        "slug": "skillhub-hello",
                        "version": "1.0.0",
                        "url": "https://bjcdn.openstorage.cn/hello.zip",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    connection = FakeBuiltinSkillConnection()
    published: list[tuple[str, list[str]]] = []

    summary = await synchronize_builtin_skills(
        FakeEngine(connection),
        settings(),
        environ={
            "SKILLHUB_BUILTIN_SKILLS_ENABLED": "true",
            "SKILLHUB_BUILTIN_SKILLS_MANIFEST_PATH": str(manifest),
        },
        downloader=lambda url: skill_zip(),
        publisher=lambda item, entries: published.append((item.slug, [entry.path for entry in entries])),
    )

    assert summary.published == 1
    assert connection.users[SYSTEM_PUBLISHER_ID]["system_account"] is True
    assert connection.namespace_members == [{"namespace_id": 1, "user_id": SYSTEM_PUBLISHER_ID, "role": "OWNER"}]
    assert published == [("skillhub-hello", ["SKILL.md", "README.md"])]


@pytest.mark.anyio
async def test_builtin_skill_sync_skips_other_owner_conflict_before_download(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "skills": [
                    {
                        "slug": "skillhub-hello",
                        "version": "1.0.0",
                        "url": "https://bjcdn.openstorage.cn/hello.zip",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    connection = FakeBuiltinSkillConnection()
    connection.skills.append({"id": 99, "namespace_id": 1, "slug": "skillhub-hello", "owner_id": "real-user"})
    downloaded = False

    def downloader(url: str) -> bytes | None:
        nonlocal downloaded
        downloaded = True
        return skill_zip()

    summary = await synchronize_builtin_skills(
        FakeEngine(connection),
        settings(),
        environ={
            "SKILLHUB_BUILTIN_SKILLS_ENABLED": "true",
            "SKILLHUB_BUILTIN_SKILLS_MANIFEST_PATH": str(manifest),
        },
        downloader=downloader,
        publisher=lambda item, entries: None,
    )

    assert summary.conflict_skipped == 1
    assert not downloaded

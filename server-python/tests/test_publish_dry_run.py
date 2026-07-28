from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from app.publish.dry_run import (
    PublishConflictContext,
    PublishDryRunInput,
    PublishDryRunRepository,
    PublishNamespaceContext,
    slugify,
    validate_publish_dry_run,
)
from app.publish.package import PackageEntry


def skill_md(name: str = "Agent Helper", version: str | None = "1.0.0") -> bytes:
    version_line = f"version: {version}\n" if version is not None else ""
    return f"---\nname: {name}\ndescription: Helps agents\n{version_line}---\n# Skill\n".encode()


def package_entries(content: bytes | None = None) -> list[PackageEntry]:
    return [
        PackageEntry("SKILL.md", content or skill_md(), "text/markdown"),
        PackageEntry("src/main.py", b"print('ok')", "text/x-python"),
    ]


@dataclass
class FakeDryRunRepository:
    namespace_context: PublishNamespaceContext | None = PublishNamespaceContext(
        namespace_id=10,
        status="ACTIVE",
        publisher_is_member=True,
        is_super_admin=False,
    )
    conflict_context: PublishConflictContext = PublishConflictContext()
    conflict_calls: int = 0

    async def read_namespace_context(
        self,
        namespace_slug: str,
        publisher_id: str,
        platform_roles: set[str],
    ) -> PublishNamespaceContext | None:
        if self.namespace_context is None:
            return None
        return PublishNamespaceContext(
            namespace_id=self.namespace_context.namespace_id,
            status=self.namespace_context.status,
            publisher_is_member=self.namespace_context.publisher_is_member,
            is_super_admin="SUPER_ADMIN" in platform_roles,
        )

    async def read_publish_conflicts(
        self,
        namespace_id: int,
        skill_slug: str,
        publisher_id: str,
        resolved_version: str,
    ) -> PublishConflictContext:
        self.conflict_calls += 1
        return self.conflict_context


async def run_dry_run(
    repository: FakeDryRunRepository,
    *,
    entries: list[PackageEntry] | None = None,
    platform_roles: set[str] | None = None,
    visibility: str = "PUBLIC",
    allowed_extensions: set[str] | None = None,
) -> Any:
    return await validate_publish_dry_run(
        PublishDryRunInput(
            namespace_slug="global",
            entries=entries or package_entries(),
            publisher_id="local-user",
            visibility=visibility,
            platform_roles=platform_roles or set(),
            now=datetime(2026, 6, 8, 12, 30, 45, tzinfo=UTC),
            allowed_extensions=allowed_extensions,
        ),
        repository,
    )


@pytest.mark.anyio
async def test_valid_dry_run_resolves_slug_and_version() -> None:
    result = await run_dry_run(FakeDryRunRepository())

    assert result.valid
    assert result.errors == []
    assert result.warnings == []
    assert result.resolved_slug == "agent-helper"
    assert result.resolved_version == "1.0.0"


@pytest.mark.anyio
async def test_missing_namespace_returns_error_without_conflict_checks() -> None:
    repository = FakeDryRunRepository(namespace_context=None)

    result = await run_dry_run(repository)

    assert not result.valid
    assert result.errors == ["Namespace not found: global"]
    assert repository.conflict_calls == 0


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "message"),
    [
        ("FROZEN", "Namespace is frozen: global"),
        ("ARCHIVED", "Namespace is archived: global"),
    ],
)
async def test_unwritable_namespace_status_is_invalid(status: str, message: str) -> None:
    result = await run_dry_run(
        FakeDryRunRepository(
            namespace_context=PublishNamespaceContext(
                namespace_id=10,
                status=status,
                publisher_is_member=True,
                is_super_admin=False,
            )
        )
    )

    assert not result.valid
    assert message in result.errors


@pytest.mark.anyio
async def test_non_member_publisher_is_invalid() -> None:
    result = await run_dry_run(
        FakeDryRunRepository(
            namespace_context=PublishNamespaceContext(
                namespace_id=10,
                status="ACTIVE",
                publisher_is_member=False,
                is_super_admin=False,
            )
        )
    )

    assert not result.valid
    assert "Publisher is not a member of namespace: global" in result.errors


@pytest.mark.anyio
async def test_super_admin_bypasses_membership_check() -> None:
    result = await run_dry_run(
        FakeDryRunRepository(
            namespace_context=PublishNamespaceContext(
                namespace_id=10,
                status="ACTIVE",
                publisher_is_member=False,
                is_super_admin=True,
            )
        ),
        platform_roles={"SUPER_ADMIN"},
    )

    assert result.valid
    assert result.errors == []


@pytest.mark.anyio
async def test_invalid_package_returns_errors_before_conflict_checks() -> None:
    repository = FakeDryRunRepository()

    result = await run_dry_run(repository, entries=[PackageEntry("README.md", b"# demo", "text/markdown")])

    assert not result.valid
    assert "Package must contain SKILL.md at root" in result.errors
    assert result.resolved_slug is None
    assert result.resolved_version is None
    assert repository.conflict_calls == 0


@pytest.mark.anyio
async def test_missing_version_auto_generates_java_timestamp_version() -> None:
    result = await run_dry_run(FakeDryRunRepository(), entries=package_entries(skill_md(version=None)))

    assert result.valid
    assert result.resolved_slug == "agent-helper"
    assert result.resolved_version == "20260608123045"


def test_slugify_preserves_java_symbol_characters() -> None:
    assert slugify("A ♥ Skill") == "a-♥-skill"
    assert slugify("🚀 Rocket") == "🚀-rocket"


@pytest.mark.anyio
async def test_warning_only_package_is_invalid_for_dry_run() -> None:
    result = await run_dry_run(
        FakeDryRunRepository(),
        entries=package_entries() + [PackageEntry("binary.exe", b"binary", "application/octet-stream")],
    )

    assert not result.valid
    assert result.errors == []
    assert "Disallowed file extension: binary.exe" in result.warnings


@pytest.mark.anyio
async def test_runtime_allowed_extension_override_accepts_dot_files() -> None:
    result = await run_dry_run(
        FakeDryRunRepository(),
        entries=[
            PackageEntry("SKILL.md", skill_md(), "text/markdown"),
            PackageEntry("docs/diagram.dot", b"digraph G { a -> b }\n", "text/vnd.graphviz"),
        ],
        allowed_extensions={".md", ".dot"},
    )

    assert result.valid
    assert result.warnings == []


@pytest.mark.anyio
async def test_runtime_allowed_extension_override_replaces_default_allowlist_for_dry_run() -> None:
    result = await run_dry_run(FakeDryRunRepository(), allowed_extensions={".md", ".dot"})

    assert not result.valid
    assert result.errors == []
    assert "Disallowed file extension: src/main.py" in result.warnings


@pytest.mark.anyio
async def test_basic_secret_scan_warning_matches_java_wording() -> None:
    result = await run_dry_run(
        FakeDryRunRepository(),
        entries=package_entries()
        + [PackageEntry("config.yaml", b"api_key: sk-12345678901234567890", "application/x-yaml")],
    )

    assert not result.valid
    assert result.warnings == [
        "config.yaml line 1 contains a value that looks like a API key. "
        "Replace real credentials with placeholders before publishing."
    ]


@pytest.mark.anyio
async def test_placeholder_secret_values_do_not_warn() -> None:
    result = await run_dry_run(
        FakeDryRunRepository(),
        entries=package_entries() + [PackageEntry("config.yaml", b"api_key: replace-me-sample-value", "application/x-yaml")],
    )

    assert result.valid
    assert result.warnings == []


@pytest.mark.anyio
async def test_own_archived_skill_is_invalid() -> None:
    result = await run_dry_run(
        FakeDryRunRepository(conflict_context=PublishConflictContext(own_skill_status="ARCHIVED"))
    )

    assert not result.valid
    assert result.errors == ["Cannot publish to archived skill: agent-helper"]


@pytest.mark.anyio
async def test_own_published_version_is_invalid() -> None:
    result = await run_dry_run(
        FakeDryRunRepository(conflict_context=PublishConflictContext(own_version_status="PUBLISHED"))
    )

    assert not result.valid
    assert result.errors == ["Version already published: 1.0.0"]


@pytest.mark.anyio
async def test_own_rejected_version_requires_a_new_version_number() -> None:
    result = await run_dry_run(
        FakeDryRunRepository(conflict_context=PublishConflictContext(own_version_status="REJECTED"))
    )

    assert not result.valid
    assert result.errors == ["error.skill.publish.rejectedVersionReuse"]


@pytest.mark.anyio
async def test_other_owner_published_skill_blocks_name() -> None:
    result = await run_dry_run(
        FakeDryRunRepository(conflict_context=PublishConflictContext(other_owner_has_published=True))
    )

    assert not result.valid
    assert result.errors == ['Name conflict: slug "agent-helper" is already published by another user']


@pytest.mark.anyio
async def test_other_owner_unpublished_skill_does_not_block_name() -> None:
    result = await run_dry_run(
        FakeDryRunRepository(conflict_context=PublishConflictContext(other_owner_has_published=False))
    )

    assert result.valid


class FakeScalarResult:
    def __init__(self, row: Any) -> None:
        self.row = row

    def one_or_none(self) -> Any:
        return self.row


class FakeMappings:
    def __init__(self, row: Any) -> None:
        self.row = row

    def one_or_none(self) -> Any:
        return self.row


class FakeResult:
    def __init__(self, row: Any = None, scalar: Any = None) -> None:
        self.row = row
        self.scalar = scalar

    def mappings(self) -> FakeMappings:
        return FakeMappings(self.row)

    def scalar_one_or_none(self) -> Any:
        return self.scalar


class FakeConnection:
    def __init__(self, results: list[FakeResult]) -> None:
        self.results = results
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: Any, params: dict[str, Any]) -> FakeResult:
        self.statements.append(str(statement))
        self.params.append(params)
        return self.results.pop(0)


class FakeConnectionContext:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class FakeEngine:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    def connect(self) -> FakeConnectionContext:
        return FakeConnectionContext(self.connection)


@pytest.mark.anyio
async def test_repository_reads_namespace_context() -> None:
    connection = FakeConnection(
        [
            FakeResult(row={"id": 10, "status": "ACTIVE"}),
            FakeResult(scalar="OWNER"),
        ]
    )
    repository = PublishDryRunRepository(FakeEngine(connection))

    context = await repository.read_namespace_context("global", "local-user", set())

    assert context == PublishNamespaceContext(
        namespace_id=10,
        status="ACTIVE",
        publisher_is_member=True,
        is_super_admin=False,
    )
    assert "FROM namespace" in connection.statements[0]
    assert "FROM namespace_member" in connection.statements[1]


@pytest.mark.anyio
async def test_repository_super_admin_skips_membership_query() -> None:
    connection = FakeConnection([FakeResult(row={"id": 10, "status": "ACTIVE"})])
    repository = PublishDryRunRepository(FakeEngine(connection))

    context = await repository.read_namespace_context("global", "local-admin", {"SUPER_ADMIN"})

    assert context == PublishNamespaceContext(
        namespace_id=10,
        status="ACTIVE",
        publisher_is_member=False,
        is_super_admin=True,
    )
    assert len(connection.statements) == 1


@pytest.mark.anyio
async def test_repository_reads_publish_conflicts() -> None:
    connection = FakeConnection(
        [
            FakeResult(row={"id": 20, "status": "ACTIVE"}),
            FakeResult(scalar="PUBLISHED"),
            FakeResult(scalar=True),
        ]
    )
    repository = PublishDryRunRepository(FakeEngine(connection))

    context = await repository.read_publish_conflicts(10, "agent-helper", "local-user", "1.0.0")

    assert context == PublishConflictContext(
        own_skill_status="ACTIVE",
        own_version_status="PUBLISHED",
        other_owner_has_published=True,
    )
    assert "FROM skill" in connection.statements[0]
    assert "FROM skill_version" in connection.statements[1]
    assert "EXISTS" in connection.statements[2]

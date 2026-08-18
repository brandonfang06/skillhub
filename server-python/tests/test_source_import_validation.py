from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.publish.package import PackageEntry
from app.source_import.contracts import SourceIdentity, SourceServiceActor
from app.source_import.service import (
    IdentityAccount,
    NamespaceRecord,
    NamespaceSourceBinding,
    SourceImportConflict,
    SourceImportValidationError,
    SourceSkillRecord,
    SourceSkillVersionRecord,
    ValidateSourceSkillInput,
    validate_source_skill_in_transaction,
)
from app.source_import.source import (
    canonicalize_github_repository,
    content_fingerprint,
    validate_source_revision,
)


def account(user_id: str, *, login_name: str | None = None) -> IdentityAccount:
    return IdentityAccount(user_id, user_id.title(), "ACTIVE", "keycloak", login_name or user_id)


def skill_entries(*, name: str = "Code Review", version: str | None = None, body: str = "# Review") -> list[PackageEntry]:
    version_line = f"version: {version}\n" if version is not None else ""
    content = (
        "---\n"
        f"name: {name}\n"
        "description: Reviews code safely\n"
        f"{version_line}"
        "---\n"
        f"{body}\n"
    ).encode()
    return [PackageEntry("SKILL.md", content, "text/markdown")]


@dataclass
class FakeValidationRepository:
    namespace: NamespaceRecord
    namespace_binding: NamespaceSourceBinding
    owner: IdentityAccount

    def __init__(self) -> None:
        self.namespace = NamespaceRecord(10, "oss-mattpocock-skills", "OSS-mattpocock-skills", "TEAM", "ACTIVE")
        self.namespace_binding = NamespaceSourceBinding(20, 10, "https://github.com/mattpocock/skills")
        self.owner = account("namespace-owner")
        self.identities: dict[tuple[str, str], list[IdentityAccount]] = {}
        self.source_skills: dict[str, SourceSkillRecord] = {}
        self.skills_by_slug: dict[str, SourceSkillRecord] = {}
        self.versions: dict[tuple[int, str], SourceSkillVersionRecord] = {}
        self.members: set[tuple[int, str]] = {(10, "namespace-owner")}

    async def read_namespace(self, slug: str) -> NamespaceRecord | None:
        return self.namespace if slug == self.namespace.slug else None

    async def read_namespace_source_by_repository(self, repository_url: str) -> NamespaceSourceBinding | None:
        return self.namespace_binding if repository_url == self.namespace_binding.repository_url else None

    async def read_namespace_source_by_namespace(self, namespace_id: int) -> NamespaceSourceBinding | None:
        return self.namespace_binding if namespace_id == self.namespace.id else None

    async def read_namespace_owners(self, namespace_id: int) -> list[IdentityAccount]:
        return [self.owner] if namespace_id == self.namespace.id else []

    async def read_identity_accounts(self, provider_code: str, login_name: str) -> list[IdentityAccount]:
        return self.identities.get((provider_code, login_name), [])

    async def read_source_skill(self, namespace_source_id: int, source_path: str) -> SourceSkillRecord | None:
        assert namespace_source_id == self.namespace_binding.id
        return self.source_skills.get(source_path)

    async def read_skill_by_slug(self, namespace_id: int, slug: str) -> SourceSkillRecord | None:
        assert namespace_id == self.namespace.id
        return self.skills_by_slug.get(slug)

    async def read_source_skill_version(self, skill_id: int, version: str) -> SourceSkillVersionRecord | None:
        return self.versions.get((skill_id, version))

    async def read_source_skill_version_by_fingerprint(
        self,
        source_skill_id: int,
        fingerprint: str,
    ) -> SourceSkillVersionRecord | None:
        source_skill = next((item for item in self.source_skills.values() if item.source_id == source_skill_id), None)
        if source_skill is None:
            return None
        return next(
            (
                version
                for (skill_id, _name), version in self.versions.items()
                if skill_id == source_skill.skill_id and version.content_fingerprint == fingerprint
            ),
            None,
        )

    async def read_namespace_membership(self, namespace_id: int, user_id: str) -> str | None:
        return "MEMBER" if (namespace_id, user_id) in self.members else None

    async def create_namespace_source(self, **kwargs: object):  # pragma: no cover - not used by validation
        raise AssertionError(kwargs)


def validation_input(
    *,
    entries: list[PackageEntry] | None = None,
    version_override: str | None = "git-" + "a" * 40,
    initiator: SourceIdentity | None = None,
) -> ValidateSourceSkillInput:
    return ValidateSourceSkillInput(
        namespace_slug="oss-mattpocock-skills",
        repository=canonicalize_github_repository("https://github.com/mattpocock/skills"),
        revision=validate_source_revision("a" * 40, "BRANCH", "main"),
        source_path="skills/code-review",
        entries=entries or skill_entries(),
        version_override=version_override,
        initiator=initiator,
        service_actor=SourceServiceActor(
            "svc_importer", "gitlab-oss-importer", "GitLab OSS Importer"
        ),
    )


@pytest.mark.anyio
async def test_plans_new_unversioned_skill_with_deterministic_override_and_fallback_owner() -> None:
    repository = FakeValidationRepository()

    plan = await validate_source_skill_in_transaction(repository, validation_input())

    assert plan.outcome == "IMPORT"
    assert plan.package.effective_version == "git-" + "a" * 40
    assert plan.skill_slug == "code-review"
    assert plan.stable_owner.user_id == "namespace-owner"
    assert plan.review_submitter.user_id == "namespace-owner"
    assert plan.add_submitter_as_member is False
    assert plan.auto_publish is False
    assert plan.visibility == "PUBLIC"


@pytest.mark.anyio
async def test_plans_active_initiator_as_new_owner_and_namespace_member() -> None:
    repository = FakeValidationRepository()
    trigger = account("trigger-user", login_name="alice")
    repository.identities[("keycloak", "alice")] = [trigger]

    plan = await validate_source_skill_in_transaction(
        repository,
        validation_input(initiator=SourceIdentity("keycloak", "alice")),
    )

    assert plan.stable_owner == trigger
    assert plan.review_submitter == trigger
    assert plan.add_submitter_as_member is True


@pytest.mark.anyio
async def test_preserves_explicit_version_and_rejects_override() -> None:
    repository = FakeValidationRepository()
    plan = await validate_source_skill_in_transaction(
        repository,
        validation_input(entries=skill_entries(version="1.2.3"), version_override=None),
    )
    assert plan.package.effective_version == "1.2.3"

    with pytest.raises(SourceImportValidationError, match="version override"):
        await validate_source_skill_in_transaction(
            repository,
            validation_input(entries=skill_entries(version="1.2.3"), version_override="git-" + "a" * 40),
        )


@pytest.mark.anyio
async def test_requires_override_when_source_version_is_missing() -> None:
    with pytest.raises(SourceImportValidationError, match="version override"):
        await validate_source_skill_in_transaction(FakeValidationRepository(), validation_input(version_override=None))


@pytest.mark.anyio
async def test_preserves_existing_skill_owner_for_later_trigger() -> None:
    repository = FakeValidationRepository()
    existing = SourceSkillRecord(30, 20, "skills/code-review", 40, "code-review", "original-owner", "ACTIVE")
    repository.source_skills[existing.source_path] = existing
    repository.skills_by_slug[existing.slug] = existing
    trigger = account("later-trigger", login_name="bob")
    repository.identities[("keycloak", "bob")] = [trigger]

    plan = await validate_source_skill_in_transaction(
        repository,
        validation_input(initiator=SourceIdentity("keycloak", "bob")),
    )

    assert plan.stable_owner.user_id == "original-owner"
    assert plan.review_submitter == trigger


@pytest.mark.anyio
async def test_returns_already_imported_for_same_version_and_fingerprint() -> None:
    repository = FakeValidationRepository()
    entries = skill_entries(version="1.0.0")
    existing = SourceSkillRecord(30, 20, "skills/code-review", 40, "code-review", "original-owner", "ACTIVE")
    repository.source_skills[existing.source_path] = existing
    repository.versions[(40, "1.0.0")] = SourceSkillVersionRecord(
        50,
        40,
        "1.0.0",
        "PENDING_REVIEW",
        content_fingerprint(entries),
    )

    plan = await validate_source_skill_in_transaction(
        repository,
        validation_input(entries=entries, version_override=None),
    )

    assert plan.outcome == "SKIPPED_ALREADY_IMPORTED"


@pytest.mark.anyio
async def test_returns_unchanged_when_new_revision_has_same_source_content() -> None:
    repository = FakeValidationRepository()
    entries = skill_entries()
    existing = SourceSkillRecord(30, 20, "skills/code-review", 40, "code-review", "original-owner", "ACTIVE")
    repository.source_skills[existing.source_path] = existing
    repository.versions[(40, "git-" + "b" * 40)] = SourceSkillVersionRecord(
        50,
        40,
        "git-" + "b" * 40,
        "PENDING_REVIEW",
        content_fingerprint(entries),
    )

    plan = await validate_source_skill_in_transaction(repository, validation_input(entries=entries))

    assert plan.outcome == "SKIPPED_UNCHANGED"


@pytest.mark.anyio
async def test_rejects_source_path_slug_drift_and_immutable_version_conflict() -> None:
    repository = FakeValidationRepository()
    existing = SourceSkillRecord(30, 20, "skills/code-review", 40, "old-slug", "original-owner", "ACTIVE")
    repository.source_skills[existing.source_path] = existing
    with pytest.raises(SourceImportConflict, match="source identity drift"):
        await validate_source_skill_in_transaction(repository, validation_input())

    existing = SourceSkillRecord(30, 20, "skills/code-review", 40, "code-review", "original-owner", "ACTIVE")
    repository.source_skills[existing.source_path] = existing
    repository.versions[(40, "1.0.0")] = SourceSkillVersionRecord(50, 40, "1.0.0", "PUBLISHED", "f" * 64)
    with pytest.raises(SourceImportConflict, match="immutable version"):
        await validate_source_skill_in_transaction(
            repository,
            validation_input(entries=skill_entries(version="1.0.0"), version_override=None),
        )


@pytest.mark.anyio
async def test_rejects_native_skill_slug_collision_for_unbound_source_path() -> None:
    repository = FakeValidationRepository()
    repository.skills_by_slug["code-review"] = SourceSkillRecord(
        None,
        None,
        None,
        40,
        "code-review",
        "native-owner",
        "ACTIVE",
    )

    with pytest.raises(SourceImportConflict, match="not bound"):
        await validate_source_skill_in_transaction(repository, validation_input())


@pytest.mark.anyio
async def test_rejects_invalid_package_without_mutation() -> None:
    repository = FakeValidationRepository()
    invalid = [PackageEntry("README.md", b"missing skill", "text/markdown")]

    with pytest.raises(SourceImportValidationError, match="SKILL.md"):
        await validate_source_skill_in_transaction(repository, validation_input(entries=invalid))

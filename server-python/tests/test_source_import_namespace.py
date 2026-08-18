from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.source_import.contracts import SourceIdentity, SourceServiceActor
from app.source_import.service import (
    EnsureSourceNamespaceInput,
    IdentityAccount,
    NamespaceRecord,
    NamespaceSourceBinding,
    SourceImportConflict,
    SourceImportNotFound,
    ensure_source_namespace_in_transaction,
    resolve_attribution_user,
)
from app.source_import.source import canonicalize_github_repository


@dataclass
class FakeSourceImportRepository:
    identities: dict[tuple[str, str], list[IdentityAccount]]
    namespaces: dict[str, NamespaceRecord]
    bindings_by_repository: dict[str, NamespaceSourceBinding]
    bindings_by_namespace: dict[int, NamespaceSourceBinding]
    owners: dict[int, list[IdentityAccount]]

    def __init__(self) -> None:
        self.identities = {}
        self.namespaces = {}
        self.bindings_by_repository = {}
        self.bindings_by_namespace = {}
        self.owners = {}
        self.created: list[dict[str, object]] = []

    async def read_identity_accounts(self, provider_code: str, login_name: str) -> list[IdentityAccount]:
        return self.identities.get((provider_code, login_name), [])

    async def read_namespace(self, slug: str) -> NamespaceRecord | None:
        return self.namespaces.get(slug)

    async def read_namespace_source_by_repository(self, repository_url: str) -> NamespaceSourceBinding | None:
        return self.bindings_by_repository.get(repository_url)

    async def read_namespace_source_by_namespace(self, namespace_id: int) -> NamespaceSourceBinding | None:
        return self.bindings_by_namespace.get(namespace_id)

    async def read_namespace_owners(self, namespace_id: int) -> list[IdentityAccount]:
        return self.owners.get(namespace_id, [])

    async def create_namespace_source(
        self,
        *,
        slug: str,
        display_name: str,
        repository_url: str,
        owner: IdentityAccount,
        service_actor: SourceServiceActor,
        request_id: str | None,
    ) -> tuple[NamespaceRecord, NamespaceSourceBinding]:
        namespace = NamespaceRecord(
            id=101,
            slug=slug,
            display_name=display_name,
            type="TEAM",
            status="ACTIVE",
        )
        binding = NamespaceSourceBinding(id=201, namespace_id=101, repository_url=repository_url)
        self.namespaces[slug] = namespace
        self.bindings_by_repository[repository_url] = binding
        self.bindings_by_namespace[101] = binding
        self.owners[101] = [owner]
        self.created.append(
            {
                "slug": slug,
                "display_name": display_name,
                "repository_url": repository_url,
                "owner_id": owner.user_id,
                "service_principal_id": service_actor.service_principal_id,
                "request_id": request_id,
            }
        )
        return namespace, binding


def account(
    user_id: str,
    *,
    status: str = "ACTIVE",
    provider_code: str = "keycloak",
    login_name: str | None = None,
) -> IdentityAccount:
    return IdentityAccount(
        user_id=user_id,
        display_name=f"Display {user_id}",
        status=status,
        provider_code=provider_code,
        login_name=login_name or user_id,
    )


def ensure_input() -> EnsureSourceNamespaceInput:
    return EnsureSourceNamespaceInput(
        repository=canonicalize_github_repository("https://github.com/mattpocock/skills"),
        requested_display_name="OSS-mattpocock-skills",
        fallback_owner=SourceIdentity(provider_code="keycloak", login_name="platform-owner"),
        service_actor=SourceServiceActor(
            "svc_importer", "gitlab-oss-importer", "GitLab OSS Importer"
        ),
        request_id="request-1",
    )


@pytest.mark.anyio
async def test_creates_missing_namespace_with_fallback_owner_and_repository_binding() -> None:
    repository = FakeSourceImportRepository()
    fallback = account("owner-user", login_name="platform-owner")
    repository.identities[("keycloak", "platform-owner")] = [fallback]

    result = await ensure_source_namespace_in_transaction(repository, ensure_input())

    assert result.outcome == "CREATED"
    assert result.namespace.slug == "oss-mattpocock-skills"
    assert result.owner == fallback
    assert repository.created == [
        {
            "slug": "oss-mattpocock-skills",
            "display_name": "OSS-mattpocock-skills",
            "repository_url": "https://github.com/mattpocock/skills",
            "owner_id": "owner-user",
            "service_principal_id": "svc_importer",
            "request_id": "request-1",
        }
    ]


@pytest.mark.anyio
async def test_returns_existing_binding_without_using_configured_fallback_owner() -> None:
    repository = FakeSourceImportRepository()
    namespace = NamespaceRecord(7, "oss-mattpocock-skills", "Custom display", "TEAM", "ACTIVE")
    binding = NamespaceSourceBinding(8, 7, "https://github.com/mattpocock/skills")
    current_owner = account("current-owner")
    repository.namespaces[namespace.slug] = namespace
    repository.bindings_by_repository[binding.repository_url] = binding
    repository.bindings_by_namespace[namespace.id] = binding
    repository.owners[namespace.id] = [current_owner]

    result = await ensure_source_namespace_in_transaction(repository, ensure_input())

    assert result.outcome == "EXISTING"
    assert result.namespace.display_name == "Custom display"
    assert result.owner == current_owner
    assert repository.created == []


@pytest.mark.anyio
async def test_rejects_repository_bound_to_another_namespace() -> None:
    repository = FakeSourceImportRepository()
    repository.bindings_by_repository["https://github.com/mattpocock/skills"] = NamespaceSourceBinding(
        8,
        99,
        "https://github.com/mattpocock/skills",
    )

    with pytest.raises(SourceImportConflict, match="repository"):
        await ensure_source_namespace_in_transaction(repository, ensure_input())


@pytest.mark.anyio
async def test_rejects_existing_slug_without_matching_source_binding() -> None:
    repository = FakeSourceImportRepository()
    repository.namespaces["oss-mattpocock-skills"] = NamespaceRecord(
        7,
        "oss-mattpocock-skills",
        "Collision",
        "TEAM",
        "ACTIVE",
    )

    with pytest.raises(SourceImportConflict, match="slug"):
        await ensure_source_namespace_in_transaction(repository, ensure_input())


@pytest.mark.anyio
@pytest.mark.parametrize(("namespace_type", "status"), [("GLOBAL", "ACTIVE"), ("TEAM", "FROZEN"), ("TEAM", "ARCHIVED")])
async def test_rejects_non_writable_existing_namespace(namespace_type: str, status: str) -> None:
    repository = FakeSourceImportRepository()
    namespace = NamespaceRecord(7, "oss-mattpocock-skills", "Existing", namespace_type, status)
    binding = NamespaceSourceBinding(8, 7, "https://github.com/mattpocock/skills")
    repository.namespaces[namespace.slug] = namespace
    repository.bindings_by_repository[binding.repository_url] = binding
    repository.bindings_by_namespace[namespace.id] = binding
    repository.owners[namespace.id] = [account("owner")]

    with pytest.raises(SourceImportConflict, match="writable"):
        await ensure_source_namespace_in_transaction(repository, ensure_input())


@pytest.mark.anyio
async def test_requires_exactly_one_active_fallback_identity_for_creation() -> None:
    repository = FakeSourceImportRepository()

    with pytest.raises(SourceImportNotFound, match="fallback owner"):
        await ensure_source_namespace_in_transaction(repository, ensure_input())

    repository.identities[("keycloak", "platform-owner")] = [account("one"), account("two")]
    with pytest.raises(SourceImportConflict, match="ambiguous"):
        await ensure_source_namespace_in_transaction(repository, ensure_input())

    repository.identities[("keycloak", "platform-owner")] = [account("disabled", status="DISABLED")]
    with pytest.raises(SourceImportConflict, match="not active"):
        await ensure_source_namespace_in_transaction(repository, ensure_input())


@pytest.mark.anyio
async def test_resolves_active_initiator_or_falls_back_to_current_owner() -> None:
    repository = FakeSourceImportRepository()
    owner = account("owner")
    trigger = account("trigger", login_name="alice")
    repository.owners[7] = [owner]
    repository.identities[("keycloak", "alice")] = [trigger]

    assert await resolve_attribution_user(repository, 7, SourceIdentity("keycloak", "alice")) == trigger
    assert await resolve_attribution_user(repository, 7, SourceIdentity("keycloak", "missing")) == owner
    assert await resolve_attribution_user(repository, 7, None) == owner


@pytest.mark.anyio
async def test_rejects_disabled_or_ambiguous_initiator_instead_of_falling_back() -> None:
    repository = FakeSourceImportRepository()
    repository.owners[7] = [account("owner")]
    repository.identities[("keycloak", "disabled")] = [account("disabled", status="DISABLED")]
    repository.identities[("keycloak", "ambiguous")] = [account("one"), account("two")]

    with pytest.raises(SourceImportConflict, match="not active"):
        await resolve_attribution_user(repository, 7, SourceIdentity("keycloak", "disabled"))
    with pytest.raises(SourceImportConflict, match="ambiguous"):
        await resolve_attribution_user(repository, 7, SourceIdentity("keycloak", "ambiguous"))


@pytest.mark.anyio
async def test_requires_exactly_one_active_current_namespace_owner() -> None:
    repository = FakeSourceImportRepository()

    with pytest.raises(SourceImportConflict, match="exactly one active OWNER"):
        await resolve_attribution_user(repository, 7, None)

    repository.owners[7] = [account("one"), account("two")]
    with pytest.raises(SourceImportConflict, match="exactly one active OWNER"):
        await resolve_attribution_user(repository, 7, None)

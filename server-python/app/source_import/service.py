from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import Any, Literal, Protocol

from app.source_import.contracts import SourceIdentity, SourceRepository


class SourceImportError(ValueError):
    def __init__(self, message: str, *, status_code: int, code: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class SourceImportConflict(SourceImportError):
    def __init__(self, message: str, *, code: str = "error.sourceImport.conflict") -> None:
        super().__init__(message, status_code=409, code=code)


class SourceImportNotFound(SourceImportError):
    def __init__(self, message: str, *, code: str = "error.sourceImport.identity.notFound") -> None:
        super().__init__(message, status_code=404, code=code)


@dataclass(frozen=True)
class IdentityAccount:
    user_id: str
    display_name: str
    status: str
    provider_code: str | None
    login_name: str | None


@dataclass(frozen=True)
class NamespaceRecord:
    id: int
    slug: str
    display_name: str
    type: str
    status: str


@dataclass(frozen=True)
class NamespaceSourceBinding:
    id: int
    namespace_id: int
    repository_url: str


@dataclass(frozen=True)
class EnsureSourceNamespaceInput:
    repository: SourceRepository
    requested_display_name: str
    fallback_owner: SourceIdentity
    actor_user_id: str
    request_id: str | None = None


@dataclass(frozen=True)
class EnsureSourceNamespaceResult:
    outcome: Literal["CREATED", "EXISTING"]
    namespace: NamespaceRecord
    binding: NamespaceSourceBinding
    owner: IdentityAccount


class SourceImportRepositoryProtocol(Protocol):
    async def read_identity_accounts(self, provider_code: str, login_name: str) -> list[IdentityAccount]: ...

    async def read_namespace(self, slug: str) -> NamespaceRecord | None: ...

    async def read_namespace_source_by_repository(self, repository_url: str) -> NamespaceSourceBinding | None: ...

    async def read_namespace_source_by_namespace(self, namespace_id: int) -> NamespaceSourceBinding | None: ...

    async def read_namespace_owners(self, namespace_id: int) -> list[IdentityAccount]: ...

    async def create_namespace_source(
        self,
        *,
        slug: str,
        display_name: str,
        repository_url: str,
        owner: IdentityAccount,
        actor_user_id: str,
        request_id: str | None,
    ) -> tuple[NamespaceRecord, NamespaceSourceBinding]: ...


async def _resolve_unique_active_identity(
    repository: SourceImportRepositoryProtocol,
    identity: SourceIdentity,
    *,
    missing_is_allowed: bool,
    label: str,
) -> IdentityAccount | None:
    accounts = await repository.read_identity_accounts(identity.provider_code, identity.login_name)
    if not accounts:
        if missing_is_allowed:
            return None
        raise SourceImportNotFound(f"{label} identity was not found")
    if len(accounts) != 1:
        raise SourceImportConflict(f"{label} identity is ambiguous", code="error.sourceImport.identity.ambiguous")
    account = accounts[0]
    if account.status != "ACTIVE":
        raise SourceImportConflict(f"{label} identity is not active", code="error.sourceImport.identity.inactive")
    return account


async def read_current_namespace_owner(
    repository: SourceImportRepositoryProtocol,
    namespace_id: int,
) -> IdentityAccount:
    owners = await repository.read_namespace_owners(namespace_id)
    if len(owners) != 1 or owners[0].status != "ACTIVE":
        raise SourceImportConflict(
            "Source namespace must have exactly one active OWNER",
            code="error.sourceImport.namespace.owner.invalid",
        )
    return owners[0]


async def resolve_attribution_user(
    repository: SourceImportRepositoryProtocol,
    namespace_id: int,
    initiator: SourceIdentity | None,
) -> IdentityAccount:
    if initiator is not None:
        resolved = await _resolve_unique_active_identity(
            repository,
            initiator,
            missing_is_allowed=True,
            label="pipeline initiator",
        )
        if resolved is not None:
            return resolved
    return await read_current_namespace_owner(repository, namespace_id)


def _require_writable_source_namespace(namespace: NamespaceRecord) -> None:
    if namespace.type != "TEAM" or namespace.status != "ACTIVE":
        raise SourceImportConflict(
            "Source namespace is not writable",
            code="error.sourceImport.namespace.notWritable",
        )


async def ensure_source_namespace_in_transaction(
    repository: SourceImportRepositoryProtocol,
    request: EnsureSourceNamespaceInput,
) -> EnsureSourceNamespaceResult:
    source = request.repository
    if request.requested_display_name != source.namespace_display_name:
        raise SourceImportConflict(
            "Namespace display name does not match repository naming rule",
            code="error.sourceImport.namespace.displayName.invalid",
        )

    namespace = await repository.read_namespace(source.namespace_slug)
    repository_binding = await repository.read_namespace_source_by_repository(source.canonical_url)
    if repository_binding is not None and (
        namespace is None or repository_binding.namespace_id != namespace.id
    ):
        raise SourceImportConflict(
            "Source repository is already bound to another namespace",
            code="error.sourceImport.repository.bound",
        )

    if namespace is not None:
        namespace_binding = await repository.read_namespace_source_by_namespace(namespace.id)
        if namespace_binding is None or namespace_binding.repository_url != source.canonical_url:
            raise SourceImportConflict(
                "Derived namespace slug already exists without the matching source binding",
                code="error.sourceImport.namespace.slug.conflict",
            )
        _require_writable_source_namespace(namespace)
        owner = await read_current_namespace_owner(repository, namespace.id)
        return EnsureSourceNamespaceResult("EXISTING", namespace, namespace_binding, owner)

    fallback_owner = await _resolve_unique_active_identity(
        repository,
        request.fallback_owner,
        missing_is_allowed=False,
        label="fallback owner",
    )
    if fallback_owner is None:
        raise AssertionError("required fallback owner cannot resolve to None")
    created_namespace, created_binding = await repository.create_namespace_source(
        slug=source.namespace_slug,
        display_name=source.namespace_display_name,
        repository_url=source.canonical_url,
        owner=fallback_owner,
        actor_user_id=request.actor_user_id,
        request_id=request.request_id,
    )
    return EnsureSourceNamespaceResult("CREATED", created_namespace, created_binding, fallback_owner)


async def ensure_source_namespace(
    engine: Any,
    request: EnsureSourceNamespaceInput,
    *,
    repository_factory: Callable[[Any], SourceImportRepositoryProtocol] | None = None,
) -> EnsureSourceNamespaceResult:
    from app.source_import.repository import SourceImportRepository

    factory = repository_factory or SourceImportRepository
    async with engine.begin() as connection:
        return await ensure_source_namespace_in_transaction(factory(connection), request)

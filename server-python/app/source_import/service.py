from __future__ import annotations

from collections.abc import Awaitable, Callable
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol, cast

from sqlalchemy.exc import IntegrityError

from app.publish.dry_run import auto_version, slugify
from app.publish.orchestration import (
    PublishWriteInput,
    PublishWriteResult,
    execute_publish_write,
)
from app.publish.package import PackageEntry, validate_package
from app.source_import.contracts import (
    SourceIdentity,
    SourceImportPlanOutcome,
    SourcePackage,
    SourceRepository,
    SourceRevision,
    SourceServiceActor,
)
from app.source_import.source import content_fingerprint, normalize_source_path


class SourceImportError(ValueError):
    def __init__(self, message: str, *, status_code: int, code: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class SourceImportConflict(SourceImportError):
    def __init__(
        self, message: str, *, code: str = "error.sourceImport.conflict"
    ) -> None:
        super().__init__(message, status_code=409, code=code)


class SourceImportNotFound(SourceImportError):
    def __init__(
        self, message: str, *, code: str = "error.sourceImport.identity.notFound"
    ) -> None:
        super().__init__(message, status_code=404, code=code)


class SourceImportValidationError(SourceImportError):
    def __init__(
        self, message: str, *, code: str = "error.sourceImport.validation"
    ) -> None:
        super().__init__(message, status_code=400, code=code)


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
class SourceSkillRecord:
    source_id: int | None
    namespace_source_id: int | None
    source_path: str | None
    skill_id: int
    slug: str
    owner_id: str
    status: str
    owner_display_name: str | None = None
    owner_status: str = "ACTIVE"


@dataclass(frozen=True)
class SourceSkillVersionRecord:
    version_id: int
    skill_id: int
    version: str
    status: str
    content_fingerprint: str | None


@dataclass(frozen=True)
class ValidateSourceSkillInput:
    namespace_slug: str
    repository: SourceRepository
    revision: SourceRevision
    source_path: str
    entries: list[PackageEntry]
    version_override: str | None
    initiator: SourceIdentity | None
    service_actor: SourceServiceActor
    allowed_extensions: AbstractSet[str] | None = None
    request_id: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    now: datetime | None = None


@dataclass(frozen=True)
class SourceSkillValidationPlan:
    outcome: SourceImportPlanOutcome
    namespace: NamespaceRecord
    namespace_binding: NamespaceSourceBinding
    source_skill: SourceSkillRecord | None
    package: SourcePackage
    skill_slug: str
    stable_owner: IdentityAccount
    review_submitter: IdentityAccount
    add_submitter_as_member: bool
    visibility: Literal["PUBLIC"] = "PUBLIC"
    auto_publish: Literal[False] = False


@dataclass(frozen=True)
class SourceSkillSubmissionRuntime:
    storage_base_path: str
    storage: Any | None = None
    scanner_enabled: bool = False
    scan_mode: str = "upload"
    notification_fanout: Any | None = None


@dataclass(frozen=True)
class SourceSkillSubmissionResult:
    outcome: Literal["IMPORTED", "SKIPPED_UNCHANGED", "SKIPPED_ALREADY_IMPORTED"]
    plan: SourceSkillValidationPlan
    skill_id: int | None
    version_id: int | None
    version_status: str | None
    review_task_id: int | None


@dataclass(frozen=True)
class EnsureSourceNamespaceInput:
    repository: SourceRepository
    requested_display_name: str
    fallback_owner: SourceIdentity
    service_actor: SourceServiceActor
    request_id: str | None = None


@dataclass(frozen=True)
class EnsureSourceNamespaceResult:
    outcome: Literal["CREATED", "EXISTING"]
    namespace: NamespaceRecord
    binding: NamespaceSourceBinding
    owner: IdentityAccount


class SourceImportRepositoryProtocol(Protocol):
    async def read_identity_accounts(
        self, provider_code: str, login_name: str
    ) -> list[IdentityAccount]: ...

    async def read_namespace(self, slug: str) -> NamespaceRecord | None: ...

    async def try_lock_source_namespace_creation(self, slug: str) -> bool: ...

    async def read_namespace_source_by_repository(
        self, repository_url: str
    ) -> NamespaceSourceBinding | None: ...

    async def read_namespace_source_by_namespace(
        self, namespace_id: int
    ) -> NamespaceSourceBinding | None: ...

    async def read_namespace_owners(
        self, namespace_id: int
    ) -> list[IdentityAccount]: ...

    async def read_service_principal_platform_admin(
        self, service_principal_id: str
    ) -> IdentityAccount | None: ...

    async def create_namespace_source(
        self,
        *,
        slug: str,
        display_name: str,
        repository_url: str,
        owner: IdentityAccount,
        platform_admin: IdentityAccount,
        service_actor: SourceServiceActor,
        request_id: str | None,
    ) -> tuple[NamespaceRecord, NamespaceSourceBinding]: ...

    async def read_source_skill(
        self, namespace_source_id: int, source_path: str
    ) -> SourceSkillRecord | None: ...

    async def read_skill_by_slug(
        self, namespace_id: int, slug: str
    ) -> SourceSkillRecord | None: ...

    async def read_source_skill_version(
        self, skill_id: int, version: str
    ) -> SourceSkillVersionRecord | None: ...

    async def read_source_skill_version_by_fingerprint(
        self,
        source_skill_id: int,
        fingerprint: str,
    ) -> SourceSkillVersionRecord | None: ...

    async def read_namespace_membership(
        self, namespace_id: int, user_id: str
    ) -> str | None: ...


async def _resolve_unique_active_identity(
    repository: SourceImportRepositoryProtocol,
    identity: SourceIdentity,
    *,
    missing_is_allowed: bool,
    label: str,
) -> IdentityAccount | None:
    accounts = await repository.read_identity_accounts(
        identity.provider_code, identity.login_name
    )
    if not accounts:
        if missing_is_allowed:
            return None
        raise SourceImportNotFound(f"{label} identity was not found")
    if len(accounts) != 1:
        raise SourceImportConflict(
            f"{label} identity is ambiguous",
            code="error.sourceImport.identity.ambiguous",
        )
    account = accounts[0]
    if account.status != "ACTIVE":
        raise SourceImportConflict(
            f"{label} identity is not active",
            code="error.sourceImport.identity.inactive",
        )
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

    if not await repository.try_lock_source_namespace_creation(source.namespace_slug):
        raise SourceImportConflict(
            "Source namespace creation is already in progress",
            code="error.sourceImport.namespace.creationInProgress",
        )
    namespace = await repository.read_namespace(source.namespace_slug)
    repository_binding = await repository.read_namespace_source_by_repository(
        source.canonical_url
    )
    if repository_binding is not None and (
        namespace is None or repository_binding.namespace_id != namespace.id
    ):
        raise SourceImportConflict(
            "Source repository is already bound to another namespace",
            code="error.sourceImport.repository.bound",
        )

    if namespace is not None:
        namespace_binding = await repository.read_namespace_source_by_namespace(
            namespace.id
        )
        if (
            namespace_binding is None
            or namespace_binding.repository_url != source.canonical_url
        ):
            raise SourceImportConflict(
                "Derived namespace slug already exists without the matching source binding",
                code="error.sourceImport.namespace.slug.conflict",
            )
        _require_writable_source_namespace(namespace)
        owner = await read_current_namespace_owner(repository, namespace.id)
        return EnsureSourceNamespaceResult(
            "EXISTING", namespace, namespace_binding, owner
        )

    fallback_owner = await _resolve_unique_active_identity(
        repository,
        request.fallback_owner,
        missing_is_allowed=False,
        label="fallback owner",
    )
    if fallback_owner is None:
        raise AssertionError("required fallback owner cannot resolve to None")
    platform_admin = await repository.read_service_principal_platform_admin(
        request.service_actor.service_principal_id
    )
    if platform_admin is None or platform_admin.status != "ACTIVE":
        raise SourceImportConflict(
            "Source importer service principal must have an active platform admin creator",
            code="error.sourceImport.platformAdmin.invalid",
        )
    if platform_admin.user_id == fallback_owner.user_id:
        raise SourceImportConflict(
            "Fallback owner and platform admin must be different users",
            code="error.sourceImport.platformAdmin.sameAsOwner",
        )
    created_namespace, created_binding = await repository.create_namespace_source(
        slug=source.namespace_slug,
        display_name=source.namespace_display_name,
        repository_url=source.canonical_url,
        owner=fallback_owner,
        platform_admin=platform_admin,
        service_actor=request.service_actor,
        request_id=request.request_id,
    )
    return EnsureSourceNamespaceResult(
        "CREATED", created_namespace, created_binding, fallback_owner
    )


def _resolve_effective_version(
    source_version: str | None,
    version_override: str | None,
    now: datetime | None,
) -> str:
    explicit_version = (source_version or "").strip()
    override = (version_override or "").strip()
    if explicit_version:
        if override:
            raise SourceImportValidationError(
                "A version override cannot replace an explicit SKILL.md version"
            )
        return explicit_version
    if not override:
        return auto_version(now)
    if len(override) > 64:
        raise SourceImportValidationError("The version override exceeds 64 characters")
    return override


def _stable_owner_for_source(
    source_skill: SourceSkillRecord | None, attribution: IdentityAccount
) -> IdentityAccount:
    if source_skill is None:
        return attribution
    return IdentityAccount(
        user_id=source_skill.owner_id,
        display_name=source_skill.owner_display_name or source_skill.owner_id,
        status=source_skill.owner_status,
        provider_code=None,
        login_name=None,
    )


async def validate_source_skill_in_transaction(
    repository: SourceImportRepositoryProtocol,
    request: ValidateSourceSkillInput,
) -> SourceSkillValidationPlan:
    namespace = await repository.read_namespace(request.namespace_slug)
    if namespace is None:
        raise SourceImportNotFound(
            "Source namespace was not found",
            code="error.sourceImport.namespace.notFound",
        )
    _require_writable_source_namespace(namespace)
    namespace_binding = await repository.read_namespace_source_by_namespace(
        namespace.id
    )
    if (
        namespace_binding is None
        or namespace_binding.repository_url != request.repository.canonical_url
    ):
        raise SourceImportConflict(
            "Source namespace repository binding does not match the request",
            code="error.sourceImport.repository.mismatch",
        )

    normalized_source_path = normalize_source_path(request.source_path)
    package_validation = validate_package(
        request.entries, allowed_extensions=request.allowed_extensions
    )
    if not package_validation.valid or package_validation.metadata is None:
        messages = package_validation.errors or [
            "Package must contain valid SKILL.md metadata"
        ]
        raise SourceImportValidationError(", ".join(messages))
    if package_validation.warnings:
        raise SourceImportValidationError(", ".join(package_validation.warnings))
    metadata = package_validation.metadata
    effective_version = _resolve_effective_version(
        metadata.version, request.version_override, request.now
    )
    try:
        resolved_slug = slugify(metadata.name)
    except ValueError as exc:
        raise SourceImportValidationError(f"Invalid skill name: {exc}") from exc

    fingerprint = content_fingerprint(request.entries)
    source_skill = await repository.read_source_skill(
        namespace_binding.id, normalized_source_path
    )
    if source_skill is not None:
        if source_skill.slug != resolved_slug:
            raise SourceImportConflict(
                "Skill source identity drift: source path now resolves to another slug",
                code="error.sourceImport.skill.sourceIdentityDrift",
            )
        if source_skill.status != "ACTIVE":
            raise SourceImportConflict(
                "Source skill is not writable",
                code="error.sourceImport.skill.notWritable",
            )
    elif await repository.read_skill_by_slug(namespace.id, resolved_slug) is not None:
        raise SourceImportConflict(
            "Skill slug already exists but is not bound to this source path",
            code="error.sourceImport.skill.slug.conflict",
        )

    attribution = await resolve_attribution_user(
        repository, namespace.id, request.initiator
    )
    stable_owner = _stable_owner_for_source(source_skill, attribution)
    existing_version = (
        await repository.read_source_skill_version(
            source_skill.skill_id, effective_version
        )
        if source_skill is not None
        else None
    )
    if existing_version is not None:
        if existing_version.content_fingerprint == fingerprint:
            outcome: SourceImportPlanOutcome = "SKIPPED_ALREADY_IMPORTED"
        else:
            raise SourceImportConflict(
                "An immutable version already exists with different source content",
                code="error.sourceImport.version.immutableConflict",
            )
    elif (
        source_skill is not None
        and source_skill.source_id is not None
        and await repository.read_source_skill_version_by_fingerprint(
            source_skill.source_id,
            fingerprint,
        )
        is not None
    ):
        outcome = "SKIPPED_UNCHANGED"
    else:
        outcome = "IMPORT"

    membership = await repository.read_namespace_membership(
        namespace.id, attribution.user_id
    )
    return SourceSkillValidationPlan(
        outcome=outcome,
        namespace=namespace,
        namespace_binding=namespace_binding,
        source_skill=source_skill,
        package=SourcePackage(
            source_path=normalized_source_path,
            entries=request.entries,
            metadata=metadata,
            content_fingerprint=fingerprint,
            effective_version=effective_version,
        ),
        skill_slug=resolved_slug,
        stable_owner=stable_owner,
        review_submitter=attribution,
        add_submitter_as_member=membership is None,
    )


async def ensure_source_namespace(
    engine: Any,
    request: EnsureSourceNamespaceInput,
    *,
    repository_factory: Callable[[Any], SourceImportRepositoryProtocol] | None = None,
) -> EnsureSourceNamespaceResult:
    from app.source_import.repository import SourceImportRepository

    factory = repository_factory or SourceImportRepository
    async with engine.begin() as connection:
        return await ensure_source_namespace_in_transaction(
            factory(connection), request
        )


async def validate_source_skill(
    engine: Any, request: ValidateSourceSkillInput
) -> SourceSkillValidationPlan:
    from app.source_import.repository import SourceImportRepository

    async with engine.connect() as connection:
        return await validate_source_skill_in_transaction(
            SourceImportRepository(connection), request
        )


def build_source_publish_input(
    plan: SourceSkillValidationPlan,
    request: ValidateSourceSkillInput,
    runtime: SourceSkillSubmissionRuntime,
) -> PublishWriteInput:
    metadata = plan.package.metadata
    resolved_frontmatter = dict(metadata.frontmatter)
    resolved_frontmatter["version"] = plan.package.effective_version
    resolved_metadata = type(metadata)(
        name=metadata.name,
        description=metadata.description,
        version=plan.package.effective_version,
        frontmatter=resolved_frontmatter,
    )
    return PublishWriteInput(
        namespace_id=plan.namespace.id,
        namespace_slug=plan.namespace.slug,
        slug=plan.skill_slug,
        display_name=metadata.name,
        summary=metadata.description,
        publisher_id=plan.stable_owner.user_id,
        submitter_id=plan.review_submitter.user_id,
        actor_service_principal_id=request.service_actor.service_principal_id,
        visibility="PUBLIC",
        version=plan.package.effective_version,
        auto_publish=False,
        metadata=resolved_metadata,
        entries=plan.package.entries,
        storage_base_path=runtime.storage_base_path,
        storage=runtime.storage,
        scanner_enabled=runtime.scanner_enabled,
        scan_mode=runtime.scan_mode,
        request_id=request.request_id,
        client_ip=request.client_ip,
        user_agent=request.user_agent,
    )


Validator = Callable[
    [Any, ValidateSourceSkillInput], Awaitable[SourceSkillValidationPlan]
]
Publisher = Callable[..., Awaitable[PublishWriteResult]]


async def submit_source_skill(
    engine: Any,
    request: ValidateSourceSkillInput,
    runtime: SourceSkillSubmissionRuntime,
    *,
    validator: Validator = validate_source_skill,
    publisher: Publisher = execute_publish_write,
    repository_factory: Callable[[Any], Any] | None = None,
) -> SourceSkillSubmissionResult:
    from app.source_import.repository import SourceImportRepository

    plan = await validator(engine, request)
    if plan.outcome != "IMPORT":
        return SourceSkillSubmissionResult(
            outcome=cast(Any, plan.outcome),
            plan=plan,
            skill_id=plan.source_skill.skill_id
            if plan.source_skill is not None
            else None,
            version_id=None,
            version_status=None,
            review_task_id=None,
        )

    factory = repository_factory or SourceImportRepository

    async def persist_provenance(
        connection: Any, skill_id: int, version_id: int
    ) -> None:
        repository = factory(connection)
        await repository.persist_source_submission(
            namespace_id=plan.namespace.id,
            namespace_source_id=plan.namespace_binding.id,
            source_skill_id=plan.source_skill.source_id
            if plan.source_skill is not None
            else None,
            source_path=plan.package.source_path,
            skill_id=skill_id,
            version_id=version_id,
            revision=request.revision,
            content_fingerprint=plan.package.content_fingerprint,
            repository_url=request.repository.canonical_url,
            service_actor=request.service_actor,
            review_submitter_id=plan.review_submitter.user_id,
            stable_owner_id=plan.stable_owner.user_id,
            outcome="IMPORTED",
            add_submitter_as_member=plan.add_submitter_as_member,
            request_id=request.request_id,
            client_ip=request.client_ip,
            user_agent=request.user_agent,
            initiator_provider_code=(
                request.initiator.provider_code if request.initiator is not None else None
            ),
            initiator_login_name=(
                request.initiator.login_name if request.initiator is not None else None
            ),
            attribution_source=(
                "INITIATOR"
                if request.initiator is not None
                and plan.review_submitter.provider_code == request.initiator.provider_code
                and plan.review_submitter.login_name == request.initiator.login_name
                else "NAMESPACE_OWNER_FALLBACK"
            ),
        )

    try:
        result = await publisher(
            engine,
            build_source_publish_input(plan, request, runtime),
            notification_fanout=runtime.notification_fanout,
            after_prepare=persist_provenance,
        )
    except IntegrityError:
        concurrent_plan = await validator(engine, request)
        if concurrent_plan.outcome == "IMPORT":
            raise
        return SourceSkillSubmissionResult(
            outcome=cast(Any, concurrent_plan.outcome),
            plan=concurrent_plan,
            skill_id=(
                concurrent_plan.source_skill.skill_id
                if concurrent_plan.source_skill is not None
                else None
            ),
            version_id=None,
            version_status=None,
            review_task_id=None,
        )
    side_effects = getattr(result, "side_effects", None)
    return SourceSkillSubmissionResult(
        outcome="IMPORTED",
        plan=plan,
        skill_id=int(result.skill_id),
        version_id=int(result.version_id),
        version_status=str(result.version_status),
        review_task_id=(
            int(side_effects.review_task_id)
            if side_effects is not None and side_effects.review_task_id is not None
            else None
        ),
    )

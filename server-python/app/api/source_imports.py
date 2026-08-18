from __future__ import annotations

from inspect import isawaitable
from typing import Any, Literal

from fastapi import (
    APIRouter,
    File,
    Form,
    Header,
    HTTPException,
    Path,
    Request,
    UploadFile,
)
from pydantic import BaseModel, ConfigDict, ValidationError

from app.auth.service_tokens import ServiceTokenPrincipal, resolve_service_token_or_401
from app.core.config import get_settings
from app.core.redis import create_redis_client
from app.core.response import ok
from app.object_storage import object_storage_for_settings
from app.publish.package import extract_package
from app.publish.scanner_handoff import RedisScanTaskPublisher
from app.source_import.contracts import SourceIdentity, SourceServiceActor
from app.source_import.service import (
    EnsureSourceNamespaceInput,
    EnsureSourceNamespaceResult,
    SourceImportError,
    SourceSkillSubmissionResult,
    SourceSkillSubmissionRuntime,
    SourceSkillValidationPlan,
    ValidateSourceSkillInput,
    ensure_source_namespace,
    submit_source_skill,
    validate_source_skill,
)
from app.source_import.source import (
    SourceInputError,
    build_browse_url,
    canonicalize_github_repository,
    validate_source_revision,
)

router = APIRouter()


class EnsureSourceNamespaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repositoryUrl: str
    displayName: str
    fallbackOwnerProviderCode: str
    fallbackOwnerLoginName: str


class SourceSkillMetadataRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repositoryUrl: str
    repositoryRevisionSha: str
    sourceRefType: Literal["TAG", "BRANCH", "COMMIT"]
    sourceRef: str | None = None
    sourcePath: str
    versionOverride: str | None = None
    initiatorProviderCode: str | None = None
    initiatorLoginName: str | None = None
    pipelineId: str | None = None
    jobId: str | None = None
    ciRefName: str | None = None


class SourceIdentityResponse(BaseModel):
    displayName: str
    providerCode: str | None = None
    loginName: str | None = None


class SourceProvenanceResponse(BaseModel):
    repositoryUrl: str
    repositoryRevisionSha: str
    sourceRefType: Literal["TAG", "BRANCH", "COMMIT"]
    sourceRef: str | None = None
    sourcePath: str
    contentFingerprint: str
    browseUrl: str


class EnsureSourceNamespaceData(BaseModel):
    outcome: Literal["CREATED", "EXISTING"]
    namespaceSlug: str
    displayName: str
    status: str
    repositoryUrl: str
    owner: SourceIdentityResponse


class ValidateSourceSkillData(BaseModel):
    outcome: Literal["IMPORT", "SKIPPED_UNCHANGED", "SKIPPED_ALREADY_IMPORTED"]
    coordinate: str
    version: str
    stableOwner: SourceIdentityResponse
    reviewSubmitter: SourceIdentityResponse
    addSubmitterAsMember: bool
    sourceProvenance: SourceProvenanceResponse


class SubmitSourceSkillData(BaseModel):
    outcome: Literal["IMPORTED", "SKIPPED_UNCHANGED", "SKIPPED_ALREADY_IMPORTED"]
    coordinate: str
    version: str
    skillId: int | None = None
    versionId: int | None = None
    versionStatus: str | None = None
    reviewTaskId: int | None = None
    stableOwner: SourceIdentityResponse
    reviewSubmitter: SourceIdentityResponse
    importerActor: SourceIdentityResponse
    sourceProvenance: SourceProvenanceResponse


class EnsureSourceNamespaceEnvelope(BaseModel):
    code: int
    msg: str
    data: EnsureSourceNamespaceData
    timestamp: str
    requestId: str


class ValidateSourceSkillEnvelope(BaseModel):
    code: int
    msg: str
    data: ValidateSourceSkillData
    timestamp: str
    requestId: str


class SubmitSourceSkillEnvelope(BaseModel):
    code: int
    msg: str
    data: SubmitSourceSkillData
    timestamp: str
    requestId: str


async def _resolve(value: Any) -> Any:
    return await value if isawaitable(value) else value


async def _require_import_actor(
    request: Request,
    authorization: str | None,
) -> ServiceTokenPrincipal:
    return await resolve_service_token_or_401(
        request,
        authorization,
        required_scope="source:import",
    )


def _identity_response(account: Any) -> dict[str, object]:
    result: dict[str, object] = {"displayName": str(account.display_name)}
    if account.provider_code is not None:
        result["providerCode"] = str(account.provider_code)
    if account.login_name is not None:
        result["loginName"] = str(account.login_name)
    return result


def _actor_response(actor: ServiceTokenPrincipal) -> dict[str, object]:
    return {"displayName": actor.display_name}


def _service_actor(actor: ServiceTokenPrincipal) -> SourceServiceActor:
    return SourceServiceActor(
        service_principal_id=actor.service_principal_id,
        code=actor.code,
        display_name=actor.display_name,
    )


def _parse_metadata(raw: str) -> SourceSkillMetadataRequest:
    try:
        return SourceSkillMetadataRequest.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(
            status_code=400, detail="error.sourceImport.metadata.invalid"
        ) from exc


def _initiator(metadata: SourceSkillMetadataRequest) -> SourceIdentity | None:
    provider = (metadata.initiatorProviderCode or "").strip()
    login = (metadata.initiatorLoginName or "").strip()
    if not provider and not login:
        return None
    if not provider or not login:
        raise HTTPException(
            status_code=400, detail="error.sourceImport.initiator.invalid"
        )
    return SourceIdentity(provider, login)


async def _skill_input(
    request: Request,
    namespace_slug: str,
    file: UploadFile,
    metadata_raw: str,
    service_actor: SourceServiceActor,
) -> ValidateSourceSkillInput:
    metadata = _parse_metadata(metadata_raw)
    try:
        repository = canonicalize_github_repository(metadata.repositoryUrl)
        revision = validate_source_revision(
            metadata.repositoryRevisionSha,
            metadata.sourceRefType,
            metadata.sourceRef,
        )
        entries = extract_package(await file.read())
    except (SourceInputError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if repository.namespace_slug != namespace_slug:
        raise HTTPException(
            status_code=400, detail="error.sourceImport.namespace.mismatch"
        )
    settings = getattr(request.app.state, "settings", get_settings())
    return ValidateSourceSkillInput(
        namespace_slug=namespace_slug,
        repository=repository,
        revision=revision,
        source_path=metadata.sourcePath,
        entries=entries,
        version_override=metadata.versionOverride,
        initiator=_initiator(metadata),
        service_actor=service_actor,
        allowed_extensions=getattr(settings, "publish_allowed_file_extensions", None),
        request_id=getattr(request.state, "request_id", None),
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


def _provenance(
    plan: SourceSkillValidationPlan, request: ValidateSourceSkillInput
) -> dict[str, object]:
    result: dict[str, object] = {
        "repositoryUrl": request.repository.canonical_url,
        "repositoryRevisionSha": request.revision.commit_sha,
        "sourceRefType": request.revision.ref_type,
        "sourcePath": plan.package.source_path,
        "contentFingerprint": plan.package.content_fingerprint,
        "browseUrl": build_browse_url(
            request.repository, request.revision, plan.package.source_path
        ),
    }
    if request.revision.ref is not None:
        result["sourceRef"] = request.revision.ref
    return result


def _validation_data(
    plan: SourceSkillValidationPlan, request: ValidateSourceSkillInput
) -> dict[str, object]:
    return {
        "outcome": plan.outcome,
        "coordinate": f"@{plan.namespace.slug}/{plan.skill_slug}",
        "version": plan.package.effective_version,
        "stableOwner": _identity_response(plan.stable_owner),
        "reviewSubmitter": _identity_response(plan.review_submitter),
        "addSubmitterAsMember": plan.add_submitter_as_member,
        "sourceProvenance": _provenance(plan, request),
    }


def _handle_source_error(exc: SourceImportError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.code)


def _db_engine(request: Request) -> Any:
    return getattr(request.app.state, "db_engine", None)


@router.put(
    "/api/cli/v1/source-imports/namespaces/{namespaceSlug}",
    response_model=EnsureSourceNamespaceEnvelope,
)
async def ensure_source_namespace_route(
    request: Request,
    body: EnsureSourceNamespaceRequest,
    namespace_slug: str = Path(alias="namespaceSlug"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    actor = await _require_import_actor(request, authorization)
    try:
        repository = canonicalize_github_repository(body.repositoryUrl)
    except SourceInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if (
        repository.namespace_slug != namespace_slug
        or repository.namespace_display_name != body.displayName
    ):
        raise HTTPException(
            status_code=400, detail="error.sourceImport.namespace.mismatch"
        )
    ensure_input = EnsureSourceNamespaceInput(
        repository=repository,
        requested_display_name=body.displayName,
        fallback_owner=SourceIdentity(
            body.fallbackOwnerProviderCode, body.fallbackOwnerLoginName
        ),
        service_actor=_service_actor(actor),
        request_id=getattr(request.state, "request_id", None),
    )
    ensurer = getattr(
        request.app.state, "source_import_namespace_ensurer", ensure_source_namespace
    )
    try:
        result: EnsureSourceNamespaceResult = await _resolve(
            ensurer(_db_engine(request), ensure_input)
        )
    except SourceImportError as exc:
        raise _handle_source_error(exc) from exc
    return ok(
        "response.success.sourceImport.namespaceEnsured",
        {
            "outcome": result.outcome,
            "namespaceSlug": result.namespace.slug,
            "displayName": result.namespace.display_name,
            "status": result.namespace.status,
            "repositoryUrl": result.binding.repository_url,
            "owner": _identity_response(result.owner),
        },
        request,
    )


@router.post(
    "/api/cli/v1/source-imports/{namespaceSlug}/skills/validate",
    response_model=ValidateSourceSkillEnvelope,
)
async def validate_source_skill_route(
    request: Request,
    file: UploadFile = File(...),
    metadata: str = Form(...),
    namespace_slug: str = Path(alias="namespaceSlug"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    actor = await _require_import_actor(request, authorization)
    source_input = await _skill_input(
        request,
        namespace_slug,
        file,
        metadata,
        _service_actor(actor),
    )
    validator = getattr(
        request.app.state, "source_import_validator", validate_source_skill
    )
    try:
        plan: SourceSkillValidationPlan = await _resolve(
            validator(_db_engine(request), source_input)
        )
    except SourceImportError as exc:
        raise _handle_source_error(exc) from exc
    except SourceInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ok(
        "response.success.sourceImport.validated",
        _validation_data(plan, source_input),
        request,
    )


@router.post(
    "/api/cli/v1/source-imports/{namespaceSlug}/skills",
    response_model=SubmitSourceSkillEnvelope,
)
async def submit_source_skill_route(
    request: Request,
    file: UploadFile = File(...),
    metadata: str = Form(...),
    namespace_slug: str = Path(alias="namespaceSlug"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    actor = await _require_import_actor(request, authorization)
    source_input = await _skill_input(
        request,
        namespace_slug,
        file,
        metadata,
        _service_actor(actor),
    )
    settings = getattr(request.app.state, "settings", get_settings())
    submitter = getattr(
        request.app.state, "source_import_submitter", submit_source_skill
    )
    storage = (
        None
        if submitter is not submit_source_skill
        else object_storage_for_settings(settings)
    )
    scan_task_publisher = None
    if submitter is submit_source_skill and settings.security_scanner_enabled:
        redis_client = getattr(request.app.state, "redis_client", None)
        if redis_client is None:
            redis_client = create_redis_client(settings)
            request.app.state.redis_client = redis_client
        scan_task_publisher = RedisScanTaskPublisher(
            redis_client, settings.scan_stream_key
        )
    runtime = SourceSkillSubmissionRuntime(
        storage_base_path=settings.storage_base_path,
        storage=storage,
        scanner_enabled=settings.security_scanner_enabled,
        scan_mode=settings.security_scanner_mode,
        scan_task_publisher=scan_task_publisher,
        notification_fanout=getattr(request.app.state, "notification_fanout", None),
    )
    try:
        result: SourceSkillSubmissionResult = await _resolve(
            submitter(_db_engine(request), source_input, runtime)
        )
    except SourceImportError as exc:
        raise _handle_source_error(exc) from exc
    except SourceInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    data = _validation_data(result.plan, source_input)
    data.update(
        {
            "outcome": result.outcome,
            "skillId": result.skill_id,
            "versionId": result.version_id,
            "versionStatus": result.version_status,
            "reviewTaskId": result.review_task_id,
            "importerActor": _actor_response(actor),
        }
    )
    data.pop("addSubmitterAsMember", None)
    return ok("response.success.sourceImport.submitted", data, request)

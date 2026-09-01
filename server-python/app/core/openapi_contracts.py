from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field
from pydantic.json_schema import models_json_schema


class OpenApiContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class AuthMeResponse(OpenApiContractModel):
    user_id: str | None = Field(default=None, alias="userId")
    display_name: str | None = Field(default=None, alias="displayName")
    email: str | None = None
    avatar_url: str | None = Field(default=None, alias="avatarUrl")
    oauth_provider: str | None = Field(default=None, alias="oauthProvider")
    can_change_password: bool | None = Field(default=None, alias="canChangePassword")
    platform_roles: list[str] | None = Field(default=None, alias="platformRoles")


class AuthProviderResponse(OpenApiContractModel):
    id: str | None = None
    name: str | None = None
    authorization_url: str | None = Field(default=None, alias="authorizationUrl")


class TokenSummaryResponse(OpenApiContractModel):
    id: int | None = None
    name: str | None = None
    token_prefix: str | None = Field(default=None, alias="tokenPrefix")
    created_at: str | None = Field(default=None, alias="createdAt")
    expires_at: str | None = Field(default=None, alias="expiresAt")
    last_used_at: str | None = Field(default=None, alias="lastUsedAt")


class TokenCreateRequest(OpenApiContractModel):
    name: str
    scopes: list[str] | None = None
    expires_at: str | None = Field(default=None, alias="expiresAt")


class TokenCreateResponse(OpenApiContractModel):
    token: str | None = None
    id: int | None = None
    name: str | None = None
    token_prefix: str | None = Field(default=None, alias="tokenPrefix")
    created_at: str | None = Field(default=None, alias="createdAt")
    expires_at: str | None = Field(default=None, alias="expiresAt")


class NamespaceRequest(OpenApiContractModel):
    slug: str
    display_name: str = Field(alias="displayName")
    description: str | None = None


class SkillLabelDto(OpenApiContractModel):
    slug: str | None = None
    type: str | None = None
    display_name: str | None = Field(default=None, alias="displayName")


class LabelTranslationResponse(OpenApiContractModel):
    locale: str | None = None
    display_name: str | None = Field(default=None, alias="displayName")


class LabelDefinitionResponse(OpenApiContractModel):
    slug: str | None = None
    type: str | None = None
    visible_in_filter: bool | None = Field(default=None, alias="visibleInFilter")
    sort_order: int | None = Field(default=None, alias="sortOrder")
    translations: list[LabelTranslationResponse] | None = None
    created_at: str | None = Field(default=None, alias="createdAt")


class SkillSummaryResponse(OpenApiContractModel):
    id: int | None = None
    slug: str | None = None
    display_name: str | None = Field(default=None, alias="displayName")
    summary: str | None = None
    visibility: str | None = None
    status: str | None = None
    download_count: int | None = Field(default=None, alias="downloadCount")
    star_count: int | None = Field(default=None, alias="starCount")
    rating_avg: float | None = Field(default=None, alias="ratingAvg")
    rating_count: int | None = Field(default=None, alias="ratingCount")
    namespace: str | None = None
    owner_id: str | None = Field(default=None, alias="ownerId")
    owner_display_name: str | None = Field(default=None, alias="ownerDisplayName")
    updated_at: str | None = Field(default=None, alias="updatedAt")
    can_submit_promotion: bool | None = Field(default=None, alias="canSubmitPromotion")
    headline_version: dict[str, Any] | None = Field(default=None, alias="headlineVersion")
    published_version: dict[str, Any] | None = Field(default=None, alias="publishedVersion")
    owner_preview_version: dict[str, Any] | None = Field(
        default=None,
        alias="ownerPreviewVersion",
    )
    resolution_mode: str | None = Field(default=None, alias="resolutionMode")
    compliance_snapshot: dict[str, Any] | None = Field(
        default=None,
        alias="complianceSnapshot",
    )
    labels: list[SkillLabelDto] | None = None


class SkillVersionResponse(OpenApiContractModel):
    id: int | None = None
    version: str | None = None
    status: str | None = None
    changelog: str | None = None
    file_count: int | None = Field(default=None, alias="fileCount")
    total_size: int | None = Field(default=None, alias="totalSize")
    published_at: str | None = Field(default=None, alias="publishedAt")
    download_available: bool | None = Field(default=None, alias="downloadAvailable")
    compliance_snapshot: dict[str, Any] | None = Field(
        default=None,
        alias="complianceSnapshot",
    )


class SkillVersionDetailResponse(OpenApiContractModel):
    id: int | None = None
    version: str | None = None
    status: str | None = None
    changelog: str | None = None
    file_count: int | None = Field(default=None, alias="fileCount")
    total_size: int | None = Field(default=None, alias="totalSize")
    published_at: str | None = Field(default=None, alias="publishedAt")
    parsed_metadata_json: str | None = Field(default=None, alias="parsedMetadataJson")
    manifest_json: str | None = Field(default=None, alias="manifestJson")
    source_provenance: dict[str, Any] | None = Field(
        default=None,
        alias="sourceProvenance",
    )
    version_attribution: dict[str, Any] | None = Field(
        default=None,
        alias="versionAttribution",
    )
    compliance_snapshot: dict[str, Any] | None = Field(
        default=None,
        alias="complianceSnapshot",
    )


FRONTEND_CONTRACT_MODELS = (
    AuthMeResponse,
    AuthProviderResponse,
    LabelDefinitionResponse,
    LabelTranslationResponse,
    NamespaceRequest,
    SkillLabelDto,
    SkillSummaryResponse,
    SkillVersionDetailResponse,
    SkillVersionResponse,
    TokenCreateRequest,
    TokenCreateResponse,
    TokenSummaryResponse,
)


def frontend_contract_components() -> dict[str, Any]:
    _, schema = models_json_schema(
        [(model, "validation") for model in FRONTEND_CONTRACT_MODELS],
        by_alias=True,
        ref_template="#/components/schemas/{model}",
    )
    return _remove_schema_defaults(dict(schema.get("$defs", {})))


def _remove_schema_defaults(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _remove_schema_defaults(item)
            for key, item in value.items()
            if key != "default"
        }
    if isinstance(value, list):
        return [_remove_schema_defaults(item) for item in value]
    return value


def install_frontend_openapi_contracts(app: FastAPI) -> None:
    default_openapi: Callable[[], dict[str, Any]] = app.openapi

    def openapi() -> dict[str, Any]:
        schema = default_openapi()
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        components.update(frontend_contract_components())
        app.openapi_schema = schema
        return schema

    app.openapi = openapi


__all__ = [
    "FRONTEND_CONTRACT_MODELS",
    "frontend_contract_components",
    "install_frontend_openapi_contracts",
]

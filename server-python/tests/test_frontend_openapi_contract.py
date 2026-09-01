from __future__ import annotations

from app.main import create_app

FRONTEND_COMPONENTS = {
    "AuthMeResponse",
    "AuthProviderResponse",
    "LabelDefinitionResponse",
    "LabelTranslationResponse",
    "NamespaceRequest",
    "SkillLabelDto",
    "SkillSummaryResponse",
    "SkillVersionDetailResponse",
    "SkillVersionResponse",
    "TokenCreateRequest",
    "TokenCreateResponse",
    "TokenSummaryResponse",
}


def test_openapi_exposes_components_consumed_by_frontend_types() -> None:
    schema = create_app().openapi()
    components = schema["components"]["schemas"]

    assert FRONTEND_COMPONENTS <= components.keys()
    assert "canChangePassword" in components["AuthMeResponse"]["properties"]
    assert "labels" in components["SkillSummaryResponse"]["properties"]
    assert "sourceProvenance" in components["SkillVersionDetailResponse"]["properties"]
    assert "versionAttribution" in components["SkillVersionDetailResponse"]["properties"]
    assert set(components["TokenCreateRequest"]["required"]) == {"name"}
    assert set(components["NamespaceRequest"]["required"]) == {"slug", "displayName"}
    assert "ownerId" not in components["SkillSummaryResponse"].get("required", [])
    assert "labels" not in components["SkillSummaryResponse"].get("required", [])
    assert "complianceSnapshot" not in components["SkillVersionResponse"].get(
        "required", []
    )


def test_token_openapi_paths_preserve_frontend_parameter_name() -> None:
    paths = create_app().openapi()["paths"]

    assert "/api/v1/tokens/{id}" in paths
    assert "/api/v1/tokens/{id}/expiration" in paths
    assert "/api/v1/tokens/{token_id}" not in paths
    assert "/api/v1/tokens/{token_id}/expiration" not in paths

from scripts.export_service_principal_openapi import build_openapi_schema


def test_service_principal_openapi_exposes_management_contract() -> None:
    schema = build_openapi_schema()
    paths = schema["paths"]
    assert set(paths) == {
        "/api/v1/admin/service-principals",
        "/api/v1/admin/service-principals/{service_principal_id}",
        "/api/v1/admin/service-principals/{service_principal_id}/tokens",
        "/api/v1/admin/service-principals/{service_principal_id}/tokens/{token_id}/rotate",
        "/api/v1/admin/service-principals/{service_principal_id}/tokens/{token_id}",
    }
    schemas = schema["components"]["schemas"]
    assert schemas["CreateServiceTokenRequest"]["required"] == [
        "name",
        "scopes",
        "expiresAt",
    ]
    assert schemas["RotateServiceTokenRequest"]["required"] == ["expiresAt"]
    for request_name in ("CreateServiceTokenRequest", "RotateServiceTokenRequest"):
        expires_at = schemas[request_name]["properties"]["expiresAt"]
        assert {item.get("type") for item in expires_at["anyOf"]} == {"string", "null"}

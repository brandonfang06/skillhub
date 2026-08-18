from __future__ import annotations

from app.main import create_app
from scripts.export_source_import_openapi import build_openapi_schema


def test_source_import_openapi_exposes_typed_contract() -> None:
    schema = create_app().openapi()
    paths = schema["paths"]

    assert "/api/cli/v1/source-imports/namespaces/{namespaceSlug}" in paths
    assert "/api/cli/v1/source-imports/{namespaceSlug}/skills/validate" in paths
    assert "/api/cli/v1/source-imports/{namespaceSlug}/skills" in paths
    assert "SourceProvenanceResponse" in schema["components"]["schemas"]


def test_focused_source_import_openapi_contains_only_source_import_routes() -> None:
    schema = build_openapi_schema()

    assert set(schema["paths"]) == {
        "/api/cli/v1/source-imports/namespaces/{namespaceSlug}",
        "/api/cli/v1/source-imports/{namespaceSlug}/skills/validate",
        "/api/cli/v1/source-imports/{namespaceSlug}/skills",
    }

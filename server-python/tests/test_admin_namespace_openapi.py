from __future__ import annotations

import json
from pathlib import Path

from scripts.export_admin_namespace_openapi import (
    build_openapi_schema,
    render_openapi_schema,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
GENERATED_OPENAPI = (
    REPOSITORY_ROOT
    / "web"
    / "src"
    / "api"
    / "generated"
    / "admin-namespaces-openapi.json"
)


def test_admin_namespace_openapi_contains_exact_router_inventory() -> None:
    schema = build_openapi_schema()
    operations = {
        (method.upper(), path)
        for path, methods in schema["paths"].items()
        for method in methods
    }

    assert operations == {
        ("GET", "/api/v1/admin/namespaces"),
        ("GET", "/api/v1/admin/namespaces/{slug}"),
        ("GET", "/api/v1/admin/namespaces/{slug}/members"),
        ("GET", "/api/v1/admin/namespaces/{slug}/member-candidates"),
        ("POST", "/api/v1/admin/namespaces/{slug}/members"),
        ("POST", "/api/v1/admin/namespaces/{slug}/members/batch"),
        ("PUT", "/api/v1/admin/namespaces/{slug}/members/{userId}/role"),
        ("DELETE", "/api/v1/admin/namespaces/{slug}/members/{userId}"),
        ("POST", "/api/v1/admin/namespaces/{slug}/transfer-ownership"),
        ("POST", "/api/v1/admin/namespaces/{slug}/freeze"),
        ("POST", "/api/v1/admin/namespaces/{slug}/unfreeze"),
        ("POST", "/api/v1/admin/namespaces/{slug}/archive"),
        ("POST", "/api/v1/admin/namespaces/{slug}/restore"),
    }
    assert schema["info"]["title"] == "SkillHub Admin Namespace API"
    schemas = schema["components"]["schemas"]
    assert "AdminNamespaceSummary" in schemas
    assert schemas["AdminNamespaceMemberRequest"]["properties"]["role"]["enum"] == [
        "ADMIN",
        "MEMBER",
    ]
    assert schemas["AdminNamespaceUpdateMemberRoleRequest"]["properties"]["role"][
        "enum"
    ] == ["ADMIN", "MEMBER"]


def test_admin_namespace_openapi_rendering_is_deterministic_and_fresh() -> None:
    rendered = render_openapi_schema()

    assert rendered == render_openapi_schema()
    assert rendered.endswith("\n")
    assert GENERATED_OPENAPI.read_text(encoding="utf-8") == rendered


def test_admin_namespace_typescript_freshness_check_is_wired_into_ci() -> None:
    package = json.loads((REPOSITORY_ROOT / "web" / "package.json").read_text())
    assert package["scripts"]["check-api:admin-namespaces"] == (
        "openapi-typescript src/api/generated/admin-namespaces-openapi.json "
        "-o src/api/generated/admin-namespaces-schema.d.ts --check"
    )
    workflow = (REPOSITORY_ROOT / ".github/workflows/pr-tests.yml").read_text()
    assert "pnpm run check-api:admin-namespaces" in workflow

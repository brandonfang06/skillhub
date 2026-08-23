from __future__ import annotations

import json
from pathlib import Path

from scripts.export_compliance_openapi import build_openapi_schema, render_openapi_schema


GENERATED_OPENAPI = (
    Path(__file__).resolve().parents[2]
    / "web"
    / "src"
    / "api"
    / "generated"
    / "compliance-openapi.json"
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_compliance_openapi_is_focused_and_typed() -> None:
    schema = build_openapi_schema()

    assert schema["info"]["title"] == "SkillHub Compliance Projection API"
    assert set(schema["paths"]) == {"/contracts/compliance-projection"}
    schemas = schema["components"]["schemas"]
    assert {
        "ComplianceEvidenceResponse",
        "ComplianceMappingResponse",
        "ComplianceProjection",
        "ComplianceSnapshotResponse",
    } <= set(schemas)
    assert schemas["ComplianceProjection"]["properties"]["complianceSnapshot"] == {
        "anyOf": [
            {"$ref": "#/components/schemas/ComplianceSnapshotResponse"},
            {"type": "null"},
        ],
    }
    assert "AdminNamespace" not in render_openapi_schema()


def test_compliance_openapi_rendering_is_deterministic() -> None:
    first = render_openapi_schema()
    second = render_openapi_schema()

    assert first == second
    assert first.endswith("\n")


def test_checked_in_compliance_openapi_is_fresh() -> None:
    assert GENERATED_OPENAPI.read_text(encoding="utf-8") == render_openapi_schema()


def test_compliance_typescript_freshness_check_is_wired_into_ci() -> None:
    package = json.loads((REPOSITORY_ROOT / "web" / "package.json").read_text(encoding="utf-8"))
    assert package["scripts"]["check-api:compliance"] == (
        "openapi-typescript src/api/generated/compliance-openapi.json "
        "-o src/api/generated/compliance-schema.d.ts --check"
    )

    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "pr-tests.yml").read_text(
        encoding="utf-8"
    )
    assert "pnpm run check-api:compliance" in workflow

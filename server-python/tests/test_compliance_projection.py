from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.review.query import _review_skill_version_response
from app.skills.compliance_contract import (
    ComplianceProjection,
    ComplianceSnapshotResponse,
)
from app.skills.read_responses import (
    build_skill_summary_response,
    build_version_detail_response,
    build_versions_page_response,
)

SNAPSHOT = {
    "schemaVersion": "1.0",
    "items": [
        {
            "standard": "mitre-attack",
            "version": "15",
            "controlId": "T1059",
            "title": "Command and Scripting Interpreter",
            "evidence": [
                {
                    "type": "packaged-file",
                    "path": "docs/security.md",
                    "url": None,
                    "sha256": "sha256:def456",
                }
            ],
        }
    ],
    "digest": "sha256:abc123",
}


def _metadata(snapshot: object = SNAPSHOT) -> str:
    return json.dumps({"complianceSnapshot": snapshot})


def test_version_list_and_detail_project_immutable_compliance_snapshot() -> None:
    base_row = {
        "id": 20,
        "version": "1.2.0",
        "status": "PUBLISHED",
        "changelog": "latest",
        "file_count": 2,
        "total_size": 128,
        "published_at": datetime(2026, 6, 7, 10, 0, tzinfo=UTC),
        "download_ready": True,
        "manifest_json": None,
    }
    list_row = {
        **base_row,
        "compliance_snapshot_json": json.dumps(SNAPSHOT),
        "parsed_metadata_json": _metadata({"digest": "sha256:must-not-be-read"}),
    }
    detail_row = {**base_row, "parsed_metadata_json": _metadata()}

    page = build_versions_page_response([list_row], total=1, page=0, size=20)
    detail = build_version_detail_response(detail_row)

    assert page["items"][0]["complianceSnapshot"] == SNAPSHOT
    assert detail["complianceSnapshot"] == SNAPSHOT


def test_compliance_projection_is_backward_compatible_with_absent_and_malformed_metadata() -> (
    None
):
    base_row = {
        "id": 20,
        "version": "1.2.0",
        "status": "PUBLISHED",
        "changelog": None,
        "file_count": 0,
        "total_size": 0,
        "published_at": None,
        "download_ready": True,
        "manifest_json": None,
    }

    for malformed_value in (
        None,
        "",
        "not-json",
        "[]",
        json.dumps("not-an-object"),
    ):
        row = {**base_row, "compliance_snapshot_json": malformed_value}
        assert (
            build_versions_page_response([row], 1, 0, 20)["items"][0][
                "complianceSnapshot"
            ]
            is None
        )
        assert (
            build_version_detail_response(
                {**row, "parsed_metadata_json": malformed_value}
            )["complianceSnapshot"]
            is None
        )


def test_compliance_projection_handles_json_integer_digit_limit_as_malformed() -> None:
    huge_integer = "1" * 4301
    base_row = {
        "id": 20,
        "version": "1.2.0",
        "status": "PUBLISHED",
        "changelog": None,
        "file_count": 0,
        "total_size": 0,
        "published_at": None,
        "download_ready": True,
        "manifest_json": None,
    }

    page_row = {**base_row, "compliance_snapshot_json": huge_integer}
    detail_row = {
        **base_row,
        "parsed_metadata_json": '{"complianceSnapshot":' + huge_integer + "}",
    }

    assert (
        build_versions_page_response([page_row], 1, 0, 20)["items"][0][
            "complianceSnapshot"
        ]
        is None
    )
    assert build_version_detail_response(detail_row)["complianceSnapshot"] is None


def test_compliance_projection_skips_malformed_items_and_defaults_missing_arrays() -> (
    None
):
    row = {
        "id": 20,
        "version": "1.2.0",
        "status": "PUBLISHED",
        "changelog": None,
        "file_count": 0,
        "total_size": 0,
        "published_at": None,
        "manifest_json": None,
        "parsed_metadata_json": _metadata(
            {
                "schemaVersion": 1,
                "items": [None, {"standard": "iso-27001", "evidence": "bad"}],
                "digest": None,
            }
        ),
    }

    assert build_version_detail_response(row)["complianceSnapshot"] == {
        "schemaVersion": "1",
        "items": [
            {
                "standard": "iso-27001",
                "version": None,
                "controlId": None,
                "title": None,
                "evidence": [],
            }
        ],
        "digest": None,
    }


def test_skill_summary_projects_snapshot_from_exact_headline_version_metadata() -> None:
    row = {
        "id": 31,
        "slug": "demo-skill",
        "display_name": "Demo Skill",
        "summary": "Demo summary",
        "visibility": "PUBLIC",
        "status": "ACTIVE",
        "download_count": 7,
        "star_count": 3,
        "rating_avg": Decimal("4.50"),
        "rating_count": 4,
        "namespace": "global",
        "updated_at": datetime(2026, 6, 7, 10, 0, tzinfo=UTC),
        "published_version_id": 41,
        "published_version": "1.2.0",
        "published_version_status": "PUBLISHED",
        "resolution_mode": "PUBLISHED",
        "published_version_compliance_snapshot_json": json.dumps(SNAPSHOT),
        "published_version_parsed_metadata_json": _metadata(
            {"digest": "sha256:must-not-be-read"}
        ),
    }

    response = build_skill_summary_response(row)

    assert response["headlineVersion"] == {
        "id": 41,
        "version": "1.2.0",
        "status": "PUBLISHED",
    }
    assert response["complianceSnapshot"] == SNAPSHOT


def test_review_versions_project_each_versions_own_snapshot() -> None:
    old_snapshot = {**SNAPSHOT, "digest": "sha256:old"}
    new_snapshot = {**SNAPSHOT, "digest": "sha256:new"}
    base = {
        "status": "PUBLISHED",
        "changelog": None,
        "file_count": 1,
        "total_size": 10,
        "published_at": None,
        "download_ready": True,
    }

    old = _review_skill_version_response(
        {
            **base,
            "id": 1,
            "version": "1.0.0",
            "compliance_snapshot_json": json.dumps(old_snapshot),
        },
        active_version_id=2,
    )
    current = _review_skill_version_response(
        {
            **base,
            "id": 2,
            "version": "2.0.0",
            "compliance_snapshot_json": json.dumps(new_snapshot),
        },
        active_version_id=2,
    )

    assert old["complianceSnapshot"]["digest"] == "sha256:old"
    assert current["complianceSnapshot"]["digest"] == "sha256:new"


def test_runtime_projection_outputs_validate_against_exported_pydantic_contract() -> None:
    base_row = {
        "id": 20,
        "version": "1.2.0",
        "status": "PUBLISHED",
        "changelog": None,
        "file_count": 1,
        "total_size": 10,
        "published_at": None,
        "download_ready": True,
        "manifest_json": None,
    }
    list_snapshot = build_versions_page_response(
        [{**base_row, "compliance_snapshot_json": json.dumps(SNAPSHOT)}],
        1,
        0,
        20,
    )["items"][0]["complianceSnapshot"]
    detail_snapshot = build_version_detail_response(
        {**base_row, "parsed_metadata_json": _metadata()}
    )["complianceSnapshot"]
    review_snapshot = _review_skill_version_response(
        {
            **base_row,
            "compliance_snapshot_json": json.dumps(SNAPSHOT),
        },
        active_version_id=20,
    )["complianceSnapshot"]

    for projected in (list_snapshot, detail_snapshot, review_snapshot):
        validated = ComplianceProjection.model_validate(
            {"complianceSnapshot": projected}
        )
        assert validated.model_dump(mode="json", by_alias=True)[
            "complianceSnapshot"
        ] == SNAPSHOT


def test_compliance_contract_forbids_projection_shape_drift() -> None:
    with pytest.raises(ValidationError):
        ComplianceSnapshotResponse.model_validate(
            {**SNAPSHOT, "unreviewedContractField": "must fail"}
        )

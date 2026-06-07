from datetime import UTC, datetime

from app.api.skills import build_version_detail_response


def test_build_version_detail_response_maps_java_fields_and_json_strings() -> None:
    row = {
        "id": 20,
        "version": "1.2.0",
        "status": "PUBLISHED",
        "changelog": "latest",
        "file_count": 2,
        "total_size": 128,
        "published_at": datetime(2026, 6, 7, 10, 0, tzinfo=UTC),
        "parsed_metadata_json": "{\"name\":\"demo\"}",
        "manifest_json": "[{\"path\":\"SKILL.md\"}]",
    }

    assert build_version_detail_response(row) == {
        "id": 20,
        "version": "1.2.0",
        "status": "PUBLISHED",
        "changelog": "latest",
        "fileCount": 2,
        "totalSize": 128,
        "publishedAt": "2026-06-07T10:00:00Z",
        "parsedMetadataJson": "{\"name\":\"demo\"}",
        "manifestJson": "[{\"path\":\"SKILL.md\"}]",
    }


def test_build_version_detail_response_preserves_null_json_fields() -> None:
    row = {
        "id": 10,
        "version": "1.0.0",
        "status": "PUBLISHED",
        "changelog": None,
        "file_count": 0,
        "total_size": 0,
        "published_at": None,
        "parsed_metadata_json": None,
        "manifest_json": None,
    }

    assert build_version_detail_response(row)["parsedMetadataJson"] is None
    assert build_version_detail_response(row)["manifestJson"] is None
    assert build_version_detail_response(row)["publishedAt"] is None

from datetime import UTC, datetime

from app.api.skills import (
    build_versions_page_response,
    lifecycle_list_priority,
    lifecycle_visible_statuses,
    normalize_page_request,
    paginate_rows,
)


def test_paginate_rows_uses_zero_based_page_and_size() -> None:
    rows = [{"id": value} for value in range(1, 6)]

    assert paginate_rows(rows, page=1, size=2) == ([{"id": 3}, {"id": 4}], 5)


def test_paginate_rows_returns_empty_page_when_offset_exceeds_total() -> None:
    rows = [{"id": 1}]

    assert paginate_rows(rows, page=5, size=20) == ([], 1)


def test_normalize_page_request_clamps_invalid_values() -> None:
    assert normalize_page_request(page=-1, size=0) == (0, 20)
    assert normalize_page_request(page=1, size=500) == (1, 100)


def test_build_versions_page_response_maps_java_field_names() -> None:
    rows = [
        {
            "id": 20,
            "version": "1.2.0",
            "status": "PUBLISHED",
            "changelog": "latest",
            "file_count": 2,
            "total_size": 128,
            "published_at": datetime(2026, 6, 7, 10, 0, tzinfo=UTC),
            "download_ready": True,
        }
    ]

    assert build_versions_page_response(rows, total=1, page=0, size=20) == {
        "items": [
            {
                "id": 20,
                "version": "1.2.0",
                "status": "PUBLISHED",
                "changelog": "latest",
                "fileCount": 2,
                "totalSize": 128,
                "publishedAt": "2026-06-07T10:00:00Z",
                "downloadAvailable": True,
            }
        ],
        "total": 1,
        "page": 0,
        "size": 20,
    }


def test_build_versions_page_response_marks_non_published_not_downloadable() -> None:
    rows = [
        {
            "id": 10,
            "version": "draft",
            "status": "DRAFT",
            "changelog": None,
            "file_count": 0,
            "total_size": 0,
            "published_at": None,
            "download_ready": True,
        }
    ]

    assert build_versions_page_response(rows, total=1, page=0, size=20)["items"][0]["downloadAvailable"] is False


def test_lifecycle_visible_statuses_are_published_only_for_public_viewer() -> None:
    assert lifecycle_visible_statuses(can_manage=False) == ("PUBLISHED",)


def test_lifecycle_visible_statuses_include_manager_preview_states() -> None:
    assert lifecycle_visible_statuses(can_manage=True) == (
        "PUBLISHED",
        "REJECTED",
        "PENDING_REVIEW",
        "UPLOADED",
        "DRAFT",
        "SCANNING",
        "SCAN_FAILED",
        "YANKED",
    )


def test_lifecycle_list_priority_matches_java_order() -> None:
    statuses = [
        "YANKED",
        "SCAN_FAILED",
        "SCANNING",
        "DRAFT",
        "UPLOADED",
        "PENDING_REVIEW",
        "REJECTED",
        "PUBLISHED",
    ]

    assert sorted(statuses, key=lifecycle_list_priority) == [
        "PUBLISHED",
        "REJECTED",
        "PENDING_REVIEW",
        "UPLOADED",
        "DRAFT",
        "SCANNING",
        "SCAN_FAILED",
        "YANKED",
    ]

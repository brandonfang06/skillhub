from datetime import UTC, datetime
from decimal import Decimal

from app.api.skills import (
    build_skill_search_response,
    build_skill_search_ts_query,
    normalize_label_slugs,
    normalize_search_sort,
    parse_non_negative_int,
    parse_positive_int,
)


def test_build_skill_search_response_maps_java_summary_fields() -> None:
    rows = [
        {
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
        }
    ]

    assert build_skill_search_response(rows, total=1, page=0, size=20) == {
        "items": [
            {
                "id": 31,
                "slug": "demo-skill",
                "displayName": "Demo Skill",
                "summary": "Demo summary",
                "visibility": "PUBLIC",
                "status": "ACTIVE",
                "downloadCount": 7,
                "starCount": 3,
                "ratingAvg": 4.5,
                "ratingCount": 4,
                "namespace": "global",
                "updatedAt": "2026-06-07T10:00:00Z",
                "canSubmitPromotion": False,
                "headlineVersion": {"id": 41, "version": "1.2.0", "status": "PUBLISHED"},
                "publishedVersion": {"id": 41, "version": "1.2.0", "status": "PUBLISHED"},
                "ownerPreviewVersion": None,
                "resolutionMode": "PUBLISHED",
            }
        ],
        "total": 1,
        "page": 0,
        "size": 20,
    }


def test_build_skill_search_response_handles_empty_page() -> None:
    assert build_skill_search_response([], total=0, page=2, size=10) == {
        "items": [],
        "total": 0,
        "page": 2,
        "size": 10,
    }


def test_search_parameter_helpers_match_java_defaults() -> None:
    assert normalize_search_sort(None) == "newest"
    assert normalize_search_sort("  ") == "newest"
    assert normalize_search_sort(" downloads ") == "downloads"
    assert parse_non_negative_int(None, 0) == 0
    assert parse_non_negative_int("bad", 0) == 0
    assert parse_non_negative_int("-1", 0) == 0
    assert parse_non_negative_int("2", 0) == 2
    assert parse_positive_int(None, 20) == 20
    assert parse_positive_int("0", 20) == 20
    assert parse_positive_int("bad", 20) == 20
    assert parse_positive_int("5", 20) == 5


def test_normalize_label_slugs_trims_lowercases_and_deduplicates() -> None:
    assert normalize_label_slugs([" Featured ", "", "featured", "Security"]) == ["featured", "security"]


def test_build_skill_search_ts_query_uses_prefix_terms() -> None:
    assert build_skill_search_ts_query("Agent Ops 2026") == "agent:* & ops:*"

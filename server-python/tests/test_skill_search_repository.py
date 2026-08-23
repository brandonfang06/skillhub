from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.api.skills import (
    build_skill_search_response,
    build_skill_search_ts_query,
    normalize_label_slugs,
    normalize_search_sort,
    parse_non_negative_int,
    parse_positive_int,
    read_skill_search,
)
from tests.support.fake_db import FakeEngine, FakeResult, normalized_sql


class FakeSkillSearchConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.params: list[dict[str, object]] = []

    async def execute(self, statement: object, params: dict[str, object] | None = None) -> FakeResult:
        self.statements.append(normalized_sql(statement))
        self.params.append(params or {})
        if "COUNT(*)" in self.statements[-1]:
            return FakeResult(scalar=0)
        return FakeResult(rows=[])


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
                "complianceSnapshot": None,
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


@pytest.mark.anyio
async def test_read_skill_search_can_filter_installable_published_fallback_before_pagination() -> None:
    connection = FakeSkillSearchConnection()

    response = await read_skill_search(
        FakeEngine(connection),
        keyword="agent",
        namespace=None,
        labels=[],
        sort="newest",
        page=0,
        size=5,
        installable_only=True,
    )

    assert response == {"items": [], "total": 0, "page": 0, "size": 5}
    assert len(connection.statements) == 2
    for statement in connection.statements:
        assert "JOIN LATERAL" in statement
        assert "isv.skill_id = s.id" in statement
        assert "isv.status = 'PUBLISHED'" in statement
        assert "isv.download_ready = TRUE" in statement
        assert "isv.yanked_at IS NULL" in statement
    assert connection.params[0]["limit"] == 5


@pytest.mark.anyio
async def test_read_skill_search_resolves_an_older_published_version_when_latest_is_unpublished() -> None:
    connection = FakeSkillSearchConnection()

    await read_skill_search(
        FakeEngine(connection),
        keyword=None,
        namespace=None,
        labels=[],
        sort="newest",
        page=0,
        size=20,
    )

    for statement in connection.statements:
        normalized = " ".join(statement.split())
        assert "JOIN LATERAL" in statement
        assert "isv.skill_id = s.id" in statement
        assert "isv.status = 'PUBLISHED'" in statement
        assert "EXISTS (SELECT 1 FROM skill_file sf WHERE sf.version_id = isv.id)" in statement
        assert "CASE WHEN isv.id = s.latest_version_id THEN 0 ELSE 1 END" in normalized
        assert "JOIN skill_version isv ON isv.id = s.latest_version_id" not in statement
        assert "isv.download_ready = TRUE" not in statement
        assert "isv.yanked_at IS NULL" not in statement
    count_sql, page_sql = connection.statements
    assert "parsed_metadata_json" not in count_sql
    assert "isv.parsed_metadata_json -> 'complianceSnapshot'" in page_sql
    assert "CAST(isv.parsed_metadata_json AS text)" not in page_sql


@pytest.mark.anyio
async def test_read_skill_search_keeps_anonymous_visibility_public_only() -> None:
    connection = FakeSkillSearchConnection()

    await read_skill_search(
        FakeEngine(connection),
        keyword=None,
        namespace=None,
        labels=[],
        sort="newest",
        page=0,
        size=20,
    )

    for statement in connection.statements:
        assert "d.visibility = 'PUBLIC'" in statement
        assert "NAMESPACE_ONLY" not in statement
        assert "namespace_member" not in statement
    assert "current_user_id" not in connection.params[0]


@pytest.mark.anyio
async def test_read_skill_search_includes_namespace_only_for_authenticated_members() -> None:
    connection = FakeSkillSearchConnection()

    await read_skill_search(
        FakeEngine(connection),
        keyword="agent",
        namespace=None,
        labels=[],
        sort="newest",
        page=0,
        size=20,
        current_user_id="user-a",
    )

    for statement in connection.statements:
        assert "d.visibility = 'PUBLIC'" in statement
        assert "d.visibility = 'NAMESPACE_ONLY'" in statement
        assert "namespace_member" in statement
        assert "nm.namespace_id = d.namespace_id" in statement
        assert "nm.user_id = :current_user_id" in statement
        assert "s.visibility = 'PRIVATE'" not in statement
    assert connection.params[0]["current_user_id"] == "user-a"


@pytest.mark.anyio
async def test_read_skill_search_excludes_archived_namespaces_for_authenticated_members() -> None:
    connection = FakeSkillSearchConnection()

    await read_skill_search(
        FakeEngine(connection),
        keyword=None,
        namespace=None,
        labels=[],
        sort="newest",
        page=0,
        size=20,
        current_user_id="user-a",
    )

    for statement in connection.statements:
        assert "n.status <> 'ARCHIVED'" in statement
        assert "n.status <> 'ARCHIVED' OR EXISTS" not in statement

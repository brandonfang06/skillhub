import pytest

from app.api.skills import (
    build_clawhub_resolve_response,
    from_clawhub_canonical_slug,
    read_clawhub_legacy_slug_coordinate,
)
from tests.support.fake_db import FakeEngine, FakeResult, normalized_sql


class LegacySlugConnection:
    def __init__(self) -> None:
        self.statement = ""

    async def execute(
        self,
        statement: object,
        params: dict[str, object],
    ) -> FakeResult:
        self.statement = normalized_sql(statement)
        assert params == {"slug": "demo"}
        return FakeResult(row={"namespace": "global", "slug": "demo"})


def test_from_clawhub_canonical_slug_maps_global_and_namespace() -> None:
    assert from_clawhub_canonical_slug("demo") == ("global", "demo")
    assert from_clawhub_canonical_slug("team-ai--demo") == ("team-ai", "demo")


def test_from_clawhub_canonical_slug_splits_on_first_separator_only() -> None:
    assert from_clawhub_canonical_slug("team--demo--extra") == ("team", "demo--extra")


def test_build_clawhub_resolve_response_maps_plain_version_info() -> None:
    assert build_clawhub_resolve_response({"version": "1.2.0"}) == {
        "match": {"version": "1.2.0"},
        "latestVersion": {"version": "1.2.0"},
    }


def test_build_clawhub_resolve_response_handles_missing_version() -> None:
    assert build_clawhub_resolve_response({"version": None}) == {
        "match": None,
        "latestVersion": None,
    }


@pytest.mark.anyio
async def test_legacy_slug_lookup_prefers_public_then_global_then_lowest_id() -> None:
    connection = LegacySlugConnection()

    assert await read_clawhub_legacy_slug_coordinate(
        FakeEngine(connection),
        "demo",
    ) == ("global", "demo")

    assert "CASE WHEN s.visibility = 'PUBLIC' THEN 0 ELSE 1 END" in connection.statement
    assert "CASE WHEN n.type = 'GLOBAL' THEN 0 ELSE 1 END" in connection.statement
    assert connection.statement.index("s.visibility = 'PUBLIC'") < connection.statement.index(
        "n.type = 'GLOBAL'"
    )
    assert connection.statement.endswith("s.id ASC LIMIT 1")

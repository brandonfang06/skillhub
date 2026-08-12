import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.skills.read_repository import read_searchable_skill_namespaces
from tests.support.fake_db import FakeEngine, FakeResult, normalized_sql


class FakeNamespaceSearchConnection:
    def __init__(self) -> None:
        self.statement = ""
        self.params: dict[str, object] = {}

    async def execute(self, statement: object, params: dict[str, object] | None = None) -> FakeResult:
        self.statement = normalized_sql(statement)
        self.params = params or {}
        return FakeResult(rows=[{"slug": "team-ai", "display_name": "AI Platform", "visible_skill_count": 3}])


def test_search_namespace_candidates_forwards_identity_and_bounds() -> None:
    seen: list[dict[str, object]] = []
    app = create_app()
    app.state.skill_search_namespace_reader = lambda **kwargs: seen.append(kwargs) or [
        {"slug": "team-ai", "displayName": "AI Platform", "visibleSkillCount": 3}
    ]

    response = TestClient(app).get(
        "/api/web/search/namespaces?q=%20AI%20&limit=500",
        headers={"X-Mock-User-Id": " user-a ", "X-Request-Id": "namespace-search"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "namespace-search"
    assert response.json()["data"][0]["slug"] == "team-ai"
    assert seen == [{"query": "AI", "limit": 50, "current_user_id": "user-a"}]


def test_search_namespace_candidates_uses_anonymous_defaults() -> None:
    seen: list[dict[str, object]] = []
    app = create_app()
    app.state.skill_search_namespace_reader = lambda **kwargs: seen.append(kwargs) or []

    response = TestClient(app).get("/api/web/search/namespaces?limit=0")

    assert response.status_code == 200
    assert response.json()["data"] == []
    assert seen == [{"query": None, "limit": 20, "current_user_id": None}]


@pytest.mark.anyio
async def test_searchable_namespace_query_matches_search_visibility_and_namespace_lifecycle() -> None:
    connection = FakeNamespaceSearchConnection()

    result = await read_searchable_skill_namespaces(
        FakeEngine(connection),
        query="AI",
        limit=20,
        current_user_id="user-a",
    )

    assert result == [{"slug": "team-ai", "displayName": "AI Platform", "visibleSkillCount": 3}]
    assert "d.visibility = 'PUBLIC'" in connection.statement
    assert "d.visibility = 'NAMESPACE_ONLY'" in connection.statement
    assert "nm.user_id = :current_user_id" in connection.statement
    assert "n.status <> 'ARCHIVED'" in connection.statement
    assert "n.status = 'ACTIVE'" not in connection.statement
    assert "sv.status = 'PUBLISHED'" in connection.statement
    assert "EXISTS (SELECT 1 FROM skill_file sf WHERE sf.version_id = sv.id)" in connection.statement
    assert connection.params == {
        "limit": 20,
        "current_user_id": "user-a",
        "query": "ai",
        "query_like": "%ai%",
        "query_prefix": "ai%",
    }

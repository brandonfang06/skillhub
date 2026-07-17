from __future__ import annotations

from typing import Any

import pytest

from app.namespace.dependencies import read_namespace_dependency_counts


class FakeMappings:
    def all(self) -> list[dict[str, int]]:
        return [{"namespace_id": 17, "skill_count": 2, "review_task_count": 3, "promotion_request_count": 4}]


class FakeResult:
    def mappings(self) -> FakeMappings:
        return FakeMappings()


class FakeConnection:
    def __init__(self) -> None:
        self.sql = ""
        self.params: dict[str, Any] = {}

    async def execute(self, statement: object, params: dict[str, Any]) -> FakeResult:
        self.sql = " ".join(str(statement).split())
        self.params = params
        return FakeResult()


@pytest.mark.anyio
async def test_dependency_reader_returns_separate_counts() -> None:
    connection = FakeConnection()

    result = await read_namespace_dependency_counts(connection, 17)

    assert result == {"skillCount": 2, "reviewTaskCount": 3, "promotionRequestCount": 4}
    assert "COUNT(*) FROM skill" in connection.sql
    assert "COUNT(*) FROM review_task" in connection.sql
    assert "COUNT(*) FROM promotion_request" in connection.sql
    assert connection.params == {"namespace_ids": [17]}

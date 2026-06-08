from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app.publish.auto_withdraw import auto_withdraw_pending_review_versions


@dataclass
class FakeResult:
    rows: list[dict[str, Any]] | None = None

    def mappings(self) -> "FakeResult":
        return self

    def all(self) -> list[dict[str, Any]]:
        return self.rows or []


class FakeConnection:
    def __init__(self, results: list[FakeResult]) -> None:
        self.results = results
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> FakeResult:
        self.statements.append(str(statement))
        self.params.append(params or {})
        if self.results:
            return self.results.pop(0)
        return FakeResult()


@pytest.mark.anyio
async def test_auto_withdraw_pending_review_versions_deletes_tasks_and_marks_uploaded() -> None:
    connection = FakeConnection(
        [
            FakeResult(rows=[{"id": 41}, {"id": 42}]),
            FakeResult(),
            FakeResult(),
        ]
    )

    withdrawn = await auto_withdraw_pending_review_versions(
        connection,
        skill_id=7,
    )

    assert withdrawn == [41, 42]
    assert "SELECT id" in connection.statements[0]
    assert "status = 'PENDING_REVIEW'" in connection.statements[0]
    assert "DELETE FROM review_task" in connection.statements[1]
    assert "UPDATE skill_version" in connection.statements[2]
    assert "status = 'UPLOADED'" in connection.statements[2]
    assert connection.params[1]["version_ids"] == [41, 42]
    assert connection.params[2]["version_ids"] == [41, 42]
    assert "updated_by" not in connection.params[2]


@pytest.mark.anyio
async def test_auto_withdraw_pending_review_versions_noops_without_pending_versions() -> None:
    connection = FakeConnection([FakeResult(rows=[])])

    withdrawn = await auto_withdraw_pending_review_versions(
        connection,
        skill_id=7,
    )

    assert withdrawn == []
    assert len(connection.statements) == 1

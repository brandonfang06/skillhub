from __future__ import annotations

from typing import Any

import pytest

from app.admin import search_refresh


class FakeTransaction:
    def __init__(self, skill_id: int) -> None:
        self.skill_id = skill_id

    async def __aenter__(self) -> Any:
        return {"skill_id": self.skill_id}

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine:
    def __init__(self) -> None:
        self.skill_ids: list[int] = []

    def begin(self) -> FakeTransaction:
        skill_id = len(self.skill_ids)
        return FakeTransaction(skill_id)


@pytest.mark.anyio
async def test_refresh_skill_search_documents_deduplicates_and_continues_after_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    engine = FakeEngine()
    rebuilt: list[int] = []
    failure_triggers: list[str] = []

    async def rebuild(_connection: Any, skill_id: int) -> None:
        rebuilt.append(skill_id)
        if skill_id == 2:
            raise RuntimeError("index unavailable")

    monkeypatch.setattr(search_refresh, "upsert_skill_search_document", rebuild)
    monkeypatch.setattr(search_refresh, "increment_search_rebuild_failure", failure_triggers.append)

    await search_refresh.refresh_skill_search_documents(engine, [1, 2, 2, 3])

    assert rebuilt == [1, 2, 2, 3]
    assert failure_triggers == ["batch"]
    assert "Retrying search document rebuild for skill 2 after attempt 1" in caplog.text
    assert "Failed to rebuild search document for skill 2 after label change" in caplog.text

from __future__ import annotations

import logging
from typing import Any

from app.admin.search import upsert_skill_search_document
from app.core.metrics import increment_search_rebuild_failure

log = logging.getLogger(__name__)
REBUILD_BATCH_SIZE = 50
REBUILD_MAX_ATTEMPTS = 2


async def _refresh_skill_search_document(engine: Any, skill_id: int, trigger: str) -> None:
    for attempt in range(1, REBUILD_MAX_ATTEMPTS + 1):
        try:
            async with engine.begin() as connection:
                await upsert_skill_search_document(connection, skill_id)
            return
        except Exception:
            if attempt < REBUILD_MAX_ATTEMPTS:
                log.warning(
                    "Retrying search document rebuild for skill %s after attempt %s",
                    skill_id,
                    attempt,
                    exc_info=True,
                )
                continue
            increment_search_rebuild_failure(trigger)
            log.exception("Failed to rebuild search document for skill %s after label change", skill_id)


async def refresh_skill_search_documents(engine: Any, skill_ids: list[int]) -> None:
    normalized_ids = list(dict.fromkeys(int(skill_id) for skill_id in skill_ids))
    trigger = "single" if len(normalized_ids) == 1 else "batch"
    for offset in range(0, len(normalized_ids), REBUILD_BATCH_SIZE):
        for skill_id in normalized_ids[offset : offset + REBUILD_BATCH_SIZE]:
            await _refresh_skill_search_document(engine, skill_id, trigger)


__all__ = ["refresh_skill_search_documents"]

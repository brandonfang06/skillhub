from __future__ import annotations

import logging
from typing import Any

from app.admin.search import upsert_skill_search_document

log = logging.getLogger(__name__)
REBUILD_BATCH_SIZE = 50


async def refresh_skill_search_documents(engine: Any, skill_ids: list[int]) -> None:
    normalized_ids = list(dict.fromkeys(int(skill_id) for skill_id in skill_ids))
    for offset in range(0, len(normalized_ids), REBUILD_BATCH_SIZE):
        for skill_id in normalized_ids[offset : offset + REBUILD_BATCH_SIZE]:
            try:
                async with engine.begin() as connection:
                    await upsert_skill_search_document(connection, skill_id)
            except Exception:
                log.exception("Failed to rebuild search document for skill %s after label change", skill_id)


__all__ = ["refresh_skill_search_documents"]

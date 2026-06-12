from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any


@asynccontextmanager
async def transaction_connection(engine: Any) -> AsyncIterator[Any]:
    async with engine.begin() as connection:
        yield connection

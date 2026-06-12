from __future__ import annotations

from typing import Any, Generic, TypeVar


TConnection = TypeVar("TConnection")


class FakeResult:
    def __init__(
        self,
        row: dict[str, Any] | list[dict[str, Any]] | None = None,
        rows: list[dict[str, Any]] | None = None,
        scalar: Any = None,
        rowcount: int = 1,
    ) -> None:
        if isinstance(row, list):
            rows = row
            row = None
        self.row = row
        self.rows = rows if rows is not None else ([row] if row is not None else [])
        self.scalar = scalar
        self.rowcount = rowcount

    def mappings(self) -> "FakeResult":
        return self

    def all(self) -> list[dict[str, Any]]:
        return self.rows or []

    def one_or_none(self) -> dict[str, Any] | None:
        if self.row is not None:
            return self.row
        rows = self.rows or []
        return rows[0] if rows else None

    def scalar_one(self) -> Any:
        if self.scalar is not None:
            return self.scalar
        row = self.one_or_none()
        if row is None:
            raise AssertionError("FakeResult.scalar_one() called without a row or scalar")
        if "count" in row:
            return int(row["count"])
        return next(iter(row.values()))


class FakeTransaction(Generic[TConnection]):
    def __init__(self, connection: TConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> TConnection:
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeEngine(Generic[TConnection]):
    def __init__(self, connection: TConnection) -> None:
        self.connection = connection

    def begin(self) -> FakeTransaction[TConnection]:
        return FakeTransaction(self.connection)

    def connect(self) -> FakeTransaction[TConnection]:
        return FakeTransaction(self.connection)


def normalized_sql(statement: object) -> str:
    return " ".join(str(statement).split())

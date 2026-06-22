from __future__ import annotations

import pytest


class FakeObjectStorage:
    def __init__(self, objects: dict[str, bytes] | None = None) -> None:
        self.objects = dict(objects or {})
        self.deleted_keys: list[str] = []

    def put_bytes(self, key: str, content: bytes, *, content_type: str | None = None) -> None:
        self.objects[key] = content

    def read_bytes(self, key: str) -> bytes:
        try:
            return self.objects[key]
        except KeyError as exc:
            raise FileNotFoundError(key) from exc

    def exists(self, key: str) -> bool:
        return key in self.objects

    def delete_many(self, keys: list[str]) -> list[str]:
        deleted: list[str] = []
        for key in keys:
            if key in self.objects:
                del self.objects[key]
                deleted.append(key)
                self.deleted_keys.append(key)
        return deleted


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def fake_object_storage_factory() -> object:
    def factory(objects: dict[str, bytes] | None = None) -> FakeObjectStorage:
        return FakeObjectStorage(objects)

    return factory

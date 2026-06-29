from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
from typing import Any

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "migrate_minio_bucket.py"


class FakeNotFoundError(Exception):
    response = {"Error": {"Code": "404"}}


class FakeBody:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.offset = 0

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = len(self.content) - self.offset
        chunk = self.content[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk


class FakePaginator:
    def __init__(self, client: "FakeS3Client") -> None:
        self.client = client

    def paginate(self, *, Bucket: str, Prefix: str) -> list[dict[str, Any]]:
        del Bucket
        contents = [
            {"Key": key, "Size": len(value["content"])}
            for key, value in sorted(self.client.objects.items())
            if key.startswith(Prefix)
        ]
        return [{"Contents": contents}]


class FakeS3Client:
    def __init__(
        self,
        objects: dict[str, bytes] | None = None,
        *,
        content_types: dict[str, str] | None = None,
        metadata: dict[str, dict[str, str]] | None = None,
        corrupt_puts: dict[str, bytes] | None = None,
    ) -> None:
        self.objects = {
            key: {
                "content": content,
                "content_type": (content_types or {}).get(key, "application/octet-stream"),
                "metadata": (metadata or {}).get(key, {}),
            }
            for key, content in (objects or {}).items()
        }
        self.corrupt_puts = corrupt_puts or {}
        self.put_calls: list[dict[str, Any]] = []

    def get_paginator(self, name: str) -> FakePaginator:
        assert name == "list_objects_v2"
        return FakePaginator(self)

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        del Bucket
        if Key not in self.objects:
            raise FakeNotFoundError(Key)
        stored = self.objects[Key]
        return {
            "ContentLength": len(stored["content"]),
            "ContentType": stored["content_type"],
            "Metadata": stored["metadata"],
        }

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        head = self.head_object(Bucket=Bucket, Key=Key)
        return {
            **head,
            "Body": FakeBody(self.objects[Key]["content"]),
        }

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: Any,
        ContentType: str | None = None,
        Metadata: dict[str, str] | None = None,
    ) -> None:
        del Bucket
        content = Body.read() if hasattr(Body, "read") else bytes(Body)
        stored_content = self.corrupt_puts.get(Key, content)
        self.objects[Key] = {
            "content": stored_content,
            "content_type": ContentType or "application/octet-stream",
            "metadata": Metadata or {},
        }
        self.put_calls.append({"Key": Key, "ContentType": ContentType, "Metadata": Metadata})


def load_script() -> Any:
    spec = importlib.util.spec_from_file_location("migrate_minio_bucket", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dry_run_lists_default_skillhub_prefixes_without_writing() -> None:
    script = load_script()
    source = FakeS3Client(
        {
            "skills/1/10/SKILL.md": b"skill",
            "packages/1/10/bundle.zip": b"zip",
            "unrelated/object.txt": b"ignore",
        }
    )
    destination = FakeS3Client()

    summary = script.migrate_bucket_objects(
        source,
        destination,
        source_bucket="old-bucket",
        dest_bucket="new-bucket",
        options=script.MigrationOptions(dry_run=True),
    )

    assert summary.planned == 2
    assert summary.copied == 0
    assert summary.results_by_status == {"dry_run": 2}
    assert destination.objects == {}


def test_copy_preserves_key_content_type_and_metadata_and_skips_same_size_existing_object() -> None:
    script = load_script()
    source = FakeS3Client(
        {
            "skills/1/10/SKILL.md": b"skill",
            "packages/1/10/bundle.zip": b"zip",
        },
        content_types={"packages/1/10/bundle.zip": "application/zip"},
        metadata={"packages/1/10/bundle.zip": {"sha": "source"}},
    )
    destination = FakeS3Client({"skills/1/10/SKILL.md": b"local"})

    summary = script.migrate_bucket_objects(
        source,
        destination,
        source_bucket="old-bucket",
        dest_bucket="new-bucket",
        options=script.MigrationOptions(),
    )

    assert summary.results_by_status == {"copied": 1, "skipped_existing": 1}
    assert destination.objects["packages/1/10/bundle.zip"]["content"] == b"zip"
    assert destination.objects["packages/1/10/bundle.zip"]["content_type"] == "application/zip"
    assert destination.objects["packages/1/10/bundle.zip"]["metadata"] == {"sha": "source"}
    assert destination.put_calls == [
        {
            "Key": "packages/1/10/bundle.zip",
            "ContentType": "application/zip",
            "Metadata": {"sha": "source"},
        }
    ]


def test_existing_destination_object_with_different_size_fails_without_overwrite() -> None:
    script = load_script()
    source = FakeS3Client({"packages/1/10/bundle.zip": b"source"})
    destination = FakeS3Client({"packages/1/10/bundle.zip": b"different-size"})

    with pytest.raises(script.MigrationError, match="different size"):
        script.migrate_bucket_objects(
            source,
            destination,
            source_bucket="old-bucket",
            dest_bucket="new-bucket",
            options=script.MigrationOptions(),
        )

    assert destination.objects["packages/1/10/bundle.zip"]["content"] == b"different-size"


def test_verify_read_back_detects_destination_content_mismatch() -> None:
    script = load_script()
    source = FakeS3Client({"packages/1/10/bundle.zip": b"abc"})
    destination = FakeS3Client(corrupt_puts={"packages/1/10/bundle.zip": b"xyz"})

    with pytest.raises(script.MigrationError, match="checksum"):
        script.migrate_bucket_objects(
            source,
            destination,
            source_bucket="old-bucket",
            dest_bucket="new-bucket",
            options=script.MigrationOptions(verify_read_back=True),
        )


def test_create_s3_client_supports_explicit_proxy_url(monkeypatch: pytest.MonkeyPatch) -> None:
    script = load_script()
    captured: dict[str, Any] = {}

    class FakeConfig:
        def __init__(self, **kwargs: Any) -> None:
            captured["config"] = kwargs

    def fake_client(**kwargs: Any) -> object:
        captured["client"] = kwargs
        return object()

    fake_botocore = types.ModuleType("botocore")
    fake_config_module = types.ModuleType("botocore.config")
    fake_config_module.Config = FakeConfig
    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=fake_client))
    monkeypatch.setitem(sys.modules, "botocore", fake_botocore)
    monkeypatch.setitem(sys.modules, "botocore.config", fake_config_module)

    script.create_s3_client(
        endpoint_url="https://minio.example.test",
        access_key="access",
        secret_key="secret",
        region="us-east-1",
        session_token=None,
        verify_ssl=True,
        path_style=True,
        proxy_url="http://proxy.example.test:8080",
    )

    assert captured["config"]["proxies"] == {
        "http": "http://proxy.example.test:8080",
        "https": "http://proxy.example.test:8080",
    }
    assert captured["client"]["endpoint_url"] == "https://minio.example.test"

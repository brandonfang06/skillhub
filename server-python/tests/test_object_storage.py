import pytest

from app.core.config import get_settings
from app.object_storage import S3ObjectStorage


class FakeS3Error(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeS3Client:
    def __init__(self, *, head_bucket_error: Exception | None = None) -> None:
        self.head_bucket_error = head_bucket_error
        self.created_buckets: list[str] = []

    def head_bucket(self, *, Bucket: str) -> None:
        if self.head_bucket_error is not None:
            raise self.head_bucket_error

    def create_bucket(self, *, Bucket: str) -> None:
        self.created_buckets.append(Bucket)


def s3_settings(monkeypatch):
    monkeypatch.setenv("SKILLHUB_STORAGE_PROVIDER", "s3")
    monkeypatch.setenv("SKILLHUB_STORAGE_S3_BUCKET", "skillhub-packages")
    monkeypatch.setenv("SKILLHUB_STORAGE_S3_AUTO_CREATE_BUCKET", "true")
    return get_settings()


def test_s3_ensure_bucket_creates_missing_bucket(monkeypatch) -> None:
    client = FakeS3Client(head_bucket_error=FakeS3Error("404"))
    storage = S3ObjectStorage(s3_settings(monkeypatch), client=client)

    storage._ensure_bucket()

    assert client.created_buckets == ["skillhub-packages"]


def test_s3_ensure_bucket_does_not_create_bucket_when_access_is_forbidden(monkeypatch) -> None:
    error = FakeS3Error("403")
    client = FakeS3Client(head_bucket_error=error)
    storage = S3ObjectStorage(s3_settings(monkeypatch), client=client)

    with pytest.raises(FakeS3Error) as raised:
        storage._ensure_bucket()

    assert raised.value is error
    assert client.created_buckets == []

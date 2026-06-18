from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from app.core.config import Settings, get_settings


class ObjectNotFoundError(FileNotFoundError):
    pass


class ObjectStorage(Protocol):
    def put_bytes(self, key: str, content: bytes, *, content_type: str | None = None) -> None:
        pass

    def read_bytes(self, key: str) -> bytes:
        pass

    def exists(self, key: str) -> bool:
        pass

    def delete_many(self, keys: list[str]) -> list[str]:
        pass


def _assert_safe_key(key: str) -> str:
    normalized = key.replace("\\", "/").strip()
    if normalized == "" or normalized.startswith("/") or ".." in normalized.split("/"):
        raise ValueError(f"Object key escapes storage base: {key}")
    return normalized


class LocalObjectStorage:
    def __init__(self, storage_base_path: str) -> None:
        self.base = Path(storage_base_path).resolve()

    def _target(self, key: str) -> Path:
        safe_key = _assert_safe_key(key)
        target = (self.base / safe_key).resolve()
        try:
            target.relative_to(self.base)
        except ValueError as exc:
            raise ValueError(f"Object key escapes storage base: {key}") from exc
        return target

    def put_bytes(self, key: str, content: bytes, *, content_type: str | None = None) -> None:
        target = self._target(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def read_bytes(self, key: str) -> bytes:
        try:
            return self._target(key).read_bytes()
        except FileNotFoundError as exc:
            raise ObjectNotFoundError(key) from exc

    def exists(self, key: str) -> bool:
        try:
            return self._target(key).is_file()
        except ValueError:
            return False

    def delete_many(self, keys: list[str]) -> list[str]:
        deleted: list[str] = []
        for key in keys:
            target = self._target(key)
            if target.exists():
                target.unlink()
                deleted.append(key)
        return deleted


class S3ObjectStorage:
    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        self.settings = settings
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = self._create_client()
            if self.settings.storage_s3_auto_create_bucket:
                self._ensure_bucket()
        return self._client

    def _create_client(self) -> Any:
        import boto3
        from botocore.config import Config

        config = Config(
            region_name=self.settings.storage_s3_region,
            max_pool_connections=self.settings.storage_s3_max_connections,
            connect_timeout=self.settings.storage_s3_connection_acquisition_timeout_seconds,
            read_timeout=self.settings.storage_s3_api_call_attempt_timeout_seconds,
            s3={
                "addressing_style": "path" if self.settings.storage_s3_force_path_style else "auto",
                "payload_signing_enabled": not self.settings.storage_s3_disable_chunked_encoding,
            },
        )
        kwargs: dict[str, Any] = {
            "service_name": "s3",
            "endpoint_url": self.settings.storage_s3_effective_endpoint or None,
            "region_name": self.settings.storage_s3_region,
            "config": config,
        }
        if self.settings.storage_s3_access_key and self.settings.storage_s3_secret_key:
            kwargs["aws_access_key_id"] = self.settings.storage_s3_access_key
            kwargs["aws_secret_access_key"] = self.settings.storage_s3_secret_key
        return boto3.client(**kwargs)

    def _ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.settings.storage_s3_bucket)
        except Exception:
            self.client.create_bucket(Bucket=self.settings.storage_s3_bucket)

    def put_bytes(self, key: str, content: bytes, *, content_type: str | None = None) -> None:
        kwargs: dict[str, Any] = {
            "Bucket": self.settings.storage_s3_bucket,
            "Key": _assert_safe_key(key),
            "Body": content,
        }
        if content_type:
            kwargs["ContentType"] = content_type
        self.client.put_object(**kwargs)

    def read_bytes(self, key: str) -> bytes:
        safe_key = _assert_safe_key(key)
        try:
            response = self.client.get_object(Bucket=self.settings.storage_s3_bucket, Key=safe_key)
        except Exception as exc:
            if _looks_like_s3_not_found(exc):
                raise ObjectNotFoundError(key) from exc
            raise
        return response["Body"].read()

    def exists(self, key: str) -> bool:
        safe_key = _assert_safe_key(key)
        try:
            self.client.head_object(Bucket=self.settings.storage_s3_bucket, Key=safe_key)
            return True
        except Exception as exc:
            if _looks_like_s3_not_found(exc):
                return False
            raise

    def delete_many(self, keys: list[str]) -> list[str]:
        safe_keys = [_assert_safe_key(key) for key in keys]
        if not safe_keys:
            return []
        self.client.delete_objects(
            Bucket=self.settings.storage_s3_bucket,
            Delete={"Objects": [{"Key": key} for key in safe_keys], "Quiet": True},
        )
        return keys

def _looks_like_s3_not_found(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    error = response.get("Error")
    if not isinstance(error, dict):
        return False
    return str(error.get("Code") or "") in {"404", "NoSuchKey", "NotFound", "NoSuchBucket"}


def object_storage_for_settings(settings: Settings) -> ObjectStorage:
    if getattr(settings, "storage_provider", "local") == "s3":
        return S3ObjectStorage(settings)
    return LocalObjectStorage(str(settings.storage_base_path))


def object_storage_for_base_path(storage_base_path: str) -> ObjectStorage:
    settings = get_settings()
    if settings.storage_provider == "s3":
        return S3ObjectStorage(settings)
    return LocalObjectStorage(storage_base_path)

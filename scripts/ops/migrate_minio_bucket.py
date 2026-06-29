#!/usr/bin/env python
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import Any, Iterable, Sequence


DEFAULT_PREFIXES = ("skills/", "packages/")
DEFAULT_REGION = "us-east-1"
DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024
DEFAULT_SPOOL_MAX_SIZE = 64 * 1024 * 1024


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class MigrationOptions:
    prefixes: Sequence[str] = DEFAULT_PREFIXES
    dry_run: bool = False
    overwrite_existing: bool = False
    verify_read_back: bool = False
    verify_existing: bool = False
    chunk_size: int = DEFAULT_CHUNK_SIZE
    spool_max_size: int = DEFAULT_SPOOL_MAX_SIZE
    manifest_path: Path | None = None


@dataclass(frozen=True)
class ObjectCandidate:
    key: str
    size: int


@dataclass(frozen=True)
class MigrationResult:
    key: str
    status: str
    size: int
    source_sha256: str | None = None
    destination_sha256: str | None = None


@dataclass(frozen=True)
class MigrationSummary:
    results: list[MigrationResult]

    @property
    def planned(self) -> int:
        return len(self.results)

    @property
    def copied(self) -> int:
        return self.results_by_status.get("copied", 0)

    @property
    def results_by_status(self) -> dict[str, int]:
        return dict(Counter(result.status for result in self.results))


def normalize_prefix(value: str) -> str:
    prefix = value.replace("\\", "/").strip()
    if prefix == "" or prefix.startswith("/") or ".." in prefix.split("/"):
        raise MigrationError(f"Unsafe prefix: {value}")
    return prefix if prefix.endswith("/") else f"{prefix}/"


def normalize_key(value: str) -> str:
    key = value.replace("\\", "/").strip()
    if key == "" or key.startswith("/") or ".." in key.split("/"):
        raise MigrationError(f"Unsafe object key: {value}")
    return key


def is_not_found_error(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    error = response.get("Error")
    if not isinstance(error, dict):
        return False
    return str(error.get("Code") or "") in {"404", "NoSuchKey", "NotFound", "NoSuchBucket"}


def head_object_or_none(client: Any, *, bucket: str, key: str) -> dict[str, Any] | None:
    try:
        return client.head_object(Bucket=bucket, Key=key)
    except Exception as exc:
        if is_not_found_error(exc):
            return None
        raise


def list_candidates(client: Any, *, bucket: str, prefixes: Iterable[str]) -> list[ObjectCandidate]:
    seen: set[str] = set()
    candidates: list[ObjectCandidate] = []
    paginator = client.get_paginator("list_objects_v2")
    for raw_prefix in prefixes:
        prefix = normalize_prefix(raw_prefix)
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                key = normalize_key(str(item["Key"]))
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(ObjectCandidate(key=key, size=int(item.get("Size", 0))))
    return candidates


def read_object_to_spool(
    client: Any,
    *,
    bucket: str,
    key: str,
    expected_size: int,
    chunk_size: int,
    spool_max_size: int,
) -> tuple[SpooledTemporaryFile[bytes], str]:
    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    digest = sha256()
    total = 0
    spool: SpooledTemporaryFile[bytes] = SpooledTemporaryFile(max_size=spool_max_size)
    try:
        while True:
            chunk = body.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            digest.update(chunk)
            spool.write(chunk)
    finally:
        close = getattr(body, "close", None)
        if callable(close):
            close()

    if total != expected_size:
        spool.close()
        raise MigrationError(f"Source object {key} size changed while reading: expected {expected_size}, got {total}")

    spool.seek(0)
    return spool, digest.hexdigest()


def read_object_sha256(client: Any, *, bucket: str, key: str, chunk_size: int) -> str:
    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    digest = sha256()
    try:
        while True:
            chunk = body.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    finally:
        close = getattr(body, "close", None)
        if callable(close):
            close()
    return digest.hexdigest()


def metadata_from_response(response: dict[str, Any]) -> tuple[str | None, dict[str, str]]:
    content_type = response.get("ContentType")
    metadata = response.get("Metadata") if isinstance(response.get("Metadata"), dict) else {}
    return (str(content_type) if content_type else None, {str(k): str(v) for k, v in metadata.items()})


def verify_destination(
    destination_client: Any,
    *,
    bucket: str,
    key: str,
    expected_size: int,
    expected_sha256: str,
    options: MigrationOptions,
) -> str | None:
    destination_head = head_object_or_none(destination_client, bucket=bucket, key=key)
    if destination_head is None:
        raise MigrationError(f"Destination object {key} was not found after upload")
    destination_size = int(destination_head.get("ContentLength", -1))
    if destination_size != expected_size:
        raise MigrationError(
            f"Destination object {key} size mismatch after upload: expected {expected_size}, got {destination_size}"
        )
    if not options.verify_read_back:
        return None
    destination_sha256 = read_object_sha256(
        destination_client,
        bucket=bucket,
        key=key,
        chunk_size=options.chunk_size,
    )
    if destination_sha256 != expected_sha256:
        raise MigrationError(f"Destination object {key} checksum mismatch after upload")
    return destination_sha256


def copy_candidate(
    source_client: Any,
    destination_client: Any,
    *,
    source_bucket: str,
    dest_bucket: str,
    candidate: ObjectCandidate,
    options: MigrationOptions,
) -> MigrationResult:
    key = normalize_key(candidate.key)
    if options.dry_run:
        return MigrationResult(key=key, status="dry_run", size=candidate.size)

    source_head = source_client.head_object(Bucket=source_bucket, Key=key)
    source_size = int(source_head.get("ContentLength", candidate.size))
    content_type, metadata = metadata_from_response(source_head)

    destination_head = head_object_or_none(destination_client, bucket=dest_bucket, key=key)
    if destination_head is not None and not options.overwrite_existing:
        destination_size = int(destination_head.get("ContentLength", -1))
        if destination_size != source_size:
            raise MigrationError(
                f"Destination object {key} exists with different size: source={source_size}, destination={destination_size}"
            )
        if options.verify_existing:
            source_sha256 = read_object_sha256(
                source_client,
                bucket=source_bucket,
                key=key,
                chunk_size=options.chunk_size,
            )
            destination_sha256 = read_object_sha256(
                destination_client,
                bucket=dest_bucket,
                key=key,
                chunk_size=options.chunk_size,
            )
            if destination_sha256 != source_sha256:
                raise MigrationError(f"Destination object {key} checksum mismatch for existing object")
            return MigrationResult(
                key=key,
                status="verified_existing",
                size=source_size,
                source_sha256=source_sha256,
                destination_sha256=destination_sha256,
            )
        return MigrationResult(key=key, status="skipped_existing", size=source_size)

    spool, source_sha256 = read_object_to_spool(
        source_client,
        bucket=source_bucket,
        key=key,
        expected_size=source_size,
        chunk_size=options.chunk_size,
        spool_max_size=options.spool_max_size,
    )
    try:
        put_kwargs: dict[str, Any] = {
            "Bucket": dest_bucket,
            "Key": key,
            "Body": spool,
        }
        if content_type:
            put_kwargs["ContentType"] = content_type
        if metadata:
            put_kwargs["Metadata"] = metadata
        destination_client.put_object(**put_kwargs)
    finally:
        spool.close()

    destination_sha256 = verify_destination(
        destination_client,
        bucket=dest_bucket,
        key=key,
        expected_size=source_size,
        expected_sha256=source_sha256,
        options=options,
    )
    return MigrationResult(
        key=key,
        status="copied",
        size=source_size,
        source_sha256=source_sha256,
        destination_sha256=destination_sha256,
    )


def append_manifest_result(path: Path, result: MigrationResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(result), sort_keys=True, separators=(",", ":")))
        handle.write("\n")


def migrate_bucket_objects(
    source_client: Any,
    destination_client: Any,
    *,
    source_bucket: str,
    dest_bucket: str,
    options: MigrationOptions,
) -> MigrationSummary:
    results: list[MigrationResult] = []
    for candidate in list_candidates(source_client, bucket=source_bucket, prefixes=options.prefixes):
        result = copy_candidate(
            source_client,
            destination_client,
            source_bucket=source_bucket,
            dest_bucket=dest_bucket,
            candidate=candidate,
            options=options,
        )
        results.append(result)
        if options.manifest_path is not None:
            append_manifest_result(options.manifest_path, result)
        print(f"{result.status}: {result.key} ({result.size} bytes)")
    return MigrationSummary(results=results)


def create_s3_client(
    *,
    endpoint_url: str,
    access_key: str,
    secret_key: str,
    region: str,
    session_token: str | None,
    verify_ssl: bool,
    path_style: bool,
    proxy_url: str | None,
) -> Any:
    import boto3
    from botocore.config import Config

    config_kwargs: dict[str, Any] = {
        "region_name": region,
        "s3": {"addressing_style": "path" if path_style else "auto"},
    }
    if proxy_url:
        config_kwargs["proxies"] = {"http": proxy_url, "https": proxy_url}
    config = Config(**config_kwargs)
    kwargs: dict[str, Any] = {
        "service_name": "s3",
        "endpoint_url": endpoint_url,
        "aws_access_key_id": access_key,
        "aws_secret_access_key": secret_key,
        "region_name": region,
        "verify": verify_ssl,
        "config": config,
    }
    if session_token:
        kwargs["aws_session_token"] = session_token
    return boto3.client(**kwargs)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy SkillHub MinIO/S3 objects from one bucket/account to another while preserving object keys.",
    )
    parser.add_argument("--source-endpoint", required=True)
    parser.add_argument("--source-bucket", required=True)
    parser.add_argument("--source-access-key", required=True)
    parser.add_argument("--source-secret-key", required=True)
    parser.add_argument("--source-region", default=DEFAULT_REGION)
    parser.add_argument("--source-session-token")
    parser.add_argument("--source-no-verify-ssl", action="store_true")
    parser.add_argument("--source-proxy-url", help="Optional HTTP proxy URL used only by the source S3 client.")
    parser.add_argument("--dest-endpoint", required=True)
    parser.add_argument("--dest-bucket", required=True)
    parser.add_argument("--dest-access-key", required=True)
    parser.add_argument("--dest-secret-key", required=True)
    parser.add_argument("--dest-region", default=DEFAULT_REGION)
    parser.add_argument("--dest-session-token")
    parser.add_argument("--dest-no-verify-ssl", action="store_true")
    parser.add_argument("--dest-proxy-url", help="Optional HTTP proxy URL used only by the destination S3 client.")
    parser.add_argument(
        "--prefix",
        action="append",
        help="Object key prefix to copy. Repeatable. Defaults to skills/ and packages/.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite-existing", action="store_true")
    parser.add_argument("--verify-read-back", action="store_true")
    parser.add_argument("--verify-existing", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--chunk-size-mib", type=int, default=8)
    parser.add_argument("--spool-max-size-mib", type=int, default=64)
    parser.add_argument("--no-path-style", action="store_true")
    return parser.parse_args(argv)


def options_from_args(args: argparse.Namespace) -> MigrationOptions:
    chunk_size = args.chunk_size_mib * 1024 * 1024
    spool_max_size = args.spool_max_size_mib * 1024 * 1024
    if chunk_size <= 0:
        raise MigrationError("--chunk-size-mib must be greater than 0")
    if spool_max_size <= 0:
        raise MigrationError("--spool-max-size-mib must be greater than 0")
    return MigrationOptions(
        prefixes=tuple(normalize_prefix(prefix) for prefix in (args.prefix or DEFAULT_PREFIXES)),
        dry_run=args.dry_run,
        overwrite_existing=args.overwrite_existing,
        verify_read_back=args.verify_read_back,
        verify_existing=args.verify_existing,
        chunk_size=chunk_size,
        spool_max_size=spool_max_size,
        manifest_path=args.manifest,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    options = options_from_args(args)
    source_client = create_s3_client(
        endpoint_url=args.source_endpoint,
        access_key=args.source_access_key,
        secret_key=args.source_secret_key,
        region=args.source_region,
        session_token=args.source_session_token,
        verify_ssl=not args.source_no_verify_ssl,
        path_style=not args.no_path_style,
        proxy_url=args.source_proxy_url,
    )
    destination_client = create_s3_client(
        endpoint_url=args.dest_endpoint,
        access_key=args.dest_access_key,
        secret_key=args.dest_secret_key,
        region=args.dest_region,
        session_token=args.dest_session_token,
        verify_ssl=not args.dest_no_verify_ssl,
        path_style=not args.no_path_style,
        proxy_url=args.dest_proxy_url,
    )

    summary = migrate_bucket_objects(
        source_client,
        destination_client,
        source_bucket=args.source_bucket,
        dest_bucket=args.dest_bucket,
        options=options,
    )
    print(json.dumps({"planned": summary.planned, "by_status": summary.results_by_status}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MigrationError as exc:
        print(f"migration failed: {exc}")
        raise SystemExit(1) from exc

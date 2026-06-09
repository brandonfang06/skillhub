from dataclasses import dataclass
import os
from pathlib import Path
import socket

DEFAULT_DATABASE_URL = "postgresql+asyncpg://skillhub:skillhub_dev@localhost:5432/skillhub"
DEFAULT_STORAGE_BASE_PATH = str(Path(__file__).resolve().parents[3] / ".dev" / "java-storage")
DEFAULT_REDIS_URL = "redis://localhost:6379"
DEFAULT_SCAN_STREAM_KEY = "skillhub:scan:requests"
DEFAULT_SCANNER_BASE_URL = "http://localhost:8000"
DEFAULT_SCANNER_HEALTH_PATH = "/health"
DEFAULT_SCANNER_SCAN_PATH = "/scan-upload"
DEFAULT_SCANNER_CONNECT_TIMEOUT_MS = 5000
DEFAULT_SCANNER_READ_TIMEOUT_MS = 300000
DEFAULT_SCAN_CONSUMER_GROUP_NAME = "skillhub-scan-workers"
DEFAULT_SCAN_CONSUMER_READ_COUNT = 10
DEFAULT_SCAN_CONSUMER_BLOCK_MS = 2000
DEFAULT_SCAN_CONSUMER_RECLAIM_MIN_IDLE_MS = 120000
DEFAULT_SCAN_CONSUMER_RECLAIM_COUNT = 20


@dataclass(frozen=True)
class Settings:
    database_url: str
    storage_base_path: str
    security_scanner_enabled: bool
    security_scanner_mode: str
    redis_url: str
    scan_stream_key: str
    scanner_base_url: str
    scanner_health_path: str
    scanner_scan_path: str
    scanner_connect_timeout_ms: int
    scanner_read_timeout_ms: int
    scan_consumer_enabled: bool
    scan_consumer_group_name: str
    scan_consumer_name: str
    scan_consumer_read_count: int
    scan_consumer_block_ms: int
    scan_consumer_reclaim_min_idle_ms: int
    scan_consumer_reclaim_count: int


def parse_bool(value: str | None) -> bool:
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}


def parse_int(value: str | None, default: int) -> int:
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def default_scan_consumer_name() -> str:
    return f"scanner-python-{socket.gethostname()}"


def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("SKILLHUB_DATABASE_URL", DEFAULT_DATABASE_URL),
        storage_base_path=os.getenv("SKILLHUB_STORAGE_BASE_PATH", DEFAULT_STORAGE_BASE_PATH),
        security_scanner_enabled=parse_bool(os.getenv("SKILLHUB_SECURITY_SCANNER_ENABLED")),
        security_scanner_mode=os.getenv("SKILLHUB_SECURITY_SCANNER_MODE", "local"),
        redis_url=os.getenv("SKILLHUB_REDIS_URL", DEFAULT_REDIS_URL),
        scan_stream_key=os.getenv("SKILLHUB_SCAN_STREAM_KEY", DEFAULT_SCAN_STREAM_KEY),
        scanner_base_url=os.getenv("SKILLHUB_SECURITY_SCANNER_BASE_URL", DEFAULT_SCANNER_BASE_URL),
        scanner_health_path=os.getenv("SKILLHUB_SECURITY_SCANNER_HEALTH_PATH", DEFAULT_SCANNER_HEALTH_PATH),
        scanner_scan_path=os.getenv("SKILLHUB_SECURITY_SCANNER_SCAN_PATH", DEFAULT_SCANNER_SCAN_PATH),
        scanner_connect_timeout_ms=parse_int(
            os.getenv("SKILLHUB_SECURITY_SCANNER_CONNECT_TIMEOUT_MS"),
            DEFAULT_SCANNER_CONNECT_TIMEOUT_MS,
        ),
        scanner_read_timeout_ms=parse_int(
            os.getenv("SKILLHUB_SECURITY_SCANNER_READ_TIMEOUT_MS"),
            DEFAULT_SCANNER_READ_TIMEOUT_MS,
        ),
        scan_consumer_enabled=parse_bool(os.getenv("SKILLHUB_SCAN_CONSUMER_ENABLED")),
        scan_consumer_group_name=os.getenv("SKILLHUB_SCAN_CONSUMER_GROUP_NAME", DEFAULT_SCAN_CONSUMER_GROUP_NAME),
        scan_consumer_name=os.getenv("SKILLHUB_SCAN_CONSUMER_NAME", default_scan_consumer_name()),
        scan_consumer_read_count=parse_int(
            os.getenv("SKILLHUB_SCAN_CONSUMER_READ_COUNT"),
            DEFAULT_SCAN_CONSUMER_READ_COUNT,
        ),
        scan_consumer_block_ms=parse_int(
            os.getenv("SKILLHUB_SCAN_CONSUMER_BLOCK_MS"),
            DEFAULT_SCAN_CONSUMER_BLOCK_MS,
        ),
        scan_consumer_reclaim_min_idle_ms=parse_int(
            os.getenv("SKILLHUB_SCAN_CONSUMER_RECLAIM_MIN_IDLE_MS"),
            DEFAULT_SCAN_CONSUMER_RECLAIM_MIN_IDLE_MS,
        ),
        scan_consumer_reclaim_count=parse_int(
            os.getenv("SKILLHUB_SCAN_CONSUMER_RECLAIM_COUNT"),
            DEFAULT_SCAN_CONSUMER_RECLAIM_COUNT,
        ),
    )

from dataclasses import dataclass
import os
from pathlib import Path

DEFAULT_DATABASE_URL = "postgresql+asyncpg://skillhub:skillhub_dev@localhost:5432/skillhub"
DEFAULT_STORAGE_BASE_PATH = str(Path(__file__).resolve().parents[3] / ".dev" / "java-storage")
DEFAULT_REDIS_URL = "redis://localhost:6379"
DEFAULT_SCAN_STREAM_KEY = "skillhub:scan:requests"


@dataclass(frozen=True)
class Settings:
    database_url: str
    storage_base_path: str
    security_scanner_enabled: bool
    security_scanner_mode: str
    redis_url: str
    scan_stream_key: str


def parse_bool(value: str | None) -> bool:
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}


def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("SKILLHUB_DATABASE_URL", DEFAULT_DATABASE_URL),
        storage_base_path=os.getenv("SKILLHUB_STORAGE_BASE_PATH", DEFAULT_STORAGE_BASE_PATH),
        security_scanner_enabled=parse_bool(os.getenv("SKILLHUB_SECURITY_SCANNER_ENABLED")),
        security_scanner_mode=os.getenv("SKILLHUB_SECURITY_SCANNER_MODE", "local"),
        redis_url=os.getenv("SKILLHUB_REDIS_URL", DEFAULT_REDIS_URL),
        scan_stream_key=os.getenv("SKILLHUB_SCAN_STREAM_KEY", DEFAULT_SCAN_STREAM_KEY),
    )

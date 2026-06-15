from dataclasses import dataclass
import os
from pathlib import Path
import re
import socket
from urllib.parse import quote, urlsplit, urlunsplit

DEFAULT_DATABASE_URL = "postgresql+asyncpg://skillhub:skillhub_dev@localhost:5432/skillhub"
DEFAULT_STORAGE_BASE_PATH = str(Path(__file__).resolve().parents[3] / ".dev" / "java-storage")
DEFAULT_REDIS_URL = "redis://localhost:6379"
DEFAULT_SCAN_STREAM_KEY = "skillhub:scan:requests"
DEFAULT_SCANNER_BASE_URL = "http://localhost:8000"
DEFAULT_SCANNER_HEALTH_PATH = "/health"
DEFAULT_SCANNER_SCAN_PATH = "/scan-upload"
DEFAULT_SCANNER_CONNECT_TIMEOUT_MS = 5000
DEFAULT_SCANNER_READ_TIMEOUT_MS = 300000
DEFAULT_STORAGE_PROVIDER = "local"
DEFAULT_STORAGE_S3_REGION = "us-east-1"
DEFAULT_STORAGE_S3_PRESIGN_EXPIRY_SECONDS = 600
DEFAULT_STORAGE_S3_MAX_CONNECTIONS = 50
DEFAULT_STORAGE_S3_CONNECTION_ACQUISITION_TIMEOUT_SECONDS = 10
DEFAULT_STORAGE_S3_API_CALL_ATTEMPT_TIMEOUT_SECONDS = 30
DEFAULT_STORAGE_S3_API_CALL_TIMEOUT_SECONDS = 60
DEFAULT_SCAN_CONSUMER_GROUP_NAME = "skillhub-scan-workers"
DEFAULT_SCAN_CONSUMER_READ_COUNT = 10
DEFAULT_SCAN_CONSUMER_BLOCK_MS = 2000
DEFAULT_SCAN_CONSUMER_RECLAIM_MIN_IDLE_MS = 120000
DEFAULT_SCAN_CONSUMER_RECLAIM_COUNT = 20


@dataclass(frozen=True)
class Settings:
    database_url: str
    storage_provider: str
    storage_base_path: str
    storage_s3_endpoint: str
    storage_s3_proxy_endpoint: str
    storage_s3_public_endpoint: str
    storage_s3_bucket: str
    storage_s3_access_key: str
    storage_s3_secret_key: str
    storage_s3_region: str
    storage_s3_force_path_style: bool
    storage_s3_disable_chunked_encoding: bool
    storage_s3_auto_create_bucket: bool
    storage_s3_presign_expiry_seconds: int
    storage_s3_max_connections: int
    storage_s3_connection_acquisition_timeout_seconds: int
    storage_s3_api_call_attempt_timeout_seconds: int
    storage_s3_api_call_timeout_seconds: int
    security_scanner_enabled: bool
    security_scanner_mode: str
    redis_url: str
    scan_stream_key: str
    scanner_base_url: str
    scanner_health_path: str
    scanner_scan_path: str
    scanner_connect_timeout_ms: int
    scanner_read_timeout_ms: int
    scanner_use_behavioral: bool
    scanner_use_llm: bool
    scanner_llm_provider: str
    scanner_enable_meta: bool
    scanner_use_aidefense: bool
    scanner_aidefense_api_key: str
    scanner_use_virustotal: bool
    scanner_use_trigger: bool
    scan_consumer_enabled: bool
    scan_consumer_group_name: str
    scan_consumer_name: str
    scan_consumer_read_count: int
    scan_consumer_block_ms: int
    scan_consumer_reclaim_min_idle_ms: int
    scan_consumer_reclaim_count: int

    @property
    def storage_s3_effective_endpoint(self) -> str:
        return self.storage_s3_proxy_endpoint or self.storage_s3_endpoint


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_int(value: str | None, default: int) -> int:
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def parse_duration_seconds(value: str | None, default: int) -> int:
    if value is None or value.strip() == "":
        return default
    normalized = value.strip().upper()
    if normalized.isdecimal():
        return int(normalized)
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", normalized)
    if match is None:
        return default
    total = int(match.group(1) or "0") * 3600
    total += int(match.group(2) or "0") * 60
    total += int(match.group(3) or "0")
    return total if total > 0 else default


def default_scan_consumer_name() -> str:
    return f"scanner-python-{socket.gethostname()}"


def first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip() != "":
            return value
    return default


def resolve_database_url() -> str:
    explicit = os.getenv("SKILLHUB_DATABASE_URL")
    if explicit is not None and explicit.strip() != "":
        return explicit

    spring_url = os.getenv("SPRING_DATASOURCE_URL")
    if spring_url is not None and spring_url.strip() != "":
        return spring_jdbc_postgres_to_asyncpg(
            spring_url,
            username=os.getenv("SPRING_DATASOURCE_USERNAME", ""),
            password=os.getenv("SPRING_DATASOURCE_PASSWORD", ""),
        )
    return DEFAULT_DATABASE_URL


def spring_jdbc_postgres_to_asyncpg(jdbc_url: str, *, username: str, password: str) -> str:
    normalized = jdbc_url.strip()
    if normalized.startswith("jdbc:"):
        normalized = normalized[len("jdbc:") :]
    parsed = urlsplit(normalized)
    if parsed.scheme != "postgresql":
        return jdbc_url

    netloc = parsed.netloc
    if parsed.username is None and username.strip() != "":
        auth = quote(username.strip(), safe="")
        if password != "":
            auth = f"{auth}:{quote(password, safe='')}"
        netloc = f"{auth}@{parsed.netloc}"
    return urlunsplit(("postgresql+asyncpg", netloc, parsed.path, parsed.query, parsed.fragment))


def resolve_redis_url() -> str:
    explicit = os.getenv("SKILLHUB_REDIS_URL")
    if explicit is not None and explicit.strip() != "":
        return explicit

    legacy_keys = (
        "SPRING_DATA_REDIS_HOST",
        "REDIS_HOST",
        "SPRING_DATA_REDIS_PORT",
        "REDIS_PORT",
        "SPRING_DATA_REDIS_PASSWORD",
        "REDIS_PASSWORD",
        "SPRING_DATA_REDIS_DATABASE",
        "REDIS_DATABASE",
    )
    if not any(os.getenv(key) not in {None, ""} for key in legacy_keys):
        return DEFAULT_REDIS_URL

    host = os.getenv("SPRING_DATA_REDIS_HOST") or os.getenv("REDIS_HOST") or "localhost"
    port = parse_int(os.getenv("SPRING_DATA_REDIS_PORT") or os.getenv("REDIS_PORT"), 6379)
    password = os.getenv("SPRING_DATA_REDIS_PASSWORD") or os.getenv("REDIS_PASSWORD") or ""
    database = parse_int(os.getenv("SPRING_DATA_REDIS_DATABASE") or os.getenv("REDIS_DATABASE"), 0)
    auth = f":{quote(password, safe='')}@" if password else ""
    return f"redis://{auth}{host}:{port}/{database}"


def get_settings() -> Settings:
    return Settings(
        database_url=resolve_database_url(),
        storage_provider=os.getenv("SKILLHUB_STORAGE_PROVIDER", DEFAULT_STORAGE_PROVIDER).strip().lower(),
        storage_base_path=os.getenv("SKILLHUB_STORAGE_BASE_PATH", DEFAULT_STORAGE_BASE_PATH),
        storage_s3_endpoint=os.getenv("SKILLHUB_STORAGE_S3_ENDPOINT", ""),
        storage_s3_proxy_endpoint=os.getenv("SKILLHUB_STORAGE_S3_PROXY_ENDPOINT", ""),
        storage_s3_public_endpoint=os.getenv("SKILLHUB_STORAGE_S3_PUBLIC_ENDPOINT", ""),
        storage_s3_bucket=os.getenv("SKILLHUB_STORAGE_S3_BUCKET", "skillhub-packages"),
        storage_s3_access_key=os.getenv("SKILLHUB_STORAGE_S3_ACCESS_KEY", ""),
        storage_s3_secret_key=os.getenv("SKILLHUB_STORAGE_S3_SECRET_KEY", ""),
        storage_s3_region=os.getenv("SKILLHUB_STORAGE_S3_REGION", DEFAULT_STORAGE_S3_REGION),
        storage_s3_force_path_style=parse_bool(os.getenv("SKILLHUB_STORAGE_S3_FORCE_PATH_STYLE")),
        storage_s3_disable_chunked_encoding=parse_bool(os.getenv("SKILLHUB_STORAGE_S3_DISABLE_CHUNKED_ENCODING")),
        storage_s3_auto_create_bucket=parse_bool(os.getenv("SKILLHUB_STORAGE_S3_AUTO_CREATE_BUCKET")),
        storage_s3_presign_expiry_seconds=parse_duration_seconds(
            os.getenv("SKILLHUB_STORAGE_S3_PRESIGN_EXPIRY"),
            DEFAULT_STORAGE_S3_PRESIGN_EXPIRY_SECONDS,
        ),
        storage_s3_max_connections=parse_int(
            os.getenv("SKILLHUB_STORAGE_S3_MAX_CONNECTIONS"),
            DEFAULT_STORAGE_S3_MAX_CONNECTIONS,
        ),
        storage_s3_connection_acquisition_timeout_seconds=parse_duration_seconds(
            os.getenv("SKILLHUB_STORAGE_S3_CONNECTION_ACQUISITION_TIMEOUT"),
            DEFAULT_STORAGE_S3_CONNECTION_ACQUISITION_TIMEOUT_SECONDS,
        ),
        storage_s3_api_call_attempt_timeout_seconds=parse_duration_seconds(
            os.getenv("SKILLHUB_STORAGE_S3_API_CALL_ATTEMPT_TIMEOUT"),
            DEFAULT_STORAGE_S3_API_CALL_ATTEMPT_TIMEOUT_SECONDS,
        ),
        storage_s3_api_call_timeout_seconds=parse_duration_seconds(
            os.getenv("SKILLHUB_STORAGE_S3_API_CALL_TIMEOUT"),
            DEFAULT_STORAGE_S3_API_CALL_TIMEOUT_SECONDS,
        ),
        security_scanner_enabled=parse_bool(os.getenv("SKILLHUB_SECURITY_SCANNER_ENABLED")),
        security_scanner_mode=os.getenv("SKILLHUB_SECURITY_SCANNER_MODE", "local"),
        redis_url=resolve_redis_url(),
        scan_stream_key=os.getenv("SKILLHUB_SCAN_STREAM_KEY", DEFAULT_SCAN_STREAM_KEY),
        scanner_base_url=first_env(
            "SKILLHUB_SECURITY_SCANNER_BASE_URL",
            "SKILLHUB_SECURITY_SCANNER_URL",
            default=DEFAULT_SCANNER_BASE_URL,
        ),
        scanner_health_path=os.getenv("SKILLHUB_SECURITY_SCANNER_HEALTH_PATH", DEFAULT_SCANNER_HEALTH_PATH),
        scanner_scan_path=os.getenv("SKILLHUB_SECURITY_SCANNER_SCAN_PATH", DEFAULT_SCANNER_SCAN_PATH),
        scanner_connect_timeout_ms=parse_int(
            first_env("SKILLHUB_SECURITY_SCANNER_CONNECT_TIMEOUT_MS", "SKILLHUB_SECURITY_SCANNER_CONNECT_TIMEOUT"),
            DEFAULT_SCANNER_CONNECT_TIMEOUT_MS,
        ),
        scanner_read_timeout_ms=parse_int(
            first_env("SKILLHUB_SECURITY_SCANNER_READ_TIMEOUT_MS", "SKILLHUB_SECURITY_SCANNER_READ_TIMEOUT"),
            DEFAULT_SCANNER_READ_TIMEOUT_MS,
        ),
        scanner_use_behavioral=parse_bool(os.getenv("SKILLHUB_SCANNER_USE_BEHAVIORAL"), True),
        scanner_use_llm=parse_bool(os.getenv("SKILLHUB_SCANNER_USE_LLM")),
        scanner_llm_provider=os.getenv("SKILLHUB_SCANNER_LLM_PROVIDER", "anthropic"),
        scanner_enable_meta=parse_bool(os.getenv("SKILLHUB_SCANNER_USE_META")),
        scanner_use_aidefense=parse_bool(os.getenv("SKILLHUB_SCANNER_USE_AI_DEFENSE")),
        scanner_aidefense_api_key=os.getenv("SKILLHUB_SCANNER_AI_DEFENSE_API_KEY", ""),
        scanner_use_virustotal=parse_bool(os.getenv("SKILLHUB_SCANNER_USE_VIRUSTOTAL")),
        scanner_use_trigger=parse_bool(os.getenv("SKILLHUB_SCANNER_USE_TRIGGER")),
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

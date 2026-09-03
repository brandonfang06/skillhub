from dataclasses import dataclass
import logging
import os
from pathlib import Path
import re
import socket
from urllib.parse import quote, urlsplit, urlunsplit

from app.core.public_url import resolve_absolute_http_url, to_public_url, validate_deployment_url_contract

DEFAULT_DATABASE_URL = "postgresql+asyncpg://skillhub:skillhub_dev@localhost:5432/skillhub"
DEFAULT_STORAGE_BASE_PATH = str(Path(__file__).resolve().parents[3] / ".dev" / "java-storage")
DEFAULT_REDIS_URL = "redis://localhost:6379"
DEFAULT_SCAN_STREAM_KEY = "skillhub:scan:requests"
DEFAULT_SCANNER_BASE_URL = "http://localhost:8000"
DEFAULT_SCANNER_HEALTH_PATH = "/health"
DEFAULT_SCANNER_MODE = "upload"
DEFAULT_SCANNER_SCAN_PATH = "/scan-upload"
DEFAULT_SCANNER_CONNECT_TIMEOUT_MS = 5000
DEFAULT_SCANNER_READ_TIMEOUT_MS = 300000
DEFAULT_STORAGE_PROVIDER = "local"
DEFAULT_STORAGE_S3_REGION = "us-east-1"
DEFAULT_STORAGE_S3_MAX_CONNECTIONS = 50
DEFAULT_STORAGE_S3_CONNECTION_ACQUISITION_TIMEOUT_SECONDS = 10
DEFAULT_STORAGE_S3_API_CALL_ATTEMPT_TIMEOUT_SECONDS = 30
DEFAULT_STORAGE_S3_API_CALL_TIMEOUT_SECONDS = 60
DEFAULT_SCAN_CONSUMER_GROUP_NAME = "skillhub-scan-workers"
DEFAULT_SCAN_CONSUMER_READ_COUNT = 10
DEFAULT_SCAN_CONSUMER_BLOCK_MS = 2000
DEFAULT_SCAN_CONSUMER_RECLAIM_MIN_IDLE_MS = 120000
DEFAULT_SCAN_CONSUMER_RECLAIM_COUNT = 20
DEFAULT_SCAN_OUTBOX_BATCH_SIZE = 50
DEFAULT_SCAN_OUTBOX_MAX_ATTEMPTS = 10
DEFAULT_SCAN_OUTBOX_LEASE_SECONDS = 120
DEFAULT_SCAN_OUTBOX_MAX_BACKOFF_SECONDS = 300
DEFAULT_SCAN_OUTBOX_DISPATCH_INTERVAL_MS = 5000
DEFAULT_SCAN_OUTBOX_SENT_RETENTION_DAYS = 7
DEFAULT_SCAN_OUTBOX_CLEANUP_INTERVAL_SECONDS = 86400
DEFAULT_DOWNLOAD_ANALYTICS_RETENTION_MONTHS = 12
RATE_LIMIT_CATEGORIES = (
    "search",
    "resolve",
    "download",
    "skills",
    "stars",
    "publish",
    "whoami",
    "auth-session-bootstrap",
    "auth-direct-login",
    "auth-password-reset-request",
    "auth-password-reset-confirm",
    "auth-register",
    "auth-local-login",
    "auth-change-password",
)
log = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class RateLimitCategoryOverride:
    authenticated: int | None = None
    anonymous: int | None = None
    window_seconds: int | None = None


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
    storage_s3_max_connections: int
    storage_s3_connection_acquisition_timeout_seconds: int
    storage_s3_api_call_attempt_timeout_seconds: int
    storage_s3_api_call_timeout_seconds: int
    publish_allowed_file_extensions: set[str] | None
    download_analytics_retention_months: int
    local_registration_enabled: bool
    global_namespace_auto_join_enabled: bool
    device_auth_verification_uri: str
    security_scanner_enabled: bool
    security_scanner_mode: str
    redis_url: str
    redis_mode: str
    redis_sentinel_master: str
    redis_sentinel_nodes: list[str]
    redis_sentinel_username: str
    redis_sentinel_password: str
    redis_username: str
    redis_password: str
    redis_database: int
    redis_ssl_enabled: bool
    redis_connect_timeout_seconds: int
    redis_timeout_seconds: int
    rate_limit_enabled: bool
    rate_limit_overrides: dict[str, RateLimitCategoryOverride]
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
    scan_outbox_batch_size: int
    scan_outbox_max_attempts: int
    scan_outbox_lease_seconds: int
    scan_outbox_max_backoff_seconds: int
    scan_outbox_dispatch_interval_ms: int
    scan_outbox_sent_retention_days: int
    scan_outbox_cleanup_interval_seconds: int
    playground_token_secret: str
    playground_token_ttl_seconds: int
    playground_token_issuer: str
    playground_token_audience: str
    playground_context_max_bytes: int

    @property
    def storage_s3_effective_endpoint(self) -> str:
        return self.storage_s3_proxy_endpoint or self.storage_s3_endpoint


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def global_namespace_auto_join_enabled() -> bool:
    return parse_bool(os.getenv("SKILLHUB_GLOBAL_NAMESPACE_AUTO_JOIN_ENABLED"))


def parse_int(value: str | None, default: int) -> int:
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def parse_optional_bounded_int(
    value: str | None,
    *,
    minimum: int,
) -> int | None:
    if value is None or value.strip() == "":
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed >= minimum else None


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


def split_csv(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_extension_set(value: str | None) -> set[str] | None:
    extensions = set()
    for item in split_csv(value):
        normalized = item.lower()
        if not normalized.startswith("."):
            normalized = f".{normalized}"
        extensions.add(normalized)
    return extensions or None


def resolve_rate_limit_overrides() -> dict[str, RateLimitCategoryOverride]:
    overrides: dict[str, RateLimitCategoryOverride] = {}
    for category in RATE_LIMIT_CATEGORIES:
        env_category = category.replace("-", "_").upper()
        prefix = f"SKILLHUB_RATELIMIT_CATEGORIES_{env_category}_"
        override = RateLimitCategoryOverride(
            authenticated=parse_optional_bounded_int(
                os.getenv(f"{prefix}AUTHENTICATED"), minimum=0
            ),
            anonymous=parse_optional_bounded_int(
                os.getenv(f"{prefix}ANONYMOUS"), minimum=0
            ),
            window_seconds=parse_optional_bounded_int(
                os.getenv(f"{prefix}WINDOW_SECONDS"), minimum=1
            ),
        )
        if any(
            value is not None
            for value in (
                override.authenticated,
                override.anonymous,
                override.window_seconds,
            )
        ):
            overrides[category] = override
    return overrides


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
        "SPRING_DATA_REDIS_USERNAME",
        "REDIS_USERNAME",
        "SKILLHUB_REDIS_USERNAME",
        "SPRING_DATA_REDIS_PASSWORD",
        "REDIS_PASSWORD",
        "SPRING_DATA_REDIS_DATABASE",
        "REDIS_DATABASE",
        "SPRING_DATA_REDIS_SSL_ENABLED",
        "SKILLHUB_REDIS_SSL_ENABLED",
    )
    if not any(os.getenv(key) not in {None, ""} for key in legacy_keys):
        return DEFAULT_REDIS_URL

    host = os.getenv("SPRING_DATA_REDIS_HOST") or os.getenv("REDIS_HOST") or "localhost"
    port = parse_int(os.getenv("SPRING_DATA_REDIS_PORT") or os.getenv("REDIS_PORT"), 6379)
    username = redis_username()
    password = os.getenv("SPRING_DATA_REDIS_PASSWORD") or os.getenv("REDIS_PASSWORD") or ""
    database = parse_int(os.getenv("SPRING_DATA_REDIS_DATABASE") or os.getenv("REDIS_DATABASE"), 0)
    auth = ""
    if username:
        auth = quote(username, safe="")
        if password:
            auth = f"{auth}:{quote(password, safe='')}"
        auth = f"{auth}@"
    elif password:
        auth = f":{quote(password, safe='')}@"
    scheme = "rediss" if redis_ssl_enabled() else "redis"
    return f"{scheme}://{auth}{host}:{port}/{database}"


def resolve_redis_mode() -> str:
    explicit = os.getenv("SKILLHUB_REDIS_URL")
    if explicit is not None and explicit.strip() != "":
        return "single"
    if redis_sentinel_master() and redis_sentinel_nodes():
        return "sentinel"
    return "single"


def redis_sentinel_master() -> str:
    return first_env("SPRING_DATA_REDIS_SENTINEL_MASTER", "SKILLHUB_REDIS_SENTINEL_MASTER")


def redis_sentinel_nodes() -> list[str]:
    return split_csv(first_env("SPRING_DATA_REDIS_SENTINEL_NODES", "SKILLHUB_REDIS_SENTINEL_NODES"))


def redis_sentinel_username() -> str:
    return first_env("SPRING_DATA_REDIS_SENTINEL_USERNAME", "SKILLHUB_REDIS_SENTINEL_USERNAME")


def redis_sentinel_password() -> str:
    return first_env("SPRING_DATA_REDIS_SENTINEL_PASSWORD", "SKILLHUB_REDIS_SENTINEL_PASSWORD")


def redis_username() -> str:
    return first_env("SPRING_DATA_REDIS_USERNAME", "REDIS_USERNAME", "SKILLHUB_REDIS_USERNAME")


def redis_password() -> str:
    return first_env("SPRING_DATA_REDIS_PASSWORD", "REDIS_PASSWORD")


def redis_database() -> int:
    return parse_int(first_env("SPRING_DATA_REDIS_DATABASE", "REDIS_DATABASE"), 0)


def redis_ssl_enabled() -> bool:
    return parse_bool(first_env("SPRING_DATA_REDIS_SSL_ENABLED", "SKILLHUB_REDIS_SSL_ENABLED"))


def resolve_device_auth_verification_uri() -> str:
    for variable_name in ("SKILLHUB_DEVICE_AUTH_VERIFICATION_URI", "DEVICE_AUTH_VERIFICATION_URI"):
        value = os.getenv(variable_name)
        if value is not None and value.strip() != "":
            return resolve_absolute_http_url(value, variable_name)
    return to_public_url("/cli/auth")


def get_settings() -> Settings:
    validate_deployment_url_contract(
        session_cookie_secure=parse_bool(first_env("SKILLHUB_SESSION_COOKIE_SECURE", "SESSION_COOKIE_SECURE")),
    )
    settings = Settings(
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
        publish_allowed_file_extensions=parse_extension_set(os.getenv("SKILLHUB_PUBLISH_ALLOWED_FILE_EXTENSIONS")),
        download_analytics_retention_months=parse_int(
            os.getenv("SKILLHUB_DOWNLOAD_ANALYTICS_RETENTION_MONTHS"),
            DEFAULT_DOWNLOAD_ANALYTICS_RETENTION_MONTHS,
        ),
        local_registration_enabled=parse_bool(os.getenv("SKILLHUB_LOCAL_REGISTRATION_ENABLED"), True),
        global_namespace_auto_join_enabled=global_namespace_auto_join_enabled(),
        device_auth_verification_uri=resolve_device_auth_verification_uri(),
        security_scanner_enabled=parse_bool(os.getenv("SKILLHUB_SECURITY_SCANNER_ENABLED")),
        security_scanner_mode=os.getenv("SKILLHUB_SECURITY_SCANNER_MODE", DEFAULT_SCANNER_MODE),
        redis_url=resolve_redis_url(),
        redis_mode=resolve_redis_mode(),
        redis_sentinel_master=redis_sentinel_master() if resolve_redis_mode() == "sentinel" else "",
        redis_sentinel_nodes=redis_sentinel_nodes() if resolve_redis_mode() == "sentinel" else [],
        redis_sentinel_username=redis_sentinel_username(),
        redis_sentinel_password=redis_sentinel_password(),
        redis_username=redis_username(),
        redis_password=redis_password(),
        redis_database=redis_database(),
        redis_ssl_enabled=redis_ssl_enabled(),
        redis_connect_timeout_seconds=parse_duration_seconds(
            first_env("SPRING_DATA_REDIS_CONNECT_TIMEOUT", "SKILLHUB_REDIS_CONNECT_TIMEOUT"),
            5,
        ),
        redis_timeout_seconds=parse_duration_seconds(
            first_env("SPRING_DATA_REDIS_TIMEOUT", "SKILLHUB_REDIS_TIMEOUT"),
            5,
        ),
        rate_limit_enabled=parse_bool(os.getenv("SKILLHUB_RATELIMIT_ENABLED")),
        rate_limit_overrides=resolve_rate_limit_overrides(),
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
        scan_outbox_batch_size=parse_int(
            os.getenv("SKILLHUB_SECURITY_OUTBOX_BATCH_SIZE"),
            DEFAULT_SCAN_OUTBOX_BATCH_SIZE,
        ),
        scan_outbox_max_attempts=parse_int(
            os.getenv("SKILLHUB_SECURITY_OUTBOX_MAX_ATTEMPTS"),
            DEFAULT_SCAN_OUTBOX_MAX_ATTEMPTS,
        ),
        scan_outbox_lease_seconds=parse_duration_seconds(
            os.getenv("SKILLHUB_SECURITY_OUTBOX_LEASE"),
            DEFAULT_SCAN_OUTBOX_LEASE_SECONDS,
        ),
        scan_outbox_max_backoff_seconds=parse_duration_seconds(
            os.getenv("SKILLHUB_SECURITY_OUTBOX_MAX_BACKOFF"),
            DEFAULT_SCAN_OUTBOX_MAX_BACKOFF_SECONDS,
        ),
        scan_outbox_dispatch_interval_ms=parse_int(
            os.getenv("SKILLHUB_SECURITY_OUTBOX_DISPATCH_INTERVAL_MS"),
            DEFAULT_SCAN_OUTBOX_DISPATCH_INTERVAL_MS,
        ),
        scan_outbox_sent_retention_days=parse_int(
            os.getenv("SKILLHUB_SECURITY_OUTBOX_SENT_RETENTION_DAYS"),
            DEFAULT_SCAN_OUTBOX_SENT_RETENTION_DAYS,
        ),
        scan_outbox_cleanup_interval_seconds=parse_int(
            os.getenv("SKILLHUB_SECURITY_OUTBOX_CLEANUP_INTERVAL_SECONDS"),
            DEFAULT_SCAN_OUTBOX_CLEANUP_INTERVAL_SECONDS,
        ),
        playground_token_secret=os.getenv("SKILLHUB_PLAYGROUND_TOKEN_SECRET", ""),
        playground_token_ttl_seconds=parse_int(
            os.getenv("SKILLHUB_PLAYGROUND_TOKEN_TTL_SECONDS"),
            300,
        ),
        playground_token_issuer=os.getenv(
            "SKILLHUB_PLAYGROUND_TOKEN_ISSUER",
            "skillhub",
        ),
        playground_token_audience=os.getenv(
            "SKILLHUB_PLAYGROUND_TOKEN_AUDIENCE",
            "skill-playground-sidecar",
        ),
        playground_context_max_bytes=parse_int(
            os.getenv("SKILLHUB_PLAYGROUND_CONTEXT_MAX_BYTES"),
            120000,
        ),
    )
    warn_redis_configuration(settings)
    return settings


def warn_redis_configuration(settings: Settings) -> None:
    if (
        os.getenv("SKILLHUB_REDIS_URL") not in {None, ""}
        and (redis_sentinel_master() or redis_sentinel_nodes())
    ):
        log.warning("SKILLHUB_REDIS_URL is set, Redis Sentinel settings will be ignored")
    if settings.scan_consumer_block_ms >= settings.redis_timeout_seconds * 1000:
        log.warning(
            "SKILLHUB_SCAN_CONSUMER_BLOCK_MS should be lower than Redis socket timeout: "
            "block_ms=%s redis_timeout_seconds=%s",
            settings.scan_consumer_block_ms,
            settings.redis_timeout_seconds,
        )

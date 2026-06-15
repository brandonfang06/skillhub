from app.core.config import DEFAULT_DATABASE_URL, DEFAULT_STORAGE_BASE_PATH, get_settings


def test_default_database_url_matches_local_docker_compose(monkeypatch):
    monkeypatch.delenv("SKILLHUB_DATABASE_URL", raising=False)

    settings = get_settings()

    assert DEFAULT_DATABASE_URL == "postgresql+asyncpg://skillhub:skillhub_dev@localhost:5432/skillhub"
    assert settings.database_url == DEFAULT_DATABASE_URL
    assert settings.storage_provider == "local"
    assert settings.storage_base_path == DEFAULT_STORAGE_BASE_PATH


def test_database_url_can_be_overridden(monkeypatch):
    monkeypatch.setenv("SKILLHUB_DATABASE_URL", "postgresql+asyncpg://user:pass@example.test:5432/db")

    settings = get_settings()

    assert settings.database_url == "postgresql+asyncpg://user:pass@example.test:5432/db"


def test_database_url_can_be_built_from_spring_datasource_env(monkeypatch):
    monkeypatch.delenv("SKILLHUB_DATABASE_URL", raising=False)
    monkeypatch.setenv("SPRING_DATASOURCE_URL", "jdbc:postgresql://postgres.internal:5432/skillhub?sslmode=require")
    monkeypatch.setenv("SPRING_DATASOURCE_USERNAME", "skillhub")
    monkeypatch.setenv("SPRING_DATASOURCE_PASSWORD", "p@ss word")

    settings = get_settings()

    assert settings.database_url == (
        "postgresql+asyncpg://skillhub:p%40ss%20word@postgres.internal:5432/skillhub?sslmode=require"
    )


def test_database_url_prefers_python_env_over_spring_datasource(monkeypatch):
    monkeypatch.setenv("SKILLHUB_DATABASE_URL", "postgresql+asyncpg://python:secret@postgres.python:5432/skillhub")
    monkeypatch.setenv("SPRING_DATASOURCE_URL", "jdbc:postgresql://postgres.java:5432/skillhub")
    monkeypatch.setenv("SPRING_DATASOURCE_USERNAME", "java")
    monkeypatch.setenv("SPRING_DATASOURCE_PASSWORD", "secret")

    settings = get_settings()

    assert settings.database_url == "postgresql+asyncpg://python:secret@postgres.python:5432/skillhub"


def test_storage_base_path_can_be_overridden(monkeypatch):
    monkeypatch.setenv("SKILLHUB_STORAGE_BASE_PATH", "C:/tmp/skillhub-storage")

    settings = get_settings()

    assert settings.storage_base_path == "C:/tmp/skillhub-storage"


def test_s3_storage_settings_use_java_compatible_env_names(monkeypatch):
    monkeypatch.setenv("SKILLHUB_STORAGE_PROVIDER", "s3")
    monkeypatch.setenv("SKILLHUB_STORAGE_S3_ENDPOINT", "http://minio.internal:9000")
    monkeypatch.setenv("SKILLHUB_STORAGE_S3_PROXY_ENDPOINT", "http://minio-proxy.internal:9000")
    monkeypatch.setenv("SKILLHUB_STORAGE_S3_PUBLIC_ENDPOINT", "https://objects.example.test")
    monkeypatch.setenv("SKILLHUB_STORAGE_S3_BUCKET", "skillhub-packages")
    monkeypatch.setenv("SKILLHUB_STORAGE_S3_ACCESS_KEY", "skillhub")
    monkeypatch.setenv("SKILLHUB_STORAGE_S3_SECRET_KEY", "secret")
    monkeypatch.setenv("SKILLHUB_STORAGE_S3_REGION", "ap-northeast-1")
    monkeypatch.setenv("SKILLHUB_STORAGE_S3_FORCE_PATH_STYLE", "true")
    monkeypatch.setenv("SKILLHUB_STORAGE_S3_DISABLE_CHUNKED_ENCODING", "true")
    monkeypatch.setenv("SKILLHUB_STORAGE_S3_AUTO_CREATE_BUCKET", "false")
    monkeypatch.setenv("SKILLHUB_STORAGE_S3_PRESIGN_EXPIRY", "PT15M")
    monkeypatch.setenv("SKILLHUB_STORAGE_S3_MAX_CONNECTIONS", "64")
    monkeypatch.setenv("SKILLHUB_STORAGE_S3_CONNECTION_ACQUISITION_TIMEOUT", "PT5S")
    monkeypatch.setenv("SKILLHUB_STORAGE_S3_API_CALL_ATTEMPT_TIMEOUT", "PT20S")
    monkeypatch.setenv("SKILLHUB_STORAGE_S3_API_CALL_TIMEOUT", "PT1M")

    settings = get_settings()

    assert settings.storage_provider == "s3"
    assert settings.storage_s3_endpoint == "http://minio.internal:9000"
    assert settings.storage_s3_proxy_endpoint == "http://minio-proxy.internal:9000"
    assert settings.storage_s3_effective_endpoint == "http://minio-proxy.internal:9000"
    assert settings.storage_s3_public_endpoint == "https://objects.example.test"
    assert settings.storage_s3_bucket == "skillhub-packages"
    assert settings.storage_s3_access_key == "skillhub"
    assert settings.storage_s3_secret_key == "secret"
    assert settings.storage_s3_region == "ap-northeast-1"
    assert settings.storage_s3_force_path_style is True
    assert settings.storage_s3_disable_chunked_encoding is True
    assert settings.storage_s3_auto_create_bucket is False
    assert settings.storage_s3_presign_expiry_seconds == 900
    assert settings.storage_s3_max_connections == 64
    assert settings.storage_s3_connection_acquisition_timeout_seconds == 5
    assert settings.storage_s3_api_call_attempt_timeout_seconds == 20
    assert settings.storage_s3_api_call_timeout_seconds == 60


def test_scanner_handoff_settings_can_be_overridden(monkeypatch):
    monkeypatch.setenv("SKILLHUB_SECURITY_SCANNER_ENABLED", "true")
    monkeypatch.setenv("SKILLHUB_SECURITY_SCANNER_MODE", "upload")
    monkeypatch.setenv("SKILLHUB_REDIS_URL", "redis://redis.test:6380")
    monkeypatch.setenv("SKILLHUB_SCAN_STREAM_KEY", "custom:scan:requests")
    monkeypatch.setenv("SKILLHUB_SECURITY_SCANNER_BASE_URL", "http://scanner.test:8000")
    monkeypatch.setenv("SKILLHUB_SECURITY_SCANNER_HEALTH_PATH", "/ready")
    monkeypatch.setenv("SKILLHUB_SECURITY_SCANNER_SCAN_PATH", "/scan-upload-custom")
    monkeypatch.setenv("SKILLHUB_SECURITY_SCANNER_CONNECT_TIMEOUT_MS", "1234")
    monkeypatch.setenv("SKILLHUB_SECURITY_SCANNER_READ_TIMEOUT_MS", "5678")

    settings = get_settings()

    assert settings.security_scanner_enabled is True
    assert settings.security_scanner_mode == "upload"
    assert settings.redis_url == "redis://redis.test:6380"
    assert settings.scan_stream_key == "custom:scan:requests"
    assert settings.scanner_base_url == "http://scanner.test:8000"
    assert settings.scanner_health_path == "/ready"
    assert settings.scanner_scan_path == "/scan-upload-custom"
    assert settings.scanner_connect_timeout_ms == 1234
    assert settings.scanner_read_timeout_ms == 5678


def test_java_scanner_env_names_are_accepted(monkeypatch):
    monkeypatch.delenv("SKILLHUB_SECURITY_SCANNER_BASE_URL", raising=False)
    monkeypatch.delenv("SKILLHUB_SECURITY_SCANNER_CONNECT_TIMEOUT_MS", raising=False)
    monkeypatch.delenv("SKILLHUB_SECURITY_SCANNER_READ_TIMEOUT_MS", raising=False)
    monkeypatch.setenv("SKILLHUB_SECURITY_SCANNER_URL", "http://scanner.java:8000")
    monkeypatch.setenv("SKILLHUB_SECURITY_SCANNER_CONNECT_TIMEOUT", "4321")
    monkeypatch.setenv("SKILLHUB_SECURITY_SCANNER_READ_TIMEOUT", "8765")
    monkeypatch.setenv("SKILLHUB_SCANNER_USE_BEHAVIORAL", "false")
    monkeypatch.setenv("SKILLHUB_SCANNER_USE_LLM", "true")
    monkeypatch.setenv("SKILLHUB_SCANNER_LLM_PROVIDER", "openai")
    monkeypatch.setenv("SKILLHUB_SCANNER_USE_META", "true")
    monkeypatch.setenv("SKILLHUB_SCANNER_USE_AI_DEFENSE", "true")
    monkeypatch.setenv("SKILLHUB_SCANNER_AI_DEFENSE_API_KEY", "aidefense-secret")
    monkeypatch.setenv("SKILLHUB_SCANNER_USE_VIRUSTOTAL", "true")
    monkeypatch.setenv("SKILLHUB_SCANNER_USE_TRIGGER", "true")

    settings = get_settings()

    assert settings.scanner_base_url == "http://scanner.java:8000"
    assert settings.scanner_connect_timeout_ms == 4321
    assert settings.scanner_read_timeout_ms == 8765
    assert settings.scanner_use_behavioral is False
    assert settings.scanner_use_llm is True
    assert settings.scanner_llm_provider == "openai"
    assert settings.scanner_enable_meta is True
    assert settings.scanner_use_aidefense is True
    assert settings.scanner_aidefense_api_key == "aidefense-secret"
    assert settings.scanner_use_virustotal is True
    assert settings.scanner_use_trigger is True


def test_scanner_analyzer_defaults_match_java_baseline(monkeypatch):
    for name in [
        "SKILLHUB_SCANNER_USE_BEHAVIORAL",
        "SKILLHUB_SCANNER_USE_LLM",
        "SKILLHUB_SCANNER_LLM_PROVIDER",
        "SKILLHUB_SCANNER_USE_META",
        "SKILLHUB_SCANNER_USE_AI_DEFENSE",
        "SKILLHUB_SCANNER_AI_DEFENSE_API_KEY",
        "SKILLHUB_SCANNER_USE_VIRUSTOTAL",
        "SKILLHUB_SCANNER_USE_TRIGGER",
    ]:
        monkeypatch.delenv(name, raising=False)

    settings = get_settings()

    assert settings.scanner_use_behavioral is True
    assert settings.scanner_use_llm is False
    assert settings.scanner_llm_provider == "anthropic"
    assert settings.scanner_enable_meta is False
    assert settings.scanner_use_aidefense is False
    assert settings.scanner_aidefense_api_key == ""
    assert settings.scanner_use_virustotal is False
    assert settings.scanner_use_trigger is False


def test_redis_url_can_be_built_from_java_compatible_env_names(monkeypatch):
    monkeypatch.delenv("SKILLHUB_REDIS_URL", raising=False)
    monkeypatch.setenv("SPRING_DATA_REDIS_HOST", "redis.internal")
    monkeypatch.setenv("SPRING_DATA_REDIS_PORT", "6380")
    monkeypatch.setenv("SPRING_DATA_REDIS_PASSWORD", "redis secret")
    monkeypatch.setenv("SPRING_DATA_REDIS_DATABASE", "2")

    settings = get_settings()

    assert settings.redis_url == "redis://:redis%20secret@redis.internal:6380/2"


def test_redis_password_falls_back_to_redis_password_env(monkeypatch):
    monkeypatch.delenv("SKILLHUB_REDIS_URL", raising=False)
    monkeypatch.delenv("SPRING_DATA_REDIS_PASSWORD", raising=False)
    monkeypatch.setenv("REDIS_HOST", "redis.compat")
    monkeypatch.setenv("REDIS_PORT", "6379")
    monkeypatch.setenv("REDIS_PASSWORD", "compat-secret")

    settings = get_settings()

    assert settings.redis_url == "redis://:compat-secret@redis.compat:6379/0"


def test_scanner_timeout_settings_fallback_to_defaults(monkeypatch):
    monkeypatch.setenv("SKILLHUB_SECURITY_SCANNER_CONNECT_TIMEOUT_MS", "bad")
    monkeypatch.setenv("SKILLHUB_SECURITY_SCANNER_READ_TIMEOUT_MS", "")

    settings = get_settings()

    assert settings.scanner_connect_timeout_ms == 5000
    assert settings.scanner_read_timeout_ms == 300000

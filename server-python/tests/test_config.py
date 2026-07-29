import logging

from app.core.config import DEFAULT_DATABASE_URL, DEFAULT_STORAGE_BASE_PATH, Settings, get_settings


def test_default_database_url_matches_local_docker_compose(monkeypatch):
    monkeypatch.delenv("SKILLHUB_DATABASE_URL", raising=False)

    settings = get_settings()

    assert DEFAULT_DATABASE_URL == "postgresql+asyncpg://skillhub:skillhub_dev@localhost:5432/skillhub"
    assert settings.database_url == DEFAULT_DATABASE_URL
    assert settings.storage_provider == "local"
    assert settings.storage_base_path == DEFAULT_STORAGE_BASE_PATH


def test_playground_defaults_to_disabled_without_affecting_startup(monkeypatch):
    monkeypatch.delenv("SKILLHUB_PLAYGROUND_TOKEN_SECRET", raising=False)
    monkeypatch.delenv("SKILLHUB_PLAYGROUND_TOKEN_TTL_SECONDS", raising=False)
    monkeypatch.delenv("SKILLHUB_PLAYGROUND_CONTEXT_MAX_BYTES", raising=False)

    settings = get_settings()

    assert settings.playground_token_secret == ""
    assert settings.playground_token_ttl_seconds == 300
    assert settings.playground_context_max_bytes == 120000


def test_playground_settings_can_be_overridden(monkeypatch):
    monkeypatch.setenv("SKILLHUB_PLAYGROUND_TOKEN_SECRET", "test-secret")
    monkeypatch.setenv("SKILLHUB_PLAYGROUND_TOKEN_TTL_SECONDS", "120")
    monkeypatch.setenv("SKILLHUB_PLAYGROUND_TOKEN_ISSUER", "custom-skillhub")
    monkeypatch.setenv("SKILLHUB_PLAYGROUND_TOKEN_AUDIENCE", "custom-sidecar")
    monkeypatch.setenv("SKILLHUB_PLAYGROUND_CONTEXT_MAX_BYTES", "64000")

    settings = get_settings()

    assert settings.playground_token_secret == "test-secret"
    assert settings.playground_token_ttl_seconds == 120
    assert settings.playground_token_issuer == "custom-skillhub"
    assert settings.playground_token_audience == "custom-sidecar"
    assert settings.playground_context_max_bytes == 64000


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
    assert settings.storage_s3_max_connections == 64
    assert settings.storage_s3_connection_acquisition_timeout_seconds == 5
    assert settings.storage_s3_api_call_attempt_timeout_seconds == 20
    assert settings.storage_s3_api_call_timeout_seconds == 60


def test_s3_storage_settings_do_not_include_presigned_url_configuration(monkeypatch):
    monkeypatch.setenv("SKILLHUB_STORAGE_S3_PRESIGN_EXPIRY", "PT15M")

    settings = get_settings()

    assert "storage_s3_presign_expiry_seconds" not in Settings.__annotations__
    assert not hasattr(settings, "storage_s3_presign_expiry_seconds")


def test_publish_allowed_file_extensions_can_be_overridden(monkeypatch):
    monkeypatch.setenv("SKILLHUB_PUBLISH_ALLOWED_FILE_EXTENSIONS", ".md,.dot,dot")

    settings = get_settings()

    assert settings.publish_allowed_file_extensions == {".md", ".dot"}


def test_local_registration_can_be_disabled_for_organization_deployments(monkeypatch):
    monkeypatch.setenv("SKILLHUB_LOCAL_REGISTRATION_ENABLED", "false")

    settings = get_settings()

    assert settings.local_registration_enabled is False


def test_collection_features_default_to_disabled(monkeypatch):
    monkeypatch.delenv("SKILLHUB_COLLECTIONS_ENABLED", raising=False)
    monkeypatch.delenv("SKILLHUB_GITLAB_IMPORT_ENABLED", raising=False)

    settings = get_settings()

    assert settings.collections_enabled is False
    assert settings.gitlab_import_enabled is False


def test_gitlab_import_requires_collections(monkeypatch):
    monkeypatch.setenv("SKILLHUB_COLLECTIONS_ENABLED", "false")
    monkeypatch.setenv("SKILLHUB_GITLAB_IMPORT_ENABLED", "true")

    settings = get_settings()

    assert settings.collections_enabled is False
    assert settings.gitlab_import_enabled is False


def test_collection_features_can_be_enabled_independently(monkeypatch):
    monkeypatch.setenv("SKILLHUB_COLLECTIONS_ENABLED", "true")
    monkeypatch.setenv("SKILLHUB_GITLAB_IMPORT_ENABLED", "false")

    settings = get_settings()

    assert settings.collections_enabled is True
    assert settings.gitlab_import_enabled is False

    monkeypatch.setenv("SKILLHUB_GITLAB_IMPORT_ENABLED", "true")

    with_import = get_settings()

    assert with_import.collections_enabled is True
    assert with_import.gitlab_import_enabled is True


def test_gitlab_import_settings_are_bounded_and_token_is_not_represented(monkeypatch):
    monkeypatch.setenv("SKILLHUB_COLLECTIONS_ENABLED", "true")
    monkeypatch.setenv("SKILLHUB_GITLAB_IMPORT_ENABLED", "true")
    monkeypatch.setenv("SKILLHUB_GITLAB_BASE_URL", "https://gitlab.internal.example/")
    monkeypatch.setenv("SKILLHUB_GITLAB_ALLOWED_GROUPS", "oss-mirrors,approved/tools")
    monkeypatch.setenv("SKILLHUB_GITLAB_TOKEN", "top-secret")
    monkeypatch.setenv("SKILLHUB_GITLAB_CA_BUNDLE_PATH", "C:/certs/internal-ca.pem")
    monkeypatch.setenv("SKILLHUB_GITLAB_CONNECT_TIMEOUT_MS", "2500")
    monkeypatch.setenv("SKILLHUB_GITLAB_READ_TIMEOUT_MS", "45000")
    monkeypatch.setenv("SKILLHUB_GITLAB_ARCHIVE_MAX_BYTES", "2048")
    monkeypatch.setenv("SKILLHUB_GITLAB_ARCHIVE_MAX_FILES", "12")
    monkeypatch.setenv("SKILLHUB_GITLAB_ARCHIVE_MAX_SINGLE_FILE_BYTES", "4096")
    monkeypatch.setenv("SKILLHUB_GITLAB_ARCHIVE_MAX_EXPANDED_BYTES", "16384")
    monkeypatch.setenv("SKILLHUB_GITLAB_IMPORT_MAX_CANDIDATES", "7")

    settings = get_settings()

    assert settings.gitlab_base_url == "https://gitlab.internal.example"
    assert settings.gitlab_allowed_groups == ["oss-mirrors", "approved/tools"]
    assert settings.gitlab_token == "top-secret"
    assert settings.gitlab_ca_bundle_path == "C:/certs/internal-ca.pem"
    assert settings.gitlab_connect_timeout_ms == 2500
    assert settings.gitlab_read_timeout_ms == 45000
    assert settings.gitlab_archive_max_bytes == 2048
    assert settings.gitlab_archive_max_files == 12
    assert settings.gitlab_archive_max_single_file_bytes == 4096
    assert settings.gitlab_archive_max_expanded_bytes == 16384
    assert settings.gitlab_import_max_candidates == 7
    assert "top-secret" not in repr(settings)


def test_gitlab_operation_limits_have_safe_defaults_and_reject_non_positive_overrides(
    monkeypatch,
):
    names = (
        "SKILLHUB_GITLAB_ARCHIVE_MAX_BYTES",
        "SKILLHUB_GITLAB_ARCHIVE_MAX_FILES",
        "SKILLHUB_GITLAB_ARCHIVE_MAX_SINGLE_FILE_BYTES",
        "SKILLHUB_GITLAB_ARCHIVE_MAX_EXPANDED_BYTES",
        "SKILLHUB_GITLAB_IMPORT_MAX_CANDIDATES",
    )
    for name in names:
        monkeypatch.delenv(name, raising=False)

    defaults = get_settings()

    assert defaults.gitlab_archive_max_bytes == 50 * 1024 * 1024
    assert defaults.gitlab_archive_max_files == 500
    assert defaults.gitlab_archive_max_single_file_bytes == 5 * 1024 * 1024
    assert defaults.gitlab_archive_max_expanded_bytes == 50 * 1024 * 1024
    assert defaults.gitlab_import_max_candidates == 100

    for name in names:
        monkeypatch.setenv(name, "0")

    bounded = get_settings()

    assert bounded.gitlab_archive_max_bytes == 50 * 1024 * 1024
    assert bounded.gitlab_archive_max_files == 500
    assert bounded.gitlab_archive_max_single_file_bytes == 5 * 1024 * 1024
    assert bounded.gitlab_archive_max_expanded_bytes == 50 * 1024 * 1024
    assert bounded.gitlab_import_max_candidates == 100


def test_download_analytics_retention_defaults_to_twelve_months(monkeypatch):
    monkeypatch.delenv("SKILLHUB_DOWNLOAD_ANALYTICS_RETENTION_MONTHS", raising=False)

    settings = get_settings()

    assert settings.download_analytics_retention_months == 12


def test_download_analytics_retention_can_be_overridden_or_disabled(monkeypatch):
    monkeypatch.setenv("SKILLHUB_DOWNLOAD_ANALYTICS_RETENTION_MONTHS", "18")

    settings = get_settings()

    assert settings.download_analytics_retention_months == 18

    monkeypatch.setenv("SKILLHUB_DOWNLOAD_ANALYTICS_RETENTION_MONTHS", "0")

    disabled = get_settings()

    assert disabled.download_analytics_retention_months == 0


def test_download_authentication_cannot_be_disabled_by_environment(monkeypatch):
    monkeypatch.setenv("SKILLHUB_DOWNLOAD_REQUIRE_AUTH", "false")

    settings = get_settings()

    assert "download_require_auth" not in Settings.__annotations__
    assert not hasattr(settings, "download_require_auth")


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


def test_scanner_handoff_defaults_to_upload_mode(monkeypatch):
    monkeypatch.delenv("SKILLHUB_SECURITY_SCANNER_MODE", raising=False)
    monkeypatch.delenv("SKILLHUB_SECURITY_SCANNER_SCAN_PATH", raising=False)

    settings = get_settings()

    assert settings.security_scanner_mode == "upload"
    assert settings.scanner_scan_path == "/scan-upload"


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
    monkeypatch.delenv("SPRING_DATA_REDIS_SENTINEL_MASTER", raising=False)
    monkeypatch.delenv("SPRING_DATA_REDIS_SENTINEL_NODES", raising=False)
    monkeypatch.delenv("SKILLHUB_REDIS_SENTINEL_MASTER", raising=False)
    monkeypatch.delenv("SKILLHUB_REDIS_SENTINEL_NODES", raising=False)
    monkeypatch.setenv("SPRING_DATA_REDIS_HOST", "redis.internal")
    monkeypatch.setenv("SPRING_DATA_REDIS_PORT", "6380")
    monkeypatch.setenv("SPRING_DATA_REDIS_PASSWORD", "redis secret")
    monkeypatch.setenv("SPRING_DATA_REDIS_DATABASE", "2")

    settings = get_settings()

    assert settings.redis_url == "redis://:redis%20secret@redis.internal:6380/2"
    assert settings.redis_mode == "single"


def test_redis_password_falls_back_to_redis_password_env(monkeypatch):
    monkeypatch.delenv("SKILLHUB_REDIS_URL", raising=False)
    monkeypatch.delenv("SPRING_DATA_REDIS_SENTINEL_MASTER", raising=False)
    monkeypatch.delenv("SPRING_DATA_REDIS_SENTINEL_NODES", raising=False)
    monkeypatch.delenv("SKILLHUB_REDIS_SENTINEL_MASTER", raising=False)
    monkeypatch.delenv("SKILLHUB_REDIS_SENTINEL_NODES", raising=False)
    monkeypatch.delenv("SPRING_DATA_REDIS_PASSWORD", raising=False)
    monkeypatch.setenv("REDIS_HOST", "redis.compat")
    monkeypatch.setenv("REDIS_PORT", "6379")
    monkeypatch.setenv("REDIS_PASSWORD", "compat-secret")

    settings = get_settings()

    assert settings.redis_url == "redis://:compat-secret@redis.compat:6379/0"
    assert settings.redis_mode == "single"


def test_redis_url_uses_rediss_for_java_compatible_ssl_flag(monkeypatch):
    monkeypatch.delenv("SKILLHUB_REDIS_URL", raising=False)
    monkeypatch.delenv("SPRING_DATA_REDIS_SENTINEL_MASTER", raising=False)
    monkeypatch.delenv("SPRING_DATA_REDIS_SENTINEL_NODES", raising=False)
    monkeypatch.delenv("SKILLHUB_REDIS_SENTINEL_MASTER", raising=False)
    monkeypatch.delenv("SKILLHUB_REDIS_SENTINEL_NODES", raising=False)
    monkeypatch.setenv("SPRING_DATA_REDIS_HOST", "redis.tls")
    monkeypatch.setenv("SPRING_DATA_REDIS_PORT", "6380")
    monkeypatch.setenv("SPRING_DATA_REDIS_SSL_ENABLED", "true")

    settings = get_settings()

    assert settings.redis_url == "rediss://redis.tls:6380/0"
    assert settings.redis_ssl_enabled is True
    assert settings.redis_mode == "single"


def test_redis_url_includes_acl_username_for_java_compatible_env_names(monkeypatch):
    monkeypatch.delenv("SKILLHUB_REDIS_URL", raising=False)
    monkeypatch.delenv("SPRING_DATA_REDIS_SENTINEL_MASTER", raising=False)
    monkeypatch.delenv("SPRING_DATA_REDIS_SENTINEL_NODES", raising=False)
    monkeypatch.delenv("SKILLHUB_REDIS_SENTINEL_MASTER", raising=False)
    monkeypatch.delenv("SKILLHUB_REDIS_SENTINEL_NODES", raising=False)
    monkeypatch.setenv("SPRING_DATA_REDIS_HOST", "redis.acl")
    monkeypatch.setenv("SPRING_DATA_REDIS_PORT", "6379")
    monkeypatch.setenv("SPRING_DATA_REDIS_USERNAME", "skill hub")
    monkeypatch.setenv("SPRING_DATA_REDIS_PASSWORD", "redis secret")

    settings = get_settings()

    assert settings.redis_url == "redis://skill%20hub:redis%20secret@redis.acl:6379/0"
    assert settings.redis_username == "skill hub"
    assert settings.redis_password == "redis secret"
    assert settings.redis_mode == "single"


def test_redis_sentinel_config_uses_spring_env_names(monkeypatch):
    monkeypatch.delenv("SKILLHUB_REDIS_URL", raising=False)
    monkeypatch.setenv("SPRING_DATA_REDIS_SENTINEL_MASTER", "mymaster")
    monkeypatch.setenv("SPRING_DATA_REDIS_SENTINEL_NODES", "redis-sentinel-1:26379, redis-sentinel-2:26379")
    monkeypatch.setenv("SPRING_DATA_REDIS_SENTINEL_USERNAME", "sentinel-user")
    monkeypatch.setenv("SPRING_DATA_REDIS_SENTINEL_PASSWORD", "sentinel-secret")
    monkeypatch.setenv("SPRING_DATA_REDIS_USERNAME", "skillhub")
    monkeypatch.setenv("SPRING_DATA_REDIS_PASSWORD", "secret")
    monkeypatch.setenv("SPRING_DATA_REDIS_DATABASE", "3")
    monkeypatch.setenv("SPRING_DATA_REDIS_SSL_ENABLED", "true")
    monkeypatch.setenv("SPRING_DATA_REDIS_CONNECT_TIMEOUT", "PT5S")
    monkeypatch.setenv("SPRING_DATA_REDIS_TIMEOUT", "PT3S")

    settings = get_settings()

    assert settings.redis_mode == "sentinel"
    assert settings.redis_sentinel_master == "mymaster"
    assert settings.redis_sentinel_nodes == ["redis-sentinel-1:26379", "redis-sentinel-2:26379"]
    assert settings.redis_sentinel_username == "sentinel-user"
    assert settings.redis_sentinel_password == "sentinel-secret"
    assert settings.redis_username == "skillhub"
    assert settings.redis_password == "secret"
    assert settings.redis_database == 3
    assert settings.redis_ssl_enabled is True
    assert settings.redis_connect_timeout_seconds == 5
    assert settings.redis_timeout_seconds == 3


def test_redis_sentinel_config_accepts_skillhub_aliases(monkeypatch):
    monkeypatch.delenv("SKILLHUB_REDIS_URL", raising=False)
    monkeypatch.delenv("SPRING_DATA_REDIS_SENTINEL_MASTER", raising=False)
    monkeypatch.delenv("SPRING_DATA_REDIS_SENTINEL_NODES", raising=False)
    monkeypatch.setenv("SKILLHUB_REDIS_SENTINEL_MASTER", "skillhub-master")
    monkeypatch.setenv("SKILLHUB_REDIS_SENTINEL_NODES", "sentinel-a:26379,sentinel-b:26379")

    settings = get_settings()

    assert settings.redis_mode == "sentinel"
    assert settings.redis_sentinel_master == "skillhub-master"
    assert settings.redis_sentinel_nodes == ["sentinel-a:26379", "sentinel-b:26379"]


def test_explicit_redis_url_wins_over_sentinel_env(monkeypatch):
    monkeypatch.setenv("SKILLHUB_REDIS_URL", "redis://redis.single:6379/0")
    monkeypatch.setenv("SPRING_DATA_REDIS_SENTINEL_MASTER", "mymaster")
    monkeypatch.setenv("SPRING_DATA_REDIS_SENTINEL_NODES", "redis-sentinel-1:26379")

    settings = get_settings()

    assert settings.redis_mode == "single"
    assert settings.redis_url == "redis://redis.single:6379/0"
    assert settings.redis_sentinel_master == ""
    assert settings.redis_sentinel_nodes == []


def test_explicit_redis_url_with_sentinel_env_logs_override_warning(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="uvicorn.error")
    monkeypatch.setenv("SKILLHUB_REDIS_URL", "redis://redis.single:6379/0")
    monkeypatch.setenv("SPRING_DATA_REDIS_SENTINEL_MASTER", "mymaster")
    monkeypatch.setenv("SPRING_DATA_REDIS_SENTINEL_NODES", "redis-sentinel-1:26379")

    settings = get_settings()

    assert settings.redis_mode == "single"
    assert "SKILLHUB_REDIS_URL is set, Redis Sentinel settings will be ignored" in caplog.text


def test_scan_consumer_block_longer_than_redis_timeout_logs_warning(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="uvicorn.error")
    monkeypatch.setenv("SPRING_DATA_REDIS_TIMEOUT", "PT3S")
    monkeypatch.setenv("SKILLHUB_SCAN_CONSUMER_BLOCK_MS", "4000")

    settings = get_settings()

    assert settings.redis_timeout_seconds == 3
    assert settings.scan_consumer_block_ms == 4000
    assert "SKILLHUB_SCAN_CONSUMER_BLOCK_MS should be lower than Redis socket timeout" in caplog.text


def test_scanner_timeout_settings_fallback_to_defaults(monkeypatch):
    monkeypatch.setenv("SKILLHUB_SECURITY_SCANNER_CONNECT_TIMEOUT_MS", "bad")
    monkeypatch.setenv("SKILLHUB_SECURITY_SCANNER_READ_TIMEOUT_MS", "")

    settings = get_settings()

    assert settings.scanner_connect_timeout_ms == 5000
    assert settings.scanner_read_timeout_ms == 300000

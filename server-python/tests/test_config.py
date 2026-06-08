from app.core.config import DEFAULT_DATABASE_URL, DEFAULT_STORAGE_BASE_PATH, get_settings


def test_default_database_url_matches_local_docker_compose(monkeypatch):
    monkeypatch.delenv("SKILLHUB_DATABASE_URL", raising=False)

    settings = get_settings()

    assert DEFAULT_DATABASE_URL == "postgresql+asyncpg://skillhub:skillhub_dev@localhost:5432/skillhub"
    assert settings.database_url == DEFAULT_DATABASE_URL
    assert settings.storage_base_path == DEFAULT_STORAGE_BASE_PATH


def test_database_url_can_be_overridden(monkeypatch):
    monkeypatch.setenv("SKILLHUB_DATABASE_URL", "postgresql+asyncpg://user:pass@example.test:5432/db")

    settings = get_settings()

    assert settings.database_url == "postgresql+asyncpg://user:pass@example.test:5432/db"


def test_storage_base_path_can_be_overridden(monkeypatch):
    monkeypatch.setenv("SKILLHUB_STORAGE_BASE_PATH", "C:/tmp/skillhub-storage")

    settings = get_settings()

    assert settings.storage_base_path == "C:/tmp/skillhub-storage"


def test_scanner_handoff_settings_can_be_overridden(monkeypatch):
    monkeypatch.setenv("SKILLHUB_SECURITY_SCANNER_ENABLED", "true")
    monkeypatch.setenv("SKILLHUB_SECURITY_SCANNER_MODE", "upload")
    monkeypatch.setenv("SKILLHUB_REDIS_URL", "redis://redis.test:6380")
    monkeypatch.setenv("SKILLHUB_SCAN_STREAM_KEY", "custom:scan:requests")

    settings = get_settings()

    assert settings.security_scanner_enabled is True
    assert settings.security_scanner_mode == "upload"
    assert settings.redis_url == "redis://redis.test:6380"
    assert settings.scan_stream_key == "custom:scan:requests"

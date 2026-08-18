from pathlib import Path

import pytest

from skillhub_oss_importer.config import Config, ConfigError


def valid_env(tmp_path: Path) -> dict[str, str]:
    return {
        "SKILLHUB_BASE_URL": "https://skillhub.example/skillhub/",
        "SKILLHUB_API_TOKEN": "secret-token",
        "SKILLHUB_SOURCE_REPOSITORY_URL": "https://github.com/MattPocock/Skills.git",
        "SKILLHUB_NAMESPACE_OWNER_PROVIDER_CODE": "keycloak",
        "SKILLHUB_NAMESPACE_OWNER_LOGIN_NAME": "platform-owner",
        "CI_PROJECT_DIR": str(tmp_path),
        "CI_COMMIT_SHA": "A" * 40,
        "CI_COMMIT_BRANCH": "main",
    }


def test_reads_required_contract_and_preserves_subpath(tmp_path: Path) -> None:
    config = Config.from_env(valid_env(tmp_path))

    assert config.base_url == "https://skillhub.example/skillhub"
    assert config.repository_url == "https://github.com/mattpocock/skills"
    assert config.namespace_slug == "oss-mattpocock-skills"
    assert config.namespace_display_name == "OSS-mattpocock-skills"
    assert config.commit_sha == "a" * 40
    assert config.ref_type == "BRANCH"
    assert config.source_ref == "main"
    assert config.trigger_provider_code == "keycloak"
    assert "secret-token" not in repr(config)


def test_requires_every_required_variable(tmp_path: Path) -> None:
    env = valid_env(tmp_path)
    del env["SKILLHUB_API_TOKEN"]
    with pytest.raises(ConfigError, match="SKILLHUB_API_TOKEN"):
        Config.from_env(env)


def test_rejects_source_root_outside_checkout(tmp_path: Path) -> None:
    env = valid_env(tmp_path)
    env["SKILLHUB_IMPORT_SOURCE_ROOT"] = str(tmp_path.parent)
    with pytest.raises(ConfigError, match="within CI_PROJECT_DIR"):
        Config.from_env(env)

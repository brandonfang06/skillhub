from pathlib import Path

import pytest

from skillhub_oss_importer.config import Config, ConfigError

HANDOFF_VARIABLES = (
    "SKILLHUB_SOURCE_REPOSITORY_URL",
    "SKILLHUB_SOURCE_COMMIT_SHA",
    "SKILLHUB_SOURCE_REF_TYPE",
    "SKILLHUB_SOURCE_REF",
    "SKILLHUB_DEV_GITLAB_REPOSITORY_URL",
    "SKILLHUB_DEV_GITLAB_COMMIT_SHA",
    "SKILLHUB_SOURCE_SCAN_STATUS",
    "SKILLHUB_SOURCE_SCAN_COMMIT_SHA",
    "SKILLHUB_SOURCE_SCAN_ID",
)


def write_handoff(tmp_path: Path, env: dict[str, str]) -> None:
    content = "\n".join(f"{name}={env[name]}" for name in HANDOFF_VARIABLES if name in env) + "\n"
    (tmp_path / "pull-code.env").write_text(content, encoding="utf-8")


def set_handoff_value(tmp_path: Path, env: dict[str, str], name: str, value: str) -> None:
    env[name] = value
    write_handoff(tmp_path, env)


def valid_env(tmp_path: Path) -> dict[str, str]:
    env = {
        "SKILLHUB_BASE_URL": "https://skillhub.example/skillhub/",
        "SKILLHUB_SERVICE_TOKEN": "st_secret-token",
        "SKILLHUB_SOURCE_REPOSITORY_URL": "https://github.com/MattPocock/Skills.git",
        "SKILLHUB_SOURCE_COMMIT_SHA": "B" * 40,
        "SKILLHUB_SOURCE_REF_TYPE": "BRANCH",
        "SKILLHUB_SOURCE_REF": "main",
        "SKILLHUB_DEV_GITLAB_REPOSITORY_URL": (
            "https://gitlab.internal/dev/oss-mattpocock-skills.git"
        ),
        "SKILLHUB_DEV_GITLAB_COMMIT_SHA": "A" * 40,
        "SKILLHUB_SOURCE_SCAN_STATUS": "PASSED",
        "SKILLHUB_SOURCE_SCAN_COMMIT_SHA": "A" * 40,
        "SKILLHUB_SOURCE_SCAN_ID": "scan-123",
        "SKILLHUB_NAMESPACE_OWNER_PROVIDER_CODE": "keycloak",
        "SKILLHUB_NAMESPACE_OWNER_LOGIN_NAME": "platform-owner",
        "CI_PROJECT_DIR": str(tmp_path),
        "CI_JOB_TOKEN": "job-secret",
    }
    write_handoff(tmp_path, env)
    return env


def test_reads_required_contract_and_preserves_subpath(tmp_path: Path) -> None:
    config = Config.from_env(valid_env(tmp_path))

    assert config.base_url == "https://skillhub.example/skillhub"
    assert config.repository_url == "https://github.com/mattpocock/skills"
    assert config.namespace_slug == "oss-mattpocock-skills"
    assert config.namespace_display_name == "OSS-mattpocock-skills"
    assert config.project_dir == tmp_path.resolve()
    assert config.source_subdirectory == Path(".")
    assert config.source_clone_url == "https://gitlab.internal/dev/oss-mattpocock-skills.git"
    assert config.dev_gitlab_commit_sha == "a" * 40
    assert config.source_commit_sha == "b" * 40
    assert config.ref_type == "BRANCH"
    assert config.source_ref == "main"
    assert config.scan_status == "PASSED"
    assert config.scan_commit_sha == "a" * 40
    assert config.scan_id == "scan-123"
    assert config.trigger_provider_code == "keycloak"
    assert "secret-token" not in repr(config)
    assert "job-secret" not in repr(config)


def test_requires_every_required_variable(tmp_path: Path) -> None:
    env = valid_env(tmp_path)
    del env["SKILLHUB_SERVICE_TOKEN"]
    env["SKILLHUB_API_TOKEN"] = "sk_personal-must-not-fallback"
    with pytest.raises(ConfigError, match="SKILLHUB_SERVICE_TOKEN"):
        Config.from_env(env)


def test_rejects_source_root_that_is_not_relative_to_the_cloned_repository(tmp_path: Path) -> None:
    env = valid_env(tmp_path)
    env["SKILLHUB_IMPORT_SOURCE_ROOT"] = str(tmp_path.parent)
    with pytest.raises(ConfigError, match="relative path"):
        Config.from_env(env)


def test_uses_the_explicit_upstream_tag_as_the_source_ref(tmp_path: Path) -> None:
    env = valid_env(tmp_path)
    set_handoff_value(tmp_path, env, "SKILLHUB_SOURCE_REF_TYPE", "TAG")
    set_handoff_value(tmp_path, env, "SKILLHUB_SOURCE_REF", "v1.2.3")

    config = Config.from_env(env)

    assert config.ref_type == "TAG"
    assert config.source_ref == "v1.2.3"


def test_does_not_fallback_to_the_central_pipeline_repository(tmp_path: Path) -> None:
    env = valid_env(tmp_path)
    del env["SKILLHUB_DEV_GITLAB_REPOSITORY_URL"]
    write_handoff(tmp_path, env)
    env["CI_REPOSITORY_URL"] = "https://gitlab.internal/platform/pull-pipeline.git"
    env["CI_COMMIT_SHA"] = "C" * 40

    with pytest.raises(ConfigError, match="SKILLHUB_DEV_GITLAB_REPOSITORY_URL"):
        Config.from_env(env)


@pytest.mark.parametrize("status", ["", "FAILED", "WARNING", "passed"])
def test_requires_an_explicit_passed_scan_status(tmp_path: Path, status: str) -> None:
    env = valid_env(tmp_path)
    set_handoff_value(tmp_path, env, "SKILLHUB_SOURCE_SCAN_STATUS", status)

    with pytest.raises(ConfigError, match="SKILLHUB_SOURCE_SCAN_STATUS must be PASSED"):
        Config.from_env(env)


def test_rejects_scan_for_a_different_dev_gitlab_commit(tmp_path: Path) -> None:
    env = valid_env(tmp_path)
    set_handoff_value(tmp_path, env, "SKILLHUB_SOURCE_SCAN_COMMIT_SHA", "C" * 40)

    with pytest.raises(ConfigError, match="scan commit must match"):
        Config.from_env(env)


def test_requires_ref_for_branch_and_tag_but_not_commit(tmp_path: Path) -> None:
    env = valid_env(tmp_path)
    set_handoff_value(tmp_path, env, "SKILLHUB_SOURCE_REF", "")
    with pytest.raises(ConfigError, match="SKILLHUB_SOURCE_REF is required"):
        Config.from_env(env)

    set_handoff_value(tmp_path, env, "SKILLHUB_SOURCE_REF_TYPE", "COMMIT")
    config = Config.from_env(env)
    assert config.source_ref is None


def test_rejects_environment_override_of_the_pull_code_artifact(tmp_path: Path) -> None:
    env = valid_env(tmp_path)
    env["SKILLHUB_DEV_GITLAB_COMMIT_SHA"] = "C" * 40

    with pytest.raises(ConfigError, match="conflicts with pull-code.env"):
        Config.from_env(env)


def test_requires_the_pull_code_artifact_in_the_central_checkout(tmp_path: Path) -> None:
    env = valid_env(tmp_path)
    (tmp_path / "pull-code.env").unlink()

    with pytest.raises(ConfigError, match="pull-code.env"):
        Config.from_env(env)


def test_rejects_unencrypted_dev_gitlab_clone_url(tmp_path: Path) -> None:
    env = valid_env(tmp_path)
    set_handoff_value(
        tmp_path,
        env,
        "SKILLHUB_DEV_GITLAB_REPOSITORY_URL",
        "http://gitlab.internal/dev/skills.git",
    )

    with pytest.raises(ConfigError, match="credential-free absolute HTTPS URL"):
        Config.from_env(env)


def test_rejects_control_characters_in_the_pull_code_artifact(tmp_path: Path) -> None:
    env = valid_env(tmp_path)
    handoff = tmp_path / "pull-code.env"
    handoff.write_bytes(handoff.read_bytes().replace(b"scan-123", b"scan-\x00hidden"))

    with pytest.raises(ConfigError, match="control characters"):
        Config.from_env(env)


def test_rejects_unknown_and_duplicate_pull_code_variables(tmp_path: Path) -> None:
    env = valid_env(tmp_path)
    handoff = tmp_path / "pull-code.env"
    with handoff.open("a", encoding="utf-8") as stream:
        stream.write("CI_JOB_TOKEN=must-not-be-an-artifact\n")
    with pytest.raises(ConfigError, match="Unexpected pull-code.env variable"):
        Config.from_env(env)

    write_handoff(tmp_path, env)
    with handoff.open("a", encoding="utf-8") as stream:
        stream.write("SKILLHUB_SOURCE_SCAN_STATUS=PASSED\n")
    with pytest.raises(ConfigError, match="Duplicate pull-code.env variable"):
        Config.from_env(env)


def test_rejects_oversized_pull_code_artifact(tmp_path: Path) -> None:
    env = valid_env(tmp_path)
    (tmp_path / "pull-code.env").write_bytes(b"x" * (64 * 1024 + 1))

    with pytest.raises(ConfigError, match="exceeds 64 KiB"):
        Config.from_env(env)

import os
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised by the Python 3.8 gate
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[3]


def test_gitlab_template_runs_the_project_local_python_importer() -> None:
    template = (ROOT / "deploy" / "gitlab" / "oss-source-import.yml").read_text(encoding="utf-8")

    assert 'name: "$SKILLHUB_PYTHON_IMAGE"' in template
    assert 'entrypoint: [""]' in template
    assert '/bin/sh "$CI_PROJECT_DIR/deploy/gitlab/oss-source-import.sh"' in template
    assert "stage: publish_skillhub" in template
    assert "needs:\n    - job: pull_code\n      artifacts: true" in template
    assert "when: always" in template
    assert '- "$SKILLHUB_IMPORT_REPORT_PATH"' in template
    assert "pip install" not in template
    assert "curl " not in template
    assert ":latest" not in template
    assert "SKILLHUB_IMPORTER_IMAGE" not in template
    assert "skillhub-oss-import --json-report" not in template
    assert "allow_failure" not in template


def test_shell_wrapper_calls_project_python_without_runtime_installation() -> None:
    wrapper_path = ROOT / "deploy" / "gitlab" / "oss-source-import.sh"
    wrapper = wrapper_path.read_text(encoding="utf-8")

    assert b"\r\n" not in wrapper_path.read_bytes()
    assert "pip install" not in wrapper
    assert "requirements-runtime.txt" not in wrapper
    assert "SKILLHUB_IMPORT_RUNTIME_DIR" not in wrapper
    assert "command -v python" in wrapper
    assert "command -v git" in wrapper
    assert 'python "$CI_PROJECT_DIR/tools/oss-source-importer/run_import.py"' in wrapper
    assert "curl " not in wrapper
    assert "skillhub-oss-import --json-report" not in wrapper


def test_template_documents_required_pipeline_variables() -> None:
    template = (ROOT / "deploy" / "gitlab" / "oss-source-import.yml").read_text(encoding="utf-8")
    for name in (
        "SKILLHUB_PYTHON_IMAGE",
        "SKILLHUB_BASE_URL",
        "SKILLHUB_SERVICE_TOKEN",
        "SKILLHUB_SOURCE_REPOSITORY_URL",
        "SKILLHUB_SOURCE_REF_TYPE",
        "SKILLHUB_DEV_GITLAB_REPOSITORY_URL",
        "SKILLHUB_DEV_GITLAB_BRANCH",
        "SKILLHUB_SOURCE_SCAN_STATUS",
        "SKILLHUB_NAMESPACE_OWNER_LOGIN_NAME",
        "CI_JOB_TOKEN",
    ):
        assert name in template
    assert "SKILLHUB_NAMESPACE_OWNER_PROVIDER_CODE" not in template
    assert "CI_REPOSITORY_URL" not in template
    assert "CI_COMMIT_SHA" not in template
    assert "SKILLHUB_SOURCE_COMMIT_SHA" not in template
    assert "SKILLHUB_DEV_GITLAB_COMMIT_SHA" not in template
    assert "SKILLHUB_SOURCE_SCAN_COMMIT_SHA" not in template


def test_project_runner_uses_only_the_python_standard_library_at_runtime() -> None:
    project = tomllib.loads(
        (ROOT / "tools" / "oss-source-importer" / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert project["project"]["dependencies"] == []
    assert project["project"]["requires-python"] == ">=3.8"
    assert not (ROOT / "tools" / "oss-source-importer" / "requirements-runtime.txt").exists()
    assert not (ROOT / "tools" / "oss-source-importer" / "Dockerfile").exists()

    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            sys.executable,
            "-S",
            str(ROOT / "tools" / "oss-source-importer" / "run_import.py"),
            "--help",
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
        env=environment,
    )
    assert result.returncode == 0, result.stderr


def test_smoke_separates_the_central_pipeline_checkout_from_the_dev_source() -> None:
    smoke = (ROOT / "scripts" / "oss-source-import-smoke-test.ps1").read_text(encoding="utf-8")
    assert '"python:3.8-bookworm"' in smoke
    assert ":/pipeline:ro" in smoke
    assert ":/dev-source:ro" in smoke
    assert "CI_PROJECT_DIR=/pipeline" in smoke
    assert "SKILLHUB_DEV_GITLAB_REPOSITORY_URL=" in smoke
    assert "SKILLHUB_DEV_GITLAB_BRANCH=main" in smoke
    assert "SKILLHUB_SOURCE_SCAN_STATUS=PASSED" in smoke
    assert "SKILLHUB_SOURCE_COMMIT_SHA=" not in smoke
    assert "SKILLHUB_DEV_GITLAB_COMMIT_SHA=" not in smoke
    assert "SKILLHUB_SOURCE_SCAN_COMMIT_SHA=" not in smoke
    assert "SKILLHUB_NAMESPACE_OWNER_PROVIDER_CODE" not in smoke
    assert "$internalRepositoryCredentialedUrl" in smoke
    assert "$jobLogLines" in smoke
    assert '"event=importer_started"' in smoke
    assert '"event=import_completed"' in smoke
    assert '"event=importer_finished"' in smoke
    assert "GitLab job log leaked a credential" in smoke
    assert '${pipeline}:/pipeline:ro' in smoke
    assert 'Join-Path $pipeline "pull-code.env"' in smoke
    assert "requirements-runtime.txt" not in smoke
    assert "pip install" not in smoke
